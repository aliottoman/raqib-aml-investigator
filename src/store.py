"""Durable application state for the Raqib portfolio solution.

Author: Ali Ottoman

The seeded bank ledger remains deliberately small and deterministic.  This
module adds the product-shaped state around it (cases, investigation runs,
events, approvals, notes, SAR versions, and editable rule configuration)
using additive SQLite migrations.  Existing ledger data is never dropped.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import config
from src import bankdb


PRODUCT_SCHEMA_VERSION = 2

PRODUCT_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    owner TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS investigation_runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by_role TEXT NOT NULL,
    conversation_id TEXT,
    current_step INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(case_id) REFERENCES cases(id)
);
CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    run_id TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    actor_role TEXT,
    call_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id),
    FOREIGN KEY(run_id) REFERENCES investigation_runs(id)
);
CREATE INDEX IF NOT EXISTS ix_case_events_case_id ON case_events(case_id, id);
CREATE TABLE IF NOT EXISTS case_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    text TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id)
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    call_id TEXT NOT NULL,
    purpose TEXT,
    sql_text TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending',
    decided_by_role TEXT,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE(run_id, call_id),
    FOREIGN KEY(case_id) REFERENCES cases(id),
    FOREIGN KEY(run_id) REFERENCES investigation_runs(id)
);
CREATE TABLE IF NOT EXISTS sar_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    report_json TEXT NOT NULL,
    pii_hits_json TEXT NOT NULL DEFAULT '[]',
    source_run_id TEXT,
    created_by_role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    reviewed_at TEXT,
    reviewed_by_role TEXT,
    review_comment TEXT,
    UNIQUE(case_id, version),
    FOREIGN KEY(case_id) REFERENCES cases(id)
);
CREATE INDEX IF NOT EXISTS ix_sar_versions_case_id ON sar_versions(case_id, version DESC);
CREATE TABLE IF NOT EXISTS rule_configs (
    rule_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    parameters_json TEXT NOT NULL,
    updated_by_role TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rule_runs (
    id TEXT PRIMARY KEY,
    rule_id TEXT,
    run_type TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_by_role TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(*, readonly: bool = False) -> sqlite3.Connection:
    bankdb.ensure_db()
    if readonly:
        con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(str(config.DB_PATH), timeout=10)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
    con.row_factory = sqlite3.Row
    return con


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def ensure_schema() -> None:
    """Apply only additive product-state migrations and seed safe defaults."""
    con = _connect()
    try:
        con.executescript(PRODUCT_SCHEMA)
        now = utcnow()
        # These alert columns make repeat screening explainable without
        # replacing the seeded alert table or its existing rows.
        columns = {r[1] for r in con.execute("PRAGMA table_info(alerts)")}
        additions = {
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "rule_version": "INTEGER NOT NULL DEFAULT 1",
            "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            "updated_at": "TEXT",
        }
        for name, ddl in additions.items():
            if name not in columns:
                con.execute(f"ALTER TABLE alerts ADD COLUMN {name} {ddl}")

        _sync_cases(con)
        # v1 of the demo marked generated (but unreviewed and non-persisted)
        # output as "sar_filed".  There is no regulatory filing record to
        # preserve, so normalize only those orphaned statuses back to open.
        con.execute(
            "UPDATE alerts SET status='open', updated_at=? WHERE status='sar_filed' "
            "AND NOT EXISTS (SELECT 1 FROM sar_versions s WHERE s.case_id=alerts.id)",
            (now,),
        )
        con.execute(
            "UPDATE cases SET status='open', updated_at=? WHERE status='draft_ready' "
            "AND NOT EXISTS (SELECT 1 FROM sar_versions s WHERE s.case_id=cases.id)",
            (now,),
        )
        _seed_rules(con)
        con.execute(
            "INSERT OR IGNORE INTO app_migrations(version, applied_at) VALUES (?,?)",
            (PRODUCT_SCHEMA_VERSION, now),
        )
        con.commit()
    finally:
        con.close()


def _status_from_legacy(status: str) -> str:
    # A generated report was historically marked "filed" before review.
    # Preserve the record, but represent it honestly in the case lifecycle.
    return {
        "sar_filed": "draft_ready",
        "closed_no_sar": "closed",
    }.get(status, status if status in {"open", "investigating"} else "open")


def _sync_cases(con: sqlite3.Connection) -> None:
    now = utcnow()
    rows = con.execute(
        "SELECT a.id, a.customer_id, a.severity, a.status, a.created, c.name "
        "FROM alerts a JOIN customers c ON c.id=a.customer_id"
    ).fetchall()
    for row in rows:
        priority = {"critical": "urgent", "high": "high", "medium": "medium", "low": "low"}.get(
            row["severity"], "medium"
        )
        con.execute(
            "INSERT OR IGNORE INTO cases "
            "(id, alert_id, customer_id, title, status, priority, owner, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                row["id"], row["id"], row["customer_id"],
                f"{row['name']} · {row['id']}", _status_from_legacy(row["status"]),
                priority, "AML Investigations", row["created"] or now, now,
            ),
        )


def sync_cases() -> None:
    ensure_schema()
    con = _connect()
    try:
        _sync_cases(con)
        con.commit()
    finally:
        con.close()


def _seed_rules(con: sqlite3.Connection) -> None:
    from src.rules import RULE_DEFINITIONS

    now = utcnow()
    for definition in RULE_DEFINITIONS:
        con.execute(
            "INSERT OR IGNORE INTO rule_configs "
            "(rule_id,label,description,version,enabled,parameters_json,updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                definition["rule"], definition["label"], definition["what"], 1, 1,
                _json(definition["parameters"]), now,
            ),
        )


def list_rule_configs() -> list[dict]:
    ensure_schema()
    con = _connect(readonly=True)
    try:
        rows = con.execute("SELECT * FROM rule_configs ORDER BY rule_id").fetchall()
        return [
            {
                "rule_id": r["rule_id"], "rule": r["rule_id"], "label": r["label"],
                "description": r["description"], "what": r["description"],
                "version": r["version"], "enabled": bool(r["enabled"]),
                "parameters": _loads(r["parameters_json"], {}),
                "updated_by_role": r["updated_by_role"], "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        con.close()


def get_rule_config(rule_id: str) -> dict:
    for rule in list_rule_configs():
        if rule["rule_id"] == rule_id:
            return rule
    raise KeyError(rule_id)


def update_rule_config(rule_id: str, *, enabled: bool | None, parameters: dict | None,
                       actor_role: str) -> dict:
    current = get_rule_config(rule_id)
    merged = dict(current["parameters"])
    if parameters is not None:
        unknown = sorted(set(parameters) - set(merged))
        if unknown:
            raise ValueError(f"Unknown parameter(s): {', '.join(unknown)}")
        for key, value in parameters.items():
            expected = type(merged[key])
            if expected is bool:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be a boolean")
            elif expected in {int, float}:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{key} must be numeric")
                if value <= 0:
                    raise ValueError(f"{key} must be greater than zero")
            merged[key] = value
    next_enabled = current["enabled"] if enabled is None else enabled
    con = _connect()
    try:
        con.execute(
            "UPDATE rule_configs SET enabled=?, parameters_json=?, version=version+1, "
            "updated_by_role=?, updated_at=? WHERE rule_id=?",
            (int(next_enabled), _json(merged), actor_role, utcnow(), rule_id),
        )
        con.commit()
    finally:
        con.close()
    return get_rule_config(rule_id)


def record_rule_run(rule_id: str | None, run_type: str, parameters: dict,
                    result: dict, actor_role: str) -> str:
    run_id = f"rr_{uuid.uuid4().hex[:12]}"
    con = _connect()
    try:
        con.execute(
            "INSERT INTO rule_runs VALUES (?,?,?,?,?,?,?)",
            (run_id, rule_id, run_type, _json(parameters), _json(result), actor_role, utcnow()),
        )
        con.commit()
        return run_id
    finally:
        con.close()


def list_cases() -> list[dict]:
    sync_cases()
    con = _connect(readonly=True)
    try:
        rows = con.execute(
            "SELECT cs.*, a.rule, a.severity, a.summary, a.created AS alert_created, "
            "a.is_active, c.name AS customer_name, c.type AS customer_type, "
            "c.kyc_risk_rating, "
            "(SELECT COUNT(*) FROM case_notes n WHERE n.case_id=cs.id) AS note_count, "
            "(SELECT COUNT(*) FROM case_events e WHERE e.case_id=cs.id) AS event_count, "
            "(SELECT status FROM sar_versions s WHERE s.case_id=cs.id ORDER BY version DESC LIMIT 1) AS sar_status "
            "FROM cases cs JOIN alerts a ON a.id=cs.alert_id "
            "JOIN customers c ON c.id=cs.customer_id "
            "ORDER BY CASE cs.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 ELSE 3 END, cs.updated_at DESC"
        ).fetchall()
        return [{**dict(r), "is_active": bool(r["is_active"])} for r in rows]
    finally:
        con.close()


def get_case(case_id: str) -> dict:
    ensure_schema()
    con = _connect(readonly=True)
    try:
        row = con.execute(
            "SELECT cs.*, a.rule, a.severity, a.summary, a.created AS alert_created, "
            "a.status AS alert_status, a.is_active, a.rule_version, a.evidence_json, "
            "c.name AS customer_name, c.type AS customer_type, c.country, "
            "c.kyc_risk_rating, c.declared_monthly_turnover_aed, c.onboarded, c.profile_note "
            "FROM cases cs JOIN alerts a ON a.id=cs.alert_id "
            "JOIN customers c ON c.id=cs.customer_id WHERE cs.id=?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        result = dict(row)
        result["is_active"] = bool(result["is_active"])
        result["evidence"] = _loads(result.pop("evidence_json"), {})
        result["notes"] = [dict(r) for r in con.execute(
            "SELECT id,text,actor_role,created_at FROM case_notes WHERE case_id=? ORDER BY id DESC",
            (case_id,),
        ).fetchall()]
        result["latest_run"] = _row_or_none(con.execute(
            "SELECT * FROM investigation_runs WHERE case_id=? ORDER BY started_at DESC LIMIT 1",
            (case_id,),
        ).fetchone())
        latest = con.execute(
            "SELECT version,status,updated_at FROM sar_versions WHERE case_id=? ORDER BY version DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        result["sar"] = dict(latest) if latest else None
        return result
    finally:
        con.close()


def _row_or_none(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def add_note(case_id: str, text: str, actor_role: str) -> dict:
    get_case(case_id)
    clean = " ".join(text.split()).strip()
    if not clean:
        raise ValueError("Note text cannot be empty")
    if len(clean) > 2000:
        raise ValueError("Note text cannot exceed 2,000 characters")
    now = utcnow()
    con = _connect()
    try:
        cur = con.execute(
            "INSERT INTO case_notes(case_id,text,actor_role,created_at) VALUES (?,?,?,?)",
            (case_id, clean, actor_role, now),
        )
        con.execute("UPDATE cases SET updated_at=? WHERE id=?", (now, case_id))
        con.commit()
        note = {"id": cur.lastrowid, "case_id": case_id, "text": clean,
                "actor_role": actor_role, "created_at": now}
    finally:
        con.close()
    append_event(case_id, "note_added", {"note": note}, actor_role=actor_role)
    return note


TRANSITIONS = {
    "open": {"investigating", "closed"},
    "investigating": {"open", "draft_ready", "closed"},
    "draft_ready": {"investigating", "pending_review", "closed"},
    "changes_requested": {"investigating", "draft_ready", "pending_review", "closed"},
    "pending_review": {"approved", "changes_requested", "closed"},
    "approved": {"closed"},
    "closed": {"open"},
}


def transition_case(case_id: str, status: str, reason: str | None, actor_role: str,
                    *, force: bool = False) -> dict:
    current = get_case(case_id)
    old = current["status"]
    if status == old:
        return current
    if not force and status not in TRANSITIONS.get(old, set()):
        raise ValueError(f"Cannot transition case from '{old}' to '{status}'")
    if actor_role == "analyst" and status in {"approved", "changes_requested"}:
        raise PermissionError("Only a reviewer can approve a case or request SAR changes")
    if actor_role == "reviewer" and status == "investigating":
        raise PermissionError("Only an analyst can start an investigation")
    now = utcnow()
    con = _connect()
    try:
        con.execute(
            "UPDATE cases SET status=?, updated_at=?, closed_at=? WHERE id=?",
            (status, now, now if status == "closed" else None, case_id),
        )
        # Alert status remains operational and never claims regulatory filing.
        alert_status = {
            "open": "open", "investigating": "investigating", "draft_ready": "sar_draft",
            "pending_review": "pending_review", "approved": "sar_approved",
            "changes_requested": "changes_requested", "closed": "closed",
        }[status]
        con.execute("UPDATE alerts SET status=?, updated_at=? WHERE id=?", (alert_status, now, case_id))
        con.commit()
    finally:
        con.close()
    append_event(case_id, "case_transition", {"from": old, "to": status, "reason": reason or ""},
                 actor_role=actor_role)
    return get_case(case_id)


def start_run(case_id: str, engine: str, actor_role: str) -> dict:
    get_case(case_id)
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    now = utcnow()
    con = _connect()
    try:
        con.execute(
            "INSERT INTO investigation_runs "
            "(id,case_id,engine,status,created_by_role,started_at) VALUES (?,?,?,?,?,?)",
            (run_id, case_id, engine, "running", actor_role, now),
        )
        con.commit()
    finally:
        con.close()
    try:
        transition_case(case_id, "investigating", "Investigation started", actor_role)
    except ValueError:
        # Re-running a draft/changed case is allowed and retains its lifecycle.
        pass
    return {"id": run_id, "case_id": case_id, "engine": engine, "status": "running",
            "created_by_role": actor_role, "started_at": now}


def update_run(run_id: str, *, status: str | None = None, conversation_id: str | None = None,
               current_step: int | None = None, error: str | None = None) -> None:
    fields, values = [], []
    for name, value in (("status", status), ("conversation_id", conversation_id),
                        ("current_step", current_step), ("error", error)):
        if value is not None:
            fields.append(f"{name}=?")
            values.append(value)
    if status in {"completed", "failed", "interrupted", "cancelled"}:
        fields.append("completed_at=?")
        values.append(utcnow())
    if not fields:
        return
    values.append(run_id)
    con = _connect()
    try:
        con.execute(f"UPDATE investigation_runs SET {', '.join(fields)} WHERE id=?", values)
        con.commit()
    finally:
        con.close()


def get_run(run_id: str) -> dict:
    ensure_schema()
    con = _connect(readonly=True)
    try:
        row = con.execute("SELECT * FROM investigation_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return dict(row)
    finally:
        con.close()


def list_runs(case_id: str) -> list[dict]:
    """Every investigation run for a case, most recent first."""
    get_case(case_id)
    con = _connect(readonly=True)
    try:
        rows = con.execute(
            "SELECT * FROM investigation_runs WHERE case_id=? ORDER BY started_at DESC, id DESC",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# A run is durable state, not a socket. Statuses here mean:
#   running     — a background task is (or should be) driving it
#   completed   — finished and released its SAR draft
#   cancelled   — an operator stopped it
#   failed      — the run raised
#   interrupted — the driving process died mid-run (see reconcile_stale_runs)
ACTIVE_RUN_STATUS = "running"


def reconcile_stale_runs() -> int:
    """Mark runs orphaned by a process restart as interrupted.

    A run left ``running`` cannot have a live background task after a restart,
    so it is closed honestly rather than appearing perpetually in-flight. The
    persisted ``conversation_id`` still allows a future resume-from-memory
    (or OCI Queue re-dispatch) path.
    """
    con = _connect()
    try:
        cur = con.execute(
            "UPDATE investigation_runs SET status='interrupted', "
            "error=COALESCE(error,'Process restarted before completion'), completed_at=? "
            "WHERE status=?",
            (utcnow(), ACTIVE_RUN_STATUS),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def append_event(case_id: str, event_type: str, payload: dict, *, run_id: str | None = None,
                 actor_role: str | None = None, call_id: str | None = None) -> int:
    now = utcnow()
    con = _connect()
    try:
        cur = con.execute(
            "INSERT INTO case_events(case_id,run_id,event_type,payload_json,actor_role,call_id,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (case_id, run_id, event_type, _json(payload), actor_role, call_id, now),
        )
        con.execute("UPDATE cases SET updated_at=? WHERE id=?", (now, case_id))
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def list_events(case_id: str, *, after: int = 0, limit: int = 500) -> list[dict]:
    get_case(case_id)
    safe_limit = max(1, min(limit, 1000))
    con = _connect(readonly=True)
    try:
        rows = con.execute(
            "SELECT * FROM case_events WHERE case_id=? AND id>? ORDER BY id LIMIT ?",
            (case_id, after, safe_limit),
        ).fetchall()
        result = []
        for row in rows:
            payload = _loads(row["payload_json"], {}) or {}
            # Rehydrate the original WebSocket event shape so a refreshed UI
            # can feed persisted events through the same timeline renderer.
            # Database metadata uses distinct names and cannot overwrite tool
            # call ids from the payload.
            item = {
                **payload,
                "id": payload.get("id", row["id"]),
                "event_id": row["id"],
                "case_id": row["case_id"],
                "run_id": payload.get("run_id") or row["run_id"],
                "type": payload.get("type") or row["event_type"],
                "event_type": row["event_type"],
                "actor_role": row["actor_role"],
                "call_id": row["call_id"],
                "created_at": row["created_at"],
                "payload": payload,
            }
            result.append(item)
        return result
    finally:
        con.close()


def request_approval(case_id: str, run_id: str, call_id: str, sql: str, purpose: str) -> None:
    con = _connect()
    try:
        con.execute(
            "INSERT INTO approvals "
            "(case_id,run_id,call_id,purpose,sql_text,decision,requested_at) VALUES (?,?,?,?,?,'pending',?) "
            "ON CONFLICT(run_id,call_id) DO NOTHING",
            (case_id, run_id, call_id, purpose, sql, utcnow()),
        )
        con.commit()
    finally:
        con.close()


def decide_approval(run_id: str, call_id: str, approved: bool, actor_role: str) -> bool:
    con = _connect()
    try:
        row = con.execute(
            "SELECT decision FROM approvals WHERE run_id=? AND call_id=?", (run_id, call_id)
        ).fetchone()
        if row is None or row["decision"] != "pending":
            return False
        con.execute(
            "UPDATE approvals SET decision=?, decided_by_role=?, decided_at=? "
            "WHERE run_id=? AND call_id=?",
            ("approved" if approved else "declined", actor_role, utcnow(), run_id, call_id),
        )
        con.commit()
        return True
    finally:
        con.close()


def save_sar(case_id: str, report: dict, *, actor_role: str,
             pii_hits: list[dict] | None = None, source_run_id: str | None = None) -> dict:
    from src.schemas import SARReport

    get_case(case_id)
    payload = dict(report)
    payload["case_id"] = case_id
    validated = SARReport.model_validate(payload).model_dump()
    now = utcnow()
    con = _connect()
    try:
        version = int(con.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM sar_versions WHERE case_id=?", (case_id,)
        ).fetchone()[0])
        con.execute(
            "INSERT INTO sar_versions "
            "(case_id,version,status,report_json,pii_hits_json,source_run_id,created_by_role,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (case_id, version, "draft", _json(validated), _json(pii_hits or []), source_run_id,
             actor_role, now, now),
        )
        con.commit()
    finally:
        con.close()
    transition_case(case_id, "draft_ready", "SAR draft created", actor_role, force=True)
    append_event(case_id, "sar_draft_saved", {"version": version, "pii_hits": pii_hits or []},
                 run_id=source_run_id, actor_role=actor_role)
    return get_sar(case_id)


def get_sar(case_id: str) -> dict:
    get_case(case_id)
    con = _connect(readonly=True)
    try:
        row = con.execute(
            "SELECT * FROM sar_versions WHERE case_id=? ORDER BY version DESC LIMIT 1", (case_id,)
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        return {
            "case_id": row["case_id"], "version": row["version"], "status": row["status"],
            "report": _loads(row["report_json"], {}), "pii_hits": _loads(row["pii_hits_json"], []),
            "source_run_id": row["source_run_id"], "created_by_role": row["created_by_role"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "submitted_at": row["submitted_at"], "reviewed_at": row["reviewed_at"],
            "reviewed_by_role": row["reviewed_by_role"], "review_comment": row["review_comment"],
        }
    finally:
        con.close()


def latest_sar_any() -> dict:
    ensure_schema()
    con = _connect(readonly=True)
    try:
        row = con.execute(
            "SELECT case_id FROM sar_versions ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise KeyError("No SAR")
    return get_sar(row["case_id"])


def submit_sar(case_id: str, actor_role: str) -> dict:
    sar = get_sar(case_id)
    if sar["status"] not in {"draft", "changes_requested"}:
        raise ValueError(f"A SAR in '{sar['status']}' status cannot be submitted")
    now = utcnow()
    con = _connect()
    try:
        con.execute(
            "UPDATE sar_versions SET status='pending_review', submitted_at=?, updated_at=? "
            "WHERE case_id=? AND version=?",
            (now, now, case_id, sar["version"]),
        )
        con.commit()
    finally:
        con.close()
    transition_case(case_id, "pending_review", "SAR submitted for reviewer approval", actor_role, force=True)
    append_event(case_id, "sar_submitted", {"version": sar["version"]}, actor_role=actor_role)
    return get_sar(case_id)


def review_sar(case_id: str, decision: str, comment: str | None, actor_role: str) -> dict:
    sar = get_sar(case_id)
    if sar["status"] != "pending_review":
        raise ValueError("Only a submitted SAR can be reviewed")
    if decision not in {"approved", "changes_requested"}:
        raise ValueError("decision must be 'approved' or 'changes_requested'")
    now = utcnow()
    con = _connect()
    try:
        con.execute(
            "UPDATE sar_versions SET status=?, reviewed_at=?, reviewed_by_role=?, "
            "review_comment=?, updated_at=? WHERE case_id=? AND version=?",
            (decision, now, actor_role, (comment or "").strip(), now, case_id, sar["version"]),
        )
        con.commit()
    finally:
        con.close()
    transition_case(case_id, decision, comment or "Reviewer decision", actor_role, force=True)
    append_event(case_id, "sar_reviewed", {"version": sar["version"], "decision": decision,
                 "comment": (comment or "").strip()}, actor_role=actor_role)
    return get_sar(case_id)
