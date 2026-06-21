from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from ..analysis.decision_engine import (
    DecisionEngine, DecisionInput, DecisionOutput,
    SMCContext, PriceActionContext, SessionContext,
    LicenseContext, RiskContext, SymbolPolicy,
)
from ..core.logger import get_logger
from ..core.config import settings
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("decision_service")

_CACHE_TTL_SECONDS = 60
_CACHE_MAX_SIZE = 256


def _get_voting_engine_lazy():
    """G-10: lazy import so agent failures dont break the whole service."""
    try:
        from ..agents.voting_engine import VotingEngine
        from ..agents.smc_agent import SMCAgent
        from ..agents.market_structure_agent import MarketStructureAgent
        from ..agents.risk_agent import RiskAgent
        from ..agents.news_agent import NewsAgent
        from ..agents.liquidity_agent import LiquidityAgent
        from ..agents.ai_prediction_agent import AIPredictionAgent

        agents = [
            MarketStructureAgent(weight=0.20),
            LiquidityAgent(weight=0.15),
            SMCAgent(weight=0.20),
            AIPredictionAgent(weight=0.20),
            RiskAgent(weight=0.15),
            NewsAgent(weight=0.05),
        ]
        return VotingEngine(
            agents=agents,
            min_score_threshold=65.0,
            min_confidence_threshold=50.0,
            run_parallel=True,
        )
    except Exception as exc:
        logger.warning("VotingEngine unavailable: %s", exc)
        return None


