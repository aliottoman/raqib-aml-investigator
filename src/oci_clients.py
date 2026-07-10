"""
Raqib — lazy singletons for the three OCI access paths.

* platform()   OpenAI SDK on /openai/v1          -> agent loop, conversations,
                                                    code_interpreter, parse, and
                                                    multimodal extraction (vision).
                                                    Phase 3 adds no new auth path:
                                                    extraction + rule suggestions
                                                    reuse this client; enrichment
                                                    reuses xai_tools().
* xai_tools()  OpenAI SDK on /20231130/actions/v1 -> xAI web_search (only
                                                    served on this base).
* inference()  native OCI SDK client              -> ApplyGuardrails + embeddings
                                                    (IAM signing, not Bearer).
"""

from __future__ import annotations

from functools import lru_cache

import config


@lru_cache(maxsize=1)
def platform():
    from openai import OpenAI
    return OpenAI(base_url=config.PLATFORM_BASE_URL, api_key=config.API_KEY,
                  project=config.PROJECT_OCID, timeout=config.LIVE_TIMEOUT_S)


@lru_cache(maxsize=1)
def xai_tools():
    from openai import OpenAI
    return OpenAI(base_url=config.XAI_TOOLS_BASE_URL, api_key=config.API_KEY,
                  project=config.PROJECT_OCID, timeout=config.LIVE_TIMEOUT_S)


@lru_cache(maxsize=1)
def inference():
    import oci
    cfg = oci.config.from_file(profile_name=config.OCI_PROFILE)
    return oci.generative_ai_inference.GenerativeAiInferenceClient(
        cfg, service_endpoint=config.INFERENCE_HOST)
