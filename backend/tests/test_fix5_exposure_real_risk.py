"""
test_fix5_exposure_real_risk.py
================================
FIX #5 -- Exposure Control Using Real Risk

Covers every sub-fix:
  FIX-5A: default_risk_percent replaces hardcoded 1.0
  FIX-5B: _clamp_risk() clamps to [0, 100]
  FIX-5C: dict open_positions normalised to ExposurePosition
  FIX-5D: _run_exposure_gate always passes clamped real risk
  FIX-5E: config_fallback uses default_risk_percent, not 1.0

Critical scenario:
  2 open positions at 1.8% each = total 3.6%
  New trade real risk = 2.0% -> projected 5.6% > 5.0% limit -> BLOCKED
  Old code: 3.6 + hardcoded 1.0 = 4.6 < 5.0 -> PASSED (WRONG)
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest


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


def _make_stub_packages():
    for pkg in ["backend", "backend.risk"]:
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = []
            m.__package__ = pkg
            sys.modules[pkg] = m

    exp_mod = types.ModuleType("backend.risk.exposure_control")
    exp_mod.ExposurePosition = ExposurePosition
    sys.modules["backend.risk.exposure_control"] = exp_mod

    pip_mod = types.ModuleType("backend.risk._pip_helpers")

    def _price_to_pips(s, d):
        s = s.upper().strip()
        ps = {
            "EURUSD": 0.0001,
            "GBPUSD": 0.0001,
            "USDJPY": 0.01,
            "XAUUSD": 0.01,
            "BTCUSD": 1.0,
        }.get(s, 0.0001)
        return round(d / ps, 6)

    def _estimate_risk_pct(sym, dist, lot, bal, pv=None):
        if not (bal > 0 and lot > 0 and dist > 0):
            return 0.0, "zero"
        pips = _price_to_pips(sym, dist)
        pip_val = 10.0
        return round((pips * lot * pip_val / bal) * 100.0, 4), "table"

    pip_mod._price_to_pips = _price_to_pips
    pip_mod._estimate_risk_pct = _estimate_risk_pct
    sys.modules["backend.risk._pip_helpers"] = pip_mod


_make_stub_packages()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import importlib.util


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ORCH_PATH = os.path.join(os.path.dirname(BASE_DIR), "risk", "risk_orchestrator.py")
orch_mod = _load_module(_ORCH_PATH, "risk_orchestrator_fix5")

RiskOrchestrator = orch_mod.RiskOrchestrator
RiskDecision = orch_mod.RiskDecision
_clamp_risk = orch_mod._clamp_risk
_normalise_positions = orch_mod._normalise_positions

BASE = dict(
    symbol="EURUSD",
    direction="BUY",
    entry_price=1.10000,
    stop_loss=1.09000,
    account_balance=10_000.0,
    user_id="u1",
    signal_id="s1",
)


def _make_lot_sizer(risk_percent=2.3, lot_size=0.23):
    ls = MagicMock()
    ls.calculate = AsyncMock(
        return_value=LotSizeResult(
            lot_size=lot_size,
            pip_value_used=10.0,
            risk_usd=230.0,
            risk_percent=risk_percent,
            kelly_lot=0.20,
            source="static",
            symbol="EURUSD",
            method="kelly_blend",
        )
    )
    return ls


def _capture_exposure(allow=True):
    calls = []

    def _check(new_symbol, new_direction, new_risk_percent, open_positions):
        calls.append({"symbol": new_symbol, "risk": new_risk_percent, "positions": open_positions})
        r = MagicMock()
        r.can_trade = allow
        r.reason = "" if allow else f"BLOCKED:{new_risk_percent:.3f}%"
        return r

    exp = MagicMock()
    exp.check = _check
    return exp, calls


def _run(coro):
    return asyncio.run(coro)


class TestClampRisk:
    def test_zero_stays_zero(self):
        assert _clamp_risk(0.0) == 0.0

    def test_negative_clamped(self):
        assert _clamp_risk(-5.0) == 0.0

    def test_slightly_negative(self):
        assert _clamp_risk(-0.001) == 0.0

    def test_normal_unchanged(self):
        assert _clamp_risk(2.5) == pytest.approx(2.5)

    def test_exactly_100(self):
        assert _clamp_risk(100.0) == pytest.approx(100.0)

    def test_above_100(self):
        assert _clamp_risk(101.0) == pytest.approx(100.0)

    def test_huge_clamped(self):
        assert _clamp_risk(9999.0) == pytest.approx(100.0)


class TestDefaultRiskPercent:
    def test_default_is_1(self):
        orc = RiskOrchestrator()
        assert orc._default_risk == pytest.approx(1.0)

    def test_custom_stored(self):
        orc = RiskOrchestrator(default_risk_percent=2.5)
        assert orc._default_risk == pytest.approx(2.5)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            RiskOrchestrator(default_risk_percent=0.0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            RiskOrchestrator(default_risk_percent=-1.0)

    def test_fallback_uses_default_not_1(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None, default_risk_percent=2.5)
        orig = orch_mod._estimate_risk_pct
        orch_mod._estimate_risk_pct = lambda *a, **kw: (0.0, "forced_zero")
        try:
            _run(orc.check(**BASE))
        finally:
            orch_mod._estimate_risk_pct = orig
        assert len(calls) == 1
        assert calls[0]["risk"] == pytest.approx(2.5, abs=1e-6)

    def test_not_hardcoded_1(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None, default_risk_percent=3.0)
        orig = orch_mod._estimate_risk_pct
        orch_mod._estimate_risk_pct = lambda *a, **kw: (0.0, "forced_zero")
        try:
            _run(orc.check(**BASE))
        finally:
            orch_mod._estimate_risk_pct = orig
        assert calls[0]["risk"] != pytest.approx(1.0, abs=1e-6)
        assert calls[0]["risk"] == pytest.approx(3.0, abs=1e-6)


class TestExposureReceivesRealRisk:
    def test_lot_sizer_forwarded(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=2.3))
        _run(orc.check(**BASE))
        assert calls[0]["risk"] == pytest.approx(2.3, abs=1e-6)

    def test_different_risks_different_exposure(self):
        exp1, calls1 = _capture_exposure(allow=True)
        exp2, calls2 = _capture_exposure(allow=True)
        _run(RiskOrchestrator(exposure_control=exp1, lot_sizer=_make_lot_sizer(1.0)).check(**BASE))
        _run(RiskOrchestrator(exposure_control=exp2, lot_sizer=_make_lot_sizer(4.5)).check(**BASE))
        assert calls1[0]["risk"] == pytest.approx(1.0, abs=1e-6)
        assert calls2[0]["risk"] == pytest.approx(4.5, abs=1e-6)

    def test_override_forwarded(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        _run(orc.check(**BASE, override_risk_pct=3.7))
        assert calls[0]["risk"] == pytest.approx(3.7, abs=1e-6)

    def test_high_risk_clamped(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=150.0))
        _run(orc.check(**BASE))
        assert calls[0]["risk"] == pytest.approx(100.0, abs=1e-6)

    def test_negative_risk_clamped(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=-2.0))
        _run(orc.check(**BASE))
        assert calls[0]["risk"] == pytest.approx(0.0, abs=1e-6)


class TestCriticalScenario:
    def _make_limit_exposure(self, limit=5.0, existing=3.6):
        calls = []

        def _check(new_symbol, new_direction, new_risk_percent, open_positions):
            projected = existing + new_risk_percent
            can = projected <= limit
            calls.append({"risk": new_risk_percent, "projected": projected})
            r = MagicMock()
            r.can_trade = can
            r.reason = "" if can else f"EXPOSURE:{projected:.2f}>{limit}"
            return r

        exp = MagicMock()
        exp.check = _check
        return exp, calls

    def test_old_1_wrongly_passes(self):
        assert (3.6 + 1.0) <= 5.0

    def test_new_real_correctly_blocked(self):
        assert (3.6 + 2.0) > 5.0

    def test_orchestrator_blocks_real_2pct(self):
        exp, calls = self._make_limit_exposure(5.0, 3.6)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=2.0))
        result = _run(orc.check(**BASE))
        assert not result.approved
        assert result.decision == RiskDecision.BLOCKED
        assert calls[0]["risk"] == pytest.approx(2.0, abs=1e-6)

    def test_orchestrator_passes_low_risk(self):
        exp, calls = self._make_limit_exposure(5.0, 3.6)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(risk_percent=1.0))
        result = _run(orc.check(**BASE))
        assert result.approved

    def test_proof_of_old_bug(self):
        assert (3.6 + 1.0) < 5.0
        assert (3.6 + 2.0) > 5.0


class TestDictPositionsNormalisation:
    def test_dict_converted(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        ctx = {"open_positions": [{"symbol": "GBPUSD", "direction": "BUY", "risk_percent": 1.5}]}
        _run(orc.check(**BASE, extra_context=ctx))
        items = calls[0]["positions"]
        assert len(items) == 1
        assert isinstance(items[0], ExposurePosition)
        assert items[0].risk_percent == pytest.approx(1.5)

    def test_multiple_dicts(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        ctx = {
            "open_positions": [
                {"symbol": "GBPUSD", "direction": "BUY", "risk_percent": 1.0},
                {"symbol": "EURUSD", "direction": "SELL", "risk_percent": 1.5},
                {"symbol": "XAUUSD", "direction": "BUY", "risk_percent": 0.8},
            ]
        }
        _run(orc.check(**BASE, extra_context=ctx))
        assert len(calls[0]["positions"]) == 3

    def test_dataclass_pass_through(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        existing = ExposurePosition("GBPUSD", "BUY", 1.2)
        ctx = {"open_positions": [existing]}
        _run(orc.check(**BASE, extra_context=ctx))
        assert calls[0]["positions"][0] is existing

    def test_mixed(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        ctx = {
            "open_positions": [
                ExposurePosition("GBPUSD", "BUY", 1.0),
                {"symbol": "USDJPY", "direction": "SELL", "risk_percent": 0.9},
            ]
        }
        _run(orc.check(**BASE, extra_context=ctx))
        items = calls[0]["positions"]
        assert len(items) == 2
        assert items[1].risk_percent == pytest.approx(0.9)

    def test_empty(self):
        exp, calls = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=None)
        _run(orc.check(**BASE, extra_context={"open_positions": []}))
        assert calls[0]["positions"] == []

    def test_normalise_helper(self):
        raw = [
            {"symbol": "EURUSD", "direction": "BUY", "risk_percent": 1.0, "risk_usd": 100.0},
            {"symbol": "XAUUSD", "direction": "SELL", "risk_percent": 2.0},
        ]
        result = _normalise_positions(raw)
        assert len(result) == 2
        assert result[0].symbol == "EURUSD"
        assert result[0].risk_percent == pytest.approx(1.0)
        assert result[1].risk_usd == pytest.approx(0.0)


class TestRiskSourceMetadata:
    def test_lot_sizer_source(self):
        exp, _ = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(1.5))
        result = _run(orc.check(**BASE))
        assert result.metadata["lot_sizing"]["risk_source"] == "lot_sizer"

    def test_override_source(self):
        orc = RiskOrchestrator()
        result = _run(orc.check(**BASE, override_risk_pct=2.2))
        assert result.metadata["lot_sizing"]["risk_source"] == "override"

    def test_config_fallback_source(self):
        orc = RiskOrchestrator(default_risk_percent=1.5)
        orig = orch_mod._estimate_risk_pct
        orch_mod._estimate_risk_pct = lambda *a, **kw: (0.0, "forced_zero")
        try:
            result = _run(orc.check(**BASE))
        finally:
            orch_mod._estimate_risk_pct = orig
        assert result.metadata["lot_sizing"]["risk_source"] == "config_fallback"

    def test_exposure_source_propagated(self):
        exp, _ = _capture_exposure(allow=True)
        orc = RiskOrchestrator(exposure_control=exp, lot_sizer=_make_lot_sizer(1.8))
        result = _run(orc.check(**BASE))
        assert result.metadata["exposure"]["risk_source"] == "lot_sizer"


class TestFailModes:
    def test_exposure_fail_closed(self):
        exp = MagicMock()
        exp.check = MagicMock(side_effect=RuntimeError("db down"))
        orc = RiskOrchestrator(exposure_control=exp, fail_mode_exposure="FAIL_CLOSED")
        result = _run(orc.check(**BASE))
        assert not result.approved
        assert "EXPOSURE_GATE_ERROR" in result.block_reason

    def test_exposure_fail_open(self):
        exp = MagicMock()
        exp.check = MagicMock(side_effect=RuntimeError("db down"))
        orc = RiskOrchestrator(exposure_control=exp, fail_mode_exposure="FAIL_OPEN")
        assert _run(orc.check(**BASE)).approved

    def test_correlation_fail_closed(self):
        corr = MagicMock()
        corr.check = MagicMock(side_effect=RuntimeError("corr fail"))
        orc = RiskOrchestrator(correlation_filter=corr, fail_mode_correlation="FAIL_CLOSED")
        assert not _run(orc.check(**BASE)).approved

    def test_correlation_fail_open(self):
        corr = MagicMock()
        corr.check = MagicMock(side_effect=RuntimeError("corr fail"))
        orc = RiskOrchestrator(correlation_filter=corr, fail_mode_correlation="FAIL_OPEN")
        assert _run(orc.check(**BASE)).approved


class TestBackwardCompat:
    def test_no_args_approves(self):
        orc = RiskOrchestrator()
        assert _run(orc.check(**BASE)).approved

    def test_invalid_sl(self):
        orc = RiskOrchestrator()
        result = _run(
            orc.check(
                symbol="EURUSD",
                direction="BUY",
                entry_price=1.10,
                stop_loss=1.10,
                account_balance=10_000.0,
                user_id="u1",
                signal_id="s1",
            )
        )
        assert not result.approved
        assert result.block_reason == "INVALID_SL"

    def test_lot_zero_blocked(self):
        orc = RiskOrchestrator(lot_sizer=_make_lot_sizer(1.0, lot_size=0.0))
        assert not _run(orc.check(**BASE)).approved

    def test_returns_risk_check_result(self):
        from risk_orchestrator_fix5 import RiskCheckResult

        orc = RiskOrchestrator()
        assert isinstance(_run(orc.check(**BASE)), RiskCheckResult)

    def test_gates_passed_recorded(self):
        orc = RiskOrchestrator(lot_sizer=_make_lot_sizer())
        result = _run(orc.check(**BASE))
        assert "LOT_SIZING" in result.gates_passed

    def test_sl_conversion_in_meta(self):
        orc = RiskOrchestrator()
        result = _run(orc.check(**BASE))
        assert "sl_conversion" in result.metadata
        assert result.metadata["sl_conversion"]["price_distance"] == pytest.approx(0.01, abs=1e-8)


if __name__ == "__main__":
    import pytest as _p

    _p.main([__file__, "-v", "--tb=short"])
