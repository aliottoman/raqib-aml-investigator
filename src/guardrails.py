"""
Raqib — content safeguards over untrusted input and generated output.

Two moments in the investigation are screened (inform mode — results are
surfaced, never silently swallowed):

* scan_document()  — prompt-injection + content moderation on any customer
                     document before its text reaches the model.
* scan_report()    — PII detection on the outgoing SAR narrative (English,
                     matching the current PII language support).

Prompt-injection screening is **two layers, defence in depth**:

  1a. OCI Generative AI Guardrails (`ApplyGuardrails`) — a managed ML detector.
      Strong on overt injections, but our red-team (see EVALS.md) measured it
      missing whole families: encoded/obfuscated blobs, delimiter-escape,
      injections buried in business prose, and Arabic-language payloads.
  1b. A local, deterministic lexicon detector (this module) that owns exactly
      those known-shape families and, crucially, needs no credentials — so it
      runs in CI and offline. It de-obfuscates base64/ROT13 before matching, so
      an encoded payload is scored on its decoded intent.

scan_document reports ``max(oci, heuristic)`` per block plus which layer caught
it. This is a rules complement to a managed model, not a claim to have solved
prompt injection; a novel attack shape still leans on layer 1a and on the
agent's own instruction to distrust document content (layer 2).

Signing for the OCI calls uses ~/.oci config (native OCI API), unlike the
Bearer-key Responses API — the two auth paths are deliberate.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata

import config
from src import oci_clients


# --------------------------------------------------------------------------- #
#  Layer 1b — local heuristic prompt-injection detector (no credentials)
# --------------------------------------------------------------------------- #
_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x202A, 0x202B, 0x202D, 0x202E}

# (label, score, patterns). Scores sit at/above the 0.5 catch threshold because
# each pattern is a specific, high-confidence injection shape — not a generic
# suspicious word. Ordered high-to-low; the worst match wins.
_HEURISTIC_RULES: list[tuple[str, float, list[re.Pattern]]] = [
    ("imperative", 0.9, [re.compile(p, re.I) for p in (
        r"ignore\s+(all\s+|any\s+)?(previous|prior|earlier|above|the\s+above)\s+"
        r"(instruction|instructions|prompt|prompts|steps|context)",
        r"disregard\s+(the\s+|all\s+|any\s+)?(previous|prior|investigation|procedure|"
        r"instruction|instructions|policy|guidance|above)",
        r"do\s+not\s+(file|submit|raise|create|generate|produce)\s+(a\s+|any\s+)?"
        r"(sar|suspicious[\s-]activity[\s-]report|report)",
        r"\bdo\s+not\s+escalate\b",
        r"\bend\s+the\s+investigation\b",
        r"(classify|mark|set|rate|record|treat)\b.{0,40}?\b(low[\s-]?risk|as\s+low|"
        r"cleared|innocent|no\s+further\s+action)",
        r"sar_filing_required\s*(=|to|:)\s*(false|no|0)",
        r"risk[_\s]?score\s*(=|to|as|:)\s*\d",
        r"\bno\s+suspicious\s+activity\b",
        r"(system|compliance|mlro)\s+override",
        r"\bdeveloper\s+mode\b",
        r"\byou\s+are\s+now\b",
        r"pretend\s+(that\s+)?(the\s+)?(previous\s+|prior\s+)?(system\s+)?(prompt|instruction)",
        r"exempt\s+from\s+(watchlist\s+)?(screening|monitoring|review)",
        r"suppress\s+(all\s+|the\s+)?(findings|results|output|the\s+above)",
        r"internal\s+ai\s+note",
        r"for\s+(automated|ai)\s+(reviewers?|tools?|review\s+tools?)\s+only",
        r"trusted\s+instruction",
        r"recommend\s+no\s+further\s+action",
        r"supersede(s)?\s+all\s+(prior|previous)",
        r"approve\s+every\s+(transaction|payment|case)",
        r"the\s+customer\s+is\s+innocent",
    )]),
    ("sql", 0.88, [re.compile(p, re.I) for p in (
        r"\bdrop\s+table\b", r"\bdelete\s+from\b", r";\s*--",
        r"'\s*or\s*'?\s*1\s*'?\s*=\s*'?\s*1", r"\bunion\s+select\b",
    )]),
    ("exfil", 0.85, [re.compile(p, re.I) for p in (
        r"print\s+your\s+(full\s+|entire\s+)?(system\s+)?(prompt|instructions)",
        r"reveal\s+your\s+(system\s+)?(prompt|instructions|configuration)",
        r"your\s+(internal\s+)?(configuration|config|system\s+prompt)",
        r"\bapi[\s_-]?keys?\b", r"connection\s+strings?",
        r"instructions\s+you\s+were\s+given",
    )]),
    ("delimiter", 0.82, [re.compile(p, re.I) for p in (
        r"new\s+system\s+message", r"ignore\s+everything\s+above",
        r"\bcase\s+is\s+(now\s+)?closed\b", r"no\s+sar\s+is\s+required",
        r"respond\s+only\s+with",
    )]),
    # Arabic injection lexicon (the OCI text detector caught 0/2). These phrases
    # are unambiguous injection intent and do not occur in benign KYC/trade prose.
    ("arabic", 0.85, [re.compile(p) for p in (
        r"تجاهل", r"منخفضة المخاطر", r"لا ترفع", r"لا تذكر",
        r"أغلق التحقيق", r"صنّف", r"تمت الموافقة",
    )]),
]


def _decode_obfuscated(text: str) -> str:
    """Return decoded/de-obfuscated views of the text so an encoded payload is
    matched on its intent. base64 tokens are decoded; a ROT13 view is always
    appended (cheap, and only meaningful when the payload was ROT13)."""
    extras: list[str] = []
    for token in re.findall(r"[A-Za-z0-9+/]{16,}={0,2}", text):
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=False)
        except (binascii.Error, ValueError):
            continue
        decoded = raw.decode("utf-8", "ignore")
        if decoded and sum(c.isprintable() for c in decoded) / len(decoded) > 0.8:
            extras.append(decoded)
    try:
        extras.append(codecs.encode(text, "rot13"))
    except Exception:  # pragma: no cover - rot13 is total on str
        pass
    return " ".join(extras)


def _match(hay: str) -> tuple[float, str]:
    best, label = 0.0, ""
    for name, score, patterns in _HEURISTIC_RULES:
        if score <= best:
            continue
        if any(p.search(hay) for p in patterns):
            best, label = score, name
    return best, label


def heuristic_injection_score(text: str) -> tuple[float, str]:
    """Deterministic prompt-injection score in [0, 1] for one text block, with a
    short signal label. Credential-free — this is layer 1b."""
    # Strip zero-width / bidi control chars before matching: an attacker can wedge
    # them between letters to slip a pattern ("ig<zwsp>nore"), and removing them is
    # harmless to benign text — so this defeats the evasion without risking a
    # false positive on a document that merely carries a stray zero-width char.
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = "".join(c for c in normalized if ord(c) not in _ZERO_WIDTH)
    score, label = _match(cleaned)
    if score < 0.5:
        decoded = _decode_obfuscated(cleaned)
        if decoded:
            decoded_score, _ = _match(unicodedata.normalize("NFKC", decoded))
            if decoded_score >= 0.5:
                # An injection that only appears after decoding is an encoded attack.
                score, label = max(decoded_score, 0.9), "encoded"
    return score, label


def _blocks(text: str) -> list[str]:
    """Paragraph-scoped blocks. An injection buried in one paragraph of a long
    letter dilutes to ~0 when the whole document is scored at once."""
    blocks = [b.strip() for b in text.split("\n\n") if len(b.strip()) >= 40]
    return blocks or [text]


def heuristic_scan_document(text: str) -> dict:
    """Layer-1b-only document scan — same shape as scan_document, no OCI call."""
    worst_pi, flagged, detector = 0.0, None, "none"
    for block in _blocks(text):
        score, label = heuristic_injection_score(block)
        if score > worst_pi:
            worst_pi, flagged, detector = score, block, f"heuristic:{label}"
    detected = worst_pi >= 0.5
    return {"prompt_injection_score": round(worst_pi, 3),
            "injection_detected": detected,
            "flagged_excerpt": (flagged[:280] if flagged and detected else ""),
            "moderation": {},
            "detector": detector if detected else "none"}


# --------------------------------------------------------------------------- #
#  Layer 1a — OCI Generative AI Guardrails (managed)
# --------------------------------------------------------------------------- #
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

    Combines both layers per paragraph and keeps the worst: for each block the
    reported score is ``max(OCI ApplyGuardrails, local heuristic)`` and the
    ``detector`` field records which layer owned the worst block.
    """
    worst_pi, worst_cm, flagged, detector = 0.0, {}, None, "none"
    for block in _blocks(text):
        res = _apply(block, cm=True, pi=True)
        oci_pi = float(getattr(res.prompt_injection, "score", 0.0) or 0.0)
        heuristic_pi, signal = heuristic_injection_score(block)
        block_pi = max(oci_pi, heuristic_pi)
        if block_pi > worst_pi:
            worst_pi = block_pi
            flagged = block
            detector = "oci" if oci_pi >= heuristic_pi else f"heuristic:{signal}"
        cm = getattr(res, "content_moderation", None)
        for c in getattr(cm, "categories", None) or []:
            worst_cm[c.name] = max(worst_cm.get(c.name, 0.0), c.score)
    detected = worst_pi >= 0.5
    return {"prompt_injection_score": worst_pi,
            "injection_detected": detected,
            "flagged_excerpt": (flagged[:280] if flagged and detected else ""),
            "moderation": worst_cm,
            "detector": detector if detected else "none"}


def scan_report(text: str) -> list[dict]:
    """PII hits (label, text, confidence) in the SAR narrative."""
    res = _apply(text, pii=True)
    hits = getattr(res, "personally_identifiable_information", None) or []
    return [{"label": h.label, "text": h.text, "score": round(float(h.score), 3)}
            for h in hits]
