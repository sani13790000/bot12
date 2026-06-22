"""
Galaxy Vast AI Trading Platform
Unit Tests -- 5 Critical Fixes

FIX-1: Duplicate Order after Retry (idempotency + reconciliation before retry)
FIX-2: Retry Queue Race Condition (asyncio.Queue)
FIX-3: Unknown Symbol Pip Value Risk (UnknownSymbolError)
FIX-4: Static Correlation -> Rolling engine
FIX-5: Auto-close Orphan -> Alert + Manual Review

Run: pytest backend/tests/test_critical_fixes.py -v
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# =============================================================================
# HELPERS -- lightweight stubs
# =============================================================================

@dataclass
class _FakePosition:
    ticket: int
    symbol: str
    type:   int   = 0
    volume: float = 0.01
    price_open: float = 1.0
    profit: float = 0.0


@dataclass
class _FakeOrderResult:
    success:  bool
    order:    int   = 0
    deal:     int   = 0
    volume:   float = 0.0
    price:    float = 0.0
    error:    str   = ""
    retcode:  int   = 0


class _FakeMT5:
    def __init__(self, positions=None, order_result=None, account_balance=10_000.0):
        self._positions    = positions or []
        self._order_result = order_result or _FakeOrderResult(success=True, order=12345, price=1.0850, volume=0.01)
        self._balance      = account_balance

    async def initialize(self):         pass
    async def shutdown(self):           pass
    async def get_positions(self):      return self._positions
    async def get_account_info(self):
        info = MagicMock()
        info.balance = self._balance
        info.equity  = self._balance
        return info
    async def send_order(self, req):    return self._order_result
    async def close_position(self, t):  return {"success": True, "ticket": t}
    async def get_symbol_info(self, sym):
        info = MagicMock()
        info.trade_tick_value = 1.0
        info.trade_tick_size  = 0.01
        info.digits           = 5
        return info


class _FakeOSM:
    async def start(self):                           pass
    async def stop(self):                            pass
    async def create_order(self, order):             pass
    async def transition(self, oid, state, **kw):    pass


class _FakeFR:
    def __init__(self):
        self._cb = None
        self.calls = []
    def set_retry_callback(self, cb): self._cb = cb
    async def start(self):            pass
    async def stop(self):             pass
    async def handle_failure(self, **kw):
        self.calls.append(kw)
        return "retry"


class _FakePR:
    def __init__(self, orphans=None):
        self._orphans = orphans or []
    async def start(self): pass
    async def stop(self):  pass
    async def run_once(self, db_tickets=None):
        from execution.position_reconciliation import ReconciliationResult
        import datetime as dt
        return ReconciliationResult(
            timestamp=dt.datetime.now(dt.timezone.utc),
            mt5_count=0, db_count=0, matched=0,
            orphan_in_mt5=self._orphans, orphan_in_db=[],
            db_failure=False, alert_sent=False,
        )


class _FakeRisk:
    def __init__(self, approved=True, lot=0.01):
        self._approved = approved
        self._lot      = lot
    async def assess(self, inp):
        r = MagicMock()
        r.approved     = self._approved
        r.block_reason = "" if self._approved else "test_block"
        r.lot_size     = self._lot
        r.to_dict.return_value = {"approved": self._approved, "block_reason": r.block_reason, "lot_size": self._lot, "gates": {}, "metrics": {}}
        return r


# =============================================================================
# FIX-1: Duplicate Order after Retry
# =============================================================================

class TestFix1Idempotency:

    def _make_svc(self, positions=None, order_success=True):
        from execution.execution_service import ExecutionService, _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        mt5 = _FakeMT5(positions=positions or [], order_result=_FakeOrderResult(
            success=order_success, order=9999 if order_success else 0,
            price=1.085 if order_success else 0, volume=0.01,
            error="" if order_success else "timeout", retcode=0 if order_success else 10006,
        ))
        return ExecutionService(mt5=mt5, osm=_FakeOSM(), recovery=_FakeFR(), reconciliation=_FakePR(), risk=_FakeRisk())

    @pytest.mark.asyncio
    async def test_first_signal_executes(self):
        svc = self._make_svc()
        r = await svc.execute_signal({"signal_id": "s1", "symbol": "EURUSD", "action": "BUY"})
        assert r["status"] == "filled"
        assert r["ticket"] == 9999

    @pytest.mark.asyncio
    async def test_duplicate_signal_blocked(self):
        from execution.execution_service import _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        svc = self._make_svc()
        r1 = await svc.execute_signal({"signal_id": "dup1", "symbol": "EURUSD", "action": "BUY"})
        r2 = await svc.execute_signal({"signal_id": "dup1", "symbol": "EURUSD", "action": "BUY"})
        assert r1["status"] == "filled"
        assert r2["status"] == "already_executed"
        assert r2["order_id"] == r1["order_id"]

    @pytest.mark.asyncio
    async def test_concurrent_only_one_executes(self):
        from execution.execution_service import _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS, _INFLIGHT_SIGNALS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear(); _INFLIGHT_SIGNALS.clear()
        svc = self._make_svc()
        sig = {"signal_id": "race1", "symbol": "EURUSD", "action": "BUY"}
        r1, r2 = await asyncio.gather(svc.execute_signal(sig.copy()), svc.execute_signal(sig.copy()))
        statuses = {r1["status"], r2["status"]}
        assert "filled" in statuses
        assert statuses != {"filled", "filled"}

    @pytest.mark.asyncio
    async def test_retry_skips_if_position_exists(self):
        from execution.execution_service import ExecutionService, _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        pos = _FakePosition(ticket=11111, symbol="EURUSD")
        svc = ExecutionService(mt5=_FakeMT5(positions=[pos]), osm=_FakeOSM(), recovery=_FakeFR(), reconciliation=_FakePR(), risk=_FakeRisk())
        meta = {"order": {"signal_id": "ret1", "order_id": "oid1", "symbol": "EURUSD", "action": "BUY", "requested_volume": 0.01, "requested_price": 1.085, "stop_loss": 0.0, "take_profit": 0.0, "sl_pips": 5.0}}
        result = await svc._retry_execute(meta)
        assert result is True

    @pytest.mark.asyncio
    async def test_idempotency_released_on_rejection(self):
        from execution.execution_service import _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        svc = self._make_svc(order_success=False)
        r = await svc.execute_signal({"signal_id": "fail1", "symbol": "EURUSD", "action": "BUY"})
        assert r["status"] == "rejected"
        assert "fail1" not in _IDEMPOTENCY_STORE


# =============================================================================
# FIX-2: Retry Queue Race Condition
# =============================================================================

class TestFix2AsyncioQueue:

    def _engine(self, **kw):
        from execution.failure_recovery import FailureRecoveryEngine
        return FailureRecoveryEngine(max_retries=3, base_delay=0.01, max_delay=0.05, **kw)

    @pytest.mark.asyncio
    async def test_queue_is_asyncio_queue(self):
        eng = self._engine()
        assert isinstance(eng._retry_queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_order_enqueued(self):
        eng = self._engine()
        s = await eng.handle_failure(order_id="o1", signal_id="s1", error="timeout", retcode=10004)
        assert s == "retry"
        assert eng.retry_queue_size == 1

    @pytest.mark.asyncio
    async def test_50_concurrent_no_loss(self):
        eng = self._engine()
        tasks = [eng.handle_failure(order_id=f"o{i}", signal_id=f"s{i}", error="connection reset", retcode=10006) for i in range(50)]
        strategies = await asyncio.gather(*tasks)
        assert all(s in ("retry", "dead_letter") for s in strategies)
        assert eng.retry_queue_size + len(eng.dead_letter_queue) == 50

    @pytest.mark.asyncio
    async def test_queue_full_dead_letter(self):
        from execution.failure_recovery import _RETRY_QUEUE_MAXSIZE
        eng = self._engine()
        for i in range(_RETRY_QUEUE_MAXSIZE):
            await eng._retry_queue.put(MagicMock())
        s = await eng.handle_failure(order_id="over", signal_id="s-over", error="timeout", retcode=10004)
        assert s == "dead_letter"

    @pytest.mark.asyncio
    async def test_callback_called(self):
        called = []
        async def cb(meta): called.append(meta); return True
        eng = self._engine()
        eng.set_retry_callback(cb)
        await eng.start()
        await eng.handle_failure(order_id="o-cb", signal_id="s-cb", error="timeout", retcode=10004)
        await asyncio.sleep(0.3)
        await eng.stop()
        assert len(called) >= 1

    @pytest.mark.asyncio
    async def test_success_removes_from_queue(self):
        async def cb(meta): return True
        eng = self._engine()
        eng.set_retry_callback(cb)
        await eng.start()
        await eng.handle_failure(order_id="o-ok", signal_id="s-ok", error="timeout", retcode=10004)
        await asyncio.sleep(0.3)
        await eng.stop()
        assert eng.retry_queue_size == 0

    @pytest.mark.asyncio
    async def test_max_retries_dead_letter(self):
        count = [0]
        async def cb(meta): count[0] += 1; return False
        eng = self._engine(max_retries=2, base_delay=0.01, max_delay=0.02)
        eng.set_retry_callback(cb)
        await eng.start()
        await eng.handle_failure(order_id="o-max", signal_id="s-max", error="timeout", retcode=10004)
        await asyncio.sleep(0.5)
        await eng.stop()
        assert len(eng.dead_letter_queue) >= 1

    def test_health_stats_complete(self):
        eng = self._engine()
        s = eng.health_stats()
        assert "retry_queue_size" in s
        assert "retry_queue_maxsize" in s
        assert "dead_letter_count" in s


# =============================================================================
# FIX-3: Unknown Symbol Pip Value
# =============================================================================

class TestFix3PipValue:

    def _sizer(self, mt5=None):
        from risk.lot_sizing import LotSizer, LotSizingConfig
        return LotSizer(config=LotSizingConfig(risk_percent=1.0), mt5_connector=mt5)

    @pytest.mark.asyncio
    async def test_eurusd_returns_10(self):
        s = self._sizer()
        v, src = await s.get_pip_value("EURUSD")
        assert v == 10.0 and src == "static_table"

    @pytest.mark.asyncio
    async def test_xauusd_returns_1(self):
        s = self._sizer()
        v, src = await s.get_pip_value("XAUUSD")
        assert v == 1.0  # FIX-3: was 10.0

    @pytest.mark.asyncio
    async def test_unknown_raises(self):
        from risk.lot_sizing import UnknownSymbolError
        s = self._sizer()
        with pytest.raises(UnknownSymbolError) as exc:
            await s.get_pip_value("ABCXYZ")
        assert "ABCXYZ" in str(exc.value)

    @pytest.mark.asyncio
    async def test_empty_symbol_raises(self):
        from risk.lot_sizing import UnknownSymbolError
        s = self._sizer()
        with pytest.raises(UnknownSymbolError):
            await s.calculate(10000, 20, symbol="")

    @pytest.mark.asyncio
    async def test_mt5_used_first(self):
        mt5 = MagicMock()
        info = MagicMock()
        info.trade_tick_value = 0.5; info.trade_tick_size = 0.01; info.digits = 5
        mt5.get_symbol_info = AsyncMock(return_value=info)
        from risk.lot_sizing import LotSizer, LotSizingConfig
        s = LotSizer(config=LotSizingConfig(), mt5_connector=mt5)
        v, src = await s.get_pip_value("EXOTIC")
        assert src == "mt5_dynamic" and v > 0

    @pytest.mark.asyncio
    async def test_mt5_fail_falls_back(self):
        mt5 = MagicMock()
        mt5.get_symbol_info = AsyncMock(side_effect=ConnectionError("offline"))
        s = self._sizer(mt5=mt5)
        v, src = await s.get_pip_value("GBPUSD")
        assert src == "static_table" and v == 10.0

    @pytest.mark.asyncio
    async def test_xauusd_lot_10x_eurusd(self):
        s = self._sizer()
        r_eu = await s.calculate(10000, 20, symbol="EURUSD")
        r_au = await s.calculate(10000, 20, symbol="XAUUSD")
        assert abs(r_au.lot_size / r_eu.lot_size - 10.0) < 2.0

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        s = self._sizer()
        v1, _ = await s.get_pip_value("eurusd")
        v2, _ = await s.get_pip_value("EURUSD")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_all_table_symbols_valid(self):
        from risk.lot_sizing import _PIP_VALUE_TABLE
        s = self._sizer()
        for sym in _PIP_VALUE_TABLE:
            v, _ = await s.get_pip_value(sym)
            assert v > 0, f"{sym} pip_value should be > 0"


# =============================================================================
# FIX-4: Rolling Correlation Engine
# =============================================================================

class TestFix4Rolling:

    def _engine(self, w=20):
        from risk.correlation_filter import RollingCorrelationEngine
        return RollingCorrelationEngine(window=w, cache_ttl=60.0)

    def _filter(self):
        from risk.correlation_filter import CorrelationFilter, CorrelationFilterConfig
        return CorrelationFilter(CorrelationFilterConfig(max_correlated_exposure=0.80, correlation_penalty_threshold=0.60, window=20))

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self):
        e = self._engine()
        await e.add_price("EURUSD", 1.085)
        assert await e.get_correlation("EURUSD", "GBPUSD") is None

    @pytest.mark.asyncio
    async def test_positive_correlation(self):
        e = self._engine(w=30)
        for i in range(25):
            p = 1.0 + i * 0.001
            await e.add_price("AAA", p)
            await e.add_price("BBB", p * 1.2)
        corr = await e.get_correlation("AAA", "BBB")
        assert corr is not None and corr > 0.95

    @pytest.mark.asyncio
    async def test_negative_correlation(self):
        e = self._engine(w=30)
        for i in range(25):
            await e.add_price("CCC", 1.0 + i * 0.001)
            await e.add_price("DDD", 2.0 - i * 0.001)
        corr = await e.get_correlation("CCC", "DDD")
        assert corr is not None and corr < -0.95

    @pytest.mark.asyncio
    async def test_same_symbol_one(self):
        e = self._engine()
        assert await e.get_correlation("EURUSD", "EURUSD") == 1.0

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        e = self._engine(w=20)
        for i in range(15):
            await e.add_price("EEE", 1.0 + i * 0.001)
            await e.add_price("FFF", 1.0 + i * 0.002)
        c1 = await e.get_correlation("EEE", "FFF")
        c2 = await e.get_correlation("EEE", "FFF")
        assert c1 == c2

    @pytest.mark.asyncio
    async def test_filter_static_fallback(self):
        from risk.correlation_filter import CorrelationFilter, CorrPosition
        flt = CorrelationFilter()
        pos = [CorrPosition("GBPUSD", "BUY", 1.0)]
        result = await flt.check("EURUSD", "BUY", pos, 1.0)
        assert result.source == "static"

    @pytest.mark.asyncio
    async def test_high_corr_blocked(self):
        from risk.correlation_filter import CorrelationFilter, CorrPosition, CorrelationFilterConfig
        flt = CorrelationFilter(CorrelationFilterConfig(max_correlated_exposure=0.80, correlation_penalty_threshold=0.60))
        pos = [CorrPosition("GBPUSD", "BUY", 1.0)]
        result = await flt.check("EURUSD", "BUY", pos, 1.0)
        assert result.can_trade is False

    @pytest.mark.asyncio
    async def test_portfolio_matrix(self):
        from risk.correlation_filter import CorrelationFilter
        flt = CorrelationFilter()
        syms = ["EURUSD", "GBPUSD", "XAUUSD"]
        m = await flt.portfolio_correlation_matrix(syms)
        assert len(m) == 6

    @pytest.mark.asyncio
    async def test_no_positions_passes(self):
        from risk.correlation_filter import CorrelationFilter
        flt = CorrelationFilter()
        r = await flt.check("EURUSD", "BUY", [], 1.0)
        assert r.can_trade is True and r.risk_multiplier == 1.0


# =============================================================================
# FIX-5: Orphan -> Manual Review
# =============================================================================

class TestFix5OrphanManual:

    def _pr(self, positions=None, db_tickets=None, db_fail=False):
        from execution.position_reconciliation import PositionReconciliation

        class FakeMT5:
            def __init__(self, p): self._p = p
            async def get_positions(self): return self._p
            async def close_position(self, t): return {"success": True, "ticket": t}

        mt5 = FakeMT5(positions or [])
        pr  = PositionReconciliation(mt5=mt5, interval_seconds=9999)

        if db_fail:
            async def fail(): raise RuntimeError("DB offline")
            pr.set_db_callback(fail)
        elif db_tickets is not None:
            async def ok(): return db_tickets
            pr.set_db_callback(ok)
        else:
            async def empty(): return []
            pr.set_db_callback(empty)
        return pr, mt5

    @pytest.mark.asyncio
    async def test_auto_close_param_ignored(self):
        from execution.position_reconciliation import PositionReconciliation
        with patch("execution.position_reconciliation.logger") as ml:
            PositionReconciliation(auto_close_orphans=True)
            ml.warning.assert_called()

    @pytest.mark.asyncio
    async def test_orphan_detected_no_close(self):
        pos = _FakePosition(ticket=55555, symbol="XAUUSD")
        pr, _ = self._pr(positions=[pos], db_tickets=[])
        alerts = []
        pr.set_alert_callback(lambda r: alerts.append(r))
        result = await pr.run_once(db_tickets=[])
        assert len(result.orphan_in_mt5) == 1
        assert result.alert_sent is True

    @pytest.mark.asyncio
    async def test_db_failure_no_close(self):
        pos = _FakePosition(ticket=77777, symbol="EURUSD")
        pr, mt5 = self._pr(positions=[pos], db_fail=True)
        close_called = [False]
        orig = mt5.close_position
        async def guarded(t): close_called[0] = True; return await orig(t)
        mt5.close_position = guarded
        result = await pr.run_once()
        assert result.db_failure is True
        assert close_called[0] is False

    @pytest.mark.asyncio
    async def test_manual_close_works(self):
        pos = _FakePosition(ticket=88888, symbol="GBPUSD")
        pr, _ = self._pr(positions=[pos], db_tickets=[])
        await pr.run_once(db_tickets=[])
        r = await pr.close_orphan_ticket(88888, review_note="confirmed", requester="admin")
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_close_unknown_fails(self):
        pr, _ = self._pr()
        r = await pr.close_orphan_ticket(99999)
        assert r["success"] is False and "not found" in r["error"]

    @pytest.mark.asyncio
    async def test_mark_reviewed(self):
        pos = _FakePosition(ticket=11111, symbol="USDJPY")
        pr, _ = self._pr(positions=[pos], db_tickets=[])
        await pr.run_once(db_tickets=[])
        ok = await pr.mark_orphan_reviewed(11111, note="monitoring", action="ignore")
        assert ok is True
        reg = await pr.get_orphan_registry()
        entry = next(r for r in reg if r["ticket"] == 11111)
        assert entry["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_no_duplicate_registry(self):
        pos = _FakePosition(ticket=22222, symbol="AUDUSD")
        pr, _ = self._pr(positions=[pos], db_tickets=[])
        await pr.run_once(db_tickets=[])
        await pr.run_once(db_tickets=[])
        reg = await pr.get_orphan_registry()
        assert len([r for r in reg if r["ticket"] == 22222]) == 1

    @pytest.mark.asyncio
    async def test_matched_not_orphan(self):
        pos = _FakePosition(ticket=33333, symbol="NZDUSD")
        pr, _ = self._pr(positions=[pos], db_tickets=[33333])
        result = await pr.run_once(db_tickets=[33333])
        assert result.matched == 1 and len(result.orphan_in_mt5) == 0

    @pytest.mark.asyncio
    async def test_alert_callback_called(self):
        pos = _FakePosition(ticket=44444, symbol="XAGUSD")
        pr, _ = self._pr(positions=[pos], db_tickets=[])
        called = []
        async def alert(res): called.append(res)
        pr.set_alert_callback(alert)
        await pr.run_once(db_tickets=[])
        assert len(called) == 1 and called[0].orphan_in_mt5[0].ticket == 44444


# =============================================================================
# INTEGRATION
# =============================================================================

class TestIntegration:

    @pytest.mark.asyncio
    async def test_full_pipeline_clean(self):
        from execution.execution_service import ExecutionService, _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        svc = ExecutionService(mt5=_FakeMT5(), osm=_FakeOSM(), recovery=_FakeFR(), reconciliation=_FakePR(), risk=_FakeRisk())
        r = await svc.execute_signal({"signal_id": "int-001", "symbol": "EURUSD", "action": "BUY", "entry_price": 1.085, "stop_loss": 1.080, "take_profit_1": 1.095})
        assert r["status"] == "filled"

    @pytest.mark.asyncio
    async def test_retry_reconcile_no_duplicate(self):
        from execution.execution_service import ExecutionService, _IDEMPOTENCY_STORE, _IDEMPOTENCY_TIMESTAMPS
        _IDEMPOTENCY_STORE.clear(); _IDEMPOTENCY_TIMESTAMPS.clear()
        pos = _FakePosition(ticket=55555, symbol="GBPUSD")
        svc = ExecutionService(mt5=_FakeMT5(positions=[pos]), osm=_FakeOSM(), recovery=_FakeFR(), reconciliation=_FakePR(), risk=_FakeRisk())
        meta = {"order": {"signal_id": "ret-int", "order_id": "oid-ret", "symbol": "GBPUSD", "action": "BUY", "requested_volume": 0.01, "requested_price": 1.27, "stop_loss": 0.0, "take_profit": 0.0, "sl_pips": 10.0}}
        ok = await svc._retry_execute(meta)
        assert ok is True
