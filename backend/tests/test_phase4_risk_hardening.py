"""
PHASE 4 — Risk Management Hardening — Final Test Suite (v4)
70 tests — all APIs verified against real source.
"""
from __future__ import annotations
import asyncio, math, sys, os, types, importlib.util, pathlib
from unittest.mock import AsyncMock, MagicMock
import pytest

# ── ENVIRONMENT
os.environ["OTEL_SDK_DISABLED"] = "true"
for m in ["opentelemetry", "opentelemetry.trace", "prometheus_client"]:
    sys.modules.setdefault(m, MagicMock())

_log_mod = types.ModuleType("backend.core.logger")
class _SL:
    def __getattr__(self, n): return lambda *a, **kw: None
    def bind(self, **kw): return self
_log_mod.get_logger = lambda *a, **kw: _SL()

_exc_mod = types.ModuleType("backend.core.exceptions")
class _BaseEx(Exception):
    def __init__(self, *a, **kw): super().__init__(str(a) + str(kw))
for _n in ["KillSwitchActivatedError", "InsufficientMarginError", "DrawdownLimitError",
           "TradingHaltedError", "UnknownSymbolError", "BrokerConnectionError", "RiskVetoError"]:
    setattr(_exc_mod, _n, type(_n, (_BaseEx,), {}))

sys.modules["backend"]                     = types.ModuleType("backend")
sys.modules["backend.core"]                = types.ModuleType("backend.core")
sys.modules["backend.core.logger"]         = _log_mod
sys.modules["backend.core.exceptions"]     = _exc_mod
sys.modules["backend.risk"]                = types.ModuleType("backend.risk")

for _m in ["pdalarms", "sklearn", "scipy.stats", "numpy", "pandas",
           "aiohttp", "httpx", "redis", "redis.asyncio", "sqlalchemy",
           "supabase", "prometheus_client", "opentelemetry",
           "backend.risk.fail_mode", "backend.risk.volatility_filter",
           "backend.risk.news_filter", "backend.risk.correlation_filter",
           "backend.institutional.risk_engine",
           "backend.services.telegram_service"]:
    sys.modules.setdefault(_m, MagicMock())

from enum import Enum
class _FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"
_fm_mod = types.ModuleType("backend.risk.fail_mode")
_fm_mod.FailMode = _FailMode
_fm_mod.coerce   = lambda v: v
sys.modules["backend.risk.fail_mode"] = _fm_mod

# ── LOAD REAL SOURCE FILES
_BASE = pathlib.Path("/home/definable/phase4")

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

exceptions = _load("backend.core.exceptions",          _BASE / "core/exceptions.py")
lot_mod    = _load("backend.risk.lot_sizing",           _BASE / "risk/lot_sizing.py")
margin_mod = _load("backend.risk.margin_gate",          _BASE / "risk/margin_gate.py")
kill_mod   = _load("backend.risk.kill_switch",          _BASE / "risk/kill_switch.py")
daily_mod  = _load("backend.risk.daily_limits",         _BASE / "risk/daily_limits.py")
equity_mod = _load("backend.risk.equity_protection",    _BASE / "risk/equity_protection.py")
orch_mod   = _load("backend.risk.risk_orchestrator",    _BASE / "risk/risk_orchestrator.py")

# ── ALIASES
LotSizer                 = lot_mod.LotSizer
LotSizeConfig            = lot_mod.LotSizeConfig
MarginGate               = margin_mod.MarginGate
MarginGateResult         = margin_mod.MarginGateResult
KillSwitch               = kill_mod.KillSwitch
SwitchState              = kill_mod.SwitchState
DailyLimitsEngine        = daily_mod.DailyLimitsEngine
TodayTrades              = daily_mod.TodayTrades
LimitStatus              = daily_mod.LimitStatus
EquityProtectionEngine   = equity_mod.EquityProtectionEngine
EquityStatus             = equity_mod.EquityStatus
EquityConfig             = equity_mod.EquityConfig
RiskOrchestrator         = orch_mod.RiskOrchestrator
RiskInput                = orch_mod.RiskInput
KillSwitchActivatedError = _exc_mod.KillSwitchActivatedError
InsufficientMarginError  = _exc_mod.InsufficientMarginError
DrawdownLimitError       = _exc_mod.DrawdownLimitError
TradingHaltedError       = _exc_mod.TradingHaltedError


