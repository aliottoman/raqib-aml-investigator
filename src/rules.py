"""
Raqib — the AML detection rules (the "checker").

Four deterministic SQL rules sweep the whole ledger and write the alert
queue. This mirrors real AML architecture: a rules engine *detects*, the
agent *investigates*. Rules are plain SQL + a little Python — no LLM here,
so screening is instant, explainable, and identical every run.

Alert ids are deterministic (rule base + customer id) so the flagship case
is always RQB-2026-0347 — the id the recorded demo tape investigates.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json

import config
from src import bankdb

_ID_BASE = {"CASH-VELOCITY-04": 340, "WATCHLIST-PROX-01": 350,
            "PROFILE-DEVIATION-02": 360, "DORMANT-SPIKE-03": 370}

# The four original curated cases keep their historical ids verbatim — the demo
# tape and golden evals reference them by string. Every other (rule, customer)
# pair derives an id from the rule base + customer_id % 100, which gives ample
# headroom; run_screening additionally asserts ids are unique so a collision can
# never silently merge two customers' alerts through the ON CONFLICT upsert.
_CANONICAL_ALERT_IDS = {
    ("CASH-VELOCITY-04", bankdb.CUSTOMER_ID): "RQB-2026-0347",
    ("WATCHLIST-PROX-01", bankdb.CUSTOMER_ID): "RQB-2026-0357",
    ("PROFILE-DEVIATION-02", 1044): "RQB-2026-0364",
    ("DORMANT-SPIKE-03", 1031): "RQB-2026-0371",
}

RULE_DEFINITIONS = [
    {"rule": "CASH-VELOCITY-04", "label": "Sub-threshold cash velocity",
     "what": "3+ cash deposits under the CTR threshold within a rolling 10-business-day window (policy §4.2)",
     "parameters": {"window_business_days": 10, "minimum_deposits": 3,
                    "minimum_branches": 3, "threshold_aed": bankdb.THRESHOLD_AED,
                    "threshold_floor_ratio": 0.7, "lookback_days": 30}},
    {"rule": "WATCHLIST-PROX-01", "label": "Watchlist proximity",
     "what": "Outbound wires to counterparties linked to watchlist records (policy §6.1)",
     "parameters": {"minimum_total_aed": 1}},
    {"rule": "PROFILE-DEVIATION-02", "label": "Profile deviation",
     "what": "Credits above 200% of declared turnover for two consecutive months (policy §5.4)",
     "parameters": {"ratio_threshold": 2.0, "consecutive_months": 2}},
    {"rule": "DORMANT-SPIKE-03", "label": "Dormant account spike",
     "what": "60+ quiet days followed by an outsized single credit",
     "parameters": {"quiet_days": 60, "spike_multiplier": 1.2, "followup_days": 14}},
]

# Backwards-compatible summary used by the existing dashboard response.
RULE_META = [{k: v for k, v in rule.items() if k != "parameters"} for rule in RULE_DEFINITIONS]

RULE_IDS = {r["rule"] for r in RULE_DEFINITIONS}
AS_OF_DATE = date(2026, 6, 28)


def _alert_id(rule: str, customer_id: int) -> str:
    canonical = _CANONICAL_ALERT_IDS.get((rule, customer_id))
    if canonical:
        return canonical
    return f"RQB-2026-{_ID_BASE[rule] + customer_id % 100:04d}"


def _business_days_inclusive(start: date, end: date) -> int:
    """Count weekdays in an inclusive interval (the policy's window unit)."""
    if end < start:
        return 0
    return sum(1 for n in range((end - start).days + 1)
               if (start + timedelta(days=n)).weekday() < 5)


def _cash_velocity(con, params: dict | None = None) -> list[dict]:
    p = params or RULE_DEFINITIONS[0]["parameters"]
    threshold = float(p["threshold_aed"])
    floor = threshold * float(p["threshold_floor_ratio"])
    earliest = AS_OF_DATE - timedelta(days=int(p["lookback_days"]))
    rows = con.execute(
        "SELECT a.customer_id, c.name, c.declared_monthly_turnover_aed AS declared, "
        "date(t.ts) AS day, t.branch, t.amount_aed "
        "FROM transactions t JOIN accounts a ON a.id=t.account_id "
        "JOIN customers c ON c.id=a.customer_id "
        "WHERE t.type='cash_deposit' AND t.amount_aed>=? AND t.amount_aed<? "
        "AND date(t.ts)>=? AND date(t.ts)<=? ORDER BY a.customer_id,t.ts",
        (floor, threshold, earliest.isoformat(), AS_OF_DATE.isoformat()),
    ).fetchall()
    by_customer: dict[int, list] = defaultdict(list)
    for row in rows:
        by_customer[row["customer_id"]].append(row)

    alerts = []
    for customer_id, txns in by_customer.items():
        best: list = []
        for start_idx, start in enumerate(txns):
            start_d = date.fromisoformat(start["day"])
            window = []
            for candidate in txns[start_idx:]:
                end_d = date.fromisoformat(candidate["day"])
                if _business_days_inclusive(start_d, end_d) > int(p["window_business_days"]):
                    break
                window.append(candidate)
            branches = {r["branch"] for r in window}
            if (len(window) >= int(p["minimum_deposits"])
                    and len(branches) >= int(p["minimum_branches"])
                    and len(window) > len(best)):
                best = window
        if not best:
            continue
        first_d, last_d = best[0]["day"], best[-1]["day"]
        business_days = _business_days_inclusive(date.fromisoformat(first_d), date.fromisoformat(last_d))
        total = sum(float(r["amount_aed"]) for r in best)
        branches = len({r["branch"] for r in best})
        sample = best[0]
        alerts.append({
            "id": _alert_id("CASH-VELOCITY-04", customer_id),
            "customer_id": customer_id, "customer_name": sample["name"],
            "rule": "CASH-VELOCITY-04", "severity": "critical",
            "summary": (f"{len(best)} cash deposits below the AED {threshold:,.0f} reporting "
                        f"threshold across {branches} branches within {business_days} business days; aggregate "
                        f"AED ~{total/1000:,.0f}k vs declared turnover AED {sample['declared']/1000:,.0f}k/month."),
            "created": f"{last_d} 08:12:00",
            "evidence": {"deposits": len(best), "branches": branches,
                         "aggregate_aed": round(total, 2), "first_date": first_d,
                         "last_date": last_d, "business_days": business_days,
                         "threshold_aed": threshold},
        })
    return alerts


def _watchlist_proximity(con, params: dict | None = None) -> list[dict]:
    p = params or RULE_DEFINITIONS[1]["parameters"]
    rows = con.execute(
        "SELECT DISTINCT a.customer_id, c.name, t.counterparty, w.entity_name, w.list_name,"
        " SUM(-t.amount_aed) OVER (PARTITION BY a.customer_id, t.counterparty) AS total "
        "FROM transactions t JOIN accounts a ON a.id = t.account_id "
        "JOIN customers c ON c.id = a.customer_id "
        "JOIN watchlist w ON (instr(w.notes, t.counterparty) > 0 OR w.entity_name = t.counterparty) "
        "WHERE t.type='wire_out'").fetchall()
    return [{
        "id": _alert_id("WATCHLIST-PROX-01", r["customer_id"]),
        "customer_id": r["customer_id"], "customer_name": r["name"],
        "rule": "WATCHLIST-PROX-01", "severity": "high",
        "summary": (f"Outbound wires of AED {r['total']:,.0f} to \"{r['counterparty']}\" — linked to "
                    f"{r['entity_name']} ({r['list_name']})."),
        "created": "2026-06-19 09:05:00",
        "evidence": {"counterparty": r["counterparty"], "linked_record": r["entity_name"]},
    } for r in rows if float(r["total"]) >= float(p["minimum_total_aed"])]


def _profile_deviation(con, params: dict | None = None) -> list[dict]:
    p = params or RULE_DEFINITIONS[2]["parameters"]
    rows = con.execute(
        "SELECT a.customer_id, c.name, c.declared_monthly_turnover_aed AS declared,"
        " strftime('%Y-%m', t.ts) AS month, SUM(t.amount_aed) AS credits "
        "FROM transactions t JOIN accounts a ON a.id = t.account_id "
        "JOIN customers c ON c.id = a.customer_id "
        "WHERE t.amount_aed > 0 AND t.ts >= '2026-05-01' AND t.ts < '2026-07-01' "
        "GROUP BY a.customer_id, month").fetchall()
    by_cust = defaultdict(dict)
    meta = {}
    for r in rows:
        by_cust[r["customer_id"]][r["month"]] = r["credits"] / max(r["declared"], 1)
        meta[r["customer_id"]] = (r["name"], r["declared"])
    alerts = []
    for cid, months in by_cust.items():
        ordered = [months.get("2026-05", 0), months.get("2026-06", 0)]
        count = min(int(p["consecutive_months"]), len(ordered))
        ratios = ordered[-count:]
        if len(ratios) == int(p["consecutive_months"]) and all(
                x >= float(p["ratio_threshold"]) for x in ratios):
            name, declared = meta[cid]
            alerts.append({
                "id": _alert_id("PROFILE-DEVIATION-02", cid),
                "customer_id": cid, "customer_name": name,
                "rule": "PROFILE-DEVIATION-02", "severity": "medium",
                "summary": (f"Monthly credits ran {ratios[0]:.0%} and {ratios[1]:.0%} of the declared "
                            f"AED {declared/1000:,.0f}k/month for two consecutive months (May–June 2026)."),
                "created": "2026-06-30 07:40:00",
                "evidence": {"may_ratio": round(ratios[0], 2), "june_ratio": round(ratios[1], 2)},
            })
    return alerts


def _dormant_spike(con, params: dict | None = None) -> list[dict]:
    p = params or RULE_DEFINITIONS[3]["parameters"]
    alerts = []
    accounts = con.execute(
        "SELECT a.id, a.customer_id, c.name, c.declared_monthly_turnover_aed AS declared "
        "FROM accounts a JOIN customers c ON c.id = a.customer_id").fetchall()
    for acc in accounts:
        txns = con.execute("SELECT ts, amount_aed FROM transactions WHERE account_id=? ORDER BY ts",
                           (acc["id"],)).fetchall()
        prev, resumed, quiet_days = None, None, 0
        for t in txns:
            ts = datetime.fromisoformat(t["ts"])
            if prev and (ts - prev).days >= int(p["quiet_days"]):
                resumed, quiet_days = ts, (ts - prev).days
            # Any outsized credit within 14 days of resuming counts, not just
            # the first transaction after the gap.
            if (resumed and (ts - resumed).days <= int(p["followup_days"])
                    and t["amount_aed"] > float(p["spike_multiplier"]) * acc["declared"]):
                alerts.append({
                    "id": _alert_id("DORMANT-SPIKE-03", acc["customer_id"]),
                    "customer_id": acc["customer_id"], "customer_name": acc["name"],
                    "rule": "DORMANT-SPIKE-03", "severity": "low",
                    "summary": (f"Account quiet for {quiet_days} days, then a credit of "
                                f"AED {t['amount_aed']:,.0f} ({t['amount_aed']/acc['declared']:.1f}× declared "
                                f"monthly turnover) on {ts.date()}."),
                    "created": f"{(ts + timedelta(days=1)).date()} 07:40:00",
                    "evidence": {"quiet_days": quiet_days, "spike_aed": t["amount_aed"]},
                })
                break
            prev = ts
    return alerts


EVALUATORS = {
    "CASH-VELOCITY-04": _cash_velocity,
    "WATCHLIST-PROX-01": _watchlist_proximity,
    "PROFILE-DEVIATION-02": _profile_deviation,
    "DORMANT-SPIKE-03": _dormant_spike,
}


def evaluate_rule(rule_id: str, parameters: dict | None = None) -> dict:
    """Evaluate one rule without changing alerts (used by the interactive simulator)."""
    if rule_id not in EVALUATORS:
        raise KeyError(rule_id)
    from src import store
    current = store.get_rule_config(rule_id)
    merged = dict(current["parameters"])
    if parameters:
        unknown = sorted(set(parameters) - set(merged))
        if unknown:
            raise ValueError(f"Unknown parameter(s): {', '.join(unknown)}")
        merged.update(parameters)
    con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        alerts = EVALUATORS[rule_id](con, merged)
        population = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        transaction_count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        con.close()
    return {"rule_id": rule_id, "parameters": merged, "matches": alerts,
            "match_count": len(alerts), "customers_scanned": population,
            "transactions_scanned": transaction_count, "persisted": False}


def run_screening(actor_role: str = "analyst") -> dict:
    """Sweep the ledger with all rules and upsert the alert queue."""
    bankdb.ensure_db()
    from src import store
    store.ensure_schema()
    configs = store.list_rule_configs()
    con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    alerts = []
    versions = {}
    for rule in configs:
        versions[rule["rule_id"]] = rule["version"]
        if rule["enabled"]:
            alerts.extend(EVALUATORS[rule["rule_id"]](con, rule["parameters"]))
    n_customers = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    n_txns = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    con.close()

    # A duplicate id would let the ON CONFLICT upsert silently merge two
    # customers' alerts into one. Fail loudly instead — this is the safety net
    # behind the collision-safe _alert_id scheme.
    ids = [a["id"] for a in alerts]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise RuntimeError(f"Alert id collision across customers: {', '.join(dupes)}")

    # Upsert, preserving triage status of alerts that already exist.
    w = sqlite3.connect(str(config.DB_PATH))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    w.execute("UPDATE alerts SET is_active=0, updated_at=?", (now,))
    for a in alerts:
        w.execute("INSERT INTO alerts "
                  "(id,customer_id,rule,severity,summary,status,created,is_active,rule_version,evidence_json,updated_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                  "severity=excluded.severity, summary=excluded.summary, is_active=1, "
                  "rule_version=excluded.rule_version, evidence_json=excluded.evidence_json, updated_at=excluded.updated_at",
                  (a["id"], a["customer_id"], a["rule"], a["severity"], a["summary"], "open",
                   a["created"], 1, versions[a["rule"]], json.dumps(a.get("evidence", {})), now))
    w.commit()
    w.close()

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: (order[a["severity"]], a["id"]))
    store.sync_cases()
    result = {"alerts": alerts, "customers_scanned": n_customers,
              "transactions_scanned": n_txns, "rules": configs, "run_at": now}
    result["run_id"] = store.record_rule_run(None, "screening",
                                              {r["rule_id"]: r["parameters"] for r in configs},
                                              {"match_count": len(alerts)}, actor_role)
    return result
