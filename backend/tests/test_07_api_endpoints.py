"""
test_07_api_endpoints.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های FastAPI endpoints با TestClient.
"""

from __future__ import annotations

import pytest


class TestAuthEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_check(self) -> None:
        r = self.client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"

    def test_login_missing_credentials_422(self) -> None:
        r = self.client.post("/api/v1/auth/login", json={})
        assert r.status_code in (422, 400)

    def test_register_missing_fields_422(self) -> None:
        r = self.client.post("/api/v1/auth/register", json={})
        assert r.status_code in (422, 400)

    def test_me_without_token_401(self) -> None:
        r = self.client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_protected_route_without_token_401(self) -> None:
        r = self.client.get("/api/v1/trades/")
        assert r.status_code == 401


class TestTradesEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_open_trade_without_auth_401(self) -> None:
        r = self.client.post(
            "/api/v1/trades/open",
            json={
                "symbol": "EURUSD",
                "direction": "buy",
                "volume": 0.10,
                "sl": 1.1000,
                "tp": 1.1150,
            },
        )
        assert r.status_code == 401

    def test_close_trade_without_auth_401(self) -> None:
        r = self.client.post("/api/v1/trades/999001/close")
        assert r.status_code == 401

    def test_list_trades_without_auth_401(self) -> None:
        r = self.client.get("/api/v1/trades/")
        assert r.status_code == 401


class TestSignalsEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_list_signals_without_auth_401(self) -> None:
        r = self.client.get("/api/v1/signals/")
        assert r.status_code == 401

    def test_approve_signal_without_auth_401(self) -> None:
        r = self.client.post("/api/v1/signals/sig001/approve")
        assert r.status_code == 401

    def test_reject_signal_without_auth_401(self) -> None:
        r = self.client.post("/api/v1/signals/sig001/reject")
        assert r.status_code == 401


class TestAdminEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_kill_switch_without_auth_401(self) -> None:
        r = self.client.post("/api/v1/admin/kill-switch/activate", json={"reason": "test"})
        assert r.status_code == 401

    def test_admin_users_without_auth_401(self) -> None:
        r = self.client.get("/api/v1/admin/users")
        assert r.status_code == 401

    def test_security_metrics_without_auth_401(self) -> None:
        r = self.client.get("/api/v1/admin/security/metrics")
        assert r.status_code == 401


class TestLicenseEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_license_status_without_auth_401(self) -> None:
        r = self.client.get("/api/v1/license/status")
        assert r.status_code == 401

    def test_license_activate_without_auth_401(self) -> None:
        r = self.client.post("/api/v1/license/activate", json={"license_key": "TEST-KEY-001"})
        assert r.status_code == 401
