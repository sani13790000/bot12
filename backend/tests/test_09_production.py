"""
backend/tests/test_09_production.py
Galaxy Vast AI Tzading Platform — Production Hardening Tests

faz I:
  - Security headers middleware
  - CORS strict mode
  - Request size limiter
  - Request ID middleware
  - Admin IP allowlist
  - Slow request logger
  - Startup validator
  - Monitoring init
"""

from __future__ import annotations

import asyncio
import os
import time
import unittest
from typing import Optional
from unittest.mock import MagicMock, patch


class MockState:
    pass


class MockClient:
    def __init__(self, host: str = "127.0.0.1"):
        self.host = host


class MockRequest:
    def __init__(
        self,
        method: str = "GET",
        path: str = "/api/test",
        headers: Optional[dict] = None,
        client_ip: str = "127.0.0.1",
    ):
        self.method = method
        self.url = MagicMock()
        self.url.path = path
        self.headers = headers or {}
        self.client = MockClient(client_ip)
        self.state = MockState()


class MockResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.headers: dict[str, str] = {}


class TestSecurityHeaders(unittest.TestCase):
    def _run_middleware(self, middleware, request, response):
        async def _run():
            async def call_next(req):
                return response

            return await middleware.dispatch(request, call_next)

        return asyncio.get_event_loop().run_until_complete(_run())

    def test_x_content_type_options(self):
        from backend.core.production_hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        request = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, request, resp)
        self.assertEqual(result.headers.get("X-Content-Type-Options"), "nosniff")

    def test_x_frame_options(self):
        from backend.core.production_hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        request = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, request, resp)
        self.assertEqual(result.headers.get("X-Frame-Options"), "DENY")

    def test_x_xss_protection(self):
        from backend.core.production_hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        request = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, request, resp)
        self.assertEqual(result.headers.get("X-XSS-Protection"), "1; mode=block")

    def test_referrer_policy(self):
        from backend.core.production_hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        request = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, request, resp)
        self.assertIn("Referrer-Policy", result.headers)


class TestRequestIDMiddleware(unittest.TestCase):
    def _run_middleware(self, middleware, request, response):
        async def _run():
            async def call_next(req):
                return response

            return await middleware.dispatch(request, call_next)

        return asyncio.get_event_loop().run_until_complete(_run())

    def test_request_id_added_to_response(self):
        from backend.core.production_hardening import RequestIDMiddleware

        mw = RequestIDMiddleware(app=MagicMock())
        req = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertIn("X-Request-ID", result.headers)
        self.assertTrue(len(result.headers["X-Request-ID"]) > 0)

    def test_existing_request_id_preserved(self):
        from backend.core.production_hardening import RequestIDMiddleware

        mw = RequestIDMiddleware(app=MagicMock())
        req = MockRequest(headers={"X-Request-ID": "custom-id-123"})
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.headers["X-Request-ID"], "custom-id-123")


class TestRequestSizeLimiter(unittest.TestCase):
    def _run_middleware(self, middleware, request, response):
        async def _run():
            async def call_next(req):
                return response

            return await middleware.dispatch(request, call_next)

        return asyncio.get_event_loop().run_until_complete(_run())

    def test_small_request_passes(self):
        from backend.core.production_hardening import RequestSizeLimiterMiddleware

        mw = RequestSizeLimiterMiddleware(app=MagicMock())
        req = MockRequest(headers={"content-length": "1024"})
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 200)

    def test_large_request_blocked(self):
        from backend.core.production_hardening import (
            MAX_REQUEST_BODY_BYTES,
            RequestSizeLimiterMiddleware,
        )

        mw = RequestSizeLimiterMiddleware(app=MagicMock())
        big = str(MAX_REQUEST_BODY_BYTES + 1)
        req = MockRequest(headers={"content-length": big})
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 413)

    def test_no_content_length_passes(self):
        from backend.core.production_hardening import RequestSizeLimiterMiddleware

        mw = RequestSizeLimiterMiddleware(app=MagicMock())
        req = MockRequest()
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 200)


class TestAdminIPAllowlist(unittest.TestCase):
    def _run_middleware(self, middleware, request, response):
        async def _run():
            async def call_next(req):
                return response

            return await middleware.dispatch(request, call_next)

        return asyncio.get_event_loop().run_until_complete(_run())

    def test_non_admin_path_always_passes(self):
        import backend.core.production_hardening as ph
        from backend.core.production_hardening import AdminIPAllowlistMiddleware

        ph.ADMIN_IP_ALLOWLIST = {"192.168.1.1"}
        mw = AdminIPAllowlistMiddleware(app=MagicMock())
        req = MockRequest(path="/api/trades", client_ip="1.2.3.4")
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 200)
        ph.ADMIN_IP_ALLOWLIST = set()

    def test_admin_path_blocked_for_unknown_ip(self):
        import backend.core.production_hardening as ph
        from backend.core.production_hardening import AdminIPAllowlistMiddleware

        ph.ADMIN_IP_ALLOWLIST = {"192.168.1.1"}
        mw = AdminIPAllowlistMiddleware(app=MagicMock())
        req = MockRequest(path="/api/admin/users", client_ip="1.2.3.4")
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 403)
        ph.ADMIN_IP_ALLOWLIST = set()

    def test_admin_path_allowed_for_whitelisted_ip(self):
        import backend.core.production_hardening as ph
        from backend.core.production_hardening import AdminIPAllowlistMiddleware

        ph.ADMIN_IP_ALLOWLIST = {"192.168.1.1"}
        mw = AdminIPAllowlistMiddleware(app=MagicMock())
        req = MockRequest(path="/api/admin/users", client_ip="192.168.1.1")
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 200)
        ph.ADMIN_IP_ALLOWLIST = set()

    def test_empty_allowlist_disables_middleware(self):
        import backend.core.production_hardening as ph
        from backend.core.production_hardening import AdminIPAllowlistMiddleware

        ph.ADMIN_IP_ALLOWLIST = set()
        mw = AdminIPAllowlistMiddleware(app=MagicMock())
        req = MockRequest(path="/api/admin/users", client_ip="1.2.3.4")
        resp = MockResponse()
        result = self._run_middleware(mw, req, resp)
        self.assertEqual(result.status_code, 200)


