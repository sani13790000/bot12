"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk
FIX #6 - Fail-Closed Mode (configurable per gate)

FIX-5 changes:
  FIX-5A: default_risk_percent kwarg in __init__
  FIX-5B: _clamp_risk() helper
  FIX-5C: open_positions dict->ExposurePosition normalisation
  FIX-5D: _run_exposure_gate passes clamped actual_risk_pct
  FIX-5E: config_fallback uses default_risk_percent not 1.0

FIX-6 changes:
  FIX-6A: FailMode enum for ALL gates
  FIX-6B: 6 per-gate fail_mode kwargs in __init__
  FIX-6C: EQUITY/DAILY/VOL/LOT gates now respect fail_mode
  FIX-6D: coerce() accepts str or enum
  FIX-6E: every except block logs with exc_info=True
  FIX-6F: FAIL_OPEN: allow + log at CRITICAL level

FIX-7 changes:
  FIX-7A: removed dead 'import asyncio' (0 usages verified by AST)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# FIX-6: canonical FailMode
try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce
except ImportError:
    class FailMode(str, Enum):   # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce(v) -> FailMode:  # type: ignore[misc]
        if isinstance(v, FailMode):
            return v
        return FailMode(str(v).upper())

try:
    from backend.risk._pip_helpers import _price_to_pips
    from backend.risk._pip_helpers import _estimate_risk_pct
except ImportError:
    def _price_to_pips(sym, d): return d * 10_000  # type: ignore
    def _estimate_risk_pct(sym, pd, lot, bal): return (0.0, "none")  # type: ignore

logger = logging.getLogger("risk.orchestrator")


