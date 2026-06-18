"""
سرویس تصمیم‌گیری

مدیریت درخواست‌های تصمیم‌گیری و تولید سیگنال.

نویسنده: MT5 Trading Team

Phase D Fix:
  D1 — VotingEngine اکنون در جریان اصلی request_decision() اجرا می‌شود.
       نتیجه vote به عنوان context['vote_result'] به DecisionEngine می‌رسد.
       اگر VotingEngine در دسترس نباشد، سیستم gracefully fallback می‌کند.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import asdict

from ..analysis.decision_engine import (
    DecisionEngine, DecisionInput, DecisionOutput,
    SMCContext, PriceActionContext, SessionContext,
    LicenseContext, RiskContext, SymbolPolicy, VolatilityContext,
    MultiTimeframeContext, LiquidityContext
)
from ..core.enums import (
    DecisionAction, MarketTrend, DecisionDirection,
    SessionType, LiquidityState, RiskLevel
)
from ..core.logger import get_logger
from ..core.config import settings
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("decision_service")

# ── D1: lazy import VotingEngine تا circular import نشود ─────────────────────
def _get_voting_engine_class():
    """Lazy import برای جلوگیری از circular import."""
    try:
        from ..agents.voting_engine import VotingEngine
        return VotingEngine
    except Exception as exc:
        logger.warning(f"VotingEngine unavailable — fallback to engine-only: {exc}")
        return None


def _get_default_agents():
    """ساخت لیست پیش‌فرض agents."""
    try:
        from ..agents.smc_agent          import SMCAgent
        from ..agents.market_structure_agent import MarketStructureAgent
        from ..agents.risk_agent         import RiskAgent
        from ..agents.news_agent         import NewsAgent
        from ..agents.liquidity_agent    import LiquidityAgent
        from ..agents.ai_prediction_agent import AIPredictionAgent
        return [
            SMCAgent(weight=0.30),
            MarketStructureAgent(weight=0.20),
            RiskAgent(weight=0.20),
            AIPredictionAgent(weight=0.15),
            LiquidityAgent(weight=0.10),
            NewsAgent(weight=0.05),
        ]
    except Exception as exc:
        logger.warning(f"Cannot build default agents: {exc}")
        return []


class DecisionService:
    """
    سرویس تصمیم‌گیری

    مسئولیت‌ها:
    - مدیریت درخواست‌های تصمیم‌گیری
    - کش کردن تصمیم‌ها
    - تولید سیگنال از تصمیم
    - ذخیره تاریخچه

    D1 Fix: VotingEngine اکنون قبل از DecisionEngine اجرا می‌شود.
    جریان:
      market_data → VotingEngine.vote() → VoteResult
                                             ↓
                                      DecisionEngine.make_decision()
                                      (با vote_result در context)
                                             ↓
                                         DecisionOutput
    """

    def __init__(self, agents: Optional[list] = None):
        self.engine = DecisionEngine()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 60  # ثانیه

        # D1: ساخت VotingEngine با agents
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
                logger.info(
                    f"DecisionService: VotingEngine فعال با {len(_agents)} agent"
                )
            else:
                self._voting_engine = None
                logger.warning("DecisionService: هیچ agent در دسترس نیست — VotingEngine غیرفعال")
        else:
            self._voting_engine = None

    async def request_decision(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
        user_id: str,
        user_settings: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        درخواست تصمیم جدید
        """
        logger.info(f"درخواست تصمیم جدید: {symbol} {timeframe} توسط {user_id}")

        cache_key = f"{symbol}_{timeframe}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # ── D1: مرحله ۱ — VotingEngine ───────────────────────────────────────
        vote_result = None
        if self._voting_engine is not None:
            try:
                vote_context = self._build_vote_context(symbol=symbol, timeframe=timeframe, market_data=market_data)
                vote_result = await self._voting_engine.vote(vote_context)
                logger.info(f"VoteResult: {vote_result.decision.value} | score={vote_result.weighted_score:.1f} | conf={vote_result.final_confidence:.1f}")
                market_data = dict(market_data)
                market_data["vote_result"] = {
                    "decision":         vote_result.decision.value,
                    "weighted_score":   vote_result.weighted_score,
                    "final_confidence": vote_result.final_confidence,
                    "direction":        vote_result.direction,
                    "passed_threshold": vote_result.passed_threshold,
                    "blocking_agents":  vote_result.blocking_agents,
                    "reason":           vote_result.reason,
                    "votes_summary":    vote_result.votes_summary,
                }
            except Exception as exc:
                logger.error(f"VotingEngine failed — continuing with engine-only: {exc}", exc_info=True)
                vote_result = None

        # ── مرحله ۲ — DecisionInput ─────────────────────────────────────────
        decision_input = self._build_decision_input(
            symbol=symbol, timeframe=timeframe, market_data=market_data,
            user_id=user_id, user_settings=user_settings
        )

        # ── مرحله ۳ — DecisionEngine ──────────────────────────────────────────
        decision_output = self.engine.make_decision(decision_input)

        result = self._output_to_dict(decision_output)

        if vote_result is not None:
            result["vote_result"] = market_data.get("vote_result", {})
            result["agents_used"] = len(self._voting_engine.agents) if self._voting_engine else 0

        self._set_cache(cache_key, result)

        await audit_service.log_decision(
            user_id=user_id, symbol=symbol,
            decision=result["decision"], score=result["quality_score"],
            ip_address=ip_address
        )

        if decision_output.decision != DecisionAction.NO_TRADE:
            await self._save_decision(user_id, decision_output)

        return result

    async def get_latest_decision(self, user_id: str, symbol: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        filters = {"user_id": user_id, "status": "generated"}
        signals = await db.select_many("signals", filters=filters, order_by="generated_at", order_desc=True, limit=limit)
        if symbol:
            signals = [s for s in signals if s.get("symbol") == symbol]
        return signals

    async def get_decision_by_id(self, decision_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await db.select_one("signals", {"id": decision_id, "user_id": user_id})

    def _build_vote_context(self, symbol: str, timeframe: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """D1: ساخت context برای VotingEngine از market_data."""
        smc     = market_data.get("smc", {})
        pa      = market_data.get("price_action", {})
        session = market_data.get("session", {})
        risk    = market_data.get("risk", {})
        liq     = market_data.get("liquidity", {})
        vol     = market_data.get("volatility", {})
        ai_pred = market_data.get("ai_prediction", {})

        smc_trend = smc.get("trend", "ranging")
        pa_dir    = pa.get("direction", "neutral")
        if smc_trend == "bullish" or pa_dir == "bullish":
            direction = "BUY"
        elif smc_trend == "bearish" or pa_dir == "bearish":
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        return {
            "symbol": symbol, "timeframe": timeframe, "direction": direction,
            "smc_trend": smc.get("trend", "ranging"),
            "smc_trend_score": smc.get("trend_score", 0),
            "structure_event": smc.get("structure_event"),
            "structure_direction": smc.get("structure_direction"),
            "liquidity_swept": smc.get("liquidity_swept", False),
            "order_blocks": smc.get("order_blocks", []),
            "fvgs": smc.get("fvgs", []),
            "premium_discount": smc.get("premium_discount", "neutral"),
            "pa_direction": pa.get("direction", "neutral"),
            "pa_direction_score": pa.get("direction_score", 0),
            "patterns": pa.get("patterns", []),
            "candle_strength": pa.get("candle_strength", "none"),
            "current_session": session.get("current_session", "closed"),
            "killzone_active": session.get("killzone_active", False),
            "killzone_name": session.get("killzone_name"),
            "session_score": session.get("session_score", 0),
            "daily_pnl": risk.get("daily_pnl", 0.0),
            "daily_trades": risk.get("daily_trades", 0),
            "open_positions": risk.get("open_positions", 0),
            "max_daily_loss": risk.get("max_daily_loss", -500.0),
            "max_daily_trades": risk.get("max_daily_trades", 5),
            "liquidity_state": liq.get("state", "none"),
            "buy_side_liquidity": liq.get("buy_side", []),
            "sell_side_liquidity": liq.get("sell_side", []),
            "sweep_score": liq.get("sweep_score", 0),
            "atr": vol.get("atr", 0.0),
            "atr_percentile": vol.get("atr_percentile", 0),
            "volatility_level": vol.get("volatility_level", "medium"),
            "spread": vol.get("spread", 0.0),
            "ai_prediction": ai_pred,
            "decision_score": market_data.get("decision_score", 50.0),
            "htf_trend": market_data.get("mtf", {}).get("htf_trend", "ranging"),
            "htf_alignment": market_data.get("mtf", {}).get("htf_alignment", False),
            "htf_score": market_data.get("mtf", {}).get("htf_score", 0),
            "upcoming_news": market_data.get("upcoming_news", []),
            "news_impact": market_data.get("news_impact", "none"),
        }

    def _build_decision_input(self, symbol, timeframe, market_data, user_id, user_settings=None) -> DecisionInput:
        smc_data = market_data.get("smc", {})
        smc_context = SMCContext(
            trend=MarketTrend(smc_data.get("trend", "ranging")),
            trend_score=smc_data.get("trend_score", 0),
            structure_event=smc_data.get("structure_event"),
            structure_direction=smc_data.get("structure_direction"),
            structure_level=smc_data.get("structure_level"),
            liquidity_swept=smc_data.get("liquidity_swept", False),
            liquidity_direction=smc_data.get("liquidity_direction"),
            premium_discount=smc_data.get("premium_discount", "neutral"),
            order_blocks=smc_data.get("order_blocks", []),
            fvgs=smc_data.get("fvgs", []),
            swing_high=smc_data.get("swing_high"),
            swing_low=smc_data.get("swing_low")
        )
        pa_data = market_data.get("price_action", {})
        pa_context = PriceActionContext(
            direction=DecisionDirection(pa_data.get("direction", "neutral")),
            direction_score=pa_data.get("direction_score", 0),
            patterns=pa_data.get("patterns", []),
            candle_strength=pa_data.get("candle_strength", "none") if isinstance(pa_data.get("candle_strength"), str) else "none"
        )
        session_data = market_data.get("session", {})
        session_context = SessionContext(
            current_session=SessionType(session_data.get("current_session", "closed")),
            killzone_active=session_data.get("killzone_active", False),
            killzone_name=session_data.get("killzone_name"),
            session_score=session_data.get("session_score", 0),
            session_overlap=session_data.get("session_overlap", False)
        )
        liq_data = market_data.get("liquidity", {})
        liquidity_context = LiquidityContext(
            state=LiquidityState(liq_data.get("state", "none")),
            buy_side_liquidity=liq_data.get("buy_side", []),
            sell_side_liquidity=liq_data.get("sell_side", []),
            sweep_score=liq_data.get("sweep_score", 0)
        )
        vol_data = market_data.get("volatility", {})
        volatility_context = VolatilityContext(
            atr=vol_data.get("atr", 0.0),
            atr_percentile=vol_data.get("atr_percentile", 0),
            volatility_level=RiskLevel(vol_data.get("volatility_level", "medium")),
            spread=vol_data.get("spread", 0.0),
            spread_percentile=vol_data.get("spread_percentile", 0)
        )
        mtf_data = market_data.get("mtf", {})
        mtf_context = MultiTimeframeContext(
            higher_timeframe_trend=MarketTrend(mtf_data.get("htf_trend", "ranging")),
            htf_alignment=mtf_data.get("htf_alignment", False),
            htf_score=mtf_data.get("htf_score", 0),
            lower_timeframe_entry=mtf_data.get("ltf_entry", False),
            ltf_score=mtf_data.get("ltf_score", 0)
        )
        risk_data = market_data.get("risk", {})
        risk_context = RiskContext(
            daily_pnl=risk_data.get("daily_pnl", 0.0),
            daily_trades=risk_data.get("daily_trades", 0),
            open_positions=risk_data.get("open_positions", 0),
            max_daily_loss=risk_data.get("max_daily_loss", -500.0),
            max_daily_trades=risk_data.get("max_daily_trades", 5),
            max_positions=risk_data.get("max_positions", 3),
            risk_per_trade=risk_data.get("risk_per_trade", 0.02),
            available_margin=risk_data.get("available_margin", 0.0)
        )
        license_data = market_data.get("license", {})
        license_context = LicenseContext(
            is_valid=license_data.get("is_valid", True),
            is_expired=license_data.get("is_expired", False),
            license_type=license_data.get("license_type", "trial"),
            allowed_features=license_data.get("allowed_features", []),
            max_devices=license_data.get("max_devices", 1),
            devices_used=license_data.get("devices_used", 0)
        )
        policy_data = market_data.get("symbol_policy", {})
        symbol_policy = SymbolPolicy(
            symbol=symbol,
            allowed=policy_data.get("allowed", True),
            max_lot=policy_data.get("max_lot", 1.0),
            min_lot=policy_data.get("min_lot", 0.01),
            max_spread=policy_data.get("max_spread", 5.0),
            max_slippage=policy_data.get("max_slippage", 3.0),
            allowed_sessions=policy_data.get("allowed_sessions", []),
            blocked_reason=policy_data.get("blocked_reason")
        )
        return DecisionInput(
            symbol=symbol, timeframe=timeframe,
            current_price=market_data.get("current_price", 0.0),
            smc_context=smc_context, price_action_context=pa_context,
            mtf_context=mtf_context, session_context=session_context,
            liquidity_context=liquidity_context, volatility_context=volatility_context,
            risk_context=risk_context, license_context=license_context,
            symbol_policy=symbol_policy, user_settings=user_settings or {}
        )

    def _output_to_dict(self, output: DecisionOutput) -> Dict[str, Any]:
        result = {
            "symbol": output.symbol, "timeframe": output.timeframe,
            "created_at": output.created_at.isoformat(),
            "decision": output.decision.value, "direction": output.direction.value,
            "confidence_score": output.confidence_score, "quality_score": output.quality_score,
            "allowed": output.allowed,
            "reason_codes": [r.value for r in output.reason_codes],
            "reasons": output.reasons_persian,
            "blocked_reasons": [r.value for r in output.blocked_reasons],
            "score_breakdown": output.score_breakdown, "metadata": output.metadata
        }
        if output.trading_levels:
            result["trading_levels"] = {
                "entry_zone": output.trading_levels.entry_zone,
                "entry_zone_high": output.trading_levels.entry_zone_high,
                "entry_zone_low": output.trading_levels.entry_zone_low,
                "stop_loss": output.trading_levels.stop_loss,
                "take_profit_1": output.trading_levels.take_profit_1,
                "take_profit_2": output.trading_levels.take_profit_2,
                "take_profit_3": output.trading_levels.take_profit_3,
                "invalidation_level": output.trading_levels.invalidation_level,
                "risk_reward_ratio": output.trading_levels.risk_reward_ratio
            }
        if output.risk_profile:
            result["risk_profile"] = {
                "risk_level": output.risk_profile.risk_level.value,
                "position_size": output.risk_profile.position_size,
                "max_loss_amount": output.risk_profile.max_loss_amount,
                "potential_profit": output.risk_profile.potential_profit,
                "risk_reward_ratio": output.risk_profile.risk_reward_ratio
            }
        return result

    async def _save_decision(self, user_id: str, output: DecisionOutput) -> Dict[str, Any]:
        valid_until = (datetime.utcnow() + timedelta(hours=4)).isoformat()
        signal_data = {
            "user_id": user_id, "symbol": output.symbol, "timeframe": output.timeframe,
            "direction": output.direction.value, "action": output.decision.value,
            "total_score": output.quality_score,
            "entry_price": output.trading_levels.entry_zone if output.trading_levels else None,
            "stop_loss": output.trading_levels.stop_loss if output.trading_levels else None,
            "take_profit_1": output.trading_levels.take_profit_1 if output.trading_levels else None,
            "take_profit_2": output.trading_levels.take_profit_2 if output.trading_levels else None,
            "take_profit_3": output.trading_levels.take_profit_3 if output.trading_levels else None,
            "risk_reward": output.trading_levels.risk_reward_ratio if output.trading_levels else None,
            "reasons": output.reasons_persian, "score_breakdown": output.score_breakdown,
            "status": "generated", "generated_at": datetime.utcnow().isoformat(),
            "valid_until": valid_until, "metadata": output.metadata
        }
        result = await db.insert("signals", signal_data)
        logger.info(f"سیگنال ذخیره شد: {result.get('id')}")
        return result

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._cache:
            cached = self._cache[key]
            if (datetime.utcnow() - datetime.fromisoformat(cached["_cached_at"])).total_seconds() < self._cache_ttl:
                return cached
            del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Dict[str, Any]) -> None:
        value["_cached_at"] = datetime.utcnow().isoformat()
        self._cache[key] = value


# نمونه گلوبال
decision_service = DecisionService()
