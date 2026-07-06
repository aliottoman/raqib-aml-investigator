from __future__ import annotations

import asyncio
import json

import pytest

from src import demo_tape


pytestmark = pytest.mark.contract


def test_demo_replay_uses_live_event_shape_and_honors_approval_pauses(
    monkeypatch: pytest.MonkeyPatch,
):
    asks = 0

    async def no_sleep(_seconds: float):
        return None

    async def approve():
        nonlocal asks
        asks += 1
        return {"approve": True}

    async def collect():
        return [event async for event in demo_tape.play(approve)]

    monkeypatch.setattr(demo_tape.asyncio, "sleep", no_sleep)
    events = asyncio.run(collect())
    source = json.loads(demo_tape.TAPE_PATH.read_text(encoding="utf-8"))

    assert len(events) == len(source)
    assert all("_t" not in event for event in events)
    assert asks == sum(event["type"] == "approval_request" for event in events)
    assert events[0]["type"] == "case_opened"
    assert events[-1]["type"] == "done"