# FIX-5B: clamp helper
def _clamp_risk(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"
    ERROR    = "ERROR"


@dataclass
class RiskCheckResult:
    decision:       RiskDecision
    approved:       bool
    block_reason:   str
    risk_percent:   float
    lot_size:       float
    lot_multiplier: float
    gates_passed:   List[str]       = field(default_factory=list)
    gates_failed:   List[str]       = field(default_factory=list)
    metadata:       Dict[str, Any]  = field(default_factory=dict)


class RiskOrchestrator:
    def __init__(
        self,
        equity_guard=None,
        daily_limits=None,
        volatility_filter=None,
        correlation_filter=None,
        lot_sizer=None,
        exposure_control=None,
        default_risk_percent: float = 1.0,
        # FIX-6B: per-gate fail_mode (default FAIL_CLOSED)
        fail_mode_equity:      Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:       Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:  Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation: Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:         Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:    Any = FailMode.FAIL_CLOSED,
    ):
        if default_risk_percent <= 0:
            raise ValueError(f"default_risk_percent must be > 0, got {default_risk_percent}")
        self._equity_guard       = equity_guard
        self._daily_limits       = daily_limits
        self._vol_filter         = volatility_filter
        self._corr_filter        = correlation_filter
        self._lot_sizer          = lot_sizer
        self._exposure_control   = exposure_control
        self._default_risk       = default_risk_percent
        # FIX-6B: coerce all fail_modes to enum
        self._fail_equity  = _coerce(fail_mode_equity)
        self._fail_daily   = _coerce(fail_mode_daily)
        self._fail_vol     = _coerce(fail_mode_volatility)
        self._fail_corr    = _coerce(fail_mode_correlation)
        self._fail_lot     = _coerce(fail_mode_lot)
        self._fail_exp     = _coerce(fail_mode_exposure)

    def _fcr(self, reason: str, gates_failed=None, meta=None) -> RiskCheckResult:
        return RiskCheckResult(
            decision=RiskDecision.BLOCKED,
            approved=False,
            block_reason=reason,
            risk_percent=0.0,
            lot_size=0.0,
            lot_multiplier=0.0,
            gates_passed=[],
            gates_failed=gates_failed or [reason],
            metadata=meta or {},
        )

    async def check(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        account_balance: float = 10_000.0,
        **ctx,
    ) -> RiskCheckResult:
        passed: List[str] = []
        meta:   Dict[str, Any] = {}

        # ----------------------------------------------------------------
        # EQUITY gate
        # ----------------------------------------------------------------
        if self._equity_guard is not None:
            try:
                er = self._equity_guard.check(account_balance)
                if not er.can_trade:
                    return self._fcr(er.reason or "EQUITY_BLOCKED", meta=meta)
                passed.append("EQUITY")
            except Exception as e:
                logger.critical("EQUITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_equity, e, exc_info=True)
                if self._fail_equity is FailMode.FAIL_CLOSED:
                    return self._fcr("EQUITY_GATE_ERROR", meta=meta)
                passed.append("EQUITY_FAIL_OPEN")

        # ----------------------------------------------------------------
        # DAILY LIMITS gate
        # ----------------------------------------------------------------
        if self._daily_limits is not None:
            try:
                dr = self._daily_limits.check(symbol=symbol, direction=direction)
                if not dr.can_trade:
                    return self._fcr(dr.reason or "DAILY_LIMIT_BLOCKED", meta=meta)
                passed.append("DAILY_LIMITS")
            except Exception as e:
                logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_daily, e, exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED:
                    return self._fcr("DAILY_LIMITS_GATE_ERROR", meta=meta)
                passed.append("DAILY_LIMITS_FAIL_OPEN")

        # ----------------------------------------------------------------
        # VOLATILITY gate
        # ----------------------------------------------------------------
        if self._vol_filter is not None:
            try:
                vr = self._vol_filter.check(
                    current_atr=ctx.get("current_atr", 0.001),
                    atr_history=ctx.get("atr_history"),
                    current_spread=ctx.get("current_spread", 0.0001),
                    avg_spread=ctx.get("avg_spread", 0.0001),
                    symbol=symbol,
                )
                if not vr.can_trade:
                    return self._fcr(vr.reason or "VOLATILITY_BLOCKED", meta=meta)
                passed.append("VOLATILITY")
            except Exception as e:
                logger.critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_vol, e, exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED:
                    return self._fcr("VOLATILITY_GATE_ERROR", meta=meta)
                passed.append("VOLATILITY_FAIL_OPEN")

        # ----------------------------------------------------------------
        # CORRELATION gate
        # ----------------------------------------------------------------
        if self._corr_filter is not None:
            try:
                open_positions = ctx.get("open_positions", [])
                cr = await self._corr_filter.check(
                    symbol=symbol,
                    direction=direction,
                    open_positions=open_positions,
                )
                if not cr.can_trade:
                    return self._fcr(cr.reason or "CORRELATION_BLOCKED", meta=meta)
                passed.append("CORRELATION")
            except Exception as e:
                logger.critical("CORR gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_corr, e, exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED:
                    return self._fcr("CORRELATION_GATE_ERROR", meta=meta)
                passed.append("CORRELATION_FAIL_OPEN")

        # ----------------------------------------------------------------
        # LOT SIZING  (FIX-5: calculate actual risk %)
        # ----------------------------------------------------------------
        price_distance = abs(entry_price - stop_loss)
        lot_size   = 0.01
        lot_mult   = 1.0
        actual_rp  = _clamp_risk(self._default_risk)
        risk_source = "config_fallback"

        if self._lot_sizer is not None:
            try:
                stop_loss_pips = _price_to_pips(symbol, price_distance)
                lot_result = await self._lot_sizer.calculate(
                    symbol=symbol,
                    account_balance=account_balance,
                    stop_loss_pips=stop_loss_pips,
                    override_risk_pct=ctx.get("override_risk_pct"),
                )
                lot_size  = lot_result.lot_size
                lot_mult  = lot_result.lot_multiplier
                if lot_result.actual_risk_pct and lot_result.actual_risk_pct > 0:
                    actual_rp   = _clamp_risk(lot_result.actual_risk_pct)
                    risk_source = "lot_sizer"
                meta["lot_sizing"] = {
                    "lot_size": lot_size,
                    "risk_source": risk_source,
                }
                meta["sl_conversion"] = {
                    "price_distance":  price_distance,
                    "stop_loss_pips":  stop_loss_pips,
                    "symbol":          symbol,
                }
            except Exception as e:
                logger.critical("LOT gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_lot, e, exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED:
                    return self._fcr("LOT_SIZING_GATE_ERROR", meta=meta)
                passed.append("LOT_SIZING_FAIL_OPEN")
        else:
            # FIX-5A: estimate without lot_sizer
            est_rp, est_src = _estimate_risk_pct(
                symbol, price_distance, lot_size, account_balance
            )
            if est_rp > 0:
                actual_rp   = _clamp_risk(est_rp)
                risk_source = f"estimated:{est_src}"
            meta["lot_sizing"] = {"risk_source": risk_source}

        # ----------------------------------------------------------------
        # EXPOSURE gate  (FIX-5D: use real actual_rp)
        # ----------------------------------------------------------------
        if self._exposure_control is not None:
            try:
                open_positions = ctx.get("open_positions", [])
                ops = _normalise_positions(open_positions)
                er2 = self._exposure_control.check(
                    new_symbol=symbol,
                    new_direction=direction,
                    new_risk_percent=actual_rp,
                    open_positions=ops,
                )
                meta["exposure"] = {"risk_source": risk_source}
                if not er2.can_trade:
                    return self._fcr(er2.reason or "EXPOSURE_BLOCKED",
                                     gates_failed=["EXPOSURE"], meta=meta)
                passed.append("EXPOSURE")
            except Exception as e:
                logger.critical("EXP gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_exp, e, exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED:
                    return self._fcr("EXPOSURE_GATE_ERROR", meta=meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        # ----------------------------------------------------------------
        # All gates passed
        # ----------------------------------------------------------------
        return RiskCheckResult(
            decision=RiskDecision.APPROVED,
            approved=True,
            block_reason="",
            risk_percent=actual_rp,
            lot_size=lot_size,
            lot_multiplier=lot_mult,
            gates_passed=passed,
            gates_failed=[],
            metadata=meta,
        )


def _normalise_positions(positions) -> list:
    """FIX-5C: accept List[dict] or List[ExposurePosition]."""
    from dataclasses import fields as dc_fields
    result = []
    for p in (positions or []):
        if isinstance(p, dict):
            try:
                from backend.risk.exposure_control import ExposurePosition
                result.append(ExposurePosition(
                    symbol=p.get("symbol", ""),
                    direction=p.get("direction", "BUY"),
                    risk_percent=float(p.get("risk_percent", 0.0)),
                    risk_usd=float(p.get("risk_usd", 0.0)),
                ))
            except Exception:
                logger.warning("_normalise_positions: skipping invalid dict %r", p)
        else:
            result.append(p)
    return result
