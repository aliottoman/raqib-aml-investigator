from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import SARReport, ev


pytestmark = pytest.mark.unit


def test_recorded_sar_conforms_to_schema(golden_sar):
    parsed = SARReport.model_validate(golden_sar)
    assert parsed.case_id == "RQB-2026-0347"
    assert parsed.risk_score == 85
    assert parsed.sar_filing_required is True
    assert parsed.counterparties[0].watchlist_hit is True
    assert parsed.model_dump(mode="json") == golden_sar


@pytest.mark.parametrize("score", [-1, 101])
def test_risk_score_is_bounded(score: int, golden_sar):
    golden_sar["risk_score"] = score
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


def test_risk_level_is_an_enumeration(golden_sar):
    golden_sar["risk_level"] = "severe"
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


def test_required_numeric_fields_do_not_accept_missing_values(golden_sar):
    del golden_sar["total_amount_aed"]
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf")])
def test_report_totals_must_be_finite_and_nonnegative(amount: float, golden_sar):
    golden_sar["total_amount_aed"] = amount
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


@pytest.mark.parametrize("amount", [-0.01, float("nan"), float("inf")])
def test_counterparty_totals_must_be_finite_and_nonnegative(amount: float, golden_sar):
    golden_sar["counterparties"][0]["total_aed"] = amount
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


def test_risk_score_rejects_boolean_coercion(golden_sar):
    golden_sar["risk_score"] = True
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


@pytest.mark.parametrize("field", ["case_id", "subject", "narrative", "narrative_ar"])
def test_required_report_text_cannot_be_blank(field: str, golden_sar):
    golden_sar[field] = "   "
    with pytest.raises(ValidationError):
        SARReport.model_validate(golden_sar)


def test_event_factory_has_a_small_stable_contract():
    assert ev("approval_result", id="call-7", approved=True) == {
        "type": "approval_result",
        "id": "call-7",
        "approved": True,
    }
