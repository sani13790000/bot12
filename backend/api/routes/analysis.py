"""
=====================================================================
مسیرهای API تحلیل بازار - Production Ready
فایل: backend/api/routes/analysis.py

توضیح:
    این ماژول تمام endpoint های مربوط به تحلیل بازار را تعریف می‌کند.
    شامل: SMC، Price Action، Decision و Score

نقشه endpoint ها:
    POST /api/v1/analysis/smc/{symbol}            - تحلیل SMC
    POST /api/v1/analysis/price-action/{symbol}   - تحلیل Price Action
    POST /api/v1/analysis/full                    - تحلیل کامل ترکیبی
    POST /api/v1/analysis/score/{symbol}          - امتیاز سریع
    POST /api/v1/analysis/decision/{symbol}       - تصمیم نهایی Decision Engine

نویسنده: MT5 Trading Team
نسخه: 2.0.0
=====================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timezone

from ...core.config import settings
from ...analysis.smc_engine import SMCEngine
from ...analysis.price_action_engine import PriceActionEngine
from ...analysis.decision_engine import (
    DecisionEngine, DecisionInput, SMCContext, PriceActionContext,
    SessionContext, RiskContext, VolatilityContext, MultiTimeframeContext,
    LiquidityContext, SymbolPolicy, LicenseContext
)
from ...analysis.smc_scoring import SMCScoring
from ...services.session_service import SessionService
from ...core.enums import (
    DecisionAction, MarketTrend, DecisionDirection,
    SessionType, LiquidityState, RiskLevel
)

logger = logging.getLogger(__name__)
router = APIRouter()

# نمونه‌های singleton از موتورها
_smc_engine = SMCEngine()
_pa_engine = PriceActionEngine()
_decision_engine = DecisionEngine()
_smc_scoring = SMCScoring()
_session_service = SessionService()


# ─────────────────────────────────────────────
# مدل‌های Pydantic برای ورودی و خروجی
# ─────────────────────────────────────────────

class CandleData(BaseModel):
    """داده یک کندل OHLCV"""
    time: int = Field(..., description="تایم‌استمپ یونیکس")
    open: float = Field(..., gt=0, description="قیمت باز شدن")
    high: float = Field(..., gt=0, description="قیمت بالا")
    low: float = Field(..., gt=0, description="قیمت پایین")
    close: float = Field(..., gt=0, description="قیمت بسته شدن")
    volume: float = Field(default=0.0, ge=0, description="حجم معامله")
    tick_volume: int = Field(default=0, ge=0, description="تعداد تیک")
    spread: int = Field(default=0, ge=0, description="اسپرد در پوینت")

    @validator("high")
    def high_must_be_above_low(cls, v, values):
        if "low" in values and v < values["low"]:
            raise ValueError("قیمت high باید از low بزرگ‌تر باشد")
        return v


class SymbolDataRequest(BaseModel):
    """درخواست تحلیل برای یک نماد"""
    candles: List[CandleData] = Field(..., min_items=50, description="لیست کندل‌ها (حداقل ۵۰)")
    timeframe: str = Field(default="H1", description="تایم‌فریم: M1, M5, M15, M30, H1, H4, D1, W1")
    symbol: Optional[str] = Field(default=None, description="نام نماد (اختیاری، از URL گرفته می‌شود)")
    spread_points: int = Field(default=10, ge=0, le=500, description="اسپرد فعلی به پوینت")
    account_balance: Optional[float] = Field(default=None, gt=0, description="موجودی حساب")
    max_risk_percent: float = Field(default=1.0, gt=0, le=10, description="حداکثر ریسک درصدی")

    class Config:
        json_schema_extra = {
            "example": {
                "candles": [{"time": 1718668000, "open": 1.08500, "high": 1.08650,
                              "low": 1.08400, "close": 1.08580, "volume": 1250.0,
                              "tick_volume": 3400, "spread": 8}],
                "timeframe": "H1",
                "spread_points": 10,
                "account_balance": 10000.0,
                "max_risk_percent": 1.0
            }
        }


class DecisionRequest(BaseModel):
    """درخواست کامل برای Decision Engine"""
    # داده تایم‌فریم اصلی
    candles: List[CandleData] = Field(..., min_items=50, description="کندل‌های تایم‌فریم اصلی")
    timeframe: str = Field(default="H1", description="تایم‌فریم اصلی")

    # داده‌های Multi-Timeframe (اختیاری)
    candles_htf: Optional[List[CandleData]] = Field(default=None, min_items=20, description="کندل‌های HTF")
    timeframe_htf: Optional[str] = Field(default=None, description="تایم‌فریم بالا: H4, D1")
    candles_ltf: Optional[List[CandleData]] = Field(default=None, min_items=20, description="کندل‌های LTF")
    timeframe_ltf: Optional[str] = Field(default=None, description="تایم‌فریم پایین: M15, M30")

    # تنظیمات ریسک
    account_balance: float = Field(default=10000.0, gt=0, description="موجودی حساب")
    max_risk_percent: float = Field(default=1.0, gt=0, le=10, description="حداکثر ریسک درصدی")
    spread_points: int = Field(default=10, ge=0, le=500, description="اسپرد فعلی")
    max_spread_points: int = Field(default=30, ge=0, le=500, description="حداکثر اسپرد مجاز")

    # تنظیمات لایسنس
    license_key: Optional[str] = Field(default=None, description="کلید لایسنس (اختیاری)")
    account_number: Optional[int] = Field(default=None, description="شماره حساب MT5")

    # سیاست نماد
    allowed_symbols: Optional[List[str]] = Field(default=None, description="نمادهای مجاز")
    min_score_to_trade: float = Field(default=65.0, ge=0, le=100, description="حداقل امتیاز برای ورود")


# ─────────────────────────────────────────────
# توابع کمکی
# ─────────────────────────────────────────────

def _build_market_data(symbol: str, request: SymbolDataRequest) -> Dict[str, Any]:
    """ساخت دیکشنری داده بازار از درخواست ورودی"""
    candles = [
        {
            "time": c.time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "tick_volume": c.tick_volume,
            "spread": c.spread
        }
        for c in request.candles
    ]
    return {
        "symbol": symbol,
        "timeframe": request.timeframe,
        "candles": candles,
        "spread_points": request.spread_points,
        "account_balance": request.account_balance,
        "max_risk_percent": request.max_risk_percent,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def _build_candles_list(candle_data: Optional[List[CandleData]]) -> Optional[List[Dict]]:
    """تبدیل لیست CandleData به لیست dict"""
    if candle_data is None:
        return None
    return [
        {"time": c.time, "open": c.open, "high": c.high,
         "low": c.low, "close": c.close, "volume": c.volume,
         "tick_volume": c.tick_volume, "spread": c.spread}
        for c in candle_data
    ]


# ─────────────────────────────────────────────
# Endpoint ها
# ─────────────────────────────────────────────

@router.post(
    "/smc/{symbol}",
    summary="تحلیل Smart Money Concept",
    description="تحلیل کامل SMC شامل: Order Block، FVG، BOS، CHOCH، Liquidity، Kill Zones"
)
async def smc_analysis(symbol: str, request: SymbolDataRequest):
    """
    تحلیل SMC برای نماد مشخص

    ورودی: کندل‌های OHLCV + تنظیمات
    خروجی: نتایج کامل SMC با امتیازدهی
    """
    try:
        market_data = _build_market_data(symbol, request)
        result = _smc_engine.analyze(market_data)
        scored = _smc_scoring.score(result)
        return {
            "success": True,
            "symbol": symbol,
            "timeframe": request.timeframe,
            "candles_count": len(request.candles),
            "analysis": result,
            "scoring": scored,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"خطا در تحلیل SMC نماد {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطا در تحلیل SMC")


@router.post(
    "/price-action/{symbol}",
    summary="تحلیل Price Action",
    description="تشخیص الگوهای پرایس اکشن: Pin Bar، Engulfing، Inside Bar و ۱۱ الگوی دیگر"
)
async def price_action_analysis(symbol: str, request: SymbolDataRequest):
    """
    تحلیل Price Action برای نماد مشخص

    ورودی: کندل‌های OHLCV
    خروجی: الگوهای شناسایی‌شده با امتیاز
    """
    try:
        market_data = _build_market_data(symbol, request)
        result = _pa_engine.analyze(market_data)
        return {
            "success": True,
            "symbol": symbol,
            "timeframe": request.timeframe,
            "candles_count": len(request.candles),
            "patterns": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"خطا در تحلیل Price Action نماد {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطا در تحلیل Price Action")


@router.post(
    "/full",
    summary="تحلیل کامل ترکیبی",
    description="اجرای همزمان SMC + Price Action + Session روی یک نماد"
)
async def full_analysis(request: SymbolDataRequest):
    """
    تحلیل کامل شامل SMC + PA + Session

    ورودی: کندل‌های OHLCV + نماد
    خروجی: ترکیب نتایج همه موتورها
    """
    try:
        symbol = request.symbol or "UNKNOWN"
        market_data = _build_market_data(symbol, request)

        smc_result = _smc_engine.analyze(market_data)
        smc_scored = _smc_scoring.score(smc_result)
        pa_result = _pa_engine.analyze(market_data)
        session_info = _session_service.get_current_session()

        return {
            "success": True,
            "symbol": symbol,
            "timeframe": request.timeframe,
            "candles_count": len(request.candles),
            "smc": {"analysis": smc_result, "scoring": smc_scored},
            "price_action": pa_result,
            "session": {
                "session_type": session_info.session_type.value,
                "kill_zone": session_info.kill_zone.value,
                "can_trade": session_info.can_trade,
                "session_score": session_info.session_score,
                "is_overlap": session_info.is_overlap,
                "is_kill_zone": session_info.is_kill_zone
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"خطا در تحلیل کامل: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطا در تحلیل کامل")


@router.post(
    "/score/{symbol}",
    summary="امتیاز سریع",
    description="دریافت امتیاز ترکیبی سریع بدون جزئیات کامل تحلیل"
)
async def quick_score(symbol: str, request: SymbolDataRequest):
    """
    امتیاز سریع برای polling سریع از MQL5

    ورودی: حداقل کندل‌های لازم
    خروجی: امتیاز ترکیبی + جهت پیشنهادی
    """
    try:
        market_data = _build_market_data(symbol, request)
        smc_result = _smc_engine.analyze(market_data)
        smc_scored = _smc_scoring.score(smc_result)
        pa_result = _pa_engine.analyze(market_data)
        session_info = _session_service.get_current_session()

        smc_score = smc_scored.get("total_score", 0.0) if isinstance(smc_scored, dict) else 0.0
        pa_score = pa_result.get("total_score", 0.0) if isinstance(pa_result, dict) else 0.0
        session_score = session_info.session_score

        combined_score = (smc_score * 0.5) + (pa_score * 0.3) + (session_score * 0.2)

        return {
            "success": True,
            "symbol": symbol,
            "timeframe": request.timeframe,
            "smc_score": round(smc_score, 2),
            "pa_score": round(pa_score, 2),
            "session_score": round(session_score, 2),
            "combined_score": round(combined_score, 2),
            "can_trade_session": session_info.can_trade,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"خطا در امتیاز سریع نماد {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطا در محاسبه امتیاز")


@router.post(
    "/decision/{symbol}",
    summary="تصمیم نهایی Decision Engine",
    description=(
        "اجرای کامل pipeline چندمرحله‌ای Decision Engine:\n"
        "مرحله ۱: فیلتر اولیه (نماد، اسپرد، ساعت)\n"
        "مرحله ۲: تحلیل Multi-Timeframe\n"
        "مرحله ۳: امتیازدهی SMC\n"
        "مرحله ۴: امتیازدهی Price Action\n"
        "مرحله ۵: فیلتر ریسک\n"
        "مرحله ۶: تصمیم نهایی BUY / SELL / NO_TRADE"
    )
)
async def decision_analysis(symbol: str, request: DecisionRequest):
    """
    تصمیم نهایی Decision Engine برای نماد مشخص

    این endpoint سبک‌ترین راه برای دریافت تصمیم نهایی است.
    MQL5 DecisionConnector باید به این endpoint متصل شود.

    ورودی: کندل‌های تایم‌فریم اصلی + اختیاری HTF/LTF
    خروجی: BUY / SELL / NO_TRADE + امتیاز + SL/TP پیشنهادی
    """
    try:
        # ساخت داده بازار اصلی
        candles_main = _build_candles_list(request.candles)
        candles_htf = _build_candles_list(request.candles_htf)
        candles_ltf = _build_candles_list(request.candles_ltf)

        # تحلیل SMC
        market_data_main = {
            "symbol": symbol,
            "timeframe": request.timeframe,
            "candles": candles_main,
            "spread_points": request.spread_points
        }
        smc_result = _smc_engine.analyze(market_data_main)
        smc_scored = _smc_scoring.score(smc_result)
        pa_result = _pa_engine.analyze(market_data_main)
        session_info = _session_service.get_current_session()

        # استخراج امتیازها
        smc_score = smc_scored.get("total_score", 0.0) if isinstance(smc_scored, dict) else 0.0
        pa_score = pa_result.get("total_score", 0.0) if isinstance(pa_result, dict) else 0.0
        smc_direction = smc_scored.get("direction", "NEUTRAL") if isinstance(smc_scored, dict) else "NEUTRAL"
        pa_direction = pa_result.get("direction", "NEUTRAL") if isinstance(pa_result, dict) else "NEUTRAL"

        # تحلیل HTF اگر وجود داشته باشد
        htf_trend = "NEUTRAL"
        htf_score = 50.0
        if candles_htf and len(candles_htf) >= 20:
            htf_data = {**market_data_main, "candles": candles_htf, "timeframe": request.timeframe_htf or "H4"}
            htf_smc = _smc_engine.analyze(htf_data)
            htf_scored = _smc_scoring.score(htf_smc)
            htf_trend = htf_scored.get("direction", "NEUTRAL") if isinstance(htf_scored, dict) else "NEUTRAL"
            htf_score = htf_scored.get("total_score", 50.0) if isinstance(htf_scored, dict) else 50.0

        # تحلیل LTF اگر وجود داشته باشد
        ltf_score = 50.0
        if candles_ltf and len(candles_ltf) >= 20:
            ltf_data = {**market_data_main, "candles": candles_ltf, "timeframe": request.timeframe_ltf or "M15"}
            ltf_pa = _pa_engine.analyze(ltf_data)
            ltf_score = ltf_pa.get("total_score", 50.0) if isinstance(ltf_pa, dict) else 50.0

        # ── فیلتر مرحله ۱: اسپرد ──
        if request.spread_points > request.max_spread_points:
            return _no_trade_response(symbol, request.timeframe, "اسپرد بیش از حد مجاز",
                                      smc_score, pa_score, session_info.session_score)

        # ── فیلتر مرحله ۲: سشن ──
        if not session_info.can_trade:
            return _no_trade_response(symbol, request.timeframe,
                                      f"سشن نامناسب: {session_info.session_type.value}",
                                      smc_score, pa_score, session_info.session_score)

        # ── محاسبه امتیاز ترکیبی ──
        combined_score = (
            smc_score   * 0.40 +
            pa_score    * 0.25 +
            htf_score   * 0.20 +
            ltf_score   * 0.05 +
            session_info.session_score * 0.10
        )

        # ── فیلتر مرحله ۳: حداقل امتیاز ──
        if combined_score < request.min_score_to_trade:
            return _no_trade_response(symbol, request.timeframe,
                                      f"امتیاز ترکیبی ناکافی: {combined_score:.1f} < {request.min_score_to_trade}",
                                      smc_score, pa_score, session_info.session_score, combined_score)

        # ── تعیین جهت نهایی ──
        buy_signals = sum(1 for d in [smc_direction, pa_direction, htf_trend] if d in ("BUY", "BULLISH"))
        sell_signals = sum(1 for d in [smc_direction, pa_direction, htf_trend] if d in ("SELL", "BEARISH"))

        if buy_signals > sell_signals and buy_signals >= 2:
            action = "BUY"
        elif sell_signals > buy_signals and sell_signals >= 2:
            action = "SELL"
        else:
            return _no_trade_response(symbol, request.timeframe,
                                      "جهت‌های تحلیل متضاد — بدون تأیید کافی",
                                      smc_score, pa_score, session_info.session_score, combined_score)

        # ── محاسبه SL و TP پیشنهادی ──
        last_candle = candles_main[-1]
        current_price = last_candle["close"]
        atr_approx = _calculate_atr(candles_main, period=14)

        sl_distance = atr_approx * 1.5
        tp_distance = atr_approx * 3.0

        if action == "BUY":
            sl_price = round(current_price - sl_distance, 5)
            tp_price = round(current_price + tp_distance, 5)
        else:
            sl_price = round(current_price + sl_distance, 5)
            tp_price = round(current_price - tp_distance, 5)

        # ── محاسبه Lot Size پیشنهادی ──
        lot_size = 0.01
        if request.account_balance and sl_distance > 0:
            risk_amount = request.account_balance * (request.max_risk_percent / 100.0)
            pip_value = 10.0  # برای EURUSD استاندارد
            lot_size = round(risk_amount / (sl_distance * pip_value * 100000), 2)
            lot_size = max(0.01, min(lot_size, 10.0))

        return {
            "success": True,
            "symbol": symbol,
            "timeframe": request.timeframe,
            "action": action,
            "can_trade": True,
            "scores": {
                "smc_score": round(smc_score, 2),
                "pa_score": round(pa_score, 2),
                "htf_score": round(htf_score, 2),
                "ltf_score": round(ltf_score, 2),
                "session_score": round(session_info.session_score, 2),
                "combined_score": round(combined_score, 2)
            },
            "directions": {
                "smc": smc_direction,
                "price_action": pa_direction,
                "htf_trend": htf_trend
            },
            "trade_params": {
                "entry_price": current_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "sl_pips": round(sl_distance * 10000, 1),
                "tp_pips": round(tp_distance * 10000, 1),
                "suggested_lot": lot_size,
                "risk_reward": round(tp_distance / sl_distance, 2) if sl_distance > 0 else 0
            },
            "session": {
                "session_type": session_info.session_type.value,
                "kill_zone": session_info.kill_zone.value,
                "is_kill_zone": session_info.is_kill_zone,
                "is_overlap": session_info.is_overlap
            },
            "reason": f"تأیید چندجانبه: SMC={smc_direction}, PA={pa_direction}, HTF={htf_trend}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"خطا در Decision Engine نماد {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="خطا در اجرای Decision Engine")


# ─────────────────────────────────────────────
# توابع کمکی داخلی
# ─────────────────────────────────────────────

def _no_trade_response(
    symbol: str,
    timeframe: str,
    reason: str,
    smc_score: float = 0.0,
    pa_score: float = 0.0,
    session_score: float = 0.0,
    combined_score: float = 0.0
) -> Dict[str, Any]:
    """ساخت پاسخ NO_TRADE استاندارد"""
    return {
        "success": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "action": "NO_TRADE",
        "can_trade": False,
        "scores": {
            "smc_score": round(smc_score, 2),
            "pa_score": round(pa_score, 2),
            "session_score": round(session_score, 2),
            "combined_score": round(combined_score, 2)
        },
        "reason": reason,
        "trade_params": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def _calculate_atr(candles: List[Dict], period: int = 14) -> float:
    """محاسبه ATR برای تخمین SL/TP"""
    if len(candles) < period + 1:
        # fallback: میانگین Range کندل‌ها
        ranges = [c["high"] - c["low"] for c in candles]
        return sum(ranges) / len(ranges) if ranges else 0.001

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    recent_trs = true_ranges[-period:]
    return sum(recent_trs) / len(recent_trs)
