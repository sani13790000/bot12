"""
tests/test_phase_s.py
Phase S -- Production Hardening -- 55 unit tests
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import unittest
from datetime import datetime, timedelta, timezone


def _b64url(b: bytes) -> str:
    import base64

    return base64.b64encode(b).rstrip(b"=").replace(b"+", b"-").replace(b"/", b"_").decode()


def _make_jwt(payload: dict, secret: str, alg: str = "HS256") -> str:
    header = _b64url(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    signing = f"{header}.{body}".encode("ascii")
    sig = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def run(coro):
    return asyncio.run(coro)


# ============================================================================
# Auth Hardening (S-9..S-12)
# ============================================================================
import sys

sys.path.insert(0, "/home/definable/phase-s")
from auth_hardening import (
    RefreshTokenStore,
    TokenRevocationList,
    check_scope,
    create_hs256_jwt,
    verify_hs256_jwt,
)


class TestS9JWTVerification(unittest.TestCase):
    SECRET = "super-secret-key-32chars-xxxxxxxx"

    def test_valid_token(self):
        payload = {"sub": "user1", "exp": int(time.time()) + 3600}
        token = create_hs256_jwt(payload, self.SECRET)
        result = verify_hs256_jwt(token, self.SECRET)
        self.assertIsNotNone(result)
        self.assertEqual(result["sub"], "user1")

    def test_wrong_secret_rejected(self):
        token = create_hs256_jwt({"sub": "user1"}, self.SECRET)
        result = verify_hs256_jwt(token, "wrong-secret-xxxxxxxxxxxxxxxxxx")
        self.assertIsNone(result)

    def test_wrong_algorithm_rejected(self):
        import base64

        header = base64.b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode()
        body = base64.b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
        result = verify_hs256_jwt(f"{header}.{body}.fakesig", self.SECRET)
        self.assertIsNone(result)

    def test_malformed_token(self):
        self.assertIsNone(verify_hs256_jwt("not.a.jwt", self.SECRET))
        self.assertIsNone(verify_hs256_jwt("only_one_part", self.SECRET))

    def test_tampered_payload_rejected(self):
        token = create_hs256_jwt({"sub": "user1", "role": "user"}, self.SECRET)
        parts = token.split(".")
        import base64

        new_payload = base64.b64encode(b'{"sub":"user1","role":"admin"}').rstrip(b"=").decode()
        tampered = f"{parts[0]}.{new_payload}.{parts[2]}"
        self.assertIsNone(verify_hs256_jwt(tampered, self.SECRET))


class TestS10RevocationList(unittest.TestCase):
    def test_revoke_and_check(self):
        rl = TokenRevocationList()
        rl.revoke("jti-1", time.time() + 3600)
        self.assertTrue(rl.is_revoked("jti-1"))
        self.assertFalse(rl.is_revoked("jti-unknown"))

    def test_purge_expired(self):
        rl = TokenRevocationList()
        rl.revoke("old-jti", time.time() - 1)
        rl.revoke("new-jti", time.time() + 3600)
        purged = rl.purge_expired()
        self.assertEqual(purged, 1)
        self.assertFalse(rl.is_revoked("old-jti"))
        self.assertTrue(rl.is_revoked("new-jti"))

    def test_lru_cap(self):
        rl = TokenRevocationList()
        rl._MAX_ENTRIES = 5
        for i in range(7):
            rl.revoke(f"jti-{i}", time.time() + 3600)
        self.assertLessEqual(len(rl), 5)


class TestS11ScopeEnforcement(unittest.TestCase):
    def test_admin_passes_all(self):
        self.assertTrue(check_scope("/api/v1/users", "DELETE", "admin", []))

    def test_non_admin_blocked_on_admin_path(self):
        self.assertFalse(check_scope("/api/v1/users", "GET", "user", ["read", "write"]))

    def test_write_without_scope_blocked(self):
        self.assertFalse(check_scope("/api/v1/backtest/new", "POST", "user", ["read"]))

    def test_self_service_write_allowed(self):
        self.assertTrue(check_scope("/api/v1/trades/close", "POST", "user", ["read"]))

    def test_read_allowed(self):
        self.assertTrue(check_scope("/api/v1/signals", "GET", "user", ["read"]))


class TestS12RefreshRotation(unittest.TestCase):
    def test_single_use_rotation(self):
        store = RefreshTokenStore()
        token1 = store.issue("user-1")
        token2 = store.rotate(token1)
        self.assertIsNotNone(token2)
        self.assertNotEqual(token1, token2)

    def test_reuse_revokes_family(self):
        store = RefreshTokenStore()
        token1 = store.issue("user-1")
        token2 = store.rotate(token1)
        result = store.rotate(token1)
        self.assertIsNone(result)
        result2 = store.rotate(token2)
        self.assertIsNone(result2)

    def test_unknown_token_rejected(self):
        store = RefreshTokenStore()
        self.assertIsNone(store.rotate("completely-unknown-token"))

    def test_revoke_user(self):
        store = RefreshTokenStore()
        token = store.issue("user-2")
        store.revoke_user("user-2")
        self.assertIsNone(store.rotate(token))


# ============================================================================
# Rate Limit Hardening (S-13..S-16)
# ============================================================================
from rate_limit_patch import (
    BurstAwareLimiter,
    WebSocketRateLimiter,
    extract_real_ip,
)


class TestS14IPExtraction(unittest.TestCase):
    def test_direct_connection(self):
        self.assertEqual(extract_real_ip("1.2.3.4", None), "1.2.3.4")

    def test_private_proxy_trusted(self):
        ip = extract_real_ip("192.168.1.1", "5.6.7.8, 192.168.1.1")
        self.assertEqual(ip, "5.6.7.8")

    def test_public_proxy_xff_ignored(self):
        ip = extract_real_ip("1.2.3.4", "99.99.99.99")
        self.assertEqual(ip, "1.2.3.4")

    def test_x_real_ip_takes_priority(self):
        ip = extract_real_ip("192.168.1.1", "5.6.7.8", real_ip_header="10.0.0.5")
        self.assertEqual(ip, "10.0.0.5")


class TestS15WebSocketLimiter(unittest.TestCase):
    def test_first_connection_allowed(self):
        limiter = WebSocketRateLimiter(max_concurrent=3, max_upgrades=5)
        allowed, _ = run(limiter.can_connect("1.2.3.4"))
        self.assertTrue(allowed)

    def test_max_concurrent_enforced(self):
        limiter = WebSocketRateLimiter(max_concurrent=2, max_upgrades=10)
        run(limiter.can_connect("1.2.3.4"))
        run(limiter.can_connect("1.2.3.4"))
        allowed, _ = run(limiter.can_connect("1.2.3.4"))
        self.assertFalse(allowed)

    def test_disconnect_frees_slot(self):
        limiter = WebSocketRateLimiter(max_concurrent=1, max_upgrades=10)
        run(limiter.can_connect("1.2.3.4"))
        run(limiter.on_disconnect("1.2.3.4"))
        allowed, _ = run(limiter.can_connect("1.2.3.4"))
        self.assertTrue(allowed)


class TestS16BurstLimiter(unittest.TestCase):
    def test_allows_up_to_limit(self):
        limiter = BurstAwareLimiter(max_requests=5, window_s=60)
        results = [limiter.is_allowed() for _ in range(5)]
        self.assertTrue(all(results))

    def test_blocks_over_limit(self):
        limiter = BurstAwareLimiter(max_requests=3, window_s=60, burst_multiplier=1.0)
        for _ in range(3):
            limiter.is_allowed()
        self.assertFalse(limiter.is_allowed())

    def test_remaining_decreases(self):
        limiter = BurstAwareLimiter(max_requests=10, window_s=60)
        for _ in range(3):
            limiter.is_allowed()
        self.assertEqual(limiter.remaining(), 7)


# ============================================================================
# Order State Machine Hardening (S-17..S-20)
# ============================================================================
from order_state_machine_patch import (
    CompletedOrderEvictionIndex,
    SignalIdempotencyGuard,
    StateMachineMetrics,
    dispatch_callbacks_safe,
)


class TestS17SignalIdempotency(unittest.TestCase):
    def test_first_registration_allowed(self):
        guard = SignalIdempotencyGuard()
        ok = run(guard.register("sig-1", "order-1"))
        self.assertTrue(ok)

    def test_duplicate_blocked(self):
        guard = SignalIdempotencyGuard()
        run(guard.register("sig-1", "order-1"))
        ok = run(guard.register("sig-1", "order-2"))
        self.assertFalse(ok)

    def test_release_allows_retry(self):
        guard = SignalIdempotencyGuard()
        run(guard.register("sig-1", "order-1"))
        run(guard.release("sig-1"))
        ok = run(guard.register("sig-1", "order-2"))
        self.assertTrue(ok)

    def test_different_signals_independent(self):
        guard = SignalIdempotencyGuard()
        run(guard.register("sig-A", "order-A"))
        ok = run(guard.register("sig-B", "order-B"))
        self.assertTrue(ok)


class TestS18CallbackIsolation(unittest.TestCase):
    def test_bad_callback_does_not_block_others(self):
        results = []

        def good_cb(*_):
            results.append("good")

        def bad_cb(*_):
            raise RuntimeError("boom")

        def also_good(*_):
            results.append("also_good")

        run(dispatch_callbacks_safe([good_cb, bad_cb, also_good], "arg1"))
        self.assertIn("good", results)
        self.assertIn("also_good", results)

    def test_async_callback_awaited(self):
        results = []

        async def async_cb(*_):
            results.append("async")

        run(dispatch_callbacks_safe([async_cb], "arg"))
        self.assertIn("async", results)


class TestS19EvictionIndex(unittest.TestCase):
    def test_expired_detected(self):
        idx = CompletedOrderEvictionIndex(ttl_hours=0)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        idx.add("order-1", past)
        self.assertIn("order-1", idx.get_expired())

    def test_fresh_not_expired(self):
        idx = CompletedOrderEvictionIndex(ttl_hours=24)
        idx.add("order-new", datetime.now(timezone.utc))
        self.assertNotIn("order-new", idx.get_expired())

    def test_remove_clears_entry(self):
        idx = CompletedOrderEvictionIndex(ttl_hours=0)
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        idx.add("order-x", past)
        idx.remove({"order-x"})
        self.assertNotIn("order-x", idx.get_expired())


class TestS20Metrics(unittest.TestCase):
    def test_active_count_tracking(self):
        m = StateMachineMetrics()
        m.record_created("o1")
        m.record_created("o2")
        self.assertEqual(m.snapshot()["active_orders"], 2)

    def test_terminal_decrements(self):
        m = StateMachineMetrics()
        m.record_created("o1")
        m.record_terminal("o1")
        self.assertEqual(m.snapshot()["active_orders"], 0)

    def test_hung_detection(self):
        m = StateMachineMetrics()
        m._hung_threshold_s = 0.01
        m.record_created("order-hung")
        time.sleep(0.02)
        self.assertIn("order-hung", m.get_hung_orders())

    def test_transition_recording(self):
        m = StateMachineMetrics()
        m.record_transition("PENDING", "SUBMITTED")
        m.record_transition("PENDING", "SUBMITTED")
        self.assertEqual(m.snapshot()["transitions"]["PENDING->SUBMITTED"], 2)


# ============================================================================
# Audit Service Hardening (S-21..S-24)
# ============================================================================
from audit_service_patch import AuditAction, AuditServiceV2


class TestS21AuditActions(unittest.TestCase):
    def test_signal_created_exists(self):
        self.assertEqual(AuditAction.SIGNAL_CREATED.value, "signal_create")

    def test_all_critical_actions_exist(self):
        required = [
            "LOGIN",
            "LOGOUT",
            "TRADE_OPEN",
            "TRADE_CLOSE",
            "SIGNAL_CREATE",
            "SIGNAL_CREATED",
            "DECISION_MADE",
            "RISK_BLOCKED",
            "ADMIN_ACTION",
            "SECURITY_EVENT",
            "CIRCUIT_OPEN",
            "TOKEN_REVOKED",
            "RATE_LIMIT_HIT",
        ]
        for name in required:
            self.assertTrue(hasattr(AuditAction, name), f"Missing: AuditAction.{name}")


class TestS22LogAsync(unittest.TestCase):
    def test_log_async_is_coroutine(self):
        import inspect

        svc = AuditServiceV2()
        result = svc.log_async(AuditAction.LOGIN, user_id="u1")
        self.assertTrue(inspect.iscoroutine(result))
        run(result)

    def test_log_sync_adds_to_buffer(self):
        svc = AuditServiceV2()
        svc.log(AuditAction.TRADE_OPEN, user_id="u1", resource_id="trade-1")
        self.assertEqual(svc.queue_size(), 1)

    def test_log_decision(self):
        svc = AuditServiceV2()
        run(svc.log_decision("u1", "EURUSD", "BUY", 0.85))
        self.assertEqual(svc.queue_size(), 1)


class TestS23FlushRetry(unittest.TestCase):
    def test_buffer_bounded(self):
        svc = AuditServiceV2()
        for i in range(600):
            svc.log(AuditAction.LOGIN, user_id=f"u{i}")
        self.assertLessEqual(svc.queue_size(), 500)


class TestS24ServiceLifecycle(unittest.TestCase):
    def test_start_creates_task(self):
        async def _run():
            svc = AuditServiceV2()
            await svc.start()
            self.assertIsNotNone(svc._task)
            await svc.stop()

        run(_run())

    def test_double_start_idempotent(self):
        async def _run():
            svc = AuditServiceV2()
            await svc.start()
            task1 = svc._task
            await svc.start()
            self.assertIs(svc._task, task1)
            await svc.stop()

        run(_run())


# ============================================================================
# DB Connection Hardening (S-1..S-4)
# ============================================================================
from connection_patch import (
    ConnectionHealth,
    run_with_timeout,
    with_retry,
)


class TestS1DBRetry(unittest.TestCase):
    def test_retries_on_transient_error(self):
        call_count = 0

        @with_retry
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection reset")
            return "ok"

        result = run(flaky())
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 3)

    def test_no_retry_on_logic_error(self):
        call_count = 0

        @with_retry
        async def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            run(bad())
        self.assertEqual(call_count, 1)


class TestS4QueryTimeout(unittest.TestCase):
    def test_timeout_raises(self):
        async def slow():
            await asyncio.sleep(10)

        with self.assertRaises(asyncio.TimeoutError):
            run(run_with_timeout(slow(), timeout=0.1))

    def test_fast_query_passes(self):
        async def fast():
            return 42

        result = run(run_with_timeout(fast(), timeout=5.0))
        self.assertEqual(result, 42)


class TestS2ConnectionHealth(unittest.TestCase):
    def test_mark_ok_healthy(self):
        h = ConnectionHealth()
        h.mark_ok()
        self.assertTrue(h.is_healthy)

    def test_mark_failed_unhealthy(self):
        h = ConnectionHealth()
        h.mark_ok()
        h.mark_failed()
        self.assertFalse(h.is_healthy)

    def test_stale_after_timeout(self):
        h = ConnectionHealth()
        h._last_ok = time.monotonic() - 100
        h._healthy = True
        self.assertFalse(h.is_healthy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
