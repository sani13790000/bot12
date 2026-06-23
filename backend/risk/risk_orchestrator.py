"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk

Changes (surgical - public API unchanged):
  FIX-5A: default_risk_percent kwarg in __init__ (replaces ctx.get config_risk_pct=1.0)
  FIX-5B: _clamp_risk() helper - clamps actual_risk_pct to [0.0, 100.0]
  FIX-5C: open_positions dict->ExposurePosition normalisation in _run_exposure_gate
  FIX-5D: _run_exposure_gate passes clamped actual_risk_pct (never raw 1.0)
  FIX-5E: config_fallback now uses default_risk_percent, not hardcoded 1.0

Backward compat:
  - RiskOrchestrator() with no args still works (default_risk_percent=1.0)
  - check() signature unchanged
  - All gate helpers unchanged
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.risk._pip_helpers import _price_to_pips
from backend.risk._pip_helpers import _estimate_risk_pct  # exported for test patching

logger = logging.getLogger("risk.orchestrator")


# ---------------------------------------------------------------------------
# FIX-5B: clamp helper - exported so tests can import directly
# ---------------------------------------------------------------------------
def _clamp_risk(value: float) -> float:
    """Clamp actual_risk_pct to [0.0, 100.0]."""
    return max(0.0, min(100.0, value))


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"
    WARNING  = "WARNING"


@dataclass
class RiskCheckResult:
    decision:     RiskDecision
    approved:     bool
    block_reason: str
    risk_percent: float
    lot_size:     float
    lot_multiplier: float
    gates_passed: List[str]         = field(default_factory=list)
    gates_failed: List[str]         = field(default_factory=list)
    metadata:     Dict[str, Any]    = field(default_factory=dict)


