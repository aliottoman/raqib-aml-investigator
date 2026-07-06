"""Deterministic tests for the eval harness itself (no network).

The scorers and summarizers are the thing every published number depends on,
so they get their own coverage — synthetic runs in, known verdicts out.
"""

from __future__ import annotations

import pytest

from evals import redteam
from evals.cases import GoldenCase
from evals.redteam import Attack, AttackResult
from evals.runner import RunResult
from evals.scoring import score, summarize

pytestmark = pytest.mark.eval


def _run(sar):
    r = RunResult(alert_id="RQB-TEST", ok=True)
    r.sar = sar
    return r


def _good_sar():
    return {
        "case_id": "RQB-TEST", "subject": "Acme", "risk_level": "high", "risk_score": 80,
        "pattern_type": "Structuring", "period": "2026-06-01 to 2026-06-10",
        "total_amount_aed": 100.0, "counterparties": [], "policy_sections_engaged": ["§4.2"],
        "key_findings": ["x"], "narrative": "n", "narrative_ar": "ن",
        "recommended_actions": ["a"], "sar_filing_required": True,
    }


def test_score_rewards_correct_verdict_and_policy(monkeypatch):
    monkeypatch.setattr("evals.scoring._customer_id", lambda _aid: 9999)
    monkeypatch.setattr("evals.scoring._entity_totals", lambda _cid: [])
    case = GoldenCase("RQB-TEST", "t", expect_sar=True, expect_risk=("high",),
                      expect_watchlist_hit=False, expect_policy=("§4.2",))
    checks = score(case, _run(_good_sar()))
    passed, total = summarize(checks)
    assert passed == total  # every check green on a well-formed matching SAR


def test_score_flags_wrong_verdict(monkeypatch):
    monkeypatch.setattr("evals.scoring._customer_id", lambda _aid: 9999)
    monkeypatch.setattr("evals.scoring._entity_totals", lambda _cid: [])
    case = GoldenCase("RQB-TEST", "t", expect_sar=False, expect_risk=("low",),
                      expect_watchlist_hit=False)
    checks = score(case, _run(_good_sar()))
    names = {c.name: c.passed for c in checks}
    assert names["verdict_filing"] is False
    assert names["verdict_risk"] is False


def test_score_catches_hallucinated_counterparty(monkeypatch):
    monkeypatch.setattr("evals.scoring._customer_id", lambda _aid: 9999)
    # Ledger has only Meridian (500). A SAR that invents "Ghost Co" or inflates
    # Meridian to 999 must fail grounding.
    monkeypatch.setattr("evals.scoring._entity_totals",
                        lambda _cid: [{"counterparty": "Meridian Ltd", "total": 500.0}])
    case = GoldenCase("RQB-TEST", "t", expect_sar=True, expect_risk=("high",),
                      expect_watchlist_hit=False)

    inflated = _good_sar()
    inflated["counterparties"] = [{"name": "Meridian Ltd", "country": "HK",
                                   "total_aed": 999.0, "watchlist_hit": False}]
    bounded = next(c for c in score(case, _run(inflated)) if c.name == "amounts_bounded")
    assert bounded.passed is False  # 999 > 500 → inflated

    fabricated = _good_sar()
    fabricated["counterparties"] = [{"name": "Ghost Trading Co", "country": "XX",
                                     "total_aed": 100.0, "watchlist_hit": False}]
    real = next(c for c in score(case, _run(fabricated)) if c.name == "counterparties_real")
    assert real.passed is False  # entity not in the ledger

    # A windowed subset of a real entity's flow must PASS.
    windowed = _good_sar()
    windowed["counterparties"] = [{"name": "Meridian Ltd", "country": "HK",
                                   "total_aed": 300.0, "watchlist_hit": False}]
    checks = {c.name: c.passed for c in score(case, _run(windowed))}
    assert checks["counterparties_real"] and checks["amounts_bounded"]


def test_invalid_sar_short_circuits(monkeypatch):
    case = GoldenCase("RQB-TEST", "t", expect_sar=True, expect_risk=("high",),
                      expect_watchlist_hit=False)
    checks = score(case, _run({}))  # empty SAR fails schema
    assert checks[0].name == "schema_valid" and not checks[0].passed
    assert len(checks) == 1  # nothing else scored without a valid SAR


def test_redteam_summarize_counts_families_and_false_positives():
    results = [
        AttackResult(Attack("d1", "direct", True, "x"), 1.0, True),
        AttackResult(Attack("d2", "direct", True, "x"), 0.0, False),
        AttackResult(Attack("b1", "benign_control", False, "x"), 1.0, True),  # false positive
        AttackResult(Attack("e1", "encoded", False, "x"), 0.0, False),        # tracked limitation
    ]
    s = redteam.summarize(results)
    assert s["families"]["direct"] == {"caught": 1, "total": 2}
    assert s["catch_rate"] == pytest.approx(0.5)
    assert s["benign_flagged"] == 1 and s["benign_total"] == 1
    assert "e1" in s["known_limitations"]


def test_corpus_is_well_formed():
    assert len(redteam.CORPUS) >= 20
    assert {a.id for a in redteam.CORPUS}.__len__() == len(redteam.CORPUS)  # unique ids
    assert any(a.family == "arabic" for a in redteam.CORPUS)
    assert any(a.family == "benign_control" for a in redteam.CORPUS)