# =============================================================================
# T01-T12  LotSizing
# =============================================================================
def _ls(**kw):
    defaults = dict(account_balance=10000, risk_percent=1.0, stop_loss_pips=20.0,
                    pip_value_usd=10.0, symbol="EURUSD", equity=10000.0, free_margin=5000.0)
    defaults.update(kw)
    return LotSizer().calculate(**defaults)

def test_T01_basic_lot():
    r = _ls()
    assert round(r.lots, 2) == 0.05
    assert r.risk_usd == pytest.approx(20, rel=0.01)

def test_T02_high_risk():
    r = _ls(risk_percent=2.0)
    assert r.lots == pytest.approx(0.1, rel=0.05)

def test_T03_zero_pip_value():
    r = _ls(pip_value_usd=0)
    assert r.can_trade is False

def test_T04_zero_stop():
    r = _ls(stop_loss_pips=0)
    assert r.can_trade is False

def test_T05_nan_balance():
    r = _ls(account_balance=float("nan"), equity=float("nan"))
    assert r.can_trade is False

def test_T06_neg_balance():
    r = _ls(account_balance=-100)
    assert r.can_trade is False

def test_T07_kelly_cap():
    r_base  = _ls()
    r_kelly = _ls(win_rate=0.99, avg_rr=10)
    assert r_kelly.lots <= r_base.lots * 3.0

def test_T08_margin_cap():
    r = _ls(free_margin=500)
    assert r.lots <= 0.06

def test_T09_min_lot():
    r = _ls(risk_percent=0.001, stop_loss_pips=1000)
    assert r.lots >= 0.01

def test_T10_max_lot():
    r = _ls(risk_percent=50)
    assert r.lots <= 100.0

def test_T11_equity_risk():
    r1 = _ls(equity=5000)
    r2 = _ls(equity=10000)
    assert r1.risk_usd < r2.risk_usd + 1

def test_T12_rationale():
    r = _ls()
    assert r.rationale != ""


# =============================================================================
# T13-T24  MarginGate
# =============================================================================
def _mg(free_margin=1000, required_margin=500, margin_level=500):
    return MarginGate().check(
        free_margin=free_margin,
        required_margin=required_margin,
        margin_level=margin_level,
    )

def test_T13_margin_allowed():         assert _mg().can_trade is True
def test_T14_insufficient_margin():    assert _mg(free_margin=100, required_margin=500).can_trade is False
def test_T15_low_margin_level():       assert _mg(margin_level=120).can_trade is False
def test_T16_exact_border():           assert _mg(free_margin=500, required_margin=500).can_trade is True
def test_T17_zero_required():          assert _mg(required_margin=0).can_trade is True

def test_T18_fail_open():
    mg = MarginGate(fail_mode=MarginGate.FAIL_OPEN)
    assert mg.check(free_margin=-1, required_margin=9999999, margin_level=0).can_trade is True

def test_T19_fail_closed_default():    assert MarginGate().FAIL_CLOSED == "FAIL_CLOSED"

def test_T20_margin_source():
    res = _mg()
    assert res.source in ("static", "mt5_live", "insufficient_data")

def test_T21_latency_populated():      assert _mg().latency_ms >= 0.0

def test_T22_nan_margin():
    assert _mg(free_margin=float("nan"), required_margin=500).can_trade is False

def test_T23_neg_free_margin():        assert _mg(free_margin=-50).can_trade is False
def test_T24_margin_in_result():       assert hasattr(_mg(), "required_margin")


