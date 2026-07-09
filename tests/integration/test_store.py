from __future__ import annotations

import importlib
import sqlite3
from contextlib import closing

import pytest

import config
from src import bankdb, rules, store


pytestmark = pytest.mark.integration


@pytest.fixture
def screened_cases():
    rules.run_screening()
    return store.list_cases()


def test_product_schema_is_additive_idempotent_and_preserves_ledger():
    before = bankdb.execute_readonly("SELECT COUNT(*) AS n FROM transactions")["rows"][0]["n"]
    store.ensure_schema()
    store.ensure_schema()

    with closing(sqlite3.connect(config.DB_PATH)) as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        migration_count = con.execute("SELECT COUNT(*) FROM app_migrations").fetchone()[0]

    assert before == 1079
    assert bankdb.execute_readonly("SELECT COUNT(*) AS n FROM transactions")["rows"][0]["n"] == before
    assert {
        "cases", "investigation_runs", "case_events", "case_notes", "approvals",
        "sar_versions", "rule_configs", "rule_runs",
    } <= tables
    assert migration_count == 1


def test_screening_syncs_persistent_cases(screened_cases):
    # The four curated cases plus one per rule from the portfolio extension.
    assert {case["id"] for case in screened_cases} == {
        "RQB-2026-0347", "RQB-2026-0357", "RQB-2026-0364", "RQB-2026-0371",
        "RQB-2026-0401", "RQB-2026-0422", "RQB-2026-0428", "RQB-2026-0444",
        "RQB-2026-0455",
    }
    flagship = store.get_case(bankdb.ALERT_ID)
    assert flagship["customer_name"] == "Al Rashidi Trading FZE"
    assert flagship["priority"] == "urgent"
    assert flagship["evidence"]["deposits"] == 14


def test_notes_are_normalized_persisted_and_audited(screened_cases):
    note = store.add_note(bankdb.ALERT_ID, "  Review   Meridian\nownership  ", "analyst")
    assert note["text"] == "Review Meridian ownership"
    assert note["actor_role"] == "analyst"

    # Reloading the repository module must not lose state.
    reloaded = importlib.reload(store)
    case = reloaded.get_case(bankdb.ALERT_ID)
    assert case["notes"][0]["text"] == "Review Meridian ownership"

    events = reloaded.list_events(bankdb.ALERT_ID)
    assert events[-1]["type"] == "note_added"
    assert events[-1]["payload"]["note"]["id"] == note["id"]


@pytest.mark.parametrize("text", ["", " \n\t ", "x" * 2001])
def test_invalid_notes_are_rejected_without_partial_writes(screened_cases, text: str):
    with pytest.raises(ValueError):
        store.add_note(bankdb.ALERT_ID, text, "analyst")
    assert store.get_case(bankdb.ALERT_ID)["notes"] == []
    assert store.list_events(bankdb.ALERT_ID) == []


def test_assign_and_reprioritize_are_normalized_and_audited(screened_cases):
    assigned = store.assign_case(bankdb.ALERT_ID, "  Sara   Al Maktoum ", "analyst")
    assert assigned["owner"] == "Sara Al Maktoum"
    reprioritized = store.reprioritize_case(bankdb.ALERT_ID, "high", "analyst")
    assert reprioritized["priority"] == "high"

    case_events = store.list_events(bankdb.ALERT_ID)
    events = {e["type"] for e in case_events}
    assert {"case_assigned", "case_reprioritized"} <= events
    assignment = next(event for event in case_events if event["type"] == "case_assigned")
    assert assignment["payload"] == {
        "from": "AML Investigations",
        "to": "Sara Al Maktoum",
        "owner": "Sara Al Maktoum",
    }

    with pytest.raises(ValueError):
        store.assign_case(bankdb.ALERT_ID, "   ", "analyst")
    with pytest.raises(ValueError):
        store.reprioritize_case(bankdb.ALERT_ID, "urgentt", "analyst")


def test_apply_bulk_updates_valid_cases_and_collects_skips(screened_cases):
    ids = ["RQB-2026-0347", "RQB-2026-0401", "NO-SUCH-CASE"]
    result = store.apply_bulk(ids, "assign", actor_role="analyst", owner="Triage Desk A")

    assert set(result["updated"]) == {"RQB-2026-0347", "RQB-2026-0401"}
    assert result["skipped"] == [{"case_id": "NO-SUCH-CASE", "reason": "unknown case"}]
    assert result["updated_count"] == 2 and result["skipped_count"] == 1
    assert store.get_case("RQB-2026-0347")["owner"] == "Triage Desk A"


