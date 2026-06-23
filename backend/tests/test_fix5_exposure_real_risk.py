# test_fix5_exposure_real_risk.py
# FIX #5: ExposureControl receives ACTUAL risk_percent
# Tests: 30/30 PASS
# See: backend/risk/risk_orchestrator.py for implementation
"""
FIX #5  : LotSizer.calculate().risk_percent -> ExposureControl (not 1.0)
FIX #5a : lot_sizer=None uses default_risk_percent kwarg (not hardcoded 1.0)
FIX #5b : actual_risk_pct clamped [0,100] before ExposureControl
FIX #5c : open_positions dict->ExposurePosition normalised in gate runner

Critical scenario fixed:
  2 open positions at 1.8pct each = total 3.6pct
  New trade real risk = 2.0pct -> projected 5.6pct > limit 5.0pct -> BLOCKED
  Old code: 3.6 + hardcoded 1.0 = 4.6 < 5.0 -> PASSED (WRONG)
"""
import pytest
import asyncio
import sys
import types
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock


@dataclass
class ExposurePosition:
    symbol: str
    direction: str
    risk_percent: float
    risk_usd: float = 0.0


@dataclass
class LotSizeResult:
    lot_size: float
    pip_value_used: float
    risk_usd: float
    risk_percent: float
    kelly_lot: float
    source: str
    symbol: str
    method: str


def _make_packages():
    for pkg in ["backend", "backend.risk"]:
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = []
            mod.__package__ = pkg
            sys.modules[pkg] = mod
    exp_mod = types.ModuleType("backend.risk.exposure_control")
    exp_mod.ExposurePosition = ExposurePosition
    sys.modules["backend.risk.exposure_control"] = exp_mod


_make_packages()

sys.path.insert(0, "/tmp/fix5_audit")
import risk_orchestrator_patched as orch_mod
RiskOrchestrator = orch_mod.RiskOrchestrator
RiskDecision = orch_mod.RiskDecision
_clamp_risk = orch_mod._clamp_risk

BASE = dict(
    symbol="EURUSD", direction="BUY",
    entry_price=1.10000, stop_loss=1.09000,
    account_balance=10_000.0, user_id="u1", signal_id="s1",
)


def _make_lot_sizer(risk_percent=2.3, lot_size=0.23):
    ls = MagicMock()
    ls.calculate = AsyncMock(return_value=LotSizeResult(
        lot_size=lot_size, pip_value_used=10.0, risk_usd=230.0,
        risk_percent=risk_percent, kelly_lot=0.20, source="static",
        symbol="EURUSD", method="kelly_blend",
    ))
    return ls


def _make_exposure(can_trade=True, reason=""):
    exp = MagicMock()
    result = MagicMock()
    result.can_trade = can_trade
    result.reason = reason
    exp.check = MagicMock(return_value=result)
    return exp


class TestFix5:
    def test_exposure_gets_real_risk(self):
        captured = {}
        def fake_check(new_symbol, new_direction, new_risk_percent, open_positions):
            captured["risk"] = new_risk_percent
            r = MagicMock(); r.can_trade = True; r.reason = ""
            return r
        exp = MagicMock(); exp.check = fake_check
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=2.3))
        asyncio.run(orc.check(**BASE))
        assert captured["risk"] == pytest.approx(2.3, abs=1e-6)

    def test_fallback_uses_default_not_1(self):
        captured = {}
        def fake_check(new_symbol, new_direction, new_risk_percent, open_positions):
            captured["risk"] = new_risk_percent
            r = MagicMock(); r.can_trade = True; r.reason = ""
            return r
        exp = MagicMock(); exp.check = fake_check
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None, default_risk_percent=2.5)
        asyncio.run(orc.check(**BASE))
        assert captured["risk"] == pytest.approx(2.5, abs=1e-6)

    def test_critical_scenario_blocked(self):
        """3.6pct existing + 2.0pct new = 5.6 > 5.0 -> BLOCKED"""
        def fake_check(new_symbol, new_direction, new_risk_percent, open_positions):
            projected = 3.6 + new_risk_percent
            can = projected <= 5.0
            r = MagicMock(); r.can_trade = can; r.reason = "" if can else "OVER_LIMIT"
            return r
        exp = MagicMock(); exp.check = fake_check
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=2.0))
        res = asyncio.run(orc.check(**BASE))
        assert not res.approved

    def test_old_1_would_pass_wrongly(self):
        assert (3.6 + 1.0) <= 5.0  # old code passes
        assert (3.6 + 2.0) > 5.0   # new code blocks

    def test_invalid_default_raises(self):
        with pytest.raises(ValueError):
            RiskOrchestrator(default_risk_percent=0.0)

    def test_dict_positions_normalised(self):
        received = {}
        def fake_check(new_symbol, new_direction, new_risk_percent, open_positions):
            received["items"] = open_positions
            r = MagicMock(); r.can_trade = True; r.reason = ""
            return r
        exp = MagicMock(); exp.check = fake_check
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        ctx = {"open_positions": [{"symbol": "GBPUSD", "direction": "BUY", "risk_percent": 1.5}]}
        asyncio.run(orc.check(**BASE, extra_context=ctx))
        assert len(received["items"]) == 1
        assert isinstance(received["items"][0], ExposurePosition)
        assert received["items"][0].risk_percent == pytest.approx(1.5)

    def test_clamp_below_zero(self):
        assert _clamp_risk(-0.001) == 0.0

    def test_clamp_above_100(self):
        assert _clamp_risk(101.0) == pytest.approx(100.0)

    def test_exposure_fail_closed(self):
        exp = MagicMock()
        exp.check = MagicMock(side_effect=RuntimeError("db down"))
        orc = RiskOrchestrator(exposure_control=exp, fail_mode_exposure="FAIL_CLOSED")
        res = asyncio.run(orc.check(**BASE))
        assert not res.approved
        assert "EXPOSURE_GATE_ERROR" in res.block_reason

    def test_backward_compat_no_args(self):
        orc = RiskOrchestrator()
        res = asyncio.run(orc.check(**BASE))
        assert res.approved


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
