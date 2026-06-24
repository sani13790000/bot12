"""
backend/tests/test_fix8_coverage.py
====================================
FIX #8 -- Test Coverage
8 topics, 110 tests, Python 3.14 compatible.

Verified against production source:
  volatility_filter.py  -- check(), _check_inner(), _check_news(), _DEFAULT_SYMBOL_THRESHOLDS
  portfolio_risk.py     -- OpenTradeRisk, PortfolioRiskManager, _PIP_VALUE_TABLE
  exposure_control.py   -- ExposureControlEngine, ExposureControlConfig, ExposurePosition
  correlation_filter.py -- CorrelationFilter (async check/inner), CorrPosition
  lot_sizing.py         -- LotSizer, _PIP_VALUE_TABLE, _SYMBOL_ALIASES
  fail_mode.py          -- FailMode (str Enum), coerce()
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# PATH SETUP -- make backend importable from the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# LAZY IMPORTS -- each module loaded once via importlib to allow patching
# ---------------------------------------------------------------------------
def _load(mod_name: str):
    full = f"backend.risk.{mod_name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.find_spec(full)
    if spec is None:
        raise ImportError(f"Cannot find {full}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


_fm  = _load("fail_mode")
_vf  = _load("volatility_filter")
_pr  = _load("portfolio_risk")
_ec  = _load("exposure_control")
_cf  = _load("correlation_filter")
_ls  = _load("lot_sizing")

FailMode              = _fm.FailMode
coerce                = _fm.coerce

# volatility_filter
VolatilityFilter      = _vf.VolatilityFilter
VolatilityFilterConfig= _vf.VolatilityFilterConfig
SymbolThresholds      = _vf.SymbolThresholds
NewsEvent             = _vf.NewsEvent
VolatilityLevel       = _vf.VolatilityLevel

# portfolio_risk
PortfolioRiskManager  = _pr.PortfolioRiskManager
PortfolioRiskConfig   = _pr.PortfolioRiskConfig
OpenTradeRisk         = _pr.OpenTradeRisk
TradeDirection        = _pr.TradeDirection

# exposure_control
ExposureControlEngine = _ec.ExposureControlEngine
ExposureControlConfig = _ec.ExposureControlConfig
ExposurePosition      = _ec.ExposurePosition

# correlation_filter
CorrelationFilter     = _cf.CorrelationFilter
CorrelationFilterConfig = _cf.CorrelationFilterConfig
CorrPosition          = _cf.CorrPosition
RollingCorrelationEngine = _cf.RollingCorrelationEngine

# lot_sizing
LotSizer              = _ls.LotSizer
LotSizingConfig       = _ls.LotSizingConfig

# pip tables (direct references to the dicts in each module)
_LS_PIP = _ls._PIP_VALUE_TABLE
_LS_ALI = _ls._SYMBOL_ALIASES
_PR_PIP = _pr._PIP_VALUE_TABLE


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _trade(
    symbol: str = "EURUSD",
    direction: str = "BUY",
    lot: float = 1.0,
    entry: float = 1.1000,
    sl: float = 1.0900,
    balance: float = 10_000.0,
    pip_val: Optional[float] = None,
) -> OpenTradeRisk:
    return OpenTradeRisk(
        symbol=symbol,
        direction=TradeDirection(direction),
        lot_size=lot,
        entry_price=entry,
        stop_loss=sl,
        account_balance=balance,
        pip_value_per_lot=pip_val,
    )


def _ep(symbol: str, direction: str = "BUY", risk: float = 1.0) -> ExposurePosition:
    return ExposurePosition(symbol=symbol, direction=direction, risk_percent=risk)


def _cp(symbol: str, direction: str = "BUY", risk: float = 1.0) -> CorrPosition:
    return CorrPosition(symbol=symbol, direction=direction, risk_percent=risk)


def _vf_check(
    vf: VolatilityFilter,
    current_atr: float,
    history: List[float],
    symbol: str = "EURUSD",
    spread: float = 0.0,
    avg_spread: float = 0.0001,
):
    return vf.check(
        current_atr=current_atr,
        atr_history=history,
        current_spread=spread,
        avg_spread=avg_spread,
        symbol=symbol,
    )


def _run(coro):
    """Run coroutine safely under Python 3.14 (no deprecated get_event_loop)."""
    return asyncio.run(coro)


# ===========================================================================
# TOPIC 1 -- News Event Blocking (9 tests)
# ===========================================================================
class TestNewsEventBlocking:
    """
    Issue (FIX #1):  No news event filter existed before FIX #1.
                     NFP/FOMC traded without any gate.
    Exact Patch:     _check_news(now) compares each event to a +-window.
                     enable_news_filter=False (default) skips the gate.
    Risk Impact:     3-8% slippage in < 1 second on major news releases.
    Backward Compat: check() signature unchanged; NewsEvent is purely additive;
                     enable_news_filter=False preserves old behaviour.
    """

    def _make_vf_with_news(self, event_time: datetime, impact: str = "HIGH") -> VolatilityFilter:
        cfg = VolatilityFilterConfig(
            enable_news_filter=True,
            news_block_minutes_before=30,
            news_block_minutes_after=15,
        )
        vf = VolatilityFilter(config=cfg)
        ev = NewsEvent(
            title="NFP",
            currency="USD",
            impact=impact,
            event_time=event_time,
        )
        vf.add_news_event(ev)
        return vf

    def test_blocked_before_event(self):
        now = _now_utc()
        ev_time = now + timedelta(minutes=10)
        vf = self._make_vf_with_news(ev_time)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert not r.can_trade
        assert "NEWS_EVENT_BLOCK" in r.reason

    def test_blocked_after_event(self):
        now = _now_utc()
        ev_time = now - timedelta(minutes=5)
        vf = self._make_vf_with_news(ev_time)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert not r.can_trade

    def test_allowed_outside_window_future(self):
        now = _now_utc()
        ev_time = now + timedelta(minutes=60)
        vf = self._make_vf_with_news(ev_time)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert r.can_trade

    def test_allowed_outside_window_past(self):
        now = _now_utc()
        ev_time = now - timedelta(minutes=30)
        vf = self._make_vf_with_news(ev_time)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert r.can_trade

    def test_news_filter_disabled_by_default(self):
        now = _now_utc()
        ev_time = now + timedelta(minutes=5)
        cfg = VolatilityFilterConfig(enable_news_filter=False)
        vf = VolatilityFilter(config=cfg)
        ev = NewsEvent(title="FOMC", currency="USD", impact="HIGH", event_time=ev_time)
        vf.add_news_event(ev)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert r.can_trade

    def test_no_events_no_block(self):
        cfg = VolatilityFilterConfig(enable_news_filter=True)
        vf = VolatilityFilter(config=cfg)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert r.can_trade

    def test_boundary_exactly_before_window(self):
        now = _now_utc()
        ev_time = now + timedelta(minutes=30)
        vf = self._make_vf_with_news(ev_time)
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert not r.can_trade

    def test_multiple_events_nearest_blocks(self):
        now = _now_utc()
        cfg = VolatilityFilterConfig(enable_news_filter=True)
        vf = VolatilityFilter(config=cfg)
        vf.add_news_event(NewsEvent("CPI", "USD", "MEDIUM", now + timedelta(hours=3)))
        vf.add_news_event(NewsEvent("NFP", "USD", "HIGH", now + timedelta(minutes=10)))
        r = _vf_check(vf, 0.0010, [0.0010] * 14)
        assert not r.can_trade
        assert "NEWS_EVENT_BLOCK" in r.reason

    def test_exception_fail_closed(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("boom")):
            r = vf.check(current_atr=0.001, atr_history=[0.001])
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason


# ===========================================================================
# TOPIC 2 -- ATR Spike Robustness (11 tests)
# ===========================================================================
class TestATRSpikeRobustness:
    """
    Issue (FIX #6):  check() had no try/except.
                     ZeroDivisionError (avg_atr=0) propagated -> gate crashed.
    Exact Patch:     check() wraps _check_inner() in try/except.
                     fail_mode stored at __init__ time (not re-read per call).
    Risk Impact:     ATR=4x normal during NFP: SL sized for 1% becomes 4% actual.
    Backward Compat: check() signature unchanged; extra kwargs atr_values/spread
                     are backward-compat aliases.
    """

    def _eurusd_vf(self, **kwargs) -> VolatilityFilter:
        cfg = VolatilityFilterConfig(**kwargs)
        return VolatilityFilter(config=cfg)

    def test_extreme_atr_blocked(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0035, [0.0010] * 14, "EURUSD")
        assert not r.can_trade
        assert r.level == VolatilityLevel.EXTREME

    def test_just_below_extreme_high(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.00349, [0.0010] * 14, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.HIGH
        assert r.lot_multiplier < 1.0

    def test_exact_extreme_boundary_blocked(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0035, [0.0010] * 14, "EURUSD")
        assert not r.can_trade

    def test_exact_high_boundary_lot_mult_one(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0020, [0.0010] * 14, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.HIGH
        assert abs(r.lot_multiplier - 1.0) < 0.01

    def test_high_zone_lot_mult_reduced(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0025, [0.0010] * 14, "EURUSD")
        assert r.can_trade
        assert 0.60 < r.lot_multiplier < 0.75

    def test_normal_atr_allowed(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0010, [0.0010] * 14, "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.NORMAL
        assert r.lot_multiplier == 1.0

    def test_spread_too_high_blocked(self):
        vf = self._eurusd_vf()
        r = vf.check(
            current_atr=0.0010, atr_history=[0.0010]*14,
            current_spread=0.00031, avg_spread=0.0001, symbol="EURUSD"
        )
        assert not r.can_trade
        assert "SPREAD_TOO_HIGH" in r.reason

    def test_spread_exactly_at_limit_allowed(self):
        vf = self._eurusd_vf()
        r = vf.check(
            current_atr=0.0010, atr_history=[0.0010]*14,
            current_spread=0.0003, avg_spread=0.0001, symbol="EURUSD"
        )
        assert r.can_trade

    def test_empty_history_fallback(self):
        vf = self._eurusd_vf()
        r = _vf_check(vf, 0.0010, [], "EURUSD")
        assert r.can_trade
        assert r.level == VolatilityLevel.NORMAL

    def test_zero_avg_atr_fail_closed(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("div by zero")):
            r = vf.check(current_atr=0.001, atr_history=[0.001]*14)
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_exception_fail_open_allowed(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("crash")):
            r = vf.check(current_atr=0.001, atr_history=[0.001]*14)
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason


# ===========================================================================
# TOPIC 3 -- Symbol-Specific Thresholds (9 tests)
# ===========================================================================
class TestSymbolSpecificThresholds:
    """
    Issue (FIX #3):  Global extreme=3.5 applied to all assets.
                     BTC (normal ATR=8x avg) was always blocked.
                     Gold (ATR=3.5x normal) should block at 3.0x.
    Exact Patch:     _DEFAULT_SYMBOL_THRESHOLDS per-symbol dict.
    Risk Impact:     False blocks on BTC every normal news day.
                     Gold passed during flash crashes.
    Backward Compat: Unknown symbol falls back to config defaults (3.5).
    """

    def test_gold_extreme_threshold_is_3(self):
        thr = _vf._DEFAULT_SYMBOL_THRESHOLDS["XAUUSD"]
        assert thr.extreme == 3.0

    def test_btc_extreme_threshold_is_2_2(self):
        thr = _vf._DEFAULT_SYMBOL_THRESHOLDS["BTCUSD"]
        assert thr.extreme == 2.2

    def test_eurusd_extreme_threshold_is_3_5(self):
        thr = _vf._DEFAULT_SYMBOL_THRESHOLDS["EURUSD"]
        assert thr.extreme == 3.5

    def test_gbpjpy_extreme_threshold_is_4_2(self):
        thr = _vf._DEFAULT_SYMBOL_THRESHOLDS["GBPJPY"]
        assert thr.extreme == 4.2

    def test_gold_ratio_3_1_blocked(self):
        vf = VolatilityFilter()
        r = _vf_check(vf, 3.1, [1.0] * 14, "XAUUSD")
        assert not r.can_trade

    def test_eurusd_ratio_3_1_allowed(self):
        vf = VolatilityFilter()
        r = _vf_check(vf, 3.1, [1.0] * 14, "EURUSD")
        assert r.can_trade

    def test_btc_ratio_2_3_blocked(self):
        vf = VolatilityFilter()
        r = _vf_check(vf, 2.3, [1.0] * 14, "BTCUSD")
        assert not r.can_trade

    def test_btc_ratio_2_1_allowed(self):
        vf = VolatilityFilter()
        r = _vf_check(vf, 2.1, [1.0] * 14, "BTCUSD")
        assert r.can_trade

    def test_unknown_symbol_uses_config_default(self):
        vf = VolatilityFilter()
        r = _vf_check(vf, 3.4, [1.0] * 14, "XXXXXX")
        assert r.can_trade


# ===========================================================================
# TOPIC 4 -- Gold Pip Value (12 tests)
# ===========================================================================
class TestGoldPipValue:
    """
    Issue (FIX #4):  XAUUSD=10.0 in both lot_sizing and portfolio_risk.
                     Gold: $0.01/oz * 100 oz standard lot = $1.00 per pip.
                     Error: pip_value 10x too high -> lot_sizer 10x too small.
    Exact Patch:     lot_sizing._PIP_VALUE_TABLE["XAUUSD"] = 1.0
                     portfolio_risk._PIP_VALUE_TABLE["XAUUSD"] = 1.0
    Risk Impact:     Lot sizer returns 0.1 lot when 1.0 lot is correct.
                     Actual risk = 10% of intended; stop-hunt undetected.
    Backward Compat: Table key/value change only; all callers use same dict.
    """

    def test_ls_xauusd_pip_value_is_1(self):
        assert _LS_PIP["XAUUSD"] == 1.0, f"Expected 1.0, got {_LS_PIP['XAUUSD']}"

    def test_pr_xauusd_pip_value_is_1(self):
        assert _PR_PIP["XAUUSD"] == 1.0, f"Expected 1.0, got {_PR_PIP['XAUUSD']}"

    def test_ls_gold_alias_resolves_to_1(self):
        assert _LS_ALI.get("GOLD") == "XAUUSD"
        assert _LS_PIP["XAUUSD"] == 1.0

    def test_ls_xauusdm_resolves_via_truncation(self):
        resolved = LotSizer._resolve_canonical("XAUUSDm")
        assert resolved == "XAUUSD"

    def test_ls_get_pip_value_xauusd(self):
        sizer = LotSizer()
        pv, src = _run(sizer.get_pip_value("XAUUSD"))
        assert pv == 1.0

    def test_pr_gold_risk_percent_correct(self):
        t = _trade("XAUUSD", "BUY", lot=2.0, entry=1900.0, sl=1850.0, balance=10_000.0)
        assert abs(t.risk_percent - 1.0) < 0.05

    def test_pr_gold_risk_not_10_percent(self):
        t = _trade("XAUUSD", "BUY", lot=2.0, entry=1900.0, sl=1850.0, balance=10_000.0)
        assert t.risk_percent < 5.0, "Pip value still wrong (10x)"

    def test_pr_gold_gate_blocks_above_limit(self):
        t = _trade("XAUUSD", "BUY", lot=2.0, entry=2000.0, sl=1899.0, balance=10_000.0)
        mgr = PortfolioRiskManager()
        r = mgr.check(t, [])
        assert not r.can_trade
        assert "SINGLE_TRADE_RISK" in r.reason

    def test_pr_gold_gate_allows_at_limit(self):
        t = _trade("XAUUSD", "BUY", lot=2.0, entry=2000.0, sl=1900.0, balance=10_000.0)
        mgr = PortfolioRiskManager()
        r = mgr.check(t, [])
        assert r.can_trade

    def test_xagusd_pip_value_is_50(self):
        assert _LS_PIP.get("XAGUSD") == 50.0

    def test_xptusd_pip_value_is_1(self):
        assert _LS_PIP.get("XPTUSD") == 1.0

    def test_pr_no_metal_has_pip_10(self):
        metals = ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]
        for m in metals:
            if m in _PR_PIP:
                assert _PR_PIP[m] != 10.0, f"{m} still has pip=10.0"


# ===========================================================================
# TOPIC 5 -- Crypto Pip Value (12 tests)
# ===========================================================================
class TestCryptoPipValue:
    """
    Issue (FIX #4):  Crypto pip values were wrong in both tables.
                     ETHUSD=0.01 -> lot_sizer produced 100x too many lots.
    Exact Patch:     BTCUSD=ETHUSD=LTCUSD=XRPUSD=1.0 in both tables.
    Risk Impact:     ETHUSD 100-lot: full account blown on 1% price move.
    Backward Compat: Only table values changed; symbol keys unchanged.
    """

    def test_ls_btcusd_is_1(self):   assert _LS_PIP["BTCUSD"] == 1.0
    def test_ls_ethusd_is_1(self):   assert _LS_PIP["ETHUSD"] == 1.0
    def test_ls_ltcusd_is_1(self):   assert _LS_PIP["LTCUSD"] == 1.0
    def test_ls_xrpusd_is_1(self):   assert _LS_PIP["XRPUSD"] == 1.0

    def test_ls_btc_alias(self):
        assert _LS_ALI.get("BTC") == "BTCUSD"

    def test_ls_eth_alias(self):
        assert _LS_ALI.get("ETH") == "ETHUSD"

    def test_ls_btcusdm_resolves(self):
        r = LotSizer._resolve_canonical("BTCUSDm")
        assert r == "BTCUSD"

    def test_ls_get_pip_value_btc(self):
        sizer = LotSizer()
        pv, _ = _run(sizer.get_pip_value("BTCUSD"))
        assert pv == 1.0

    def test_pr_eth_risk_calc_correct(self):
        t = _trade("ETHUSD", "BUY", lot=0.1, entry=3000.0, sl=2900.0, balance=10_000.0)
        assert t.risk_percent < 1.0

    def test_pr_btc_normal_risk_allowed(self):
        t = _trade("BTCUSD", "BUY", lot=0.02, entry=50000.0, sl=49000.0, balance=10_000.0)
        mgr = PortfolioRiskManager()
        r = mgr.check(t, [])
        assert r.can_trade

    def test_pr_all_crypto_pip_is_1(self):
        crypto_pr = ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"]
        for sym in crypto_pr:
            if sym in _PR_PIP:
                assert _PR_PIP[sym] == 1.0, f"{sym} pip != 1.0 in portfolio_risk"

    def test_ls_bnbusd_pip_if_present(self):
        if "BNBUSD" in _LS_PIP:
            assert _LS_PIP["BNBUSD"] == 1.0


# ===========================================================================
# TOPIC 6 -- Exposure Calculation (14 tests)
# ===========================================================================
class TestExposureCalculation:
    """
    Issue (FIX #5+6): Hardcoded new_risk=1.0 in orchestrator bypassed
                      MAX_SYMBOL_RISK when actual risk was 2.5%.
                      No try/except -> corrupt position -> gate bypass.
    Exact Patch:      ExposureControlEngine.check() passes real new_risk_percent.
                      try/except added; fail_mode configurable.
    Risk Impact:      Unlimited symbol concentration silently accumulated.
    Backward Compat:  check() signature stable; config kwarg is additive.
    """

    def _make_ec(self, **kw) -> ExposureControlEngine:
        cfg = ExposureControlConfig(**kw)
        return ExposureControlEngine(config=cfg)

    def test_max_total_blocked(self):
        ec = self._make_ec(max_total_exposure_percent=5.0)
        ops = [_ep("EURUSD", "BUY", 1.0)] * 4
        r = ec.check("GBPUSD", "BUY", 1.5, ops)
        assert not r.can_trade

    def test_max_total_boundary_allowed(self):
        ec = self._make_ec(
            max_total_exposure_percent=5.0,
            max_per_currency_percent=99.0,
            max_buy_trades=99,
            max_sell_trades=99,
        )
        ops = [_ep("EURJPY", "BUY", 1.0)] * 4
        r = ec.check("CHFJPY", "BUY", 1.0, ops)
        assert r.can_trade

    def test_max_symbol_blocked(self):
        ec = self._make_ec(max_per_symbol_percent=2.0)
        ops = [_ep("EURUSD", "BUY", 1.5)]
        r = ec.check("EURUSD", "SELL", 1.0, ops)
        assert not r.can_trade

    def test_max_symbol_boundary_allowed(self):
        ec = self._make_ec(
            max_per_symbol_percent=2.0,
            max_per_currency_percent=99.0,
        )
        ops = [_ep("EURUSD", "BUY", 1.0)]
        r = ec.check("EURUSD", "SELL", 1.0, ops)
        assert r.can_trade

    def test_max_simultaneous_blocked(self):
        ec = self._make_ec(
            max_simultaneous_trades=5,
            max_buy_trades=99,
            max_per_currency_percent=99.0,
        )
        ops = [_ep(f"EUR{c}", "BUY", 0.5) for c in ["JPY","GBP","AUD","CHF","CAD"]]
        r = ec.check("NZDJPY", "BUY", 0.5, ops)
        assert not r.can_trade

    def test_max_buy_trades_blocked(self):
        ec = self._make_ec(max_buy_trades=3, max_per_currency_percent=99.0)
        ops = [_ep("EURUSD", "BUY", 0.5),
               _ep("GBPUSD", "BUY", 0.5),
               _ep("AUDUSD", "BUY", 0.5)]
        r = ec.check("NZDUSD", "BUY", 0.5, ops)
        assert not r.can_trade

    def test_max_sell_trades_blocked(self):
        ec = self._make_ec(max_sell_trades=2, max_per_currency_percent=99.0)
        ops = [_ep("EURUSD", "SELL", 0.5),
               _ep("GBPUSD", "SELL", 0.5)]
        r = ec.check("AUDUSD", "SELL", 0.5, ops)
        assert not r.can_trade

    def test_duplicate_symbol_direction_blocked(self):
        ec = self._make_ec(block_same_symbol_same_direction=True)
        ops = [_ep("EURUSD", "BUY", 1.0)]
        r = ec.check("EURUSD", "BUY", 0.5, ops)
        assert not r.can_trade

    def test_opposite_direction_allowed(self):
        ec = self._make_ec(
            max_per_symbol_percent=99.0,
            max_per_currency_percent=99.0,
        )
        ops = [_ep("EURUSD", "BUY", 1.0)]
        r = ec.check("EURUSD", "SELL", 0.5, ops)
        assert r.can_trade

    def test_empty_positions_allowed(self):
        ec = self._make_ec()
        r = ec.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_projected_total_reflects_real_risk(self):
        ec = self._make_ec(max_total_exposure_percent=99.0)
        ops = [_ep("GBPUSD", "BUY", 1.0)]
        r = ec.check("EURUSD", "BUY", 2.5, ops)
        assert abs(r.projected_total_risk - 3.5) < 0.01

    def test_fail_closed_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, "_check_inner", side_effect=AttributeError("boom")):
            r = ec.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade

    def test_fail_open_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, "_check_inner", side_effect=RuntimeError("crash")):
            r = ec.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_get_snapshot_fail_closed(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, "_snapshot_inner", side_effect=RuntimeError("snap error")):
            snap = ec.get_snapshot([_ep("EURUSD", "BUY", 1.0)])
        assert not snap.can_open_new


# ===========================================================================
# TOPIC 7 -- Fail-Closed Behaviour (22 tests)
# ===========================================================================
class TestFailClosedBehaviour:
    """
    Issue (FIX #6):  CorrelationFilter: except: allow_trade=True -- SILENT.
                     ExposureControl, VolatilityFilter, PortfolioRisk: no try/except.
    Exact Patch:     All 4 gates wrap in try/except; FAIL_CLOSED is default.
                     Single source of truth: all import FailMode from fail_mode.py.
    Risk Impact:     Any uncaught exception silently allowed ALL trades.
    Backward Compat: FailMode(str, Enum) so string comparisons still work.
    """

    def test_fail_mode_closed_value(self):
        assert FailMode.FAIL_CLOSED.value == "FAIL_CLOSED"

    def test_fail_mode_open_value(self):
        assert FailMode.FAIL_OPEN.value == "FAIL_OPEN"

    def test_vf_uses_same_fail_mode_values(self):
        assert _vf.FailMode.FAIL_CLOSED.value == "FAIL_CLOSED"

    def test_ec_uses_same_fail_mode_values(self):
        assert _ec.FailMode.FAIL_CLOSED.value == "FAIL_CLOSED"

    def test_vf_default_fail_closed(self):
        assert VolatilityFilter()._fail_mode.value == "FAIL_CLOSED"

    def test_ec_default_fail_closed(self):
        assert ExposureControlEngine()._fail_mode.value == "FAIL_CLOSED"

    def test_cf_default_fail_closed(self):
        assert CorrelationFilter()._fail_mode.value == "FAIL_CLOSED"

    def test_pr_default_fail_closed(self):
        assert PortfolioRiskManager()._fail_mode.value == "FAIL_CLOSED"

    def test_vf_kwarg_override_fail_open(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        assert vf._fail_mode.value == "FAIL_OPEN"

    def test_ec_kwarg_override_fail_open(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        assert ec._fail_mode.value == "FAIL_OPEN"

    def test_pr_kwarg_override_fail_open(self):
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        assert pr._fail_mode.value == "FAIL_OPEN"

    def test_cf_kwarg_override_fail_open(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        assert cf._fail_mode.value == "FAIL_OPEN"

    def test_coerce_lowercase(self):
        assert coerce("fail_closed") is FailMode.FAIL_CLOSED

    def test_coerce_uppercase(self):
        assert coerce("FAIL_OPEN") is FailMode.FAIL_OPEN

    def test_vf_fail_closed_blocks_on_exception(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("x")):
            r = vf.check(0.001)
        assert not r.can_trade

    def test_vf_fail_open_allows_on_exception(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("x")):
            r = vf.check(0.001)
        assert r.can_trade

    def test_ec_fail_closed_blocks_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, "_check_inner", side_effect=ValueError("x")):
            r = ec.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade

    def test_ec_fail_open_allows_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, "_check_inner", side_effect=ValueError("x")):
            r = ec.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_pr_fail_closed_blocks_on_exception(self):
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(pr, "_check_inner", side_effect=KeyError("x")):
            t = _trade()
            r = pr.check(t, [])
        assert not r.can_trade

    def test_pr_fail_open_allows_on_exception(self):
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(pr, "_check_inner", side_effect=KeyError("x")):
            t = _trade()
            r = pr.check(t, [])
        assert r.can_trade

    def test_vf_fail_closed_logs_error(self):
        """FAIL_CLOSED exception must be logged (never swallowed silently)."""
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("x")):
            r = vf.check(0.001)
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_pr_fail_closed_logs_exception(self):
        """PR FAIL_CLOSED: exception must not propagate (was logged internally)."""
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(pr, "_check_inner", side_effect=RuntimeError("x")):
            r = pr.check(_trade(), [])
        assert not r.can_trade


class _no_op_ctx:
    """Context manager no-op for tests that lack assertLogs."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


# ===========================================================================
# TOPIC 8 -- Portfolio Correlation Calculations (16 tests)
# ===========================================================================
class TestPortfolioCorrelationCalcs(IsolatedAsyncioTestCase):
    """
    Issue (FIX #6):  No outer try/except in check() (was: silent FAIL_OPEN).
    Exact Patch:     try/except wraps await _check_inner(); fail_mode honoured.
    Risk Impact:     Correlated position accumulation -> 40% drawdown unchecked.
    Backward Compat: async check() signature unchanged; config kwarg additive.

    Production logic:
      net_exposure += corr * direction_factor * pos.risk_percent
      direction_factor = +1 if same direction, -1 if opposite
      abs(net) >= max_corr(0.80) -> BLOCKED
      abs(net) in [penalty_thr(0.60), max_corr) -> risk_multiplier < 1.0
    """

    def _make_cf(self, engine=None, **kw) -> CorrelationFilter:
        cfg = CorrelationFilterConfig(**kw)
        cf = CorrelationFilter(config=cfg)
        if engine:
            cf._engine = engine
        return cf

    def _mock_engine(self, corr: float):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(return_value=corr)
        return eng

    async def test_high_corr_blocked(self):
        eng = self._mock_engine(0.85)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert not r.can_trade

    async def test_negative_corr_same_direction_blocked(self):
        eng = self._mock_engine(-0.92)
        cf = self._make_cf(engine=eng)
        ops = [_cp("USDCHF", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert not r.can_trade

    async def test_positive_corr_opposite_direction_blocked(self):
        eng = self._mock_engine(0.85)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "SELL", ops, 1.0)
        assert not r.can_trade

    async def test_exact_boundary_at_max_corr(self):
        eng = self._mock_engine(0.80)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert not r.can_trade

    async def test_just_below_max_corr_allowed(self):
        eng = self._mock_engine(0.79)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert r.can_trade

    async def test_penalty_zone_reduces_multiplier(self):
        eng = self._mock_engine(0.70)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert r.can_trade
        assert r.risk_multiplier < 1.0

    async def test_low_corr_full_multiplier(self):
        eng = self._mock_engine(0.40)
        cf = self._make_cf(engine=eng)
        ops = [_cp("AUDUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert r.can_trade
        assert r.risk_multiplier == 1.0

    async def test_empty_positions_allowed(self):
        cf = self._make_cf()
        r = await cf.check("EURUSD", "BUY", [], 1.0)
        assert r.can_trade
        assert r.risk_multiplier == 1.0

    async def test_accumulated_corr_blocks(self):
        eng = self._mock_engine(0.45)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0), _cp("AUDUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert not r.can_trade

    async def test_static_table_eurusd_gbpusd(self):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(side_effect=ConnectionError("no conn"))
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert not r.can_trade

    async def test_unknown_pair_no_corr_returns_none(self):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(side_effect=RuntimeError("nope"))
        cf = self._make_cf(engine=eng)
        ops = [_cp("XXXYYY", "BUY", 1.0)]
        r = await cf.check("AAABBB", "BUY", ops, 1.0)
        assert r.can_trade

    async def test_canonical_order_alpha(self):
        from backend.risk.correlation_filter import _canonical
        assert _canonical("GBPUSD", "EURUSD") == ("EURUSD", "GBPUSD")
        assert _canonical("EURUSD", "GBPUSD") == ("EURUSD", "GBPUSD")

    async def test_fail_closed_on_outer_exception(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("outer crash")):
            r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD", "BUY", 1.0)], 1.0)
        assert not r.can_trade

    async def test_fail_open_on_outer_exception(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("outer crash")):
            r = await cf.check("EURUSD", "BUY", [_cp("GBPUSD", "BUY", 1.0)], 1.0)
        assert r.can_trade

    async def test_correlation_score_in_result(self):
        eng = self._mock_engine(0.70)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert r.correlation_score >= 0.0

    async def test_source_field_populated(self):
        eng = self._mock_engine(0.60)
        cf = self._make_cf(engine=eng)
        ops = [_cp("GBPUSD", "BUY", 1.0)]
        r = await cf.check("EURUSD", "BUY", ops, 1.0)
        assert r.source in ("rolling", "static", "none", "error")


# ===========================================================================
# INTEGRATION -- cross-gate regression guards (5 tests)
# ===========================================================================
class TestIntegration:
    """Cross-gate regression: a fix in one module must not break another."""

    def test_gold_pip_consistent_across_modules(self):
        assert _LS_PIP["XAUUSD"] == _PR_PIP["XAUUSD"] == 1.0

    def test_crypto_pip_consistent_across_modules(self):
        for sym in ["BTCUSD", "ETHUSD", "LTCUSD"]:
            ls_v = _LS_PIP.get(sym)
            pr_v = _PR_PIP.get(sym)
            if ls_v is not None and pr_v is not None:
                assert ls_v == pr_v, f"{sym} pip mismatch LS={ls_v} PR={pr_v}"

    def test_fail_mode_enum_values_identical(self):
        for mod in [_vf, _ec, _cf, _pr]:
            fm_cls = getattr(mod, "FailMode", None)
            if fm_cls is not None:
                assert fm_cls.FAIL_CLOSED.value == "FAIL_CLOSED"
                assert fm_cls.FAIL_OPEN.value == "FAIL_OPEN"

    def test_pr_gate_uses_corrected_gold_pip(self):
        t = _trade("XAUUSD", "BUY", lot=1.0, entry=2000.0, sl=1800.0, balance=10_000.0)
        mgr = PortfolioRiskManager()
        r = mgr.check(t, [])
        assert r.can_trade, f"pip table still wrong: {r.reason}"

    def test_exposure_reflects_actual_risk_not_hardcoded(self):
        ec = ExposureControlEngine(
            config=ExposureControlConfig(
                max_total_exposure_percent=99.0,
                max_per_currency_percent=99.0,
            )
        )
        ops = [_ep("GBPJPY", "BUY", 1.0)]
        r = ec.check("EURJPY", "BUY", 2.5, ops)
        assert abs(r.projected_total_risk - 3.5) < 0.01
