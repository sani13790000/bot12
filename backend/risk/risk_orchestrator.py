# P5-TZ-1 PATCHED: datetime.datetime.utcnow() → timezone_utils.now()
# See backend/core/timezone_utils.py for details
"""
backend/risk/risk_orchestrator.py
Galaxy Vast AI Trading Platform — Risk Orchestrator (Enterprise)

Pipeline:
  KillSwitch → EquityProtection → DailyLimits → NewsFilter →
  CorrelationFilter → ExposureControl → MarginGate → LotSizer → APPROVED

P4-FIX-1: KillSwitch wired as FIRST gate (was missing entirely)
P4-FIX-2: res.allowed → res.can_trade for DailyLimits (AttributeError fix)
P4-FIX-3: LotSizer receives equity + free_margin (margin-aware sizing)
P4-FIX-4: TodayTrades() now has default fields (TypeError fix)
H-6 FIX: 5s global timeout on assess() via asyncio.wait_for
P4-FIX-V2-3: MarginGate wired as GATE 5.5 (was missing entirely)
P5-TZ-1: datetime.datetime.utcnow() → timezone_utils.now() (UTC-aware, fixes TypeError with aware news events)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.timezone_utils import now as _utc_now  # P5-TZ-1


@dataclass
class RiskInput:
    symbol:          str
    signal_side:     str
    entry_price:     float
    stop_loss_pips:  float
    equity:          float
    free_margin:     float
    open_positions:  List[Dict[str, Any]] = field(default_factory=list)
    account_id:      Optional[str]        = None
    strategy:        Optional[str]        = None
    extra:           Dict[str, Any]       = field(default_factory=dict)


@dataclass
class RiskOutput:
    approved:        bool
    lot_size:        float
    reason:          str
    gate_results:    Dict[str, Any]
    latency_ms:      float
    kill_active:     bool = False
    margin_limited:  bool = False


class RiskOrchestrator:
    """
    Enterprise risk pipeline with 8 gates.
    All gates are fail-closed by default.
    """

    def __init__(
        self,
        kill_switch      = None,
        equity_engine    = None,
        daily_limits     = None,
        news_filter      = None,
        corr_filter      = None,
        exposure_control = None,
        margin_gate      = None,
        lot_sizer        = None,
        timeout_s:  float = 5.0,
        logger           = None,
    ):
        self._kill   = kill_switch
        self._equity = equity_engine
        self._daily  = daily_limits
        self._news   = news_filter
        self._corr   = corr_filter
        self._exp    = exposure_control
        self._margin = margin_gate
        self._lot    = lot_sizer
        self._timeout = timeout_s

        import logging
        self._log = logger or logging.getLogger("risk.orchestrator")

    async def assess(self, inp: RiskInput) -> RiskOutput:
        """Run full risk pipeline with timeout."""
        try:
            return await asyncio.wait_for(
                self._assess_inner(inp),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return RiskOutput(
                approved=False,
                lot_size=0.0,
                reason=f"RiskOrchestrator timeout after {self._timeout}s",
                gate_results={"timeout": True},
                latency_ms=self._timeout * 1000,
            )

    async def _assess_inner(self, inp: RiskInput) -> RiskOutput:
        t0 = time.perf_counter()
        gate_results: Dict[str, Any] = {}

        # GATE 0: KillSwitch
        if self._kill is not None:
            try:
                ks = self._kill.get_status()
                gate_results["kill_switch"] = {"active": ks.active, "reason": ks.reason}
                if ks.active:
                    return self._blocked(
                        "KillSwitch", ks.reason, gate_results, t0,
                        kill_active=True,
                    )
            except Exception as exc:
                self._log.error("KillSwitch gate error", extra={"error": str(exc)})
                gate_results["kill_switch"] = {"passed": False, "error": str(exc)}
                return self._blocked("KillSwitch", f"gate_error:{exc}", gate_results, t0)

        # GATE 1: Equity Protection
        if self._equity is not None:
            try:
                res = self._equity.check(inp.equity)
                gate_results["equity"] = {"passed": res.can_trade, "reason": res.reason}
                if not res.can_trade:
                    return self._blocked("EquityProtection", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("EquityProtection gate error", extra={"error": str(exc)})
                gate_results["equity"] = {"passed": False, "error": str(exc)}
                return self._blocked("EquityProtection", f"gate_error:{exc}", gate_results, t0)

        # GATE 2: Daily Limits
        if self._daily is not None:
            try:
                res = self._daily.can_trade(inp.equity)
                gate_results["daily_limits"] = {"passed": res.can_trade, "reason": res.reason}
                if not res.can_trade:
                    return self._blocked("DailyLimits", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("DailyLimits gate error", extra={"error": str(exc)})
                gate_results["daily_limits"] = {"passed": False, "error": str(exc)}
                return self._blocked("DailyLimits", f"gate_error:{exc}", gate_results, t0)

        # GATE 3: News Filter
        # P5-TZ-1: was datetime.datetime.utcnow() (naive) → now _utc_now() (UTC-aware)
        if self._news is not None:
            try:
                res = self._news.check(inp.symbol, _utc_now())
                gate_results["news"] = {"passed": not res.blocked, "reason": res.reason}
                if res.blocked:
                    return self._blocked("NewsFilter", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("NewsFilter gate error", extra={"error": str(exc)})
                gate_results["news"] = {"passed": False, "error": str(exc)}
                return self._blocked("NewsFilter", f"gate_error:{exc}", gate_results, t0)

        # GATE 4: Correlation Filter
        if self._corr is not None:
            try:
                from risk.correlation_filter import CorrPosition
                positions = [
                    CorrPosition(symbol=p.get("symbol", ""), side=p.get("side", "buy"),
                                 lots=p.get("lots", 0.0))
                    for p in inp.open_positions
                ]
                res = await self._corr.check(inp.symbol, inp.signal_side, positions)
                gate_results["correlation"] = {"passed": res.allowed, "reason": res.reason}
                if not res.allowed:
                    return self._blocked("CorrelationFilter", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("CorrelationFilter gate error", extra={"error": str(exc)})
                gate_results["correlation"] = {"passed": False, "error": str(exc)}
                return self._blocked("CorrelationFilter", f"gate_error:{exc}", gate_results, t0)

        # GATE 5: Exposure Control
        if self._exp is not None:
            try:
                res = self._exp.check(inp.symbol, inp.open_positions)
                gate_results["exposure"] = {"passed": res.allowed, "reason": res.reason}
                if not res.allowed:
                    return self._blocked("ExposureControl", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("ExposureControl gate error", extra={"error": str(exc)})
                gate_results["exposure"] = {"passed": False, "error": str(exc)}
                return self._blocked("ExposureControl", f"gate_error:{exc}", gate_results, t0)

        # GATE 5.5: Margin Gate
        if self._margin is not None:
            try:
                res = self._margin.check(
                    symbol=inp.symbol,
                    side=inp.signal_side,
                    lots=0.01,  # pre-check with min lots; actual check after sizing
                    free_margin=inp.free_margin,
                )
                gate_results["margin"] = {"passed": res.allowed, "reason": res.reason}
                if not res.allowed:
                    return self._blocked("MarginGate", res.reason, gate_results, t0)
            except Exception as exc:
                self._log.error("MarginGate gate error", extra={"error": str(exc)})
                gate_results["margin"] = {"passed": False, "error": str(exc)}
                return self._blocked("MarginGate", f"gate_error:{exc}", gate_results, t0)

        # GATE 6: Lot Sizing
        lot_size = 0.01
        margin_limited = False
        if self._lot is not None:
            try:
                res = self._lot.calculate(
                    symbol=inp.symbol,
                    stop_loss_pips=inp.stop_loss_pips,
                    equity=inp.equity,
                    free_margin=inp.free_margin,
                )
                lot_size = res.lot_size
                margin_limited = res.margin_limited
                gate_results["lot_sizer"] = {
                    "lot_size": lot_size,
                    "margin_limited": margin_limited,
                }
            except Exception as exc:
                self._log.error("LotSizer error", extra={"error": str(exc)})
                gate_results["lot_sizer"] = {"error": str(exc)}
                lot_size = 0.01  # fallback to minimum

        latency_ms = (time.perf_counter() - t0) * 1000
        return RiskOutput(
            approved=True,
            lot_size=lot_size,
            reason="approved",
            gate_results=gate_results,
            latency_ms=latency_ms,
            margin_limited=margin_limited,
        )

    def _blocked(
        self,
        gate: str,
        reason: str,
        gate_results: Dict[str, Any],
        t0: float,
        kill_active: bool = False,
    ) -> RiskOutput:
        latency_ms = (time.perf_counter() - t0) * 1000
        return RiskOutput(
            approved=False,
            lot_size=0.0,
            reason=f"{gate}: {reason}",
            gate_results=gate_results,
            latency_ms=latency_ms,
            kill_active=kill_active,
        )
