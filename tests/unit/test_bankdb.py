from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import config
from src import bankdb


pytestmark = pytest.mark.unit


def test_seed_is_deterministic_and_contains_flagship_facts(tmp_path: Path):
    first = tmp_path / "first.sqlite3"
    second = tmp_path / "second.sqlite3"
    bankdb.build(first)
    bankdb.build(second)

    query = (
        "SELECT account_id, ts, type, branch, amount_aed, counterparty, reference "
        "FROM transactions ORDER BY id"
    )
    with closing(sqlite3.connect(first)) as a, closing(sqlite3.connect(second)) as b:
        assert a.execute(query).fetchall() == b.execute(query).fetchall()
        assert a.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 19
        assert a.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1079

        count, total, branches, first_day, last_day = a.execute(
            "SELECT COUNT(*), ROUND(SUM(amount_aed), 2), COUNT(DISTINCT branch), "
            "MIN(date(ts)), MAX(date(ts)) FROM transactions "
            "WHERE account_id=5001 AND type='cash_deposit' AND ts >= '2026-06-01'"
        ).fetchone()
    assert (count, total, branches) == (14, 484_829.01, 4)
    assert (first_day, last_day) == ("2026-06-08", "2026-06-18")


@pytest.mark.parametrize(
    "sql, message",
    [
        ("DELETE FROM customers", "Only SELECT"),
        ("UPDATE customers SET name='changed'", "Only SELECT"),
        ("SELECT 1; SELECT 2", "single statement"),
        ("PRAGMA user_version", "Only SELECT"),
    ],
)
def test_execute_readonly_rejects_non_read_queries(sql: str, message: str):
    result = bankdb.execute_readonly(sql)
    assert message.lower() in result["error"].lower()


def test_execute_readonly_uses_database_read_only_mode():
    result = bankdb.execute_readonly(
        "WITH changed AS (SELECT 1) DELETE FROM customers WHERE id=1017"
    )
    assert "error" in result
    remaining = bankdb.execute_readonly("SELECT COUNT(*) AS n FROM customers WHERE id=1017")
    assert remaining["rows"] == [{"n": 1}]


def test_execute_readonly_supports_ctes_and_caps_rows():
    cte = bankdb.execute_readonly("WITH x(v) AS (SELECT 42) SELECT v FROM x")
    assert cte == {
        "columns": ["v"],
        "rows": [{"v": 42}],
        "row_count": 1,
        "truncated": False,
    }

    limited = bankdb.execute_readonly("SELECT id FROM transactions ORDER BY id", max_rows=7)
    assert limited["row_count"] == 7
    assert limited["truncated"] is True


def test_ensure_db_does_not_replace_current_schema(monkeypatch: pytest.MonkeyPatch):
    before = config.DB_PATH.stat().st_mtime_ns
    bankdb.ensure_db()
    assert config.DB_PATH.stat().st_mtime_ns == before


def test_get_alert_is_parameterized_and_unknown_ids_fail():
    from src import rules

    rules.run_screening()
    case = bankdb.get_alert(bankdb.ALERT_ID)
    assert case["alert"]["id"] == bankdb.ALERT_ID
    assert case["customer"]["id"] == bankdb.CUSTOMER_ID
    assert case["threshold_aed"] == bankdb.THRESHOLD_AED

    with pytest.raises(KeyError):
        bankdb.get_alert("' OR 1=1 --")
