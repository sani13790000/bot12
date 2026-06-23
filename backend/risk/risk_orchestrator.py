"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk
FIX #6 - Fail-Closed Mode (configurable per gate)
FIX #7 - Dead code: removed dead `import asyncio`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

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


def _clamp_risk(value: float) -> float:
    return max(0.0, min(100.0, value))


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"


@dataclass
class RiskCheckResult:
    approved:       bool
    decision:       RiskDecision
    reason:         str            = ""
    lot_size:       float          = 0.0
    risk_percent:   float          = 0.0
    gates_passed:   List[str]       = field(default_factory=list)
    gates_failed:   List[str]       = field(default_factory=list)
    metadata:       Dict[str, Any]  = field(default_factory=dict)


def _normalise_positions(positions) -> list:
    out = []
    for p in (positions or []):
        if isinstance(p, dict):
            try:
                from backend.risk.exposure_control import ExposurePosition  # type: ignore
                out.append(ExposurePosition(
                    symbol=p.get("symbol", ""),
                    direction=p.get("direction", "BUY"),
                    risk_percent=float(p.get("risk_percent", 0.0)),
                    risk_usd=float(p.get("risk_usd", 0.0)),
                ))
            except Exception as e:
                logger.warning("Skipping invalid position dict: %s", e)
        else:
            out.append(p)
    return out


