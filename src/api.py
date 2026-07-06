"""Raqib FastAPI application.

Author: Ali Ottoman

The API keeps the original one-process demo experience while exposing a
durable, role-aware case workflow for the expanded React workbench.  Identity
is deliberately simulated with ``X-Raqib-Role``; the response contract marks
that clearly so it cannot be mistaken for real authentication.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Callable

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
from src import bankdb, store
from src.schemas import CaseTransition, NoteCreate, RuleSimulation, RuleUpdate, SARReview, ev


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.ensure_schema()
    yield


app = FastAPI(
    title="Raqib — AML Case Investigator",
    version="2.0",
    description="Portfolio-grade AML investigation reference solution on OCI Generative AI.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Raqib-Role"],
)


ROLE_INFO = {
    "analyst": {
        "label": "AML Analyst", "description": "Investigates alerts and prepares SAR drafts.",
        "capabilities": ["investigate", "approve_sql", "add_notes", "transition_cases", "edit_sar", "submit_sar"],
    },
    "reviewer": {
        "label": "MLRO Reviewer", "description": "Reviews case evidence and approves or returns SARs.",
        "capabilities": ["add_notes", "transition_cases", "review_sar"],
    },
    "auditor": {
        "label": "Auditor", "description": "Reads cases, decisions, and the immutable event history.",
        "capabilities": ["read"],
    },
    "rule_admin": {
        "label": "Rule Administrator", "description": "Tunes, simulates, and runs deterministic detection rules.",
        "capabilities": ["configure_rules", "simulate_rules", "run_screening"],
    },
}

RoleHeader = Annotated[str | None, Header(alias="X-Raqib-Role")]


def current_role(x_raqib_role: RoleHeader = None) -> str:
    role = (x_raqib_role or "analyst").strip().lower()
    if role not in ROLE_INFO:
        raise HTTPException(400, f"Unknown simulated role '{role}'")
    return role


def require_roles(*allowed: str) -> Callable:
    def dependency(role: str = Depends(current_role)) -> str:
        if role not in allowed:
            names = ", ".join(ROLE_INFO[r]["label"] for r in allowed)
            raise HTTPException(403, f"This action is available to: {names}")
        return role
    return dependency


def _ensure_alert(alert_id: str) -> None:
    try:
        bankdb.get_alert(alert_id)
    except KeyError:
        from src import rules
        rules.run_screening()
        try:
            bankdb.get_alert(alert_id)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown case: {alert_id}") from exc
    store.sync_cases()


def _case_dossier(alert_id: str) -> dict:
    """Customer snapshot and evidence preview used by both legacy and new UI."""
    _ensure_alert(alert_id)
    base = bankdb.get_alert(alert_id)
    cid = int(base["customer"]["id"])
    deposits = bankdb.execute_readonly(
        "SELECT t.ts, t.branch, t.amount_aed FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id "
        f"WHERE a.customer_id = {cid} AND t.type='cash_deposit' "
        "AND t.ts >= '2026-05-01' ORDER BY t.ts"
    )
    wires = bankdb.execute_readonly(
        "SELECT t.ts, t.counterparty, t.counterparty_country, t.amount_aed, t.reference "
        "FROM transactions t JOIN accounts a ON a.id = t.account_id "
        f"WHERE a.customer_id = {cid} AND t.type='wire_out' AND t.ts >= '2026-05-01' "
        "ORDER BY ABS(t.amount_aed) DESC LIMIT 8"
    )
    return {
        **base,
        "june_deposits": deposits.get("rows", []),
        "june_wires": wires.get("rows", []),
        "is_flagship": alert_id == bankdb.ALERT_ID,
    }


def _case_or_404(case_id: str) -> dict:
    _ensure_alert(case_id)
    try:
        return store.get_case(case_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown case: {case_id}") from exc


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "live_available": config.live_configured(),
        "guardrails_available": config.guardrails_configured(),
        "orchestrator_model": config.ORCHESTRATOR_MODEL,
        "region": config.REGION,
        "persistence": "sqlite",
        "auth_mode": "simulated_personas",
    }


@app.get("/api/readiness")
def readiness() -> dict:
    checks = {}
    try:
        store.ensure_schema()
        con = sqlite3.connect(str(config.DB_PATH))
        checks["database"] = con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        con.close()
    except Exception:
        checks["database"] = False
    checks["trusted_policy"] = (config.DOCS_DIR / "aml_policy.md").is_file()
    checks["web_build"] = (config.WEB_DIST / "index.html").is_file()
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}


@app.get("/api/session")
def session(role: str = Depends(current_role)) -> dict:
    return {
        "simulated": True,
        "notice": "Persona simulation for the portfolio reference solution; not an authentication mechanism.",
        "current_role": role,
        "persona": {"id": role, **ROLE_INFO[role]},
        "roles": [{"id": key, **value} for key, value in ROLE_INFO.items()],
    }


@app.get("/api/portfolio")
def portfolio() -> dict:
    bankdb.ensure_db()
    rows = bankdb.execute_readonly(
        "SELECT c.id, c.name, c.type, c.kyc_risk_rating, c.declared_monthly_turnover_aed,"
        " c.onboarded, c.profile_note,"
        " ROUND(SUM(CASE WHEN t.amount_aed > 0 AND t.ts >= '2026-06-01' THEN t.amount_aed ELSE 0 END)) AS june_credits,"
        " COUNT(t.id) AS txn_count"
        " FROM customers c JOIN accounts a ON a.customer_id = c.id"
        " LEFT JOIN transactions t ON t.account_id = a.id"
        " GROUP BY c.id ORDER BY c.name"
    )
    return {"customers": rows.get("rows", [])}


@app.post("/api/screening/run")
def screening_run(role: str = Depends(require_roles("analyst", "rule_admin"))) -> dict:
    from src import rules
    return rules.run_screening(actor_role=role)


@app.get("/api/alerts")
def alerts(active_only: bool = False) -> dict:
    store.ensure_schema()
    where = "WHERE al.is_active=1" if active_only else ""
    rows = bankdb.execute_readonly(
        "SELECT al.*, c.name AS customer_name, cs.status AS case_status, cs.priority, cs.owner "
        "FROM alerts al JOIN customers c ON c.id = al.customer_id "
        "LEFT JOIN cases cs ON cs.id=al.id " + where +
        " ORDER BY CASE al.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
        "WHEN 'medium' THEN 2 ELSE 3 END, al.id"
    )
    result = []
    import json
    for row in rows.get("rows", []):
        row["is_active"] = bool(row.get("is_active", 1))
        try:
            row["evidence"] = json.loads(row.pop("evidence_json", "{}") or "{}")
        except Exception:
            row["evidence"] = {}
        result.append(row)
    return {"alerts": result, "total": len(result)}


@app.get("/api/case")
def legacy_case(alert_id: str = bankdb.ALERT_ID) -> dict:
    return _case_dossier(alert_id)


@app.get("/api/cases")
def cases(status: str | None = None, search: str | None = None) -> dict:
    rows = store.list_cases()
    if status:
        rows = [r for r in rows if r["status"] == status]
    if search:
        needle = search.casefold()
        rows = [r for r in rows if needle in r["id"].casefold() or needle in r["customer_name"].casefold()]
    return {"cases": rows, "total": len(rows)}


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str) -> dict:
    case = _case_or_404(case_id)
    return {**case, "dossier": _case_dossier(case_id)}


@app.get("/api/cases/{case_id}/events")
def case_events(case_id: str, after: int = 0, limit: int = Query(default=500, ge=1, le=1000)) -> dict:
    _case_or_404(case_id)
    rows = store.list_events(case_id, after=after, limit=limit)
    return {"case_id": case_id, "events": rows, "total": len(rows),
            "next_after": rows[-1]["event_id"] if rows else after}


@app.post("/api/cases/{case_id}/notes", status_code=201)
def create_note(case_id: str, body: NoteCreate,
                role: str = Depends(require_roles("analyst", "reviewer"))) -> dict:
    _case_or_404(case_id)
    try:
        return {"note": store.add_note(case_id, body.text, role)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/cases/{case_id}/transition")
def transition(case_id: str, body: CaseTransition,
               role: str = Depends(require_roles("analyst", "reviewer"))) -> dict:
    _case_or_404(case_id)
    try:
        return {"case": store.transition_case(case_id, body.status, body.reason, role)}
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/overview")
def overview() -> dict:
    rows = store.list_cases()
    counts = Counter(r["status"] for r in rows)
    active = [r for r in rows if r["is_active"] and r["status"] != "closed"]
    urgent = [r for r in active if r["priority"] in {"urgent", "high"}]
    pending = [r for r in rows if r["status"] == "pending_review"]
    return {
        "metrics": {
            "active_cases": len(active), "urgent_cases": len(urgent),
            "pending_review": len(pending),
            "coverage": "4 rules",
        },
        "status_counts": dict(counts),
        "priority_queue": active[:5],
        "recent_cases": sorted(rows, key=lambda r: r["updated_at"], reverse=True)[:5],
        "principle": "Rules detect. AI investigates. Humans decide.",
    }


@app.get("/api/analytics")
def analytics() -> dict:
    case_rows = store.list_cases()
    by_status = Counter(r["status"] for r in case_rows)
    by_severity = Counter(r["severity"] for r in case_rows if r["is_active"])
    by_rule = Counter(r["rule"] for r in case_rows if r["is_active"])
    activity = bankdb.execute_readonly(
        "SELECT strftime('%Y-%m', ts) AS month, "
        "ROUND(SUM(CASE WHEN amount_aed>0 THEN amount_aed ELSE 0 END),2) AS credits_aed, "
        "ROUND(SUM(CASE WHEN amount_aed<0 THEN -amount_aed ELSE 0 END),2) AS debits_aed, "
        "COUNT(*) AS transaction_count FROM transactions GROUP BY month ORDER BY month"
    ).get("rows", [])
    alerts_by_rule = [
        {"rule_id": rule, "alerts": count,
         "open": sum(1 for c in case_rows if c["rule"] == rule and c["status"] not in {"closed", "approved"})}
        for rule, count in sorted(by_rule.items())
    ]
    return {
        "summary": {
            "customers_monitored": bankdb.execute_readonly("SELECT COUNT(*) AS n FROM customers")["rows"][0]["n"],
            "transactions_monitored": bankdb.execute_readonly("SELECT COUNT(*) AS n FROM transactions")["rows"][0]["n"],
            "active_alerts": sum(by_rule.values()), "cases": len(case_rows),
        },
        "cases_by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "alerts_by_severity": [{"severity": k, "count": v} for k, v in sorted(by_severity.items())],
        "alerts_by_rule": alerts_by_rule,
        "monthly_activity": activity,
    }


@app.get("/api/rules")
def get_rules() -> dict:
    rules = store.list_rule_configs()
    return {"rules": rules, "total": len(rules),
            "explanation": "Versioned deterministic rules generate alerts; configuration changes do not alter historical events."}


@app.patch("/api/rules/{rule_id}")
def patch_rule(rule_id: str, body: RuleUpdate,
               role: str = Depends(require_roles("rule_admin"))) -> dict:
    if body.enabled is None and body.parameters is None:
        raise HTTPException(422, "Provide enabled and/or parameters")
    try:
        return {"rule": store.update_rule_config(
            rule_id, enabled=body.enabled, parameters=body.parameters, actor_role=role
        )}
    except KeyError as exc:
        raise HTTPException(404, f"Unknown rule: {rule_id}") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/rules/{rule_id}/simulate")
def simulate_rule(rule_id: str, body: RuleSimulation | None = None,
                  role: str = Depends(require_roles("rule_admin"))) -> dict:
    from src import rules
    try:
        baseline_result = rules.evaluate_rule(rule_id)
        result = rules.evaluate_rule(rule_id, (body.parameters if body else None))
    except KeyError as exc:
        raise HTTPException(404, f"Unknown rule: {rule_id}") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    result["simulation_id"] = store.record_rule_run(
        rule_id, "simulation", result["parameters"], {"match_count": result["match_count"]}, role
    )
    delta = result["match_count"] - baseline_result["match_count"]
    result["baseline"] = {
        "parameters": baseline_result["parameters"],
        "match_count": baseline_result["match_count"],
        "customer_ids": [m["customer_id"] for m in baseline_result["matches"]],
    }
    result["candidate"] = {
        "parameters": result["parameters"],
        "match_count": result["match_count"],
        "customer_ids": [m["customer_id"] for m in result["matches"]],
    }
    result["delta"] = delta
    result["summary"] = (
        "No change in alert volume" if delta == 0 else
        f"{abs(delta)} {'more' if delta > 0 else 'fewer'} alert{'s' if abs(delta) != 1 else ''} than baseline"
    )
    return result


@app.get("/api/cases/{case_id}/sar")
def get_sar(case_id: str) -> dict:
    _case_or_404(case_id)
    try:
        return store.get_sar(case_id)
    except KeyError as exc:
        raise HTTPException(404, "No SAR draft exists for this case") from exc


@app.put("/api/cases/{case_id}/sar")
def put_sar(case_id: str, body: dict = Body(...),
            role: str = Depends(require_roles("analyst"))) -> dict:
    _case_or_404(case_id)
    report = body.get("report", body)
    if not isinstance(report, dict):
        raise HTTPException(422, "report must be an object")
    try:
        return store.save_sar(case_id, report, actor_role=role)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/cases/{case_id}/sar/submit")
def submit_sar(case_id: str, role: str = Depends(require_roles("analyst"))) -> dict:
    _case_or_404(case_id)
    try:
        return store.submit_sar(case_id, role)
    except KeyError as exc:
        raise HTTPException(404, "No SAR draft exists for this case") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/cases/{case_id}/sar/review")
def review_sar(case_id: str, body: SARReview,
               role: str = Depends(require_roles("reviewer"))) -> dict:
    _case_or_404(case_id)
    try:
        return store.review_sar(case_id, body.decision, body.comment, role)
    except KeyError as exc:
        raise HTTPException(404, "No SAR draft exists for this case") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _pdf_response(sar: dict, lang: str) -> Response:
    from src import report
    language = "ar" if lang == "ar" else "en"
    pdf = report.build_pdf(sar["report"], lang=language)
    name = f"SAR_{sar['case_id']}_v{sar['version']}_{language}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/api/cases/{case_id}/sar/pdf")
def case_report_pdf(case_id: str, lang: str = "en") -> Response:
    _case_or_404(case_id)
    try:
        return _pdf_response(store.get_sar(case_id), lang)
    except KeyError as exc:
        raise HTTPException(404, "No SAR draft exists for this case") from exc


@app.get("/api/report/pdf")
def legacy_report_pdf(lang: str = "en", case_id: str | None = None) -> Response:
    """Legacy download route; deterministic when ``case_id`` is provided."""
    try:
        sar = store.get_sar(case_id) if case_id else store.latest_sar_any()
    except KeyError as exc:
        raise HTTPException(404, "No SAR generated yet — run an investigation first.") from exc
    return _pdf_response(sar, lang)


@app.get("/api/architecture")
def architecture() -> dict:
    return {
        "principle": "Rules detect. AI investigates. Humans decide.",
        "current": {
            "label": "Implemented reference solution",
            "nodes": [
                {"id": "ui", "label": "React investigation workbench", "layer": "experience", "status": "implemented"},
                {"id": "api", "label": "FastAPI case service", "layer": "application", "status": "implemented"},
                {"id": "rules", "label": "Deterministic AML rules", "layer": "decision", "status": "implemented"},
                {"id": "agent", "label": "OCI Responses API agent", "layer": "intelligence", "status": "implemented"},
                {"id": "guardrails", "label": "OCI AI Guardrails", "layer": "governance", "status": "implemented"},
                {"id": "store", "label": "SQLite ledger + case state", "layer": "data", "status": "implemented"},
                {"id": "evidence", "label": "Trusted policy / untrusted evidence", "layer": "data", "status": "implemented"},
            ],
            "edges": [
                {"from": "ui", "to": "api", "label": "REST + WebSocket"},
                {"from": "api", "to": "rules", "label": "screen + simulate"},
                {"from": "api", "to": "agent", "label": "governed investigation"},
                {"from": "agent", "to": "guardrails", "label": "scan input/output"},
                {"from": "api", "to": "store", "label": "durable workflow"},
                {"from": "agent", "to": "evidence", "label": "separated retrieval paths"},
            ],
        },
        "target": {
            "label": "OCI deployment path",
            "nodes": [
                {"id": "identity", "label": "OCI Identity Domains", "layer": "security", "status": "next"},
                {"id": "runtime", "label": "OCI Hosted Generative AI Application", "layer": "application", "status": "next"},
                {"id": "adb", "label": "Autonomous AI Database", "layer": "data", "status": "optional"},
                {"id": "objects", "label": "Object Storage", "layer": "data", "status": "optional"},
                {"id": "vector", "label": "OCI Generative AI Vector Store", "layer": "intelligence", "status": "optional"},
                {"id": "observability", "label": "Logging, Monitoring & APM", "layer": "operations", "status": "optional"},
            ],
            "edges": [
                {"from": "identity", "to": "runtime", "label": "SSO + roles"},
                {"from": "runtime", "to": "adb", "label": "case records"},
                {"from": "runtime", "to": "objects", "label": "evidence + reports"},
                {"from": "runtime", "to": "vector", "label": "policy retrieval"},
                {"from": "runtime", "to": "observability", "label": "telemetry"},
            ],
        },
        "controls": [
            {"title": "Human approval", "detail": "Every model-proposed ledger query is bound to a run and tool call."},
            {"title": "Corpus separation", "detail": "Only trusted AML policy is searchable; customer evidence is scanned on read."},
            {"title": "Maker-checker", "detail": "Analysts submit drafts; the reviewer approves or requests changes."},
            {"title": "Auditability", "detail": "Investigation events, notes, approvals, rules, and SAR versions persist by case."},
        ],
        "deployment_profiles": [
            {"id": "showcase", "label": "Chicago showcase", "agentic_services": True, "data_residency": "US"},
            {"id": "ksa", "label": "Riyadh deployment", "agentic_services": True, "data_residency": "Saudi Arabia"},
            {"id": "uae", "label": "UAE-resident integration", "agentic_services": False, "data_residency": "UAE", "note": "Use approved regional models and customer-controlled orchestration."},
        ],
    }


@app.websocket("/ws/investigate")
async def ws_investigate(ws: WebSocket) -> None:
    await ws.accept()
    role = ws.query_params.get("role", "analyst").strip().lower()
    if role not in ROLE_INFO:
        await ws.send_json(ev("error", message=f"Unknown simulated role '{role}'"))
        await ws.close(code=1008)
        return
    if role != "analyst":
        await ws.send_json(ev("error", message="Only the AML Analyst persona can run an investigation."))
        await ws.close(code=1008)
        return

    engine = ws.query_params.get("engine", "auto")
    alert_id = ws.query_params.get("case", bankdb.ALERT_ID)
    if engine not in {"auto", "demo", "live"}:
        await ws.send_json(ev("error", message=f"Unknown investigation engine '{engine}'"))
        await ws.close(code=1008)
        return
    if engine == "auto":
        engine = "live" if config.live_configured() else "demo"
    try:
        _ensure_alert(alert_id)
    except HTTPException as exc:
        await ws.send_json(ev("error", message=str(exc.detail)))
        await ws.close(code=1008)
        return
    if engine == "demo" and alert_id != bankdb.ALERT_ID:
        await ws.send_json(ev(
            "error", message=f"Demo mode replays {bankdb.ALERT_ID}. Configure live credentials for other cases."
        ))
        await ws.close(code=1008)
        return

    run = store.start_run(alert_id, engine, role)
    run_id = run["id"]
    pending_call_id: str | None = None
    decisions: dict[str, bool] = {}

    async def ask() -> dict:
        nonlocal pending_call_id
        try:
            decision = await ws.receive_json()
        except Exception:
            decision = {"approve": False}
        call_id = pending_call_id
        if not call_id:
            return {"approve": False}
        supplied_call = decision.get("id") or decision.get("call_id")
        supplied_run = decision.get("run_id")
        identifiers_match = ((supplied_call is None or supplied_call == call_id)
                             and (supplied_run is None or supplied_run == run_id))
        approved = bool(decision.get("approve", False)) and identifiers_match
        recorded = store.decide_approval(run_id, call_id, approved, role)
        approved = approved and recorded
        decisions[call_id] = approved
        return {"approve": approved, "call_id": call_id, "run_id": run_id}

    if engine == "demo":
        from src import demo_tape
        runner = demo_tape.play(ask)
    else:
        from src import agent
        runner = agent.investigate(ask, alert_id)

    pending_sar: dict | None = None
    pii_hits: list[dict] | None = None

    async def send_event(event: dict) -> None:
        enriched = {**event, "run_id": run_id}
        event_id = store.append_event(
            alert_id, event.get("type", "unknown"), enriched, run_id=run_id,
            actor_role=role, call_id=event.get("id"),
        )
        enriched["event_id"] = event_id
        await ws.send_json(enriched)

    async def release_sar(event: dict) -> None:
        # save_sar validates the structured contract before the UI sees it.
        saved = store.save_sar(
            alert_id, event["report"], actor_role=role, pii_hits=pii_hits or [], source_run_id=run_id
        )
        await send_event({**event, "version": saved["version"], "status": saved["status"]})

    try:
        async for raw_event in runner:
            event = dict(raw_event)
            kind = event.get("type")
            if kind == "approval_request":
                pending_call_id = event.get("id")
                event["run_id"] = run_id
                store.request_approval(
                    alert_id, run_id, pending_call_id or "unknown", event.get("sql", ""), event.get("purpose", "")
                )
            elif kind == "approval_result":
                call_id = event.get("id")
                if call_id in decisions:
                    event["approved"] = decisions[call_id]
                pending_call_id = None
            elif kind == "memory":
                store.update_run(run_id, conversation_id=event.get("conversation_id"))
            elif kind == "step":
                store.update_run(run_id, current_step=int(event.get("n", 0)))

            # The recorded v1 tape emits SAR then PII.  Buffering makes both
            # demo and live modes obey PII-before-release without rewriting
            # historical evidence.
            if kind == "sar":
                pending_sar = event
                if pii_hits is not None:
                    await release_sar(pending_sar)
                    pending_sar = None
                continue
            if kind == "pii":
                pii_hits = event.get("hits", [])
                await send_event(event)
                if pending_sar is not None:
                    await release_sar(pending_sar)
                    pending_sar = None
                continue

            if kind == "done" and pending_sar is not None:
                # A missing output scan is a failed governance check: do not
                # expose or persist the report.
                await send_event(ev("error", message="SAR output scan did not complete; draft was withheld."))
                pending_sar = None
            await send_event(event)
        store.update_run(run_id, status="completed")
    except WebSocketDisconnect:
        store.update_run(run_id, status="interrupted", error="Client disconnected")
    except Exception as exc:
        store.update_run(run_id, status="failed", error=str(exc)[:1000])
        try:
            await send_event(ev("error", message=f"Investigation could not complete: {exc}"))
        except Exception:
            pass


# Serve the built React app after every API route.  Resolution and containment
# checks prevent paths such as /../.env from escaping web/dist.
if config.WEB_DIST.exists():
    assets = config.WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path == "api" or path.startswith(("api/", "ws/")):
            raise HTTPException(404, "Route not found")
        root = config.WEB_DIST.resolve()
        target = (root / path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise HTTPException(404, "File not found") from exc
        if path and target.is_file():
            return FileResponse(target)
        # Client-side routes are extensionless.  A missing file-like path (or
        # dotfile) must not fall through to index.html, which keeps traversal
        # probes and accidental asset URLs unambiguous.
        parts = Path(path).parts
        if Path(path).suffix or any(part.startswith(".") for part in parts):
            raise HTTPException(404, "File not found")
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(404, "Web application is not built")
        return FileResponse(index)
