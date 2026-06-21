"""
Decision Service - Phase D fixes applied:
  ARCH-4: bounded LRU OrderedDict cache (maxsize=256)
  TECH-6: datetime.now(timezone.utc) everywhere
  CRITICAL: _build_decision_input() field names fixed to match decision_engine.py
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
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


def _get_voting_engine_class():
    try:
        from ..agents.voting_engine import VotingEngine
        return VotingEngine
    except ImportError:
        return None


def _get_default_agents():
    try:
        from ..agents.smc_agent import SMCAgent
        from ..agents.market_structure_agent import MarketStructureAgent
        from ..agents.risk_agent import RiskAgent
        from ..agents.news_agent import NewsAgent
        from ..agents.liquidity_agent import LiquidityAgent
        from ..agents.ai_prediction_agent import AIPredictionAgent
        return [
            MarketStructureAgent(weight=0.20),
            LiquidityAgent(weight=0.15),
            SMCAgent(weight=0.20),
            AIPredictionAgent(weight=0.20),
            RiskAgent(weight=0.15),
            NewsAgent(weight=0.05),
        ]
    except ImportError:
        return []


class DecisionService:
    """Orchestrates trade decisions via DecisionEngine + VotingEngine."""

    def __init__(self, agents: Optional[list] = None):
        self.engine = DecisionEngine()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._cache_max = 256
        self._cache_ttl = 60

        VotingEngine = _get_voting_engine_class()
        if VotingEngine is not None:
            _agents = agents if agents is not None else _get_default_agents()
            if _agents:
                self._voting_engine = VotingEngine(
                    agents=_agents,
                    min_score_threshold=65.0,
                    min_confidence_threshold=50.0,
                    run_parallel=True,
                )
            else:
                self._voting_engine = None
        else:
            self._voting_engine = None

    async def request_decision(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
        user_id: str,
        user_settings: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        cache_key = f"{user_id}:{symbol}:{timeframe}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        vote_result = None
        if self._voting_engine is not None:
            try:
                vote_context = self._build_vote_context(symbol, timeframe, market_data)
                vote_result = await self._voting_engine.vote(vote_context)
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
        self._set_cache(cache_key, result)
        return result

    async def get_latest_decision(
        self, user_id: str, symbol: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            rows = await db.select("decisions", filters={"user_id": user_id}, limit=limit)
            if symbol:
                rows = [r for r in rows if r.get("symbol") == symbol]
            return rows
        except Exception as exc:
            logger.error("get_latest_decision error: %s", exc)
            return []

    async def get_decision_by_id(
        self, decision_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        try:
            rows = await db.select(
                "decisions",
                filters={"id": decision_id, "user_id": user_id},
                limit=1,
            )
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("get_decision_by_id error: %s", exc)
            return None

    def _build_vote_context(
        self, symbol: str, timeframe: str, market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "symbol":        symbol,
            "timeframe":     timeframe,
            "market_data":   market_data,
            "ohlcv":         market_data.get("ohlcv", []),
            "current_price": market_data.get("current_price", 0.0),
            "spread":        market_data.get("spread", 0.0),
            "atr":           market_data.get("atr", 0.0),
        }

    def _build_decision_input(
        self, symbol, timeframe, market_data, user_id, user_settings=None
    ) -> DecisionInput:
        smc_data = market_data.get("smc", {})
        pa_data  = market_data.get("price_action", {})
        now_utc  = datetime.now(timezone.utc)
        user_cfg = user_settings or {}

        return DecisionInput(
            symbol=symbol,
            timeframe=timeframe,
            smc_context=SMCContext(
                # FIX: trend= not direction=, trend_score= not score=
                trend=smc_data.get("direction", "ranging"),
                trend_score=float(smc_data.get("score", 0)),
                structure_event=smc_data.get("structure_event"),
                structure_direction=smc_data.get("structure_direction"),
                structure_level=smc_data.get("structure_level"),
                order_blocks=smc_data.get("order_blocks") or [],
                fvgs=smc_data.get("fvgs") or [],
                swing_high=smc_data.get("swing_high"),
                swing_low=smc_data.get("swing_low"),
                liquidity_direction=smc_data.get("liquidity_direction"),
            ),
            price_action_context=PriceActionContext(
                # FIX: direction_score= not score=
                direction=pa_data.get("direction", "neutral"),
                direction_score=float(pa_data.get("score", 0)),
                patterns=pa_data.get("patterns") or [],
            ),
            session_context=SessionContext(
                # FIX: removed hour_utc (not a field); session_score added
                current_session=market_data.get("session", "london"),
                session_score=float(market_data.get("session_score", 50.0)),
            ),
            license_context=LicenseContext(
                # FIX: removed features, allowed_symbols (not fields)
                is_valid=user_cfg.get("license_valid", True),
                license_type=user_cfg.get("license_type", "standard"),
            ),
            risk_context=RiskContext(
                # FIX: use actual field names from RiskContext dataclass
                available_margin=float(user_cfg.get("equity", 10_000)),
                risk_per_trade=float(user_cfg.get("risk_per_trade", 0.01)),
                max_daily_loss=float(user_cfg.get("max_daily_loss", 0.03)),
                open_positions=int(user_cfg.get("open_positions", 0)),
                max_positions=int(user_cfg.get("max_positions", 3)),
                daily_loss_pct=float(user_cfg.get("daily_loss_percent", 0.0)),
            ),
            symbol_policy=SymbolPolicy(
                # FIX: is_allowed= not allowed=, min_score_override= not min_score=
                symbol=symbol,
                is_allowed=user_cfg.get("symbol_allowed", True),
                min_score_override=user_cfg.get("min_score"),
            ),
        )

    def _output_to_dict(self, output: DecisionOutput) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "symbol":           output.symbol,
            "timeframe":        output.timeframe,
            "decision":         output.decision,
            "direction":        output.direction,
            "confidence_score": output.confidence_score,
            "quality_score":    output.quality_score,
            "allowed":          output.allowed,
            "created_at":       datetime.now(timezone.utc).isoformat(),
        }
        for attr, key in [
            ("reason_codes",    "reason_codes"),
            ("reasons_persian", "reasons"),
            ("blocked_reasons", "blocked_reasons"),
        ]:
            val = getattr(output, attr, None)
            if val:
                result[key] = [v.value if hasattr(v, "value") else str(v) for v in val]
        for attr in ("trading_levels", "risk_profile"):
            val = getattr(output, attr, None)
            if val:
                result[attr] = asdict(val)
        for attr in ("score_breakdown", "metadata"):
            val = getattr(output, attr, None)
            if val:
                result[attr] = val
        return result

    async def _save_decision(
        self, user_id: str, output: DecisionOutput
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        record = {
            "user_id":          user_id,
            "symbol":           output.symbol,
            "timeframe":        output.timeframe,
            "decision":         output.decision,
            "confidence_score": output.confidence_score,
            "quality_score":    output.quality_score,
            "allowed":          output.allowed,
            "created_at":       now.isoformat(),
            "valid_until":      (now + timedelta(hours=4)).isoformat(),
            "status":           "generated",
            "generated_at":     now.isoformat(),
        }
        try:
            await db.insert("decisions", record)
        except Exception as exc:
            logger.error("_save_decision failed: %s", exc)
        return record

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._cache:
            cached = self._cache[key]
            cached_at = datetime.fromisoformat(cached["_cached_at"])
            now = datetime.now(timezone.utc)
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            if (now - cached_at).total_seconds() < self._cache_ttl:
                self._cache.move_to_end(key)
                return cached
            del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Dict[str, Any]) -> None:
        value["_cached_at"] = datetime.now(timezone.utc).isoformat()
        if key not in self._cache and len(self._cache) >= self._cache_max:
            self._cache.popitem(last=False)
        self._cache[key] = value
        self._cache.move_to_end(key)


decision_service = DecisionService()
