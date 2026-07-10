"""
Raqib — AI-assisted rule authoring (Phase 3, Feature 3).

The model PROPOSES deterministic rule parameters; it never persists them. A
suggestion is re-validated against the rule's real keys and types (the same
unknown-key / positive-number guard the human save path enforces), so the model
can never introduce a parameter the deterministic evaluator would reject. The
Rule Administrator still simulates and saves — "AI suggests, humans decide", and
rules.py stays LLM-free.

Two backends: oci (Responses API structured parse) and a deterministic local
heuristic used offline and in tests.
"""

from __future__ import annotations

import config
from src import oci_clients, store
from src.schemas import RuleParameterSuggestion

# Directional cues for the offline heuristic.
_TIGHTEN = ("tighten", "stricter", "sensitive", "rising", "aggressive", "more alert")
_LOOSEN = ("loosen", "relax", "reduce noise", "fewer", "false positive", "too many", "too noisy")


def _validated(current: dict, proposed: dict) -> dict:
    """Keep only known keys whose type matches and (for numbers) stay positive —
    mirrors store.update_rule_config so a suggestion can't slip a bad parameter
    past the deterministic evaluator. Invalid entries are dropped, not raised."""
    clean: dict = {}
    for key, value in (proposed or {}).items():
        if key not in current:
            continue
        expected = type(current[key])
        if expected is bool:
            if isinstance(value, bool):
                clean[key] = value
        elif expected in (int, float):
            # Coerce first, then check positivity: a fractional proposal for an
            # int param truncates to 0, which the evaluator would reject.
            if not isinstance(value, bool) and isinstance(value, (int, float)):
                coerced = expected(value)
                if coerced > 0:
                    clean[key] = coerced
    return clean


def _heuristic(current: dict, intent: str) -> tuple[dict, str]:
    """A crude, deterministic offline stand-in: nudge every numeric parameter
    ±10%. It is intentionally simple — the human simulates to see the real alert
    impact before saving, which is where correctness is actually established."""
    text = intent.lower()
    tighten = any(word in text for word in _TIGHTEN)
    loosen = any(word in text for word in _LOOSEN)
    if tighten == loosen:  # neither, or contradictory — propose nothing
        return {}, ("No clear 'tighten' or 'loosen' signal in the intent, so no candidate "
                    "was proposed.")
    factor = 0.9 if tighten else 1.1
    proposed: dict = {}
    for key, value in current.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        proposed[key] = max(1, round(value * factor)) if isinstance(value, int) else round(value * factor, 2)
    label = "tighter" if tighten else "looser"
    return proposed, (f"Crude offline heuristic ({label}, ~10%) for: {intent.strip()}. "
                      "Simulate to confirm the real alert impact before saving.")


def _oci(rule_id: str, current: dict, intent: str) -> tuple[dict, str]:
    parsed = oci_clients.platform().responses.parse(
        model=config.SAR_MODEL,
        input=(f"AML rule {rule_id} has these parameters: {current}. Analyst intent: "
               f"\"{intent}\". Propose new values for these EXISTING parameters only "
               "(same keys, positive numbers) and explain the change in one or two sentences."),
        text_format=RuleParameterSuggestion,
    )
    out: RuleParameterSuggestion = parsed.output_parsed
    return out.parameters, out.rationale


def suggest_rule_parameters(rule_id: str, intent: str) -> dict:
    """Propose deterministic parameters for one rule. Never persists; the
    returned candidate feeds the existing simulate -> save flow."""
    current = store.get_rule_config(rule_id)["parameters"]  # KeyError -> unknown rule
    if config.rule_authoring_backend() == "oci":
        proposed, rationale = _oci(rule_id, current, intent)
        backend = "oci"
    else:
        proposed, rationale = _heuristic(current, intent)
        backend = "heuristic"
    return {
        "rule_id": rule_id,
        "current_parameters": current,
        "suggested_parameters": _validated(current, proposed),
        "rationale": rationale,
        "backend": backend,
    }
