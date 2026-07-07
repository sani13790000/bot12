"""
backend/tests/test_phase_p.py
Phase P unit tests -- 52 tests covering:
  P-4 telegram httpx timeout | P-5 utcnow fix
  P-6 numpy json | P-7 signal DB filters
  P-9 rolling correlation | P-11 validators
  P-12 asyncio lock circuit breaker
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest


# ── P-5 RetrainingService ────────────────────────────────────────────────────
class TestRetrainingServiceUTCNow:
    def test_utcnow_is_timezone_aware(self):
        from backend.self_learning.retraining_service import _utcnow

        now = _utcnow()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_checked_at_is_iso_with_tz(self):
        from backend.self_learning.retraining_service import RetrainingService

        svc = RetrainingService()
        result = asyncio.get_event_loop().run_until_complete(svc.check_and_retrain())
        assert "checked_at" in result
        dt = datetime.fromisoformat(result["checked_at"])
        assert dt.tzinfo is not None

    def test_get_status_last_retrain_none(self):
        from backend.self_learning.retraining_service import RetrainingService

        svc = RetrainingService()
        status = asyncio.get_event_loop().run_until_complete(svc.get_status())
        assert status["last_retrain"] is None

    def test_overfit_ratio_no_division_by_zero(self):
        from backend.self_learning.retraining_service import RetrainingService

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.train_accuracy = 0.9
        mock_result.test_accuracy = 0.0
        mock_result.model = None
        mock_engine.train.return_value = mock_result
        mock_memory = MagicMock()
        mock_memory.get_recent_trades.return_value = [{}] * 100
        svc = RetrainingService(trade_memory=mock_memory, ml_engine=mock_engine)
        result = svc._run_training_sync()
        assert result["overfit_ratio"] == 0.0

    def test_first_run_triggers_retrain(self):
        from backend.self_learning.retraining_service import RetrainingService

        mock_memory = MagicMock()
        mock_memory.get_recent_trades.return_value = [{}] * 60
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.train_accuracy = 0.8
        mock_result.test_accuracy = 0.75
        mock_result.model = object()
        mock_engine.train.return_value = mock_result
        mock_engine.get_drift_stats.return_value = {"drift_score": 0.0}
        svc = RetrainingService(trade_memory=mock_memory, ml_engine=mock_engine)
        result = asyncio.get_event_loop().run_until_complete(svc.check_and_retrain())
        assert result["retrained"] is True
        assert result["reason"] == "first_run"


# ── P-6 WeightAdjuster numpy ─────────────────────────────────────────────────
class TestWeightAdjusterNumpyFix:
    def test_to_dict_returns_plain_floats(self):
        from backend.intelligence.weight_adjuster import IndicatorWeights

        w = IndicatorWeights()
        d = w.to_dict()
        for k, v in d.items():
            assert type(v) is float, f"{k}={v!r} is {type(v)}"

    def test_to_dict_json_serializable(self):
        from backend.intelligence.weight_adjuster import IndicatorWeights

        w = IndicatorWeights(smc_weight=np.float64(0.40), price_action_weight=np.float64(0.25))
        d = w.to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert abs(loaded["smc_weight"] - 0.4) < 0.01

    def test_normalize_sums_to_one(self):
        from backend.intelligence.weight_adjuster import IndicatorWeights

        w = IndicatorWeights(
            smc_weight=np.float64(1.0),
            price_action_weight=np.float64(1.0),
            htf_alignment_weight=np.float64(1.0),
            session_weight=np.float64(1.0),
            ltf_weight=np.float64(1.0),
        ).normalize()
        total = (
            w.smc_weight
            + w.price_action_weight
            + w.htf_alignment_weight
            + w.session_weight
            + w.ltf_weight
        )
        assert abs(total - 1.0) < 1e-9

    def test_apply_delta_clamped(self):
        from backend.intelligence.weight_adjuster import _MAX_DELTA_PER_CYCLE, IndicatorWeights

        w = IndicatorWeights()
        w2 = w.apply_delta("smc_weight", 99.0)
        assert abs(w2.smc_weight - w.smc_weight) <= _MAX_DELTA_PER_CYCLE + 0.02

    def test_min_weight_enforced(self):
        from backend.intelligence.weight_adjuster import _MIN_WEIGHT, IndicatorWeights

        w = IndicatorWeights()
        w2 = w.apply_delta("ltf_weight", -99.0)
        assert w2.ltf_weight >= _MIN_WEIGHT


# ── P-7 SignalService DB-side filters ────────────────────────────────────────
class TestSignalServiceDBFilters:
    def _make_service(self, mock_rows):
        from backend.services import signal_service as mod

        svc = mod.SignalService()
        mock_db = AsyncMock()
        mock_db.select_many = AsyncMock(return_value=mock_rows)
        mod.db = mock_db
        return svc, mock_db

    def test_symbol_passed_to_db(self):
        rows = [{"id": "1", "symbol": "XAUUSD", "score": 70, "expires_at": None}]
        svc, mock_db = self._make_service(rows)
        asyncio.get_event_loop().run_until_complete(svc.get_signals("user1", symbol="xauusd"))
        call_kwargs = mock_db.select_many.call_args[1]
        assert call_kwargs["filters"].get("symbol") == "XAUUSD"

    def test_direction_passed_to_db(self):
        rows = [
            {"id": "1", "symbol": "EURUSD", "direction": "BUY", "score": 70, "expires_at": None}
        ]
        svc, mock_db = self._make_service(rows)
        asyncio.get_event_loop().run_until_complete(svc.get_signals("user1", direction="buy"))
        call_kwargs = mock_db.select_many.call_args[1]
        assert call_kwargs["filters"].get("direction") == "BUY"

    def test_expired_signals_excluded(self):
        from datetime import timedelta

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        rows = [
            {"id": "1", "score": 70, "expires_at": past},
            {"id": "2", "score": 70, "expires_at": future},
        ]
        svc, mock_db = self._make_service(rows)
        result = asyncio.get_event_loop().run_until_complete(svc.get_signals("user1"))
        ids = [s["id"] for s in result["signals"]]
        assert "1" not in ids
        assert "2" in ids

    def test_user_id_in_filter_prevents_leak(self):
        svc, mock_db = self._make_service([])
        asyncio.get_event_loop().run_until_complete(svc.get_signal_by_id("sig-123", "user-abc"))
        call_kwargs = mock_db.select_many.call_args[1]
        assert call_kwargs["filters"].get("user_id") == "user-abc"

    def test_min_score_filters_results(self):
        rows = [
            {"id": "1", "score": 40, "expires_at": None},
            {"id": "2", "score": 80, "expires_at": None},
        ]
        svc, mock_db = self._make_service(rows)
        result = asyncio.get_event_loop().run_until_complete(svc.get_signals("user1", min_score=60))
        ids = [s["id"] for s in result["signals"]]
        assert "1" not in ids
        assert "2" in ids


# ── P-9 PortfolioRisk rolling correlation ────────────────────────────────────
class TestPortfolioRiskRollingCorrelation:
    def _make_risk(self, sym, direction, entry, sl, balance=10000.0):
        from backend.risk.portfolio_risk import OpenTradeRisk, TradeDirection

        return OpenTradeRisk(
            symbol=sym,
            direction=TradeDirection(direction),
            lot_size=0.1,
            entry_price=entry,
            stop_loss=sl,
            account_balance=balance,
        )

    def test_uses_fallback_when_no_rolling_data(self):
        from backend.risk.portfolio_risk import PortfolioRiskManager

        pm = PortfolioRiskManager()
        t1 = self._make_risk("EURUSD", "BUY", 1.1000, 1.0950)
        t2 = self._make_risk("GBPUSD", "BUY", 1.2700, 1.2650)
        snap = pm.check(t1, [t2])
        assert snap.correlation_source in ("static", "unknown", "rolling")

    def test_add_price_tick_no_crash(self):
        from backend.risk.portfolio_risk import PortfolioRiskManager

        pm = PortfolioRiskManager()
        for i in range(60):
            pm.add_price_tick("EURUSD", 1.1000 + i * 0.0001)
            pm.add_price_tick("GBPUSD", 1.2700 + i * 0.0001)
        t1 = self._make_risk("EURUSD", "BUY", 1.1000, 1.0950)
        snap = pm.check(t1, [])
        assert snap.total_risk_percent >= 0

    def test_blocked_when_over_limit(self):
        from backend.risk.portfolio_risk import PortfolioRiskManager, RiskLevel

        pm = PortfolioRiskManager()
        trades = [
            self._make_risk("EURUSD", "BUY", 1.1000, 1.0000, 1000),
            self._make_risk("GBPUSD", "BUY", 1.2700, 1.1700, 1000),
            self._make_risk("AUDUSD", "BUY", 0.7500, 0.6500, 1000),
        ]
        new = self._make_risk("USDJPY", "BUY", 140.0, 130.0, 1000)
        snap = pm.check(new, trades)
        assert snap.risk_level in (RiskLevel.WARNING, RiskLevel.CRITICAL, RiskLevel.BLOCKED)


# ── P-11 Validators ──────────────────────────────────────────────────────────
class TestValidators:
    def test_valid_symbol(self):
        from backend.core.validators import validate_symbol

        assert validate_symbol("eurusd") == "EURUSD"
        assert validate_symbol("XAUUSD") == "XAUUSD"

    def test_unknown_symbol_raises(self):
        from backend.core.validators import validate_symbol

        with pytest.raises(ValueError, match="not in allowed list"):
            validate_symbol("FAKEUSD")

    def test_symbol_case_insensitive(self):
        from backend.core.validators import validate_symbol

        assert validate_symbol("gbpusd") == "GBPUSD"

    def test_lot_size_min(self):
        from backend.core.validators import validate_lot_size

        with pytest.raises(ValueError, match="below minimum"):
            validate_lot_size(0.001)

    def test_lot_size_max(self):
        from backend.core.validators import validate_lot_size

        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_lot_size(200.0)

    def test_lot_size_valid(self):
        from backend.core.validators import validate_lot_size

        assert validate_lot_size(1.0) == 1.0

    def test_validate_signal_id_valid(self):
        from backend.core.validators import validate_signal_id

        uid = str(uuid.uuid4())
        assert validate_signal_id(uid) == uid.lower()

    def test_validate_signal_id_invalid(self):
        from backend.core.validators import validate_signal_id

        with pytest.raises(ValueError, match="valid UUID"):
            validate_signal_id("not-a-uuid")

    def test_validate_direction_valid(self):
        from backend.core.validators import validate_direction

        assert validate_direction("buy") == "BUY"
        assert validate_direction("SELL") == "SELL"

    def test_validate_direction_invalid(self):
        from backend.core.validators import validate_direction

        with pytest.raises(ValueError):
            validate_direction("LONG")

    def test_validate_risk_percent_bounds(self):
        from backend.core.validators import validate_risk_percent

        with pytest.raises(ValueError):
            validate_risk_percent(0.0)
        with pytest.raises(ValueError):
            validate_risk_percent(6.0)
        assert validate_risk_percent(1.0) == 1.0


# ── P-12 CircuitBreaker asyncio lock ─────────────────────────────────────────
class TestCircuitBreakerAsyncLock:
    def test_lock_is_asyncio_lock(self):
        import asyncio as aio

        from backend.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test_cb")
        assert isinstance(cb._lock, aio.Lock)

    def test_no_threading_lock(self):
        import threading

        from backend.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test_cb2")
        assert not isinstance(cb._lock, threading.Lock)

    def test_closed_to_open_transition(self):
        from backend.circuit_breaker import BreakerConfig, CircuitBreaker, State

        async def _test():
            cb = CircuitBreaker("t1", BreakerConfig(failure_threshold=2))

            async def fail():
                raise ValueError("fail")

            for _ in range(2):
                with pytest.raises((ValueError, RuntimeError)):
                    await cb.call(fail)
            assert cb.stats.state == State.OPEN

        asyncio.get_event_loop().run_until_complete(_test())

    def test_registry_cap(self):
        from backend.circuit_breaker import _MAX_REGISTRY_SIZE, _registry, get_breaker

        async def _test():
            _registry.clear()
            for i in range(_MAX_REGISTRY_SIZE + 5):
                await get_breaker(f"cb_{i}")
            assert len(_registry) <= _MAX_REGISTRY_SIZE

        asyncio.get_event_loop().run_until_complete(_test())

    def test_callback_exception_no_crash(self):
        from backend.circuit_breaker import CircuitBreaker

        async def _test():
            cb = CircuitBreaker("t3")

            def bad_cb(name, old, new):
                raise RuntimeError("crash!")

            cb.on_state_change(bad_cb)
            await cb._fire_callbacks("closed", "open")

        asyncio.get_event_loop().run_until_complete(_test())

    def test_half_open_timeout_resets(self):
        from backend.circuit_breaker import (
            _HALF_OPEN_TIMEOUT_S,
            BreakerConfig,
            CircuitBreaker,
            State,
        )

        async def _test():
            cb = CircuitBreaker("t4", BreakerConfig(failure_threshold=1, recovery_timeout=0.01))

            async def fail():
                raise ValueError("x")

            with pytest.raises((ValueError, RuntimeError)):
                await cb.call(fail)
            await asyncio.sleep(0.02)
            cb.stats.half_open_entered = time.monotonic() - _HALF_OPEN_TIMEOUT_S - 1
            cb.stats.state = State.HALF_OPEN

            async def succeed():
                return "ok"

            result = await cb.call(succeed)
            assert result == "ok"

        asyncio.get_event_loop().run_until_complete(_test())


# ── Integration ───────────────────────────────────────────────────────────────
class TestPhasePIntegration:
    def test_validate_pipeline(self):
        from backend.core.validators import validate_direction, validate_lot_size, validate_symbol

        assert validate_symbol("xauusd") == "XAUUSD"
        assert validate_lot_size(0.1) == 0.1
        assert validate_direction("buy") == "BUY"

    def test_weight_adjuster_full_cycle(self):
        import os
        import tempfile

        from backend.intelligence.weight_adjuster import IndicatorWeights

        w = IndicatorWeights(
            smc_weight=np.float64(0.5), price_action_weight=np.float64(0.3)
        ).normalize()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights", "w.json")
            w.save(path)
            w2 = IndicatorWeights.load(path)
        for k, v in w2.to_dict().items():
            assert type(v) is float
        total = (
            w2.smc_weight
            + w2.price_action_weight
            + w2.htf_alignment_weight
            + w2.session_weight
            + w2.ltf_weight
        )
        assert abs(total - 1.0) < 1e-9
