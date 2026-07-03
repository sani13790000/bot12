"""AgentService--orchestrates all 7 specialist agents."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .voting_engine import VotingEngine, VoteResult
from .base_agent import AgentConfig

logger = logging.getLogger(__name__)


class AgentService:
    """High-level facade over the VotingEngine."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self._engine = VotingEngine(config)

    async def run_analysis(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
    ) -> VoteResult:
        """Run all agents and return aggregated decision."""
        return await self._engine.run(symbol=symbol, timeframe=timeframe, market_data=market_data)


agent_service = AgentService()
