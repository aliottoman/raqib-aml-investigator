from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

import config


pytestmark = pytest.mark.security


def test_cors_allows_local_ui_but_not_arbitrary_origins(api_client):
    local = api_client.options(
        "/api/session",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Raqib-Role",
        },
    )
    attacker = api_client.options(
        "/api/session",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert attacker.status_code == 400
    assert "access-control-allow-origin" not in attacker.headers


@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor"])
def test_rule_suggest_is_rule_admin_only(api_client, role: str):
    forbidden = api_client.post(
        "/api/rules/CASH-VELOCITY-04/suggest",
        json={"intent": "tighten"},
        headers={"X-Raqib-Role": role},
    )
    assert forbidden.status_code == 403


def test_spa_cannot_escape_build_directory_or_shadow_unknown_api_routes(tmp_path):
    dist = tmp_path / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>RAQIB-SPA</html>", encoding="utf-8")
    (dist / "app.txt").write_text("public asset", encoding="utf-8")
    secret = dist.parent / "secret.txt"
    secret.write_text("TOP-SECRET-SENTINEL", encoding="utf-8")
    config.WEB_DIST = dist

    import src.api

    module = importlib.reload(src.api)
    with TestClient(module.app) as client:
        public = client.get("/app.txt")
        traversal = client.get("/%2e%2e/secret.txt")
        nested_traversal = client.get("/assets/%2e%2e/%2e%2e/secret.txt")
        missing_api = client.get("/api/does-not-exist")

    assert public.status_code == 200
    assert public.text == "public asset"
    assert "TOP-SECRET-SENTINEL" not in traversal.text
    assert traversal.status_code in {404, 200}
    if traversal.status_code == 200:
        assert "RAQIB-SPA" in traversal.text
    assert "TOP-SECRET-SENTINEL" not in nested_traversal.text
    assert missing_api.status_code == 404
    assert "RAQIB-SPA" not in missing_api.text

