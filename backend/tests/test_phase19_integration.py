"""
Phase 19 — Final Integration & Smoke Tests
144 tests covering:
- End-to-end flows (auth → billing → license → EA → signal → trade)
- Cross-phase regression guard
- Production readiness gate
- Duplicate signal / timeout / reconciliation / invalid webhook / expired license
- Concurrent safety
- Smoke test suite
"""

from __future__ import annotations

import sys
import time
import uuid

import pytest

sys.path.insert(0, "/home/definable/phase19")
sys.path.insert(0, "/home/definable/phase19/backend")

from core.integration_harness import (
    _TEST_SECRET,
    AuthContext,
    BillingEngine,
    E2EFlowSimulator,
    KillSwitch,
    KillSwitchActivatedError,
    License,
    LicenseState,
    Position,
    ProductionReadinessGate,
    ReconciliationEngine,
    RegressionGuard,
    SignalService,
    SmokeTestSuite,
    SubStatus,
    TradeRegistry,
    make_jwt,
    verify_jwt,
)


class TestJWTIntegration:
    def _sim(self):
        return E2EFlowSimulator()

    def test_T001_issue_and_verify(self):
        sim = self._sim()
        tok = sim.issue_token("u1")
        payload = sim.verify_token(tok)
        assert payload is not None
        assert payload["sub"] == "u1"

    def test_T002_expired_token_rejected(self):
        sim = self._sim()
        tok = sim.issue_token("u1", exp_offset=-1)
        time.sleep(0.01)
        assert sim.verify_token(tok) is None

    def test_T003_tampered_token_rejected(self):
        sim = self._sim()
        tok = sim.issue_token("u1")
        parts = tok.split(".")
        parts[1] = parts[1][:-2] + "AA"
        assert sim.verify_token(".".join(parts)) is None

    def test_T004_wrong_secret_rejected(self):
        tok = make_jwt({"sub": "u1", "exp": int(time.time()) + 3600}, "wrong-secret")
        assert verify_jwt(tok, _TEST_SECRET) is None

    def test_T005_alg_none_rejected(self):
        import base64
        import json

        hdr = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        pld = base64.urlsafe_b64encode(json.dumps({"sub": "u1"}).encode()).rstrip(b"=").decode()
        tok = f"{hdr}.{pld}."
        assert verify_jwt(tok, _TEST_SECRET) is None

    def test_T006_role_customer_in_payload(self):
        sim = self._sim()
        tok = sim.issue_token("u1", role="customer")
        p = sim.verify_token(tok)
        assert p["role"] == "customer"

    def test_T007_role_admin_in_payload(self):
        sim = self._sim()
        tok = sim.issue_token("u1", role="admin")
        p = sim.verify_token(tok)
        assert p["role"] == "admin"

    def test_T008_jti_unique_per_token(self):
        sim = self._sim()
        t1 = sim.verify_token(sim.issue_token("u1"))
        t2 = sim.verify_token(sim.issue_token("u1"))
        assert t1["jti"] != t2["jti"]

    def test_T009_missing_parts_rejected(self):
        assert verify_jwt("only.two", _TEST_SECRET) is None

    def test_T010_empty_token_rejected(self):
        assert verify_jwt("", _TEST_SECRET) is None

    def test_T011_auth_context_customer_perms(self):
        ctx = AuthContext(user_id="u1", role="customer")
        assert ctx.has_perm("read:own")
        assert ctx.has_perm("write:own")
        assert not ctx.has_perm("read:any")

    def test_T012_auth_context_admin_all_perms(self):
        ctx = AuthContext(user_id="u1", role="admin")
        assert ctx.has_perm("admin:action")
        assert ctx.has_perm("revoke:license")

    def test_T013_blocked_user_no_perms(self):
        ctx = AuthContext(user_id="u1", role="admin", is_blocked=True)
        assert not ctx.has_perm("admin:action")

    def test_T014_inactive_user_no_perms(self):
        ctx = AuthContext(user_id="u1", role="customer", is_active=False)
        assert not ctx.has_perm("read:own")

    def test_T015_assert_owns_self(self):
        ctx = AuthContext(user_id="u1")
        ctx.assert_owns("u1")

    def test_T016_assert_owns_other_denied(self):
        ctx = AuthContext(user_id="u1", role="customer")
        with pytest.raises(PermissionError):
            ctx.assert_owns("u2")