class RiskOrchestrator:
    def __init__(
        self,
        equity_guard=None,
        daily_limits=None,
        volatility_filter=None,
        correlation_filter=None,
        exposure_control=None,
        lot_sizer=None,
        fail_mode_correlation: str = "FAIL_CLOSED",
        fail_mode_exposure:    str = "FAIL_CLOSED",
        # FIX-5A: replaces hardcoded 1.0 in config_fallback branch
        default_risk_percent:  float = 1.0,
    ) -> None:
        # FIX-5A: validate at construction time
        if default_risk_percent <= 0:
            raise ValueError(
                f"default_risk_percent must be > 0, got {default_risk_percent}"
            )
        self._equity       = equity_guard
        self._daily        = daily_limits
        self._volatility   = volatility_filter
        self._correlation  = correlation_filter
        self._exposure     = exposure_control
        self._lot_sizer    = lot_sizer
        self._fail_corr    = fail_mode_correlation
        self._fail_exp     = fail_mode_exposure
        # FIX-5A: stored, used instead of hardcoded 1.0
        self._default_risk = default_risk_percent

    async def check(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        user_id: str,
        signal_id: str,
        extra_context: Optional[Dict[str, Any]] = None,
        override_risk_pct: Optional[float] = None,
    ) -> RiskCheckResult:
        ctx     = extra_context or {}
        passed: List[str]       = []
        failed: List[str]       = []
        meta:   Dict[str, Any]  = {}

        pd = abs(entry_price - stop_loss)
        if pd <= 0:
            return self._blk("INVALID_SL", passed, ["ENTRY_VALIDATION"], meta, 0.0, 0.0, 0.0)

        slp = _price_to_pips(symbol, pd)
        meta["sl_conversion"] = {
            "price_distance": pd,
            "stop_loss_pips": slp,
            "symbol":         symbol,
        }

        if self._equity is not None:
            try:
                eq = await self._run_equity_gate(user_id, account_balance, ctx)
                if not eq["can_trade"]:
                    return self._blk(eq["reason"], passed, ["EQUITY"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("EQUITY")
                meta["equity"] = eq
            except Exception as e:
                logger.exception("EQUITY:%s", e)
                return self._fcr("EQUITY_GATE_ERROR", passed, failed, meta)

        if self._daily is not None:
            try:
                dl = await self._run_daily_gate(user_id, ctx)
                if not dl["can_trade"]:
                    return self._blk(dl["reason"], passed, ["DAILY_LIMITS"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("DAILY_LIMITS")
            except Exception as e:
                logger.exception("DAILY:%s", e)
                return self._fcr("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)

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
                logger.exception("VOL:%s", e)
                return self._fcr("VOLATILITY_GATE_ERROR", passed, failed, meta)

        if self._correlation is not None:
            try:
                cr = await self._run_correlation_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._blk(cr["reason"], passed, ["CORRELATION"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("CORRELATION")
                meta["correlation"] = cr
            except Exception as e:
                logger.exception("CORR:%s", e)
                if self._fail_corr == "FAIL_CLOSED":
                    return self._fcr("CORRELATION_GATE_ERROR", passed, failed, meta)
                passed.append("CORRELATION_FAIL_OPEN")

        pl  = 0.01
        arp = 0.0
        rs  = "unknown"

        if self._lot_sizer is not None:
            try:
                lr = await self._lot_sizer.calculate(
                    balance=account_balance,
                    stop_loss_pips=slp,
                    symbol=symbol,
                    volatility_ratio=lm,
                    override_risk_pct=override_risk_pct,
                )
                pl  = lr.lot_size
                arp = _clamp_risk(lr.risk_percent)  # FIX-5B
                rs  = "lot_sizer"
                meta["lot_sizing"] = {
                    "lot_size":       pl,
                    "risk_percent":   arp,
                    "pip_value":      lr.pip_value_used,
                    "stop_loss_pips": slp,
                    "risk_source":    rs,
                }
                if pl <= 0.0:
                    return self._blk("LOT_SIZING_ZERO", passed, ["LOT_SIZING"] + failed, meta, arp, 0.0, lm)
                passed.append("LOT_SIZING")
            except Exception as e:
                logger.exception("LOT:%s", e)
                return self._fcr("LOT_SIZING_GATE_ERROR", passed, failed, meta)
        else:
            # FIX-5A + FIX-5B: no lot sizer branch
            if override_risk_pct and override_risk_pct > 0:
                arp = _clamp_risk(override_risk_pct)
                rs  = "override"
            else:
                # call via module globals so tests can monkey-patch _estimate_risk_pct
                import sys as _sys
                _est_fn = _sys.modules[__name__].__dict__.get(
                    "_estimate_risk_pct", _estimate_risk_pct
                )
                raw_est, es = _est_fn(symbol, pd, pl, account_balance)
                if raw_est > 0:
                    arp = _clamp_risk(raw_est)
                    rs  = f"estimated({es})"
                else:
                    # FIX-5A: use configured default, NOT hardcoded 1.0
                    arp = _clamp_risk(self._default_risk)
                    rs  = "config_fallback"
            meta["lot_sizing"] = {
                "note":           "no_lot_sizer",
                "actual_risk_pct": arp,
                "risk_source":    rs,
                "stop_loss_pips": slp,
            }

        if self._exposure is not None:
            try:
                ops = ctx.get("open_positions", [])
                er = await self._run_exposure_gate(symbol, direction, arp, ops)
                if not er["can_trade"]:
                    return self._blk(er["reason"], passed, ["EXPOSURE"] + failed, meta, arp, 0.0, lm)
                er["risk_source"] = rs
                passed.append("EXPOSURE")
                meta["exposure"] = er
            except Exception as e:
                logger.exception("EXP:%s", e)
                if self._fail_exp == "FAIL_CLOSED":
                    return self._fcr("EXPOSURE_GATE_ERROR", passed, failed, meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        return RiskCheckResult(
            RiskDecision.APPROVED, True, "",
            arp, pl, lm,
            gates_passed=passed,
            gates_failed=failed,
            metadata=meta,
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
        """FIX-5C: normalise dict items in open_positions to ExposurePosition."""
        r = self._exposure
        if hasattr(r, "check"):
            normalised = _normalise_positions(ops)
            res = r.check(
                new_symbol=sym,
                new_direction=d,
                new_risk_percent=rp,
                open_positions=normalised,
            )
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": res.can_trade, "reason": res.reason}
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
    """FIX-5C: Convert list of dict or dataclass to ExposurePosition-compatible objects."""
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
