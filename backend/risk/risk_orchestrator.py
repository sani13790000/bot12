"""
backend/risk/risk_orchestrator.py
Galaxy Vast AI Trading Platform — Risk Orchestrator (Enterprise)

Pipeline:
  EquityProtection → DailyLimits → NewsFilter →
  CorrelationFilter → ExposureControl → LotSizer → APPROVED

H-6 FIX: 5s global timeout on assess() via asyncio.wait_for
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.logger import get_logger

logger = get_logger("risk.orchestrator")

# ── Lazy singleton ──────────────────────────────────────────────────────────────
_instance: "Optional[RiskOrchestrator]" = None
_instance_lock: "Optional[asyncio.Lock]" = None


def _get_instance_lock() -> asyncio.Lock:
    global _instance_lock
    if _instance_lock is None:
        _instance_lock = asyncio.Lock()
    return _instance_lock


@dataclass
class RiskInput:
    """Normalised input for every risk gate."""
    signal_id:       str
    symbol:          str
    direction:       str          # "BUY" | "SELL"
    balance:         float
    equity:          float
    stop_loss_pips:  float        = 20.0
    risk_percent:    float        = 1.0
    open_positions:  List[Any]    = field(default_factory=list)
    metadata:        Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskDecision:
    """Final risk decision returned to ExecutionService."""
    approved:       bool
    reason:         str           = ""
    lot_size:       float         = 0.0
    risk_percent:   float         = 1.0
    gate_results:   Dict[str, Any] = field(default_factory=dict)
    latency_ms:     float         = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved":     self.approved,
            "reason":       self.reason,
            "lot_size":     self.lot_size,
            "risk_percent": self.risk_percent,
            "gate_results": self.gate_results,
            "latency_ms":   self.latency_ms,
        }


class RiskOrchestrator:
    """
    Wires all risk gates in sequence.
    Constructed once via get_risk_orchestrator() — double-checked locking singleton.
    """

    def __init__(
        self,
        *,
        equity_engine: Any    = None,
        daily_limits:  Any    = None,
        news_filter:   Any    = None,
        corr_filter:   Any    = None,
        exposure_ctrl: Any    = None,
        lot_sizer:     Any    = None,
    ) -> None:
        self._equity    = equity_engine
        self._daily     = daily_limits
        self._news      = news_filter
        self._corr      = corr_filter
        self._exposure  = exposure_ctrl
        self._lot_sizer = lot_sizer

    # ── Public API ───────────────────────────────────────────────────────────────

    async def assess(self, inp: Any) -> RiskDecision:
        """Run full risk pipeline with 5s global timeout (H-6 FIX)."""
        try:
            return await asyncio.wait_for(self._assess_inner(inp), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error(
                "RiskOrchestrator pipeline timed out (>5s)",
                symbol=getattr(inp, "symbol", "?"),
            )
            return RiskDecision(approved=False, reason="risk_pipeline_timeout", lot_size=0.0)

    async def _assess_inner(self, inp: Any) -> RiskDecision:
        """Internal pipeline — never call directly; use assess() (H-6)."""
        if not isinstance(inp, RiskInput):
            inp = self._coerce(inp)

        t0 = time.monotonic()
        gate_results: Dict[str, Any] = {}

        # 1. Equity Protection
        if self._equity is not None:
            try:
                res = self._equity.check()
                gate_results["equity"] = {
                    "passed": res.can_trade,
                    "level":  str(res.level),
                    "reason": res.reason,
                }
                if not res.can_trade:
                    return self._blocked("EquityProtection", res.reason, gate_results, t0)
            except Exception as exc:
                logger.error("EquityProtection gate error", error=str(exc))
                gate_results["equity"] = {"passed": False, "error": str(exc)}
                return self._blocked("EquityProtection", f"gate_error:{exc}", gate_results, t0)

        # 2. Daily Limits
        if self._daily is not None:
            try:
                from .daily_limits import TodayTrades
                today = inp.metadata.get("today_trades") or TodayTrades()
                res = self._daily.check_limits(inp.balance, today)
                gate_results["daily_limits"] = {"passed": res.allowed, "reason": res.reason}
                if not res.allowed:
                    return self._blocked("DailyLimits", res.reason, gate_results, t0)
            except Exception as exc:
                logger.error("DailyLimits gate error", error=str(exc))
                gate_results["daily_limits"] = {"passed": False, "error": str(exc)}
                return self._blocked("DailyLimits", f"gate_error:{exc}", gate_results, t0)

        # 3. News Filter
        if self._news is not None:
            try:
                import datetime
                res = self._news.check(inp.symbol, datetime.datetime.utcnow())
                gate_results["news"] = {"passed": not res.blocked, "reason": res.reason}
                if res.blocked:
                    return self._blocked("NewsFilter", res.reason, gate_results, t0)
            except Exception as exc:
                logger.error("NewsFilter gate error", error=str(exc))
                gate_results["news"] = {"passed": False, "error": str(exc)}
                return self._blocked("NewsFilter", f"gate_error:{exc}", gate_results, t0)

        # 4. Correlation Filter
        if self._corr is not None:
            try:
                from .correlation_filter import CorrPosition
                open_pos = [
                    CorrPosition(symbol=p.get("symbol",""), direction=p.get("direction",""),
                                 risk_percent=p.get("risk_percent", 1.0))
                    for p in inp.open_positions if isinstance(p, dict)
                ]
                res = await self._corr.check(
                    new_symbol=inp.symbol,
                    new_direction=inp.direction,
                    open_positions=open_pos,
                    base_risk_percent=inp.risk_percent,
                )
                gate_results["correlation"] = {
                    "passed": res.can_trade,
                    "score":  round(res.correlation_score, 4),
                    "reason": res.reason,
                }
                if not res.can_trade:
                    return self._blocked("CorrelationFilter", res.reason, gate_results, t0)
            except Exception as exc:
                logger.error("CorrelationFilter gate error", error=str(exc))
                gate_results["correlation"] = {"passed": False, "error": str(exc)}
                return self._blocked("CorrelationFilter", f"gate_error:{exc}", gate_results, t0)

        # 5. Exposure Control
        if self._exposure is not None:
            try:
                from .exposure_control import ExposurePosition
                open_pos_exp = [
                    ExposurePosition(
                        symbol=p.get("symbol",""),
                        direction=p.get("direction",""),
                        risk_percent=p.get("risk_percent", 1.0),
                        ticket=p.get("ticket", 0),
                    )
                    for p in inp.open_positions if isinstance(p, dict)
                ]
                res = self._exposure.check(
                    new_symbol=inp.symbol,
                    new_direction=inp.direction,
                    new_risk_percent=inp.risk_percent,
                    open_positions=open_pos_exp,
                )
                gate_results["exposure"] = {"passed": res.approved, "reason": res.reason}
                if not res.approved:
                    return self._blocked("ExposureControl", res.reason, gate_results, t0)
            except Exception as exc:
                logger.error("ExposureControl gate error", error=str(exc))
                gate_results["exposure"] = {"passed": False, "error": str(exc)}
                return self._blocked("ExposureControl", f"gate_error:{exc}", gate_results, t0)

        # 6. Lot Sizing
        lot_size = 0.01
        if self._lot_sizer is not None:
            try:
                res = await self._lot_sizer.calculate(
                    balance=inp.balance,
                    stop_loss_pips=inp.stop_loss_pips if inp.stop_loss_pips > 0 else 20.0,
                    symbol=inp.symbol,
                    override_risk_pct=inp.risk_percent,
                )
                lot_size = res.lot_size
                gate_results["lot_sizer"] = {"passed": True, "lot_size": lot_size}
            except Exception as exc:
                logger.error("LotSizer gate error", error=str(exc))
                gate_results["lot_sizer"] = {"passed": False, "error": str(exc)}

        latency = (time.monotonic() - t0) * 1000
        logger.info(
            "RiskOrchestrator approved",
            symbol=inp.symbol, direction=inp.direction,
            lot_size=lot_size, latency_ms=round(latency, 2),
        )
        return RiskDecision(
            approved=True, reason="",
            lot_size=lot_size,
            risk_percent=inp.risk_percent,
            gate_results=gate_results,
            latency_ms=round(latency, 2),
        )

    async def check(self, **kwargs: Any) -> RiskDecision:
        """IRiskGate-compatible wrapper."""
        inp = RiskInput(
            signal_id=kwargs.get("signal_id", ""),
            symbol=kwargs.get("symbol", ""),
            direction=kwargs.get("direction", "BUY"),
            balance=float(kwargs.get("balance", 10000.0)),
            equity=float(kwargs.get("equity", 10000.0)),
            stop_loss_pips=float(kwargs.get("stop_loss_pips", 20.0)),
            risk_percent=float(kwargs.get("risk_percent", 1.0)),
            open_positions=kwargs.get("open_positions", []),
            metadata=kwargs.get("metadata", {}),
        )
        return await self.assess(inp)

    # ── Helpers ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _blocked(gate: str, reason: str, gate_results: Dict[str, Any], t0: float) -> RiskDecision:
        latency = (time.monotonic() - t0) * 1000
        logger.warning("RiskOrchestrator BLOCKED", gate=gate, reason=reason)
        return RiskDecision(
            approved=False, reason=f"{gate}: {reason}",
            lot_size=0.0, gate_results=gate_results,
            latency_ms=round(latency, 2),
        )

    @staticmethod
    def _coerce(raw: Any) -> RiskInput:
        if isinstance(raw, dict):
            return RiskInput(
                signal_id=raw.get("signal_id", ""),
                symbol=raw.get("symbol", ""),
                direction=raw.get("direction", "BUY"),
                balance=float(raw.get("balance", 10000.0)),
                equity=float(raw.get("equity", 10000.0)),
                stop_loss_pips=float(raw.get("stop_loss_pips", 20.0)),
                risk_percent=float(raw.get("risk_percent", 1.0)),
                open_positions=raw.get("open_positions", []),
                metadata=raw.get("metadata", {}),
            )
        return RiskInput(signal_id="", symbol="", direction="BUY",
                         balance=10000.0, equity=10000.0)


# ── Singleton factory ─────────────────────────────────────────────────────────────

async def get_risk_orchestrator() -> RiskOrchestrator:
    """Double-checked locking singleton — returns wired RiskOrchestrator."""
    global _instance
    if _instance is not None:
        return _instance
    async with _get_instance_lock():
        if _instance is not None:
            return _instance
        _instance = _build_orchestrator()
        logger.info("RiskOrchestrator singleton created")
        return _instance


def _build_orchestrator() -> RiskOrchestrator:
    """Wire all gates. Import errors are logged; missing gate = skipped."""
    equity_engine = None
    daily_limits  = None
    news_filter   = None
    corr_filter   = None
    exposure_ctrl = None
    lot_sizer     = None

    try:
        from .equity_protection import EquityProtectionEngine, EquityProtectionConfig
        equity_engine = EquityProtectionEngine(EquityProtectionConfig())
    except Exception as exc:
        logger.warning("EquityProtection unavailable", error=str(exc))

    try:
        from .daily_limits import DailyLimitsEngine
        daily_limits = DailyLimitsEngine()
    except Exception as exc:
        logger.warning("DailyLimits unavailable", error=str(exc))

    try:
        from .news_filter import NewsFilterGate
        news_filter = NewsFilterGate()
    except Exception as exc:
        logger.warning("NewsFilter unavailable", error=str(exc))

    try:
        from .correlation_filter import CorrelationFilter
        corr_filter = CorrelationFilter()
    except Exception as exc:
        logger.warning("CorrelationFilter unavailable", error=str(exc))

    try:
        from .exposure_control import ExposureControlEngine, ExposureControlConfig
        exposure_ctrl = ExposureControlEngine(ExposureControlConfig())
    except Exception as exc:
        logger.warning("ExposureControl unavailable", error=str(exc))

    try:
        from .lot_sizing import LotSizer
        lot_sizer = LotSizer()
    except Exception as exc:
        logger.warning("LotSizer unavailable", error=str(exc))

    return RiskOrchestrator(
        equity_engine=equity_engine,
        daily_limits=daily_limits,
        news_filter=news_filter,
        corr_filter=corr_filter,
        exposure_ctrl=exposure_ctrl,
        lot_sizer=lot_sizer,
    )
