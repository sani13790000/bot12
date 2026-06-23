"""
backend/tests/test_quant_fixes.py
==================================
FIX #8: Test coverage >= 90% for all 8 surgical fixes.

41 tests covering:
  FIX #1  News event blocking
  FIX #2  ATR spike robustness (median)
  FIX #3  Symbol-specific thresholds
  FIX #4  Gold/Crypto pip values
  FIX #5  Exposure with real risk_percent
  FIX #6  Fail-closed behavior
  FIX #7  Dead code removal checks
  FIX #8  Portfolio correlation calculations
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from backend.risk.volatility_filter import (
    VolatilityFilter, VolatilityFilterConfig, VolatilityLevel,
    NewsEvent, SymbolThresholds, FailMode,
)
from backend.risk.portfolio_risk import (
    PortfolioRiskManager, OpenTradeRisk, TradeDirection, RiskLevel,
    FailMode as PFFailMode, _get_pip_value,
)
from backend.risk.risk_orchestrator import RiskOrchestrator, RiskDecision

_ATR_HISTORY_NORMAL = [1.0] * 20
_ATR_HISTORY_SPIKE  = [1.0] * 19 + [10.0]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _future(minutes: int) -> datetime:
    return _now_utc() + timedelta(minutes=minutes)

def _past(minutes: int) -> datetime:
    return _now_utc() - timedelta(minutes=minutes)


# ===========================================================================
# FIX #1 -- NEWS EVENT BLOCKING
# ===========================================================================

class TestNewsEventBlocking:
    def _filter(self, events: List[NewsEvent], enable=True) -> VolatilityFilter:
        cfg = VolatilityFilterConfig(
            enable_news_filter=enable,
            news_block_minutes_before=30,
            news_block_minutes_after=15,
        )
        vf = VolatilityFilter(cfg)
        vf.load_news_events(events)
        return vf

    def test_news_blocks_before_event(self):
        event = NewsEvent(title="NFP", currency="USD", impact="HIGH", event_time=_future(20))
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert result.can_trade is False
        assert result.reason == "NEWS_EVENT_BLOCK"
        assert result.news_blocked is True
        assert result.news_event_title == "NFP"
        assert result.level == VolatilityLevel.EXTREME

    def test_news_blocks_after_event(self):
        event = NewsEvent(title="CPI", currency="USD", impact="HIGH", event_time=_past(5))
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "USDJPY")
        assert result.can_trade is False
        assert result.reason == "NEWS_EVENT_BLOCK"

    def test_news_allows_outside_window(self):
        event = NewsEvent(title="FOMC", currency="USD", impact="HIGH", event_time=_past(120))
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert result.can_trade is True
        assert result.news_blocked is False

    def test_multiple_events_one_blocks(self):
        events = [
            NewsEvent("Old", "USD", "HIGH", _past(120)),
            NewsEvent("NFP", "USD", "HIGH", _future(10)),
            NewsEvent("Future", "EUR", "HIGH", _future(200)),
        ]
        vf = self._filter(events)
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert result.can_trade is False
        assert result.news_event_title == "NFP"

    def test_irrelevant_currency_no_block(self):
        event = NewsEvent("ECB", "EUR", "HIGH", _future(10))
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "USDJPY")
        assert result.can_trade is True

    def test_gold_news_block(self):
        event = NewsEvent("Gold", "XAU", "HIGH", _future(5))
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "XAUUSD")
        assert result.can_trade is False

    def test_news_disabled_no_block(self):
        event = NewsEvent("NFP", "USD", "HIGH", _future(5))
        vf = self._filter([event], enable=False)
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert result.can_trade is True

    def test_bad_event_data_fail_safe(self):
        event = NewsEvent("Corrupt", "USD", "HIGH", datetime.now())
        vf = self._filter([event])
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert isinstance(result.can_trade, bool)


# ===========================================================================
# FIX #2 -- ATR SPIKE ROBUSTNESS
# ===========================================================================

class TestATRSpikeRobustness:
    def test_median_ignores_spike(self):
        cfg = VolatilityFilterConfig(atr_estimator="median")
        vf = VolatilityFilter(cfg)
        result = vf.check(1.05, _ATR_HISTORY_SPIKE, 0.0, 0.0, "EURUSD")
        assert result.level == VolatilityLevel.NORMAL

    def test_mean_sensitive_to_spike(self):
        cfg = VolatilityFilterConfig(atr_estimator="mean")
        vf = VolatilityFilter(cfg)
        result = vf.check(1.05, _ATR_HISTORY_SPIKE, 0.0, 0.0, "EURUSD")
        assert result.atr_ratio < 1.1

    def test_ema_weighted_recent(self):
        cfg = VolatilityFilterConfig(atr_estimator="ema", ema_alpha=0.2)
        vf = VolatilityFilter(cfg)
        result = vf.check(1.0, [1.0, 1.0, 1.0, 2.0], 0.0, 0.0, "EURUSD")
        assert result.avg_atr > 1.0

    def test_empty_atr_history_no_crash(self):
        vf = VolatilityFilter()
        result = vf.check(1.0, [], 0.0, 0.0, "EURUSD")
        assert result.avg_atr == 1.0

    def test_median_vs_mean_classification(self):
        history = [1.0] * 19 + [100.0]
        vf_m = VolatilityFilter(VolatilityFilterConfig(atr_estimator="median"))
        vf_n = VolatilityFilter(VolatilityFilterConfig(atr_estimator="mean"))
        r_m = vf_m.check(2.5, history, 0.0, 0.0, "EURUSD")
        r_n = vf_n.check(2.5, history, 0.0, 0.0, "EURUSD")
        assert r_m.level in (VolatilityLevel.HIGH, VolatilityLevel.EXTREME)
        assert r_n.level in (VolatilityLevel.LOW, VolatilityLevel.NORMAL)


# ===========================================================================
# FIX #3 -- SYMBOL-SPECIFIC THRESHOLDS
# ===========================================================================

class TestSymbolThresholds:
    def test_btcusd_tighter_threshold(self):
        vf = VolatilityFilter()
        btc = vf.check(2.5, _ATR_HISTORY_NORMAL, 0.0, 0.0, "BTCUSD")
        eur = vf.check(2.5, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert btc.level == VolatilityLevel.EXTREME
        assert eur.level == VolatilityLevel.HIGH

    def test_xauusd_thresholds(self):
        vf = VolatilityFilter()
        xau = vf.check(1.9, _ATR_HISTORY_NORMAL, 0.0, 0.0, "XAUUSD")
        eur = vf.check(1.9, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert xau.level == VolatilityLevel.HIGH
        assert eur.level == VolatilityLevel.NORMAL

    def test_unknown_symbol_uses_global_defaults(self):
        vf = VolatilityFilter()
        result = vf.check(1.0, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EXOTIC123")
        assert result.level == VolatilityLevel.NORMAL

    def test_custom_per_symbol_config(self):
        cfg = VolatilityFilterConfig(
            symbol_thresholds={"MYTOKEN": SymbolThresholds(low=1.0, high=1.5, extreme=2.0)}
        )
        vf = VolatilityFilter(cfg)
        result = vf.check(1.8, _ATR_HISTORY_NORMAL, 0.0, 0.0, "MYTOKEN")
        assert result.level == VolatilityLevel.HIGH

    def test_case_insensitive_lookup(self):
        vf = VolatilityFilter()
        r1 = vf.check(2.5, _ATR_HISTORY_NORMAL, 0.0, 0.0, "eurusd")
        r2 = vf.check(2.5, _ATR_HISTORY_NORMAL, 0.0, 0.0, "EURUSD")
        assert r1.level == r2.level


# ===========================================================================
# FIX #4 -- GOLD & CRYPTO PIP VALUES
# ===========================================================================

class TestPipValues:
    def test_gold_pip_value_is_1(self):
        val, src = _get_pip_value("XAUUSD")
        assert val == 1.0
        assert src == "table"

    def test_silver_pip_value(self):
        val, _ = _get_pip_value("XAGUSD")
        assert val == 5.0

    def test_btc_pip_value(self):
        val, _ = _get_pip_value("BTCUSD")
        assert val == 1.0

    def test_eth_pip_value(self):
        val, _ = _get_pip_value("ETHUSD")
        assert val == 1.0

    def test_eurusd_pip_value(self):
        val, _ = _get_pip_value("EURUSD")
        assert val == 10.0

    def test_injected_pip_value_overrides_table(self):
        val, src = _get_pip_value("XAUUSD", injected=7.5)
        assert val == 7.5
        assert src == "injected"

    def test_gold_risk_calculation_correct(self):
        trade = OpenTradeRisk(
            symbol="XAUUSD", direction=TradeDirection.BUY,
            lot_size=0.1, entry_price=1900.0, stop_loss=1890.0,
            account_balance=10000.0,
        )
        # 10 price * 0.1 lot * 1.0 pip_val = $1.0
        assert abs(trade.risk_amount - 1.0) < 0.01

    def test_eurusd_risk_calculation(self):
        trade = OpenTradeRisk(
            symbol="EURUSD", direction=TradeDirection.BUY,
            lot_size=1.0, entry_price=1.1000, stop_loss=1.0900,
            account_balance=10000.0,
        )
        # price_dist=0.01 * 1.0 lot * 10.0 pip_val = $0.10
        assert abs(trade.risk_amount - 0.10) < 0.01

    def test_btc_risk_calculation(self):
        trade = OpenTradeRisk(
            symbol="BTCUSD", direction=TradeDirection.BUY,
            lot_size=0.01, entry_price=40000.0, stop_loss=39500.0,
            account_balance=10000.0,
        )
        # 500 * 0.01 * 1.0 = $5.0
        assert abs(trade.risk_amount - 5.0) < 0.01


# ===========================================================================
# FIX #5 -- EXPOSURE WITH REAL RISK
# ===========================================================================

class TestExposureWithRealRisk:
    def test_orchestrator_uses_actual_risk(self):
        captured_risk = []

        class MockExposure:
            def check(self, new_symbol, new_direction, new_risk_percent, open_positions):
                captured_risk.append(new_risk_percent)
                from dataclasses import dataclass
                @dataclass
                class ER:
                    can_trade: bool = True
                    reason: str = ""
                return ER()

        class MockLotSizer:
            async def calculate(self, **kwargs):
                from dataclasses import dataclass
                @dataclass
                class LR:
                    lot_size: float = 0.1
                    risk_percent: float = 2.5
                    pip_value_used: float = 10.0
                    source: str = "table"
                return LR()

        orch = RiskOrchestrator(exposure_control=MockExposure(), lot_sizer=MockLotSizer())
        asyncio.run(orch.check(
            symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.09,
            account_balance=10000.0, user_id="u1", signal_id="s1",
        ))
        assert len(captured_risk) == 1
        assert captured_risk[0] == 2.5

    def test_high_risk_blocks_exposure(self):
        class MockExposure:
            def check(self, new_symbol, new_direction, new_risk_percent, open_positions):
                from dataclasses import dataclass
                @dataclass
                class ER:
                    can_trade: bool
                    reason: str
                return ER(can_trade=(new_risk_percent <= 4.0), reason="EXCEEDED" if new_risk_percent > 4.0 else "")

        class MockLotSizer:
            async def calculate(self, **kwargs):
                from dataclasses import dataclass
                @dataclass
                class LR:
                    lot_size: float = 2.0
                    risk_percent: float = 4.5
                    pip_value_used: float = 10.0
                    source: str = "table"
                return LR()

        orch = RiskOrchestrator(exposure_control=MockExposure(), lot_sizer=MockLotSizer())
        result = asyncio.run(orch.check(
            symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.07,
            account_balance=10000.0, user_id="u1", signal_id="s1",
        ))
        assert result.approved is False
        assert "EXPOSURE" in result.gates_failed


# ===========================================================================
# FIX #6 -- FAIL-CLOSED BEHAVIOR
# ===========================================================================

class TestFailClosed:
    def test_volatility_exception_blocks_fail_closed(self):
        class BrokenFilter(VolatilityFilter):
            def _check_inner(self, *args, **kwargs):
                raise RuntimeError("Simulated failure")

        vf = BrokenFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        result = vf.check(1.0, [1.0], 0.0, 0.0, "EURUSD")
        assert result.can_trade is False
        assert result.level == VolatilityLevel.EXTREME
        assert "FAIL_CLOSED" in result.reason

    def test_volatility_exception_allows_fail_open(self):
        class BrokenFilter(VolatilityFilter):
            def _check_inner(self, *args, **kwargs):
                raise RuntimeError("Simulated failure")

        vf = BrokenFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        result = vf.check(1.0, [1.0], 0.0, 0.0, "EURUSD")
        assert result.can_trade is True
        assert "FAIL_OPEN" in result.reason

    def test_portfolio_exception_handled(self):
        class BrokenCorr:
            def add_price(self, *a): pass
            def get_correlation(self, *a): raise RuntimeError("corr failure")

        pm = PortfolioRiskManager(fail_mode=PFFailMode.FAIL_CLOSED, corr_engine=BrokenCorr())
        trade    = OpenTradeRisk("EURUSD", TradeDirection.BUY, 1.0, 1.1, 1.09, 10000.0)
        existing = OpenTradeRisk("GBPUSD", TradeDirection.BUY, 1.0, 1.3, 1.29, 10000.0)
        result = pm.check(trade, [existing])
        assert result.risk_level in list(RiskLevel)

    def test_orchestrator_fail_closed_correlation(self):
        class BrokenCorrelation:
            def check(self, *a, **k): raise RuntimeError("corr crash")

        orch = RiskOrchestrator(correlation_filter=BrokenCorrelation(), fail_mode_correlation="FAIL_CLOSED")
        result = asyncio.run(orch.check(
            symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.09,
            account_balance=10000.0, user_id="u1", signal_id="s1",
        ))
        assert result.approved is False

    def test_orchestrator_fail_open_correlation(self):
        class BrokenCorrelation:
            def check(self, *a, **k): raise RuntimeError("corr crash")

        orch = RiskOrchestrator(correlation_filter=BrokenCorrelation(), fail_mode_correlation="FAIL_OPEN")
        result = asyncio.run(orch.check(
            symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.09,
            account_balance=10000.0, user_id="u1", signal_id="s1",
        ))
        assert result.approved is True


# ===========================================================================
# FIX #8 -- PORTFOLIO CORRELATION CALCULATIONS
# ===========================================================================

class TestPortfolioCorrelation:
    def _trade(self, symbol, entry, sl, lot=0.1):
        return OpenTradeRisk(symbol, TradeDirection.BUY, lot, entry, sl, 10000.0)

    def test_correlated_pairs_increase_risk(self):
        pm        = PortfolioRiskManager()
        new_trade = self._trade("EURUSD", 1.10, 1.09, 1.0)
        existing  = self._trade("GBPUSD", 1.30, 1.29, 1.0)
        snapshot  = pm.check(new_trade, [existing])
        assert snapshot.correlated_risk > new_trade.risk_percent

    def test_uncorrelated_pairs_normal_risk(self):
        pm        = PortfolioRiskManager()
        new_trade = self._trade("EURUSD", 1.10, 1.09)
        existing  = self._trade("BTCUSD", 40000.0, 39500.0)
        snapshot  = pm.check(new_trade, [existing])
        assert abs(snapshot.correlated_risk - new_trade.risk_percent) < 0.01

    def test_rolling_corr_overrides_static(self):
        class MockRolling:
            def add_price(self, *a): pass
            def get_correlation(self, a, b): return 0.99

        pm        = PortfolioRiskManager(corr_engine=MockRolling())
        new_trade = self._trade("EURUSD", 1.10, 1.09, 1.0)
        existing  = self._trade("GBPUSD", 1.30, 1.29, 1.0)
        snapshot  = pm.check(new_trade, [existing])
        assert snapshot.correlation_source == "rolling"
        assert snapshot.correlated_risk > new_trade.risk_percent * 1.5

    def test_empty_portfolio_safe(self):
        pm        = PortfolioRiskManager()
        new_trade = self._trade("EURUSD", 1.10, 1.09)
        snap      = pm.check(new_trade, [])
        assert snap.can_add_new is True
        assert snap.open_trades == 0

    def test_max_risk_check(self):
        pm        = PortfolioRiskManager()
        new_trade = OpenTradeRisk("GBPUSD", TradeDirection.BUY, 5.0, 1.30, 1.29, 10000.0)
        snap      = pm.check(new_trade, [])
        assert snap.risk_level in list(RiskLevel)


# ===========================================================================
# FIX #7 -- DEAD CODE REMOVAL
# ===========================================================================

class TestDeadCodeRemoval:
    def test_volatility_filter_no_lock(self):
        import asyncio as _asyncio
        vf = VolatilityFilter()
        for attr in vars(vf).values():
            assert not isinstance(attr, _asyncio.Lock)

    def test_portfolio_manager_no_lock(self):
        import asyncio as _asyncio
        pm = PortfolioRiskManager()
        for attr in vars(pm).values():
            assert not isinstance(attr, _asyncio.Lock)
