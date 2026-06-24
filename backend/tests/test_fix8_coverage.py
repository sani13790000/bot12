"""
backend/tests/test_fix8_coverage.py
FIX #8 - Production-ready test suite.
111 tests across 9 classes. Verified against live production code.
Python 3.14 compatible (asyncio.run() only).
"""
from __future__ import annotations
import asyncio, importlib, importlib.util, sys, types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

def _load(filename, alias):
    p = HERE / filename
    spec = importlib.util.spec_from_file_location(alias, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod

for pkg in ("backend", "backend.risk"):
    if pkg not in sys.modules:
        sys.modules[pkg] = types.ModuleType(pkg)

_fm_mod = _load("fail_mode.py",          "backend.risk.fail_mode")
_ls_mod = _load("lot_sizing.py",         "backend.risk.lot_sizing")
_pr_mod = _load("portfolio_risk.py",     "backend.risk.portfolio_risk")
_vf_mod = _load("volatility_filter.py",  "backend.risk.volatility_filter")
_ec_mod = _load("exposure_control.py",   "backend.risk.exposure_control")
_cf_mod = _load("correlation_filter.py", "backend.risk.correlation_filter")

FailMode               = _fm_mod.FailMode
VolatilityFilter       = _vf_mod.VolatilityFilter
VolatilityFilterConfig = _vf_mod.VolatilityFilterConfig
SymbolThresholds       = _vf_mod.SymbolThresholds
NewsEvent              = _vf_mod.NewsEvent
VolatilityCheckResult  = _vf_mod.VolatilityCheckResult
VolatilityLevel        = _vf_mod.VolatilityLevel
OpenTradeRisk          = _pr_mod.OpenTradeRisk
PortfolioRiskManager   = _pr_mod.PortfolioRiskManager
PortfolioRiskConfig    = _pr_mod.PortfolioRiskConfig
TradeDirection         = _pr_mod.TradeDirection
ExposureControlEngine  = _ec_mod.ExposureControlEngine
ExposureControlConfig  = _ec_mod.ExposureControlConfig
ExposurePosition       = _ec_mod.ExposurePosition
CorrelationFilter      = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig
CorrPosition           = _cf_mod.CorrPosition

def _trade(symbol="EURUSD", lot=1.0, entry=1.1, sl=1.09, bal=10000.0, direction="BUY"):
    return OpenTradeRisk(
        symbol=symbol,
        direction=TradeDirection.BUY if direction == "BUY" else TradeDirection.SELL,
        lot_size=lot, entry_price=entry, stop_loss=sl, account_balance=bal)

def _pos(symbol="EURUSD", risk_pct=1.0, direction="BUY"):
    return ExposurePosition(symbol=symbol, risk_percent=risk_pct, direction=direction)

def _cpos(symbol="EURUSD", risk_pct=1.0, direction="BUY"):
    return CorrPosition(symbol=symbol, risk_percent=risk_pct, direction=direction)

def _run(coro):
    return asyncio.run(coro)


# ============================================================
# TOPIC 1 - NEWS EVENT BLOCKING  (9 tests)
# DETECTED ISSUE: No news filter before FIX #1. NFP/FOMC unguarded.
# EXACT PATCH: _check_news(now) blocks -before_s <= diff_s <= after_s.
# RISK: 5-lot EURUSD on NFP = 3-8% slippage in <1s.
# COMPAT: check() signature unchanged. NewsEvent additive.
# ============================================================
class TestNewsEventBlocking:
    def _vf(self, before=30, after=15):
        return VolatilityFilter(config=VolatilityFilterConfig(
            enable_news_filter=True,
            news_block_minutes_before=before,
            news_block_minutes_after=after))

    def test_no_news_allowed(self):
        assert self._vf()._check_news(datetime.now(timezone.utc)) is None

    def test_block_before_event(self):
        vf = self._vf()
        now = datetime(2025,1,3,13,40,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="NFP",currency="USD",impact="HIGH",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        r = vf._check_news(now)
        assert r is not None and r.can_trade is False
        assert "NEWS_EVENT_BLOCK" in r.reason

    def test_block_after_event(self):
        vf = self._vf()
        now = datetime(2025,1,3,14,10,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="FOMC",currency="USD",impact="HIGH",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        assert vf._check_news(now) is not None

    def test_outside_window_allowed(self):
        vf = self._vf()
        now = datetime(2025,1,3,13,0,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="CPI",currency="USD",impact="LOW",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        assert vf._check_news(now) is None

    def test_boundary_exactly_before(self):
        vf = self._vf()
        now = datetime(2025,1,3,13,30,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="NFP",currency="USD",impact="HIGH",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        assert vf._check_news(now) is not None

    def test_multiple_events_one_blocking(self):
        vf = self._vf()
        now = datetime(2025,1,3,13,45,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="GDP",currency="EUR",impact="LOW",
                                    event_time=datetime(2025,1,3,17,0,0,tzinfo=timezone.utc)))
        vf.add_news_event(NewsEvent(title="NFP",currency="USD",impact="HIGH",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        r = vf._check_news(now)
        assert r is not None and r.can_trade is False

    def test_filter_disabled_ignores(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(enable_news_filter=False))
        now = datetime(2025,1,3,13,50,0,tzinfo=timezone.utc)
        vf.add_news_event(NewsEvent(title="NFP",currency="USD",impact="HIGH",
                                    event_time=datetime(2025,1,3,14,0,0,tzinfo=timezone.utc)))
        assert vf._check_news(now) is None

    def test_portfolio_risk_single_trade_blocked(self):
        # DETECTED ISSUE: portfolio_risk.check() no try/except before FIX #6.
        # XAUUSD pip=1.0: dist=201, lot=1, bal=10000 -> 2.01% > 2.0% -> blocked
        mgr = PortfolioRiskManager()
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=1.0,entry_price=2201.0,stop_loss=2000.0,account_balance=10000.0)
        r = mgr.check(t, [])
        assert r.can_trade is False
        assert "SINGLE_TRADE_RISK_TOO_HIGH" in r.reason

    def test_portfolio_risk_boundary_allowed(self):
        # XAUUSD pip=1.0: dist=200, lot=1, bal=10000 -> 2.0% NOT > 2.0% -> allowed
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=1.0,entry_price=2200.0,stop_loss=2000.0,account_balance=10000.0)
        assert PortfolioRiskManager().check(t, []).can_trade is True


# ============================================================
# TOPIC 2 - ATR SPIKE ROBUSTNESS  (11 tests)
# DETECTED ISSUE: check() no try/except -> ZeroDivisionError -> gate crash -> allowed.
# EXACT PATCH: check() wraps _check_inner(); _fail_mode cached in __init__.
# RISK: ATR ratio=4x on NFP: SL 4x bigger -> 4% actual vs 1%.
# COMPAT: check() signature unchanged; atr_values=/spread= kwargs preserved.
# ============================================================
class TestATRSpikeRobustness:
    def _vf(self, **kw):
        return VolatilityFilter(config=VolatilityFilterConfig(**kw))

    def test_extreme_blocked(self):
        assert self._vf().check(4.0,[1.0]*20,0.0001,0.0001,"EURUSD").can_trade is False

    def test_extreme_boundary_at_35(self):
        # ratio==3.5 exactly at extreme -> blocked (condition >=)
        assert self._vf().check(3.5,[1.0]*20,0.0001,0.0001,"EURUSD").can_trade is False

    def test_just_below_extreme_is_high(self):
        r = self._vf().check(3.49,[1.0]*20,0.0001,0.0001,"EURUSD")
        assert r.can_trade is True and r.level == VolatilityLevel.HIGH and r.lot_multiplier < 1.0

    def test_high_lot_multiplier_formula(self):
        # ratio=2.5: mult = 1-(2.5-2.0)/(3.5-2.0) = 0.667
        r = self._vf().check(2.5,[1.0]*20,0.0001,0.0001,"EURUSD")
        assert 0.66 <= r.lot_multiplier <= 0.68

    def test_at_high_boundary_mult_one(self):
        assert self._vf().check(2.0,[1.0]*20,0.0001,0.0001,"EURUSD").lot_multiplier == 1.0

    def test_spread_blocked(self):
        r = self._vf().check(1.0,[1.0]*20,0.00031,0.0001,"EURUSD")
        assert r.can_trade is False and "SPREAD" in r.reason

    def test_spread_boundary_allowed(self):
        assert self._vf().check(1.0,[1.0]*20,0.00030,0.0001,"EURUSD").can_trade is True

    def test_empty_history_normal(self):
        r = self._vf().check(0.001,[],0.0001,0.0001,"EURUSD")
        assert r.can_trade is True and r.level == VolatilityLevel.NORMAL

    def test_fail_closed_on_exception(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf,"_check_inner",side_effect=RuntimeError("boom")):
            r = vf.check(1.0,[1.0]*5,0.0001,0.0001,"EURUSD")
        assert r.can_trade is False and "FAIL_CLOSED" in r.reason

    def test_fail_open_on_exception(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf,"_check_inner",side_effect=ZeroDivisionError()):
            r = vf.check(1.0,[1.0]*5,0.0001,0.0001,"EURUSD")
        assert r.can_trade is True and "FAIL_OPEN" in r.reason

    def test_normal_full_lot(self):
        r = self._vf().check(1.0,[1.0]*20,0.0001,0.0001,"EURUSD")
        assert r.can_trade is True and r.level == VolatilityLevel.NORMAL and r.lot_multiplier == 1.0


# ============================================================
# TOPIC 3 - SYMBOL-SPECIFIC THRESHOLDS  (9 tests)
# DETECTED ISSUE: Global extreme=3.5 wrong for all assets.
# EXACT PATCH: _DEFAULT_SYMBOL_THRESHOLDS per-asset. add_symbol_threshold() override.
# RISK: BTC always blocked in normal market; Gold passes flash crashes.
# COMPAT: Unknown symbols use VolatilityFilterConfig extreme (default 3.5).
# ============================================================
class TestSymbolSpecificThresholds:
    def test_gold_tighter_extreme(self):
        # XAUUSD extreme=3.0; ratio=3.1 -> blocked
        assert VolatilityFilter().check(3.1,[1.0]*20,0.01,0.01,"XAUUSD").can_trade is False

    def test_gold_below_extreme_allowed(self):
        assert VolatilityFilter().check(2.9,[1.0]*20,0.01,0.01,"XAUUSD").can_trade is True

    def test_btc_lower_extreme(self):
        # BTCUSD extreme=2.2; ratio=2.3 -> blocked
        assert VolatilityFilter().check(2.3,[1.0]*20,50.0,50.0,"BTCUSD").can_trade is False

    def test_btc_normal_allowed(self):
        assert VolatilityFilter().check(1.5,[1.0]*20,50.0,50.0,"BTCUSD").can_trade is True

    def test_eurusd_standard(self):
        # EURUSD extreme=3.5; ratio=3.4 -> allowed
        assert VolatilityFilter().check(3.4,[1.0]*20,0.0001,0.0001,"EURUSD").can_trade is True

    def test_gbpjpy_looser(self):
        # GBPJPY extreme=4.2; ratio=3.8 -> allowed
        assert VolatilityFilter().check(3.8,[1.0]*20,0.01,0.01,"GBPJPY").can_trade is True

    def test_isolation_btc_vs_eurusd(self):
        vf = VolatilityFilter()
        assert vf.check(2.3,[1.0]*20,50.0,50.0,"BTCUSD").can_trade is False
        assert vf.check(2.3,[1.0]*20,0.0001,0.0001,"EURUSD").can_trade is True

    def test_override_at_runtime(self):
        vf = VolatilityFilter()
        vf.add_symbol_threshold("XAUUSD",SymbolThresholds(0.5,1.5,5.0))
        assert vf.check(4.0,[1.0]*20,0.01,0.01,"XAUUSD").can_trade is True

    def test_unknown_symbol_config_fallback(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(extreme_volatility_ratio=4.0))
        assert vf.check(3.8,[1.0]*20,0.0001,0.0001,"EXOTIC123").can_trade is True


# ============================================================
# TOPIC 4 - GOLD PIP VALUE  (13 tests)
# DETECTED ISSUE: XAUUSD=10.0 in both modules before FIX #4.
# EXACT PATCH: 'XAUUSD': 1.0 in lot_sizing.py and portfolio_risk.py.
# RISK: pip=10 -> lot 10x undersized -> actual risk = 10% of intended.
# COMPAT: _get_pip_value/_get_pip_value_with_source/_resolve_canonical unchanged.
# ============================================================
class TestGoldPipValue:
    def test_pr_xauusd_is_1(self):
        assert _pr_mod._PIP_VALUE_TABLE["XAUUSD"] == 1.0

    def test_ls_xauusd_is_1(self):
        assert _ls_mod._PIP_VALUE_TABLE["XAUUSD"] == 1.0

    def test_gold_alias(self):
        pip, _ = _pr_mod._get_pip_value_with_source("GOLD")
        assert pip == 1.0

    def test_xauusdm_suffix(self):
        pip, _ = _pr_mod._get_pip_value_with_source("XAUUSDm")
        assert pip == 1.0

    def test_xagusd_is_50(self):
        assert _pr_mod._PIP_VALUE_TABLE["XAGUSD"] == 50.0

    def test_gold_risk_1pct(self):
        # dist=50, lot=2, pip=1.0, bal=10000 -> 1.0% (was 10.0% with pip=10)
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=2.0,entry_price=1900.0,stop_loss=1850.0,account_balance=10000.0)
        assert abs(t.risk_percent - 1.0) < 0.01

    def test_gold_not_overrisked(self):
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=5.0,entry_price=2000.0,stop_loss=1980.0,account_balance=10000.0)
        assert t.risk_percent < 2.0

    def test_gold_gate_triggers(self):
        mgr = PortfolioRiskManager()
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=5000.0,entry_price=1950.0,stop_loss=1949.0,account_balance=10000.0)
        assert mgr.check(t,[]).can_trade is False

    def test_both_modules_agree(self):
        assert _ls_mod._PIP_VALUE_TABLE["XAUUSD"] == _pr_mod._PIP_VALUE_TABLE["XAUUSD"]

    def test_ls_gold_alias(self):
        canon = _ls_mod.LotSizer._resolve_canonical("GOLD")
        assert _ls_mod._PIP_VALUE_TABLE.get(canon) == 1.0

    def test_source_not_fallback(self):
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=1.0,entry_price=1950.0,stop_loss=1940.0,account_balance=10000.0)
        assert "fallback" not in t.pip_value_source

    def test_pip_value_used_field(self):
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=1.0,entry_price=2000.0,stop_loss=1990.0,account_balance=10000.0)
        assert t.pip_value_used == 1.0

    def test_injected_overrides_table(self):
        t = OpenTradeRisk(symbol="XAUUSD",direction=TradeDirection.BUY,
                          lot_size=1.0,entry_price=2000.0,stop_loss=1990.0,
                          account_balance=10000.0,pip_value_per_lot=5.0)
        assert t.pip_value_used == 5.0


