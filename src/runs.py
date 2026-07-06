"""
Raqib — durable investigation run manager (Track D).

Phase 1 welded a run to the socket that started it: a disconnect abandoned the
in-flight agent work and there was no way back in. This manager decouples the
run from any socket so it can survive a reconnect and be driven from more than
one place:

* One background task per run consumes the ``agent.investigate`` / demo-tape
  generator, persists every event once, and fans it out to any attached
  subscribers. A socket is now just a subscriber.
* The human SQL-approval gate is a per-run future, so the decision can arrive
  from the originating socket, a reconnected socket, or the REST endpoint —
  whichever the analyst uses.
* The PII-before-release buffering that used to live in the WebSocket handler
  moves here, so persisted history and replayed streams are always correct.
* Runs can be cancelled; a run whose process dies is reconciled to
  ``interrupted`` on the next startup (see ``store.reconcile_stale_runs``).

This is the application-tier durability an OCI Queue would later dispatch: the
seam is the run lifecycle in ``store``, not this in-process registry.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable

from src import store
from src.schemas import ev


@dataclass
class _RunState:
    run_id: str
    case_id: str
    engine: str
    role: str
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None
    pending_call_id: str | None = None
    approval_future: asyncio.Future | None = None
    decisions: dict[str, bool] = field(default_factory=dict)
    terminal: bool = False


class RunManager:
    """In-process registry of active investigation runs."""

    def __init__(self) -> None:
        self._active: dict[str, _RunState] = {}

    # -- lifecycle ---------------------------------------------------------- #
    def reset(self) -> None:
        """Drop registry state (used when the app is (re)created for tests)."""
        self._active.clear()

    def create(self, case_id: str, engine: str, role: str) -> str:
        """Register a new run and return its id (does not start it yet)."""
        record = store.start_run(case_id, engine, role)
        run_id = record["id"]
        self._active[run_id] = _RunState(run_id=run_id, case_id=case_id, engine=engine, role=role)
        return run_id

    def is_active(self, run_id: str) -> bool:
        return run_id in self._active

    def subscribe(self, run_id: str) -> asyncio.Queue | None:
        """Attach a subscriber queue. None if the run is not active (finished
        or unknown) — the caller should replay persisted events instead."""
        run = self._active.get(run_id)
        if run is None:
            return None
        queue: asyncio.Queue = asyncio.Queue()
        run.subscribers.add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        run = self._active.get(run_id)
        if run is not None:
            run.subscribers.discard(queue)

    def begin(self, run_id: str) -> None:
        """Start the background driver task once. Subscribe first so no early
        event is missed."""
        run = self._active.get(run_id)
        if run is None or run.task is not None:
            return
        run.task = asyncio.create_task(self._drive(run))

    def cancel(self, run_id: str) -> bool:
        """Request cancellation of an active run. False if it is not active."""
        run = self._active.get(run_id)
        if run is None or run.task is None:
            return False
        run.task.cancel()
        return True

    # -- approval gate ------------------------------------------------------ #
    def decide(self, run_id: str, decision: dict, role: str) -> dict:
        """Resolve the run's pending SQL approval. Mirrors the phase-1 binding:
        a supplied identifier that does not match the pending call fails closed
        (records a decline) rather than approving the wrong query."""
        run = self._active.get(run_id)
        if run is None or run.pending_call_id is None:
            return {"accepted": False, "approved": False}
        call_id = run.pending_call_id
        supplied_call = decision.get("id") or decision.get("call_id")
        supplied_run = decision.get("run_id")
        identifiers_match = (
            (supplied_call is None or supplied_call == call_id)
            and (supplied_run is None or supplied_run == run_id)
        )
        approved = bool(decision.get("approve", False)) and identifiers_match
        recorded = store.decide_approval(run_id, call_id, approved, role)
        approved = approved and recorded
        run.decisions[call_id] = approved
        future = run.approval_future
        if future is not None and not future.done():
            future.set_result({"approve": approved, "call_id": call_id, "run_id": run_id})
        return {"accepted": True, "approved": approved}

    def _ask_for(self, run: _RunState) -> Callable[[], Awaitable[dict]]:
        async def ask() -> dict:
            future = run.approval_future
            if future is None:
                return {"approve": False}
            # A CancelledError here means the run is being cancelled: let it
            # propagate so _drive tears the run down rather than silently
            # continuing with a declined query.
            return await future
        return ask

    # -- the driver --------------------------------------------------------- #
    def _runner(self, run: _RunState) -> AsyncGenerator[dict, None]:
        ask = self._ask_for(run)
        if run.engine == "demo":
            from src import demo_tape
            return demo_tape.play(ask)
        from src import agent
        return agent.investigate(ask, run.case_id)

    async def _drive(self, run: _RunState) -> None:
        runner = self._runner(run)
        pending_sar: dict | None = None
        pii_hits: list[dict] | None = None
        finalized = False
        try:
            async for raw_event in runner:
                event = dict(raw_event)
                kind = event.get("type")

                if kind == "approval_request":
                    run.pending_call_id = event.get("id")
                    # The generator awaits this future on its next step; create
                    # it now, before the request reaches any subscriber.
                    run.approval_future = asyncio.get_running_loop().create_future()
                    store.request_approval(
                        run.case_id, run.run_id, run.pending_call_id or "unknown",
                        event.get("sql", ""), event.get("purpose", ""),
                    )
                elif kind == "approval_result":
                    call_id = event.get("id")
                    if call_id in run.decisions:
                        event["approved"] = run.decisions[call_id]
                    run.pending_call_id = None
                elif kind == "memory":
                    store.update_run(run.run_id, conversation_id=event.get("conversation_id"))
                elif kind == "step":
                    store.update_run(run.run_id, current_step=int(event.get("n", 0)))

                # Historical tapes emit the SAR before its PII scan. Buffer so
                # both demo and live obey PII-before-release without rewriting
                # recorded evidence.
                if kind == "sar":
                    pending_sar = event
                    if pii_hits is not None:
                        await self._release_sar(run, pending_sar, pii_hits)
                        pending_sar = None
                    continue
                if kind == "pii":
                    pii_hits = event.get("hits", [])
                    await self._emit(run, event)
                    if pending_sar is not None:
                        await self._release_sar(run, pending_sar, pii_hits)
                        pending_sar = None
                    continue
                if kind == "done":
                    if pending_sar is not None:
                        # A missing output scan is a failed governance check:
                        # never expose or persist the report.
                        await self._emit(run, ev(
                            "error", message="SAR output scan did not complete; draft was withheld."))
                        pending_sar = None
                    # Commit the durable terminal status *before* emitting done,
                    # so a subscriber never observes completion ahead of the
                    # persisted run record.
                    store.update_run(run.run_id, status="completed")
                    finalized = True

                await self._emit(run, event)
            if not finalized:
                store.update_run(run.run_id, status="completed")
        except asyncio.CancelledError:
            store.update_run(run.run_id, status="cancelled", error="Cancelled by operator")
            await self._safe_emit(run, ev("error", message="Investigation cancelled by operator."))
        except Exception as exc:  # noqa: BLE001 — surfaced to the client and persisted
            store.update_run(run.run_id, status="failed", error=str(exc)[:1000])
            await self._safe_emit(run, ev("error", message=f"Investigation could not complete: {exc}"))
        finally:
            run.terminal = True
            await self._safe_aclose(runner)
            for queue in list(run.subscribers):
                queue.put_nowait(None)  # sentinel: no more live events
            self._active.pop(run.run_id, None)

    async def _emit(self, run: _RunState, event: dict) -> dict:
        enriched = {**event, "run_id": run.run_id}
        event_id = store.append_event(
            run.case_id, event.get("type", "unknown"), enriched,
            run_id=run.run_id, actor_role=run.role, call_id=event.get("id"),
        )
        enriched["event_id"] = event_id
        for queue in list(run.subscribers):
            queue.put_nowait(enriched)
        return enriched

    async def _safe_emit(self, run: _RunState, event: dict) -> None:
        try:
            await self._emit(run, event)
        except Exception:
            pass

    async def _release_sar(self, run: _RunState, sar_event: dict, pii_hits: list[dict]) -> None:
        # save_sar validates the structured contract before the UI sees it.
        saved = store.save_sar(
            run.case_id, sar_event["report"], actor_role=run.role,
            pii_hits=pii_hits or [], source_run_id=run.run_id,
        )
        await self._emit(run, {**sar_event, "version": saved["version"], "status": saved["status"]})

    @staticmethod
    async def _safe_aclose(runner: Any) -> None:
        aclose = getattr(runner, "aclose", None)
        if aclose is None:
            return
        try:
            await aclose()
        except Exception:
            pass


# Module-level singleton. The app's lifespan resets it and reconciles stale
# runs so a restarted process never shows a run as perpetually in-flight.
manager = RunManager()
