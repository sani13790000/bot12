"""
روت‌های تصمیم‌گیری

Endpointهای مربوط به تصمیم‌گیری و سیگنال‌ها.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from ...core.logger import get_logger
from ...core.exceptions import LicenseError
from ...services.decision_service import decision_service
from ...services.signal_service import signal_service
from ...services.license_service import license_service
from .auth import get_current_user

logger = get_logger("api.decision")
router = APIRouter()


# =====================================================
# مدل‌های Pydantic
# =====================================================

class MarketDataRequest(BaseModel):
    """درخواست داده بازار"""
    symbol: str = Field(..., description="نماد معاملاتی")
    timeframe: str = Field(default="H1", description="تایم‌فریم")

    # داده کندل‌ها
    current_price: float = Field(..., description="قیمت فعلی")

    # SMC Data
    smc: Optional[Dict[str, Any]] = Field(default=None, description="داده SMC")

    # Price Action Data
    price_action: Optional[Dict[str, Any]] = Field(default=None, description="داده Price Action")

    # Session Data
    session: Optional[Dict[str, Any]] = Field(default=None, description="داده سشن")

    # Liquidity Data
    liquidity: Optional[Dict[str, Any]] = Field(default=None, description="داده نقدینگی")

    # Volatility Data
    volatility: Optional[Dict[str, Any]] = Field(default=None, description="داده نوسان")

    # Multi-Timeframe Data
    mtf: Optional[Dict[str, Any]] = Field(default=None, description="داده چند تایم‌فریم")

    # Risk Data
    risk: Optional[Dict[str, Any]] = Field(default=None, description="داده ریسک")

    # License Data
    license: Optional[Dict[str, Any]] = Field(default=None, description="داده لایسنس")

    # Symbol Policy
    symbol_policy: Optional[Dict[str, Any]] = Field(default=None, description="سیاست نماد")


class DecisionResponse(BaseModel):
    """پاسخ تصمیم"""
    success: bool
    data: Dict[str, Any]


# =====================================================
# Endpoints
# =====================================================

@router.post("/request", response_model=DecisionResponse)
async def request_decision(
    request: Request,
    data: MarketDataRequest,
    user: dict = Depends(get_current_user)
):
    """
    درخواست تصمیم‌گیری جدید

    این endpoint تحلیل کامل بازار را انجام داده و تصمیم معاملاتی تولید می‌کند.

    ** نیاز به داده بازار **

    خروجی شامل:
    - decision: BUY/SELL/NO_TRADE
    - trading_levels: سطوح ورود، حد ضرر، حد سود
    - quality_score: امتیاز کیفیت
    - confidence_score: امتیاز اعتماد
    - reason_codes: کدهای دلیل تصمیم
    """
    logger.info(f"درخواست تصمیم: {data.symbol} {data.timeframe} توسط {user.get('id')}")

    # بررسی دسترسی
    user_license = await license_service.get_user_license(user.get("id"))
    if user_license:
        license_key = user_license.get("license_key")
        has_feature = await license_service.has_feature(license_key, "auto_trading")
        if not has_feature:
            raise HTTPException(
                status_code=403,
                detail="دسترسی به ویژگی معاملات خودکار مجاز نیست"
            )

    # استخراج IP
    ip_address = request.client.host if request.client else None

    # ساخت market_data
    market_data = data.dict()
    market_data["license"] = market_data.get("license") or {}
    if user_license:
        market_data["license"] = {
            "is_valid": user_license.get("status") == "active",
            "is_expired": False,
            "license_type": user_license.get("license_type"),
            "allowed_features": user_license.get("features", [])
        }

    # درخواست تصمیم
    try:
        result = await decision_service.request_decision(
            symbol=data.symbol,
            timeframe=data.timeframe,
            market_data=market_data,
            user_id=user.get("id"),
            user_settings=user.get("settings", {}),
            ip_address=ip_address
        )

        return {
            "success": True,
            "data": result
        }

    except LicenseError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"خطا در تصمیم‌گیری: {e}")
        raise HTTPException(status_code=500, detail=f"خطا در تصمیم‌گیری: {str(e)}")


@router.get("/latest")
async def get_latest_decisions(
    symbol: Optional[str] = Query(None),
    limit: int = Query(default=10, le=50),
    user: dict = Depends(get_current_user)
):
    """
    دریافت آخرین تصمیم‌ها

    آخرین تصمیم‌های تولید شده برای کاربر را برمی‌گرداند.
    """
    decisions = await decision_service.get_latest_decision(
        user_id=user.get("id"),
        symbol=symbol,
        limit=limit
    )

    return {
        "success": True,
        "data": {
            "decisions": decisions,
            "count": len(decisions)
        }
    }


@router.get("/{decision_id}")
async def get_decision(
    decision_id: str,
    user: dict = Depends(get_current_user)
):
    """
    دریافت یک تصمیم خاص

    جزئیات یک تصمیم خاص را برمی‌گرداند.
    """
    decision = await decision_service.get_decision_by_id(
        decision_id=decision_id,
        user_id=user.get("id")
    )

    if not decision:
        raise HTTPException(status_code=404, detail="تصمیم یافت نشد")

    return {
        "success": True,
        "data": decision
    }


# =====================================================
# Signal Endpoints
# =====================================================

@router.get("/signals/")
async def list_signals(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
    user: dict = Depends(get_current_user)
):
    """
    لیست سیگنال‌ها

    فیلترهای موجود:
    - status: generated, sent, executed, expired
    - symbol: نماد
    - direction: buy, sell
    - min_score: حداقل امتیاز
    """
    result = await signal_service.get_signals(
        user_id=user.get("id"),
        status=status,
        symbol=symbol,
        direction=direction,
        min_score=min_score,
        limit=limit,
        offset=offset
    )

    return {
        "success": True,
        "data": result
    }


@router.get("/signals/active")
async def get_active_signals(
    limit: int = Query(default=10, le=20),
    user: dict = Depends(get_current_user)
):
    """
    دریافت سیگنال‌های فعال

    سیگنال‌هایی که هنوز منقضی نشده و اجرا نشده‌اند.
    """
    result = await signal_service.get_active_signals(
        user_id=user.get("id"),
        limit=limit
    )

    return {
        "success": True,
        "data": result
    }


@router.get("/signals/{signal_id}")
async def get_signal(
    signal_id: str,
    user: dict = Depends(get_current_user)
):
    """
    جزئیات یک سیگنال
    """
    signal = await signal_service.get_signal(
        signal_id=signal_id,
        user_id=user.get("id")
    )

    if not signal:
        raise HTTPException(status_code=404, detail="سیگنال یافت نشد")

    return {
        "success": True,
        "data": signal
    }


@router.post("/signals/{signal_id}/execute")
async def mark_signal_executed(
    signal_id: str,
    execution_price: float,
    execution_type: str = "manual",
    user: dict = Depends(get_current_user)
):
    """
    علامت‌گذاری سیگنال به عنوان اجرا شده
    """
    result = await signal_service.mark_signal_executed(
        signal_id=signal_id,
        user_id=user.get("id"),
        execution_price=execution_price,
        execution_type=execution_type
    )

    if not result:
        raise HTTPException(status_code=404, detail="سیگنال یافت نشد")

    return {
        "success": True,
        "message": "سیگنال به عنوان اجرا شده علامت‌گذاری شد",
        "data": result
    }


@router.get("/signals/stats/summary")
async def get_signal_stats(
    days: int = Query(default=30, le=90),
    user: dict = Depends(get_current_user)
):
    """
    آمار سیگنال‌ها

    آمار و عملکرد سیگنال‌ها در بازه مشخص.
    """
    stats = await signal_service.get_signal_stats(
        user_id=user.get("id"),
        days=days
    )

    return {
        "success": True,
        "data": stats
    }
