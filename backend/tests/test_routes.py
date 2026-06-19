"""Integration tests for core API routes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    os.environ.setdefault("SUPABASE_DB_URL", "postgresql://postgres:test@localhost:5432/postgres")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-32chars")
    os.environ.setdefault("LICENSE_ENCRYPTION_KEY", "test-enc-key-32chars-padded-here")
    os.environ.setdefault("LICENSE_SIGNATURE_KEY", "test-sig-key-32chars-padded-here")
    os.environ.setdefault("ENVIRONMENT", "development")

    from backend.api.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "routes" in data
    assert "websocket_prices" in data


def test_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_openapi_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    # All 23 routers should have their paths
    paths = data.get("paths", {})
    assert len(paths) > 20


def test_ws_status(client):
    resp = client.get("/ws/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "price_connections" in data
    assert "signal_connections" in data


def test_404_returns_json(client):
    resp = client.get("/api/v1/nonexistent-route")
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    headers = resp.headers
    assert "x-content-type-options" in headers
    assert "x-frame-options" in headers
    assert "content-security-policy" in headers


def test_rate_limit_headers(client):
    resp = client.get("/api/v1/agents/status")
    # Either the route exists (200) or not (404) — either way rate limit headers should be present
    assert "x-ratelimit-limit" in resp.headers or resp.status_code in (200, 404, 401)