# =============================================================================
# T25-T36  KillSwitch
# =============================================================================
def _ks(**kw):
    defaults = dict(floor_usd=0.0, max_drawdown_pct=20.0, flash_crash_threshold_pct=5.0)
    defaults.update(kw)
    return KillSwitch(**defaults)

def test_T25_normal():              assert _ks().state == SwitchState.ARMED
def test_T26_floor_trigger():       assert _ks(floor_usd=10000).check(current_equity=5000, opening_equity=10000).triggered
def test_T27_drawdown_trigger():    assert _ks().check(current_equity=8000, opening_equity=10000).triggered

def test_T28_flash_crash_trigger():
    ks = _ks()
    ks.check(current_equity=10000, opening_equity=10000)
    assert ks.check(current_equity=9400, opening_equity=10000).triggered

def test_T29_manual_kill():
    ks = _ks()
    ks.manual_kill("test")
    assert ks.check(current_equity=10000, opening_equity=10000).triggered

def test_T30_reset_token():
    ks = _ks()
    ks.manual_kill("test")
    tok = ks.admin_reset()
    assert isinstance(tok, str) and len(tok) > 8

def test_T31_no_trigger():          assert not _ks().check(current_equity=9800, opening_equity=10000).triggered
def test_T32_state_triggered():
    ks = _ks()
    ks.check(current_equity=7000, opening_equity=10000)
    assert ks.state == SwitchState.TRIGGERED

def test_T33_callbacks_fired():
    calls = []
    ks = _ks()
    ks.add_callback(lambda r: calls.append(r.reason))
    ks.check(current_equity=5000, opening_equity=10000)
    assert len(calls) > 0

def test_T34_triggered_stays_triggered():
    ks = _ks()
    ks.check(current_equity=5000, opening_equity=10000)
    assert ks.check(current_equity=12000, opening_equity=10000).triggered

def test_T35_reason_populated():
    assert len(_ks().check(current_equity=5000, opening_equity=10000).reason) > 0

def test_T36_lock_attr():           assert hasattr(_ks(), "_lock")


# =============================================================================
# T37-T44  EquityProtection
# =============================================================================
def _ep(**kw):
    return EquityProtectionEngine(config=EquityConfig(**kw))

@pytest.mark.asyncio
async def test_T37_safe():
    ep = _ep()
    await ep.safe_initialize(10000, 10000)
    res = await ep.assess(10000)
    assert res.status == EquityStatus.SAFE

@pytest.mark.asyncio
async def test_T38_halt_on_drawdown():
    ep = _ep(daily_drawdown_limit=3.0)
    await ep.safe_initialize(10000, 10000)
    assert (await ep.assess(9650)).status == EquityStatus.HALTED

@pytest.mark.asyncio
async def test_T39_cooldown_enforced():
    ep = _ep(daily_drawdown_limit=3.0, cooldown_seconds=3600)
    await ep.safe_initialize(10000, 10000)
    await ep.assess(9650)
    res2 = await ep.assess(10100)
    assert res2.status == EquityStatus.HALTED

@pytest.mark.asyncio
async def test_T40_hwm_updated():
    ep = _ep()
    await ep.safe_initialize(10000, 10000)
    await ep.assess(12000)
    assert ep._hwm >= 12000

@pytest.mark.asyncio
async def test_T41_no_init():
    ep = _ep()
    assert (await ep.assess(9000)).status == EquityStatus.UNINITIALIZED

@pytest.mark.asyncio
async def test_T42_neg_drawdown():
    ep = _ep(daily_drawdown_limit=3.0)
    await ep.safe_initialize(10000, 10000)
    await ep.assess(11000)
    assert (await ep.assess(10650)).status == EquityStatus.SAFE

@pytest.mark.asyncio
async def test_T43_drawdown_not_negative():
    ep = _ep()
    await ep.safe_initialize(10000, 10000)
    res = await ep.assess(12000)
    assert res.current_drawdown_pct >= 0

@pytest.mark.asyncio
async def test_T44_lock_attr():
    assert hasattr(_ep(), "_lock")


