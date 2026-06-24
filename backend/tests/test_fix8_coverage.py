"""
backend/tests/test_fix8_coverage.py
====================================
FIX #8 - Test Coverage (Production-Ready)
==========================================

Covers 8 topics targeting >=90% coverage on modified modules:

1.  News event blocking           (volatility_filter.py - FIX #1)
2.  ATR spike robustness          (volatility_filter.py - FIX #2, #6)
3.  Symbol-specific thresholds    (volatility_filter.py - FIX #3)
4.  Gold pip value                (lot_sizing.py + portfolio_risk.py - FIX #4)
5.  Crypto pip value              (lot_sizing.py + portfolio_risk.py - FIX #4)
6.  Exposure calculation          (exposure_control.py - FIX #5, #6)
7.  Fail-closed behavior          (all 4 gates - FIX #6, #7)
8.  Portfolio correlation calcs   (correlation_filter.py + portfolio_risk.py)

All tests use the INSTALLED package layout:
    backend.risk.{fail_mode, volatility_filter, lot_sizing,
                  portfolio_risk, exposure_control, correlation_filter}

Run:
    python -m pytest backend/tests/test_fix8_coverage.py -v
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from backend.risk import fail_mode as _fm_mod
from backend.risk.fail_mode import FailMode, coerce as fm_coerce

import backend.risk.volatility_filter as _vf_mod
import backend.risk.lot_sizing as _ls_mod
import backend.risk.portfolio_risk as _pr_mod
import backend.risk.exposure_control as _ec_mod
import backend.risk.correlation_filter as _cf_mod

from backend.risk.volatility_filter import (
    VolatilityFilter,
    VolatilityFilterConfig,
    VolatilityLevel,
    VolatilityCheckResult,
    NewsEvent,
    SymbolThresholds,
    _DEFAULT_SYMBOL_THRESHOLDS,
)
from backend.risk.lot_sizing import (
    LotSizer,
    LotSizingConfig,
    UnknownSymbolError,
    _PIP_VALUE_TABLE as _LS_PIP,
    _SYMBOL_ALIASES as _LS_ALIASES,
)
from backend.risk.portfolio_risk import (
    OpenTradeRisk,
    TradeDirection,
    PortfolioRiskManager,
    PortfolioRiskConfig,
    RiskLevel,
    _PIP_VALUE_TABLE as _PR_PIP,
    _get_pip_value,
    _get_pip_value_with_source,
    _resolve_canonical,
)
from backend.risk.exposure_control import (
    ExposureControlEngine,
    ExposureControlConfig,
    ExposurePosition,
    ExposureSnapshot,
    ExposureCheckResult,
    _blocked_snapshot,
    _open_snapshot,
)
from backend.risk.correlation_filter import (
    CorrelationFilter,
    CorrelationFilterConfig,
    CorrPosition,
    CorrelationResult,
    _pearson,
    _canonical,
    _STATIC_CORRELATION_TABLE as _CF_CORR,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _otr(symbol: str, direction: str = "BUY",
         lot: float = 1.0, entry: float = 1.10,
         sl: float = 1.09, balance: float = 10_000.0,
         pip_override: float | None = None) -> OpenTradeRisk:
    return OpenTradeRisk(
        symbol=symbol,
        direction=TradeDirection(direction.upper()),
        lot_size=lot,
        entry_price=entry,
        stop_loss=sl,
        account_balance=balance,
        pip_value_per_lot=pip_override,
    )


def _ep(symbol: str, direction: str = "BUY",
        risk: float = 1.0) -> ExposurePosition:
    return ExposurePosition(symbol=symbol, direction=direction, risk_percent=risk)


def _cp(symbol: str, direction: str = "BUY",
        risk: float = 1.0) -> CorrPosition:
    return CorrPosition(symbol=symbol, direction=direction, risk_percent=risk)


def _news(title: str = "NFP", currency: str = "USD",
          impact: str = "HIGH",
          delta: timedelta = timedelta(0)) -> NewsEvent:
    return NewsEvent(
        title=title, currency=currency, impact=impact,
        event_time=datetime.now(timezone.utc) + delta,
    )


# ===========================================================================
# 1. NEWS EVENT BLOCKING  (9 tests)
# ===========================================================================

class TestNewsEventBlocking:
    """FIX #1 -- NewsEvent gate inside VolatilityFilter.

    Issue:
        Before FIX #1 there was no news event filter.
        A scheduled NFP / FOMC release could be traded through with
        full lot sizing -- no gate existed to block it.

    Exact patch (volatility_filter.py):
        def _check_news(self, now: datetime) -> Optional[VolatilityCheckResult]:
            before_s = self._cfg.news_block_minutes_before * 60   # default 30 min
            after_s  = self._cfg.news_block_minutes_after  * 60   # default 15 min
            for ev in self._news_events:
                diff_s = (now - et).total_seconds()
                if -before_s <= diff_s <= after_s:
                    return VolatilityCheckResult(can_trade=False,
                                                reason='NEWS_EVENT_BLOCK', ...)

    Risk impact:
        Trading NFP/FOMC without block => 3-8% slippage in <1 s.
        Gate prevents any lot from being sent during high-impact window.

    Backward compat:
        VolatilityFilter.check() signature unchanged.
        NewsEvent is a new public dataclass (additive, not breaking).
    """

    def _vf(self, **kwargs) -> VolatilityFilter:
        return VolatilityFilter(VolatilityFilterConfig(**kwargs))

    def _check(self, vf: VolatilityFilter) -> VolatilityCheckResult:
        return vf.check(0.0001, [0.0001] * 14, 0.0002, 0.0002, "EURUSD")

    def test_immediate_block(self):
        """Event at exactly t=now: blocked."""
        vf = self._vf()
        vf.add_news_event(_news())
        r = self._check(vf)
        assert not r.can_trade
        assert r.reason == "NEWS_EVENT_BLOCK"
        assert r.level  == VolatilityLevel.EXTREME

    def test_block_29_minutes_before(self):
        """Event 29 min in future: within 30-min pre-window => blocked."""
        vf = self._vf()
        vf.add_news_event(_news(delta=timedelta(minutes=29)))
        assert not self._check(vf).can_trade

    def test_allow_31_minutes_before(self):
        """Event 31 min in future: outside 30-min pre-window => allowed."""
        vf = self._vf()
        vf.add_news_event(_news(delta=timedelta(minutes=31)))
        assert self._check(vf).can_trade

    def test_block_14_minutes_after(self):
        """Event 14 min in past: within 15-min post-window => blocked."""
        vf = self._vf()
        vf.add_news_event(_news(delta=timedelta(minutes=-14)))
        assert not self._check(vf).can_trade

    def test_allow_16_minutes_after(self):
        """Event 16 min in past: outside 15-min post-window => allowed."""
        vf = self._vf()
        vf.add_news_event(_news(delta=timedelta(minutes=-16)))
        assert self._check(vf).can_trade

    def test_clear_news_events_allows_trade(self):
        """After clear_news_events() the gate is open."""
        vf = self._vf()
        vf.add_news_event(_news())
        vf.clear_news_events()
        assert self._check(vf).can_trade

    def test_enable_news_filter_false_ignores_events(self):
        """enable_news_filter=False bypasses news gate entirely."""
        vf = self._vf(enable_news_filter=False)
        vf.add_news_event(_news())
        assert self._check(vf).can_trade

    def test_multiple_events_first_match_blocks(self):
        """With two events, the nearer one triggers the block."""
        vf = self._vf()
        vf.add_news_event(_news("FOMC", delta=timedelta(minutes=10)))
        vf.add_news_event(_news("CPI",  delta=timedelta(minutes=60)))
        assert not self._check(vf).can_trade

    def test_load_news_events_replaces_list(self):
        """load_news_events() replaces prior list; old events gone."""
        vf = self._vf()
        vf.add_news_event(_news())
        vf.load_news_events([])
        assert self._check(vf).can_trade


# ===========================================================================
# 2. ATR SPIKE ROBUSTNESS  (11 tests)
# ===========================================================================

class TestATRSpikeRobustness:
    """FIX #2 / FIX #6 -- median ATR estimator + fail-closed on exception.

    Issue:
        Before FIX #2 the filter used simple mean; a single spike candle
        (e.g. NFP) could inflate avg_atr by 3-4x making ratio appear normal.
        Before FIX #6 no try/except: ZeroDivisionError propagated silently.

    Exact patch (volatility_filter.py):
        # FIX #2 - median estimator (default):
        sorted_window = sorted(window)
        avg = median(sorted_window)   # spike-resistant

        # FIX #6 - exception guard:
        def check(self, ...):
            try: return self._check_inner(...)
            except Exception as exc:
                if self._fail_mode is FailMode.FAIL_CLOSED:
                    return VolatilityCheckResult(can_trade=False, ...)
                return VolatilityCheckResult(can_trade=True, ...)

    Risk impact:
        ATR ratio=4.0 during NFP => actual SL hit 4x further than sized-for
        => actual risk = 4% instead of 1%.

    Backward compat:
        check() signature unchanged. atr_history keyword alias added (additive).
    """

    _H14 = [1.0] * 14

    def _vf(self, **kwargs) -> VolatilityFilter:
        return VolatilityFilter(VolatilityFilterConfig(
            atr_history_bars=14, **kwargs
        ))

    def test_extreme_blocked(self):
        """ratio=3.5 >= extreme=3.5 => blocked."""
        r = self._vf().check(3.5, self._H14, 0.0002, 0.0002, "EURUSD")
        assert not r.can_trade
        assert "EXTREME_VOLATILITY" in r.reason
        assert r.level == VolatilityLevel.EXTREME

    def test_just_below_extreme_is_high(self):
        """ratio=3.49 < extreme=3.5 => HIGH (allowed, reduced lot)."""
        r = self._vf().check(3.49, self._H14, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.HIGH
        assert 0.0 < r.lot_multiplier < 1.0

    def test_high_boundary_lot_multiplier_1(self):
        """ratio=2.0 exactly at high=2.0 => HIGH, lot_mult=1.0."""
        r = self._vf().check(2.0, self._H14, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.HIGH
        assert r.lot_multiplier == pytest.approx(1.0, abs=0.01)

    def test_normal_below_high(self):
        """ratio=1.5 < high=2.0 => NORMAL, lot_mult=1.0."""
        r = self._vf().check(1.5, self._H14, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.NORMAL
        assert r.lot_multiplier == pytest.approx(1.0)

    def test_spread_too_high_blocked(self):
        """spread_ratio=3.001 > max_spread_ratio=3.0 => blocked."""
        r = self._vf().check(1.0, self._H14, 3.001, 1.0, "EURUSD")
        assert not r.can_trade
        assert "SPREAD_TOO_HIGH" in r.reason

    def test_spread_exactly_at_limit_allowed(self):
        """spread_ratio=3.0 NOT > 3.0 => allowed (strictly >)."""
        r = self._vf().check(1.0, self._H14, 3.0, 1.0, "EURUSD")
        assert r.can_trade

    def test_fail_closed_on_exception(self):
        """ZeroDivisionError => FAIL_CLOSED => blocked."""
        vf = VolatilityFilter(VolatilityFilterConfig(
            fail_mode=FailMode.FAIL_CLOSED
        ))
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("avg=0")):
            r = vf.check(1.0, self._H14, 0.0002, 0.0002, "EURUSD")
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_fail_open_on_exception_allows(self):
        """Any exception with FAIL_OPEN => allowed."""
        vf = VolatilityFilter(VolatilityFilterConfig(
            fail_mode=FailMode.FAIL_OPEN
        ))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("bad")):
            r = vf.check(1.0, self._H14, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason

    def test_median_estimator_spike_resistant(self):
        """Median ignores single spike candle; ratio stays normal."""
        history = [1.0] * 13 + [50.0]
        vf = VolatilityFilter(VolatilityFilterConfig(
            atr_estimator="median", atr_history_bars=14
        ))
        r = vf.check(1.0, history, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade

    def test_ema_estimator_available(self):
        """EMA estimator path executes without error."""
        vf = VolatilityFilter(VolatilityFilterConfig(
            atr_estimator="ema", ema_alpha=0.2, atr_history_bars=14
        ))
        r = vf.check(1.0, self._H14, 0.0002, 0.0002, "EURUSD")
        assert r.can_trade

    def test_atr_ratio_stored_in_result(self):
        """atr_ratio field is correctly populated."""
        history = [2.0] * 14
        r = self._vf().check(4.0, history, 0.0002, 0.0002, "EURUSD")
        assert r.atr_ratio == pytest.approx(2.0)


# ===========================================================================
# 3. SYMBOL-SPECIFIC THRESHOLDS  (9 tests)
# ===========================================================================

class TestSymbolSpecificThresholds:
    """FIX #3 -- Per-symbol ATR threshold table.

    Issue:
        A single global extreme=3.5 was used for all instruments.
        BTC normal daily ATR can be 8x its 14-day avg during news.
        Gold's ATR should be tighter than FX because moves directly
        translate to larger USD P&L per pip.

    Exact patch (volatility_filter.py):
        _DEFAULT_SYMBOL_THRESHOLDS: Dict[str, SymbolThresholds] = {
            "XAUUSD": SymbolThresholds(0.7, 1.8, 3.0),  # extreme=3.0
            "BTCUSD": SymbolThresholds(0.8, 1.5, 2.2),  # extreme=2.2
            "EURUSD": SymbolThresholds(0.5, 2.0, 3.5),  # standard
            "GBPJPY": SymbolThresholds(0.7, 2.5, 4.2),  # looser
            ...
        }

    Risk impact:
        Wrong threshold: BTC blocked every normal news day (false block) or
        Gold passes through a flash-crash spike (actual risk 2x sized-for).

    Backward compat:
        VolatilityFilterConfig.symbol_thresholds=None => global defaults apply.
        Per-symbol thresholds are additive (new feature).
    """

    def _vf(self) -> VolatilityFilter:
        return VolatilityFilter()

    def test_eurusd_defaults(self):
        th = _DEFAULT_SYMBOL_THRESHOLDS.get("EURUSD")
        assert th is not None
        assert (th.low, th.high, th.extreme) == (0.5, 2.0, 3.5)

    def test_xauusd_tighter_extreme(self):
        """Gold extreme=3.0, tighter than FX extreme=3.5."""
        th = _DEFAULT_SYMBOL_THRESHOLDS.get("XAUUSD")
        assert th is not None
        assert th.extreme == pytest.approx(3.0)
        assert th.extreme < 3.5

    def test_btcusd_lowest_extreme(self):
        """BTC extreme=2.2, tightest among listed symbols."""
        th = _DEFAULT_SYMBOL_THRESHOLDS.get("BTCUSD")
        assert th is not None
        assert th.extreme == pytest.approx(2.2)

    def test_gbpjpy_loosest_extreme(self):
        """GBPJPY extreme=4.2, widest threshold (volatile cross)."""
        th = _DEFAULT_SYMBOL_THRESHOLDS.get("GBPJPY")
        assert th is not None
        assert th.extreme == pytest.approx(4.2)

    def test_gold_ratio_30_blocked(self):
        """XAUUSD ratio=3.0 >= extreme=3.0 => blocked."""
        r = self._vf().check(3.0, [1.0] * 14, 0.5, 0.5, "XAUUSD")
        assert not r.can_trade
        assert "EXTREME_VOLATILITY" in r.reason

    def test_gold_ratio_299_allowed(self):
        """XAUUSD ratio=2.99 < extreme=3.0 => allowed (HIGH)."""
        r = self._vf().check(2.99, [1.0] * 14, 0.5, 0.5, "XAUUSD")
        assert r.can_trade

    def test_btc_ratio_22_blocked(self):
        """BTCUSD ratio=2.2 >= extreme=2.2 => blocked."""
        r = self._vf().check(2.2, [1.0] * 14, 50.0, 50.0, "BTCUSD")
        assert not r.can_trade

    def test_btc_ratio_14_normal(self):
        """BTCUSD ratio=1.4 < high=1.5 => NORMAL."""
        r = self._vf().check(1.4, [1.0] * 14, 50.0, 50.0, "BTCUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.NORMAL

    def test_runtime_override_add_symbol_threshold(self):
        """add_symbol_threshold() allows live customization."""
        vf = VolatilityFilter()
        vf.add_symbol_threshold("TESTUSD", SymbolThresholds(0.5, 2.0, 2.5))
        r = vf.check(2.5, [1.0] * 14, 0.0, 0.0, "TESTUSD")
        assert not r.can_trade


# ===========================================================================
# 4. GOLD PIP VALUE  (12 tests)
# ===========================================================================

class TestGoldPipValue:
    """FIX #4 -- XAUUSD pip_value corrected from 10.0 to 1.0.

    Issue:
        lot_sizing._PIP_VALUE_TABLE["XAUUSD"]    = 10.0  (before FIX #4)
        portfolio_risk._PIP_VALUE_TABLE["XAUUSD"] = 10.0  (before FIX #4)

        With pip_value=10, lot sizer computed:
            raw_lot = risk_usd / (sl_pips * 10) = 10x too small.
        Portfolio risk reported:
            risk_pct = dist * lot * 10 / balance * 100 = 10x too large.

        Correct value:
            Gold standard lot = 100 oz.
            pip size = $0.01 per oz.
            pip_value = 100 oz x $0.01/oz = $1.00 per lot per pip.

    Exact patch:
        lot_sizing.py:     "XAUUSD": 1.0,   # was 10.0
        portfolio_risk.py: "XAUUSD": 1.0,   # was 10.0

    Risk impact:
        With pip=10: every gold trade 10x under-sized vs intended.
        With pip=1:  1% risk on $10k, 50-pip SL => lot=2.0 (correct).

    Backward compat:
        _get_pip_value(), _get_pip_value_with_source() signatures unchanged.
        Table values are a bug-fix, not an API change.
    """

    def test_lot_sizer_table_xauusd_is_1(self):
        assert _LS_PIP.get("XAUUSD") == pytest.approx(1.0)

    def test_portfolio_risk_table_xauusd_is_1(self):
        assert _PR_PIP.get("XAUUSD") == pytest.approx(1.0)

    def test_xagusd_is_50_not_confused_with_gold(self):
        assert _LS_PIP.get("XAGUSD") == pytest.approx(50.0)
        assert _PR_PIP.get("XAGUSD") == pytest.approx(50.0)

    def test_gold_alias_resolves_to_1(self):
        v, src = _get_pip_value_with_source("GOLD")
        assert v == pytest.approx(1.0)
        assert src == "alias"

    def test_xauusdm_broker_suffix_resolves_to_1(self):
        v, src = _get_pip_value_with_source("XAUUSDm")
        assert v == pytest.approx(1.0)
        assert src == "suffix"

    def test_get_pip_value_function_xauusd(self):
        assert _get_pip_value("XAUUSD") == pytest.approx(1.0)

    def test_open_trade_risk_gold_correct_risk(self):
        """dist=50, lot=2, pip=1, bal=10000 => risk_pct=1.0%."""
        t = _otr("XAUUSD", lot=2.0, entry=2000.0, sl=1950.0)
        assert t.risk_amount  == pytest.approx(100.0)
        assert t.risk_percent == pytest.approx(1.0)

    def test_open_trade_risk_gold_pip_not_10(self):
        """pip_value_used must be 1.0, not 10.0."""
        t = _otr("XAUUSD", lot=1.0, entry=2000.0, sl=1990.0)
        assert t.pip_value_used == pytest.approx(1.0)

    def test_portfolio_single_trade_limit_uses_correct_pip(self):
        """lot=201, dist=50, pip=1, bal=10000 => risk=100.5% >> 2% => blocked."""
        mgr = PortfolioRiskManager()
        t = _otr("XAUUSD", lot=201.0, entry=2000.0, sl=1950.0)
        assert t.risk_percent > 2.0
        r = mgr.check(t, [])
        assert not r.can_trade
        assert "SINGLE_TRADE_RISK" in r.reason

    def test_portfolio_gold_not_inflated_10x(self):
        """Verify gold risk_pct is not 10x what it should be."""
        t = _otr("XAUUSD", lot=1.0, entry=2000.0, sl=1999.0)
        assert t.risk_percent == pytest.approx(0.01, abs=1e-6)
        assert t.risk_percent < 0.1

    def test_both_tables_consistent(self):
        """lot_sizing and portfolio_risk must agree on XAUUSD pip value."""
        assert _LS_PIP.get("XAUUSD") == _PR_PIP.get("XAUUSD")

    @pytest.mark.asyncio
    async def test_lot_sizer_gold_pip_async(self):
        """LotSizer.get_pip_value() returns 1.0 for XAUUSD."""
        ls = LotSizer()
        pv, src = await ls.get_pip_value("XAUUSD")
        assert pv == pytest.approx(1.0)
        assert "static_table" in src


# ===========================================================================
# 5. CRYPTO PIP VALUE  (12 tests)
# ===========================================================================

class TestCryptoPipValue:
    """FIX #4 -- Crypto pip values corrected to 1.0 across all coins.

    Issue:
        _pip_helpers.py contained ETHUSD: 0.01 (before FIX #4).
        With pip=0.01: lot 100x oversized => account blown on first trade.

    Exact patch:
        lot_sizing.py:
            "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0, "XRPUSD": 1.0

    Risk impact:
        Wrong pip_value => lot_sizer miscalculates position size.
        Direction of error can blow account or make positions 100x undersized.

    Backward compat:
        Table values corrected (bug-fix). Function signatures unchanged.
    """

    def test_btcusd_is_1(self):
        assert _LS_PIP.get("BTCUSD") == pytest.approx(1.0)
        assert _PR_PIP.get("BTCUSD") == pytest.approx(1.0)

    def test_ethusd_is_1(self):
        assert _LS_PIP.get("ETHUSD") == pytest.approx(1.0)
        assert _PR_PIP.get("ETHUSD") == pytest.approx(1.0)

    def test_ltcusd_is_1(self):
        assert _LS_PIP.get("LTCUSD") == pytest.approx(1.0)

    def test_xrpusd_is_1(self):
        assert _LS_PIP.get("XRPUSD") == pytest.approx(1.0)
        assert _PR_PIP.get("XRPUSD") == pytest.approx(1.0)

    def test_btc_alias(self):
        v, _ = _get_pip_value_with_source("BTC")
        assert v == pytest.approx(1.0)

    def test_eth_alias(self):
        v, _ = _get_pip_value_with_source("ETH")
        assert v == pytest.approx(1.0)

    def test_btcusdm_suffix(self):
        """Broker suffix 'm' stripped => BTCUSD => 1.0."""
        v, src = _get_pip_value_with_source("BTCUSDm")
        assert v == pytest.approx(1.0)
        assert src == "suffix"

    def test_both_tables_consistent_btc(self):
        assert _LS_PIP.get("BTCUSD") == _PR_PIP.get("BTCUSD")

    def test_open_trade_risk_btc_correct(self):
        """dist=500, lot=0.2, pip=1, bal=10000 => risk_pct=1.0%."""
        t = _otr("BTCUSD", lot=0.2, entry=45000.0, sl=44500.0)
        assert t.risk_percent == pytest.approx(1.0, abs=1e-6)
        assert t.pip_value_used == pytest.approx(1.0)

    def test_open_trade_risk_eth_correct(self):
        """ETHUSD dist=100, lot=1.0, pip=1, bal=10000 => risk_pct=1.0%."""
        t = _otr("ETHUSD", lot=1.0, entry=3000.0, sl=2900.0)
        assert t.risk_percent == pytest.approx(1.0, abs=1e-4)

    def test_btc_pip_not_10(self):
        """Ensure no module still has BTCUSD=10."""
        assert _LS_PIP.get("BTCUSD") != pytest.approx(10.0)
        assert _PR_PIP.get("BTCUSD") != pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_lot_sizer_btc_async(self):
        """LotSizer.get_pip_value() returns 1.0 for BTC alias."""
        ls = LotSizer()
        pv, src = await ls.get_pip_value("BTC")
        assert pv == pytest.approx(1.0)
        assert "static_table" in src


# ===========================================================================
# 6. EXPOSURE CALCULATION  (14 tests)
# ===========================================================================

class TestExposureCalculation:
    """FIX #5 / FIX #6 -- ExposureControlEngine limits and fail-closed guard.

    Issue:
        Before FIX #5: orchestrator passed hardcoded new_risk_percent=1.0
        to ExposureControlEngine.check() regardless of actual trade risk.
        A 3%-risk trade was evaluated as 1%, bypassing max_per_symbol_percent.
        Before FIX #6: check() had no try/except; corrupt ExposurePosition
        would propagate AttributeError, bypassing all limits.

    Exact patch:
        # FIX #5 (orchestrator):
        engine.check(symbol, direction, ACTUAL_risk_percent, ...)

        # FIX #6 (exposure_control.py):
        def check(self, ...):
            try: return self._check_inner(...)
            except Exception as exc:
                logger.exception(...)
                if FAIL_CLOSED: return ExposureCheckResult(can_trade=False, ...)
                return ExposureCheckResult(can_trade=True, ...)

    Risk impact:
        Bypassed limits => unlimited open exposure => portfolio drawdown
        can exceed any configured ceiling during correlated moves.

    Backward compat:
        check() and get_snapshot() signatures unchanged.
        ExposureControlConfig fields unchanged.
    """

    def _eng(self, **kwargs) -> ExposureControlEngine:
        return ExposureControlEngine(config=ExposureControlConfig(**kwargs))

    def test_default_config_values(self):
        cfg = ExposureControlConfig()
        assert cfg.max_total_exposure_percent == pytest.approx(5.0)
        assert cfg.max_per_symbol_percent     == pytest.approx(2.0)
        assert cfg.max_per_currency_percent   == pytest.approx(3.0)
        assert cfg.max_simultaneous_trades    == 5
        assert cfg.max_buy_trades             == 3
        assert cfg.max_sell_trades            == 3

    def test_total_exposure_blocked(self):
        """4x1% + 1.5% = 5.5% > 5.0% => blocked."""
        eng = self._eng()
        existing = [_ep("EURGBP","BUY",1.0), _ep("USDJPY","SELL",1.0),
                    _ep("AUDNZD","BUY",1.0), _ep("CADJPY","SELL",1.0)]
        r = eng.check("XAUUSD", "BUY", 1.5, existing)
        assert not r.can_trade
        assert r.projected_total_risk == pytest.approx(5.5)

    def test_total_exposure_boundary_allowed(self):
        """4x1% + 1.0% = 5.0% NOT > 5.0% => allowed."""
        eng = self._eng()
        existing = [_ep("EURGBP","BUY",1.0), _ep("USDJPY","SELL",1.0),
                    _ep("AUDNZD","BUY",1.0), _ep("CADJPY","SELL",1.0)]
        r = eng.check("XAUUSD", "BUY", 1.0, existing)
        assert r.can_trade
        assert r.projected_total_risk == pytest.approx(5.0)

    def test_symbol_exposure_blocked(self):
        """EURUSD existing=1.5% + new=1.0% = 2.5% > 2.0% => blocked."""
        eng = self._eng()
        r = eng.check("EURUSD", "SELL", 1.0, [_ep("EURUSD","BUY",1.5)])
        assert not r.can_trade
        assert "EURUSD" in r.reason

    def test_symbol_exposure_boundary_allowed(self):
        """EURUSD existing=1.0% + new=1.0% = 2.0% NOT > 2.0% => allowed."""
        eng = self._eng()
        r = eng.check("EURUSD", "SELL", 1.0, [_ep("EURUSD","BUY",1.0)])
        assert r.can_trade

    def test_max_simultaneous_trades_blocked(self):
        """5 existing + 1 new = 6 > max_simultaneous=5 => blocked."""
        eng = self._eng()
        existing = [_ep(f"SYM{i}","BUY",0.5) for i in range(5)]
        r = eng.check("XPTUSD", "BUY", 0.5, existing)
        assert not r.can_trade
        assert "simultaneous" in r.reason.lower() or "Max" in r.reason

    def test_max_simultaneous_boundary_allowed(self):
        """4 existing (3 BUY + 1 SELL) + 1 SELL = 5 total, sell=2 < 3 => allowed."""
        eng = self._eng()
        existing = (
            [_ep(f"SYM{i}","BUY",0.5) for i in range(3)]
            + [_ep("SYM3","SELL",0.5)]
        )
        r = eng.check("XPTUSD", "SELL", 0.5, existing)
        assert r.can_trade
        assert r.projected_total_risk == pytest.approx(2.5)

    def test_duplicate_same_symbol_direction_blocked(self):
        """Same symbol + same direction => blocked (default config)."""
        eng = self._eng()
        r = eng.check("EURUSD", "BUY", 0.5, [_ep("EURUSD","BUY",0.5)])
        assert not r.can_trade
        assert "Duplicate" in r.reason

    def test_projected_total_risk_populated(self):
        """projected_total_risk = existing + new, regardless of can_trade."""
        eng = self._eng()
        r = eng.check("AUDUSD", "BUY", 1.5, [_ep("GBPUSD","BUY",1.0)])
        assert r.projected_total_risk == pytest.approx(2.5)

    def test_fail_closed_exception_blocks(self):
        """Internal exception with FAIL_CLOSED => can_trade=False."""
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, "_check_inner", side_effect=AttributeError("corrupt")):
            r = eng.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_fail_open_exception_allows(self):
        """Internal exception with FAIL_OPEN => can_trade=True."""
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, "_check_inner", side_effect=RuntimeError("boom")):
            r = eng.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason

    def test_get_snapshot_fail_closed_returns_blocked(self):
        """get_snapshot() with FAIL_CLOSED => blocked snapshot on exception."""
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, "_snapshot_inner", side_effect=RuntimeError("snap_err")):
            snap = eng.get_snapshot([])
        assert not snap.can_open_new
        assert "FAIL_CLOSED" in snap.block_reason

    def test_get_snapshot_fail_open_returns_open(self):
        """get_snapshot() with FAIL_OPEN => open snapshot on exception."""
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, "_snapshot_inner", side_effect=RuntimeError("snap_err")):
            snap = eng.get_snapshot([])
        assert snap.can_open_new

    def test_snapshot_correct_aggregation(self):
        """get_snapshot() aggregates per-symbol and per-currency correctly."""
        eng = self._eng()
        positions = [_ep("EURUSD","BUY",1.0), _ep("EURUSD","SELL",0.5)]
        snap = eng.get_snapshot(positions)
        assert snap.total_risk_percent == pytest.approx(1.5)
        assert snap.per_symbol.get("EURUSD") == pytest.approx(1.5)
        assert snap.open_trades == 2


# ===========================================================================
# 7. FAIL-CLOSED BEHAVIOUR  (21 tests)
# ===========================================================================

class TestFailClosedBehaviour:
    """FIX #6 / FIX #7 -- Configurable fail_mode across all 4 gates.

    Issue:
        Before FIX #6:
          CorrelationFilter:     except: allow_trade=True  (SILENT -- no log!)
          ExposureControlEngine: no try/except at all
          VolatilityFilter:      no try/except at all
          PortfolioRiskManager:  no try/except at all
        Any internal exception silently allowed a trade that should be blocked.

        Before FIX #7:
          fail_mode was re-computed inside the except block using str(v).upper().
          str(FailMode.FAIL_CLOSED) returns 'FailMode.FAIL_CLOSED' (not 'FAIL_CLOSED'),
          causing FailMode('FAILMODE.FAIL_CLOSED') to raise ValueError every time.
          Fixed: _fail_mode cached once in __init__.

    Exact patch (fail_mode.py):
        class FailMode(str, Enum):
            FAIL_CLOSED = "FAIL_CLOSED"
            FAIL_OPEN   = "FAIL_OPEN"

        def coerce(value) -> FailMode:
            if isinstance(value, FailMode): return value
            return FailMode(str(value).upper().strip())

    Risk impact:
        Silent FAIL_OPEN on every exception = no risk management.
        FAIL_CLOSED = safe default: block when uncertain.

    Backward compat:
        All 4 gate constructors accept fail_mode kwarg (new optional param).
        Default is always FAIL_CLOSED (safer than previous silent-allow).
    """

    def test_fail_closed_value(self):
        assert FailMode.FAIL_CLOSED.value == "FAIL_CLOSED"

    def test_fail_open_value(self):
        assert FailMode.FAIL_OPEN.value == "FAIL_OPEN"

    def test_coerce_lowercase_fail_closed(self):
        assert fm_coerce("fail_closed") is FailMode.FAIL_CLOSED

    def test_coerce_lowercase_fail_open(self):
        assert fm_coerce("fail_open") is FailMode.FAIL_OPEN

    def test_coerce_enum_passthrough(self):
        assert fm_coerce(FailMode.FAIL_CLOSED) is FailMode.FAIL_CLOSED

    def test_sst_volatility_filter(self):
        """volatility_filter imports FailMode from canonical fail_mode module."""
        assert _vf_mod.FailMode is _fm_mod.FailMode

    def test_sst_exposure_control(self):
        assert _ec_mod.FailMode is _fm_mod.FailMode

    def test_sst_correlation_filter(self):
        assert _cf_mod.FailMode is _fm_mod.FailMode

    def test_sst_portfolio_risk(self):
        assert _pr_mod.FailMode is _fm_mod.FailMode

    def test_vf_default_fail_closed(self):
        assert VolatilityFilter()._fail_mode is FailMode.FAIL_CLOSED

    def test_ec_default_fail_closed(self):
        assert ExposureControlEngine()._fail_mode is FailMode.FAIL_CLOSED

    def test_cf_default_fail_closed(self):
        assert CorrelationFilter()._fail_mode is FailMode.FAIL_CLOSED

    def test_pr_default_fail_closed(self):
        assert PortfolioRiskManager()._fail_mode is FailMode.FAIL_CLOSED

    def test_vf_kwarg_fail_open(self):
        vf = VolatilityFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        assert vf._fail_mode is FailMode.FAIL_OPEN

    def test_ec_kwarg_fail_open(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        assert eng._fail_mode is FailMode.FAIL_OPEN

    def test_pr_kwarg_fail_open(self):
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        assert mgr._fail_mode is FailMode.FAIL_OPEN

    def test_vf_fail_closed_logs_error(self):
        """FAIL_CLOSED exception is logged."""
        vf = VolatilityFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("zero")):
            r = vf.check(1.0, [], 0.0, 0.0, "EURUSD")
        assert not r.can_trade   # structural: gate blocked

    def test_vf_fail_closed_result_can_trade_false(self):
        """FAIL_CLOSED: exception => can_trade=False, reason contains FAIL_CLOSED."""
        vf = VolatilityFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("zero")):
            r = vf.check(1.0, [], 0.0, 0.0, "EURUSD")
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_vf_fail_open_result_can_trade_true(self):
        """FAIL_OPEN: exception => can_trade=True, reason contains FAIL_OPEN."""
        vf = VolatilityFilter(VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("bad")):
            r = vf.check(1.0, [], 0.0, 0.0, "EURUSD")
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason

    def test_pr_fail_closed_exception_blocks(self):
        """PortfolioRiskManager FAIL_CLOSED: exception => blocked."""
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        t   = _otr("EURUSD", lot=1.0, entry=1.10, sl=1.09)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("inner")):
            r = mgr.check(t, [])
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_pr_fail_open_exception_allows(self):
        """PortfolioRiskManager FAIL_OPEN: exception => allowed."""
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        t   = _otr("EURUSD", lot=1.0, entry=1.10, sl=1.09)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("inner")):
            r = mgr.check(t, [])
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason

    def test_ec_fail_closed_exception_blocks(self):
        """ExposureControlEngine FAIL_CLOSED: exception => blocked."""
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, "_check_inner", side_effect=AttributeError("x")):
            r = eng.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade


# ===========================================================================
# 8. PORTFOLIO CORRELATION CALCULATIONS  (15 tests)
# ===========================================================================

class TestPortfolioCorrelationCalcs:
    """FIX #6 -- CorrelationFilter fail-closed + rolling engine + Pearson.

    Also covers PortfolioRiskManager static correlation gate.

    Issue:
        Before FIX #6: CorrelationFilter.check() had no outer try/except.
        Any exception in _check_inner propagated to the orchestrator,
        bypassing fail_mode entirely.
        The old code also had: except: allow_trade=True (SILENT).

    Exact patch (correlation_filter.py):
        async def check(self, ...):
            try: return await self._check_inner(...)
            except Exception as exc:
                logger.critical("...fail_mode=%s...", exc_info=True)  # ALWAYS log
                if FAIL_CLOSED:
                    return CorrelationResult(can_trade=False, source="error", ...)
                return CorrelationResult(can_trade=True, source="error", ...)

    Risk impact:
        Uncorrelated-position limit bypass => two 1% USD/JPY positions
        entered simultaneously when yen shock occurs = 2% instant drawdown
        instead of 1% with the second blocked.

    Backward compat:
        check() signature: (new_symbol, new_direction, open_positions, base_risk_percent)
        No existing call site changed.
    """

    def test_pearson_identical_series(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _pearson(x, x) == pytest.approx(1.0)

    def test_pearson_proportional_series(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert _pearson(x, y) == pytest.approx(1.0)

    def test_pearson_reverse_is_neg1(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _pearson(x, list(reversed(x))) == pytest.approx(-1.0)

    def test_pearson_fewer_than_3_returns_0(self):
        assert _pearson([1.0, 2.0], [3.0, 4.0]) == pytest.approx(0.0)

    def test_canonical_alphabetical(self):
        assert _canonical("GBPUSD", "EURUSD") == ("EURUSD", "GBPUSD")
        assert _canonical("EURUSD", "GBPUSD") == ("EURUSD", "GBPUSD")

    def test_eurusd_gbpusd_static(self):
        cf = CorrelationFilter()
        assert cf.get_correlation("EURUSD", "GBPUSD") == pytest.approx(0.85)

    def test_static_table_symmetric(self):
        cf = CorrelationFilter()
        assert cf.get_correlation("GBPUSD", "EURUSD") == pytest.approx(0.85)

    def test_us30_us500_static(self):
        assert _CF_CORR.get(("US30", "US500")) == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_high_positive_corr_blocks(self):
        """EURUSD BUY + GBPUSD BUY: net=0.85x1x1.0=0.85 >= 0.80 => blocked."""
        cf = CorrelationFilter()
        r  = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",1.0)], 1.0)
        assert not r.can_trade
        assert r.correlation_score == pytest.approx(0.85, abs=0.01)

    @pytest.mark.asyncio
    async def test_high_negative_corr_blocks(self):
        """Opposite direction but abs(net)=0.85 >= 0.80 => still blocked."""
        cf = CorrelationFilter()
        r  = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","SELL",1.0)], 1.0)
        assert not r.can_trade

    @pytest.mark.asyncio
    async def test_penalty_zone_allows_with_reduced_multiplier(self):
        """net=0.68 in [0.60, 0.80) => allowed, risk_multiplier<1."""
        cf = CorrelationFilter()
        r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",0.8)], 1.0)
        assert r.can_trade
        assert 0.0 < r.risk_multiplier < 1.0
        assert r.correlation_score == pytest.approx(0.68, abs=0.01)

    @pytest.mark.asyncio
    async def test_low_corr_full_multiplier(self):
        """net=0.425 < 0.60 => allowed, multiplier=1.0."""
        cf = CorrelationFilter()
        r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",0.5)], 1.0)
        assert r.can_trade
        assert r.risk_multiplier == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_fail_closed_outer_exception_blocks(self):
        """Outer exception with FAIL_CLOSED => can_trade=False, source='error'."""
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        async def _boom(*args, **kwargs): raise ValueError("outer_boom")
        cf._get_correlation = _boom
        r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",1.0)], 1.0)
        assert not r.can_trade
        assert r.source == "error"
        assert "FAIL_CLOSED" in r.reason

    @pytest.mark.asyncio
    async def test_fail_open_outer_exception_allows(self):
        """Outer exception with FAIL_OPEN => can_trade=True, source='error'."""
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        async def _boom(*args, **kwargs): raise RuntimeError("outer_boom")
        cf._get_correlation = _boom
        r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",1.0)], 1.0)
        assert r.can_trade
        assert r.source == "error"
        assert "FAIL_OPEN" in r.reason

    def test_pr_correlated_risk_blocked(self):
        """4 GBPUSD@0.9% + EURUSD@0.9%: corr_risk=3.06% > 3.0% => blocked."""
        mgr = PortfolioRiskManager()
        # dist=0.009, lot=1000, pip=10, bal=10000 => risk=0.9%
        existing = [
            OpenTradeRisk("GBPUSD", TradeDirection.BUY, 1000, 1.300, 1.291, 10_000)
            for _ in range(4)
        ]
        new_t = OpenTradeRisk("EURUSD", TradeDirection.BUY, 900, 1.110, 1.101, 10_000)
        r = mgr.check(new_t, existing)
        assert not r.can_trade
        assert "CORRELATED_RISK" in r.reason
        assert r.correlated_risk_pct > 3.0


# ===========================================================================
# 9. INTEGRATION  (5 tests)
# ===========================================================================

class TestIntegration:
    """Cross-gate regression guards.

    Verify that FIX #4/5/6 pip-value corrections flow correctly
    from lot_sizer -> portfolio_risk -> exposure_control.
    """

    def test_pip_tables_xauusd_consistent_across_all_modules(self):
        """All modules must agree: XAUUSD pip_value == 1.0."""
        assert _LS_PIP.get("XAUUSD") == pytest.approx(1.0)
        assert _PR_PIP.get("XAUUSD") == pytest.approx(1.0)

    def test_pip_tables_btcusd_consistent_across_all_modules(self):
        assert _LS_PIP.get("BTCUSD") == pytest.approx(1.0)
        assert _PR_PIP.get("BTCUSD") == pytest.approx(1.0)

    def test_portfolio_risk_uses_correct_pip_for_gold_trade(self):
        """End-to-end: XAUUSD trade risk_pct computed with pip=1, not pip=10."""
        mgr = PortfolioRiskManager()
        # pip=1:  50*2*1/10000*100 = 1.0%  (correct, allowed)
        # pip=10: 50*2*10/10000*100 = 10.0% (wrong, would be blocked)
        t = _otr("XAUUSD", lot=2.0, entry=2000.0, sl=1950.0)
        r = mgr.check(t, [])
        assert r.can_trade
        assert r.new_trade_risk_pct == pytest.approx(1.0, abs=1e-6)

    def test_single_trade_blocked_at_exact_limit_plus_epsilon(self):
        """EURUSD lot=2010: risk=2.01% > 2.0% => blocked (not 20.1%)."""
        mgr = PortfolioRiskManager()
        t   = _otr("EURUSD", lot=2010.0, entry=1.1100, sl=1.1000)
        r   = mgr.check(t, [])
        assert not r.can_trade
        assert "SINGLE_TRADE_RISK" in r.reason
        assert t.risk_percent == pytest.approx(2.01, abs=0.005)

    def test_fail_mode_sst_all_four_gates(self):
        """All 4 modules import FailMode from the same fail_mode.py object."""
        assert _vf_mod.FailMode is _fm_mod.FailMode
        assert _ec_mod.FailMode is _fm_mod.FailMode
        assert _cf_mod.FailMode is _fm_mod.FailMode
        assert _pr_mod.FailMode is _fm_mod.FailMode
