"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk
FIX #6 - Fail-Closed Mode (configurable per gate)

FIX-5 changes:
  FIX-5A: default_risk_percent kwarg in __init__
  FIX-5B: _clamp_risk() helper
  FIX-5C: open_positions dict normalisation
  FIX-5D: exposure gate uses real risk_pct
  FIX-5E: config_fallback uses default_risk_percent

FIX-6 changes (this commit):
  FIX-6A: FailMode enum for ALL gates
  FIX-6B: per-gate fail_mode kwargs added
  FIX-6C: EQUITY/DAILY/VOL/LOT gates now configurable
  FIX-6D: every except logs exc_info=True at CRITICAL
  FIX-6E: _coerce() accepts str or FailMode
  FIX-6F: FAIL_OPEN appends GATE_FAIL_OPEN + logs CRITICAL

Backward compat:
  - RiskOrchestrator() no args still works
  - check() signature unchanged
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.risk._pip_helpers import _price_to_pips
from backend.risk._pip_helpers import _estimate_risk_pct

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce
except ImportError:
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce(v) -> FailMode:  # type: ignore[misc]
        if isinstance(v, FailMode):
            return v
        return FailMode(str(v).upper())

logger = logging.getLogger("risk.orchestrator")


def _clamp_risk(value: float) -> float:
    return max(0.0, min(100.0, value))


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"
    WARNING  = "WARNING"


@dataclass
class RiskCheckResult:
    decision:       RiskDecision
    approved:       bool
    block_reason:   str
    risk_percent:   float
    lot_size:       float
    lot_multiplier: float
    gates_passed:   List[str]      = field(default_factory=list)
    gates_failed:   List[str]      = field(default_factory=list)
    metadata:       Dict[str, Any] = field(default_factory=dict)


