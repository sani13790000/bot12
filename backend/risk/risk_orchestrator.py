# P5-TZ-1 PATCHED: datetime.datetime.utcnow() → timezone_utils.now()
"""
backend/risk/risk_orchestrator.py
Galaxy Vast AI Trading Platform — Risk Orchestrator (Enterprise)

Pipeline:
  KillSwitch → EquityProtection → DailyLimits → NewsFilter →
  CorrelationFilter → ExposureControl → MarginGate → LotSizer → APPROVED

Fixes:
  CB-NEW-3a: GATE 1 uses get_kill_switch() singleton, NOT KillSwitch()
  CB-NEW-3b: ks.check(equity, balance) called WITH required args
  CB-NEW-3c: KillSwitchActivatedError caught correctly
  AI-NEW-1:  Gate numbering corrected (no duplicate GATE 5)
  AI-NEW-8:  MarginGate uses actual input.volume not hardcoded 0.01
  P4-FIX-1:  KillSwitch wired as FIRST gate
  P4-FIX-2:  res.allowed → res.can_trade for DailyLimits
  P4-FIX-3:  LotSizer receives equity + free_margin
  P4-FIX-4:  TodayTrades() has default fields
  H-6 FIX:   5s global timeout on assess()
  P5-TZ-1:   utcnow() → timezone_utils.now()
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.timezone_utils import now as _utc_now


@dataclass
class RiskInput:
    symbol: str
    direction: str
    volume: float
    confidence: float
    equity: float
    free_margin: float
    open_positions: List[Dict[str, Any]] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskResult:
    approved: bool
    approved_volume: float = 0.0
    reject_reason: Optional[str] = None
    gate_name: Optional[str] = None
    gate_details: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class TodayTrades:
    count: int = 0
    pfl: float = 0.0
    max_drawdown_pct: float = 0.0


class RiskOrchestrator:
    """Enterprise Risk Orchestrator -- multi-gate risk assessment pipeline."""

    def __init__(self) -> None:
        import logging
        self._log = logging.getLogger(__name__)
        self._log.info("RiskOrchestrator initialized")

    async def assess(self, input: RiskInput) -> RiskResult:
        """Run the complete risk pipeline with 5s global timeout."""
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(self._run_pipeline(input), timeout=5.0)
        except asyncio.TimeoutError:
            self._log.error("Risk assessment timeout for %s", input.symbol)
            result = RiskResult(
                approved=False,
                reject_reason="risk_assessment_timeout",
                gate_name="TIMEOUT",
            )
        result.latency_ms = (time.monotonic() - t0) * 1000
        return result

    async def _run_pipeline(self, input: RiskInput) -> RiskResult:

        # GATE 1: KillSwitch
        # CB-NEW-3a FIX: get_kill_switch() singleton, NOT KillSwitch()
        # CB-NEW-3b FIX: pass equity AND balance as required positional args
        # CB-NEW-3c FIX: catch KillSwitchActivatedError specifically
        try:
            from backend.risk.kill_switch import get_kill_switch
            from backend.core.exceptions import KillSwitchActivatedError
            ks = get_kill_switch()
            try:
                await ks.check(equity=input.equity, balance=input.free_margin)
            except KillSwitchActivatedError as ks_err:
                return RiskResult(
                    approved=False,
                    reject_reason=f"kill_switch: {ks_err.reason}",
                    gate_name="GATE1_KILLSWITCH",
                )
        except ImportError:
            self._log.warning("KillSwitch not available, skipping GATE 1")

        # GATE 2: EquityProtection
        try:
            from backend.risk.equity_protection import EquityProtection
            ep = EquityProtection()
            res = await ep.check(input.equity)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="equity_protection", gate_name="GATE2_EQUITY")
        except ImportError:
            self._log.warning("EquityProtection not available, skipping GATE 2")

        # GATE 3: DailyLimits
        try:
            from backend.risk.daily_limits import DailyLimits
            dl = DailyLimits()
            res = await dl.check(TodayTrades())
            if hasattr(res, 'can_trade') and not res.can_trade:
                return RiskResult(approved=False, reject_reason="daily_limits", gate_name="GATE3_DAILY")
        except ImportError:
            self._log.warning("DailyLimits not available, skipping GATE 3")

        # GATE 4: NewsFilter
        try:
            from backend.risk.news_filter import NewsFilter
            nf = NewsFilter()
            now = _utc_now()
            res = await nf.check(symbol=input.symbol, now=now, events=input.news_events)
            if hasattr(res, 'blocked') and res.blocked:
                return RiskResult(
                    approved=False,
                    reject_reason=f"news_filter: {getattr(res, 'reason', 'news event')}",
                    gate_name="GATE4_NEWS",
                )
        except ImportError:
            self._log.warning("NewsFilter not available, skipping GATE 4")

        # GATE 5: CorrelationFilter
        try:
            from backend.risk.correlation_filter import CorrelationFilter
            cf = CorrelationFilter()
            res = await cf.check(
                symbol=input.symbol, direction=input.direction,
                open_positions=input.open_positions,
            )
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(
                    approved=False,
                    reject_reason=f"correlation_filter: {getattr(res, 'reason', '')}",
                    gate_name="GATE5_CORRELATION",
                )
        except ImportError:
            self._log.warning("CorrelationFilter not available, skipping GATE 5")

        # GATE 6: ExposureControl (AI-NEW-1 FIX: was duplicate GATE 5)
        try:
            from backend.risk.exposure_control import ExposureControl
            ec = ExposureControl()
            res = await ec.check(
                symbol=input.symbol, volume=input.volume,
                open_positions=input.open_positions, equity=input.equity,
            )
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(
                    approved=False,
                    reject_reason=f"exposure_control: {getattr(res, 'reason', '')}",
                    gate_name="GATE6_EXPOSURE",
                )
        except ImportError:
            self._log.warning("ExposureControl not available, skipping GATE 6")

        # GATE 7: MarginGate (AI-NEW-1 FIX: was GATE 5.5)
        # AI-NEW-8 FIX: use actual input.volume not hardcoded 0.01
        try:
            from backend.risk.margin_gate import MarginGate
            mg = MarginGate()
            res = await mg.check(
                symbol=input.symbol,
                lots=input.volume,
                free_margin=input.free_margin,
            )
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(
                    approved=False,
                    reject_reason=f"margin_gate: {getattr(res, 'reason', '')}",
                    gate_name="GATE7_MARGIN",
                )
        except ImportError:
            self._log.warning("MarginGate not available, skipping GATE 7")

        # GATE 8: LotSizer (AI-NEW-1 FIX: was GATE 6)
        approved_volume = input.volume
        try:
            from backend.risk.lot_sizer import LotSizer
            ls = LotSizer()
            res = await ls.calculate(
                symbol=input.symbol, confidence=input.confidence,
                equity=input.equity, free_margin=input.free_margin,
            )
            if hasattr(res, 'lots'):
                approved_volume = res.lots
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(
                    approved=False,
                    reject_reason=f"lot_sizer: {getattr(res, 'reason', '')}",
                    gate_name="GATE8_LOTSIZER",
                )
        except ImportError:
            self._log.warning("LotSizer not available, skipping GATE 8")

        return RiskResult(approved=True, approved_volume=approved_volume, gate_name="ALL_PASSED")


_orchestrator: Optional[RiskOrchestrator] = None


async def get_risk_orchestrator() -> RiskOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RiskOrchestrator()
    return _orchestrator