class TestBillingIntegration:
    def _eng(self):
        return BillingEngine()

    def test_T017_checkout_creates_sub(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        assert sub.status == SubStatus.ACTIVE
        assert sub.user_id == "u1"

    def test_T018_trial_plan_status(self):
        e = self._eng()
        sub = e.checkout("u1", "trial")
        assert sub.status == SubStatus.TRIAL

    def test_T019_duplicate_active_sub_blocked(self):
        e = self._eng()
        e.checkout("u1", "pro")
        with pytest.raises(ValueError, match="already has active"):
            e.checkout("u1", "basic")

    def test_T020_unknown_plan_rejected(self):
        e = self._eng()
        with pytest.raises(ValueError, match="Unknown plan"):
            e.checkout("u1", "enterprise_gold")

    def test_T021_webhook_payment_succeeded(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        r = e.process_webhook("stripe", "pi_001", "payment_succeeded", sub.sub_id)
        assert r["status"] == "processed"

    def test_T022_webhook_idempotency(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        r1 = e.process_webhook("stripe", "pi_001", "payment_succeeded", sub.sub_id)
        r2 = e.process_webhook("stripe", "pi_001", "payment_succeeded", sub.sub_id)
        assert r1["status"] == "processed"
        assert r2["status"] == "duplicate"

    def test_T023_invalid_webhook_no_crash(self):
        e = self._eng()
        r = e.process_webhook("stripe", "pi_999", "payment_succeeded", "nonexistent")
        assert r["status"] == "processed"

    def test_T024_dunning_3_moves_to_past_due(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        for i in range(3):
            e.process_webhook("stripe", f"pi_fail_{i}", "payment_failed", sub.sub_id)
        assert sub.status == SubStatus.PAST_DUE

    def test_T025_cancel_moves_to_canceled(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        e.cancel(sub.sub_id)
        assert sub.status == SubStatus.CANCELED
        assert sub.is_terminal

    def test_T026_audit_log_recorded(self):
        e = self._eng()
        e.checkout("u1", "pro")
        audit = e.get_audit()
        assert any(a["event"] == "checkout" for a in audit)

    def test_T027_two_users_independent(self):
        e = self._eng()
        s1 = e.checkout("u1", "pro")
        s2 = e.checkout("u2", "basic")
        assert s1.sub_id != s2.sub_id

    def test_T028_is_active_property(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        assert sub.is_active is True

    def test_T029_is_terminal_false_for_active(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        assert sub.is_terminal is False

    def test_T030_invoice_ids_appended(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        e.process_webhook("stripe", "pi_A", "payment_succeeded", sub.sub_id)
        assert len(sub.invoice_ids) == 1

    def test_T031_multiple_plans_available(self):
        for plan in ("trial", "basic", "pro", "vip", "annual"):
            eng2 = BillingEngine()
            sub = eng2.checkout("u1", plan)
            assert sub.plan == plan

    def test_T032_double_invoice_no_double_append(self):
        e = self._eng()
        sub = e.checkout("u1", "pro")
        e.process_webhook("stripe", "pi_A", "payment_succeeded", sub.sub_id)
        e.process_webhook("stripe", "pi_A", "payment_succeeded", sub.sub_id)
        assert len(sub.invoice_ids) == 1


class TestLicenseLifecycle:
    def _make(self, user_id="u1", max_devices=1) -> License:
        return License(
            license_id=f"lic_{uuid.uuid4().hex[:6]}",
            user_id=user_id,
            plan="pro",
            max_devices=max_devices,
        )

    def test_T033_pending_not_active(self):
        assert not self._make().is_active()

    def test_T034_activate_sets_active(self):
        lic = self._make()
        lic.activate(86400.0)
        assert lic.is_active()
        assert lic.status == LicenseState.ACTIVE

    def test_T035_expired_license_not_active(self):
        lic = self._make()
        lic.activate(expires_in=0.001)
        time.sleep(0.01)
        assert not lic.is_active()

    def test_T036_revoked_license_not_active(self):
        lic = self._make()
        lic.activate()
        lic.revoke()
        assert not lic.is_active()
        assert lic.status == LicenseState.REVOKED

    def test_T037_suspended_license_not_active(self):
        lic = self._make()
        lic.activate()
        lic.suspend()
        assert not lic.is_active()

    def test_T038_heartbeat_ok_when_active(self):
        lic = self._make()
        lic.activate()
        assert lic.record_heartbeat("dev001")

    def test_T039_heartbeat_fails_when_inactive(self):
        assert not self._make().record_heartbeat("dev001")

    def test_T040_device_limit_enforced(self):
        lic = self._make(max_devices=1)
        lic.activate()
        assert lic.record_heartbeat("dev001")
        assert not lic.record_heartbeat("dev002")

    def test_T041_multi_device_license(self):
        lic = self._make(max_devices=3)
        lic.activate()
        assert lic.record_heartbeat("dev001")
        assert lic.record_heartbeat("dev002")
        assert lic.record_heartbeat("dev003")
        assert not lic.record_heartbeat("dev004")

    def test_T042_heartbeat_age_increases(self):
        lic = self._make()
        lic.activate()
        lic.record_heartbeat("dev001")
        assert lic.heartbeat_age() >= 0.0

    def test_T043_no_heartbeat_age_infinite(self):
        assert self._make().heartbeat_age() == float("inf")

    def test_T044_key_hash_not_empty(self):
        import hashlib

        lic = self._make()
        lic.key_hash = hashlib.sha256(b"test").hexdigest()
        assert len(lic.key_hash) == 64

    def test_T045_pending_state_initial(self):
        assert self._make().status == LicenseState.PENDING

    def test_T046_repeated_heartbeat_same_device_ok(self):
        lic = self._make()
        lic.activate()
        assert lic.record_heartbeat("dev001")
        assert lic.record_heartbeat("dev001")
        assert len(lic.device_ids) == 1

    def test_T047_revoke_reason_accepted(self):
        lic = self._make()
        lic.activate()
        lic.revoke(reason="non_payment")
        assert lic.status == LicenseState.REVOKED

    def test_T048_license_created_via_simulator(self):
        sim = E2EFlowSimulator()
        lic = sim.create_license("u1", "pro")
        assert lic.key_hash != ""
        assert lic.status == LicenseState.PENDING


class TestSignalService:
    def _svc(self):
        return SignalService()

    def test_T049_emit_buy_signal(self):
        sig = self._svc().emit("u1", "EURUSD", "BUY")
        assert sig is not None and sig.direction == "BUY"

    def test_T050_emit_sell_signal(self):
        assert self._svc().emit("u1", "EURUSD", "SELL") is not None

    def test_T051_duplicate_signal_returns_none(self):
        svc = self._svc()
        assert svc.emit("u1", "EURUSD", "BUY") is not None
        assert svc.emit("u1", "EURUSD", "BUY") is None

    def test_T052_different_direction_not_duplicate(self):
        svc = self._svc()
        assert svc.emit("u1", "EURUSD", "BUY") is not None
        assert svc.emit("u1", "EURUSD", "SELL") is not None

    def test_T053_different_symbol_not_duplicate(self):
        svc = self._svc()
        assert svc.emit("u1", "EURUSD", "BUY") is not None
        assert svc.emit("u1", "GBPUSD", "BUY") is not None

    def test_T054_cross_user_not_duplicate(self):
        svc = self._svc()
        assert svc.emit("u1", "EURUSD", "BUY") is not None
        assert svc.emit("u2", "EURUSD", "BUY") is not None

    def test_T055_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            self._svc().emit("u1", "EURUSD", "HOLD")

    def test_T056_direction_case_insensitive(self):
        sig = self._svc().emit("u1", "EURUSD", "buy")
        assert sig.direction == "BUY"

    def test_T057_expired_signal_not_returned(self):
        svc = self._svc()
        sig = svc.emit("u1", "EURUSD", "BUY", expires_in=0.001)
        time.sleep(0.01)
        assert sig not in svc.get_signals("u1")

    def test_T058_active_signal_returned(self):
        svc = self._svc()
        sig = svc.emit("u1", "EURUSD", "BUY", expires_in=300.0)
        assert sig in svc.get_signals("u1")

    def test_T059_kill_switch_blocks_signal(self):
        sim = E2EFlowSimulator()
        sim.kill_sw.activate("test_block", "test")
        assert sim.emit_signal("u1", "EURUSD", "BUY") is None

    def test_T060_kill_switch_event_logged(self):
        sim = E2EFlowSimulator()
        sim.kill_sw.activate("test_block", "test")
        sim.emit_signal("u1", "EURUSD", "BUY")
        assert "signal_blocked" in sim.event_types()

    def test_T061_signal_id_unique(self):
        svc = self._svc()
        s1 = svc.emit("u1", "EURUSD", "BUY")
        s2 = svc.emit("u1", "GBPUSD", "BUY")
        assert s1.signal_id != s2.signal_id

    def test_T062_get_signals_user_isolated(self):
        svc = self._svc()
        svc.emit("u1", "EURUSD", "BUY")
        svc.emit("u2", "GBPUSD", "SELL")
        assert all(s.user_id == "u1" for s in svc.get_signals("u1"))

    def test_T063_signal_has_generated_at(self):
        sig = self._svc().emit("u1", "EURUSD", "BUY")
        assert sig.generated_at > 0

    def test_T064_signal_not_expired_immediately(self):
        sig = self._svc().emit("u1", "EURUSD", "BUY", expires_in=300.0)
        assert not sig.is_expired()


class TestTradeRegistry:
    def _reg(self):
        return TradeRegistry()

    def test_T065_insert_trade(self):
        t = self._reg().insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        assert t.trade_id.startswith("trd_")

    def test_T066_idempotency_same_key(self):
        reg = self._reg()
        t1 = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        t2 = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        assert t1.trade_id == t2.trade_id

    def test_T067_duplicate_mt5_ticket_blocked(self):
        reg = self._reg()
        reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001", mt5_ticket=12345)
        with pytest.raises(ValueError, match="Duplicate MT5 ticket"):
            reg.insert("u1", "EURUSD", "SELL", 0.1, "idem_002", mt5_ticket=12345)

    def test_T068_different_user_same_ticket_ok(self):
        reg = self._reg()
        reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001", mt5_ticket=12345)
        t2 = reg.insert("u2", "EURUSD", "BUY", 0.1, "idem_002", mt5_ticket=12345)
        assert t2 is not None

    def test_T069_kill_switch_blocks_trade(self):
        sim = E2EFlowSimulator()
        sim.kill_sw.activate("test")
        with pytest.raises(KillSwitchActivatedError):
            sim.insert_trade("u1", "EURUSD", "BUY", 0.1, "idem_001")

    def test_T070_trade_status_open(self):
        assert self._reg().insert("u1", "EURUSD", "BUY", 0.1, "idem_001").status == "open"

    def test_T071_trade_get_by_id(self):
        reg = self._reg()
        t = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        assert reg.get(t.trade_id) is t

    def test_T072_trade_get_missing_returns_none(self):
        assert self._reg().get("nonexistent") is None

    def test_T073_lot_size_preserved(self):
        t = self._reg().insert("u1", "EURUSD", "BUY", 0.23, "idem_001")
        assert abs(t.lot_size - 0.23) < 0.0001

    def test_T074_direction_preserved(self):
        assert self._reg().insert("u1", "EURUSD", "SELL", 0.1, "idem_001").direction == "SELL"

    def test_T075_opened_at_set(self):
        assert self._reg().insert("u1", "EURUSD", "BUY", 0.1, "idem_001").opened_at > 0

    def test_T076_multiple_trades_unique_ids(self):
        reg = self._reg()
        t1 = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        t2 = reg.insert("u1", "GBPUSD", "SELL", 0.2, "idem_002")
        assert t1.trade_id != t2.trade_id

    def test_T077_no_ticket_trade_ok(self):
        t = self._reg().insert("u1", "EURUSD", "BUY", 0.1, "idem_001", mt5_ticket=None)
        assert t.mt5_ticket is None

    def test_T078_two_ticketless_trades_ok(self):
        reg = self._reg()
        t1 = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_001")
        t2 = reg.insert("u1", "EURUSD", "BUY", 0.1, "idem_002")
        assert t1.trade_id != t2.trade_id

    def test_T079_idempotency_key_stored(self):
        t = self._reg().insert("u1", "EURUSD", "BUY", 0.1, "my_idem_key")
        assert t.idempotency_key == "my_idem_key"

    def test_T080_concurrent_idempotency(self):
        import threading

        reg = self._reg()
        results = []

        def worker():
            t = reg.insert("u1", "EURUSD", "BUY", 0.1, "shared_idem")
            results.append(t.trade_id)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert len(set(results)) == 1


class TestKillSwitch:
    def _ks(self):
        return KillSwitch(max_drawdown_pct=10.0, equity_floor_usd=500.0)

    def test_T081_inactive_by_default(self):
        assert not self._ks().is_active

    def test_T082_check_ok_when_inactive(self):
        self._ks().check()

    def test_T083_activate_manual(self):
        ks = self._ks()
        ks.activate("manual_test")
        assert ks.is_active

    def test_T084_check_raises_when_active(self):
        ks = self._ks()
        ks.activate("reason")
        with pytest.raises(KillSwitchActivatedError):
            ks.check()

    def test_T085_equity_floor_triggers(self):
        ks = self._ks()
        assert ks.update_equity(400.0)
        assert ks.is_active

    def test_T086_drawdown_10pct_triggers(self):
        ks = self._ks()
        ks.update_equity(1000.0)
        assert ks.update_equity(890.0)
        assert ks.is_active

    def test_T087_drawdown_below_threshold_no_trigger(self):
        ks = self._ks()
        ks.update_equity(1000.0)
        assert not ks.update_equity(950.0)
        assert not ks.is_active

    def test_T088_callback_fired_on_activate(self):
        ks = self._ks()
        fired = []
        ks.add_callback(lambda r, a: fired.append(r))
        ks.activate("cb_test")
        assert "cb_test" in fired

    def test_T089_reset_with_correct_token(self):
        ks = self._ks()
        ks.set_reset_token("valid_token_32chars_minimum_lengt")
        ks.activate("test")
        assert ks.reset("valid_token_32chars_minimum_lengt") is True
        assert not ks.is_active

    def test_T090_reset_wrong_token_fails(self):
        ks = self._ks()
        ks.set_reset_token("correct_token_32chars_minimum_len")
        ks.activate("test")
        assert ks.reset("wrong_token") is False
        assert ks.is_active

    def test_T091_reason_preserved(self):
        ks = self._ks()
        ks.activate("specific_reason_here")
        assert ks.reason == "specific_reason_here"

    def test_T092_peak_equity_tracked(self):
        ks = self._ks()
        ks.update_equity(1000.0)
        ks.update_equity(1200.0)
        assert ks._peak_equity == 1200.0

    def test_T093_peak_equity_not_decrease(self):
        ks = self._ks()
        ks.update_equity(1000.0)
        ks.update_equity(800.0)
        assert ks._peak_equity == 1000.0

    def test_T094_multiple_callbacks(self):
        ks = self._ks()
        count = [0]
        ks.add_callback(lambda r, a: count.__setitem__(0, count[0] + 1))
        ks.add_callback(lambda r, a: count.__setitem__(0, count[0] + 1))
        ks.activate("test")
        assert count[0] == 2

    def test_T095_equity_floor_reason_in_message(self):
        ks = self._ks()
        ks.update_equity(300.0)
        assert "equity_floor" in ks.reason

    def test_T096_drawdown_reason_in_message(self):
        ks = self._ks()
        ks.update_equity(1000.0)
        ks.update_equity(850.0)
        assert "drawdown" in ks.reason


class TestReconciliation:
    def _eng(self):
        return ReconciliationEngine()

    def test_T097_clean_reconciliation(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.1, "long")])
        assert len(mm) == 0

    def test_T098_mismatch_detected(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.2, "long")])
        assert len(mm) == 1 and mm[0]["type"] == "mismatch"

    def test_T099_ghost_position_detected(self):
        eng = self._eng()
        mm = eng.reconcile([], [Position("GBPUSD", 0.1, "long")])
        assert any(m["type"] == "ghost" for m in mm)

    def test_T100_missing_position_detected(self):
        eng = self._eng()
        mm = eng.reconcile([Position("GBPUSD", 0.1, "long")], [])
        assert any(m["type"] == "missing" for m in mm)

    def test_T101_side_mismatch_detected(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.1, "short")])
        assert len(mm) == 1

    def test_T102_multiple_symbols(self):
        eng = self._eng()
        mm = eng.reconcile(
            [Position("EURUSD", 0.1, "long"), Position("GBPUSD", 0.2, "short")],
            [Position("EURUSD", 0.1, "long"), Position("USDJPY", 0.3, "long")],
        )
        assert len(mm) >= 2

    def test_T103_history_accumulated(self):
        eng = self._eng()
        eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.2, "long")])
        eng.reconcile([Position("GBPUSD", 0.1, "long")], [Position("GBPUSD", 0.2, "long")])
        assert len(eng.history()) == 2

    def test_T104_mismatch_has_symbol(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.2, "long")])
        assert mm[0]["symbol"] == "EURUSD"

    def test_T105_broker_qty_in_mismatch(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.3, "long")])
        assert abs(mm[0]["broker_qty"] - 0.3) < 0.001

    def test_T106_local_qty_in_mismatch(self):
        eng = self._eng()
        mm = eng.reconcile([Position("EURUSD", 0.1, "long")], [Position("EURUSD", 0.3, "long")])
        assert abs(mm[0]["local_qty"] - 0.1) < 0.001

    def test_T107_small_diff_tolerance(self):
        eng = self._eng()
        mm = eng.reconcile(
            [Position("EURUSD", 0.1000, "long")], [Position("EURUSD", 0.1005, "long")]
        )
        assert len(mm) == 0

    def test_T108_simulator_reconcile(self):
        sim = E2EFlowSimulator()
        mm = sim.run_reconciliation(
            [Position("EURUSD", 0.1, "long")],
            [Position("EURUSD", 0.2, "long")],
        )
        assert len(mm) == 1
        assert "reconciliation" in sim.event_types()