# ============================================================
# TOPIC 5 - CRYPTO PIP VALUE  (12 tests)
# DETECTED ISSUE: ETHUSD=0.01 (100x too small) before FIX #4.
# EXACT PATCH: BTCUSD=ETHUSD=LTCUSD=XRPUSD=1.0 in both modules.
# RISK: lot 100x oversized -> instant account wipe on first crypto trade.
# COMPAT: table lookups, aliases, suffix stripping unchanged.
# ============================================================
class TestCryptoPipValue:
    _COINS = ["BTCUSD","ETHUSD","LTCUSD","XRPUSD"]

    def test_btcusd_both(self):
        assert _ls_mod._PIP_VALUE_TABLE["BTCUSD"] == 1.0
        assert _pr_mod._PIP_VALUE_TABLE["BTCUSD"] == 1.0

    def test_ethusd_both(self):
        assert _ls_mod._PIP_VALUE_TABLE["ETHUSD"] == 1.0
        assert _pr_mod._PIP_VALUE_TABLE["ETHUSD"] == 1.0

    def test_ltcusd_is_1(self):
        assert _ls_mod._PIP_VALUE_TABLE["LTCUSD"] == 1.0

    def test_xrpusd_is_1(self):
        assert _ls_mod._PIP_VALUE_TABLE["XRPUSD"] == 1.0

    def test_btc_alias(self):
        pip, _ = _pr_mod._get_pip_value_with_source("BTC")
        assert pip == 1.0

    def test_eth_alias(self):
        pip, _ = _pr_mod._get_pip_value_with_source("ETH")
        assert pip == 1.0

    def test_btcusdm_suffix(self):
        pip, _ = _pr_mod._get_pip_value_with_source("BTCUSDm")
        assert pip == 1.0

    def test_all_coins_consistent(self):
        for sym in self._COINS:
            assert _ls_mod._PIP_VALUE_TABLE.get(sym) == _pr_mod._PIP_VALUE_TABLE.get(sym)

    def test_btc_risk_correct(self):
        # dist=500, lot=0.1, pip=1.0, bal=10000 -> 0.5%
        t = OpenTradeRisk(symbol="BTCUSD",direction=TradeDirection.BUY,
                          lot_size=0.1,entry_price=50000.0,stop_loss=49500.0,account_balance=10000.0)
        assert abs(t.risk_percent - 0.5) < 0.01

    def test_eth_not_overrisked(self):
        t = OpenTradeRisk(symbol="ETHUSD",direction=TradeDirection.BUY,
                          lot_size=0.01,entry_price=3000.0,stop_loss=2900.0,account_balance=10000.0)
        assert t.risk_percent < 2.0

    def test_pip_value_used_field(self):
        t = OpenTradeRisk(symbol="BTCUSD",direction=TradeDirection.BUY,
                          lot_size=0.01,entry_price=50000.0,stop_loss=49000.0,account_balance=10000.0)
        assert t.pip_value_used == 1.0

    def test_pip_source_not_fallback(self):
        t = OpenTradeRisk(symbol="ETHUSD",direction=TradeDirection.BUY,
                          lot_size=0.01,entry_price=3000.0,stop_loss=2800.0,account_balance=10000.0)
        assert "fallback" not in t.pip_value_source


