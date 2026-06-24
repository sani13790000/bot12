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
  FIX-7B: removed dead 'Optional' from typing import (0 usages verified by AST)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

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
class GateResult:
    gate:    str
    passed:  bool
    reason:  str  = ""
    details: Dict = field(default_factory=dict)


@dataclass
class RiskCheckResult:
    approved:      bool
    decision:      RiskDecision
    gates_passed:  list = field(default_factory=list)
    gates_failed:  list = field(default_factory=list)
    metadata:      Dict = field(default_factory=dict)

    # convenience aliases
    @property
    def can_trade(self) -> bool:
        return self.approved

    @property
    def reason(self) -> str:
        if self.gates_failed:
            return self.gates_failed[0] if isinstance(self.gates_failed[0], str) \
                   else str(self.gates_failed[0])
        return "APPROVED"


# ---------------------------------------------------------------------------
# RiskOrchestrator
# ---------------------------------------------------------------------------
class RiskOrchestrator:
    """
    Central risk gate runner.

    All gates default to FAIL_CLOSED: exception => block trade.
    Set fail_mode_X='FAIL_OPEN' to allow trades when gate X crashes.
    """

    def __init__(
        self,
        equity_guard=None,
        daily_loss_guard=None,
        volatility_filter=None,
        correlation_filter=None,
        lot_sizer=None,
        exposure_control=None,
        # FIX-5A: real default risk
        default_risk_percent: float = 1.0,
        # FIX-6B: per-gate fail modes
        fail_mode_equity:       Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:        Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:   Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation:  Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:          Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:     Any = FailMode.FAIL_CLOSED,
    ):
        if default_risk_percent <= 0:
            raise ValueError(f"default_risk_percent must be >0, got {default_risk_percent}")

        self._equity    = equity_guard
        self._daily     = daily_loss_guard
        self._vol       = volatility_filter
        self._corr      = correlation_filter
        self._lot       = lot_sizer
        self._exp       = exposure_control
        self._default_risk = default_risk_percent

        # FIX-6D: coerce strings/enums uniformly
        self._fail_equity = _coerce(fail_mode_equity)
        self._fail_daily  = _coerce(fail_mode_daily)
        self._fail_vol    = _coerce(fail_mode_volatility)
        self._fail_corr   = _coerce(fail_mode_correlation)
        self._fail_lot    = _coerce(fail_mode_lot)
        self._fail_exp    = _coerce(fail_mode_exposure)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _fcr(self, reason: str, passed=None, meta=None) -> RiskCheckResult:
        """Build a blocked RiskCheckResult."""
        return RiskCheckResult(
            approved=False,
            decision=RiskDecision.BLOCKED,
            gates_passed=passed or [],
            gates_failed=[reason],
            metadata=meta or {},
        )

    def _ok(self, passed, meta=None) -> RiskCheckResult:
        return RiskCheckResult(
            approved=True,
            decision=RiskDecision.APPROVED,
            gates_passed=passed,
            gates_failed=[],
            metadata=meta or {},
        )

    # ------------------------------------------------------------------
    # Gate runners
    # ------------------------------------------------------------------
    def _run_equity_gate(self, symbol, passed, meta):
        if self._equity is None:
            return None
        try:
            result = self._equity.check()
            if not result.can_trade:
                return self._fcr("EQUITY_DRAWDOWN_LIMIT", passed, meta)
            passed.append("EQUITY")
        except Exception as e:
            logger.critical("EQUITY gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_equity, e, exc_info=True)
            if self._fail_equity is FailMode.FAIL_CLOSED:
                return self._fcr("EQUITY_GATE_ERROR", passed, meta)
            logger.critical("FAIL_OPEN: EQUITY gate exception swallowed symbol=%s", symbol)
            passed.append("EQUITY_FAIL_OPEN")
        return None

    def _run_daily_gate(self, symbol, passed, meta):
        if self._daily is None:
            return None
        try:
            result = self._daily.check()
            if not result.can_trade:
                return self._fcr("DAILY_LOSS_LIMIT", passed, meta)
            passed.append("DAILY_LOSS")
        except Exception as e:
            logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_daily, e, exc_info=True)
            if self._fail_daily is FailMode.FAIL_CLOSED:
                return self._fcr("DAILY_GATE_ERROR", passed, meta)
            logger.critical("FAIL_OPEN: DAILY gate exception swallowed symbol=%s", symbol)
            passed.append("DAILY_FAIL_OPEN")
        return None

    def _run_volatility_gate(self, symbol, passed, meta, ctx):
        if self._vol is None:
            return None
        try:
            atr         = ctx.get("atr", 0.0)
            atr_history = ctx.get("atr_history", [])
            spread      = ctx.get("spread", 0.0)
            avg_spread  = ctx.get("avg_spread", 0.0)
            result = self._vol.check(atr, atr_history, spread, avg_spread, symbol)
            if not result.can_trade:
                return self._fcr(f"VOLATILITY:{result.reason}", passed, meta)
            passed.append("VOLATILITY")
        except Exception as e:
            logger.critical("VOL gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_vol, e, exc_info=True)
            if self._fail_vol is FailMode.FAIL_CLOSED:
                return self._fcr("VOL_GATE_ERROR", passed, meta)
            logger.critical("FAIL_OPEN: VOL gate exception swallowed symbol=%s", symbol)
            passed.append("VOL_FAIL_OPEN")
        return None

    async def _run_correlation_gate(self, symbol, direction, passed, meta, open_trades):
        if self._corr is None:
            return None
        try:
            result = await self._corr.check(symbol, direction, open_trades)
            if not result.can_trade:
                return self._fcr(f"CORRELATION:{result.reason}", passed, meta)
            passed.append("CORRELATION")
        except Exception as e:
            logger.critical("CORR gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_corr, e, exc_info=True)
            if self._fail_corr is FailMode.FAIL_CLOSED:
                return self._fcr("CORR_GATE_ERROR", passed, meta)
            logger.critical("FAIL_OPEN: CORR gate exception swallowed symbol=%s", symbol)
            passed.append("CORR_FAIL_OPEN")
        return None

    async def _run_lot_gate(self, symbol, direction, passed, meta, ctx, balance):
        """Returns (block_result_or_None, actual_risk_pct)."""
        if self._lot is None:
            return None, _clamp_risk(self._default_risk)

        entry_price = ctx.get("entry_price", 0.0)
        stop_loss   = ctx.get("stop_loss",   0.0)
        price_distance = abs(entry_price - stop_loss) if (entry_price and stop_loss) else 0.0
        stop_loss_pips = _price_to_pips(symbol, price_distance)

        try:
            lot_result = await self._lot.calculate(
                symbol=symbol,
                balance=balance,
                stop_loss_pips=stop_loss_pips,
            )
            passed.append("LOT_SIZING")
            meta["lot_sizing"] = {
                "lot_size":     lot_result.lot_size,
                "risk_percent": lot_result.risk_percent,
                "risk_usd":     lot_result.risk_usd,
                "risk_source":  "lot_sizer",
                "sl_pips":      stop_loss_pips,
            }
            arp = _clamp_risk(lot_result.risk_percent)
            return None, arp
        except Exception as e:
            logger.critical("LOT gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_lot, e, exc_info=True)
            if self._fail_lot is FailMode.FAIL_CLOSED:
                return self._fcr("LOT_GATE_ERROR", passed, meta), 0.0
            logger.critical("FAIL_OPEN: LOT gate exception swallowed symbol=%s", symbol)
            passed.append("LOT_FAIL_OPEN")
            arp = _clamp_risk(self._default_risk)
            return None, arp

    async def _run_exposure_gate(self, symbol, direction, arp, ops, passed, meta, balance):
        if self._exp is None:
            return None
        try:
            result = self._exp.check(
                new_symbol=symbol,
                new_direction=direction,
                new_risk_percent=arp,
                open_positions=ops,
                account_balance=balance,
            )
            if not result.can_trade:
                return self._fcr(f"EXPOSURE:{result.reason}", passed, meta)
            passed.append("EXPOSURE")
            meta["exposure"] = {
                "projected_total": result.projected_total_risk,
                "risk_source":     meta.get("lot_sizing", {}).get("risk_source", "default"),
            }
        except Exception as e:
            logger.critical("EXPOSURE gate exception symbol=%s fail_mode=%s: %s",
                            symbol, self._fail_exp, e, exc_info=True)
            if self._fail_exp is FailMode.FAIL_CLOSED:
                return self._fcr("EXPOSURE_GATE_ERROR", passed, meta)
            logger.critical("FAIL_OPEN: EXPOSURE gate exception swallowed symbol=%s", symbol)
            passed.append("EXPOSURE_FAIL_OPEN")
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def check(self, symbol: str, direction: str, **ctx) -> RiskCheckResult:
        """
        Run all risk gates sequentially.
        Gates are skipped if the corresponding engine is None.
        """
        balance     = float(ctx.get("balance", 10_000.0))
        open_trades = ctx.get("open_trades", [])
        open_positions = _normalise_positions(ctx.get("open_positions", []))
        passed: list = []
        meta:   Dict = {}

        # 1. Equity gate (sync)
        r = self._run_equity_gate(symbol, passed, meta)
        if r: return r

        # 2. Daily loss gate (sync)
        r = self._run_daily_gate(symbol, passed, meta)
        if r: return r

        # 3. Volatility gate (sync)
        r = self._run_volatility_gate(symbol, passed, meta, ctx)
        if r: return r

        # 4. Correlation gate (async)
        r = await self._run_correlation_gate(symbol, direction, passed, meta, open_trades)
        if r: return r

        # 5. Lot sizing gate (async) — determines actual_risk_pct
        r, arp = await self._run_lot_gate(symbol, direction, passed, meta, ctx, balance)
        if r: return r

        # 6. Exposure gate (async) — uses real arp
        r = await self._run_exposure_gate(symbol, direction, arp, open_positions, passed, meta, balance)
        if r: return r

        meta["actual_risk_pct"] = arp
        return self._ok(passed, meta)


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
                logger.warning("_normalise_positions: skipping invalid dict %s", p)
        else:
            result.append(p)
    return result