class TestProductionReadinessGate:
    def _gate(self, overrides=None):
        cfg = {
            "JWT_SECRET_KEY": "A" * 32,
            "ALLOWED_ORIGINS": "https://app.example.com",
            "ENVIRONMENT": "production",
            "FORCE_HTTPS": True,
            "SECRETS_MASTER_KEY": "B" * 32,
            "FIELD_ENCRYPTION_KEY": "C" * 32,
            "DEBUG": False,
            "HSTS_ENABLED": True,
        }
        if overrides:
            cfg.update(overrides)
        return ProductionReadinessGate(cfg)

    def test_T109_all_good_passes(self):
        r = self._gate().run()
        assert r.passed, f"Failures: {r.failures}"

    def test_T110_short_jwt_fails(self):
        assert not self._gate({"JWT_SECRET_KEY": "short"}).run().passed

    def test_T111_weak_jwt_fails(self):
        assert not self._gate({"JWT_SECRET_KEY": "changeme"}).run().passed

    def test_T112_wildcard_cors_in_production_fails(self):
        r = self._gate({"ALLOWED_ORIGINS": "*"}).run()
        assert not r.passed

    def test_T113_missing_master_key_fails(self):
        assert not self._gate({"SECRETS_MASTER_KEY": ""}).run().passed

    def test_T114_missing_field_enc_key_fails(self):
        assert not self._gate({"FIELD_ENCRYPTION_KEY": ""}).run().passed

    def test_T115_debug_in_production_fails(self):
        assert not self._gate({"DEBUG": True}).run().passed

    def test_T116_no_hsts_in_production_fails(self):
        assert not self._gate({"HSTS_ENABLED": False}).run().passed

    def test_T117_dev_environment_relaxed(self):
        r = ProductionReadinessGate(
            {
                "JWT_SECRET_KEY": "A" * 32,
                "ENVIRONMENT": "development",
                "SECRETS_MASTER_KEY": "B" * 32,
                "FIELD_ENCRYPTION_KEY": "C" * 32,
                "ALLOWED_ORIGINS": "*",
            }
        ).run()
        assert r.passed

    def test_T118_checks_dict_populated(self):
        assert len(self._gate().run().checks) > 0

    def test_T119_failures_list_empty_when_pass(self):
        assert self._gate().run().failures == []

    def test_T120_failures_list_populated_when_fail(self):
        assert len(self._gate({"JWT_SECRET_KEY": "x"}).run().failures) > 0


