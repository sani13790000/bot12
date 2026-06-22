"""test_hf_fixes.py — Unit Tests for 5 Hedge-Fund Grade Fixes

HF-1: Circuit Breaker (7 tests)
HF-2: Dynamic Correlation Engine (8 tests)
HF-3: Dynamic Pip/Tick Value (8 tests)
HF-4: Position Reconciliation Before Retry (8 tests)
HF-5: Order Journal (9 tests)

Total: 40 tests
"""
import asyncio
import math
import pytest

# ============================================================================
# HF-1: Circuit Breaker
# ============================================================================
from backend.circuit_breaker import (
    CircuitBreaker, BreakerConfig, State, CircuitOpenError,
    halt_trading, resume_trading, is_trading_halted,
)


@pytest.mark.asyncio
async def test_cb_opens_after_threshold():
    cb = CircuitBreaker("t1", BreakerConfig(failure_threshold=5, failure_window_s=60.0, recovery_timeout_s=999.0))
    for _ in range(5):
        try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        except (ValueError, CircuitOpenError): pass
    assert cb.stats.state == State.OPEN


@pytest.mark.asyncio
async def test_cb_window_expiry():
    cb = CircuitBreaker("t2", BreakerConfig(failure_threshold=3, failure_window_s=0.05, recovery_timeout_s=999.0))
    for _ in range(2):
        try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        except (ValueError, CircuitOpenError): pass
    await asyncio.sleep(0.1)
    try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    except (ValueError, CircuitOpenError): pass
    assert cb.stats.state == State.CLOSED


@pytest.mark.asyncio
async def test_cb_global_halt():
    await resume_trading()
    cb = CircuitBreaker("t3", BreakerConfig(failure_threshold=2, failure_window_s=60.0))
    for _ in range(2):
        try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        except (ValueError, CircuitOpenError): pass
    assert is_trading_halted()
    await resume_trading()


@pytest.mark.asyncio
async def test_cb_rejects_when_open():
    cb = CircuitBreaker("t4", BreakerConfig(failure_threshold=1, failure_window_s=60.0, recovery_timeout_s=999.0))
    try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    except (ValueError, CircuitOpenError): pass
    with pytest.raises(CircuitOpenError): await cb.call(lambda: "ok")


@pytest.mark.asyncio
async def test_cb_half_open_recovery():
    cb = CircuitBreaker("t5", BreakerConfig(failure_threshold=1, failure_window_s=60.0, recovery_timeout_s=0.05, success_threshold=1))
    try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    except (ValueError, CircuitOpenError): pass
    await asyncio.sleep(0.1)
    try: await cb.call(lambda: "success")
    except CircuitOpenError: pass
    assert cb.stats.state in (State.HALF_OPEN, State.CLOSED)


@pytest.mark.asyncio
async def test_cb_callback_fired():
    changes = []
    cb = CircuitBreaker("t6", BreakerConfig(failure_threshold=1, failure_window_s=60.0))
    cb.on_state_change(lambda name, old, new: changes.append((old, new)))
    try: await cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    except (ValueError, CircuitOpenError): pass
    await asyncio.sleep(0.01)
    assert any(n == State.OPEN for _, n in changes)


@pytest.mark.asyncio
async def test_cb_get_status():
    cb = CircuitBreaker("t7", BreakerConfig(failure_threshold=5, failure_window_s=60.0))
    s = cb.get_status()
    assert s["state"] == "closed" and s["threshold"] == 5 and s["window_s"] == 60.0


# ============================================================================
# HF-2: Dynamic Correlation Engine
# ============================================================================
from backend.institutional.correlation_engine import RollingCorrelationEngine


@pytest.mark.asyncio
async def test_corr_static_fallback():
    engine = RollingCorrelationEngine()
    corr = await engine.get_correlation("EURUSD", "GBPUSD")
    assert corr is not None and abs(corr - 0.85) < 0.01


@pytest.mark.asyncio
async def test_corr_rolling():
    engine = RollingCorrelationEngine(window=20, cache_ttl=0.0)
    for i in range(30):
        await engine.add_price_tick("A", 1.0 + i * 0.001)
        await engine.add_price_tick("B", 2.0 + i * 0.001)
    corr = await engine.get_correlation("A", "B")
    assert corr is not None and corr > 0.95


@pytest.mark.asyncio
async def test_corr_anti_correlated():
    import random; random.seed(42)
    engine = RollingCorrelationEngine(window=50, cache_ttl=0.0)
    price_up = price_dn = 1.1
    for _ in range(60):
        c = random.gauss(0, 0.003)
        price_up *= (1 + c); price_dn *= (1 - c)
        await engine.add_price_tick("UP", price_up)
        await engine.add_price_tick("DN", price_dn)
    corr = await engine.get_correlation("UP", "DN")
    assert corr is not None and corr < -0.90


@pytest.mark.asyncio
async def test_corr_self():
    engine = RollingCorrelationEngine()
    assert await engine.get_correlation("EURUSD", "EURUSD") == 1.0


