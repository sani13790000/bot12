"""
سرویس تصمیم‌گیری

مدیریت درخواست‌های تصمیم‌گیری و تولید سیگنال.

نویسنده: MT5 Trading Team
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


class DecisionService:
    """
    سرویس تصمیم‌گیری

    مسئولیت‌ها:
    - مدیریت درخواست‌های تصمیم‌گیری
    - کش کردن تصمیم‌ها
    - تولید سیگنال از تصمیم
    - ذخیره تاریخچه
    """

    def __init__(self):
        self.engine = DecisionEngine()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 60  # ثانیه

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

        Args:
            symbol: نماد
            timeframe: تایم‌فریم
            market_data: داده بازار
            user_id: شناسه کاربر
            user_settings: تنظیمات کاربر
            ip_address: آدرس IP

        Returns:
            نتیجه تصمیم‌گیری
        """
        logger.info(f"درخواست تصمیم جدید: {symbol} {timeframe} توسط {user_id}")

        # بررسی کش
        cache_key = f"{symbol}_{timeframe}"
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug(f"استفاده از تصمیم کش شده: {cache_key}")
            return cached

        # ساخت DecisionInput
        decision_input = self._build_decision_input(
            symbol=symbol,
            timeframe=timeframe,
            market_data=market_data,
            user_id=user_id,
            user_settings=user_settings
        )

        # تصمیم‌گیری
        decision_output = self.engine.make_decision(decision_input)

        # تبدیل به دیکشنری
        result = self._output_to_dict(decision_output)

        # کش کردن
        self._set_cache(cache_key, result)

        # ثبت لاگ
        await audit_service.log_decision(
            user_id=user_id,
            symbol=symbol,
            decision=result["decision"],
            score=result["quality_score"],
            ip_address=ip_address
        )

        # ذخیره در دیتابیس اگر BUY یا SELL
        if decision_output.decision != DecisionAction.NO_TRADE:
            await self._save_decision(user_id, decision_output)

        return result

    async def get_latest_decision(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        دریافت آخرین تصمیم‌ها

        Args:
            user_id: شناسه کاربر
            symbol: فیلتر نماد
            limit: حدمكثر تعداد

        Returns:
            لیست تصمیم‌ها
        """
        filters = {"user_id": user_id, "status": "generated"}

        # دریافت از signals Table
        signals = await db.select_many(
            "signals",
            filters=filters,
            order_by="generated_at",
            order_desc=True,
            limit=limit
        )

        if symbol:
            signals = [s for s in signals if s.get("symbol") == symbol]

        return signals

    async def get_decision_by_id(
        self,
        decision_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        دریافت یک تصمیم خاص

        Args:
            decision_id: شناسه تصمیم
            user_id: شناسه کاربر

        Returns:
            تصمیم یا None
        """
        signal = await db.select_one("signals", {
            "id": decision_id,
            "user_id": user_id
        })

        return signal

    def _build_decision_input(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
        user_id: str,
        user_settings: Optional[Dict[str, Any]] = None
    ) -> DecisionInput:
        """
        ساخت DecisionInput از داده‌ها

        Args:
            symbol: نماد
            timeframe: تایم‌فریم
            market_data: داده بازار
            user_id: شناسه کاربر
            user_settings: تنظیمات کاربر

        Returns:
            DecisionInput
        """
        # استخراج SMC Context
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

        # استخراج Price Action Context
        pa_data = market_data.get("price_action", {})
        pa_context = PriceActionContext(
            direction=DecisionDirection(pa_data.get("direction", "neutral")),
            direction_score=pa_data.get("direction_score", 0),
            patterns=pa_data.get("patterns", []),
            candle_strength=pa_data.get("candle_strength", "none") if isinstance(pa_data.get("candle_strength"), str) else "none"
        )

        # Session Context
        session_data = market_data.get("session", {})
        session_context = SessionContext(
            current_session=SessionType(session_data.get("current_session", "closed")),
            killzone_active=session_data.get("killzone_active", False),
            killzone_name=session_data.get("killzone_name"),
            session_score=session_data.get("session_score", 0),
            session_overlap=session_data.get("session_overlap", False)
        )

        # Liquidity Context
        liq_data = market_data.get("liquidity", {})
        liquidity_context = LiquidityContext(
            state=LiquidityState(liq_data.get("state", "none")),
            buy_side_liquidity=liq_data.get("buy_side", []),
            sell_side_liquidity=liq_data.get("sell_side", []),
            sweep_score=liq_data.get("sweep_score", 0)
        )

        # Volatility Context
        vol_data = market_data.get("volatility", {})
        volatility_context = VolatilityContext(
            atr=vol_data.get("atr", 0.0),
            atr_percentile=vol_data.get("atr_percentile", 0),
            volatility_level=RiskLevel(vol_data.get("volatility_level", "medium")),
            spread=vol_data.get("spread", 0.0),
            spread_percentile=vol_data.get("spread_percentile", 0)
        )

        # MTF Context
        mtf_data = market_data.get("mtf", {})
        mtf_context = MultiTimeframeContext(
            higher_timeframe_trend=MarketTrend(mtf_data.get("htf_trend", "ranging")),
            htf_alignment=mtf_data.get("htf_alignment", False),
            htf_score=mtf_data.get("htf_score", 0),
            lower_timeframe_entry=mtf_data.get("ltf_entry", False),
            ltf_score=mtf_data.get("ltf_score", 0)
        )

        # Risk Context
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

        # License Context
        license_data = market_data.get("license", {})
        license_context = LicenseContext(
            is_valid=license_data.get("is_valid", True),
            is_expired=license_data.get("is_expired", False),
            license_type=license_data.get("license_type", "trial"),
            allowed_features=license_data.get("allowed_features", []),
            max_devices=license_data.get("max_devices", 1),
            devices_used=license_data.get("devices_used", 0)
        )

        # Symbol Policy
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
            symbol=symbol,
            timeframe=timeframe,
            current_price=market_data.get("current_price", 0.0),
            smc_context=smc_context,
            price_action_context=pa_context,
            mtf_context=mtf_context,
            session_context=session_context,
            liquidity_context=liquidity_context,
            volatility_context=volatility_context,
            risk_context=risk_context,
            license_context=license_context,
            symbol_policy=symbol_policy,
            user_settings=user_settings or {}
        )

    def _output_to_dict(self, output: DecisionOutput) -> Dict[str, Any]:
        """
        تبدیل DecisionOutput به دیکشنری قابل JSON

        Args:
            output: خروجی تصمیم‌گیری

        Returns:
            دیکشنری
        """
        result = {
            "symbol": output.symbol,
            "timeframe": output.timeframe,
            "created_at": output.created_at.isoformat(),
            "decision": output.decision.value,
            "direction": output.direction.value,
            "confidence_score": output.confidence_score,
            "quality_score": output.quality_score,
            "allowed": output.allowed,
            "reason_codes": [r.value for r in output.reason_codes],
            "reasons": output.reasons_persian,
            "blocked_reasons": [r.value for r in output.blocked_reasons],
            "score_breakdown": output.score_breakdown,
            "metadata": output.metadata
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

    async def _save_decision(
        self,
        user_id: str,
        output: DecisionOutput
    ) -> Dict[str, Any]:
        """
        ذخیره تصمیم در دیتابیس

        Args:
            user_id: شناسه کاربر
            output: خروجی تصمیم

        Returns:
            رکورد ذخیره شده
        """
        valid_until = (datetime.utcnow() + timedelta(hours=4)).isoformat()

        signal_data = {
            "user_id": user_id,
            "symbol": output.symbol,
            "timeframe": output.timeframe,
            "direction": output.direction.value,
            "action": output.decision.value,
            "total_score": output.quality_score,
            "entry_price": output.trading_levels.entry_zone if output.trading_levels else None,
            "stop_loss": output.trading_levels.stop_loss if output.trading_levels else None,
            "take_profit_1": output.trading_levels.take_profit_1 if output.trading_levels else None,
            "take_profit_2": output.trading_levels.take_profit_2 if output.trading_levels else None,
            "take_profit_3": output.trading_levels.take_profit_3 if output.trading_levels else None,
            "risk_reward": output.trading_levels.risk_reward_ratio if output.trading_levels else None,
            "reasons": output.reasons_persian,
            "score_breakdown": output.score_breakdown,
            "status": "generated",
            "generated_at": datetime.utcnow().isoformat(),
            "valid_until": valid_until,
            "metadata": output.metadata
        }

        result = await db.insert("signals", signal_data)
        logger.info(f"سیگنال ذخیره شد: {result.get('id')}")

        return result

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        """دریافت از کش"""
        if key in self._cache:
            cached = self._cache[key]
            if (datetime.utcnow() - datetime.fromisoformat(cached["_cached_at"])).total_seconds() < self._cache_ttl:
                return cached
            del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Dict[str, Any]) -> None:
        """تنظیم کش"""
        value["_cached_at"] = datetime.utcnow().isoformat()
        self._cache[key] = value


# نمونه گلوبال
decision_service = DecisionService()
