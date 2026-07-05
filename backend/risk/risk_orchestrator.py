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
H-6 FIX: 5s global timeout on assess() via asyncio.wait_forP4-FIX-V2-3: MarginGate wired as GATE 5.5 (was missing entirely)
P5-TZ-1: datetime.datetime.utcnow() → timezone_utils.now() (UTC-aware, fixes TypeError with aware news events)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.timezone_utils import now as _utc_now  # P5-TZ-1 FIXED


@dataclass
class RiskInput:
    symbol: str
    direction: str
    volume: float
    confidence: float
    equity: float
    free_margin: float
    open_positions: List[Dict[str, Any]] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory = list)
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
    """
    Enterprise Risk Orchestrator -- multi-gate risk assessment pipeline.
    """

    def __init__(self) -> None:
        import logging
        self._log = logging.getLogger(__name__)
        self._log.info("RiskOrchestrator initialized")

    async def assess(self, input: RiskInput) -> RiskResult:
        """Run the complete risk pipeline with 5s global timeout."""
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_pipeline(input),
                timeout=5.0
            )
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
        try:
            from backend.risk.kill_switch import KillSwitch
            ks = KillSwitch()
            if not await ks.check():
                return RiskResult(approved=False, reject_reason="kill_switch", gate_name="KILLSWITCH")
        except ImportError:
            self._log.warning("KillSwitch not available, skipping")

        # GATE 2: EquityProtection
        try:
            from backend.risk.equity_protection import EquityProtection
            ep = EquityProtection()
            res = await ep.check(input.equity)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="equity_protection", gate_name="EQUITY")
        except ImportError:
            self._log.warning("EquityProtection not available, skipping")

        # GATE 3: DailyLimits
        try:
            from backend.risk.daily_limits import DailyLimits
            dl = DailyLimits()
            res = await dl.check(TodayTrades())
            if hasattr(res, 'can_trade') and not res.can_trade:
                return RiskResult(approved=False, reject_reason="daily_limits", gate_name="DAILY")
        except ImportError:
            self._log.warning("DailyLimits not available, skipping")

        # GATE 4: NewsFilter
        try:
            from backend.risk.news_filter import NewsFilter
            nf = NewsFilter()
            now = _utc_now()
            res = await nf.check(input.symbol, now, input.news_events)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="news_filter", gate_name="NEWS")
        except ImportError:
            self._log.warning("NewsFilter not available, skipping")

        # GATE 5: CorrelationFilter
        try:
            from backend.risk.correlation_filter import CorrelationFilter, CorrPosition  # B6 FIXED
            cf = CorrelationFilter()
            positions = [
                CorrPosition(symbol=p.get("symbol", ""), side=p.get("side", "buy"),
                             volume=p.get("volume", 0.0))
                for p in input.open_positions
            ]
            res = await cf.check(input.symbol, positions)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="correlation", gate_name="CORR")
        except ImportError:
            self._log.warning("CorrelationFilter not available, skipping")

        # GATE 5: ExposureControl
        try:
            from backend.risk.exposure_control import ExposureControl
            ec = ExposureControl()
            res = await ec.check(input.symbol, input.open_positions)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="exposure", gate_name="EXPOSURE")
        except ImportError:
            self._log.warning("ExposureControl not available, skipping")

        # GATE 5.5: MarginGate
        try:
            from backend.risk.margin_gate import MarginGate
            mg = MarginGate()
            res = await mg.check(input.volume, input.free_margin)
            if hasattr(res, 'approved') and not res.approved:
                return RiskResult(approved=False, reject_reason="margin", gate_name="MARGIN")
        except ImportError:
            self._log.warning("MarginGate not available, skipping")

        # GATE 6: LotSizer
        approved_volume = input.volume
        try:
            from backend.risk.lot_sizing import LotSizer
            ls = LotSizer()
            approved_volume = await ls.size(
                input.symbol, input.equity, input.free_margin
            )
        except ImportError:
            self._log.warning("LotSizer not available, using input volume")

        return RiskResult(approved=True, approved_volume=approved_volume)


# ── Singleton & factory ────────────────────────────────────────────────────────────

_risk_orchestrator: Optional[RiskOrchestrator] = None


async def get_risk_orchestrator() -> RiskOrchestrator:
    global _risk_orchestrator
    if _risk_orchestrator is None:
        _risk_orchestrator = RiskOrchestrator()
    return _risk_orchestrator
