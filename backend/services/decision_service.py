"""backend/services/decision_service.py
Phase Q Fixes:
  Q-4: cache key includes user_id (no cross-user cache pollution)
  Q-5: VotingEngine singleton (not re-created per call)
"""
from __future__ import annotations
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from ..analysis.decision_engine import (DecisionEngine, DecisionInput, DecisionOutput, SMCContext, PriceActionContext, SessionContext, LicenseContext, RiskContext, SymbolPolicy)
from ..core.logger import get_logger
from ..core.config import settings
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("decision_service")
_CACHE_TTL_SECONDS = 60
_CACHE_MAX_SIZE = 256

# Q-5: singleton
_voting_engine_instance = None
_voting_engine_lock = asyncio.Lock()


async def _get_voting_engine():
    """Q-5: lazy singleton — created once, reused forever."""
    global _voting_engine_instance
    if _voting_engine_instance is not None:
        return _voting_engine_instance
    async with _voting_engine_lock:
        if _voting_engine_instance is not None:
            return _voting_engine_instance
        try:
            from ..agents.voting_engine import VotingEngine
            from ..agents.smc_agent import SMCAgent
            from ..agents.market_structure_agent import MarketStructureAgent
            from ..agents.risk_agent import RiskAgent
            from ..agents.news_agent import NewsAgent
            from ..agents.liquidity_agent import LiquidityAgent
            from ..agents.ai_prediction_agent import AIPredictionAgent
            agents = [MarketStructureAgent(weight=0.20), LiquidityAgent(weight=0.15), SMCAgent(weight=0.20), AIPredictionAgent(weight=0.20), RiskAgent(weight=0.15), NewsAgent(weight=0.05)]
            _voting_engine_instance = VotingEngine(agents=agents, min_score_threshold=65.0, min_confidence_threshold=50.0, run_parallel=True)
            logger.info("VotingEngine singleton created with %d agents", len(agents))
        except Exception as exc:
            logger.warning("VotingEngine unavailable: %s", exc)
            _voting_engine_instance = None
    return _voting_engine_instance


class DecisionService:
    def __init__(self, agents=None):
        self.engine = DecisionEngine()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._cache_max = _CACHE_MAX_SIZE
        self._lock = asyncio.Lock()

    def _cache_key(self, user_id: str, symbol: str, direction: str) -> str:
        return f"{user_id}:{symbol}:{direction}"  # Q-4 FIX

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if entry is None: return None
        age = (datetime.now(timezone.utc) - entry["_cached_at"]).total_seconds()
        if age > _CACHE_TTL_SECONDS:
            self._cache.pop(key, None); return None
        self._cache.move_to_end(key); return entry

    def _cache_set(self, key: str, value: Dict[str, Any]) -> None:
        value["_cached_at"] = datetime.now(timezone.utc)
        if key in self._cache: self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    async def make_decision(self, user_id: str, symbol: str, direction: str, timeframe: str = "H1", use_cache: bool = True, **kwargs: Any) -> Dict[str, Any]:
        key = self._cache_key(user_id, symbol, direction)  # Q-4
        if use_cache:
            cached = self._cache_get(key)
            if cached:
                cached["from_cache"] = True; return cached
        voting_engine = await _get_voting_engine()  # Q-5: singleton
        try:
            input_data = DecisionInput(symbol=symbol, direction=direction, timeframe=timeframe, user_id=user_id, **{k: v for k, v in kwargs.items() if k in DecisionInput.__dataclass_fields__})
            output: DecisionOutput = await asyncio.to_thread(self.engine.make_decision, input_data)
            result = asdict(output) if hasattr(output, "__dataclass_fields__") else vars(output)
        except Exception as exc:
            logger.error("DecisionEngine failed symbol=%s: %s", symbol, exc)
            result = {"decision": "NO_TRADE", "score": 0.0, "reason": f"engine_error: {exc}"}
        result["from_cache"] = False
        result["user_id"] = user_id  # Q-4: never leak across users
        if voting_engine:
            try:
                vote_result = await voting_engine.vote(symbol=symbol, direction=direction, user_id=user_id)
                result["vote"] = {"direction": vote_result.direction, "score": vote_result.score, "confidence": vote_result.confidence, "consensus": vote_result.consensus_pct}
            except Exception as exc:
                logger.warning("VotingEngine failed: %s", exc); result["vote"] = None
        if use_cache: self._cache_set(key, result)
        return result

    async def get_decision_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            return await db.select_many("decisions", filters={"user_id": user_id}, order_by="created_at", order_desc=True, limit=limit)
        except Exception as exc:
            logger.error("get_decision_history failed: %s", exc); return []

    def invalidate_cache(self, user_id: str, symbol: Optional[str] = None) -> int:
        prefix = f"{user_id}:"
        keys_to_remove = [k for k in list(self._cache.keys()) if k.startswith(prefix) and (symbol is None or f":{symbol}:" in k)]
        for k in keys_to_remove: self._cache.pop(k, None)
        return len(keys_to_remove)


decision_service = DecisionService()
