"""
Raqib — demo tape replayer.

demo_tape.json is a real recorded live investigation (same event schema the
live agent emits), so demo mode and live mode are pixel-identical in the UI.
Replay keeps the live run's rhythm (scaled, capped) and still honors the
analyst's approval gate — the presenter clicks through the same SQL approvals.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable

TAPE_PATH = Path(__file__).parent / "demo_tape.json"
SPEED = 0.55       # fraction of real elapsed time
MAX_GAP_S = 2.6    # never stall longer than this between events


async def play(ask: Callable[[], Awaitable[dict]]) -> AsyncGenerator[dict, None]:
    events = json.loads(TAPE_PATH.read_text())
    prev_t = 0.0
    for e in events:
        t = float(e.get("_t", prev_t))
        await asyncio.sleep(min((t - prev_t) * SPEED, MAX_GAP_S))
        prev_t = t
        event = {k: v for k, v in e.items() if k != "_t"}
        yield event
        if event["type"] == "approval_request":
            await ask()  # presenter clicks Approve — the tape then continues