# ============================================================
# TOPIC 6 - EXPOSURE CALCULATION  (14 tests)
# DETECTED ISSUE: FIX #5: hardcoded risk=1.0 in orchestrator. FIX #6: no try/except.
# EXACT PATCH: actual new_risk_percent passed through; try/except added.
# RISK: Wrong risk=1.0 bypasses symbol limit silently; no except = gate bypass.
# COMPAT: check(symbol, direction, risk_percent, positions) unchanged.
# ============================================================
class TestExposureCalculation:
    def _ec(self, **kw):
        return ExposureControlEngine(config=ExposureControlConfig(**kw))

    def test_total_blocked(self):
        ec = self._ec()
        ops = [_pos("EURUSD",1.0),_pos("GBPUSD",1.0),_pos("AUDUSD",1.0),_pos("USDCAD",1.0)]
        r = ec.check("NZDUSD","BUY",1.5,ops)
        assert r.can_trade is False and "Total" in r.reason

    def test_total_boundary_allowed(self):
        # 2 BUY + 2 SELL + new SELL: total=5.0 NOT >5.0, sell=3 NOT >3
        ec = self._ec()
        ops = [_pos("EURUSD",1.0,"BUY"),_pos("GBPUSD",1.0,"BUY"),
               _pos("CADJPY",1.0,"SELL"),_pos("NZDUSD",1.0,"SELL")]
        assert ec.check("CHFJPY","SELL",1.0,ops).can_trade is True

    def test_symbol_blocked(self):
        assert self._ec().check("EURUSD","SELL",1.0,[_pos("EURUSD",1.5)]).can_trade is False

    def test_symbol_boundary_allowed(self):
        assert self._ec().check("EURUSD","SELL",1.0,[_pos("EURUSD",1.0)]).can_trade is True

    def test_max_simultaneous_blocked(self):
        ec = self._ec(max_simultaneous_trades=5)
        ops = [_pos(f"P{i}",0.5) for i in range(5)]
        r = ec.check("P9","BUY",0.5,ops)
        assert r.can_trade is False and "simultaneous" in r.reason

    def test_max_simultaneous_boundary(self):
        ec = self._ec(max_simultaneous_trades=5,max_buy_trades=10,max_sell_trades=10)
        ops = [_pos(f"P{i}",0.5) for i in range(4)]
        assert ec.check("P9","BUY",0.5,ops).can_trade is True

    def test_max_buy_blocked(self):
        ec = self._ec(max_buy_trades=3)
        ops = [_pos("EU",0.5,"BUY"),_pos("GU",0.5,"BUY"),_pos("AU",0.5,"BUY")]
        r = ec.check("NU","BUY",0.5,ops)
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


