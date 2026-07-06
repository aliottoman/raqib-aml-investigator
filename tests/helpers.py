"""Small builders shared by rule and API tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src import bankdb


def build_minimal_ledger(path: Path, *, declared_turnover: int = 100_000) -> sqlite3.Connection:
    """Create the real ledger schema with one customer/account and return a connection."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(bankdb.SCHEMA)
    con.execute(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)",
        (2001, "Window Test Trading", "LLC", "AE", "Low", declared_turnover,
         "2025-01-01", "Synthetic test customer"),
    )
    con.execute(
        "INSERT INTO accounts VALUES (?,?,?,?,?,?)",
        (9001, 2001, "AE00 TEST", "AED", "2025-01-01", "Deira"),
    )
    con.commit()
    return con


def add_cash_deposit(
    con: sqlite3.Connection,
    date: str,
    *,
    branch: str,
    amount: float = 36_000,
    reference: str = "TEST-CASH",
) -> None:
    con.execute(
        "INSERT INTO transactions "
        "(account_id, ts, type, channel, branch, amount_aed, counterparty, "
        "counterparty_country, reference) VALUES (?,?,?,?,?,?,?,?,?)",
        (9001, f"{date} 10:00:00", "cash_deposit", "branch", branch, amount,
         "CASH", "AE", reference),
    )
    con.commit()

