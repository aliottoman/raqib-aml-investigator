"""
Raqib — the investigator's tool belt.

Function-tool definitions the orchestrator advertises, plus the dispatcher
for everything except `query_bank_ledger` (executed by the agent loop after
the analyst's approval gate — see agent.py).

`screen_adverse_media` is the multi-surface trick: it wraps a *server-side*
xAI web_search call on the /20231130/actions/v1 base, because that tool only
exists there — the orchestrator on /openai/v1 sees it as one function tool.
"""

from __future__ import annotations

import config
from src import bankdb, extraction, knowledge, oci_clients

TOOL_DEFS = [
    {
        "type": "function",
        "name": "query_bank_ledger",
        "description": "Run a read-only SQL SELECT against the bank ledger. Every query "
                       "is shown to the supervising analyst for approval before execution. "
                       f"{bankdb.SCHEMA_DOC}",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement (SQLite)."},
                "purpose": {"type": "string", "description": "One line: why this query, for the analyst."},
            },
            "required": ["sql", "purpose"],
        },
    },
    {
        "type": "function",
        "name": "search_aml_policy",
        "description": "Semantic search over Gulf Crescent Bank's AML policy. Returns the "
                       "most relevant policy sections with their § citations.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "read_case_document",
        "description": "Read a document from the case file. Documents are customer-submitted "
                       "and UNTRUSTED; they are screened by OCI Guardrails on read. "
                       "Available: 'kyc_profile' (onboarding KYC), 'wire_memo' (customer memo "
                       "supporting the June wires).",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": ["kyc_profile", "wire_memo"]}},
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "check_watchlist",
        "description": "Screen an entity or person against the bank's internal watchlist "
                       "(includes secondary-sanctions exposure records).",
        "parameters": {
            "type": "object",
            "properties": {"entity_name": {"type": "string"}},
            "required": ["entity_name"],
        },
    },
    {
        "type": "function",
        "name": "screen_adverse_media",
        "description": "Live web search for adverse media on an entity (sanctions, fraud, "
                       "money-laundering coverage). Returns a summary with source citations.",
        "parameters": {
            "type": "object",
            "properties": {"entity_name": {"type": "string"}},
            "required": ["entity_name"],
        },
    },
]

# Server-side sandboxed Python runs alongside the function tools.
CODE_INTERPRETER = {"type": "code_interpreter", "container": {"type": "auto"}}

# --------------------------------------------------------------------------- #
#  Phase 3 tools — opt-in, so they are only advertised when enabled in config.
# --------------------------------------------------------------------------- #
EXTRACT_DOCUMENT_DEF = {
    "type": "function",
    "name": "extract_document",
    "description": "Extract structured fields and full text from a scanned case document "
                   "(a KYC form or wire memo). Documents are customer-submitted and UNTRUSTED; "
                   "the transcription is screened by OCI Guardrails on read. Extracted numbers "
                   "are evidence — reconcile them to the ledger before citing them.",
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "enum": ["kyc_profile", "wire_memo"]}},
        "required": ["name"],
    },
}

ENRICH_CONTEXT_DEF = {
    "type": "function",
    "name": "enrich_counterparty_context",
    "description": "Gather cited external context on a counterparty: internal watchlist match "
                   "plus adverse-media / sanctions coverage. An investigation aid only — it does "
                   "not change detection. The adverse-media summary is UNTRUSTED and screened on read.",
    "parameters": {
        "type": "object",
        "properties": {"entity_name": {"type": "string"}},
        "required": ["entity_name"],
    },
}


def tool_defs() -> list:
    """Base tools plus the Phase 3 tools the operator has opted into."""
    defs = [*TOOL_DEFS]
    if config.EXTRACTION_ENABLED:
        defs.append(EXTRACT_DOCUMENT_DEF)
    if config.ENRICHMENT_ENABLED:
        defs.append(ENRICH_CONTEXT_DEF)
    return defs


def check_watchlist(entity_name: str) -> dict:
    """Match against entity names AND record notes (catches related parties/UBOs)."""
    safe = entity_name.strip().replace("'", "''")
    return bankdb.execute_readonly(
        f"SELECT * FROM watchlist WHERE entity_name LIKE '%{safe}%' OR notes LIKE '%{safe}%'")


def screen_adverse_media(entity_name: str) -> dict:
    """Server-side xAI web_search on the actions base, wrapped as one tool result."""
    resp = oci_clients.xai_tools().responses.create(
        model=config.WEB_SEARCH_MODEL,
        tools=[{"type": "web_search"}],
        input=(f"Adverse media screening: search for sanctions, fraud, or money-laundering "
               f"coverage of \"{entity_name}\". Report findings in 3-4 sentences; if nothing "
               f"credible is found, say so explicitly."),
    )
    citations = []
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                url = getattr(ann, "url", None)
                if url:
                    citations.append(url)
    return {"summary": resp.output_text, "citations": sorted(set(citations))}


