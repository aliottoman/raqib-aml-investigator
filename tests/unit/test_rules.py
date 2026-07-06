from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import config
from src import bankdb, rules
from tests.helpers import add_cash_deposit, build_minimal_ledger


pytestmark = pytest.mark.unit


def test_flagship_screening_is_exact_and_explainable():
    result = rules.run_screening()

    assert result["customers_scanned"] == 9
    assert result["transactions_scanned"] == 508
    assert [(a["id"], a["rule"], a["severity"]) for a in result["alerts"]] == [
        ("RQB-2026-0347", "CASH-VELOCITY-04", "critical"),
        ("RQB-2026-0357", "WATCHLIST-PROX-01", "high"),
        ("RQB-2026-0364", "PROFILE-DEVIATION-02", "medium"),
        ("RQB-2026-0371", "DORMANT-SPIKE-03", "low"),
    ]

    cash = result["alerts"][0]
    assert cash["customer_id"] == bankdb.CUSTOMER_ID
    assert {
        "deposits": 14,
        "branches": 4,
        "aggregate_aed": 484_829.01,
    }.items() <= cash["evidence"].items()
    assert cash["evidence"]["first_date"] == "2026-06-08"
    assert cash["evidence"]["last_date"] == "2026-06-18"
    assert cash["evidence"]["business_days"] == 9
    assert cash["evidence"]["threshold_aed"] == bankdb.THRESHOLD_AED
    assert "AED ~485k" in cash["summary"]


def test_screening_is_idempotent_and_preserves_workflow_status():
    rules.run_screening()
    with closing(sqlite3.connect(config.DB_PATH)) as con:
        con.execute("UPDATE alerts SET status='investigating' WHERE id=?", (bankdb.ALERT_ID,))
        con.commit()

    first = rules.run_screening()
    second = rules.run_screening()
    assert first["alerts"] == second["alerts"]

    with closing(sqlite3.connect(config.DB_PATH)) as con:
        rows = con.execute("SELECT id, status FROM alerts ORDER BY id").fetchall()
    assert len(rows) == 4
    assert dict(rows)[bankdb.ALERT_ID] == "investigating"


def test_cash_velocity_detects_three_branches_inside_ten_business_days(tmp_path: Path):
    con = build_minimal_ledger(tmp_path / "inside-window.sqlite3")
    add_cash_deposit(con, "2026-06-08", branch="Deira")
    add_cash_deposit(con, "2026-06-12", branch="Jebel Ali")
    add_cash_deposit(con, "2026-06-18", branch="Al Barsha")

    alerts = rules._cash_velocity(con)
    con.close()

    assert len(alerts) == 1
    assert alerts[0]["customer_id"] == 2001
    assert alerts[0]["evidence"]["deposits"] == 3


def test_cash_velocity_does_not_aggregate_across_separate_windows(tmp_path: Path):
    con = build_minimal_ledger(tmp_path / "outside-window.sqlite3")
    add_cash_deposit(con, "2026-06-01", branch="Deira")
    add_cash_deposit(con, "2026-06-15", branch="Jebel Ali")
    add_cash_deposit(con, "2026-06-26", branch="Al Barsha")

    alerts = rules._cash_velocity(con)
    con.close()

    assert alerts == [], "Deposits outside one rolling 10-business-day window must not be combined"


def test_cash_velocity_excludes_at_or_above_reporting_threshold(tmp_path: Path):
    con = build_minimal_ledger(tmp_path / "threshold.sqlite3")
    add_cash_deposit(con, "2026-06-08", branch="Deira")
    add_cash_deposit(con, "2026-06-09", branch="Jebel Ali")
    add_cash_deposit(con, "2026-06-10", branch="Al Barsha", amount=bankdb.THRESHOLD_AED)

    alerts = rules._cash_velocity(con)
    con.close()

    assert alerts == []


def test_rule_ids_are_stable_and_rule_scoped():
    assert rules._alert_id("CASH-VELOCITY-04", 1017) == bankdb.ALERT_ID
    assert rules._alert_id("WATCHLIST-PROX-01", 1017) != bankdb.ALERT_ID
    assert len({rules._alert_id(rule["rule"], 1017) for rule in rules.RULE_META}) == 4
