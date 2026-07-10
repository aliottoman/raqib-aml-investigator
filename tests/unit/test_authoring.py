from __future__ import annotations

from types import SimpleNamespace

import pytest

import config
from src import authoring, oci_clients, store


pytestmark = pytest.mark.unit


def test_heuristic_tighten_keeps_only_known_positive_keys():
    result = authoring.suggest_rule_parameters("CASH-VELOCITY-04", "tighten for rising smurfing")
    assert result["backend"] == "heuristic"
    current = result["current_parameters"]
    suggested = result["suggested_parameters"]
    assert suggested and set(suggested).issubset(current)          # only existing keys
    assert all(isinstance(v, (int, float)) and v > 0 for v in suggested.values())
    # Nothing is persisted: the live configuration is unchanged.
    assert store.get_rule_config("CASH-VELOCITY-04")["parameters"] == current


def test_no_directional_signal_proposes_nothing():
    result = authoring.suggest_rule_parameters("CASH-VELOCITY-04", "make it better somehow")
    assert result["suggested_parameters"] == {}
    assert "no candidate" in result["rationale"].lower()


def test_unknown_rule_raises_keyerror():
    with pytest.raises(KeyError):
        authoring.suggest_rule_parameters("NO-SUCH-RULE", "tighten")


def test_oci_backend_drops_unsafe_suggested_parameters(monkeypatch: pytest.MonkeyPatch):
    # A live model proposing an unknown key, a non-positive value, and a
    # fractional value for an int param (which truncates to 0): all are dropped,
    # so the deterministic evaluator can never see a bad parameter.
    parsed = SimpleNamespace(output_parsed=SimpleNamespace(
        parameters={"minimum_deposits": 5, "threshold_aed": -1, "minimum_branches": 0.4, "evil_key": 9},
        rationale="try tighter"))

    class _Responses:
        def parse(self, **_kwargs):
            return parsed

    monkeypatch.setattr(config, "API_KEY", "k")
    monkeypatch.setattr(config, "PROJECT_OCID", "p")
    monkeypatch.setattr(config, "RULE_AUTHORING_ENABLED", True)
    monkeypatch.setattr(oci_clients, "platform", lambda: SimpleNamespace(responses=_Responses()))

    result = authoring.suggest_rule_parameters("CASH-VELOCITY-04", "tighten")
    assert result["backend"] == "oci"
    assert result["suggested_parameters"] == {"minimum_deposits": 5}
