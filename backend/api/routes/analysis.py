"""
روت‌های تحلیل بازار

این فایل endpoint های مربوط به تحلیل بازار را تعریف می‌کند.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel

from ...core.logger import get_logger
from ...core.enums import TimeFrame
from ...analysis.smc_engine import SMCEngine
from ...analysis.price_action_engine import PriceActionEngine
from ...analysis.decision_engine import DecisionEngine, DecisionInput

logger = get_logger("api.analysis")
router = APIRouter()


# =====================================================
# Model های Pydantic
# =====================================================

class AnalysisRequest(BaseModel):
    """درخواست تحلیل"""
    symbol: str
    timeframe: str = "H1"
    use_multi_tf: bool = True
    include_price_action: bool = True


class MarketData(BaseModel):
    """داده بازار"""
    opens: list
    highs: list
    lows: list
    closes: list
    volumes: Optional[list] = None


# موتورها
smc_engine = SMCEngine()
pa_engine = PriceActionEngine()
decision_engine = DecisionEngine()


# =====================================================
# Endpoints
# =====================================================

@router.post("/full")
async def full_analysis(
    request: AnalysisRequest,
    data: MarketData
) -> Dict[str, Any]:
    """
    تحلیل کامل بازار

    شامل:
    - Smart Money Concept
    - Price Action
    - تصمیم‌گیری
    """
    logger.info(f"درخواست تحلیل کامل برای {request.symbol} {request.timeframe}")

    try:
        # آماده‌سازی داده
        times = [t for t in range(len(data.opens))]  # placeholder

        market_data = {
            "opens": data.opens,
            "highs": data.highs,
            "lows": data.lows,
            "closes": data.closes,
            "times": times
        }

        # تحلیل SMC
        smc_result = smc_engine.analyze(request.symbol, market_data)

        # تحلیل Price Action
        candles = [
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "time": t
            }
            for o, h, l, c, t in zip(
                data.opens, data.highs, data.lows, data.closes, times
            )
        ]

        pa_result = pa_engine.analyze(
            candles,
            levels={
                "resistances": [smc_result.details.get("structure", {}).get("key_levels", {}).get("last_swing_high", 0)],
                "supports": [smc_result.details.get("structure", {}).get("key_levels", {}).get("last_swing_low", 0)]
            }
        )

        # ساخت DecisionInput
        decision_input = DecisionInput(
            smc_score=smc_result.total_score,
            smc_direction=smc_result.trend.value,
            smc_details={
                "last_event": smc_result.details.get("structure", {}).get("last_event"),
                "liquidity_swept": smc_result.liquidity_swept,
                "key_levels": smc_result.details.get("structure", {}).get("key_levels", {}),
                "premium_discount": smc_result.premium_discount
            },
            price_action_score=pa_result.total_score,
            price_action_direction=pa_result.direction,
            price_action_details={
                "patterns": [{"pattern_name": p.pattern_name, "direction": p.direction}
                            for p in pa_result.patterns]
            },
            liquidity_score=smc_result.details.get("liquidity", {}).get("score", 0),
            liquidity_details={
                "liquidity_swept": smc_result.liquidity_swept,
                "available_buy_side": smc_result.details.get("liquidity", {}).get("available_buy_side", []),
                "available_sell_side": smc_result.details.get("liquidity", {}).get("available_sell_side", [])
            },
            mtf_score=0,  # نیاز به داده چند تایم‌فریم
            mtf_alignment={},
            session_score=smc_result.session_score,
            session_details={
                "killzone_active": smc_result.killzone_active,
                "current_session": smc_result.details.get("session", {}).get("current_session")
            },
            volatility_score=0,
            current_price=data.closes[-1] if data.closes else 0
        )

        # تصمیم‌گیری
        decision = decision_engine.make_decision(decision_input)

        return {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "current_price": data.closes[-1] if data.closes else None,
                "smc": {
                    "score": smc_result.total_score,
                    "trend": smc_result.trend.value,
                    "liquidity_swept": smc_result.liquidity_swept,
                    "premium_discount": smc_result.premium_discount,
                    "details": smc_result.details
                },
                "price_action": {
                    "score": pa_result.total_score,
                    "direction": pa_result.direction,
                    "confidence": pa_result.confidence,
                    "patterns": [{"name": p.pattern_name, "direction": p.direction, "score": p.score}
                                  for p in pa_result.patterns]
                },
                "decision": {
                    "action": decision.decision.value,
                    "quality": decision.quality.value,
                    "confidence": decision.confidence.value,
                    "total_score": decision.total_score,
                    "direction": decision.direction,
                    "reasons": decision.reasons,
                    "suggested_entry": decision.suggested_entry,
                    "suggested_sl": decision.suggested_sl,
                    "suggested_tp": decision.suggested_tp,
                    "risk_reward": decision.risk_reward_ratio
                }
            }
        }

    except Exception as e:
        logger.error(f"خطا در تحلیل: {e}")
        raise HTTPException(status_code=500, detail=f"خطا در تحلیل: {str(e)}")


@router.get("/smc/{symbol}")
async def smc_analysis(
    symbol: str,
    timeframe: str = Query(default="H1", description="تایم‌فریم")
) -> Dict[str, Any]:
    """
    تحلیل Smart Money Concept

    شامل:
    - Market Structure (BOS, CHOCH, MSS)
    - Liquidity
    - Order Blocks
    - FVG
    - Sessions
    """
    logger.info(f"درخواست تحلیل SMC برای {symbol}")

    # اینجا داده بازار واقعی دریافت می‌شود
    # فعلاً placeholder
    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "message": "در حال حاضر داده بازار در دسترس نیست",
            "hint": "لطفاً از endpoint /full با داده بازار استفاده کنید"
        }
    }


@router.get("/price-action/{symbol}")
async def price_action_analysis(
    symbol: str,
    timeframe: str = Query(default="H1", description="تایم‌فریم")
) -> Dict[str, Any]:
    """
    تحلیل Price Action

    شامل:
    - الگوهای کندلی
    - ساختار قیمت
    """
    logger.info(f"درخواست تحلیل Price Action برای {symbol}")

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "message": "لطفاً از endpoint /full با داده بازار استفاده کنید"
        }
    }


@router.get("/score/{symbol}")
async def get_scores(
    symbol: str,
    timeframe: str = Query(default="H1")
) -> Dict[str, Any]:
    """
    دریافت امتیازهای تحلیل بدون جزئیات
    """
    logger.info(f"درخواست امتیازها برای {symbol}")

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "scores": {
                "smc": 0,
                "price_action": 0,
                "liquidity": 0,
                "session": 0,
                "total": 0
            },
            "message": "لطفاً از endpoint /full با داده بازار استفاده کنید"
        }
    }