class TestE2EFlowSimulator:
    def test_T121_full_lifecycle_events(self):
        sim = E2EFlowSimulator()
        uid = f"u_{uuid.uuid4().hex[:6]}"
        sub = sim.checkout(uid, "pro")
        sim.webhook("stripe", "pi_001", "payment_succeeded", sub.sub_id)
        lic = sim.create_license(uid, "pro")
        sim.activate_license(lic.license_id)
        sim.heartbeat(lic.license_id, "dev001")
        sim.emit_signal(uid, "EURUSD", "BUY")
        sim.insert_trade(uid, "EURUSD", "BUY", 0.1, "idem_001")
        types = sim.event_types()
        for expected in [
            "checkout",
            "webhook",
            "license_created",
            "license_activated",
            "heartbeat",
            "signal_emitted",
            "trade_inserted",
        ]:
            assert expected in types

    def test_T122_duplicate_signal_logged(self):
        sim = E2EFlowSimulator()
        sim.emit_signal("u1", "EURUSD", "BUY")
        sim.emit_signal("u1", "EURUSD", "BUY")
        assert "signal_duplicate" in sim.event_types()

    def test_T123_equity_drawdown_triggers_ks(self):
        sim = E2EFlowSimulator()
        sim.update_equity(1000.0)
        sim.update_equity(800.0)
        assert sim.kill_sw.is_active
        assert "kill_switch_auto" in sim.event_types()

    def test_T124_reconciliation_mismatch_logged(self):
        sim = E2EFlowSimulator()
        sim.run_reconciliation(
            [Position("EURUSD", 0.1, "long")],
            [Position("EURUSD", 0.5, "long")],
        )
        assert "reconciliation" in sim.event_types()

    def test_T125_two_users_isolated(self):
        sim = E2EFlowSimulator()
        sim.checkout("u1", "pro")
        with pytest.raises(ValueError):
            sim.checkout("u1", "basic")
        sub2 = sim.checkout("u2", "basic")
        assert sub2.user_id == "u2"

    def test_T126_expired_license_heartbeat_fails(self):
        sim = E2EFlowSimulator()
        lic = sim.create_license("u1")
        sim.activate_license(lic.license_id, expires_in=0.001)
        time.sleep(0.02)
        assert not sim.heartbeat(lic.license_id, "dev001")

    def test_T127_signal_blocked_after_ks(self):
        sim = E2EFlowSimulator()
        sim.kill_sw.activate("manual")
        assert sim.emit_signal("u1", "EURUSD", "BUY") is None

    def test_T128_trade_blocked_after_ks(self):
        sim = E2EFlowSimulator()
        sim.kill_sw.activate("manual")
        with pytest.raises(KillSwitchActivatedError):
            sim.insert_trade("u1", "EURUSD", "BUY", 0.1, "idem")

    def test_T129_events_snapshot(self):
        sim = E2EFlowSimulator()
        sim.checkout("u1", "pro")
        events = sim.events()
        assert isinstance(events, list)
        assert events[0]["event"] == "checkout"

    def test_T130_webhook_duplicate_no_double_invoice(self):
        sim = E2EFlowSimulator()
        sub = sim.checkout("u1", "pro")
        r1 = sim.webhook("stripe", "pi_X", "payment_succeeded", sub.sub_id)
        r2 = sim.webhook("stripe", "pi_X", "payment_succeeded", sub.sub_id)
        assert r1["status"] == "processed"
        assert r2["status"] == "duplicate"

    def test_T131_reconciliation_history(self):
        sim = E2EFlowSimulator()
        sim.run_reconciliation([], [Position("EURUSD", 0.1, "long")])
        assert len(sim.reconcile.history()) == 1

    def test_T132_signal_not_expired_immediately(self):
        sim = E2EFlowSimulator()
        sig = sim.emit_signal("u1", "EURUSD", "BUY")
        assert sig is not None and not sig.is_expired()