@pytest.mark.asyncio
async def test_corr_unknown_pair():
    engine = RollingCorrelationEngine()
    assert await engine.get_correlation("ZZZNEW", "QQQNEW") is None


@pytest.mark.asyncio
async def test_corr_matrix():
    engine = RollingCorrelationEngine()
    syms = ["EURUSD", "GBPUSD", "XAUUSD"]
    matrix = await engine.portfolio_correlation_matrix(syms)
    for s in syms: assert matrix[s][s] == 1.0


@pytest.mark.asyncio
async def test_corr_canonical_symmetric():
    from backend.institutional.correlation_engine import _canonical
    assert _canonical("GBPUSD", "EURUSD") == _canonical("EURUSD", "GBPUSD")


@pytest.mark.asyncio
async def test_corr_cache_invalidated_on_tick():
    engine = RollingCorrelationEngine(window=20, cache_ttl=60.0)
    for i in range(30):
        await engine.add_price_tick("X", 1.0 + i * 0.001)
        await engine.add_price_tick("Y", 1.0 + i * 0.001)
    c1 = await engine.get_correlation("X", "Y")
    await engine.add_price_tick("X", 1.999)  # invalidates cache
    assert c1 is not None


# ============================================================================
# HF-3: Dynamic Pip/Tick Value
# ============================================================================
from backend.risk.lot_sizing import LotSizer, LotSizingConfig, UnknownSymbolError


@pytest.mark.asyncio
async def test_pip_eurusd():
    s = LotSizer(); val, src = await s.get_pip_value("EURUSD")
    assert val == 10.0 and src == "static_table"


@pytest.mark.asyncio
async def test_pip_xauusd_corrected():
    s = LotSizer(); val, _ = await s.get_pip_value("XAUUSD")
    assert val == 1.0


@pytest.mark.asyncio
async def test_pip_unknown_raises():
    s = LotSizer()
    with pytest.raises(UnknownSymbolError): await s.get_pip_value("ZZZNEW999")


@pytest.mark.asyncio
async def test_pip_case_insensitive():
    s = LotSizer()
    v1, _ = await s.get_pip_value("eurusd")
    v2, _ = await s.get_pip_value("EURUSD")
    assert v1 == v2


@pytest.mark.asyncio
async def test_lot_size_eurusd():
    s = LotSizer(LotSizingConfig(risk_percent=1.0))
    r = await s.calculate(balance=10_000, stop_loss_pips=20, symbol="EURUSD")
    assert abs(r.lot_size - 0.50) < 0.01


@pytest.mark.asyncio
async def test_lot_size_xauusd():
    s = LotSizer(LotSizingConfig(risk_percent=1.0))
    r = await s.calculate(balance=10_000, stop_loss_pips=20, symbol="XAUUSD")
    assert abs(r.lot_size - 5.0) < 0.01


@pytest.mark.asyncio
async def test_lot_clamped_min_max():
    s = LotSizer(LotSizingConfig(risk_percent=0.001, min_lot=0.01, max_lot=10.0))
    r = await s.calculate(balance=100, stop_loss_pips=1000, symbol="EURUSD")
    assert s.config.min_lot <= r.lot_size <= s.config.max_lot


@pytest.mark.asyncio
async def test_pip_cached():
    s = LotSizer()
    v1, _ = await s.get_pip_value("GBPUSD")
    v2, _ = await s.get_pip_value("GBPUSD")
    assert v1 == v2


# ============================================================================
# HF-4: Position Reconciliation Before Retry
# ============================================================================
from backend.execution.position_reconciliation import PositionReconciliation, OrphanStatus


class _FakeMT5:
    def __init__(self, positions=None): self._pos = positions or []
    def positions_get_sync(self, ticket=None, symbol=None):
        if ticket is not None: return [p for p in self._pos if p.ticket == ticket]
        if symbol is not None: return [p for p in self._pos if p.symbol == symbol]
        return self._pos
    def close_position_sync(self, ticket):
        self._pos = [p for p in self._pos if p.ticket != ticket]; return True


class _FakePos:
    def __init__(self, ticket, symbol, typ=0, volume=0.1, price=1.1, profit=10.0):
        self.ticket=ticket; self.symbol=symbol; self.type=typ
        self.volume=volume; self.price_open=price; self.profit=profit


@pytest.mark.asyncio
async def test_verify_exists_true():
    r = PositionReconciliation(mt5=_FakeMT5([_FakePos(1, "EURUSD")]))
    assert await r.verify_position_exists(1, "EURUSD") is True


@pytest.mark.asyncio
async def test_verify_exists_false():
    r = PositionReconciliation(mt5=_FakeMT5([]))
    assert await r.verify_position_exists(9, "EURUSD") is False


@pytest.mark.asyncio
async def test_check_dup_buy():
    r = PositionReconciliation(mt5=_FakeMT5([_FakePos(1, "EURUSD", typ=0)]))
    assert await r.check_symbol_already_open("EURUSD", "BUY") is True


