"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk
FIX #6 - Fail-Closed Mode (configurable per gate)
FIX #7 - Dead code removal: removed 'import asyncio' (zero usages)

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
        exposure_control=None,
        lot_sizer=None,
        # FIX-6B: per-gate fail_mode (default FAIL_CLOSED)
        fail_mode_equity:      Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:       Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:  Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation: Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:         Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:    Any = FailMode.FAIL_CLOSED,
        # FIX-5A: replaces hardcoded 1.0
        default_risk_percent:  float = 1.0,
    ) -> None:
        if default_risk_percent <= 0:
            raise ValueError(f"default_risk_percent must be > 0, got {default_risk_percent}")
        self._equity     = equity_guard
        self._daily      = daily_limits
        self._vol        = volatility_filter
        self._corr       = correlation_filter
        self._exposure   = exposure_control
        self._lot_sizer  = lot_sizer
        # FIX-6D: coerce all modes
        self._fail_equity  = _coerce(fail_mode_equity)
        self._fail_daily   = _coerce(fail_mode_daily)
        self._fail_vol     = _coerce(fail_mode_volatility)
        self._fail_corr    = _coerce(fail_mode_correlation)
        self._fail_lot     = _coerce(fail_mode_lot)
        self._fail_exp     = _coerce(fail_mode_exposure)
        self._default_risk = default_risk_percent

    async def check(
        self,
        symbol:          str,
        direction:       str,
        entry_price:     float,
        stop_loss:       float,
        account_balance: float,
        user_id:         str = "",
        signal_id:       str = "",
        override_risk_pct: Optional[float] = None,
        **ctx,
    ) -> RiskCheckResult:
        passed:  List[str]       = []
        failed:  List[str]       = []
        meta:    Dict[str, Any]  = {}

        pd  = abs(entry_price - stop_loss)
        slp = _price_to_pips(symbol, pd)
        meta["sl_conversion"] = {"price_distance": pd, "stop_loss_pips": slp, "symbol": symbol}

        # Gate 1: Equity
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

        # Gate 2: Daily Limits
        if self._daily is not None:
            try:
                dl = await self._run_daily_gate(user_id, ctx)
                if not dl["can_trade"]:
                    return self._blk(dl["reason"], passed, ["DAILY_LIMITS"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("DAILY_LIMITS")
                meta["daily"] = dl
            except Exception as e:
                logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_daily, e, exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED:
                    return self._fcr("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)
                passed.append("DAILY_LIMITS_FAIL_OPEN")

        # Gate 3: Volatility
        lm = 1.0
        if self._vol is not None:
            try:
                vr = await self._run_vol_gate(symbol, pd, entry_price, ctx)
                if not vr["can_trade"]:
                    return self._blk(vr["reason"], passed, ["VOLATILITY"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("VOLATILITY")
                lm = vr.get("lot_multiplier", 1.0)
                meta["volatility"] = vr
            except Exception as e:
                logger.critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_vol, e, exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED:
                    return self._fcr("VOLATILITY_GATE_ERROR", passed, failed, meta)
                passed.append("VOLATILITY_FAIL_OPEN")

        # Gate 4: Correlation
        if self._corr is not None:
            try:
                cr = await self._run_corr_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._blk(cr["reason"], passed, ["CORRELATION"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("CORRELATION")
                meta["correlation"] = cr
            except Exception as e:
                logger.critical("CORR gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_corr, e, exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED:
                    return self._fcr("CORRELATION_GATE_ERROR", passed, failed, meta)
                passed.append("CORRELATION_FAIL_OPEN")

        # Gate 5: Lot Sizing (preliminary)
        pl  = 0.01
        arp = 0.0
        rs  = "unknown"
        if self._lot_sizer is not None:
            try:
                lot_res = await self._lot_sizer.calculate(
                    symbol=symbol,
                    account_balance=account_balance,
                    stop_loss_pips=max(slp, 0.1),
                    lot_multiplier=lm,
                    override_risk_pct=override_risk_pct,
                )
                pl  = getattr(lot_res, "lot_size",     pl)
                arp = _clamp_risk(getattr(lot_res, "risk_percent", self._default_risk))
                rs  = "lot_sizer"
                meta["lot_sizing"] = {"lot_size": pl, "risk_percent": arp, "risk_source": rs}
                if pl <= 0:
                    return self._blk("LOT_SIZING_ZERO", passed, ["LOT_SIZING"] + failed, meta, arp, 0.0, lm)
                passed.append("LOT_SIZING")
            except Exception as e:
                logger.critical("LOT gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_lot, e, exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED:
                    return self._fcr("LOT_SIZING_GATE_ERROR", passed, failed, meta)
                passed.append("LOT_SIZING_FAIL_OPEN")
                arp = _clamp_risk(self._default_risk)
                rs  = "config_fallback"
        else:
            if override_risk_pct and override_risk_pct > 0:
                arp = _clamp_risk(override_risk_pct)
                rs  = "override"
            else:
                est_raw, est_src = _estimate_risk_pct(symbol, pd, pl, account_balance)
                if est_raw > 0:
                    arp = _clamp_risk(est_raw)
                    rs  = f"estimated:{est_src}"
                else:
                    arp = _clamp_risk(self._default_risk)
                    rs  = "config_fallback"

        # Gate 6: Exposure
        if self._exposure is not None:
            try:
                ops = _normalise_positions(ctx.get("open_positions", []))
                er  = await self._run_exposure_gate(symbol, direction, arp, ops)
                if not er["can_trade"]:
                    return self._blk(er["reason"], passed, ["EXPOSURE"] + failed, meta, arp, 0.0, lm)
                er["risk_source"] = rs
                passed.append("EXPOSURE")
                meta["exposure"] = er
            except Exception as e:
                logger.critical("EXP gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_exp, e, exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED:
                    return self._fcr("EXPOSURE_GATE_ERROR", passed, failed, meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        return RiskCheckResult(
            RiskDecision.APPROVED, True, "",
            arp, pl, lm,
            gates_passed=passed, gates_failed=failed, metadata=meta,
        )

    # -- Gate runners --

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

    async def _run_vol_gate(self, symbol, pd, entry, ctx):
        r = self._vol
        if hasattr(r, "check"):
            res = r.check(symbol=symbol, price_distance=pd, entry_price=entry, **ctx)
            if hasattr(res, "__await__"): res = await res
            return {
                "can_trade":      getattr(res, "can_trade",      True),
                "reason":         getattr(res, "reason",         ""),
                "lot_multiplier": getattr(res, "lot_multiplier", 1.0),
            }
        return {"can_trade": True, "reason": "", "lot_multiplier": 1.0}

    async def _run_corr_gate(self, symbol, direction, ctx):
        r = self._corr
        if hasattr(r, "check"):
            res = r.check(symbol=symbol, direction=direction, **ctx)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_exposure_gate(self, symbol, direction, arp, ops):
        r = self._exposure
        if hasattr(r, "check"):
            res = r.check(symbol, direction, arp, ops)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    @staticmethod
    def _fcr(r, p, f, m) -> RiskCheckResult:
        return RiskCheckResult(
            RiskDecision.BLOCKED, False, r, 0.0, 0.0, 0.0,
            gates_passed=p, gates_failed=[r] + f, metadata=m,
        )

    @staticmethod
    def _blk(r, p, f, m, rp, ls, lm) -> RiskCheckResult:
        return RiskCheckResult(
            RiskDecision.BLOCKED, False, r, rp, ls, lm,
            gates_passed=p, gates_failed=f, metadata=m,
        )


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
                    symbol        = str(p.get("symbol", "")),
                    direction     = str(p.get("direction", "BUY")),
                    risk_percent  = float(p.get("risk_percent", 0.0)),
                    risk_usd      = float(p.get("risk_usd",     0.0)),
                )
                result.append(ep)
            except Exception as e:
                logger.warning("Skipping invalid position dict: %s - %s", p, e)
        else:
            result.append(p)
    return result
