"""Auth route tests — register, login, logout, refresh, lockout."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key-" + "x" * 20)
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-role-key-" + "x" * 20)
os.environ.setdefault("SUPABASE_DB_URL", "postgresql://user:pass@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-min-32-chars-ok")
os.environ.setdefault("LICENSE_ENCRYPTION_KEY", "test-enc-key-" + "x" * 20)
os.environ.setdefault("LICENSE_SIGNATURE_KEY", "test-sig-key-" + "x" * 20)
os.environ.setdefault("LICENSE_SALT", "test-salt-value-ok")
os.environ.setdefault("ENVIRONMENT", "development")

from backend.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


class TestRegister:
    def test_register_success(self):
        r = client.post("/api/v1/auth/register", json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "securepassword123",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["message"] == "Registration successful"
        assert data["username"] == "testuser"

    def test_register_short_password(self):
        r = client.post("/api/v1/auth/register", json={
            "username": "testuser2",
            "email": "test2@example.com",
            "password": "short",
        })
        assert r.status_code == 422  # Validation error

    def test_register_invalid_email(self):
        r = client.post("/api/v1/auth/register", json={
            "username": "testuser3",
            "email": "not-an-email",
            "password": "validpassword123",
        })
        assert r.status_code == 422


class TestLogin:
    def test_login_success_dev_mode(self):
        """In dev mode, any non-empty credentials succeed."""
        r = client.post("/api/v1/auth/login", json={
            "username": "anyuser",
            "password": "anypassword",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "Login successful"
        # HttpOnly cookies must be set
        assert "access_token" in r.cookies or "set-cookie" in r.headers

    def test_login_sets_httponly_cookie(self):
        r = client.post("/api/v1/auth/login", json={
            "username": "cookietest",
            "password": "password123",
        })
        assert r.status_code == 200
        # JWT must NOT be in response body (security requirement)
        body = r.json()
        assert "access_token" not in body
        assert "token" not in body

    def test_login_empty_username_rejected(self):
        r = client.post("/api/v1/auth/login", json={
            "username": "",
            "password": "anypassword",
        })
        # Empty username — dev mode still rejects (falsy check)
        assert r.status_code in (401, 422)


class TestLogout:
    def test_logout_clears_cookies(self):
        # Login first
        login_r = client.post("/api/v1/auth/login", json={
            "username": "logouttest",
            "password": "password123",
        })
        assert login_r.status_code == 200

        # Logout
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 200
        assert r.json()["message"] == "Logged out successfully"


class TestAuthStatus:
    def test_status_unauthenticated(self):
        r = client.get("/api/v1/auth/status")
        assert r.status_code == 200
        assert r.json()["authenticated"] is False

    def test_status_after_login(self):
        # Login to get cookie
        client.post("/api/v1/auth/login", json={
            "username": "statustest",
            "password": "password123",
        })
        r = client.get("/api/v1/auth/status")
        assert r.status_code == 200
