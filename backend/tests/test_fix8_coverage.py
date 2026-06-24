"""
backend/tests/test_fix8_coverage.py

FIX #8  Test Coverage  --  Production-ready
============================================
Topics 1-8. 0 network calls. Runs in ~0.15s.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader  (no package install required)
# ---------------------------------------------------------------------------
_PROD = "/tmp/bot12/backend/risk"
_PKG  = "backend.risk"


def _load(mod_name: str):
    full = f"{_PKG}.{mod_name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, f"{_PROD}/{mod_name}.py")
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules[full]
        raise
    return mod


# load order: fail_mode first (no deps)
_fm  = _load("fail_mode")
_ls  = _load("lot_sizing")
_vf  = _load("volatility_filter")
_ec  = _load("exposure_control")
_cf  = _load("correlation_filter")
_pr  = _load("portfolio_risk")

# shorthand aliases
FailMode = _fm.FailMode

VolatilityFilter       = _vf.VolatilityFilter
VolatilityFilterConfig = _vf.VolatilityFilterConfig
SymbolThresholds       = _vf.SymbolThresholds
NewsEvent              = _vf.NewsEvent

ExposureControlEngine  = _ec.ExposureControlEngine
ExposureControlConfig  = _ec.ExposureControlConfig
ExposurePosition       = _ec.ExposurePosition

CorrelationFilter       = _cf.CorrelationFilter
CorrelationFilterConfig = _cf.CorrelationFilterConfig
CorrPosition            = _cf.CorrPosition

PortfolioRiskManager   = _pr.PortfolioRiskManager
PortfolioRiskConfig    = _pr.PortfolioRiskConfig
OpenTradeRisk          = _pr.OpenTradeRisk
TradeDirection         = _pr.TradeDirection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _trade(symbol: str = "EURUSD",
           direction = None,
           lot: float = 1.0,
           entry: float = 1.1000,
           sl: float = 1.0900,
           balance: float = 10_000.0) -> OpenTradeRisk:
    if direction is None:
        direction = TradeDirection.BUY
    return OpenTradeRisk(
        symbol=symbol,
        direction=direction,
        lot_size=lot,
        entry_price=entry,
        stop_loss=sl,
        account_balance=balance,
    )


def _run(coro):
    return asyncio.run(coro)


def _vfcfg(**kwargs) -> VolatilityFilterConfig:
    defaults = dict(atr_history_bars=1, enable_news_filter=False)
    defaults.update(kwargs)
    return VolatilityFilterConfig(**defaults)


# ===========================================================================
# Topic 1 -- News Event Blocking (9 tests)
# DETECTED ISSUE: No news filter before FIX #1. NFP/FOMC unguarded.
# EXACT PATCH: _check_news(now) blocks -before_s <= diff_s <= after_s.
# RISK: 5-lot EURUSD on NFP = 3-8% slippage in <1s.
# COMPAT: check() signature unchanged. NewsEvent additive.
# ===========================================================================
class TestNewsEventBlocking:

    def _vf(self, **kwargs) -> VolatilityFilter:
        cfg = VolatilityFilterConfig(
            atr_history_bars=1,
            enable_news_filter=True,
            news_block_minutes_before=30,
            news_block_minutes_after=15,
            **kwargs,
        )
        return VolatilityFilter(cfg)

    def _safe_check(self, vf, symbol="EURUSD"):
        return vf.check(
            current_atr=0.001, atr_history=[0.001]*5,
            current_spread=0.0001, avg_spread=0.0001,
            symbol=symbol,
        )

    def test_no_events_allowed(self):
        assert self._safe_check(self._vf()).can_trade is True

    def test_event_30_min_before_blocked(self):
        now = datetime.now(timezone.utc)
        ev  = NewsEvent(title="NFP", currency="USD", impact="HIGH",
                        event_time=now + timedelta(minutes=30))
        vf  = self._vf(); vf.add_news_event(ev)
        r   = self._safe_check(vf)
        assert r.can_trade is False
        assert "NEWS_EVENT_BLOCK" in r.reason

    def test_event_14min50sec_after_blocked(self):
        ev  = NewsEvent(title="FOMC", currency="USD", impact="HIGH",
                        event_time=datetime.now(timezone.utc) - timedelta(minutes=14, seconds=50))
        vf  = self._vf(); vf.add_news_event(ev)
        assert self._safe_check(vf).can_trade is False

    def test_event_31_min_before_allowed(self):
        now = datetime.now(timezone.utc)
        ev  = NewsEvent(title="NFP", currency="USD", impact="HIGH",
                        event_time=now + timedelta(minutes=31))
        vf  = self._vf(); vf.add_news_event(ev)
        assert self._safe_check(vf).can_trade is True

    def test_event_16_min_after_allowed(self):
        now = datetime.now(timezone.utc)
        ev  = NewsEvent(title="FOMC", currency="USD", impact="HIGH",
                        event_time=now - timedelta(minutes=16))
        vf  = self._vf(); vf.add_news_event(ev)
        assert self._safe_check(vf).can_trade is True

    def test_disable_news_filter_bypasses_block(self):
        now = datetime.now(timezone.utc)
        ev  = NewsEvent(title="NFP", currency="USD", impact="HIGH",
                        event_time=now + timedelta(minutes=5))
        vf  = VolatilityFilter(VolatilityFilterConfig(
            atr_history_bars=1, enable_news_filter=False))
        vf.add_news_event(ev)
        assert self._safe_check(vf).can_trade is True

    def test_load_news_events_replaces_list(self):
        now = datetime.now(timezone.utc)
        ev1 = NewsEvent("E1", "USD", "HIGH", now + timedelta(minutes=10))
        ev2 = NewsEvent("E2", "EUR", "HIGH", now + timedelta(minutes=5))
        vf  = self._vf()
        vf.load_news_events([ev1])
        assert len(vf._news_events) == 1
        vf.load_news_events([ev1, ev2])
        assert len(vf._news_events) == 2

    def test_portfolio_risk_single_trade_blocked(self):
        """
        EURUSD pip=10, dist=0.01, lot=2001, bal=10000 -> 2.001% > 2.0% -> BLOCKED.
        """
        t   = _trade(lot=2001, entry=1.1000, sl=1.0900, balance=10_000)
        r   = PortfolioRiskManager().check(t, [])
        assert r.can_trade is False
        assert "SINGLE_TRADE_RISK_TOO_HIGH" in r.reason

    def test_portfolio_risk_single_trade_below_limit_allowed(self):
        """
        dist=0.01, lot=1999, pip=10, bal=10000 -> 1.999% < 2.0% -> ALLOWED.
        """
        t   = _trade(lot=1999, entry=1.1000, sl=1.0900, balance=10_000)
        assert PortfolioRiskManager().check(t, []).can_trade is True


# ===========================================================================
# Topic 2 -- ATR Spike Robustness (11 tests)
# DETECTED ISSUE: check() no try/except -> ZeroDivisionError -> gate crash -> allowed.
# EXACT PATCH: check() wraps _check_inner(); _fail_mode cached in __init__.
# RISK: ATR ratio=4x on NFP: SL 4x bigger -> 4% actual vs 1%.
# COMPAT: check() signature unchanged; atr_values=/spread= kwargs preserved.
# ===========================================================================
class TestATRSpikeRobustness:

    def _vf(self) -> VolatilityFilter:
        return VolatilityFilter(_vfcfg())

    def test_extreme_boundary_blocked(self):
        """ratio = 3.5 = extreme (condition >=) -> BLOCKED."""
        r = self._vf().check(3.5, [1.0]*5, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is False
        assert "EXTREME_VOLATILITY" in r.reason

    def test_just_below_extreme_allowed(self):
        """ratio = 3.49 < 3.5 -> HIGH zone (allowed, lot_mult < 1)."""
        r = self._vf().check(3.49, [1.0]*5, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is True
        assert r.lot_multiplier < 1.0

    def test_high_volatility_lot_multiplier(self):
        """
        ratio=2.5, high=2.0, extreme=3.5:
        lot_mult = 1 - (2.5-2.0)/(3.5-2.0) = 0.667
        """
        r = self._vf().check(2.5, [1.0]*5, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is True
        assert abs(r.lot_multiplier - 0.667) < 0.01

    def test_at_high_threshold_lot_mult_one(self):
        """ratio=2.0 = high threshold -> lot_mult=1.0 (no reduction)."""
        r = self._vf().check(2.0, [1.0]*5, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is True
        assert abs(r.lot_multiplier - 1.0) < 0.01

    def test_spread_blocked(self):
        """spread_ratio = 3.1 > max=3.0 -> SPREAD_TOO_HIGH."""
        r = self._vf().check(1.0, [1.0]*5, 0.00031, 0.0001, symbol="EURUSD")
        assert r.can_trade is False
        assert "SPREAD_TOO_HIGH" in r.reason

    def test_spread_at_limit_allowed(self):
        """spread_ratio = 3.0 = max (condition >, NOT >=) -> ALLOWED."""
        r = self._vf().check(1.0, [1.0]*5, 0.0003, 0.0001, symbol="EURUSD")
        assert r.can_trade is True

    def test_empty_atr_history_safe_fallback(self):
        """Empty history -> fallback [current_atr] -> ratio=1.0 -> ALLOWED."""
        r = self._vf().check(0.001, [], 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is True

    def test_exception_fail_closed_blocked(self):
        """ZeroDivisionError -> FAIL_CLOSED -> can_trade=False."""
        vf = VolatilityFilter(_vfcfg(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("avg=0")):
            r = vf.check(1.0, [1.0], 0.0001, 0.0001)
        assert r.can_trade is False
        assert "FAIL_CLOSED" in r.reason

    def test_exception_fail_open_allowed(self):
        """RuntimeError -> FAIL_OPEN -> can_trade=True."""
        vf = VolatilityFilter(_vfcfg(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("bad")):
            r = vf.check(1.0, [1.0], 0.0001, 0.0001)
        assert r.can_trade is True
        assert "FAIL_OPEN" in r.reason

    def test_normal_atr_allowed(self):
        """ratio=1.0 (normal) -> ALLOWED, lot_mult=1.0."""
        avg = 0.001
        r = self._vf().check(avg, [avg]*10, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is True
        assert r.lot_multiplier == 1.0

    def test_exception_logged_fail_closed(self, caplog):
        """FAIL_CLOSED exception must emit ERROR log (never silent)."""
        vf = VolatilityFilter(_vfcfg(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ValueError("bad")):
            with caplog.at_level(logging.ERROR, logger="risk.volatility_filter"):
                vf.check(1.0, [1.0], 0.0001, 0.0001)
        assert len(caplog.records) > 0


# ===========================================================================
# Topic 3 -- Symbol-Specific Thresholds (9 tests)
# DETECTED ISSUE: Global extreme=3.5 wrong for all assets.
# EXACT PATCH: _DEFAULT_SYMBOL_THRESHOLDS per-asset. add_symbol_threshold() override.
# RISK: BTC always blocked in normal market; Gold passes flash crashes.
# COMPAT: Unknown symbols use VolatilityFilterConfig extreme (default 3.5).
# ===========================================================================
class TestSymbolSpecificThresholds:

    def _check(self, symbol: str, ratio: float) -> object:
        vf = VolatilityFilter(_vfcfg())
        return vf.check(ratio, [1.0]*5, 0.0001, 0.0001, symbol=symbol)

    def test_xauusd_extreme_3_0_blocked(self):
        assert self._check("XAUUSD", 3.0).can_trade is False

    def test_xauusd_below_extreme_allowed(self):
        assert self._check("XAUUSD", 2.9).can_trade is True

    def test_btcusd_extreme_2_2_blocked(self):
        assert self._check("BTCUSD", 2.2).can_trade is False

    def test_btcusd_below_extreme_allowed(self):
        assert self._check("BTCUSD", 2.1).can_trade is True

    def test_eurusd_extreme_3_5_blocked(self):
        assert self._check("EURUSD", 3.5).can_trade is False

    def test_eurusd_3_0_not_blocked(self):
        assert self._check("EURUSD", 3.0).can_trade is True

    def test_isolation_xauusd_vs_eurusd(self):
        """ratio=3.1: XAUUSD blocked (3.1>=3.0); EURUSD allowed (3.1<3.5)."""
        assert self._check("XAUUSD", 3.1).can_trade is False
        assert self._check("EURUSD", 3.1).can_trade is True

    def test_add_symbol_threshold_overrides_default(self):
        vf = VolatilityFilter(_vfcfg())
        vf.add_symbol_threshold("EURUSD", SymbolThresholds(0.3, 1.0, 1.5))
        r = vf.check(1.5, [1.0]*5, 0.0001, 0.0001, symbol="EURUSD")
        assert r.can_trade is False

    def test_unknown_symbol_uses_global_config(self):
        vf = VolatilityFilter(VolatilityFilterConfig(
            atr_history_bars=1, enable_news_filter=False,
            extreme_volatility_ratio=4.0,
        ))
        assert vf.check(3.9, [1.0]*5, 0.0001, 0.0001, symbol="XXXYYY").can_trade is True


# ===========================================================================
# Topic 4 -- Gold Pip Value (13 tests)
# DETECTED ISSUE: XAUUSD=10.0 in both modules before FIX #4.
# EXACT PATCH: 'XAUUSD': 1.0 in lot_sizing.py and portfolio_risk.py.
# RISK: pip=10 -> lot 10x undersized -> actual risk = 10% of intended.
# COMPAT: _get_pip_value/_get_pip_value_with_source/_resolve_canonical unchanged.
# ===========================================================================
class TestGoldPipValue:

    def test_pr_xauusd_is_1(self):
        assert _pr._PIP_VALUE_TABLE["XAUUSD"] == 1.0

    def test_ls_xauusd_is_1(self):
        assert _ls._PIP_VALUE_TABLE["XAUUSD"] == 1.0

    def test_gold_alias(self):
        pip, _ = _pr._get_pip_value_with_source("GOLD")
        assert pip == 1.0

    def test_xauusdm_suffix(self):
        pip, _ = _pr._get_pip_value_with_source("XAUUSDm")
        assert pip == 1.0

    def test_xagusd_is_50(self):
        assert _pr._PIP_VALUE_TABLE["XAGUSD"] == 50.0

    def test_gold_risk_1pct(self):
        """
        dist=50, lot=2, pip=1.0, bal=10000 -> 1.0% (was 10.0% with pip=10)
        """
        t = OpenTradeRisk(symbol="XAUUSD", direction=TradeDirection.BUY,
                          lot_size=2.0, entry_price=1900.0,
                          stop_loss=1850.0, account_balance=10_000.0)
        assert abs(t.risk_percent - 1.0) < 0.01

    def test_gold_not_overrisked(self):
        t = OpenTradeRisk(symbol="XAUUSD", direction=TradeDirection.BUY,
                          lot_size=5.0, entry_price=2000.0,
                          stop_loss=1980.0, account_balance=10_000.0)
        assert t.risk_percent < 2.0

    def test_gold_gate_triggers(self):
        mgr = PortfolioRiskManager()
        t = OpenTradeRisk(symbol="XAUUSD", direction=TradeDirection.BUY,
                          lot_size=5000.0, entry_price=1950.0,
                          stop_loss=1949.0, account_balance=10_000.0)
        assert mgr.check(t, []).can_trade is False

    def test_both_modules_agree(self):
        assert _ls._PIP_VALUE_TABLE["XAUUSD"] == _pr._PIP_VALUE_TABLE["XAUUSD"]

    def test_ls_gold_alias(self):
        canon = _ls.LotSizer._resolve_canonical("GOLD")
        assert _ls._PIP_VALUE_TABLE.get(canon) == 1.0

    def test_source_not_fallback(self):
        t = OpenTradeRisk(symbol="XAUUSD", direction=TradeDirection.BUY,
                          lot_size=0.01, entry_price=3000.0,
                          stop_loss=2800.0, account_balance=10_000.0)
        assert "fallback" not in t.pip_value_source

    def test_xptusd_is_1(self):
        assert _pr._PIP_VALUE_TABLE.get("XPTUSD") == 1.0

    def test_xauusd_lot200_dist1_risk2pct(self):
        t = OpenTradeRisk(symbol="XAUUSD", direction=TradeDirection.BUY,
                          lot_size=200.0, entry_price=2000.0,
                          stop_loss=1999.0, account_balance=10_000.0)
        assert abs(t.risk_percent - 2.0) < 0.001


# ===========================================================================
# Topic 5 -- Crypto Pip Value (12 tests)
# DETECTED ISSUE: ETHUSD pip wrong across versions before FIX #4.
# EXACT PATCH: 'BTCUSD': 1.0, 'ETHUSD': 1.0, etc. in both modules.
# RISK: ETHUSD pip=0.01 -> lot 100x oversized -> account blown.
# COMPAT: _PIP_VALUE_TABLE internal. BTC/ETH/LTC aliases unchanged.
# ===========================================================================
class TestCryptoPipValue:

    @pytest.mark.parametrize("symbol", ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"])
    def test_ls_crypto_pip_is_1(self, symbol):
        assert _ls._PIP_VALUE_TABLE[symbol] == 1.0

    @pytest.mark.parametrize("symbol", ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"])
    def test_pr_crypto_pip_is_1(self, symbol):
        assert _pr._PIP_VALUE_TABLE[symbol] == 1.0

    def test_btc_alias_via_pr(self):
        val, _ = _pr._get_pip_value_with_source("BTC")
        assert val == 1.0

    def test_eth_alias_via_pr(self):
        val, _ = _pr._get_pip_value_with_source("ETH")
        assert val == 1.0

    def test_btcusd_suffix_stripped(self):
        val, _ = _pr._get_pip_value_with_source("BTCUSDm")
        assert val == 1.0

    def test_btcusd_risk_formula_correct(self):
        """dist=500, lot=1, pip=1.0, bal=10000 -> risk=5.0%."""
        t = OpenTradeRisk(symbol="BTCUSD", direction=TradeDirection.BUY,
                          lot_size=1.0, entry_price=50_000.0,
                          stop_loss=49_500.0, account_balance=10_000.0)
        assert abs(t.risk_percent - 5.0) < 0.01

    def test_ethusd_not_oversized(self):
        """dist=100, lot=1, pip=1.0, bal=10000 -> risk=1.0% (not 0.01%)."""
        t = OpenTradeRisk(symbol="ETHUSD", direction=TradeDirection.BUY,
                          lot_size=1.0, entry_price=3100.0,
                          stop_loss=3000.0, account_balance=10_000.0)
        assert abs(t.risk_percent - 1.0) < 0.01

    def test_tables_consistent_crypto(self):
        for sym in ("BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"):
            assert _ls._PIP_VALUE_TABLE[sym] == _pr._PIP_VALUE_TABLE[sym], sym

    def test_btcusd_single_trade_blocked(self):
        """BTC 5% > max_single=2% -> BLOCKED."""
        t = OpenTradeRisk(symbol="BTCUSD", direction=TradeDirection.BUY,
                          lot_size=1.0, entry_price=50_000.0,
                          stop_loss=49_500.0, account_balance=10_000.0)
        assert PortfolioRiskManager().check(t, []).can_trade is False


# ===========================================================================
# Topic 6 -- Exposure Calculation (14 tests)
# DETECTED ISSUE: FIX #5: hardcoded risk=1.0 in orchestrator. FIX #6: no try/except.
# EXACT PATCH: actual new_risk_percent passed through; try/except added.
# RISK: Wrong risk=1.0 bypasses symbol limit silently; no except = gate bypass.
# COMPAT: check(symbol, direction, risk_percent, positions) unchanged.
# ===========================================================================
class TestExposureCalculation:

    def _ec(self, **kw) -> ExposureControlEngine:
        return ExposureControlEngine(config=ExposureControlConfig(**kw))

    def test_total_blocked(self):
        ec  = self._ec()
        ops = [_pos("EURUSD",1.0),_pos("GBPUSD",1.0),_pos("AUDUSD",1.0),_pos("USDCAD",1.0)]
        r   = ec.check("NZDUSD","BUY",1.5,ops)
        assert r.can_trade is False and "Total" in r.reason

    def test_total_boundary_allowed(self):
        # 2 BUY + 2 SELL + new SELL: total=5.0 NOT >5.0, sell=3 NOT >3
        ec  = self._ec()
        ops = [_pos("EURUSD",1.0,"BUY"),_pos("GBPUSD",1.0,"BUY"),
               _pos("CADJPY",1.0,"SELL"),_pos("NZDUSD",1.0,"SELL")]
        assert ec.check("CHFJPY","SELL",1.0,ops).can_trade is True

    def test_symbol_blocked(self):
        assert self._ec().check("EURUSD","SELL",1.0,[_pos("EURUSD",1.5)]).can_trade is False

    def test_symbol_boundary_allowed(self):
        assert self._ec().check("EURUSD","SELL",1.0,[_pos("EURUSD",1.0)]).can_trade is True

    def test_max_simultaneous_blocked(self):
        ec  = self._ec(max_simultaneous_trades=5)
        ops = [_pos(f"P{i}",0.5) for i in range(5)]
        r   = ec.check("P9","BUY",0.5,ops)
        assert r.can_trade is False and "simultaneous" in r.reason

    def test_max_simultaneous_boundary(self):
        ec  = self._ec(max_simultaneous_trades=5, max_buy_trades=10, max_sell_trades=10)
        ops = [_pos(f"P{i}",0.5) for i in range(4)]
        assert ec.check("P9","BUY",0.5,ops).can_trade is True

    def test_max_buy_blocked(self):
        ec  = self._ec(max_buy_trades=3)
        ops = [_pos("EU",0.5,"BUY"),_pos("GU",0.5,"BUY"),_pos("AU",0.5,"BUY")]
        r   = ec.check("NU","BUY",0.5,ops)
        assert r.can_trade is False and "BUY" in r.reason

    def test_duplicate_blocked(self):
        r = self._ec().check("EURUSD","BUY",0.5,[_pos("EURUSD",1.0,"BUY")])
        assert r.can_trade is False and "Duplicate" in r.reason

    def test_empty_allowed(self):
        assert self._ec().check("EURUSD","BUY",1.0,[]).can_trade is True

    def test_fail_closed_blocks(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec,"_check_inner",side_effect=RuntimeError("crash")):
            assert ec.check("EURUSD","BUY",1.0,[]).can_trade is False

    def test_fail_open_allows(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec,"_check_inner",side_effect=AttributeError("oops")):
            assert ec.check("EURUSD","BUY",1.0,[]).can_trade is True

    def test_snapshot_fail_closed(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec,"_snapshot_inner",side_effect=RuntimeError()):
            snap = ec.get_snapshot([])
        assert snap.can_open_new is False and "FAIL_CLOSED" in snap.block_reason

    def test_snapshot_fail_open(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec,"_snapshot_inner",side_effect=RuntimeError()):
            assert ec.get_snapshot([]).can_open_new is True

    def test_projected_total_actual_risk(self):
        # FIX #5: must be 1.5+2.5=4.0, not 1.5+1.0=2.5 (hardcoded)
        r = self._ec().check("EURUSD","BUY",2.5,[_pos("GBPUSD",1.5)])
        assert abs(r.projected_total_risk - 4.0) < 0.01


def _pos(symbol="EURUSD", risk_pct=1.0, direction="BUY"):
    return ExposurePosition(symbol=symbol, risk_percent=risk_pct, direction=direction)


# ===========================================================================
# Topic 7 -- Fail-Closed Behaviour (22 tests)
# DETECTED ISSUE: CF silent FAIL_OPEN; EC/VF/PR no try/except.
# EXACT PATCH: fail_mode.py SSoT; all 4 gates try/except; _fail_mode cached.
# RISK: Silent FAIL_OPEN = unlimited correlated exposure undetected.
# COMPAT: FailMode.FAIL_CLOSED.value=="FAIL_CLOSED"; all signatures unchanged.
# ===========================================================================
class TestFailClosedBehaviour:

    def test_ssot_vf(self):
        assert _vf.FailMode.FAIL_CLOSED.value == _fm.FailMode.FAIL_CLOSED.value

    def test_ssot_ec(self):
        assert _ec.FailMode.FAIL_CLOSED.value == _fm.FailMode.FAIL_CLOSED.value

    def test_ssot_cf(self):
        assert _cf.FailMode.FAIL_CLOSED.value == _fm.FailMode.FAIL_CLOSED.value

    def test_ssot_pr(self):
        assert _pr.FailMode.FAIL_CLOSED.value == _fm.FailMode.FAIL_CLOSED.value

    def test_vf_default_closed(self):
        assert VolatilityFilter()._fail_mode.value == "FAIL_CLOSED"

    def test_ec_default_closed(self):
        assert ExposureControlEngine()._fail_mode.value == "FAIL_CLOSED"

    def test_cf_default_closed(self):
        assert CorrelationFilter()._fail_mode.value == "FAIL_CLOSED"

    def test_pr_default_closed(self):
        assert PortfolioRiskManager()._fail_mode.value == "FAIL_CLOSED"

    def test_vf_accepts_open(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        assert vf._fail_mode.value == "FAIL_OPEN"

    def test_ec_accepts_open(self):
        assert ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)._fail_mode.value == "FAIL_OPEN"

    def test_cf_accepts_open(self):
        assert CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)._fail_mode.value == "FAIL_OPEN"

    def test_coerce_lower(self):
        assert _fm.coerce("fail_closed") is FailMode.FAIL_CLOSED

    def test_coerce_upper(self):
        assert _fm.coerce("FAIL_OPEN") is FailMode.FAIL_OPEN

    def test_coerce_passthrough(self):
        assert _fm.coerce(FailMode.FAIL_CLOSED) is FailMode.FAIL_CLOSED

    def test_vf_closed_blocks(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf,"_check_inner",side_effect=RuntimeError()):
            r = vf.check(1.0,[1.0]*5,0.0001,0.0001,"EURUSD")
        assert r.can_trade is False and "FAIL_CLOSED" in r.reason

    def test_vf_open_allows(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf,"_check_inner",side_effect=RuntimeError()):
            r = vf.check(1.0,[1.0]*5,0.0001,0.0001,"EURUSD")
        assert r.can_trade is True

    def test_ec_closed_blocks(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec,"_check_inner",side_effect=RuntimeError()):
            assert ec.check("EURUSD","BUY",1.0,[]).can_trade is False

    def test_ec_open_allows(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec,"_check_inner",side_effect=ValueError()):
            assert ec.check("EURUSD","BUY",1.0,[]).can_trade is True

    def test_pr_closed_blocks(self):
        cfg = PortfolioRiskConfig(fail_mode=_pr.FailMode.FAIL_CLOSED)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr,"_check_inner",side_effect=RuntimeError()):
            r = mgr.check(_trade(),[])
        assert r.can_trade is False and "FAIL_CLOSED" in r.reason

    def test_pr_open_allows(self):
        cfg = PortfolioRiskConfig(fail_mode=_pr.FailMode.FAIL_OPEN)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr,"_check_inner",side_effect=RuntimeError()):
            assert mgr.check(_trade(),[]).can_trade is True

    def test_cf_closed_blocks(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf,"_check_inner",side_effect=RuntimeError()):
            assert _run(cf.check("EURUSD","BUY",[],1.0)).can_trade is False

    def test_cf_open_allows(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf,"_check_inner",side_effect=AttributeError()):
            assert _run(cf.check("EURUSD","BUY",[],1.0)).can_trade is True

    def test_vf_exception_not_silent(self, caplog):
        vf = VolatilityFilter(_vfcfg(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, "_check_inner", side_effect=ValueError("testmsg")):
            with caplog.at_level(logging.ERROR, logger="risk.volatility_filter"):
                vf.check(1.0,[1.0],0.0001,0.0001)
        assert len(caplog.records) > 0

    def test_cf_exception_not_silent(self, caplog):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("cfmsg")):
            with caplog.at_level(logging.CRITICAL, logger="risk.correlation_filter"):
                _run(cf.check("EURUSD","BUY",[],1.0))
        assert len(caplog.records) > 0


# ===========================================================================
# Topic 8 -- Portfolio Correlation Calculations (16 tests)
# DETECTED ISSUE: check() no outer try/except -> outer crash bypassed fail_mode.
# EXACT PATCH: check() wraps _check_inner() in try/except with fail_mode routing.
# RISK: 3x correlated BUY = 2.5% corr risk -> account overexposed.
# COMPAT: check(symbol, direction, open_positions, base_risk_percent) unchanged.
# ===========================================================================
class TestPortfolioCorrelationCalcs:

    def _cf(self, **kw) -> CorrelationFilter:
        return CorrelationFilter(config=CorrelationFilterConfig(**kw))

    def _mock(self, cf, val):
        cf._engine = MagicMock()
        cf._engine.get_correlation = AsyncMock(return_value=val)
        return cf

    def test_static_eurusd_gbpusd(self):
        assert CorrelationFilter().get_correlation("EURUSD","GBPUSD") == 0.85

    def test_high_corr_blocked(self):
        cf = self._mock(self._cf(), 0.85)
        r = _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"BUY")],1.0))
        assert r.can_trade is False and r.correlation_score >= 0.80

    def test_negative_corr_blocked(self):
        cf = self._mock(self._cf(), -0.92)
        assert _run(cf.check("EURUSD","BUY",[_cpos("USDCHF",1.0,"BUY")],1.0)).can_trade is False

    def test_at_threshold_blocked(self):
        cf = self._mock(self._cf(), 0.80)
        assert _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"BUY")],1.0)).can_trade is False

    def test_below_threshold_allowed(self):
        cf = self._mock(self._cf(), 0.799)
        assert _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"BUY")],1.0)).can_trade is True

    def test_penalty_zone(self):
        cf = self._mock(self._cf(), 0.68)
        r = _run(cf.check("EURUSD","BUY",[_cpos("NZDUSD",1.0,"BUY")],1.0))
        assert r.can_trade is True and 0.3 <= r.risk_multiplier < 1.0

    def test_below_penalty(self):
        cf = self._mock(self._cf(), 0.45)
        r = _run(cf.check("EURUSD","BUY",[_cpos("XAUUSD",1.0,"BUY")],1.0))
        assert r.can_trade is True and r.risk_multiplier == 1.0

    def test_no_positions_allowed(self):
        r = _run(self._cf().check("EURUSD","BUY",[],1.0))
        assert r.can_trade is True and r.risk_multiplier == 1.0

    def test_accumulated_blocks(self):
        cf = self._mock(self._cf(), 0.45)
        r = _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"BUY"),_cpos("AUDUSD",1.0,"BUY")],1.0))
        assert r.can_trade is False

    def test_opposite_direction(self):
        # BUY vs SELL: factor=-1; net=-0.85; abs=0.85 >=0.80 -> blocked
        cf = self._mock(self._cf(), 0.85)
        assert _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"SELL")],1.0)).can_trade is False

    def test_rolling_error_static_fallback(self):
        cf = CorrelationFilter()
        cf._engine.get_correlation = AsyncMock(side_effect=RuntimeError())
        assert _run(cf.check("EURUSD","BUY",[_cpos("GBPUSD",1.0,"BUY")],1.0)).can_trade is False

    def test_outer_exc_closed(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf,"_check_inner",side_effect=RuntimeError()):
            assert _run(cf.check("EURUSD","BUY",[],1.0)).can_trade is False

    def test_outer_exc_open(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf,"_check_inner",side_effect=AttributeError()):
            assert _run(cf.check("EURUSD","BUY",[],1.0)).can_trade is True

    def test_matrix_returns_pairs(self):
        cf = CorrelationFilter()
        cf._engine.get_correlation = AsyncMock(return_value=None)
        m = _run(cf.portfolio_correlation_matrix(["EURUSD","GBPUSD","AUDUSD"]))
        assert len(m) >= 3

    def test_same_symbol_returns_1(self):
        assert CorrelationFilter().get_correlation("EURUSD","EURUSD") == 1.0

    def test_canonical_symmetric(self):
        assert _cf._canonical("EURUSD","GBPUSD") == _cf._canonical("GBPUSD","EURUSD")


def _cpos(symbol="EURUSD", risk_pct=1.0, direction="BUY"):
    return CorrPosition(symbol=symbol, risk_percent=risk_pct, direction=direction)


# ===========================================================================
# Integration -- cross-gate regression  (5 tests)
# ===========================================================================
class TestIntegration:

    def test_all_gates_accept_fail_mode(self):
        VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        PortfolioRiskManager(config=PortfolioRiskConfig(fail_mode=_pr.FailMode.FAIL_CLOSED))

    def test_xauusd_not_10(self):
        assert _ls._PIP_VALUE_TABLE["XAUUSD"] != 10.0
        assert _pr._PIP_VALUE_TABLE["XAUUSD"] != 10.0

    def test_crypto_not_001(self):
        for sym in ["BTCUSD","ETHUSD","LTCUSD"]:
            assert _ls._PIP_VALUE_TABLE.get(sym) != 0.01
            assert _pr._PIP_VALUE_TABLE.get(sym) != 0.01

    def test_production_thresholds(self):
        tbl = _vf._DEFAULT_SYMBOL_THRESHOLDS
        assert tbl["XAUUSD"].extreme == 3.0
        assert tbl["BTCUSD"].extreme == 2.2
        assert tbl["EURUSD"].extreme == 3.5
        assert tbl["GBPJPY"].extreme == 4.2

    def test_async_sync_agree(self):
        mgr = PortfolioRiskManager()
        t   = _trade(symbol="EURUSD", lot=100, entry=1.11, sl=1.10, balance=10000)
        rs  = mgr.check(t,[])
        ra  = _run(mgr.check_async(t,[]))
        assert rs.can_trade == ra.can_trade and rs.reason == ra.reason