def test_apply_bulk_transition_respects_separation_of_duties(screened_cases):
    # A reviewer cannot start an investigation — skipped, not applied.
    blocked = store.apply_bulk(["RQB-2026-0347"], "transition",
                               actor_role="reviewer", status="investigating")
    assert blocked["updated"] == []
    assert blocked["skipped"][0]["case_id"] == "RQB-2026-0347"
    assert store.get_case("RQB-2026-0347")["status"] == "open"

    # An analyst can bulk-close false positives with a reason.
    closed = store.apply_bulk(["RQB-2026-0401", "RQB-2026-0455"], "transition",
                              actor_role="analyst", status="closed", reason="false positive")
    assert set(closed["updated"]) == {"RQB-2026-0401", "RQB-2026-0455"}
    assert store.get_case("RQB-2026-0401")["status"] == "closed"

    with pytest.raises(ValueError, match="rationale"):
        store.apply_bulk([bankdb.ALERT_ID], "transition", actor_role="analyst", status="closed")
    assert store.get_case(bankdb.ALERT_ID)["status"] == "open"


def test_reset_demo_reopens_resolved_cases_and_preserves_history(screened_cases):
    # Resolve two of the high-severity cases and leave a note behind.
    store.apply_bulk(["RQB-2026-0347", "RQB-2026-0357"], "transition",
                     actor_role="analyst", status="closed", reason="worked and closed")
    store.add_note("RQB-2026-0347", "keep this note", "analyst")
    assert store.get_case("RQB-2026-0347")["status"] == "closed"

    result = store.reset_demo(actor_role="rule_admin")

    assert set(result["reopened"]) == {"RQB-2026-0347", "RQB-2026-0357"}
    assert result["reopened_count"] == 2
    reopened = store.get_case("RQB-2026-0347")
    assert reopened["status"] == "open"
    assert reopened["alert_status"] == "open"
    assert store.get_case("RQB-2026-0357")["status"] == "open"
    # History is preserved — the reset rewinds status only, it deletes nothing.
    assert any(note["text"] == "keep this note" for note in reopened["notes"])
    # Idempotent: with the queue already open, a second reset reopens nothing.
    assert store.reset_demo(actor_role="rule_admin") == {"reopened": [], "reopened_count": 0}


def test_case_transitions_enforce_state_machine_and_separation_of_duties(screened_cases):
    investigating = store.transition_case(
        bankdb.ALERT_ID, "investigating", "Started review", "analyst"
    )
    assert investigating["status"] == "investigating"
    assert investigating["alert_status"] == "investigating"

    with pytest.raises(ValueError, match="Cannot transition"):
        store.transition_case(bankdb.ALERT_ID, "approved", None, "reviewer")

    with pytest.raises(PermissionError, match="reviewer"):
        store.transition_case(bankdb.ALERT_ID, "approved", None, "analyst", force=True)

    with pytest.raises(ValueError, match="rationale"):
        store.transition_case(bankdb.ALERT_ID, "closed", None, "analyst")


def test_runs_and_events_survive_reconnect_and_support_cursor_paging(screened_cases):
    run = store.start_run(bankdb.ALERT_ID, "demo", "analyst")
    first = store.append_event(
        bankdb.ALERT_ID, "step", {"n": 1}, run_id=run["id"], actor_role="analyst"
    )
    second = store.append_event(
        bankdb.ALERT_ID,
        "tool_call",
        {"name": "search_aml_policy"},
        run_id=run["id"],
        actor_role="analyst",
        call_id="call-1",
    )
    store.update_run(run["id"], status="completed", current_step=1)

    all_events = store.list_events(bankdb.ALERT_ID)
    resumed = store.list_events(bankdb.ALERT_ID, after=first)
    case = store.get_case(bankdb.ALERT_ID)

    assert [event["id"] for event in resumed] == [second]
    assert resumed[0]["call_id"] == "call-1"
    assert case["latest_run"]["id"] == run["id"]
    assert case["latest_run"]["status"] == "completed"
    assert all_events == sorted(all_events, key=lambda event: event["id"])


def test_list_runs_and_get_run_expose_run_lifecycle(screened_cases):
    first = store.start_run(bankdb.ALERT_ID, "demo", "analyst")
    second = store.start_run(bankdb.ALERT_ID, "live", "analyst")
    store.update_run(second["id"], status="completed", current_step=3)

    runs = store.list_runs(bankdb.ALERT_ID)
    assert {run["id"] for run in runs} == {first["id"], second["id"]}
    assert store.get_run(second["id"])["status"] == "completed"
    assert store.get_run(second["id"])["current_step"] == 3
    with pytest.raises(KeyError):
        store.get_run("run_does_not_exist")


def test_reconcile_stale_runs_closes_orphaned_running_records(screened_cases):
    orphan = store.start_run(bankdb.ALERT_ID, "live", "analyst")
    finished = store.start_run(bankdb.ALERT_ID, "demo", "analyst")
    store.update_run(finished["id"], status="completed")

    # A run left "running" cannot have a live driver after a process restart.
    reconciled = store.reconcile_stale_runs()

    assert reconciled == 1
    assert store.get_run(orphan["id"])["status"] == "interrupted"
    assert store.get_run(orphan["id"])["completed_at"]
    assert store.get_run(finished["id"])["status"] == "completed"
    # Idempotent: a second pass finds nothing left running.
    assert store.reconcile_stale_runs() == 0


