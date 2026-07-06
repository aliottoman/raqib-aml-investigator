"""
Raqib — the AML policy knowledge tool.

Retrieval has two interchangeable backends behind one ``search()`` contract:

* local  (default) — OCI embeddings + local cosine search. Policy sections are
  chunked by heading, embedded once with Cohere Embed (multilingual) on OCI,
  and searched per query. Portable, deterministic, and demo-friendly.
* managed (Track B) — an OCI Generative AI Vector Store / File Search. The same
  heading-scoped chunks are uploaded, each tagged with its ``section`` so a
  managed match maps 1:1 back to a section citation. Selected with
  ``config.USE_MANAGED_VECTOR_STORES``.

Either way ``search(query, k)`` returns ``[{"source", "section", "text"}]`` so
`tools.py` and the UI evidence cards never learn which backend served them.

Only the trusted AML policy corpus is indexed here. Customer KYC and
correspondence are untrusted case evidence and only reach the agent through
``read_case_document`` plus its Guardrails scan — they never enter this index.
"""

from __future__ import annotations

import math
import re

import config
from src import oci_clients

_index: list[dict] | None = None  # [{"source", "section", "text", "vec"}]
_managed_store_id: str | None = None  # resolved OCI vector store id (managed backend)

POLICY_SOURCES = ("aml_policy.md",)


def _chunks() -> list[dict]:
    """Split the trusted policy corpus into heading-scoped chunks.

    Customer KYC and correspondence are intentionally *not* part of this
    index.  They are untrusted case evidence and only enter the agent through
    ``read_case_document`` plus its Guardrails scan.
    """
    out = []
    for filename in POLICY_SOURCES:
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


def search(query: str, k: int = 3) -> list[dict]:
    """Top-k trusted-policy passages for a query, with section citations.

    Routes to the managed Vector Store backend when it is enabled, otherwise
    to local embeddings + cosine search. The return shape is identical.
    """
    if config.USE_MANAGED_VECTOR_STORES:
        return _managed_search(query, k)
    return _local_search(query, k)


# --------------------------------------------------------------------------- #
#  Local backend — OCI embeddings + cosine search
# --------------------------------------------------------------------------- #
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


def _local_search(query: str, k: int = 3) -> list[dict]:
    """Top-k policy passages by local cosine similarity."""
    _ensure_index()
    qvec = _embed([query], "SEARCH_QUERY")[0]
    scored = sorted(_index, key=lambda c: _cosine(qvec, c["vec"]), reverse=True)[:k]
    return [{"source": c["source"], "section": c["section"], "text": c["text"]} for c in scored]


# --------------------------------------------------------------------------- #
#  Managed backend — OCI Generative AI Vector Store / File Search
# --------------------------------------------------------------------------- #
def _resolve_store_id() -> str:
    """The vector store id to search, provisioning one on first use if needed.

    A pre-provisioned store (``RAQIB_VECTOR_STORE_ID``) is used verbatim so a
    deployment can own the store lifecycle out of band.
    """
    global _managed_store_id
    if config.VECTOR_STORE_ID:
        return config.VECTOR_STORE_ID
    if _managed_store_id is None:
        _managed_store_id = provision_managed_store()
    return _managed_store_id


def provision_managed_store() -> str:
    """Create a vector store from the trusted policy corpus and return its id.

    Each policy section is uploaded as its own file carrying ``section`` and
    ``source`` attributes, so a File Search hit reconstructs the same citation
    the local backend produces. Safe to call once per process; the result is
    cached by ``_resolve_store_id``.
    """
    client = oci_clients.platform()
    store = client.vector_stores.create(name=config.VECTOR_STORE_NAME)
    for i, chunk in enumerate(_chunks()):
        uploaded = client.files.create(
            file=(f"policy-{i:03d}-{_slug(chunk['section'])}.md", chunk["text"].encode("utf-8")),
            purpose="assistants",
        )
        client.vector_stores.files.create(
            vector_store_id=store.id,
            file_id=uploaded.id,
            attributes={"section": chunk["section"], "source": chunk["source"]},
        )
    return store.id


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "section"


def _managed_search(query: str, k: int = 3) -> list[dict]:
    """Top-k policy passages from the managed Vector Store, mapped to the
    same ``{source, section, text}`` contract as the local backend."""
    client = oci_clients.platform()
    resp = client.vector_stores.search(
        vector_store_id=_resolve_store_id(), query=query, max_num_results=k)
    out = []
    for item in getattr(resp, "data", None) or []:
        attributes = getattr(item, "attributes", None) or {}
        source = attributes.get("source") or getattr(item, "filename", None) or "aml_policy.md"
        section = attributes.get("section") or getattr(item, "filename", "") or ""
        parts = getattr(item, "content", None) or []
        text = "\n".join(
            getattr(part, "text", "") for part in parts
            if getattr(part, "type", "text") == "text"
        ).strip()
        out.append({"source": source, "section": section, "text": text})
    return out
