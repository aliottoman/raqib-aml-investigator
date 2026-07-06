"""
Raqib — the bank ledger the agent investigates.

A deterministic SQLite database (per-customer seeded RNG, stable across
rebuilds) holding a small retail-commercial portfolio at Gulf Crescent Bank
(fictional, AED). Most customers are unremarkable; three trip detection rules:

* 1017 Al Rashidi Trading FZE — THE case. 14 sub-threshold cash deposits in
  9 business days across four branches (structuring), then rapid wires out —
  one counterparty's beneficial owner is on the internal watchlist. This
  customer's rows are seeded exactly as v1 so the recorded demo tape and the
  dossier stay consistent.
* 1031 Marhaba Foodstuff Trading — dormant for ~3 months, then one large
  inbound wire (explainable: seasonal Ramadan restocking, per its profile).
* 1044 Nujoom Events LLC — running ~2.3x its declared turnover (borderline
  profile deviation; growth, not laundering).

Detection lives in src/rules.py — this module only owns data + safe access.
`execute_readonly()` is the enforcement half of the governed-SQL story: the
agent only ever *proposes* SQL; this validates a single SELECT and runs it
against a read-only connection.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta

import config

SCHEMA_VERSION = 2  # deterministic ledger seed version; never auto-destructively migrated

CUSTOMER_ID = 1017              # the flagship case subject
ALERT_ID = "RQB-2026-0347"      # the taped investigation
THRESHOLD_AED = 37_500          # internal cash-reporting threshold

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT, type TEXT, country TEXT,
    kyc_risk_rating TEXT, declared_monthly_turnover_aed INTEGER, onboarded DATE,
    profile_note TEXT
);
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
    iban TEXT, currency TEXT, opened DATE, home_branch TEXT
);
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY, account_id INTEGER REFERENCES accounts(id),
    ts DATETIME, type TEXT,          -- cash_deposit | wire_out | wire_in | pos_settlement | fee
    channel TEXT,                    -- branch | atm | online
    branch TEXT, amount_aed REAL, counterparty TEXT,
    counterparty_country TEXT, reference TEXT
);
CREATE TABLE alerts (
    id TEXT PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
    rule TEXT, severity TEXT, summary TEXT, status TEXT, created DATETIME
);
CREATE TABLE watchlist (
    entity_name TEXT, list_name TEXT, category TEXT, notes TEXT
);
"""

BRANCHES = ["Deira", "Jebel Ali", "Business Bay", "Al Barsha"]

# name, type, country, rating, declared turnover, onboarded, profile note
CUSTOMERS = [
    (1009, "Al Noor Electronics LLC", "LLC", "AE", "Low", 220_000, "2021-04-12",
     "Retail electronics chain, 3 outlets. Long-standing relationship."),
    (1013, "Bahri Marine Services", "LLC", "AE", "Low", 340_000, "2020-09-30",
     "Vessel maintenance contractor; invoices DP World and regional operators."),
    (CUSTOMER_ID, "Al Rashidi Trading FZE", "Free-zone company", "AE", "Medium", 150_000, "2025-11-03",
     "Electronics re-exporter, JAFZA. First UAE banking relationship; BVI holding layer accepted with 12-month review condition."),
    (1022, "Dr. Layla Haddad", "Individual", "AE", "Low", 85_000, "2019-02-18",
     "Consultant physician; salary + clinic income."),
    (1026, "Qamar Textiles Trading", "LLC", "AE", "Medium", 190_000, "2023-06-05",
     "Fabric importer, Deira souk; seasonal cash-heavy sales are declared."),
    (1031, "Marhaba Foodstuff Trading", "LLC", "AE", "Low", 260_000, "2018-11-21",
     "FMCG distributor. Activity is strongly seasonal around Ramadan restocking."),
    (1037, "Falcon Peak Real Estate", "LLC", "AE", "Medium", 410_000, "2022-01-10",
     "Brokerage; commission inflows from developers, escrow handled elsewhere."),
    (1044, "Nujoom Events LLC", "LLC", "AE", "Low", 120_000, "2024-03-27",
     "Corporate events agency; fast-growing client roster in 2026."),
    (1052, "Atlas Auto Spare Parts", "Sole establishment", "AE", "Low", 95_000, "2020-07-08",
     "Spare-parts trader, Sharjah corridor; small steady supplier wires to CN."),
]


