"""
backend/services/signal_processor.py
Galaxy Vast AI Trading Platform

FIX: Was placeholder string 'SIGNAL_PROCESSOR_CONTENT' -- not Python code.
     Full SignalProcessor with VotingEngine integration.

BUG-3 FIX: vote(signal) wrong signature -> vote(agents, context) correct.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE = float(__import__("os").environ.get("SIGNAL_MIN_CONFIDENCE", "0.55"))
_MIN_RR = float(__import__("os").environ.get("SIGNAL_MIN_RR", "1.5"))


@dataclass
class TradingSignal:
    symbol:      str
    direction:   str
    confidence:  float
    risk_reward: float
    entry_price: float
    sl:          float
    tp:          float
    timeframe:   str = "H1"
    source:      str = "unknown"
    equity:      float = 0.0
    free_margin: float = 0.0
    volume:      float = 0.01
    metadata:    Dict[str, Any] = field(default_factory=dict)
    created_at:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProcessedSignal:
    approved:         bool
    signal:           Optional[TradingSignal]
    rejection_reason: Optional[str] = None
    vote_result:      Optional[Any] = None


class SignalProcessor:
    """
    Validates and routes trading signals through multi-agent voting.

    Usage:
        processor = SignalProcessor()
        processor.register_agents([smc_agent, ml_agent, news_agent])
        result = await processor.process(signal)
    """

    def __init__(self) -> None:
        self._agents: List[Any] = []
        self._voting_engine: Optional[Any] = None
        self._processed = self._approved = self._rejected = 0

    def register_agents(self, agents: List[Any]) -> None:
        self._agents = list(agents)
        logger.info("[SignalProcessor] registered %d agent(s)", len(self._agents))

    def _get_voting_engine(self) -> Optional[Any]:
        if self._voting_engine is None:
            try:
                from backend.agents.voting_engine import VotingEngine
                self._voting_engine = VotingEngine()
            except ImportError:
                logger.warning("[SignalProcessor] VotingEngine not available")
        return self._voting_engine

    async def process(self, signal: TradingSignal) -> ProcessedSignal:
        self._processed += 1

        reject = self._validate(signal)
        if reject:
            self._rejected += 1
            return ProcessedSignal(approved=False, signal=signal, rejection_reason=reject)

        vote_result = await self._run_vote(signal)

        if vote_result is None:
            logger.warning("[SignalProcessor] VotingEngine unavailable, approving by confidence")
            self._approved += 1
            return ProcessedSignal(approved=True, signal=signal)

        vote_name = str(getattr(vote_result, "signal", "ABSTAIN")).upper()
        if vote_name in ("BUY", "SELL") and vote_name == signal.direction.upper():
            self._approved += 1
            return ProcessedSignal(approved=True, signal=signal, vote_result=vote_result)

        self._rejected += 1
        return ProcessedSignal(approved=False, signal=signal,
                               rejection_reason=f"voting_rejected:{vote_name}",
                               vote_result=vote_result)

    def _validate(self, signal: TradingSignal) -> Optional[str]:
        if signal.confidence < _MIN_CONFIDENCE:
            return f"low_confidence:{signal.confidence:.2f}"
        if signal.risk_reward < _MIN_RR:
            return f"low_rr:{signal.risk_reward:.2f}"
        if signal.direction.upper() not in ("BUY", "SELL"):
            return f"invalid_direction:{signal.direction}"
        if signal.sl <= 0 or signal.tp <= 0 or signal.entry_price <= 0:
            return "invalid_prices"
        if signal.direction.upper() == "BUY" and signal.sl >= signal.entry_price:
            return f"sl_above_entry_buy:sl={signal.sl},entry={signal.entry_price}"
        if signal.direction.upper() == "SELL" and signal.sl <= signal.entry_price:
            return f"sl_below_entry_sell:sl={signal.sl},entry={signal.entry_price}"
        return None

    async def _run_vote(self, signal: TradingSignal) -> Optional[Any]:
        """BUG-3 FIX: vote(agents, context) not vote(signal)."""
        ve = self._get_voting_engine()
        if ve is None:
            return None
        if not self._agents:
            logger.warning("[SignalProcessor] no agents -- call register_agents() first")
            return None
        context: Dict[str, Any] = {
            "symbol": signal.symbol, "direction": signal.direction,
            "confidence": signal.confidence, "risk_reward": signal.risk_reward,
            "entry_price": signal.entry_price, "sl": signal.sl, "tp": signal.tp,
            "timeframe": signal.timeframe, "source": signal.source,
        }
        try:
            return await asyncio.wait_for(ve.vote(self._agents, context), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("[SignalProcessor] VotingEngine timeout for %s", signal.symbol)
            return None
        except Exception as exc:
            logger.error("[SignalProcessor] VotingEngine error: %s", exc)
            return None

    def stats(self) -> Dict[str, Any]:
        return {
            "processed": self._processed, "approved": self._approved,
            "rejected": self._rejected, "agents": len(self._agents),
            "approval_rate": self._approved / self._processed if self._processed else 0.0,
        }


signal_processor = SignalProcessor()
