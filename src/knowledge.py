"""
Raqib — the AML policy knowledge tool.

Vector Stores / File Search are not yet enabled in this region (404, verified
July 2026), so retrieval runs on OCI embeddings + local cosine search:
policy sections are chunked by heading, embedded once with Cohere Embed
(multilingual) on OCI, and searched per query. Swap to the managed Vector
Stores API when config.USE_MANAGED_VECTOR_STORES flips.

Chunks stay small (one policy section each) so a citation maps 1:1 to a
section heading — the UI shows those as evidence cards.
"""

from __future__ import annotations

import math
import re

import config
from src import oci_clients

_index: list[dict] | None = None  # [{"source", "section", "text", "vec"}]


def _chunks() -> list[dict]:
    """Split the trusted policy corpus into heading-scoped chunks.

    Customer KYC and correspondence are intentionally *not* part of this
    index.  They are untrusted case evidence and only enter the agent through
    ``read_case_document`` plus its Guardrails scan.
    """
    out = []
    for filename in ("aml_policy.md",):
        path = config.DOCS_DIR / filename
        if not path.is_file():
            continue
        text = path.read_text()
        # split on ## headings; keep the heading with its body
        parts = re.split(r"(?m)^##\s+", text)
        header, sections = parts[0], parts[1:]
        if not sections:  # un-sectioned doc -> one chunk
            out.append({"source": path.name, "section": path.stem, "text": text.strip()})
        for s in sections:
            title, _, body = s.partition("\n")
            out.append({"source": path.name, "section": title.strip(),
                        "text": f"{title.strip()}\n{body.strip()}"})
    return out


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    import oci
    m = oci.generative_ai_inference.models
    details = m.EmbedTextDetails(
        inputs=texts,
        serving_mode=m.OnDemandServingMode(model_id=config.EMBED_MODEL),
        compartment_id=config.COMPARTMENT_ID,
        input_type=input_type,
    )
    return oci_clients.inference().embed_text(details).data.embeddings


def _ensure_index():
    global _index
    if _index is None:
        chunks = _chunks()
        vecs = _embed([c["text"] for c in chunks], "SEARCH_DOCUMENT")
        _index = [{**c, "vec": v} for c, v in zip(chunks, vecs)]


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def search(query: str, k: int = 3) -> list[dict]:
    """Top-k policy passages for a query, with section citations."""
    _ensure_index()
    qvec = _embed([query], "SEARCH_QUERY")[0]
    scored = sorted(_index, key=lambda c: _cosine(qvec, c["vec"]), reverse=True)[:k]
    return [{"source": c["source"], "section": c["section"],
             "text": c["text"], } for c in scored]
