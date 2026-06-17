"""
روت‌های تحلیل بازار

این فایل endpoint های مربوط به تحلیل بازار را تعریف می‌کند.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import numpy as np

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
    """داده بازار — ارسال‌شده از EA یا Dashboard"""
    opens: List[float] = Field(..., min_items=10, description="قیمت‌های باز شدن")
    highs: List[float] = Field(..., min_items=10, description="بالاترین قیمت‌ها")
    lows: List[float] = Field(..., min_items=10, description="پایین‌ترین قیمت‌ها")
    closes: List[float] = Field(..., min_items=10, description="قیمت‌های بسته شدن")
    volumes: Optional[List[float]] = None
    timestamps: Optional[List[int]] = None  # Unix epoch در صورت موجود بودن


class SymbolDataRequest(BaseModel):
    """درخواست با داده نماد — برای endpoint های که به داده نیاز دارند"""
    opens: List[float] = Field(..., min_items=10)
    highs: List[float] = Field(..., min_items=10)
    lows: List[float] = Field(..., min_items=10)
    closes: List[float] = Field(..., min_items=10)
    volumes: Optional[List[float]] = None
    timestamps: Optional[List[int]] = None


# موتورها — singleton
smc_engine = SMCEngine()
pa_engine = PriceActionEngine()
decision_engine = DecisionEngine()


def _build_market_data(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    timestamps: Optional[List[int]] = None
) -> Dict[str, Any]:
    """ساخت dict داده بازار برای ورودی موتورها"""
    times = timestamps if timestamps else list(range(len(opens)))
    return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "times": times}


def _build_candles(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    times: List[int]
) -> List[Dict[str, Any]]:
    """ساخت لیست کندل برای Price Action Engine"""
    return [
        {"open": o, "high": h, "low": l, "close": c, "time": t}
        for o, h, l, c, t in zip(opens, highs, lows, closes, times)
    ]


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

    if len(data.opens) != len(data.highs) or len(data.opens) != len(data.lows) or len(data.opens) != len(data.closes):
        raise HTTPException(status_code=422, detail="طول آرایه‌های OHLC باید یکسان باشد")

    try:
        times = data.timestamps if data.timestamps else list(range(len(data.opens)))

        market_data = _build_market_data(
            data.opens, data.highs, data.lows, data.closes, data.timestamps
        )

        # تحلیل SMC
        smc_result = smc_engine.analyze(request.symbol, market_data)

        # تحلیل Price Action
        candles = _build_candles(data.opens, data.highs, data.lows, data.closes, times)
        pa_result = pa_engine.analyze(
            candles,
            levels={
                "resistances": [
                    smc_result.details.get("structure", {}).get("key_levels", {}).get("last_swing_high", 0)
                ],
                "supports": [
                    smc_result.details.get("structure", {}).get("key_levels", {}).get("last_swing_low", 0)
                ]
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
                "patterns": [
                    {"pattern_name": p.pattern_name, "direction": p.direction}
                    for p in pa_result.patterns
                ]
            },
            liquidity_score=smc_result.details.get("liquidity", {}).get("score", 0),
            liquidity_details={
                "liquidity_swept": smc_result.liquidity_swept,
                "available_buy_side": smc_result.details.get("liquidity", {}).get("available_buy_side", []),
                "available_sell_side": smc_result.details.get("liquidity", {}).get("available_sell_side", [])
            },
            mtf_score=0,
            mtf_alignment={},
            session_score=smc_result.session_score,
            session_details={
                "killzone_active": smc_result.killzone_active,
                "current_session": smc_result.details.get("session", {}).get("current_session")
            },
            volatility_score=0,
            current_price=data.closes[-1] if data.closes else 0
        )

        decision = decision_engine.make_decision(decision_input)

        return {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "current_price": data.closes[-1] if data.closes else None,
                "candle_count": len(data.opens),
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
                    "patterns": [
                        {"name": p.pattern_name, "direction": p.direction, "score": p.score}
                        for p in pa_result.patterns
                    ]
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در تحلیل کامل {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در تحلیل: {str(e)}")


@router.post("/smc/{symbol}")
async def smc_analysis(
    symbol: str,
    data: SymbolDataRequest,
    timeframe: str = Query(default="H1", description="تایم‌فریم")
) -> Dict[str, Any]:
    """
    تحلیل Smart Money Concept

    داده OHLC را در body دریافت می‌کند (از EA یا Dashboard).
    شامل:
    - Market Structure (BOS, CHOCH, MSS)
    - Liquidity
    - Order Blocks
    - FVG
    - Sessions
    """
    logger.info(f"درخواست تحلیل SMC برای {symbol} {timeframe} — {len(data.opens)} کندل")

    if len(data.opens) < 10:
        raise HTTPException(status_code=422, detail="حداقل ۱۰ کندل نیاز است")

    if len(data.opens) != len(data.highs) or len(data.opens) != len(data.lows) or len(data.opens) != len(data.closes):
        raise HTTPException(status_code=422, detail="طول آرایه‌های OHLC باید یکسان باشد")

    try:
        market_data = _build_market_data(
            data.opens, data.highs, data.lows, data.closes, data.timestamps
        )

        smc_result = smc_engine.analyze(symbol, market_data)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_count": len(data.opens),
                "current_price": data.closes[-1],
                "score": smc_result.total_score,
                "trend": smc_result.trend.value,
                "liquidity_swept": smc_result.liquidity_swept,
                "premium_discount": smc_result.premium_discount,
                "killzone_active": smc_result.killzone_active,
                "session_score": smc_result.session_score,
                "details": smc_result.details
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در تحلیل SMC {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در تحلیل SMC: {str(e)}")


@router.post("/price-action/{symbol}")
async def price_action_analysis(
    symbol: str,
    data: SymbolDataRequest,
    timeframe: str = Query(default="H1", description="تایم‌فریم")
) -> Dict[str, Any]:
    """
    تحلیل Price Action

    داده OHLC را در body دریافت می‌کند.
    شامل:
    - الگوهای کندلی (Pin Bar, Engulfing, Fakey, ...)
    - ساختار قیمت
    - اعتماد الگو
    """
    logger.info(f"درخواست تحلیل Price Action برای {symbol} {timeframe} — {len(data.opens)} کندل")

    if len(data.opens) < 5:
        raise HTTPException(status_code=422, detail="حداقل ۵ کندل نیاز است")

    if len(data.opens) != len(data.highs) or len(data.opens) != len(data.lows) or len(data.opens) != len(data.closes):
        raise HTTPException(status_code=422, detail="طول آرایه‌های OHLC باید یکسان باشد")

    try:
        times = data.timestamps if data.timestamps else list(range(len(data.opens)))
        candles = _build_candles(data.opens, data.highs, data.lows, data.closes, times)

        pa_result = pa_engine.analyze(candles, levels={})

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_count": len(data.opens),
                "current_price": data.closes[-1],
                "score": pa_result.total_score,
                "direction": pa_result.direction,
                "confidence": pa_result.confidence,
                "patterns": [
                    {
                        "name": p.pattern_name,
                        "direction": p.direction,
                        "score": p.score,
                        "candle_index": getattr(p, "candle_index", len(candles) - 1)
                    }
                    for p in pa_result.patterns
                ],
                "pattern_count": len(pa_result.patterns)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در تحلیل Price Action {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در تحلیل Price Action: {str(e)}")


@router.post("/score/{symbol}")
async def get_scores(
    symbol: str,
    data: SymbolDataRequest,
    timeframe: str = Query(default="H1")
) -> Dict[str, Any]:
    """
    دریافت امتیازهای تحلیل بدون جزئیات — سبک برای polling سریع
    """
    logger.info(f"درخواست امتیازها برای {symbol} {timeframe}")

    if len(data.opens) < 10:
        raise HTTPException(status_code=422, detail="حداقل ۱۰ کندل نیاز است")

    try:
        times = data.timestamps if data.timestamps else list(range(len(data.opens)))
        market_data = _build_market_data(
            data.opens, data.highs, data.lows, data.closes, data.timestamps
        )
        candles = _build_candles(data.opens, data.highs, data.lows, data.closes, times)

        smc_result = smc_engine.analyze(symbol, market_data)
        pa_result = pa_engine.analyze(candles, levels={})

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timeframe": timeframe,
                "current_price": data.closes[-1],
                "scores": {
                    "smc": smc_result.total_score,
                    "price_action": pa_result.total_score,
                    "liquidity": smc_result.details.get("liquidity", {}).get("score", 0),
                    "session": smc_result.session_score,
                    "total": round((smc_result.total_score + pa_result.total_score) / 2, 1)
                },
                "trend": smc_result.trend.value,
                "direction": pa_result.direction,
                "killzone_active": smc_result.killzone_active
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در محاسبه امتیاز {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در محاسبه امتیاز: {str(e)}")