# ============================================================
# TOPIC 7 - FAIL-CLOSED BEHAVIOUR  (22 tests)
# DETECTED ISSUE: CF silent FAIL_OPEN; EC/VF/PR no try/except.
# EXACT PATCH: fail_mode.py SSoT; all 4 gates try/except; _fail_mode cached.
# RISK: Silent FAIL_OPEN = unlimited correlated exposure undetected.
# COMPAT: FailMode.FAIL_CLOSED.value=="FAIL_CLOSED"; all signatures unchanged.
# ============================================================
class TestFailClosedBehaviour:
    def test_ssot_vf(self):
        assert _vf_mod.FailMode.FAIL_CLOSED.value == _fm_mod.FailMode.FAIL_CLOSED.value

    def test_ssot_ec(self):
        assert _ec_mod.FailMode.FAIL_CLOSED.value == _fm_mod.FailMode.FAIL_CLOSED.value

    def test_ssot_cf(self):
        assert _cf_mod.FailMode.FAIL_CLOSED.value == _fm_mod.FailMode.FAIL_CLOSED.value

    def test_ssot_pr(self):
        assert _pr_mod.FailMode.FAIL_CLOSED.value == _fm_mod.FailMode.FAIL_CLOSED.value

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
        assert _fm_mod.coerce("fail_closed") is FailMode.FAIL_CLOSED

    def test_coerce_upper(self):
        assert _fm_mod.coerce("FAIL_OPEN") is FailMode.FAIL_OPEN

    def test_coerce_passthrough(self):
        assert _fm_mod.coerce(FailMode.FAIL_CLOSED) is FailMode.FAIL_CLOSED

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
        cfg = PortfolioRiskConfig(fail_mode=_pr_mod.FailMode.FAIL_CLOSED)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr,"_check_inner",side_effect=RuntimeError()):
            r = mgr.check(_trade(),[])
        assert r.can_trade is False and "FAIL_CLOSED" in r.reason

    def test_pr_open_allows(self):
        cfg = PortfolioRiskConfig(fail_mode=_pr_mod.FailMode.FAIL_OPEN)
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


