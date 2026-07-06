"""
Headless investigation runner for evals.

Drives `agent.investigate()` exactly as the WebSocket does, but with an
auto-approving analyst, and records everything worth measuring: the full
event stream, wall-clock latency, tool usage, guardrail catches, the final
SAR, and token usage.

Token usage is captured by wrapping the cached platform client's
`responses.create/parse` at eval time — the agent code is untouched, so the
demo tape and the 100+ unit tests stay exactly as they are.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import config
from src import agent, oci_clients


@dataclass
class RunResult:
    alert_id: str
    ok: bool
    events: list[dict] = field(default_factory=list)
    sar: dict | None = None
    pii_hits: list[dict] = field(default_factory=list)
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_calls: int = 0
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def tool_calls(self) -> list[str]:
        return [e["name"] for e in self.events if e["type"] == "tool_call"]

    def guardrail_catches(self) -> list[dict]:
        return [e for e in self.events if e["type"] == "guardrail" and e.get("injection_detected")]

    def injection_flagged(self) -> bool:
        return bool(self.guardrail_catches())


@contextmanager
def _token_meter(result: RunResult):
    """Tally usage across every platform model call for the duration of a run."""
    client = oci_clients.platform()
    real_create, real_parse = client.responses.create, client.responses.parse

    def tally(resp):
        result.model_calls += 1
        usage = getattr(resp, "usage", None)
        if usage:
            result.prompt_tokens += getattr(usage, "input_tokens", 0) or 0
            result.completion_tokens += getattr(usage, "output_tokens", 0) or 0
        return resp

    client.responses.create = lambda *a, **k: tally(real_create(*a, **k))
    client.responses.parse = lambda *a, **k: tally(real_parse(*a, **k))
    try:
        yield
    finally:
        client.responses.create, client.responses.parse = real_create, real_parse


async def _run(alert_id: str) -> RunResult:
    result = RunResult(alert_id=alert_id, ok=False)

    async def auto_approve() -> dict:
        return {"approve": True}   # the eval analyst approves every governed query

    t0 = time.time()
    with _token_meter(result):
        try:
            async for event in agent.investigate(auto_approve, alert_id):
                result.events.append(event)
                if event["type"] == "sar":
                    result.sar = event["report"]
                elif event["type"] == "pii":
                    result.pii_hits = event["hits"]
                elif event["type"] == "error":
                    result.error = event.get("message", "unknown error")
            result.ok = result.sar is not None and not result.error
        except Exception as exc:  # a crash is a run outcome, not a harness failure
            result.error = f"{type(exc).__name__}: {exc}"
    result.latency_s = round(time.time() - t0, 1)
    return result


def run_case(alert_id: str) -> RunResult:
    """Investigate one alert end-to-end (blocking). Requires live OCI config."""
    if not config.live_configured():
        raise RuntimeError("Live OCI credentials required for eval runs (set OPENAI_API_KEY_CHICAGO).")
    return asyncio.run(_run(alert_id))