class RiskOrchestrator:
    def __init__(
        self,
        equity_guard=None, daily_limits=None, volatility_filter=None,
        correlation_filter=None, lot_sizer=None, exposure_control=None,
        default_risk_percent: float = 1.0,
        fail_mode_equity:      Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:       Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:  Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation: Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:         Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:    Any = FailMode.FAIL_CLOSED,
    ):
        if default_risk_percent <= 0:
            raise ValueError("default_risk_percent must be > 0")
        self._equity    = equity_guard
        self._daily     = daily_limits
        self._vol       = volatility_filter
        self._corr      = correlation_filter
        self._lot_sizer = lot_sizer
        self._exposure  = exposure_control
        self._default_risk = default_risk_percent
        self._fail_equity  = _coerce(fail_mode_equity)
        self._fail_daily   = _coerce(fail_mode_daily)
        self._fail_vol     = _coerce(fail_mode_volatility)
        self._fail_corr    = _coerce(fail_mode_correlation)
        self._fail_lot     = _coerce(fail_mode_lot)
        self._fail_exp     = _coerce(fail_mode_exposure)

    async def check(
        self,
        user_id: str, symbol: str, direction: str,
        entry_price: float, stop_loss: float, account_balance: float,
        **ctx,
    ) -> RiskCheckResult:
        passed: List[str] = []
        failed: List[str] = []
        meta:   Dict[str, Any] = {}
        price_distance = abs(entry_price - stop_loss)
        arp = _clamp_risk(self._default_risk)

        if self._equity is not None:
            try:
                eq = await self._run_equity_gate(user_id, account_balance, ctx)
                if not eq["can_trade"]:
                    return self._fcr(eq["reason"], passed, failed, meta)
                passed.append("EQUITY")
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
                    return self._fcr(dl["reason"], passed, failed, meta)
                passed.append("DAILY_LIMITS")
            except Exception as e:
                logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_daily, e, exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED:
                    return self._fcr("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)
                passed.append("DAILY_LIMITS_FAIL_OPEN")

        if self._vol is not None:
            try:
                vr = await self._run_vol_gate(symbol, price_distance, entry_price, ctx)
                if not vr["can_trade"]:
                    return self._fcr(vr["reason"], passed, failed, meta)
                meta["lot_multiplier"] = vr.get("lot_multiplier", 1.0)
                passed.append("VOLATILITY")
            except Exception as e:
                logger.critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_vol, e, exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED:
                    return self._fcr("VOLATILITY_GATE_ERROR", passed, failed, meta)
                passed.append("VOLATILITY_FAIL_OPEN")

        if self._corr is not None:
            try:
                cr = await self._run_corr_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._fcr(cr["reason"], passed, failed, meta)
                passed.append("CORRELATION")
            except Exception as e:
                logger.critical("CORR gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_corr, e, exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED:
                    return self._fcr("CORRELATION_GATE_ERROR", passed, failed, meta)
                passed.append("CORRELATION_FAIL_OPEN")

        if self._lot_sizer is not None:
            try:
                pd_in_pips = _price_to_pips(symbol, price_distance)
                override_rp = ctx.get("override_risk_pct")
                lot_res = await self._lot_sizer.calculate(
                    symbol=symbol, account_balance=account_balance,
                    stop_loss_pips=pd_in_pips, override_risk_pct=override_rp,
                )
                arp = _clamp_risk(getattr(lot_res, "risk_percent", None) or self._default_risk)
                meta["lot_sizing"] = {
                    "lot_size": getattr(lot_res, "lot_size", 0.0),
                    "risk_percent": arp,
                    "risk_source": getattr(lot_res, "risk_source", "lot_sizer"),
                }
                passed.append("LOT_SIZING")
            except Exception as e:
                logger.critical("LOT gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_lot, e, exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED:
                    return self._fcr("LOT_SIZING_GATE_ERROR", passed, failed, meta)
                passed.append("LOT_SIZING_FAIL_OPEN")
        else:
            estimated, source = _estimate_risk_pct(
                symbol, price_distance, ctx.get("lot_size", 1.0), account_balance,
            )
            if estimated > 0:
                arp = _clamp_risk(estimated)
                meta["risk_source"] = source
            else:
                arp = _clamp_risk(ctx.get("override_risk_pct") or self._default_risk)
                meta["risk_source"] = "config_fallback"

        if self._exposure is not None:
            try:
                ops = _normalise_positions(ctx.get("open_positions", []))
                er  = await self._run_exposure_gate(symbol, direction, arp, ops)
                if not er["can_trade"]:
                    return self._fcr(er["reason"], passed, failed, meta)
                meta["exposure"] = {"risk_source": meta.get("risk_source", "lot_sizer")}
                passed.append("EXPOSURE")
            except Exception as e:
                logger.critical("EXP gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_exp, e, exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED:
                    return self._fcr("EXPOSURE_GATE_ERROR", passed, failed, meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        return RiskCheckResult(
            approved=True, decision=RiskDecision.APPROVED,
            risk_percent=arp, gates_passed=passed,
            gates_failed=failed, metadata=meta,
        )

    async def _run_equity_gate(self, u, b, ctx):
        if self._equity is None: return {"can_trade": True, "reason": ""}
        res = self._equity.check(u, b)
        if hasattr(res, "__await__"): res = await res
        return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}

    async def _run_daily_gate(self, u, ctx):
        if self._daily is None: return {"can_trade": True, "reason": ""}
        res = self._daily.check(u)
        if hasattr(res, "__await__"): res = await res
        return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}

    async def _run_vol_gate(self, symbol, pd, entry, ctx):
        if self._vol is None: return {"can_trade": True, "reason": "", "lot_multiplier": 1.0}
        res = self._vol.check(symbol, pd, entry)
        if hasattr(res, "__await__"): res = await res
        return {
            "can_trade": getattr(res, "can_trade", True),
            "reason": getattr(res, "reason", ""),
            "lot_multiplier": getattr(res, "lot_multiplier", 1.0),
        }

    async def _run_corr_gate(self, symbol, direction, ctx):
        if self._corr is None: return {"can_trade": True, "reason": ""}
        res = self._corr.check(symbol, direction)
        if hasattr(res, "__await__"): res = await res
        return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}

    async def _run_exposure_gate(self, symbol, direction, arp, ops):
        if self._exposure is None: return {"can_trade": True, "reason": ""}
        res = self._exposure.check(symbol, direction, arp, ops)
        if hasattr(res, "__await__"): res = await res
        return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}


def _fcr(r, p, f, m) -> RiskCheckResult:
    f.append(r)
    return RiskCheckResult(
        approved=False, decision=RiskDecision.BLOCKED,
        reason=r, gates_passed=p, gates_failed=f, metadata=m,
    )

RiskOrchestrator._fcr = staticmethod(_fcr)

_orch_instance: Optional[RiskOrchestrator] = None

def get_risk_orchestrator(**kwargs) -> RiskOrchestrator:
    global _orch_instance
    if _orch_instance is None:
        try:
            from backend.risk.equity_protection  import EquityProtection
            from backend.risk.daily_limits        import DailyLimitsEngine
            from backend.risk.volatility_filter   import VolatilityFilter
            from backend.risk.correlation_filter  import CorrelationFilter
            from backend.risk.lot_sizing          import LotSizer
            from backend.risk.exposure_control    import ExposureControlEngine
            _orch_instance = RiskOrchestrator(
                equity_guard=EquityProtection(), daily_limits=DailyLimitsEngine(),
                volatility_filter=VolatilityFilter(), correlation_filter=CorrelationFilter(),
                lot_sizer=LotSizer(), exposure_control=ExposureControlEngine(), **kwargs,
            )
        except Exception:
            _orch_instance = RiskOrchestrator(**kwargs)
    return _orch_instance