# ============================================================
# TOPIC 8 - PORTFOLIO CORRELATION CALCULATIONS  (16 tests)
# DETECTED ISSUE: check() no outer try/except -> outer crash bypassed fail_mode.
# EXACT PATCH: check() wraps _check_inner() in try/except with fail_mode routing.
# RISK: 3x correlated BUY = 2.5% corr risk -> account overexposed.
# COMPAT: check(symbol, direction, open_positions, base_risk_percent) unchanged.
# ============================================================
class TestPortfolioCorrelationCalcs:
    def _cf(self, **kw):
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
        assert _cf_mod._canonical("EURUSD","GBPUSD") == _cf_mod._canonical("GBPUSD","EURUSD")


# ============================================================
# INTEGRATION - CROSS-GATE REGRESSION  (5 tests)
# ============================================================
class TestIntegration:
    def test_all_gates_accept_fail_mode(self):
        VolatilityFilter(config=VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED))
        ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        PortfolioRiskManager(config=PortfolioRiskConfig(fail_mode=_pr_mod.FailMode.FAIL_CLOSED))

    def test_xauusd_not_10(self):
        assert _ls_mod._PIP_VALUE_TABLE["XAUUSD"] != 10.0
        assert _pr_mod._PIP_VALUE_TABLE["XAUUSD"] != 10.0

    def test_crypto_not_001(self):
        for sym in ["BTCUSD","ETHUSD","LTCUSD"]:
            assert _ls_mod._PIP_VALUE_TABLE.get(sym) != 0.01
            assert _pr_mod._PIP_VALUE_TABLE.get(sym) != 0.01

    def test_production_thresholds(self):
        tbl = _vf_mod._DEFAULT_SYMBOL_THRESHOLDS
        assert tbl["XAUUSD"].extreme == 3.0
        assert tbl["BTCUSD"].extreme == 2.2
        assert tbl["EURUSD"].extreme == 3.5
        assert tbl["GBPJPY"].extreme == 4.2

    def test_async_sync_agree(self):
        mgr = PortfolioRiskManager()
        t = _trade(symbol="EURUSD",lot=100,entry=1.11,sl=1.10,bal=10000)
        rs = mgr.check(t,[])
        ra = _run(mgr.check_async(t,[]))
        assert rs.can_trade == ra.can_trade and rs.reason == ra.reason
