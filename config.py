"""
==============================================================================
 Raqib (رقيب) · AI-Assisted AML Operations  —  config.py
 Author: Ali Ottoman | Oracle GenAI
==============================================================================

What this file does
-------------------
Single source of truth for endpoints, model ids, and tuning constants.
Nothing OCI-specific is hard-coded anywhere else in src/.

The two base URLs matter (verified on this tenancy, July 2026):

* PLATFORM base  (/openai/v1)              -> the orchestrator agent loop:
  Responses API + Conversations (case memory) + code_interpreter +
  function tools + structured parse.
* XAI_TOOLS base (/20231130/actions/v1)    -> xAI server-side tools;
  web_search only works here, and only for grok models. Raqib wraps it
  as the adverse-media screening step.

OCI now offers managed Vector Stores and File Search. Both retrieval backends
are implemented behind one search() contract (see src/knowledge.py); local
OCI-embeddings + cosine search stays the default so demo mode is portable and
retrieval deterministic. Flip USE_MANAGED_VECTOR_STORES (env
RAQIB_USE_MANAGED_VECTOR_STORES) to serve policy retrieval from a managed
Vector Store / File Search instead.

Run modes
---------
* live — .env has OPENAI_API_KEY_CHICAGO + CHICAGO_PROJECT_OCID -> real calls.
* demo — no credentials -> a recorded investigation plays with identical
         event choreography, so the demo works on any laptop.

The service-specific API key is appropriate for development. OCI IAM-based
authentication is the recommended path for production workloads and
OCI-managed environments.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_ROOT / "docs"
WEB_DIST = PROJECT_ROOT / "web" / "dist"

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

_db_path_override = os.getenv("RAQIB_DB_PATH")
DB_PATH = (
    Path(_db_path_override).expanduser().resolve()
    if _db_path_override
    else PROJECT_ROOT / "raqib_bank.db"
)

# --------------------------------------------------------------------------- #
#  Endpoints (region is Chicago — the Enterprise AI project lives there)
# --------------------------------------------------------------------------- #
REGION = os.getenv("RAQIB_REGION", "us-chicago-1")
INFERENCE_HOST = f"https://inference.generativeai.{REGION}.oci.oraclecloud.com"

PLATFORM_BASE_URL = f"{INFERENCE_HOST}/openai/v1"              # loop + memory
XAI_TOOLS_BASE_URL = f"{INFERENCE_HOST}/20231130/actions/v1"   # web_search

# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #
API_KEY = os.getenv("OPENAI_API_KEY_CHICAGO", "")
PROJECT_OCID = os.getenv("CHICAGO_PROJECT_OCID", "")
COMPARTMENT_ID = os.getenv("OCI_COMPARTMENT_ID", "")
OCI_PROFILE = os.getenv("RAQIB_OCI_PROFILE", "DEFAULT")        # guardrails + embeddings

# --------------------------------------------------------------------------- #
#  Models (verify per region before a customer demo)
# --------------------------------------------------------------------------- #
ORCHESTRATOR_MODEL = os.getenv("RAQIB_ORCHESTRATOR_MODEL", "xai.grok-4.20-reasoning")
SAR_MODEL = os.getenv("RAQIB_SAR_MODEL", "xai.grok-4.20-multi-agent-0309")  # structured parse
WEB_SEARCH_MODEL = os.getenv("RAQIB_WEB_SEARCH_MODEL", "xai.grok-4.20-reasoning")
EMBED_MODEL = os.getenv("RAQIB_EMBED_MODEL", "cohere.embed-multilingual-v3.0")

# --------------------------------------------------------------------------- #
#  Feature flags / tuning
# --------------------------------------------------------------------------- #
def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Managed retrieval (Track B). When true, search_aml_policy is served by an OCI
# Generative AI Vector Store / File Search instead of local cosine search. The
# local path stays the default so demo mode is portable and tests are
# deterministic. The public search() contract is identical for both backends.
USE_MANAGED_VECTOR_STORES = _flag("RAQIB_USE_MANAGED_VECTOR_STORES", False)
# Point at a pre-provisioned store to skip in-process provisioning; otherwise
# the managed backend provisions one on first use and caches its id.
VECTOR_STORE_ID = os.getenv("RAQIB_VECTOR_STORE_ID", "")
VECTOR_STORE_NAME = os.getenv("RAQIB_VECTOR_STORE_NAME", "raqib-aml-policy")

MAX_AGENT_STEPS = 12                # hard ceiling on tool-loop iterations
LIVE_TIMEOUT_S = 180                # per model call

PORT = int(os.getenv("RAQIB_PORT", "8117"))

# Explicit local origins keep the demo convenient without making credentialed
# browser calls available to every site.  Deployments can provide a
# comma-separated allowlist via RAQIB_ALLOWED_ORIGINS.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "RAQIB_ALLOWED_ORIGINS",
        f"http://localhost:{PORT},http://127.0.0.1:{PORT},"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5178,http://127.0.0.1:5178",
    ).split(",")
    if origin.strip()
]


def live_configured() -> bool:
    """True when the Responses API credentials exist -> live mode possible."""
    return bool(API_KEY and PROJECT_OCID)


def guardrails_configured() -> bool:
    """Guardrails signs with ~/.oci config (not the Bearer key)."""
    return os.path.exists(os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")))


def retrieval_backend() -> str:
    """Which policy-retrieval backend search_aml_policy uses."""
    return "managed" if USE_MANAGED_VECTOR_STORES else "local"
