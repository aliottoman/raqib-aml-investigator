from __future__ import annotations

import json

import pytest

from src import bankdb, rules
from src.schemas import SARReport
from tests.conftest import DEMO_TAPE


pytestmark = pytest.mark.eval


def test_recorded_event_tape_has_monotonic_timing_and_valid_terminal_report():
    events = json.loads(DEMO_TAPE.read_text(encoding="utf-8"))
    times = [float(event.get("_t", 0)) for event in events]
    assert times == sorted(times)
    assert events[0]["type"] == "case_opened"
    assert events[-1]["type"] == "done"
    assert sum(event["type"] == "sar" for event in events) == 1
    SARReport.model_validate(next(e["report"] for e in events if e["type"] == "sar"))


def test_recorded_tool_events_are_correlated():
    events = json.loads(DEMO_TAPE.read_text(encoding="utf-8"))
    calls = {e["id"]: e for e in events if e["type"] == "tool_call"}
    results = {e["id"]: e for e in events if e["type"] == "tool_result"}
    approvals = {e["id"] for e in events if e["type"] == "approval_request"}
    approval_results = {e["id"] for e in events if e["type"] == "approval_result"}

    assert calls
    assert calls.keys() == results.keys()
    assert approvals == approval_results
    assert approvals <= calls.keys()
    assert all(calls[event_id]["name"] == results[event_id]["name"] for event_id in calls)


def test_flagship_report_reconciles_to_ledger(golden_sar):
    screening = rules.run_screening()
    cash_alert = next(a for a in screening["alerts"] if a["id"] == bankdb.ALERT_ID)
    ledger = bankdb.execute_readonly(
        "SELECT COUNT(*) AS deposits, ROUND(SUM(amount_aed), 2) AS cash_total "
        "FROM transactions WHERE account_id=5001 AND type='cash_deposit' "
        "AND ts BETWEEN '2026-06-01' AND '2026-06-30 23:59:59'"
    )["rows"][0]
    wires = bankdb.execute_readonly(
        "SELECT ROUND(SUM(-amount_aed), 2) AS wire_total FROM transactions "
        "WHERE account_id=5001 AND type='wire_out' AND ts >= '2026-06-01'"
    )["rows"][0]

    assert ledger["deposits"] == cash_alert["evidence"]["deposits"] == 14
    assert ledger["cash_total"] == cash_alert["evidence"]["aggregate_aed"]
    assert golden_sar["total_amount_aed"] == pytest.approx(ledger["cash_total"], abs=1.0)
    assert sum(cp["total_aed"] for cp in golden_sar["counterparties"]) == pytest.approx(
        wires["wire_total"]
    )


def test_flagship_report_contains_required_grounding_signals(golden_sar):
    assert golden_sar["case_id"] == bankdb.ALERT_ID
    assert golden_sar["subject"] == "Al Rashidi Trading FZE"
    assert golden_sar["period"] == "2026-06-08 to 2026-06-19"
    assert any(cp["watchlist_hit"] for cp in golden_sar["counterparties"])
    assert any("§4.2" in section for section in golden_sar["policy_sections_engaged"])
    assert any("prompt injection" in finding.lower() for finding in golden_sar["key_findings"])
    assert "484829" in golden_sar["narrative"]
    assert golden_sar["narrative_ar"].strip()

