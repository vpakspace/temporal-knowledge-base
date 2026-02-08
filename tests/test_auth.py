"""Tests for API key authentication."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture()
def _auth_enabled():
    """Enable API key authentication with a test key."""
    with patch("api.auth.get_settings") as mock:
        mock.return_value.api_key = "test-secret-key"
        yield


@pytest.fixture()
def _auth_disabled():
    """Disable API key authentication."""
    with patch("api.auth.get_settings") as mock:
        mock.return_value.api_key = ""
        yield


@pytest.fixture()
def client():
    """Create test client (no lifespan to avoid real connections)."""
    return TestClient(app, raise_server_exceptions=False)


# --- Auth disabled ---


class TestAuthDisabled:
    """When APP_API_KEY is empty, all endpoints are open."""

    @pytest.mark.usefixtures("_auth_disabled")
    def test_health_always_open(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.usefixtures("_auth_disabled")
    def test_stats_open_without_key(self, client: TestClient):
        resp = client.get("/api/stats")
        # Will fail with 500 (no state) but NOT 401
        assert resp.status_code != status.HTTP_401_UNAUTHORIZED


# --- Auth enabled ---


class TestAuthEnabled:
    """When APP_API_KEY is set, endpoints require X-API-Key header."""

    @pytest.mark.usefixtures("_auth_enabled")
    def test_health_always_open(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.usefixtures("_auth_enabled")
    def test_missing_key_returns_401(self, client: TestClient):
        resp = client.get("/api/stats")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing" in resp.json()["detail"]

    @pytest.mark.usefixtures("_auth_enabled")
    def test_wrong_key_returns_401(self, client: TestClient):
        resp = client.get("/api/stats", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid" in resp.json()["detail"]

    @pytest.mark.usefixtures("_auth_enabled")
    def test_correct_key_passes(self, client: TestClient):
        resp = client.get("/api/stats", headers={"X-API-Key": "test-secret-key"})
        # Will fail with 500 (no state) but NOT 401
        assert resp.status_code != status.HTTP_401_UNAUTHORIZED

    @pytest.mark.usefixtures("_auth_enabled")
    def test_post_endpoint_requires_key(self, client: TestClient):
        resp = client.post("/api/ask", json={"question": "test"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.usefixtures("_auth_enabled")
    def test_post_endpoint_with_key(self, client: TestClient):
        resp = client.post(
            "/api/ask",
            json={"question": "test"},
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code != status.HTTP_401_UNAUTHORIZED

    @pytest.mark.usefixtures("_auth_enabled")
    @pytest.mark.parametrize(
        "path",
        [
            "/api/ingest",
            "/api/search",
            "/api/ask",
            "/api/stats",
            "/api/ingest/batch",
            "/api/entities",
            "/api/entities/fake-id",
            "/api/graph",
            "/api/contradictions",
            "/api/export",
            "/api/import",
            "/api/timeline/fake-id",
            "/api/evolution/fake-id",
        ],
    )
    def test_all_api_endpoints_protected(self, client: TestClient, path: str):
        if path == "/api/ingest/batch":
            resp = client.post(path, json=[{"content": "x"}])
        elif path == "/api/import":
            resp = client.post(path, json={"version": "1.0"})
        elif path.startswith("/api/ingest") and "file" not in path:
            resp = client.post(path, json={"content": "x"})
        elif path.startswith("/api/search") or path.startswith("/api/ask"):
            resp = client.post(path, json={"query": "x", "question": "x"})
        else:
            resp = client.get(path)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED, f"{path} not protected"
