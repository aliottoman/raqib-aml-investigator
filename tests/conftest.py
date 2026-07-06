"""Shared test isolation and deterministic Raqib fixtures.

Every test receives a freshly seeded SQLite database and a private copy of
the bundled documents. OCI client factories fail closed unless a test
explicitly replaces them with a fake. This prevents an accidental live call
even when the developer's real ``.env`` is present.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from src import bankdb, knowledge, oci_clients  # noqa: E402


SOURCE_DOCS = PROJECT_ROOT / "docs"
DEMO_TAPE = PROJECT_ROOT / "src" / "demo_tape.json"


def _unexpected_live_call(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError(
        "A test attempted to construct a real OCI client. Replace the client "
        "factory with a fake, or mark an explicitly opted-in test as live."
    )


@pytest.fixture(autouse=True)
def isolated_runtime(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep tests away from the developer's database, documents, and OCI account."""
    if request.node.get_closest_marker("live") and os.getenv("RAQIB_RUN_LIVE_TESTS") == "1":
        # Opt-in live smoke tests are read-only and deliberately exercise the
        # configured clients. Merely possessing credentials is never enough;
        # the explicit run flag is required as well.
        yield
        return

    docs_dir = tmp_path / "docs"
    shutil.copytree(SOURCE_DOCS, docs_dir)

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "raqib-test.sqlite3")
    monkeypatch.setattr(config, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(config, "WEB_DIST", tmp_path / "web-dist")
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setattr(config, "PROJECT_OCID", "")
    monkeypatch.setattr(config, "COMPARTMENT_ID", "test-compartment")

    monkeypatch.setattr(oci_clients, "platform", _unexpected_live_call)
    monkeypatch.setattr(oci_clients, "inference", _unexpected_live_call)
    monkeypatch.setattr(oci_clients, "xai_tools", _unexpected_live_call)

    knowledge._index = None
    knowledge._managed_store_id = None
    bankdb.build(config.DB_PATH)
    yield
    knowledge._index = None
    knowledge._managed_store_id = None


@pytest.fixture
def seeded_db_path() -> Path:
    return config.DB_PATH


@pytest.fixture
def golden_sar() -> dict[str, Any]:
    """The recorded flagship report, copied so tests may mutate it safely."""
    events = json.loads(DEMO_TAPE.read_text(encoding="utf-8"))
    report = next(event["report"] for event in events if event["type"] == "sar")
    return copy.deepcopy(report)


@pytest.fixture
def role_headers():
    return lambda role: {"X-Raqib-Role": role}


@pytest.fixture
def api_client():
    """A fresh application bound to the test's temporary database and paths."""
    import src.api

    module = importlib.reload(src.api)
    with TestClient(module.app) as client:
        yield client