def _seed_flagship(rows: list, rng: random.Random) -> None:
    """Customer 1017 — byte-identical to v1 (the tape depends on these rows)."""
    day = datetime(2025, 12, 1, 10, 0)
    while day < datetime(2026, 5, 25):
        if day.weekday() < 5 and rng.random() < 0.45:
            kind = rng.choice(["pos_settlement", "wire_out", "wire_in", "fee"])
            amount = {
                "pos_settlement": rng.uniform(4_000, 22_000),
                "wire_out": -rng.uniform(8_000, 60_000),
                "wire_in": rng.uniform(15_000, 70_000),
                "fee": -rng.uniform(35, 420),
            }[kind]
            counterparty = {
                "pos_settlement": ("Network International POS", "AE"),
                "wire_out": (rng.choice(["Shenzhen Electronics Wholesale Co", "Hamriyah Logistics LLC",
                                         "TechSource Distribution DMCC"]), rng.choice(["CN", "AE", "AE"])),
                "wire_in": (rng.choice(["Al Noor Electronics LLC", "Bahri Trading Co", "Gulf Gadget Mart"]), "AE"),
                "fee": ("Gulf Crescent Bank", "AE"),
            }[kind]
            rows.append((5001, day.replace(hour=rng.randint(9, 16)), kind,
                         "online" if kind != "pos_settlement" else "branch",
                         "Jebel Ali", round(amount, 2), counterparty[0], counterparty[1],
                         f"INV-{rng.randint(10_000, 99_999)}"))
        day += timedelta(days=1)

    deposit_days = ["2026-06-08", "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-10",
                    "2026-06-11", "2026-06-12", "2026-06-12", "2026-06-15", "2026-06-15",
                    "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-18"]
    for i, d in enumerate(deposit_days):
        amount = rng.uniform(33_500, 36_900)
        rows.append((5001, datetime.fromisoformat(d).replace(hour=rng.randint(9, 17), minute=rng.randint(0, 59)),
                     "cash_deposit", "branch", BRANCHES[i % 4], round(amount, 2),
                     "CASH", "AE", f"CD-{2026_0000 + i}"))

    wires = [
        ("2026-06-12", 128_000, "Meridian Global Components Ltd", "HK", "PO-8841 advance"),
        ("2026-06-16", 96_500, "Aurora Trade House LLC", "AE", "PO-8867 settlement"),
        ("2026-06-19", 158_200, "Meridian Global Components Ltd", "HK", "PO-8871 balance"),
        ("2026-06-19", 74_300, "Aurora Trade House LLC", "AE", "consulting services"),
    ]
    for d, amount, cp, cc, ref in wires:
        rows.append((5001, datetime.fromisoformat(d).replace(hour=rng.randint(10, 15)),
                     "wire_out", "online", "Jebel Ali", -float(amount), cp, cc, ref))


def _seed_ordinary(rows: list, account_id: int, customer: tuple, rng: random.Random) -> None:
    """Plausible commercial noise scaled to the declared turnover."""
    cid, name, ctype, *_ = customer
    turnover = customer[5]
    day = datetime(2026, 1, 2, 10, 0)
    dormant = cid == 1031  # Marhaba: quiet Feb–Apr, one big May restock wire
    boost = 2.6 if cid == 1044 else 1.0  # Nujoom: growing well past its declared profile
    scale = turnover * boost
    while day < datetime(2026, 6, 28):
        quiet = dormant and datetime(2026, 2, 1) <= day < datetime(2026, 5, 4)
        if day.weekday() < 5 and not quiet and rng.random() < 0.5:
            kind = rng.choice(["pos_settlement", "wire_in", "wire_out", "fee", "cash_deposit"])
            # Credits average ≈ 1× declared turnover for a normal customer.
            # Cash stays small and well below the CTR band — cash-heavy
            # patterns belong to the flagship case only.
            amount = {
                "pos_settlement": rng.uniform(0.14, 0.21) * scale,
                "wire_in": rng.uniform(0.11, 0.35) * scale,
                "wire_out": -rng.uniform(0.10, 0.30) * scale,
                "fee": -rng.uniform(35, 380),
                "cash_deposit": rng.uniform(2_000, 16_000),
            }[kind]
            cp = {
                "pos_settlement": ("Network International POS", "AE"),
                "wire_in": (rng.choice(["Emaar Facilities", "GEMS Corporate", "Etisalat Business",
                                        "Majid Al Futtaim Retail"]), "AE"),
                "wire_out": (rng.choice(["Guangzhou Trade Partners", "Dubai Customs", "Staff Payroll WPS",
                                         "DEWA", "Landlord — JLT Tower"]), rng.choice(["CN", "AE", "AE", "AE", "AE"])),
                "fee": ("Gulf Crescent Bank", "AE"),
                "cash_deposit": ("CASH", "AE"),
            }[kind]
            rows.append((account_id, day.replace(hour=rng.randint(9, 17)), kind,
                         "branch" if kind == "cash_deposit" else "online",
                         rng.choice(BRANCHES), round(amount, 2), cp[0], cp[1],
                         f"REF-{rng.randint(10_000, 99_999)}"))
        day += timedelta(days=1)
    if dormant:  # the explainable spike: one seasonal restocking inflow
        rows.append((account_id, datetime(2026, 5, 6, 11, 20), "wire_in", "online", "Deira",
                     388_000.0, "Marhaba Trading — HQ Treasury", "AE", "Ramadan season restock float"))
    if cid == 1044:  # Nujoom: two big event retainers pin May ≥ 2× declared
        rows.append((account_id, datetime(2026, 5, 7, 10, 5), "wire_in", "online", "Business Bay",
                     118_000.0, "GEMS Corporate", "AE", "annual gala — retainer"))
        rows.append((account_id, datetime(2026, 5, 19, 14, 30), "wire_in", "online", "Business Bay",
                     96_000.0, "Etisalat Business", "AE", "product launch — production"))