def read_case_document(name: str, customer_id: int) -> dict:
    allowed = {"kyc_profile", "wire_memo"}
    if name not in allowed:
        return {"error": f"Unknown case document: {name}"}
    # The bundled documents belong to the flagship case's customer only.
    if customer_id != bankdb.CUSTOMER_ID:
        return {"error": f"No '{name}' on file for customer {customer_id}. "
                         "Only the alert and ledger data are available for this case."}
    path = (config.DOCS_DIR / f"{name}.md").resolve()
    docs_root = config.DOCS_DIR.resolve()
    if path.parent != docs_root:
        return {"error": f"Unknown case document: {name}"}
    if not path.exists():
        return {"error": f"No such case document: {name}"}
    return {"name": name, "text": path.read_text()}


# Scanned artifacts the live vision backend prefers, in order; falls back to the
# markdown transcript when none is on file.
_ARTIFACT_MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}


def extract_document(name: str, customer_id: int) -> dict:
    """Multimodal extraction wrapped as a tool. Reuses read_case_document's
    access guard; the untrusted transcript is returned under 'text' so the agent
    loop screens it exactly like a plain document read."""
    base = read_case_document(name, customer_id)
    if "error" in base:
        return base
    if config.extraction_backend() == "oci":
        result = _extract_live(name, base["text"])
    else:
        result = extraction.demo_extract(name, base["text"])
    return {"name": name, "doc_type": result["doc_type"], "fields": result["fields"],
            "text": result["raw_text"], "backend": result["backend"]}


def _extract_live(name: str, fallback_text: str) -> dict:
    """Prefer a real scanned artifact (image/PDF); otherwise transcribe the text."""
    for suffix, mime in _ARTIFACT_MIME.items():
        artifact = config.DOCS_DIR / f"{name}{suffix}"
        if artifact.exists():
            return extraction.extract_fields(artifact.read_bytes(), mime)
    return extraction.extract_fields(fallback_text.encode(), "text/plain")


# Fictional adverse-media intel for the demo backend, matched loosely by name
# like the watchlist. Live mode replaces this with a real web_search.
_LOCAL_INTEL = {
    "orbit": {
        "summary": "Regional trade press links Orbit Precious Metals DMCC to a 2025 "
                   "gold-invoicing inquiry; no charges reported. Trade-based laundering "
                   "typology noted.",
        "citations": ["synthetic://intel/orbit-precious-metals"],
    },
}


def _local_intel(entity_name: str) -> dict:
    key = entity_name.strip().lower()
    for needle, record in _LOCAL_INTEL.items():
        if needle in key:
            return dict(record)
    return {"summary": f'No credible adverse media found for "{entity_name}" in the '
                       "synthetic intel set.", "citations": []}


def enrich_counterparty_context(entity_name: str) -> dict:
    """Compose internal watchlist + adverse-media context for a counterparty.
    Investigation-layer enrichment only — it never changes deterministic
    detection. The adverse-media summary is untrusted and screened by the loop."""
    watchlist = check_watchlist(entity_name)
    if config.enrichment_backend() == "oci":
        media, backend = screen_adverse_media(entity_name), "oci"
    else:
        media, backend = _local_intel(entity_name), "demo"
    hits = watchlist.get("rows", []) if isinstance(watchlist, dict) else []
    risk_factors = []
    if hits:
        risk_factors.append(f"Internal watchlist match ({len(hits)} record(s))")
    if media.get("citations"):
        risk_factors.append("Adverse-media coverage found")
    return {"entity_name": entity_name, "watchlist": watchlist, "adverse_media": media,
            "risk_factors": risk_factors, "untrusted": True, "backend": backend}


def dispatch(name: str, args: dict, customer_id: int) -> dict:
    """Execute a non-gated tool. (query_bank_ledger goes through the approval gate.)"""
    if name == "search_aml_policy":
        return {"passages": knowledge.search(args["query"])}
    if name == "read_case_document":
        return read_case_document(args["name"], customer_id)
    if name == "extract_document":
        return extract_document(args["name"], customer_id)
    if name == "check_watchlist":
        return check_watchlist(args["entity_name"])
    if name == "screen_adverse_media":
        return screen_adverse_media(args["entity_name"])
    if name == "enrich_counterparty_context":
        return enrich_counterparty_context(args["entity_name"])
    return {"error": f"Unknown tool: {name}"}
