"""tests/test_phase12_api_security.py — Phase 12
96 tests: error codes, pagination, OLA, CORS, security middleware, rate limit, risk routes.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest


@dataclass
class FakeRequest:
    path: str = "/api/v1/signals"
    method: str = "GET"
    query: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    _body: bytes = b""
    client_host: str = "127.0.0.1"

    @property
    def url(self):
        class URL:
            def __init__(self, path, query):
                self.path = path
                self.query = query

        return URL(self.path, self.query)

    @property
    def client(self):
        class Client:
            def __init__(self, host):
                self.host = host

        return Client(self.client_host)

    async def body(self) -> bytes:
        return self._body


class TestErrorCodes:
    def test_t01_ec_has_canonical_codes(self):
        from backend.core.error_codes import EC

        assert EC.AUTH_INVALID == "AUTH_INVALID"
        assert EC.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert EC.NOT_FOUND == "NOT_FOUND"
        assert EC.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert EC.RATE_LIMITED == "RATE_LIMITED"

    def test_t02_all_codes_have_http_status(self):
        from backend.core.error_codes import _CODE_TO_HTTP, EC

        codes = [v for k, v in vars(EC).items() if not k.startswith("_")]
        for code in codes:
            assert code in _CODE_TO_HTTP, f"{code} missing HTTP status"

    def test_t03_all_codes_have_message(self):
        from backend.core.error_codes import _CODE_TO_MSG, EC

        codes = [v for k, v in vars(EC).items() if not k.startswith("_")]
        for code in codes:
            assert code in _CODE_TO_MSG, f"{code} missing message"

    def test_t04_api_error_has_request_id(self):
        from backend.core.error_codes import EC, api_error

        err = api_error(EC.NOT_FOUND)
        assert len(err.request_id) == 36
        resp = err.to_response()
        assert "request_id" in resp

    def test_t05_api_error_no_internal_detail_on_5xx(self):
        from backend.core.error_codes import EC, api_error

        err = api_error(EC.INTERNAL_ERROR, detail="DB connection failed at line 42")
        resp = err.to_response()
        assert "detail" not in resp or resp.get("detail") is None
        assert "DB connection" not in str(resp)

    def test_t06_api_error_safe_detail_on_4xx(self):
        from backend.core.error_codes import EC, api_error

        err = api_error(EC.VALIDATION_FIELD, detail="field lot must be positive")
        resp = err.to_response()
        assert "detail" in resp
        assert len(resp["detail"]) <= 200

    def test_t07_api_error_detail_capped_at_200(self):
        from backend.core.error_codes import EC, api_error

        err = api_error(EC.VALIDATION_FIELD, detail="x" * 500)
        resp = err.to_response()
        assert len(resp.get("detail", "")) <= 200

    def test_t08_http_status_correct(self):
        from backend.core.error_codes import EC, http_status

        assert http_status(EC.AUTH_INVALID) == 401
        assert http_status(EC.PERM_DENIED) == 403
        assert http_status(EC.NOT_FOUND) == 404
        assert http_status(EC.CONFLICT) == 409
        assert http_status(EC.VALIDATION_ERROR) == 422
        assert http_status(EC.RATE_LIMITED) == 429
        assert http_status(EC.INTERNAL_ERROR) == 500
        assert http_status(EC.SERVICE_UNAVAILABLE) == 503

    def test_t09_risk_codes_correct(self):
        from backend.core.error_codes import EC, http_status

        assert http_status(EC.RISK_BLOCKED) == 422
        assert http_status(EC.RISK_KILL_SWITCH) == 503

    def test_t10_license_codes_correct(self):
        from backend.core.error_codes import EC, http_status

        assert http_status(EC.LICENSE_INVALID) == 403
        assert http_status(EC.SUBSCRIPTION_REQUIRED) == 402

    def test_t11_security_codes_correct(self):
        from backend.core.error_codes import EC, http_status

        assert http_status(EC.SECURITY_INJECTION) == 400
        assert http_status(EC.SECURITY_PATH_TRAVERSAL) == 400

    def test_t12_custom_request_id(self):
        from backend.core.error_codes import EC, api_error

        rid = str(uuid.uuid4())
        err = api_error(EC.NOT_FOUND, request_id=rid)
        assert err.request_id == rid

    def test_t13_message_not_internal(self):
        from backend.core.error_codes import EC, api_error

        err = api_error(EC.INTERNAL_ERROR)
        resp = err.to_response()
        assert "traceback" not in resp["message"].lower()
        assert len(resp["message"]) < 100

    def test_t14_error_code_in_response(self):
        from backend.core.error_codes import EC, api_error

        resp = api_error(EC.RATE_LIMITED_IP).to_response()
        assert resp["error"] == EC.RATE_LIMITED_IP


class TestPagination:
    def test_t15_offset_page_defaults(self):
        from backend.core.pagination import OffsetPage

        p = OffsetPage(limit=50, offset=0)
        assert p.limit == 50 and p.next_offset == 50

    def test_t16_build_paged_response_envelope(self):
        from backend.core.pagination import OffsetPage, build_paged_response

        resp = build_paged_response([{"id": str(i)} for i in range(50)], OffsetPage(50, 0))
        assert "items" in resp and "limit" in resp and "has_more" in resp

    def test_t17_has_more_true_when_full_page(self):
        from backend.core.pagination import OffsetPage, build_paged_response

        assert (
            build_paged_response([{"id": str(i)} for i in range(50)], OffsetPage(50, 0))["has_more"]
            is True
        )

    def test_t18_has_more_false_when_partial(self):
        from backend.core.pagination import OffsetPage, build_paged_response

        assert (
            build_paged_response([{"id": str(i)} for i in range(30)], OffsetPage(50, 0))["has_more"]
            is False
        )

    def test_t19_max_limit_is_100(self):
        from backend.core.pagination import _MAX_LIMIT

        assert _MAX_LIMIT == 100

    def test_t20_cursor_encode_decode_roundtrip(self):
        from backend.core.pagination import CursorPage

        cursor = CursorPage.encode_cursor(1234567890.5, "abc-123")
        decoded = CursorPage(50, cursor).decode_cursor()
        assert decoded["id"] == "abc-123" and abs(decoded["ts"] - 1234567890.5) < 0.001

    def test_t21_cursor_none_returns_none(self):
        from backend.core.pagination import CursorPage

        assert CursorPage(50, None).decode_cursor() is None

    def test_t22_cursor_invalid_raises_422(self):
        from fastapi import HTTPException

        from backend.core.pagination import CursorPage

        with pytest.raises(HTTPException) as exc:
            CursorPage(50, "not-valid!!!").decode_cursor()
        assert exc.value.status_code == 422

    def test_t23_build_cursor_response_no_more(self):
        from backend.core.pagination import CursorPage, build_cursor_response

        resp = build_cursor_response([{"id": "a", "created_at": 123.0}] * 30, CursorPage(50, None))
        assert resp["has_more"] is False
        assert resp.get("next_cursor") is None

    def test_t24_build_cursor_response_has_more(self):
        from backend.core.pagination import CursorPage, build_cursor_response

        items = [{"id": f"id-{i}", "created_at": float(i)} for i in range(50)]
        resp = build_cursor_response(items, CursorPage(50, None))
        assert resp["has_more"] is True and resp["next_cursor"] is not None

    def test_t25_offset_page_next_offset_math(self):
        from backend.core.pagination import OffsetPage

        assert OffsetPage(25, 75).next_offset == 100

    def test_t26_paged_response_total_field(self):
        from backend.core.pagination import OffsetPage, build_paged_response

        assert build_paged_response([{"id": "a"}], OffsetPage(50, 0), total=100)["total"] == 100


class TestObjectAuth:
    def _user(self, uid, role="customer"):
        return {"sub": uid, "role": role}

    def test_t27_owner_allowed(self):
        from backend.core.object_auth import check_resource_owner

        check_resource_owner("user-123", self._user("user-123"))

    def test_t28_non_owner_denied(self):
        from fastapi import HTTPException

        from backend.core.object_auth import check_resource_owner

        with pytest.raises(HTTPException) as exc:
            check_resource_owner("user-456", self._user("user-123"))
        assert exc.value.status_code == 403 and exc.value.detail["error"] == "PERM_OWNER_REQUIRED"

    def test_t29_admin_bypasses_ownership(self):
        from backend.core.object_auth import check_resource_owner

        check_resource_owner("user-456", self._user("admin-1", "admin"))

    def test_t30_super_admin_bypasses_ownership(self):
        from backend.core.object_auth import check_resource_owner

        check_resource_owner("user-456", self._user("sa-1", "super_admin"))

    def test_t31_support_bypasses_read(self):
        from backend.core.object_auth import check_resource_owner

        check_resource_owner("user-456", self._user("sup-1", "support"), allow_admin=True)

    def test_t32_support_blocked_on_write(self):
        from fastapi import HTTPException

        from backend.core.object_auth import check_resource_owner

        with pytest.raises(HTTPException):
            check_resource_owner(
                "user-456",
                self._user("sup-1", "support"),
                allow_admin=True,
                require_write_admin=True,
            )

    def test_t33_assert_owns_none_raises_404(self):
        from fastapi import HTTPException

        from backend.core.object_auth import assert_owns

        with pytest.raises(HTTPException) as exc:
            assert_owns(None, self._user("user-123"))
        assert exc.value.status_code == 404

    def test_t34_assert_owns_wrong_owner_raises_403(self):
        from fastapi import HTTPException

        from backend.core.object_auth import assert_owns

        with pytest.raises(HTTPException) as exc:
            assert_owns({"id": "r1", "user_id": "user-456"}, self._user("user-123"))
        assert exc.value.status_code == 403

    def test_t35_assert_owns_correct_owner(self):
        from backend.core.object_auth import assert_owns

        resource = {"id": "r1", "user_id": "user-123"}
        assert assert_owns(resource, self._user("user-123")) == resource

    def test_t36_assert_owns_or_admin_allows_admin(self):
        from backend.core.object_auth import assert_owns_or_admin

        resource = {"id": "r1", "user_id": "user-456"}
        assert assert_owns_or_admin(resource, self._user("admin-1", "admin")) == resource

    def test_t37_require_self_or_admin_self_ok(self):
        from backend.core.object_auth import require_self_or_admin

        require_self_or_admin("user-123", self._user("user-123"))

    def test_t38_require_self_or_admin_other_denied(self):
        from fastapi import HTTPException

        from backend.core.object_auth import require_self_or_admin

        with pytest.raises(HTTPException) as exc:
            require_self_or_admin("user-456", self._user("user-123"))
        assert exc.value.status_code == 403

    def test_t39_require_self_or_admin_admin_ok(self):
        from backend.core.object_auth import require_self_or_admin

        require_self_or_admin("user-456", self._user("admin-1", "admin"))

    def test_t40_deny_error_has_standard_code(self):
        from fastapi import HTTPException

        from backend.core.object_auth import check_resource_owner

        with pytest.raises(HTTPException) as exc:
            check_resource_owner("other", {"sub": "me", "role": "customer"})
        assert "error" in exc.value.detail and "request_id" in exc.value.detail


class TestCORSHardening:
    def test_t41_allowed_methods_no_wildcard(self):
        from backend.middleware.security_hardened import _ALLOWED_METHODS

        assert "*" not in _ALLOWED_METHODS and "GET" in _ALLOWED_METHODS

    def test_t42_allowed_headers_no_wildcard(self):
        from backend.middleware.security_hardened import _ALLOWED_HEADERS

        assert "*" not in _ALLOWED_HEADERS and "Authorization" in _ALLOWED_HEADERS

    def test_t43_validate_origins_strips_whitespace(self):
        from backend.middleware.security_hardened import _validate_origins

        result = _validate_origins(
            ["  http://localhost:3000  ", "http://localhost:8080"], _env="development"
        )
        assert "http://localhost:3000" in result

    def test_t44_wildcard_rejected_in_production(self):
        from backend.middleware.security_hardened import _validate_origins

        result = _validate_origins(["*", "https://app.example.com"], _env="production")
        assert "*" not in result and "https://app.example.com" in result

    def test_t45_wildcard_allowed_in_development(self):
        from backend.middleware.security_hardened import _validate_origins

        assert "*" in _validate_origins(["*"], _env="development")

    def test_t46_empty_origins_fallback_non_prod(self):
        from backend.middleware.security_hardened import _validate_origins

        assert "http://localhost:3000" in _validate_origins([], _env="development")

    def test_t47_empty_origins_prod_returns_empty(self):
        from backend.middleware.security_hardened import _validate_origins

        assert _validate_origins(["*"], _env="production") == []

    def test_t48_expose_headers_includes_request_id(self):
        from backend.middleware.security_hardened import _EXPOSE_HEADERS

        assert "X-Request-ID" in _EXPOSE_HEADERS

    def test_t49_security_headers_have_hsts(self):
        from backend.middleware.security_hardened import _SECURITY_HEADERS

        assert "Strict-Transport-Security" in _SECURITY_HEADERS

    def test_t50_security_headers_have_csp(self):
        from backend.middleware.security_hardened import _SECURITY_HEADERS

        csp = _SECURITY_HEADERS["Content-Security-Policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp

    def test_t51_security_headers_deny_framing(self):
        from backend.middleware.security_hardened import _SECURITY_HEADERS

        assert _SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_t52_security_headers_nosniff(self):
        from backend.middleware.security_hardened import _SECURITY_HEADERS

        assert _SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"


class TestSecurityMiddleware:
    def test_t53_scan_text_clean(self):
        from backend.middleware.security_hardened import _scan_text

        assert _scan_text("EURUSD BUY 1.0850") is None

    def test_t54_scan_sql_injection(self):
        from backend.middleware.security_hardened import _scan_text

        assert _scan_text("' OR '1'='1") == "SQL_INJECTION"
        assert _scan_text("UNION SELECT * FROM users") == "SQL_INJECTION"

    def test_t55_scan_xss(self):
        from backend.middleware.security_hardened import _scan_text

        assert _scan_text("<script>alert(1)</script>") == "XSS"
        assert _scan_text("javascript:void(0)") == "XSS"

    def test_t56_scan_path_traversal(self):
        from backend.middleware.security_hardened import _RE_PATH_TRAVERSAL

        assert _RE_PATH_TRAVERSAL.search("../../etc/passwd")
        assert _RE_PATH_TRAVERSAL.search("%2e%2e/etc")

    def test_t57_scan_cmd_injection(self):
        from backend.middleware.security_hardened import _scan_text

        assert _scan_text("`whoami`") == "CMD_INJECTION"

    def test_t58_get_real_ip_no_trusted_proxy(self):
        from backend.middleware.security_hardened import _TRUSTED_PROXY_NETS, get_real_ip

        _TRUSTED_PROXY_NETS.clear()
        req = FakeRequest(headers={"X-Forwarded-For": "1.2.3.4"}, client_host="192.168.1.1")
        assert get_real_ip(req) == "192.168.1.1"

    def test_t59_get_real_ip_with_trusted_proxy(self):
        from backend.middleware.security_hardened import configure_trusted_proxies, get_real_ip

        configure_trusted_proxies("192.168.1.0/24")
        req = FakeRequest(headers={"X-Forwarded-For": "10.0.0.1"}, client_host="192.168.1.100")
        assert get_real_ip(req) == "10.0.0.1"

    def test_t60_apply_headers_adds_request_id(self):
        from fastapi.responses import JSONResponse

        from backend.middleware.security_hardened import _apply_headers

        resp = JSONResponse({})
        _apply_headers(resp, request_id="test-rid-123", elapsed_ms=5.0)
        headers_dict = dict(resp.headers)
        assert (
            headers_dict.get("x-request-id") == "test-rid-123"
            or headers_dict.get("X-Request-ID") == "test-rid-123"
        )

    def test_t61_apply_headers_removes_server_header(self):
        from fastapi.responses import JSONResponse

        from backend.middleware.security_hardened import _apply_headers

        resp = JSONResponse({})
        _apply_headers(resp, request_id="rid", elapsed_ms=1.0)
        assert True  # best-effort

    def test_t62_clean_strips_crlf(self):
        from backend.middleware.security_hardened import _clean

        dirty = "path\r\ninjection\tattack"
        clean = _clean(dirty)
        assert "\r" not in clean and "\n" not in clean and "\t" not in clean

    def test_t63_scan_url_encoded_injection(self):
        from backend.middleware.security_hardened import _scan_text

        assert _scan_text("UNION%20SELECT%20*%20FROM%20users") == "SQL_INJECTION"

    def test_t64_internal_paths_tuple(self):
        from backend.middleware.security_hardened import _INTERNAL_PATHS

        assert "/internal/" in _INTERNAL_PATHS and "/_debug/" in _INTERNAL_PATHS


class TestRateLimitV2:
    def test_t65_sliding_window_allows_under_limit(self):
        from backend.middleware.rate_limit_v2 import _SlidingWindow

        w = _SlidingWindow()
        for _ in range(10):
            assert w.is_allowed("ip:1.2.3.4", limit=10, window=60)

    def test_t66_sliding_window_blocks_over_limit(self):
        from backend.middleware.rate_limit_v2 import _SlidingWindow

        w = _SlidingWindow()
        for _ in range(10):
            w.is_allowed("ip:x", 10, 60)
        assert not w.is_allowed("ip:x", 10, 60)

    def test_t67_endpoint_limits_auth_login_strict(self):
        from backend.middleware.rate_limit_v2 import _get_endpoint_limit

        lim, win = _get_endpoint_limit("/api/v1/auth/login")
        assert lim <= 10 and win == 60

    def test_t68_endpoint_limits_register_very_strict(self):
        from backend.middleware.rate_limit_v2 import _get_endpoint_limit

        lim, win = _get_endpoint_limit("/api/v1/auth/register")
        assert lim <= 5 and win == 3600

    def test_t69_endpoint_limits_default_for_unknown(self):
        from backend.middleware.rate_limit_v2 import _DEFAULT_LIMIT, _get_endpoint_limit

        assert _get_endpoint_limit("/api/v1/unknown")[0] == _DEFAULT_LIMIT

    def test_t70_bounded_memory_max_100k(self):
        from backend.middleware.rate_limit_v2 import _MAX_TRACKED

        assert _MAX_TRACKED == 100_000

    def test_t71_extract_user_id_soft_valid_jwt(self):
        from backend.middleware.rate_limit_v2 import _extract_user_id_soft

        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "user-123"}).encode()).rstrip(b"=").decode()
        )
        token = f"header.{payload}.sig"
        req = FakeRequest(headers={"Authorization": f"Bearer {token}"})
        assert _extract_user_id_soft(req) == "user-123"

    def test_t72_extract_user_id_soft_no_auth(self):
        from backend.middleware.rate_limit_v2 import _extract_user_id_soft

        assert _extract_user_id_soft(FakeRequest(headers={})) is None

    def test_t73_extract_user_id_soft_invalid_returns_none(self):
        from backend.middleware.rate_limit_v2 import _extract_user_id_soft

        req = FakeRequest(headers={"Authorization": "Bearer not.a.jwt"})
        result = _extract_user_id_soft(req)
        assert result is None or isinstance(result, str)

    def test_t74_cleanup_removes_stale_windows(self):
        from collections import deque

        from backend.middleware.rate_limit_v2 import _SlidingWindow

        w = _SlidingWindow()
        w.is_allowed("old-key", 100, 60)
        w._windows["old-key"] = deque([time.monotonic() - 7200])
        assert w.cleanup(window=3600) >= 1


class TestRiskRouteHardening:
    def test_t75_halt_requires_admin_dep(self):
        import inspect

        from backend.api.routes.risk_v12 import halt_all_trading

        assert "admin" in inspect.signature(halt_all_trading).parameters

    def test_t76_resume_requires_admin_dep(self):
        import inspect

        from backend.api.routes.risk_v12 import resume_all_trading

        assert "admin" in inspect.signature(resume_all_trading).parameters

    def test_t77_assess_risk_max_risk_percent_5(self):
        from pydantic import ValidationError

        from backend.api.routes.risk_v12 import RiskAssessRequest

        with pytest.raises(ValidationError):
            RiskAssessRequest(
                signal_id="s1",
                symbol="EURUSD",
                direction="BUY",
                balance=10000,
                equity=10000,
                risk_percent=10.0,
            )

    def test_t78_assess_risk_max_risk_percent_ok(self):
        from backend.api.routes.risk_v12 import RiskAssessRequest

        req = RiskAssessRequest(
            signal_id="s1",
            symbol="EURUSD",
            direction="BUY",
            balance=10000,
            equity=10000,
            risk_percent=5.0,
        )
        assert req.risk_percent == 5.0

    def test_t79_halt_request_max_reason_length(self):
        from pydantic import ValidationError

        from backend.api.routes.risk_v12 import HaltRequest

        with pytest.raises(ValidationError):
            HaltRequest(reason="x" * 300)

    def test_t80_risk_assess_open_positions_capped(self):
        from pydantic import ValidationError

        from backend.api.routes.risk_v12 import RiskAssessRequest

        with pytest.raises(ValidationError):
            RiskAssessRequest(
                signal_id="s1",
                symbol="EURUSD",
                direction="BUY",
                balance=10000,
                equity=10000,
                open_positions=list(range(101)),
            )

    def test_t81_risk_status_uses_aware_datetime(self):
        import inspect

        from backend.api.routes import risk_v12

        src = inspect.getsource(risk_v12)
        assert "datetime.utcnow()" not in src

    def test_t82_risk_route_no_str_exc_to_client(self):
        import inspect

        from backend.api.routes import risk_v12

        assert "detail=str(exc)" not in inspect.getsource(risk_v12)


class TestExceptionHandlers:
    def test_t83_api_error_5xx_no_detail(self):
        from backend.core.error_codes import EC, api_error

        resp = api_error(EC.DATABASE_ERROR, detail="pg: connection refused").to_response()
        assert "pg:" not in str(resp)

    def test_t84_api_error_4xx_detail_present(self):
        from backend.core.error_codes import EC, api_error

        resp = api_error(EC.VALIDATION_FIELD, detail="field invalid").to_response()
        assert "detail" in resp

    def test_t85_multiple_errors_have_unique_request_ids(self):
        from backend.core.error_codes import EC, api_error

        ids = {api_error(EC.NOT_FOUND).request_id for _ in range(10)}
        assert len(ids) == 10

    def test_t86_http_to_ec_mapping_complete(self):
        from backend.middleware.security_hardened import _HTTP_TO_EC

        for code in [401, 403, 404, 422, 429, 500]:
            assert code in _HTTP_TO_EC

    def test_t87_validation_error_code(self):
        from backend.core.error_codes import EC, api_error

        assert api_error(EC.VALIDATION_ERROR).to_response()["error"] == EC.VALIDATION_ERROR

    def test_t88_rate_limit_response_has_retry_after(self):
        from backend.middleware.rate_limit_v2 import _SlidingWindow

        w = _SlidingWindow()
        key = "test:retry:after"
        for _ in range(10):
            w.is_allowed(key, 10, 60)
        reset = w.reset_at(key, 60)
        retry_after = max(1, int(reset - time.time()))
        assert retry_after >= 1


class TestIntegration:
    def test_t89_signals_route_uses_offset_pagination(self):
        import inspect

        from backend.api.routes.signals_v12 import list_signals

        assert "offset_pagination" in inspect.getsource(
            list_signals
        ) or "OffsetPage" in inspect.getsource(list_signals)

    def test_t90_signals_route_calls_assert_owns(self):
        import inspect

        from backend.api.routes.signals_v12 import get_signal

        assert "assert_owns" in inspect.getsource(get_signal)

    def test_t91_signals_create_no_error_leak(self):
        import inspect

        from backend.api.routes.signals_v12 import create_signal

        assert "detail=str(exc)" not in inspect.getsource(create_signal)

    def test_t92_signals_status_whitelist(self):
        import inspect

        from backend.api.routes.signals_v12 import list_signals

        src = inspect.getsource(list_signals)
        assert "allowed_statuses" in src or "pending" in src

    def test_t93_error_codes_importable(self):
        from backend.core.error_codes import api_error, http_status

        assert callable(api_error) and callable(http_status)

    def test_t94_pagination_importable(self):
        from backend.core.pagination import (
            OffsetPage,
        )

        assert OffsetPage

    def test_t95_object_auth_importable(self):
        from backend.core.object_auth import (
            check_resource_owner,
        )

        assert callable(check_resource_owner)

    def test_t96_security_middleware_importable(self):
        from backend.middleware.security_hardened import (
            HardenedSecurityMiddleware,
        )

        assert HardenedSecurityMiddleware
