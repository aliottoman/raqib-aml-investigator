from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from src import bankdb, demo_tape


pytestmark = pytest.mark.contract


def _screen(api_client):
    response = api_client.post("/api/screening/run")
    assert response.status_code == 200


def test_demo_investigation_persists_events_approval_and_case_scoped_sar(
    api_client,
    golden_sar,
    monkeypatch: pytest.MonkeyPatch,
):
    _screen(api_client)

    async def fake_play(ask):
        yield {"type": "case_opened", "alert": {"id": bankdb.ALERT_ID}}
        yield {
            "type": "approval_request",
            "id": "call-approved",
            "sql": "SELECT COUNT(*) FROM transactions",
            "purpose": "Reconcile ledger volume",
        }
        decision = await ask()
        yield {"type": "approval_result", "id": "call-approved", "approved": decision["approve"]}
        # Historical tapes emit the report before its scan; the API must buffer it.
        yield {"type": "sar", "report": golden_sar}
        yield {"type": "pii", "hits": []}
        yield {"type": "done"}

    monkeypatch.setattr(demo_tape, "play", fake_play)
    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        opened = ws.receive_json()
        approval = ws.receive_json()
        assert opened["type"] == "case_opened"
        assert approval["type"] == "approval_request"
        assert opened["run_id"] == approval["run_id"]

        ws.send_json({
            "approve": True,
            "call_id": approval["id"],
            "run_id": approval["run_id"],
        })
        approved = ws.receive_json()
        pii = ws.receive_json()
        sar = ws.receive_json()
        done = ws.receive_json()

    assert approved["type"] == "approval_result"
    assert approved["approved"] is True
    assert pii["type"] == "pii"
    assert sar["type"] == "sar"
    assert sar["status"] == "draft"
    assert done["type"] == "done"
    assert all(event["run_id"] == opened["run_id"] for event in [approved, pii, sar, done])

    stored = api_client.get(f"/api/cases/{bankdb.ALERT_ID}/sar")
    history = api_client.get(f"/api/cases/{bankdb.ALERT_ID}/events").json()["events"]
    detail = api_client.get(f"/api/cases/{bankdb.ALERT_ID}").json()
    assert stored.status_code == 200
    assert stored.json()["report"]["case_id"] == bankdb.ALERT_ID
    assert stored.json()["source_run_id"] == opened["run_id"]
    assert {"approval_request", "approval_result", "pii", "sar", "done"} <= {
        event["type"] for event in history
    }
    assert detail["latest_run"]["status"] == "completed"


def test_mismatched_approval_identifiers_fail_closed(
    api_client,
    golden_sar,
    monkeypatch: pytest.MonkeyPatch,
):
    _screen(api_client)

    async def fake_play(ask):
        yield {
            "type": "approval_request",
            "id": "call-real",
            "sql": "SELECT 1",
            "purpose": "Test identifier binding",
        }
        decision = await ask()
        yield {"type": "approval_result", "id": "call-real", "approved": decision["approve"]}
        yield {"type": "pii", "hits": []}
        yield {"type": "sar", "report": golden_sar}
        yield {"type": "done"}

    monkeypatch.setattr(demo_tape, "play", fake_play)
    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        approval = ws.receive_json()
        ws.send_json({
            "approve": True,
            "call_id": "call-from-another-tab",
            "run_id": approval["run_id"],
        })
        result = ws.receive_json()
        assert result["type"] == "approval_result"
        assert result["approved"] is False


def test_sar_is_withheld_when_output_scan_never_completes(
    api_client,
    golden_sar,
    monkeypatch: pytest.MonkeyPatch,
):
    _screen(api_client)

    async def unsafe_play(_ask):
        yield {"type": "sar", "report": golden_sar}
        yield {"type": "done"}

    monkeypatch.setattr(demo_tape, "play", unsafe_play)
    with api_client.websocket_connect(
        f"/ws/investigate?engine=demo&case={bankdb.ALERT_ID}&role=analyst"
    ) as ws:
        error = ws.receive_json()
        done = ws.receive_json()

    assert error["type"] == "error"
    assert "withheld" in error["message"]
    assert done["type"] == "done"
    assert api_client.get(f"/api/cases/{bankdb.ALERT_ID}/sar").status_code == 404


@pytest.mark.parametrize("role", ["reviewer", "auditor", "rule_admin", "unknown"])
def test_non_analyst_websocket_personas_are_rejected(api_client, role: str):
    with api_client.websocket_connect(f"/ws/investigate?engine=demo&role={role}") as ws:
        event = ws.receive_json()
        assert event["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008


def test_demo_tape_cannot_be_applied_to_a_different_case(api_client):
    _screen(api_client)
    with api_client.websocket_connect(
        "/ws/investigate?engine=demo&case=RQB-2026-0357&role=analyst"
    ) as ws:
        event = ws.receive_json()
        assert event["type"] == "error"
        assert bankdb.ALERT_ID in event["message"]

