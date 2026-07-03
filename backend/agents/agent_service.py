"""backend/agents/agent_service.py
Agent orchestration service.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .voting_engine import voting_engine
from ..core.logger import get_logger

logger = get_logger("agents.agent_service")


class AgentService:
    """Orchestrates multi-agent voting for trade decisions."""

    def __init__(self):
        self._engine = voting_engine

    async def get_signal(
        self,
        symbol: str,
        context: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run all agents and return aggregated signal."""
        try:
            result = await self._engine.vote(context)
            return {
                "symbol": symbol,
                "signal": result.signal.value if result else "HOLD",
                "confidence": result.confidence if result else 0.0,
                "agent_votes": [
                    {
                        "agent_id": v.agent_id,
                        "signal": v.signal.value,
                        "confidence": v.confidence,
                        "weight": v.weight,
                    }
                    for v in (result.votes if result else [])
                ],
                "quorum_reached": result.quorum_reached if result else False,
            }
        except Exception as e:
            logger.error(f"AgentService.get_signal error: {e}")
            return {"symbol": symbol, "signal": "HOLD", "confidence": 0.0, "error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Return agent service health."""
        return {
            "status": "ok",
            "engine": "voting_engine",
            "agents": len(getattr(self._engine, '_agents', [])),
        }