def build(path=None) -> None:
    """Create and seed the database from scratch (idempotent, deterministic)."""
    path = str(path or config.DB_PATH)
    con = sqlite3.connect(path)
    con.executescript("DROP TABLE IF EXISTS customers; DROP TABLE IF EXISTS accounts;"
                      "DROP TABLE IF EXISTS transactions; DROP TABLE IF EXISTS alerts;"
                      "DROP TABLE IF EXISTS watchlist;")
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    rows = []
    for i, cust in enumerate(CUSTOMERS):
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", cust)
        account_id = 5001 if cust[0] == CUSTOMER_ID else 5100 + i
        con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?)",
                    (account_id, cust[0], f"AE07 0331 2345 67{cust[0]} 456", "AED",
                     cust[6], "Jebel Ali" if cust[0] == CUSTOMER_ID else BRANCHES[i % 4]))
        if cust[0] == CUSTOMER_ID:
            _seed_flagship(rows, random.Random(7741))  # v1 seed — do not change
        else:
            _seed_ordinary(rows, account_id, cust, random.Random(cust[0]))

    con.executemany(
        "INSERT INTO transactions (account_id, ts, type, channel, branch, amount_aed,"
        " counterparty, counterparty_country, reference) VALUES (?,?,?,?,?,?,?,?,?)", rows)

    con.executemany("INSERT INTO watchlist VALUES (?,?,?,?)", [
        ("Viktor Baranov", "Internal Watchlist — Secondary Sanctions Exposure", "UBO",
         "Beneficial owner of Meridian Global Components Ltd (HK). Affiliate of a "
         "designated entity; enhanced due diligence mandatory, see policy §6.1."),
        ("Caspian Freight Alliance", "Internal Watchlist — Shell Indicators", "Entity",
         "Suspected layering vehicle; multiple correspondent-bank RFIs in 2025."),
    ])
    con.commit()
    con.close()


def ensure_db() -> None:
    """Build the demo ledger once, without destroying existing case state.

    Earlier versions rebuilt the whole file whenever ``user_version``
    changed.  The application now stores investigation history in the same
    SQLite file, so migrations must be additive.  A database containing the
    five ledger tables is therefore kept as-is; an incomplete database is
    surfaced clearly rather than silently erased.
    """
    if not config.DB_PATH.exists():
        build()
        return
    con = sqlite3.connect(str(config.DB_PATH))
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        con.close()
    required = {"customers", "accounts", "transactions", "alerts", "watchlist"}
    if required.issubset(tables):
        return
    if not tables:
        build()
        return
    missing = ", ".join(sorted(required - tables))
    raise RuntimeError(f"Raqib database is incomplete; missing ledger table(s): {missing}")


def execute_readonly(sql: str, max_rows: int = 50) -> dict:
    """Run ONE validated SELECT against a read-only connection.

    This mirrors the DBTools-MCP governance split: the model proposes SQL,
    the platform (here: this function, after analyst approval) executes it.
    """
    ensure_db()
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return {"error": "Only a single statement is allowed."}
    if not stripped.lower().startswith(("select", "with")):
        return {"error": "Only SELECT queries are allowed on the bank ledger."}

    con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(stripped)
        rows = [dict(r) for r in cur.fetchmany(max_rows)]
        return {"columns": [c[0] for c in cur.description or []], "rows": rows,
                "row_count": len(rows), "truncated": len(rows) == max_rows}
    except sqlite3.Error as e:
        return {"error": f"SQL error: {e}"}
    finally:
        con.close()


def get_alert(alert_id: str = ALERT_ID) -> dict:
    """One alert + its customer snapshot — the seed of an investigation."""
    ensure_db()
    con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if row is None:
        con.close()
        raise KeyError(f"No such alert: {alert_id}")
    alert = dict(row)
    customer = dict(con.execute("SELECT * FROM customers WHERE id=?", (alert["customer_id"],)).fetchone())
    con.close()
    return {"alert": alert, "customer": customer, "threshold_aed": THRESHOLD_AED}


SCHEMA_DOC = """Tables available (SQLite dialect, read-only):
customers(id, name, type, country, kyc_risk_rating, declared_monthly_turnover_aed, onboarded, profile_note)
accounts(id, customer_id, iban, currency, opened, home_branch)
transactions(id, account_id, ts, type[cash_deposit|wire_out|wire_in|pos_settlement|fee],
             channel[branch|atm|online], branch, amount_aed, counterparty,
             counterparty_country, reference)
alerts(id, customer_id, rule, severity, summary, status, created)
watchlist(entity_name, list_name, category, notes)"""
