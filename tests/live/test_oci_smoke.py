"""Explicitly opt-in OCI checks.

These are skipped in every normal test run. To enable them, configure the OCI
credentials as documented by the application and set ``RAQIB_RUN_LIVE_TESTS=1``.
"""

from __future__ import annotations

import os

import pytest

import config
from src import guardrails, oci_clients


pytestmark = [pytest.mark.live, pytest.mark.contract]


def _live_enabled() -> bool:
    return os.getenv("RAQIB_RUN_LIVE_TESTS") == "1"


@pytest.mark.skipif(not _live_enabled(), reason="set RAQIB_RUN_LIVE_TESTS=1 to call OCI")
def test_responses_api_credentials_are_configured():
    assert config.API_KEY
    assert config.PROJECT_OCID


@pytest.mark.skipif(not _live_enabled(), reason="set RAQIB_RUN_LIVE_TESTS=1 to call OCI")
def test_configured_region_has_an_inference_endpoint():
    region = os.getenv("RAQIB_REGION", config.REGION)
    assert config.INFERENCE_HOST == f"https://inference.generativeai.{region}.oci.oraclecloud.com"


@pytest.mark.skipif(not _live_enabled(), reason="set RAQIB_RUN_LIVE_TESTS=1 to call OCI")
def test_responses_api_minimal_round_trip():
    """A tiny real request proves Bearer auth, project, endpoint, and model access."""
    assert config.API_KEY and config.PROJECT_OCID
    oci_clients.platform.cache_clear()
    response = oci_clients.platform().responses.create(
        model=config.ORCHESTRATOR_MODEL,
        input="Reply with exactly the word READY.",
        max_output_tokens=16,
    )
    assert response.id
    assert response.output


@pytest.mark.skipif(not _live_enabled(), reason="set RAQIB_RUN_LIVE_TESTS=1 to call OCI")
def test_guardrails_minimal_round_trip():
    """A benign real scan proves native OCI signing and Guardrails availability."""
    if not config.guardrails_configured():
        pytest.skip("OCI config profile is not available")
    oci_clients.inference.cache_clear()
    result = guardrails.scan_document(
        "This is a benign fictional compliance memo used only for a live service health check."
    )
    assert 0.0 <= result["prompt_injection_score"] <= 1.0
    assert isinstance(result["injection_detected"], bool)