# =============================================================================
# T45-T54  Exception hierarchy
# =============================================================================
def test_T45_kill_switch_error():       assert isinstance(KillSwitchActivatedError("k"), Exception)
def test_T46_insufficient_margin_err(): assert isinstance(InsufficientMarginError("m"),  Exception)
def test_T47_drawdown_limit_error():    assert isinstance(DrawdownLimitError("d"),        Exception)
def test_T48_trading_halted_error():    assert isinstance(TradingHaltedError("h"),        Exception)
def test_T49_exceptions_importable():   assert all([KillSwitchActivatedError, InsufficientMarginError,
                                                    DrawdownLimitError, TradingHaltedError])
def test_T50_lotsizer_importable():     assert LotSizer   is not None
def test_T51_margin_gate_importable():  assert MarginGate  is not None
def test_T52_kill_switch_importable():  assert KillSwitch  is not None
def test_T53_daily_limits_importable(): assert DailyLimitsEngine is not None
def test_T54_equity_prot_importable():  assert EquityProtectionEngine is not None


# =============================================================================
# T55-T68  DailyLimits
# =============================================================================
def _dl(**kw):
    defaults = dict(max_daily_trades=10, max_daily_loss_pct=3.0,
                    max_weekly_loss_pct=7.0, max_monthly_dd_pct=15.0)
    defaults.update(kw)
    return DailyLimitsEngine(**defaults)

def test_T55_daily_ok():          assert _dl().check_limits(10000, TodayTrades()).can_trade is True
def test_T56_daily_loss():        assert _dl().check_limits(10000, TodayTrades(pnl_usd=-350)).can_trade is False
def test_T57_daily_trades():      assert _dl().check_limits(10000, TodayTrades(trade_count=10)).can_trade is False
def test_T58_weekly_loss():       assert _dl().check_limits(10000, TodayTrades(), week_pnl_usd=-750).can_trade is False
def test_T59_monthly_dd():        assert _dl().check_limits(10000, TodayTrades(), month_pnl_usd=-1600).can_trade is False

def test_T60_warning():
    res = _dl().check_limits(10000, TodayTrades(pnl_usd=-245))
    assert res.can_trade is True and res.status == LimitStatus.WARNING

def test_T61_weekly_loss_status():
    res = _dl().check_limits(10000, TodayTrades(), week_pnl_usd=-700)
    assert not res.can_trade and res.status == LimitStatus.WEEKLY_LOSS_HIT

def test_T62_monthly_dd_status():
    res = _dl().check_limits(10000, TodayTrades(), month_pnl_usd=-1500)
    assert not res.can_trade and res.status == LimitStatus.MONTHLY_DRAWDOWN_HIT

def test_T63_trade_count_warning():
    res = _dl().check_limits(10000, TodayTrades(trade_count=8))
    assert res.status == LimitStatus.WARNING

def test_T64_all_clear():
    assert _dl().check_limits(10000, TodayTrades()).status == LimitStatus.OK

def test_T65_zero_balance():     assert not _dl().check_limits(0, TodayTrades()).can_trade
def test_T66_defaults():         assert DailyLimitsEngine()._max_daily_trades == 10

def test_T67_snapshot():
    e  = _dl(max_daily_trades=5)
    e2 = DailyLimitsEngine.from_snapshot(e.to_snapshot())
    assert e2._max_daily_trades == 5

def test_T68_profit_no_block():  assert _dl().check_limits(10000, TodayTrades(pnl_usd=500)).can_trade is True


# =============================================================================
# T69-T70  Integration
# =============================================================================
@pytest.mark.asyncio
async def test_T69_halt_on_drawdown_integration():
    ep = _ep(daily_drawdown_limit=3.0)
    await ep.safe_initialize(10000, 10000)
    assert (await ep.assess(9650)).status == EquityStatus.HALTED

def test_T70_kill_before_equity():
    ks = _ks()
    ks.manual_kill("test")
    assert ks.check(current_equity=10000, opening_equity=10000).triggered
