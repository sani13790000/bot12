"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine
"""
from __future__ import annotations
import logging
from typing import Any
logger = logging.getLogger(__name__)

class VotingEngine:
    """Coordinates agents, collects votes, applies weighting."""
    def __init__(self) -> None:
        self._weights: dict[str, float] = {}
        self._votes: list[dict] = []

    def register_agent(self, name: str, weight: float = 1.0) -> None:
        self._weights[name] = weight

    def submit_vote(self, agent: str, signal: str, confidence: float, **meta: Any) -> None:
        self._votes.append({"agent": agent, "signal": signal, "confidence": confidence, **meta})

    def aggregate(self) -> dict[str, Any]:
        if not self._votes:
            return {"signal": "NEUTRAL", "confidence": 0.0}
        scores: dict[str, float] = {}
        for v in self._votes:
            w = self._weights.get(v["agent"], 1.0)
            key = v["signal"]
            scores[key] = scores.get(key, 0.0) + v["confidence"] * w
        best = max(scores, key=scores.__getitem__)
        return {"signal": best, "confidence": scores[best], "scores": scores}

    def reset(self) -> None:
        self._votes.clear()

__all__ = ["VotingEngine"]
