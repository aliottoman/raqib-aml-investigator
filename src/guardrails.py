"""
Raqib — OCI Generative AI Guardrails wrappers.

Two moments in the investigation call ApplyGuardrails (inform mode — results
are surfaced, never silently swallowed):

* scan_document()  — prompt-injection + content moderation on any customer
                     document before its text reaches the model. The planted
                     note in docs/wire_memo.md is caught here.
* scan_report()    — PII detection on the outgoing SAR narrative (English,
                     matching the current PII language support).

Signing uses ~/.oci config (native OCI API), unlike the Bearer-key Responses
API — the two auth paths are deliberate and documented in the README.
"""

from __future__ import annotations

import config
from src import oci_clients


def _apply(content: str, cm=False, pi=False, pii=False) -> dict:
    import oci
    m = oci.generative_ai_inference.models
    details = m.ApplyGuardrailsDetails(
        input=m.GuardrailsTextInput(content=content[:8000]),
        guardrail_configs=m.GuardrailConfigs(
            content_moderation_config=m.ContentModerationConfiguration() if cm else None,
            prompt_injection_config=m.PromptInjectionConfiguration() if pi else None,
            personally_identifiable_information_config=(
                m.PersonallyIdentifiableInformationConfiguration() if pii else None),
        ),
        compartment_id=config.COMPARTMENT_ID,
    )
    return oci_clients.inference().apply_guardrails(details).data.results


def scan_document(text: str) -> dict:
    """Prompt-injection + content-moderation screen for an untrusted document.

    Scans paragraph-by-paragraph and keeps the worst score: an injection buried
    in one paragraph of a long business letter dilutes to ~0.0 when the whole
    document is scored as a single input (verified on this tenancy).
    """
    blocks = [b.strip() for b in text.split("\n\n") if len(b.strip()) >= 40]
    worst_pi, worst_cm, flagged = 0.0, {}, None
    for block in blocks or [text]:
        res = _apply(block, cm=True, pi=True)
        pi_score = float(getattr(res.prompt_injection, "score", 0.0) or 0.0)
        if pi_score > worst_pi:
            worst_pi, flagged = pi_score, block
        cm = getattr(res, "content_moderation", None)
        for c in getattr(cm, "categories", None) or []:
            worst_cm[c.name] = max(worst_cm.get(c.name, 0.0), c.score)
    return {"prompt_injection_score": worst_pi,
            "injection_detected": worst_pi >= 0.5,
            "flagged_excerpt": (flagged[:280] if flagged and worst_pi >= 0.5 else ""),
            "moderation": worst_cm}


def scan_report(text: str) -> list[dict]:
    """PII hits (label, text, confidence) in the SAR narrative."""
    res = _apply(text, pii=True)
    hits = getattr(res, "personally_identifiable_information", None) or []
    return [{"label": h.label, "text": h.text, "score": round(float(h.score), 3)}
            for h in hits]