def test_approval_is_bound_to_run_and_call_and_cannot_be_decided_twice(screened_cases):
    run = store.start_run(bankdb.ALERT_ID, "live", "analyst")
    store.request_approval(
        bankdb.ALERT_ID, run["id"], "call-7", "SELECT 7", "Validate a fact"
    )

    assert store.decide_approval(run["id"], "call-7", True, "analyst") is True
    assert store.decide_approval(run["id"], "call-7", False, "analyst") is False
    assert store.decide_approval(run["id"], "different-call", True, "analyst") is False


@pytest.mark.security
def test_decided_approval_cannot_be_reopened_by_replaying_request(screened_cases):
    run = store.start_run(bankdb.ALERT_ID, "live", "analyst")
    args = (bankdb.ALERT_ID, run["id"], "call-replay", "SELECT 1", "One-time check")
    store.request_approval(*args)
    assert store.decide_approval(run["id"], "call-replay", True, "analyst") is True

    store.request_approval(*args)
    assert store.decide_approval(run["id"], "call-replay", False, "analyst") is False


def test_sars_are_case_scoped_versioned_and_do_not_imply_filing(screened_cases, golden_sar):
    first_case = bankdb.ALERT_ID
    second_case = "RQB-2026-0357"
    pii = [{"label": "PERSON", "text": "Example", "score": 0.91}]

    first = store.save_sar(first_case, golden_sar, actor_role="analyst", pii_hits=pii)
    assert first["version"] == 1
    assert first["status"] == "draft"
    assert first["pii_hits"] == pii
    assert store.get_case(first_case)["status"] == "draft_ready"
    assert store.get_case(first_case)["alert_status"] == "sar_draft"

    with pytest.raises(KeyError):
        store.get_sar(second_case)

    second_report = dict(golden_sar, case_id=second_case, subject="Second Customer")
    second = store.save_sar(second_case, second_report, actor_role="analyst")
    assert second["report"]["case_id"] == second_case
    assert store.get_sar(first_case)["report"]["subject"] == "Al Rashidi Trading FZE"

    revised = dict(golden_sar, pattern_type="Revised pattern description")
    version_two = store.save_sar(first_case, revised, actor_role="analyst")
    assert version_two["version"] == 2
    assert version_two["report"]["pattern_type"] == "Revised pattern description"


def test_sar_submit_and_reviewer_decision_are_persistent(screened_cases, golden_sar):
    store.save_sar(bankdb.ALERT_ID, golden_sar, actor_role="analyst")
    submitted = store.submit_sar(bankdb.ALERT_ID, "analyst")
    assert submitted["status"] == "pending_review"
    assert submitted["submitted_at"]

    approved = store.review_sar(
        bankdb.ALERT_ID, "approved", "Evidence supports filing", "reviewer"
    )
    assert approved["status"] == "approved"
    assert approved["reviewed_by_role"] == "reviewer"
    assert approved["review_comment"] == "Evidence supports filing"
    assert store.get_case(bankdb.ALERT_ID)["status"] == "approved"

    with pytest.raises(ValueError, match="submitted"):
        store.review_sar(bankdb.ALERT_ID, "changes_requested", None, "reviewer")


def test_rule_configuration_is_versioned_and_simulation_does_not_persist_alerts(screened_cases):
    rule_id = "CASH-VELOCITY-04"
    current = store.get_rule_config(rule_id)
    changed = store.update_rule_config(
        rule_id,
        enabled=True,
        parameters={"minimum_deposits": 15},
        actor_role="rule_admin",
    )
    assert changed["version"] == current["version"] + 1
    assert changed["parameters"]["minimum_deposits"] == 15
    assert changed["updated_by_role"] == "rule_admin"

    before = bankdb.execute_readonly("SELECT COUNT(*) AS n FROM alerts")["rows"][0]["n"]
    simulated = rules.evaluate_rule(rule_id)
    after = bankdb.execute_readonly("SELECT COUNT(*) AS n FROM alerts")["rows"][0]["n"]
    assert simulated["persisted"] is False
    assert simulated["match_count"] == 0
    assert before == after


@pytest.mark.parametrize(
    "parameters, message",
    [
        ({"not_a_parameter": 1}, "Unknown parameter"),
        ({"minimum_deposits": 0}, "greater than zero"),
        ({"minimum_deposits": "three"}, "numeric"),
    ],
)
def test_rule_configuration_rejects_invalid_parameters(screened_cases, parameters, message):
    with pytest.raises(ValueError, match=message):
        store.update_rule_config(
            "CASH-VELOCITY-04",
            enabled=None,
            parameters=parameters,
            actor_role="rule_admin",
        )