class RiskOrchestrator:
    def __init__(
        self,
        equity_guard=None,
        daily_limits=None,
        volatility_filter=None,
        correlation_filter=None,
        exposure_control=None,
        lot_sizer=None,
        default_risk_percent: float = 1.0,
        fail_mode_equity:      Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:       Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:  Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation: Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:         Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:    Any = FailMode.FAIL_CLOSED,
    ) -> None:
        if default_risk_percent <= 0:
            raise ValueError(f"default_risk_percent must be > 0, got {default_risk_percent}")
        self._equity      = equity_guard
        self._daily       = daily_limits
        self._volatility  = volatility_filter
        self._correlation = correlation_filter
        self._exposure    = exposure_control
        self._lot_sizer   = lot_sizer
        self._default_risk = default_risk_percent
        self._fail_equity  = _coerce(fail_mode_equity)
        self._fail_daily   = _coerce(fail_mode_daily)
        self._fail_vol     = _coerce(fail_mode_volatility)
        self._fail_corr    = _coerce(fail_mode_correlation)
        self._fail_lot     = _coerce(fail_mode_lot)
        self._fail_exp     = _coerce(fail_mode_exposure)

    async def check(
        self,
        symbol:          str,
        direction:       str,
        entry_price:     float,
        stop_loss:       float,
        account_balance: float,
        user_id:         str,
        signal_id:       str,
        extra_context:   Optional[Dict[str, Any]] = None,
        override_risk_pct: Optional[float] = None,
    ) -> RiskCheckResult:
        ctx    = extra_context or {}
        passed: List[str]      = []
        failed: List[str]      = []
        meta:   Dict[str, Any] = {}

        pd = abs(entry_price - stop_loss)
        if pd <= 0:
            return self._blk("INVALID_SL", passed, ["ENTRY_VALIDATION"], meta, 0.0, 0.0, 0.0)

        slp = _price_to_pips(symbol, pd)
        meta["sl_conversion"] = {"price_distance": pd, "stop_loss_pips": slp, "symbol": symbol}

        if self._equity is not None:
            try:
                eq = await self._run_equity_gate(user_id, account_balance, ctx)
                if not eq["can_trade"]:
                    return self._blk(eq["reason"], passed, ["EQUITY"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("EQUITY")
                meta["equity"] = eq
            except Exception as e:
                logger.critical("EQUITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_equity, e, exc_info=True)
                if self._fail_equity is FailMode.FAIL_CLOSED:
                    return self._fcr("EQUITY_GATE_ERROR", passed, failed, meta)
                passed.append("EQUITY_FAIL_OPEN")

        if self._daily is not None:
            try:
                dl = await self._run_daily_gate(user_id, ctx)
                if not dl["can_trade"]:
                    return self._blk(dl["reason"], passed, ["DAILY_LIMITS"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("DAILY_LIMITS")
            except Exception as e:
                logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_daily, e, exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED:
                    return self._fcr("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)
                passed.append("DAILY_FAIL_OPEN")

        lm = 1.0
        if self._volatility is not None:
            try:
                vr = await self._run_volatility_gate(symbol, ctx)
                if not vr["can_trade"]:
                    return self._blk(vr["reason"], passed, ["VOLATILITY"] + failed, meta, 0.0, 0.0, 0.0)
                lm = vr.get("lot_multiplier", 1.0)
                passed.append("VOLATILITY")
                meta["volatility"] = vr
            except Exception as e:
                logger.critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_vol, e, exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED:
                    return self._fcr("VOLATILITY_GATE_ERROR", passed, failed, meta)
                passed.append("VOLATILITY_FAIL_OPEN")

        if self._correlation is not None:
            try:
                cr = await self._run_correlation_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._blk(cr["reason"], passed, ["CORRELATION"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("CORRELATION")
                meta["correlation"] = cr
            except Exception as e:
                logger.critical("CORRELATION gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_corr, e, exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED:
                    return self._fcr("CORRELATION_GATE_ERROR", passed, failed, meta)
                passed.append("CORRELATION_FAIL_OPEN")

        pl  = 0.01
        arp = 0.0
        rs  = "unknown"

        if self._lot_sizer is not None:
            try:
                lr = await self._lot_sizer.calculate(
                    balance=account_balance, stop_loss_pips=slp, symbol=symbol,
                    volatility_ratio=lm, override_risk_pct=override_risk_pct,
                )
                pl  = lr.lot_size
                arp = _clamp_risk(lr.risk_percent)
                rs  = "lot_sizer"
                meta["lot_sizing"] = {
                    "lot_size": pl, "risk_percent": arp,
                    "pip_value": lr.pip_value_used,
                    "stop_loss_pips": slp, "risk_source": rs,
                }
                if pl <= 0.0:
                    return self._blk("LOT_SIZING_ZERO", passed, ["LOT_SIZING"] + failed, meta, arp, 0.0, lm)
                passed.append("LOT_SIZING")
            except Exception as e:
                logger.critical("LOT_SIZING gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_lot, e, exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED:
                    return self._fcr("LOT_SIZING_GATE_ERROR", passed, failed, meta)
                arp = _clamp_risk(self._default_risk)
                rs  = "config_fallback_after_error"
                passed.append("LOT_SIZING_FAIL_OPEN")
        else:
            if override_risk_pct and override_risk_pct > 0:
                arp = _clamp_risk(override_risk_pct)
                rs  = "override"
            else:
                import sys as _sys
                _est_fn = _sys.modules[__name__].__dict__.get("_estimate_risk_pct", _estimate_risk_pct)
                raw_est, es = _est_fn(symbol, pd, pl, account_balance)
                if raw_est > 0:
                    arp = _clamp_risk(raw_est)
                    rs  = f"estimated({es})"
                else:
                    arp = _clamp_risk(self._default_risk)
                    rs  = "config_fallback"
            meta["lot_sizing"] = {
                "note": "no_lot_sizer", "actual_risk_pct": arp,
                "risk_source": rs, "stop_loss_pips": slp,
            }

        if self._exposure is not None:
            try:
                ops = ctx.get("open_positions", [])
                er  = await self._run_exposure_gate(symbol, direction, arp, ops)
                if not er["can_trade"]:
                    return self._blk(er["reason"], passed, ["EXPOSURE"] + failed, meta, arp, 0.0, lm)
                er["risk_source"] = rs
                passed.append("EXPOSURE")
                meta["exposure"] = er
            except Exception as e:
                logger.critical("EXPOSURE gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_exp, e, exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED:
                    return self._fcr("EXPOSURE_GATE_ERROR", passed, failed, meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        return RiskCheckResult(
            RiskDecision.APPROVED, True, "", arp, pl, lm,
            gates_passed=passed, gates_failed=failed, metadata=meta,
        )

    async def _run_equity_gate(self, u, b, ctx):
        r = self._equity
        if hasattr(r, "check"):
            res = r.check(user_id=u, account_balance=b, **ctx)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_daily_gate(self, u, ctx):
        r = self._daily
        if hasattr(r, "check"):
            res = r.check(user_id=u)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_volatility_gate(self, sym, ctx):
        r = self._volatility
        if hasattr(r, "check"):
            res = r.check(symbol=sym, current_atr=ctx.get("current_atr", 0.0))
            if hasattr(res, "__await__"): res = await res
            return {
                "can_trade": getattr(res, "can_trade", True),
                "reason": getattr(res, "reason", ""),
                "lot_multiplier": getattr(res, "lot_multiplier", 1.0),
            }
        return {"can_trade": True, "reason": "", "lot_multiplier": 1.0}

    async def _run_correlation_gate(self, sym, d, ctx):
        r = self._correlation
        if hasattr(r, "check"):
            res = r.check(symbol=sym, direction=d)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_exposure_gate(self, sym, d, rp, ops):
        r = self._exposure
        if hasattr(r, "check"):
            normalised = _normalise_positions(ops)
            res = r.check(new_symbol=sym, new_direction=d, new_risk_percent=rp, open_positions=normalised)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": res.can_trade, "reason": res.reason}
        return {"can_trade": True, "reason": ""}

    @staticmethod
    def _fcr(r, p, f, m) -> RiskCheckResult:
        return RiskCheckResult(RiskDecision.BLOCKED, False, r, 0.0, 0.0, 0.0,
                               gates_passed=p, gates_failed=[r] + f, metadata=m)

    @staticmethod
    def _blk(r, p, f, m, rp, ls, lm) -> RiskCheckResult:
        return RiskCheckResult(RiskDecision.BLOCKED, False, r, rp, ls, lm,
                               gates_passed=p, gates_failed=f, metadata=m)


def _normalise_positions(positions) -> list:
    try:
        from backend.risk.exposure_control import ExposurePosition
    except Exception:
        from types import SimpleNamespace as ExposurePosition  # type: ignore
    result = []
    for p in positions:
        if isinstance(p, dict):
            try:
                ep = ExposurePosition(
                    symbol=p.get("symbol", ""),
                    direction=p.get("direction", "BUY"),
                    risk_percent=float(p.get("risk_percent", 0.0)),
                    risk_usd=float(p.get("risk_usd", 0.0)),
                )
                result.append(ep)
            except Exception as e:
                logger.warning("Skipping invalid position dict: %s - %s", p, e)
        else:
            result.append(p)
    return result