class TestStartupValidator(unittest.TestCase):
    def test_missing_required_var_returns_false(self):
        from backend.core.startup_validator import validate_environment

        save = {}
        for k in [
            "JWT_SECRET",
            "LICENSE_SECRET",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "MT5_GATEWAY_URL",
            "APP_ENV",
        ]:
            save[k] = os.environ.pop(k, None)
        try:
            result = validate_environment(strict=False)
            self.assertFalse(result)
        finally:
            for k, v in save.items():
                if v is not None:
                    os.environ[k] = v

    def test_all_vars_set_returns_true(self):
        from backend.core.startup_validator import validate_environment

        env = {
            "JWT_SECRET": "a" * 32,
            "LICENSE_SECRET": "b" * 32,
            "SUPABASE_URL": "https://xxx.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "c" * 40,
            "TELEGRAM_BOT_TOKEN": "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefg",
            "TELEGRAM_CHAT_ID": "-100123456",
            "MT5_GATEWAY_URL": "http://192.168.1.100:8080",
            "APP_ENV": "development",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validate_environment(strict=False)
        self.assertTrue(result)

    def test_insecure_jwt_secret_blocked(self):
        from backend.core.startup_validator import EnvVar

        var = EnvVar(
            "JWT_SECRET",
            required=True,
            min_length=32,
            forbidden_values=("change-me-in-production",),
        )
        with patch.dict(os.environ, {"JWT_SECRET": "change-me-in-production"}):
            error = var.validate()
        self.assertIsNotNone(error)
        self.assertIn("INSECURE", error)

    def test_short_secret_blocked(self):
        from backend.core.startup_validator import EnvVar

        var = EnvVar("JWT_SECRET", required=True, min_length=32)
        with patch.dict(os.environ, {"JWT_SECRET": "short"}):
            error = var.validate()
        self.assertIsNotNone(error)
        self.assertIn("TOO SHORT", error)


class TestMonitoring(unittest.TestCase):
    def test_uptime_increases(self):
        from backend.observability.monitoring import get_uptime_seconds

        t1 = get_uptime_seconds()
        time.sleep(0.01)
        t2 = get_uptime_seconds()
        self.assertGreater(t2, t1)

    def test_uptime_human_format(self):
        from backend.observability.monitoring import get_uptime_human

        result = get_uptime_human()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_drawdown_alert_fires(self):
        from backend.observability.monitoring import (
            _alert_state,
            add_alert_hook,
            check_drawdown_alert,
        )

        fired = []

        def hook(alert_type, message, value):
            fired.append((alert_type, value))

        add_alert_hook(hook)
        _alert_state.last_drawdown_alert = 0.0
        check_drawdown_alert(10.0)
        self.assertTrue(any(t == "DRAWDOWN" for t, _ in fired))

    def test_setup_logging_no_error(self):
        from backend.observability.monitoring import setup_logging

        try:
            setup_logging("WARNING")
            setup_logging("DEBUG")
        except Exception as e:
            self.fail(f"setup_logging raised: {e}")

    def test_init_monitoring_no_sentry_dsn(self):
        from backend.observability.monitoring import init_monitoring

        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            try:
                init_monitoring("WARNING")
            except Exception as e:
                self.fail(f"init_monitoring raised: {e}")


class TestSlowRequestLogger(unittest.TestCase):
    def test_response_time_header_added(self):
        from backend.core.production_hardening import SlowRequestMiddleware

        mw = SlowRequestMiddleware(app=MagicMock())
        req = MockRequest()
        resp = MockResponse()

        async def _run():
            async def call_next(r):
                return resp

            return await mw.dispatch(req, call_next)

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("X-Response-Time-Ms", result.headers)
        ms = int(result.headers["X-Response-Time-Ms"])
        self.assertGreaterEqual(ms, 0)


class TestCORSConfiguration(unittest.TestCase):
    def test_wildcard_not_in_default(self):
        import backend.core.production_hardening as ph

        self.assertNotIn("*", ph.ALLOWED_ORIGINS)

    def test_allowed_origins_is_list(self):
        import backend.core.production_hardening as ph

        self.assertIsInstance(ph.ALLOWED_ORIGINS, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
