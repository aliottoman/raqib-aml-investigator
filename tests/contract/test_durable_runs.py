"""Durability contract for investigation runs (Track D).

A run lives in the RunManager, decoupled from the socket that started it, so it
survives a reconnect and can be driven from a reconnected socket or REST. These
tests exercise resume, out-of-band approval, cancellation, and the run-listing
endpoint against the demo engine (no OCI calls).
"""

from __future__ import annotations

import pytest

from src import bankdb, demo_tape, store


pytestmark = pytest.mark.contract


def _screen(api_client):
    assert api_client.post("/api/screening/run").status_code == 200


def _tape_paused_at_approval(golden_sar):
    """A demo generator that parks on one SQL approval, then files a SAR."""
    async def fake_play(ask):
        yield {"type": "case_opened", "alert": {"id": bankdb.ALERT_ID}}
        yield {"type": "approval_request", "id": "call-1",
               "sql": "SELECT COUNT(*) FROM transactions", "purpose": "Reconcile volume"}
        decision = await ask()
        yield {"type": "approval_result", "id": "call-1", "approved": decision["approve"]}
        yield {"type": "pii", "hits": []}
        yield {"type": "sar", "report": golden_sar}
        yield {"type": "done"}
    return fake_play


def test_run_resumes_after_reconnect_and_completes(api_client, golden_sar, monkeypatch):
    _screen(api_client)
    monkeypatch.setattr(demo_tape, "play", _tape_paused_at_approval(golden_sar))

    # First connection drops while the run is parked on the approval gate.
    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        opened = ws.receive_json()
        approval = ws.receive_json()
        run_id = approval["run_id"]
        assert opened["type"] == "case_opened"
        assert approval["type"] == "approval_request"
    # The socket is gone but the run is not abandoned.
    assert store.get_run(run_id)["status"] == "running"

    # Reconnect to the same run: prior events replay, then it streams live.
    with api_client.websocket_connect(
        f"/ws/investigate?run={run_id}&role=analyst"
    ) as ws2:
        replay_opened = ws2.receive_json()
        replay_approval = ws2.receive_json()
        assert replay_opened["type"] == "case_opened"
        assert replay_approval["type"] == "approval_request"

        ws2.send_json({"approve": True, "call_id": "call-1", "run_id": run_id})
        result = ws2.receive_json()
        pii = ws2.receive_json()
        sar = ws2.receive_json()
        done = ws2.receive_json()

    assert result["type"] == "approval_result" and result["approved"] is True
    assert [pii["type"], sar["type"], done["type"]] == ["pii", "sar", "done"]
    assert sar["status"] == "draft"
    assert store.get_run(run_id)["status"] == "completed"
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}/sar").json()["source_run_id"] == run_id


def test_reconnect_honours_the_after_cursor(api_client, golden_sar, monkeypatch):
    _screen(api_client)
    monkeypatch.setattr(demo_tape, "play", _tape_paused_at_approval(golden_sar))

    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        opened = ws.receive_json()
        approval = ws.receive_json()
        run_id = approval["run_id"]

    # Resume past the first event: only events after the cursor replay.
    with api_client.websocket_connect(
        f"/ws/investigate?run={run_id}&after={opened['event_id']}&role=analyst"
    ) as ws2:
        first = ws2.receive_json()
        assert first["type"] == "approval_request"
        assert first["event_id"] > opened["event_id"]
        ws2.send_json({"approve": False, "call_id": "call-1", "run_id": run_id})
        result = ws2.receive_json()
        assert result["type"] == "approval_result" and result["approved"] is False
        # drain to completion
        assert {ws2.receive_json()["type"] for _ in range(3)} == {"pii", "sar", "done"}


def test_run_can_be_approved_out_of_band_via_rest(api_client, golden_sar, role_headers, monkeypatch):
    _screen(api_client)
    monkeypatch.setattr(demo_tape, "play", _tape_paused_at_approval(golden_sar))

    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        ws.receive_json()  # case_opened
        approval = ws.receive_json()
        run_id = approval["run_id"]

        decided = api_client.post(
            f"/api/runs/{run_id}/approvals",
            json={"approve": True, "call_id": "call-1"},
            headers=role_headers("analyst"),
        )
        assert decided.status_code == 200
        assert decided.json() == {"run_id": run_id, "approved": True}

        result = ws.receive_json()
        assert result["type"] == "approval_result" and result["approved"] is True
        assert {ws.receive_json()["type"] for _ in range(3)} == {"pii", "sar", "done"}


def test_run_can_be_cancelled(api_client, golden_sar, role_headers, monkeypatch):
    _screen(api_client)
    monkeypatch.setattr(demo_tape, "play", _tape_paused_at_approval(golden_sar))

    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        ws.receive_json()  # case_opened
        approval = ws.receive_json()
        run_id = approval["run_id"]

        cancelled = api_client.post(f"/api/runs/{run_id}/cancel", headers=role_headers("analyst"))
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelling"

        error = ws.receive_json()
        assert error["type"] == "error"
        assert "cancelled" in error["message"].lower()

    assert store.get_run(run_id)["status"] == "cancelled"
    # A cancelled run never released a SAR draft.
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}/sar").status_code == 404


def test_case_runs_endpoint_lists_runs(api_client, golden_sar, monkeypatch):
    _screen(api_client)
    monkeypatch.setattr(demo_tape, "play", _tape_paused_at_approval(golden_sar))

    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        ws.receive_json()
        run_id = ws.receive_json()["run_id"]
        ws.send_json({"approve": True, "call_id": "call-1", "run_id": run_id})
        while ws.receive_json()["type"] != "done":
            pass

    listing = api_client.get(f"/api/cases/{bankdb.ALERT_ID}/runs").json()
    assert listing["total"] >= 1
    assert run_id in {run["id"] for run in listing["runs"]}
    assert listing["active_run_id"] is None  # finished, so no longer live
    assert all("live" in run for run in listing["runs"])


def test_run_control_endpoints_validate(api_client, role_headers):
    _screen(api_client)
    assert api_client.post("/api/runs/run_missing/cancel",
                           headers=role_headers("analyst")).status_code == 404
    assert api_client.post("/api/runs/run_missing/approvals", json={"approve": True},
                           headers=role_headers("analyst")).status_code == 404

    # A real run with no live driver (never registered with the manager) has no
    # pending approval to decide.
    run = store.start_run(bankdb.ALERT_ID, "live", "analyst")
    stale = api_client.post(f"/api/runs/{run['id']}/approvals", json={"approve": True},
                            headers=role_headers("analyst"))
    assert stale.status_code == 409


@pytest.mark.parametrize("role", ["reviewer", "auditor", "rule_admin"])
def test_run_control_endpoints_are_analyst_only(api_client, role_headers, role):
    # The role gate rejects before any run lookup, so no real run is needed.
    assert api_client.post("/api/runs/run_probe/cancel",
                           headers=role_headers(role)).status_code == 403
    assert api_client.post("/api/runs/run_probe/approvals", json={"approve": True},
                           headers=role_headers(role)).status_code == 403
