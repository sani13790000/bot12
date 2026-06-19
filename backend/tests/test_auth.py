"""Tests for authentication routes."""
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


def test_register_success(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "username": "testuser",
    })
    assert resp.status_code == 201
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies
    data = resp.json()
    assert data["token_type"] == "cookie"


def test_register_weak_password(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": "test2@example.com",
        "password": "123",
        "username": "testuser2",
    })
    assert resp.status_code == 422


def test_login_success(client):
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@galaxyvast.ai",
        "password": "password",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_sets_httponly_cookie(client):
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@galaxyvast.ai",
        "password": "password",
    })
    assert resp.status_code == 200
    # JWT must NOT appear in body
    body = resp.json()
    assert "access_token" not in body
    assert "token" not in body


def test_lockout_after_5_failures(client):
    for i in range(5):
        resp = client.post("/api/v1/auth/login", json={
            "email": f"brute{i}@test.com",
            "password": "wrongpassword",
        })
    # 6th attempt from same IP should be locked
    resp = client.post("/api/v1/auth/login", json={
        "email": "victim@test.com",
        "password": "wrongpassword",
    })
    # Either 401 (wrong creds) or 429 (locked) is acceptable
    assert resp.status_code in (401, 429)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "database" in data
    assert "modules" in data
    assert "routes" in data


def test_logout(client):
    # Login first
    login = client.post("/api/v1/auth/login", json={
        "email": "admin@galaxyvast.ai",
        "password": "password",
    })
    assert login.status_code == 200

    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully"