class DecisionService:
    """Orchestrates trade decisions via DecisionEngine + VotingEngine."""

    def __init__(self, agents=None):
        self.engine = DecisionEngine()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._cache_max = _CACHE_MAX_SIZE
        self._cache_ttl = _CACHE_TTL_SECONDS
        self._cache_lock = asyncio.Lock()  # G-9
        self._voting_engine = None
        self._voting_engine_ready = False
        self._injected_agents = agents

    def _get_voting_engine(self):
        if not self._voting_engine_ready:
            if self._injected_agents:
                try:
                    from ..agents.voting_engine import VotingEngine
                    self._voting_engine = VotingEngine(
                        agents=self._injected_agents,
                        min_score_threshold=65.0,
                        min_confidence_threshold=50.0,
                        run_parallel=True,
                    )
                except Exception as exc:
                    logger.warning("VotingEngine init failed: %s", exc)
                    self._voting_engine = _get_voting_engine_lazy()
            else:
                self._voting_engine = _get_voting_engine_lazy()
            self._voting_engine_ready = True
        return self._voting_engine

    def _get_cached(self, key: str):
        entry = self._cache.get(key)
        if entry is None:
            return None
        if datetime.now(timezone.utc) - entry["_cached_at"] > timedelta(seconds=self._cache_ttl):
            self._cache.pop(key, None)
            return None
        return {k: v for k, v in entry.items() if k != "_cached_at"}

    async def _set_cache(self, key: str, value: Dict[str, Any]) -> None:
        async with self._cache_lock:  # G-9
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = {**value, "_cached_at": datetime.now(timezone.utc)}
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    async def request_decision(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
        user_id: str,
        user_settings=None,
        ip_address=None,
    ) -> Dict[str, Any]:
        cache_key = f"{user_id}:{symbol}:{timeframe}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        vote_result = None
        ve = self._get_voting_engine()
        if ve is not None:
            try:
                vote_context = self._build_vote_context(symbol, timeframe, market_data)
                vote_result = await ve.vote(vote_context)
            except Exception as exc:
                logger.warning("VotingEngine failed: %s", exc)

        decision_input = self._build_decision_input(
            symbol, timeframe, market_data, user_id, user_settings
        )
        output: DecisionOutput = self.engine.make_decision(decision_input)

        if vote_result is not None:
            try:
                if hasattr(vote_result, "weighted_score"):
                    output.confidence_score = round(
                        output.confidence_score * 0.4 + vote_result.weighted_score * 0.6, 4
                    )
                if hasattr(vote_result, "final_confidence"):
                    output.quality_score = round(
                        output.quality_score * 0.4 + vote_result.final_confidence * 0.6, 4
                    )
            except Exception as exc:
                logger.debug("Vote merge failed: %s", exc)

        await audit_service.log_decision(
            user_id=user_id,
            symbol=symbol,
            decision=output.decision,
            confidence=output.confidence_score,
            ip_address=ip_address,
        )

        result = self._output_to_dict(output)
        await self._set_cache(cache_key, result)
        return result

    async def get_latest_decision(self, user_id: str, symbol=None, limit: int = 10):
        try:
            filters: Dict[str, Any] = {"user_id": user_id}
            if symbol:
                filters["symbol"] = symbol  # G-12: DB-side filter
            return await db.select("decisions", filters=filters, limit=limit)
        except Exception as exc:
            logger.error("get_latest_decision error: %s", exc)
            return []

    async def get_decision_by_id(self, decision_id: str, user_id: str):
        try:
            return await db.select_one("decisions", {"id": decision_id, "user_id": user_id})
        except Exception as exc:
            logger.error("get_decision_by_id error: %s", exc)
            return None

    def get_cache_stats(self):
        return {"size": len(self._cache), "max_size": self._cache_max, "ttl_seconds": self._cache_ttl}

    def clear_cache(self, user_id=None) -> int:
        if user_id is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        keys = [k for k in self._cache if k.startswith(f"{user_id}:")]
        for k in keys:
            self._cache.pop(k, None)
        return len(keys)

    def _build_vote_context(self, symbol, timeframe, market_data):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "price": market_data.get("price", 0.0),
            "trend": market_data.get("trend", "NEUTRAL"),
            "volatility": market_data.get("volatility", 1.0),
            "session": market_data.get("session", "london"),
            "spread": market_data.get("spread", 0.0),
            **market_data,
        }

    def _build_decision_input(
        self, symbol, timeframe, market_data, user_id, user_settings=None
    ) -> DecisionInput:
        """
        G-8 FIX: all field names verified against decision_engine.py dataclasses.
        """
        s = user_settings or {}
        md = market_data

        smc_ctx = SMCContext(
            trend=md.get("trend", "NEUTRAL"),
            has_order_block=md.get("has_order_block", False),
            has_fvg=md.get("has_fvg", False),
            has_bos=md.get("has_bos", False),
            has_choch=md.get("has_choch", False),
            premium_discount=md.get("premium_discount", 0.5),
            liquidity_score=md.get("liquidity_score", 0.5),
        )

        pa_ctx = PriceActionContext(
            direction_score=float(md.get("direction_score", md.get("pa_score", 50.0))),
            has_pin_bar=md.get("has_pin_bar", False),
            has_engulfing=md.get("has_engulfing", False),
            has_inside_bar=md.get("has_inside_bar", False),
            trend_alignment=md.get("trend_alignment", True),
        )

        hour_utc = datetime.now(timezone.utc).hour
        session_ctx = SessionContext(
            session=md.get("session", "london"),
            hour=hour_utc,
            is_high_impact_news=md.get("is_high_impact_news", False),
        )

        license_ctx = LicenseContext(
            is_valid=s.get("license_valid", True),
            plan=s.get("license_plan", "standard"),
        )

        risk_ctx = RiskContext(
            available_margin=float(md.get("available_margin", md.get("balance", 10000.0))),
            open_positions_count=int(md.get("open_positions_count", 0)),
            daily_loss_percent=float(md.get("daily_loss_percent", 0.0)),
            max_daily_loss=float(s.get("max_daily_loss", 3.0)),
            max_open_positions=int(s.get("max_open_positions", 5)),
        )

        policy = SymbolPolicy(
            symbol=symbol,
            min_score_override=float(s.get("min_score_override", 65.0)),
            allowed=symbol in s.get("allowed_symbols", [symbol]),
        )

        return DecisionInput(
            symbol=symbol,
            timeframe=timeframe,
            smc=smc_ctx,
            price_action=pa_ctx,
            session=session_ctx,
            license=license_ctx,
            risk=risk_ctx,
            policy=policy,
        )

    def _output_to_dict(self, output: DecisionOutput) -> Dict[str, Any]:
        return {
            "decision": output.decision,
            "confidence_score": round(output.confidence_score, 4),  # G-11: no int()
            "quality_score": round(output.quality_score, 4),
            "reasons": output.reasons,
            "blocked_by": output.blocked_by,
            "symbol": output.symbol,
            "timeframe": output.timeframe,
            "timestamp": output.timestamp.isoformat() if hasattr(output, "timestamp") else None,
        }


decision_service = DecisionService()
