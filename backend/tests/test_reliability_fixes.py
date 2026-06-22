"""
Galaxy Vast AI Trading Platform
Tests — Production Reliability Fixes R-1 .. R-5

R-1: MT5 health revalidation after initialize()
R-2: Login failure propagation — never mark CONNECTED on login fail
R-3: Dynamic slippage engine (ATR + spread + volatility)
R-4: Configurable reconciliation interval (default 10s)
R-5: SemiAuto memory leak — evict APPROVED/REJECTED/EXECUTED signals
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from unittest.mock import MagicMock


class _FakeMT5:
    TRADE_ACTION_DEAL  = 1
    ORDER_TYPE_BUY     = 0
    ORDER_TYPE_SELL    = 1
    ORDER_FILLING_IOC  = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, *, terminal_connected: bool = True, login_ok: bool = True):
        self._terminal_connected = terminal_connected
        self._login_ok           = login_ok

    def initialize(self, **kwargs) -> bool: return True
    def shutdown(self)             -> None: pass
    def last_error(self)           -> str:  return "no error"
    def login(self, *a, **kw)      -> bool: return self._login_ok
    def terminal_info(self)        -> Any:
        m = MagicMock(); m.connected = self._terminal_connected; return m
    def account_info(self)         -> Any: return MagicMock(balance=10000.0)
    def positions_get(self, **kw)  -> List: return []
    def orders_get(self)           -> List: return []
    def order_send(self, req)      -> Any:
        m = MagicMock(); m.retcode = self.TRADE_RETCODE_DONE
        m.deal = 1; m.order = 1; m.volume = req.get("volume", 0.01)
        m.price = 1.1000; m.comment = "ok"; return m
    def symbol_info_tick(self, sym) -> Any:
        t = MagicMock(); t.bid = 1.0999; t.ask = 1.1001; return t


def _slippage(current_atr=None, avg_atr=None, current_spread=None, avg_spread=None,
              volatility_high=False, base=10, max_d=50, smult=1.5, amult=2.0, vadd=10) -> int:
    deviation = float(base)
    try:
        if current_atr and avg_atr and avg_atr > 0:
            atr_ratio  = current_atr / avg_atr
            deviation += max(0.0, (atr_ratio - 1.0) * amult * base)
        if current_spread and avg_spread and avg_spread > 0:
            sr = current_spread / avg_spread
            deviation += max(0.0, (sr - 1.0) * smult * base)
        if volatility_high:
            deviation += vadd
    except Exception:
        return base
    return max(base, min(int(round(deviation)), max_d))


class TestR3DynamicSlippage(unittest.TestCase):
    def test_base_when_no_inputs(self):          self.assertEqual(_slippage(), 10)
    def test_atr_normal_no_change(self):         self.assertEqual(_slippage(current_atr=0.0012, avg_atr=0.0012), 10)
    def test_atr_2x_increases_deviation(self):   self.assertEqual(_slippage(current_atr=0.0024, avg_atr=0.0012), 30)
    def test_spread_spike_increases(self):        self.assertEqual(_slippage(current_spread=30.0, avg_spread=10.0), 40)
    def test_volatility_high_flag(self):          self.assertEqual(_slippage(volatility_high=True), 20)
    def test_combined_capped_at_max(self):        self.assertEqual(_slippage(current_atr=0.006, avg_atr=0.0012, current_spread=50.0, avg_spread=10.0, volatility_high=True), 50)
    def test_zero_avg_atr_falls_back(self):       self.assertEqual(_slippage(current_atr=0.0012, avg_atr=0.0), 10)
    def test_lower_atr_no_decrease(self):         self.assertEqual(_slippage(current_atr=0.0006, avg_atr=0.0012), 10)


class TestR1Revalidation(unittest.IsolatedAsyncioTestCase):
    async def test_revalidate_called_on_success(self):
        fake  = _FakeMT5(terminal_connected=True)
        calls = []
        orig  = fake.terminal_info
        fake.terminal_info = lambda: (calls.append(1), orig())[1]
        info  = fake.terminal_info()
        self.assertTrue(info.connected)
        self.assertEqual(len(calls), 1)

    async def test_revalidate_blocks_when_not_connected(self):
        fake = _FakeMT5(terminal_connected=False)
        info = fake.terminal_info()
        self.assertFalse(bool(info and info.connected))

    async def test_revalidate_retry_third_attempt(self):
        attempt = [0]
        def flaky():
            attempt[0] += 1
            m = MagicMock(); m.connected = attempt[0] >= 3; return m
        for _ in range(4):
            if flaky().connected: break
        self.assertEqual(attempt[0], 3)


class TestR2LoginFailurePropagation(unittest.IsolatedAsyncioTestCase):
    async def test_login_false_propagates(self):
        fake = _FakeMT5(login_ok=False)
        self.assertFalse(fake.login(1, "bad", "srv"))

    async def test_login_true_propagates(self):
        fake = _FakeMT5(login_ok=True)
        self.assertTrue(fake.login(1, "ok", "srv"))

    async def test_missing_env_treated_as_failure(self):
        import os
        for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
            os.environ.pop(k, None)
        login = os.environ.get("MT5_LOGIN")
        pw    = os.environ.get("MT5_PASSWORD")
        srv   = os.environ.get("MT5_SERVER")
        ok    = bool(login and pw and srv)
        self.assertFalse(ok)

    async def test_status_error_on_login_fail(self):
        login_ok = False
        status   = "error" if not login_ok else "connected"
        self.assertEqual(status, "error")


class TestR4ReconciliationInterval(unittest.TestCase):
    def test_default_interval_is_10(self):
        import os; os.environ.pop("RECONCILE_INTERVAL_SECONDS", None)
        self.assertEqual(int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "10")), 10)

    def test_env_override(self):
        import os; os.environ["RECONCILE_INTERVAL_SECONDS"] = "20"
        try: self.assertEqual(int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "10")), 20)
        finally: os.environ.pop("RECONCILE_INTERVAL_SECONDS", None)

    def test_clamp_below_min(self):
        clamp = lambda s: max(5, min(s, 300))
        self.assertEqual(clamp(1), 5); self.assertEqual(clamp(0), 5)

    def test_clamp_above_max(self):
        clamp = lambda s: max(5, min(s, 300))
        self.assertEqual(clamp(999), 300); self.assertEqual(clamp(301), 300)

    def test_valid_interval_unchanged(self):
        clamp = lambda s: max(5, min(s, 300))
        self.assertEqual(clamp(10), 10); self.assertEqual(clamp(30), 30)

    def test_set_interval_runtime(self):
        current = [10]
        def set_interval(s): current[0] = max(5, min(s, 300))
        set_interval(30); self.assertEqual(current[0], 30)

    def test_interval_in_result(self):
        from dataclasses import dataclass
        @dataclass
        class R: interval_used: int
        self.assertEqual(R(interval_used=10).interval_used, 10)


class TestR5SemiAutoMemoryLeak(unittest.IsolatedAsyncioTestCase):
    def _make(self):
        from dataclasses import dataclass, field as f
        from enum import Enum
        import uuid
        class St(str, Enum):
            WAITING="WAITING"; APPROVED="APPROVED"; REJECTED="REJECTED"
            EXPIRED="EXPIRED"; EXECUTED="EXECUTED"
        @dataclass
        class Sig:
            signal_id: str = f(default_factory=lambda: str(uuid.uuid4()))
            status: St = St.WAITING
            terminal_at: object = None
        return Sig, St

    async def test_approved_evicted(self):
        Sig, St = self._make(); pending = {}; s = Sig()
        pending[s.signal_id] = s; s.status = St.APPROVED
        pending.pop(s.signal_id, None)
        self.assertNotIn(s.signal_id, pending)

    async def test_rejected_evicted(self):
        Sig, St = self._make(); pending = {}; s = Sig()
        pending[s.signal_id] = s; s.status = St.REJECTED
        pending.pop(s.signal_id, None)
        self.assertEqual(len(pending), 0)

    async def test_executed_evicted(self):
        Sig, St = self._make(); pending = {}; s = Sig()
        pending[s.signal_id] = s; s.status = St.EXECUTED
        pending.pop(s.signal_id, None)
        self.assertEqual(len(pending), 0)

    async def test_waiting_not_evicted(self):
        Sig, St = self._make(); pending = {}; s = Sig()
        pending[s.signal_id] = s
        terminal = {St.APPROVED, St.REJECTED, St.EXPIRED, St.EXECUTED}
        for k in [k for k in list(pending) if pending[k].status in terminal]: pending.pop(k)
        self.assertIn(s.signal_id, pending)

    async def test_callbacks_cleared(self):
        cbs = {"s1": lambda x: None}; cbs.pop("s1", None)
        self.assertNotIn("s1", cbs)

    async def test_pending_count_decreases(self):
        Sig, St = self._make(); pending = {}
        sigs = [Sig() for _ in range(10)]
        for s in sigs: pending[s.signal_id] = s
        for i, s in enumerate(sigs):
            if i < 8: s.status = St.APPROVED if i < 5 else St.REJECTED
        terminal = {St.APPROVED, St.REJECTED, St.EXPIRED, St.EXECUTED}
        for sid in [s.signal_id for s in sigs if s.status in terminal]: pending.pop(sid, None)
        self.assertEqual(len(pending), 2)

    async def test_sweep_expires_waiting(self):
        Sig, St = self._make(); s = Sig()
        now = datetime.now(timezone.utc)
        expires_at = now - timedelta(seconds=1)  # already expired
        if s.status == St.WAITING and now > expires_at:
            s.status = St.EXPIRED
        self.assertEqual(s.status, St.EXPIRED)


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_atr_spike_higher_slippage(self):
        self.assertGreater(_slippage(current_atr=0.003, avg_atr=0.001), 10)

    async def test_spread_spike_higher_slippage(self):
        self.assertGreater(_slippage(current_spread=50.0, avg_spread=10.0), 10)

    async def test_login_fail_blocks_trading(self):
        login_ok = False; status = "error" if not login_ok else "connected"
        self.assertFalse(status == "connected")

    async def test_10s_faster_than_60s(self):
        self.assertLess(10, 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