class TestSmokeTestSuite:
    def test_T133_all_smoke_tests_pass(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        results = suite.run_all()
        failed = [r for r in results if not r.passed]
        assert not failed, f"Smoke failures: {[r.name + ': ' + r.error for r in failed]}"

    def test_T134_summary_has_all_fields(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        suite.run_all()
        s = suite.summary()
        for k in ("total", "passed", "failed", "pass_rate", "avg_latency_ms"):
            assert k in s

    def test_T135_pass_rate_100(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        suite.run_all()
        assert suite.summary()["pass_rate"] == 1.0

    def test_T136_latency_ms_positive(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        suite.run_all()
        assert suite.summary()["avg_latency_ms"] >= 0.0

    def test_T137_smoke_result_has_name(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        results = suite.run_all()
        assert all(r.name for r in results)

    def test_T138_smoke_result_has_latency(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        results = suite.run_all()
        assert all(r.latency_ms >= 0 for r in results)

    def test_T139_smoke_covers_jwt(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        results = suite.run_all()
        assert any("jwt" in r.name for r in results)

    def test_T140_smoke_covers_trade(self):
        sim = E2EFlowSimulator()
        suite = SmokeTestSuite(sim)
        results = suite.run_all()
        assert any("trade" in r.name for r in results)


class TestRegressionGuard:
    def test_T141_phase16_kill_switch_api(self):
        assert RegressionGuard.check_phase16_kill_switch(), "Phase 16 KillSwitch API broken"

    def test_T142_phase13_db_migration_exists(self):
        assert RegressionGuard.check_phase13_db_migration(), "Phase 13 DB migration missing"

    def test_T143_phase18_docs_complete(self):
        assert RegressionGuard.check_phase18_docs(), "Phase 18 docs missing or too small"

    def test_T144_run_all_returns_dict(self):
        guard = RegressionGuard()
        results = guard.run_all()
        assert isinstance(results, dict)
        assert results["phase16_kill_switch"]
        assert results["phase18_docs"]