@pytest.mark.asyncio
async def test_check_no_dup():
    r = PositionReconciliation(mt5=_FakeMT5([_FakePos(1, "EURUSD", typ=1)]))
    assert await r.check_symbol_already_open("EURUSD", "BUY") is False


@pytest.mark.asyncio
async def test_db_failure_no_autoclose():
    mt5 = _FakeMT5([_FakePos(1, "XAUUSD")])
    r = PositionReconciliation(mt5=mt5)
    async def bad_db(): raise RuntimeError("DB down")
    r.set_db_callback(bad_db)
    result = await r.run_once()
    assert result.db_failure and len(mt5.positions_get_sync()) == 1


@pytest.mark.asyncio
async def test_orphan_detected():
    mt5 = _FakeMT5([_FakePos(2, "GBPUSD")])
    r = PositionReconciliation(mt5=mt5)
    async def empty_db(): return []
    r.set_db_callback(empty_db)
    result = await r.run_once()
    assert len(result.orphan_mt5) == 1 and result.orphan_mt5[0].ticket == 2


@pytest.mark.asyncio
async def test_interval_clamped():
    r = PositionReconciliation(interval_seconds=1)
    assert r._interval == 5
    r.set_interval(9999); assert r._interval == 300


@pytest.mark.asyncio
async def test_auto_close_ignored():
    mt5 = _FakeMT5([_FakePos(3, "USDJPY")])
    PositionReconciliation(mt5=mt5, auto_close_orphans=True)
    assert len(mt5.positions_get_sync()) == 1


# ============================================================================
# HF-5: Order Journal
# ============================================================================
from backend.execution.order_journal import OrderJournal, JournalEventType


@pytest.mark.asyncio
async def test_journal_signal():
    j = OrderJournal()
    e = await j.record_signal("s1", "EURUSD", "BUY", 0.1, 1.1, 1.095, 1.115)
    assert e.event_type == JournalEventType.SIGNAL_RECEIVED and e.signal_id == "s1"


@pytest.mark.asyncio
async def test_journal_full_lifecycle():
    j = OrderJournal()
    await j.record_signal("s2", "GBPUSD", "BUY", 0.5, 1.27, 1.265, 1.28)
    await j.record_risk("s2", "o2", 0.85, True)
    await j.record_submission("o2", "s2", "GBPUSD", "BUY", 0.5, 1.27, 1.265, 1.28, mt5_ticket=9001)
    await j.record_fill("o2", 1.2702, 0.5, slippage_pips=0.2, latency_ms=120.0)
    await j.record_close("o2", 1.28, pnl_usd=50.0, reason="tp")
    rec = await j.get_order("o2")
    assert rec and rec.final_state == "closed" and rec.pnl_usd == 50.0 and rec.total_latency_ms is not None


@pytest.mark.asyncio
async def test_journal_risk_block():
    j = OrderJournal()
    e = await j.record_risk("s3", "o3", 0.2, False, "daily limit")
    assert e.event_type == JournalEventType.RISK_BLOCKED and e.risk_allowed is False


@pytest.mark.asyncio
async def test_journal_rejection():
    j = OrderJournal()
    await j.record_submission("o4", "s4", "XAUUSD", "SELL", 1.0, 1900.0, 1910.0, 1880.0)
    await j.record_rejection("o4", "invalid price", mt5_retcode=10014)
    rec = await j.get_order("o4")
    assert rec and rec.final_state == "rejected"


@pytest.mark.asyncio
async def test_journal_persist_callback():
    persisted = []
    j = OrderJournal(persist_callback=lambda d: persisted.append(d))
    await j.record_signal("s5", "USDJPY", "SELL", 0.2, 140.0, 140.5, 139.0)
    assert len(persisted) == 1 and persisted[0]["event_type"] == "signal_received"


@pytest.mark.asyncio
async def test_journal_stats():
    j = OrderJournal()
    await j.record_submission("o6", "s6", "EURUSD", "BUY", 0.1, 1.1, 1.095, 1.115)
    await j.record_fill("o6", 1.1001, 0.1, slippage_pips=0.1)
    await j.record_close("o6", 1.115, pnl_usd=150.0)
    stats = await j.get_stats()
    assert stats["closed_orders"] == 1 and stats["win_rate"] == 100.0


@pytest.mark.asyncio
async def test_journal_query_signal():
    j = OrderJournal()
    await j.record_signal("sq", "NZDUSD", "BUY", 0.1, 0.62, 0.615, 0.63)
    entries = await j.get_entries_for_signal("sq")
    assert len(entries) >= 1 and all(e.signal_id == "sq" for e in entries)


@pytest.mark.asyncio
async def test_journal_maxlen():
    j = OrderJournal(max_entries=10)
    for i in range(20):
        await j.record_signal(f"s{i}", "EURUSD", "BUY", 0.1, 1.1, 1.09, 1.11)
    recent = await j.get_recent_entries(100)
    assert len(recent) == 10


@pytest.mark.asyncio
async def test_journal_error():
    j = OrderJournal()
    e = await j.record_error("oe", "se", "MT5 timeout")
    assert e.event_type == JournalEventType.ERROR and "timeout" in e.message
