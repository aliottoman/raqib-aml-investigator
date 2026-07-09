from __future__ import annotations

from copy import deepcopy

import pytest

from src import bankdb


pytestmark = pytest.mark.contract


def _screen(api_client, role: str = "analyst") -> dict:
    response = api_client.post("/api/screening/run", headers={"X-Raqib-Role": role})
    assert response.status_code == 200, response.text
    return response.json()


def _save_sar(api_client, report: dict, case_id: str = bankdb.ALERT_ID) -> dict:
    response = api_client.put(
        f"/api/cases/{case_id}/sar",
        json={"report": report},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_readiness_and_session_are_explicit_about_simulation(api_client):
    health = api_client.get("/api/health")
    readiness = api_client.get("/api/readiness")
    session = api_client.get("/api/session")

    assert health.status_code == 200
    assert health.json()["auth_mode"] == "simulated_personas"
    assert readiness.status_code == 200
    assert readiness.json()["checks"] == {
        "database": True,
        "trusted_policy": True,
        "web_build": False,
    }
    assert readiness.json()["status"] == "degraded"
    assert session.json()["simulated"] is True
    assert session.json()["current_role"] == "analyst"
    assert {role["id"] for role in session.json()["roles"]} == {
        "analyst", "reviewer", "auditor", "rule_admin",
    }


@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor", "rule_admin"])
def test_session_selects_each_supported_persona(api_client, role: str):
    response = api_client.get("/api/session", headers={"X-Raqib-Role": f"  {role.upper()} "})
    assert response.status_code == 200
    assert response.json()["current_role"] == role
    assert response.json()["persona"]["id"] == role


def test_unknown_persona_is_rejected(api_client):
    response = api_client.get("/api/session", headers={"X-Raqib-Role": "superuser"})
    assert response.status_code == 400
    assert "Unknown simulated role" in response.json()["detail"]


@pytest.mark.parametrize("role", ["analyst", "rule_admin"])
def test_authorized_roles_can_run_screening(api_client, role: str):
    result = _screen(api_client, role)
    assert result["customers_scanned"] == 19
    assert len(result["alerts"]) == 9
    assert result["run_id"].startswith("rr_")


@pytest.mark.parametrize("role", ["reviewer", "auditor"])
def test_read_only_roles_cannot_run_screening(api_client, role: str):
    response = api_client.post("/api/screening/run", headers={"X-Raqib-Role": role})
    assert response.status_code == 403


def test_case_routes_support_search_filtering_notes_and_event_cursors(api_client):
    _screen(api_client)
    cases = api_client.get("/api/cases").json()
    assert cases["total"] == 9

    searched = api_client.get("/api/cases", params={"search": "rashidi"}).json()
    assert searched["total"] == 2  # one customer may have multiple rule-specific cases
    assert {case["id"] for case in searched["cases"]} == {
        bankdb.ALERT_ID, "RQB-2026-0357",
    }

    note = api_client.post(
        f"/api/cases/{bankdb.ALERT_ID}/notes",
        json={"text": "Validate Meridian ownership"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert note.status_code == 201
    assert note.json()["note"]["actor_role"] == "analyst"

    first_page = api_client.get(f"/api/cases/{bankdb.ALERT_ID}/events", params={"limit": 1}).json()
    assert first_page["total"] == 1
    second_page = api_client.get(
        f"/api/cases/{bankdb.ALERT_ID}/events",
        params={"after": first_page["next_after"]},
    ).json()
    assert all(event["id"] > first_page["next_after"] for event in second_page["events"])

    detail = api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()
    assert detail["notes"][0]["text"] == "Validate Meridian ownership"
    assert len(detail["dossier"]["june_deposits"]) == 14


def test_bulk_triage_assigns_and_reports_skips(api_client):
    _screen(api_client)
    response = api_client.post(
        "/api/cases/bulk",
        json={"case_ids": [bankdb.ALERT_ID, "NO-SUCH-CASE"], "action": "assign", "owner": "Desk 3"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == [bankdb.ALERT_ID]
    assert body["skipped"] == [{"case_id": "NO-SUCH-CASE", "reason": "unknown case"}]
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()["owner"] == "Desk 3"


def test_bulk_triage_validates_payload_and_gates_roles(api_client):
    _screen(api_client)
    missing_owner = api_client.post(
        "/api/cases/bulk",
        json={"case_ids": [bankdb.ALERT_ID], "action": "assign"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert missing_owner.status_code == 422

    missing_close_reason = api_client.post(
        "/api/cases/bulk",
        json={"case_ids": [bankdb.ALERT_ID], "action": "transition", "status": "closed"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert missing_close_reason.status_code == 422
    assert "rationale" in missing_close_reason.json()["detail"]
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()["status"] == "open"

    for role in ("auditor", "rule_admin"):
        forbidden = api_client.post(
            "/api/cases/bulk",
            json={"case_ids": [bankdb.ALERT_ID], "action": "priority", "priority": "low"},
            headers={"X-Raqib-Role": role},
        )
        assert forbidden.status_code == 403


def test_demo_reset_reopens_cases_and_is_rule_admin_only(api_client):
    _screen(api_client)
    closed = api_client.post(
        "/api/cases/bulk",
        json={"case_ids": [bankdb.ALERT_ID], "action": "transition",
              "status": "closed", "reason": "worked and closed"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert closed.status_code == 200
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()["status"] == "closed"

    # Only the Rule Administrator persona can reset the demo.
    for role in ("analyst", "reviewer", "auditor"):
        forbidden = api_client.post("/api/demo/reset", headers={"X-Raqib-Role": role})
        assert forbidden.status_code == 403

    reset = api_client.post("/api/demo/reset", headers={"X-Raqib-Role": "rule_admin"})
    assert reset.status_code == 200
    assert bankdb.ALERT_ID in reset.json()["reopened"]
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()["status"] == "open"


def test_case_queue_filters_by_rule_and_owner(api_client):
    _screen(api_client)
    api_client.post(
        "/api/cases/bulk",
        json={"case_ids": [bankdb.ALERT_ID], "action": "assign", "owner": "Nadia"},
        headers={"X-Raqib-Role": "analyst"},
    )
    by_rule = api_client.get("/api/cases", params={"rule": "WATCHLIST-PROX-01"}).json()
    assert by_rule["total"] == 3
    assert {case["rule"] for case in by_rule["cases"]} == {"WATCHLIST-PROX-01"}

    by_owner = api_client.get("/api/cases", params={"owner": "Nadia"}).json()
    assert [case["id"] for case in by_owner["cases"]] == [bankdb.ALERT_ID]

    alerts = api_client.get("/api/alerts").json()["alerts"]
    flagship = next(alert for alert in alerts if alert["id"] == bankdb.ALERT_ID)
    assert flagship["workflow_status"] == "open"
    assert flagship["case_status"] == "open"


def test_triage_summary_aggregates_the_queue(api_client):
    _screen(api_client)
    triage = api_client.get("/api/triage").json()
    assert triage["total"] == 9 and triage["active"] == 9
    assert triage["by_rule"]["WATCHLIST-PROX-01"] == 3
    assert triage["by_severity"]["critical"] == 2
    assert set(triage["by_status"]) == {"open"}


@pytest.mark.parametrize("role", ["auditor", "rule_admin"])
def test_read_only_and_rule_personas_cannot_add_case_notes(api_client, role: str):
    _screen(api_client)
    response = api_client.post(
        f"/api/cases/{bankdb.ALERT_ID}/notes",
        json={"text": "unauthorized"},
        headers={"X-Raqib-Role": role},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["analyst", "reviewer"])
def test_case_transitions_are_available_to_workflow_roles(api_client, role: str):
    _screen(api_client)
    response = api_client.post(
        f"/api/cases/{bankdb.ALERT_ID}/transition",
        json={"status": "closed", "reason": "Resolved during test"},
        headers={"X-Raqib-Role": role},
    )
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "closed"


def test_case_closure_requires_a_rationale(api_client):
    _screen(api_client)
    response = api_client.post(
        f"/api/cases/{bankdb.ALERT_ID}/transition",
        json={"status": "closed"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert response.status_code == 422
    assert "rationale" in response.json()["detail"]
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()["status"] == "open"


def test_overview_analytics_rules_and_architecture_have_stable_shapes(api_client):
    _screen(api_client)
    overview = api_client.get("/api/overview").json()
    analytics = api_client.get("/api/analytics").json()
    rules = api_client.get("/api/rules").json()
    architecture = api_client.get("/api/architecture").json()

    assert overview["principle"] == "Rules detect. AI investigates. Humans decide."
    assert overview["metrics"]["active_cases"] == 9
    assert analytics["summary"]["customers_monitored"] == 19
    assert analytics["summary"]["transactions_monitored"] == 1079
    assert len(rules["rules"]) == 4
    assert {node["status"] for node in architecture["current"]["nodes"]} == {"implemented"}
    assert {profile["id"] for profile in architecture["deployment_profiles"]} == {
        "showcase", "ksa", "uae",
    }


def test_rule_admin_can_patch_and_simulate_without_persisting_candidate(api_client):
    _screen(api_client)
    headers = {"X-Raqib-Role": "rule_admin"}
    changed = api_client.patch(
        "/api/rules/CASH-VELOCITY-04",
        json={"parameters": {"minimum_deposits": 15}},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["rule"]["parameters"]["minimum_deposits"] == 15

    simulation = api_client.post(
        "/api/rules/CASH-VELOCITY-04/simulate",
        json={"parameters": {"minimum_deposits": 3}},
        headers=headers,
    )
    assert simulation.status_code == 200
    assert simulation.json()["persisted"] is False
    assert simulation.json()["match_count"] == 2  # flagship 1017 + extension 1061
    assert simulation.json()["simulation_id"].startswith("rr_")

    persisted = next(
        rule for rule in api_client.get("/api/rules").json()["rules"]
        if rule["rule_id"] == "CASH-VELOCITY-04"
    )
    assert persisted["parameters"]["minimum_deposits"] == 15


@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor"])
def test_only_rule_admin_can_change_or_simulate_rules(api_client, role: str):
    patch = api_client.patch(
        "/api/rules/CASH-VELOCITY-04",
        json={"enabled": False},
        headers={"X-Raqib-Role": role},
    )
    simulate = api_client.post(
        "/api/rules/CASH-VELOCITY-04/simulate",
        json={},
        headers={"X-Raqib-Role": role},
    )
    assert patch.status_code == 403
    assert simulate.status_code == 403


def test_sar_lifecycle_is_case_scoped_and_maker_checker_enforced(api_client, golden_sar):
    _screen(api_client)
    first_id, second_id = bankdb.ALERT_ID, "RQB-2026-0357"

    first = _save_sar(api_client, golden_sar, first_id)
    second_report = deepcopy(golden_sar)
    second_report["subject"] = "Second case subject"
    second = _save_sar(api_client, second_report, second_id)
    assert first["report"]["case_id"] == first_id
    assert second["report"]["case_id"] == second_id
    assert api_client.get(f"/api/cases/{first_id}/sar").json()["report"]["subject"] != (
        api_client.get(f"/api/cases/{second_id}/sar").json()["report"]["subject"]
    )

    submit = api_client.post(
        f"/api/cases/{first_id}/sar/submit", headers={"X-Raqib-Role": "analyst"}
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "pending_review"

    analyst_review = api_client.post(
        f"/api/cases/{first_id}/sar/review",
        json={"decision": "approved"},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert analyst_review.status_code == 403

    review = api_client.post(
        f"/api/cases/{first_id}/sar/review",
        json={"decision": "approved", "comment": "Evidence reconciled"},
        headers={"X-Raqib-Role": "reviewer"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"
    assert api_client.get(f"/api/cases/{second_id}/sar").json()["status"] == "draft"


@pytest.mark.parametrize("role", ["reviewer", "auditor", "rule_admin"])
def test_only_analyst_can_edit_or_submit_sar(api_client, golden_sar, role: str):
    _screen(api_client)
    edit = api_client.put(
        f"/api/cases/{bankdb.ALERT_ID}/sar",
        json={"report": golden_sar},
        headers={"X-Raqib-Role": role},
    )
    submit = api_client.post(
        f"/api/cases/{bankdb.ALERT_ID}/sar/submit",
        headers={"X-Raqib-Role": role},
    )
    assert edit.status_code == 403
    assert submit.status_code == 403


def test_case_scoped_pdf_downloads_use_the_requested_case(api_client, golden_sar):
    _screen(api_client)
    first_id, second_id = bankdb.ALERT_ID, "RQB-2026-0357"
    _save_sar(api_client, golden_sar, first_id)
    _save_sar(api_client, dict(golden_sar, subject="Second case"), second_id)

    first = api_client.get(f"/api/cases/{first_id}/sar/pdf", params={"lang": "en"})
    second = api_client.get(f"/api/cases/{second_id}/sar/pdf", params={"lang": "ar"})
    legacy = api_client.get("/api/report/pdf", params={"case_id": first_id, "lang": "en"})

    assert first.status_code == second.status_code == legacy.status_code == 200
    assert first.content.startswith(b"%PDF-")
    assert second.content.startswith(b"%PDF-")
    assert f"SAR_{first_id}_v1_en.pdf" in first.headers["content-disposition"]
    assert f"SAR_{second_id}_v1_ar.pdf" in second.headers["content-disposition"]
    assert f"SAR_{first_id}_v1_en.pdf" in legacy.headers["content-disposition"]


def test_missing_resources_and_invalid_payloads_return_actionable_statuses(api_client, golden_sar):
    _screen(api_client)
    assert api_client.get("/api/cases/NO-SUCH-CASE").status_code == 404
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}/sar").status_code == 404

    invalid = deepcopy(golden_sar)
    invalid["risk_score"] = 999
    response = api_client.put(
        f"/api/cases/{bankdb.ALERT_ID}/sar",
        json={"report": invalid},
        headers={"X-Raqib-Role": "analyst"},
    )
    assert response.status_code == 422
