"""
backend/risk/risk_orchestrator.py
FIX #5: ExposureControl uses ACTUAL risk_percent (not hardcoded 1.0)
FIX #6: Fail-closed on Correlation and Exposure gates
FIX #7: Removed dead singleton remnant + unused imports

Gate order unchanged: Equity->DailyLimits->Volatility->Correlation->LotSizing->Exposure
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("risk.orchestrator")


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"
    REDUCED  = "REDUCED"


@dataclass
class RiskCheckResult:
    decision:       RiskDecision
    approved:       bool
    block_reason:   str
    risk_percent:   float
    lot_size:       float
    lot_multiplier: float
    gates_passed:   List[str] = field(default_factory=list)
    gates_failed:   List[str] = field(default_factory=list)
    metadata:       Dict[str, Any] = field(default_factory=dict)


class RiskOrchestrator:
    """
    FIX #5: Gate 5 (ExposureControl) receives ACTUAL risk_percent from LotSizer.
    FIX #6: Correlation and Exposure gates are fail-closed by default.
    FIX #7: Removed dead _singleton_init() remnant.
    """

    def __init__(
        self,
        equity_guard=None, daily_limits=None, volatility_filter=None,
        correlation_filter=None, exposure_control=None, lot_sizer=None,
        fail_mode_correlation: str = "FAIL_CLOSED",
        fail_mode_exposure:    str = "FAIL_CLOSED",
    ) -> None:
        self._equity      = equity_guard
        self._daily       = daily_limits
        self._volatility  = volatility_filter
        self._correlation = correlation_filter
        self._exposure    = exposure_control
        self._lot_sizer   = lot_sizer
        self._fail_corr   = fail_mode_correlation
        self._fail_exp    = fail_mode_exposure

    async def check(
        self, symbol: str, direction: str, entry_price: float, stop_loss: float,
        account_balance: float, user_id: str, signal_id: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> RiskCheckResult:
        ctx = extra_context or {}
        passed: List[str] = []
        failed: List[str] = []
        meta:   Dict[str, Any] = {}

        pip_distance = abs(entry_price - stop_loss)
        if pip_distance <= 0:
            return RiskCheckResult(decision=RiskDecision.BLOCKED, approved=False,
                block_reason="INVALID_SL:pip_distance<=0", risk_percent=0.0,
                lot_size=0.0, lot_multiplier=0.0, gates_failed=["ENTRY_VALIDATION"])

        # Gate 1: Equity
        if self._equity is not None:
            try:
                eq = await self._run_equity_gate(user_id, account_balance, ctx)
                if not eq["can_trade"]:
                    return self._blocked(eq["reason"], passed, ["EQUITY"]+failed, meta, 0.0, 0.0, 0.0)
                passed.append("EQUITY"); meta["equity"] = eq
            except Exception as exc:
                logger.exception("Gate EQUITY error: %s", exc)
                return self._fail_closed_result("EQUITY_GATE_ERROR", passed, failed, meta)

        # Gate 2: Daily Limits
        if self._daily is not None:
            try:
                dl = await self._run_daily_gate(user_id, ctx)
                if not dl["can_trade"]:
                    return self._blocked(dl["reason"], passed, ["DAILY_LIMITS"]+failed, meta, 0.0, 0.0, 0.0)
                passed.append("DAILY_LIMITS")
            except Exception as exc:
                logger.exception("Gate DAILY_LIMITS error: %s", exc)
                return self._fail_closed_result("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)

        # Gate 3: Volatility
        lot_multiplier = 1.0
        if self._volatility is not None:
            try:
                vr = await self._run_volatility_gate(symbol, ctx)
                if not vr["can_trade"]:
                    return self._blocked(vr["reason"], passed, ["VOLATILITY"]+failed, meta, 0.0, 0.0, 0.0)
                lot_multiplier = vr.get("lot_multiplier", 1.0)
                passed.append("VOLATILITY"); meta["volatility"] = vr
            except Exception as exc:
                logger.exception("Gate VOLATILITY error: %s", exc)
                return self._fail_closed_result("VOLATILITY_GATE_ERROR", passed, failed, meta)

        # Gate 4: Correlation
        if self._correlation is not None:
            try:
                cr = await self._run_correlation_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._blocked(cr["reason"], passed, ["CORRELATION"]+failed, meta, 0.0, 0.0, 0.0)
                passed.append("CORRELATION"); meta["correlation"] = cr
            except Exception as exc:
                logger.exception("Gate CORRELATION error: %s", exc)
                if self._fail_corr == "FAIL_CLOSED":
                    return self._fail_closed_result("CORRELATION_GATE_ERROR", passed, failed, meta)
                logger.critical("CORRELATION FAIL_OPEN — trade continues for %s", symbol)
                passed.append("CORRELATION_FAIL_OPEN")

        # Gate 5: Lot Sizing (MUST run before Exposure — FIX #5)
        preliminary_lot = 0.01
        actual_risk_pct = 0.0
        if self._lot_sizer is not None:
            try:
                lot_result = await self._lot_sizer.calculate(
                    balance=account_balance, stop_loss_pips=pip_distance,
                    symbol=symbol, volatility_ratio=lot_multiplier,
                )
                preliminary_lot = lot_result.lot_size
                actual_risk_pct = lot_result.risk_percent  # FIX #5: real risk, not 1.0
                meta["lot_sizing"] = {"lot_size": preliminary_lot, "risk_percent": actual_risk_pct,
                                      "pip_value": lot_result.pip_value_used, "source": lot_result.source}
                if preliminary_lot <= 0.0:
                    return self._blocked("LOT_SIZING_ZERO", passed, ["LOT_SIZING"]+failed, meta,
                                        actual_risk_pct, 0.0, lot_multiplier)
                passed.append("LOT_SIZING")
            except Exception as exc:
                logger.exception("Gate LOT_SIZING error: %s", exc)
                return self._fail_closed_result("LOT_SIZING_GATE_ERROR", passed, failed, meta)
        else:
            actual_risk_pct = 1.0
            meta["lot_sizing"] = {"note": "no_lot_sizer_injected"}

        # Gate 6: Exposure — FIX #5: uses actual_risk_pct (NOT hardcoded 1.0)
        if self._exposure is not None:
            try:
                open_positions = ctx.get("open_positions", [])
                er = await self._run_exposure_gate(symbol, direction, actual_risk_pct, open_positions)
                if not er["can_trade"]:
                    return self._blocked(er["reason"], passed, ["EXPOSURE"]+failed, meta,
                                        actual_risk_pct, 0.0, lot_multiplier)
                passed.append("EXPOSURE"); meta["exposure"] = er
            except Exception as exc:
                logger.exception("Gate EXPOSURE error: %s", exc)
                if self._fail_exp == "FAIL_CLOSED":
                    return self._fail_closed_result("EXPOSURE_GATE_ERROR", passed, failed, meta)
                logger.critical("EXPOSURE FAIL_OPEN — trade continues for %s", symbol)
                passed.append("EXPOSURE_FAIL_OPEN")

        logger.info("risk_orchestrator: APPROVED %s %s lot=%.2f risk=%.3f%% gates=%s",
                    symbol, direction, preliminary_lot, actual_risk_pct, passed)
        return RiskCheckResult(decision=RiskDecision.APPROVED, approved=True, block_reason="",
            risk_percent=actual_risk_pct, lot_size=preliminary_lot, lot_multiplier=lot_multiplier,
            gates_passed=passed, gates_failed=failed, metadata=meta)

    async def _run_equity_gate(self, user_id, balance, ctx) -> dict:
        r = self._equity
        if hasattr(r, "check"):
            result = r.check(balance=balance, user_id=user_id)
            if hasattr(result, "__await__"): result = await result
            return {"can_trade": result.can_trade, "reason": getattr(result, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_daily_gate(self, user_id, ctx) -> dict:
        r = self._daily
        if hasattr(r, "check"):
            result = r.check(user_id=user_id)
            if hasattr(result, "__await__"): result = await result
            return {"can_trade": result.can_trade, "reason": getattr(result, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_volatility_gate(self, symbol, ctx) -> dict:
        r = self._volatility
        if hasattr(r, "check"):
            atr_hist = ctx.get("atr_history", [1.0] * 14)
            cur_atr  = ctx.get("current_atr", 1.0)
            cur_spr  = ctx.get("current_spread", 0.0)
            avg_spr  = ctx.get("avg_spread", 0.0)
            result   = r.check(cur_atr, atr_hist, cur_spr, avg_spr, symbol)
            if hasattr(result, "__await__"): result = await result
            return {"can_trade": result.can_trade, "reason": result.reason,
                    "lot_multiplier": result.lot_multiplier, "level": result.level}
        return {"can_trade": True, "reason": "", "lot_multiplier": 1.0}

    async def _run_correlation_gate(self, symbol, direction, ctx) -> dict:
        r = self._correlation
        if hasattr(r, "check"):
            open_pos = ctx.get("open_positions", [])
            result   = r.check(symbol=symbol, direction=direction, open_positions=open_pos)
            if hasattr(result, "__await__"): result = await result
            return {"can_trade": result.can_trade, "reason": getattr(result, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_exposure_gate(self, symbol, direction, risk_percent, open_positions) -> dict:
        r = self._exposure
        if hasattr(r, "check"):
            result = r.check(new_symbol=symbol, new_direction=direction,
                             new_risk_percent=risk_percent, open_positions=open_positions)
            if hasattr(result, "__await__"): result = await result
            return {"can_trade": result.can_trade, "reason": result.reason}
        return {"can_trade": True, "reason": ""}

    @staticmethod
    def _fail_closed_result(reason, passed, failed, meta) -> RiskCheckResult:
        return RiskCheckResult(decision=RiskDecision.BLOCKED, approved=False, block_reason=reason,
            risk_percent=0.0, lot_size=0.0, lot_multiplier=0.0,
            gates_passed=passed, gates_failed=[reason]+failed, metadata=meta)

    @staticmethod
    def _blocked(reason, passed, failed, meta, risk_pct, lot_size, lot_mult) -> RiskCheckResult:
        return RiskCheckResult(decision=RiskDecision.BLOCKED, approved=False, block_reason=reason,
            risk_percent=risk_pct, lot_size=lot_size, lot_multiplier=lot_mult,
            gates_passed=passed, gates_failed=failed, metadata=meta)
