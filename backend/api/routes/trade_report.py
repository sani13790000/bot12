"""
روت‌های گزارش معاملات

Endpointهای ثبت و مدیریت گزارش‌های معاملاتی از MT5.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from ...core.logger import get_logger
from ...services.trade_service import trade_service
from .auth import get_current_user

logger = get_logger("api.trades")
router = APIRouter()


# =====================================================
# مدل‌های Pydantic
# =====================================================

class TradeReportRequest(BaseModel):
    """درخواست گزارش معامله"""
    symbol: str = Field(..., description="نماد")
    direction: str = Field(..., description="جهت: buy یا sell")
    entry_price: float = Field(..., description="قیمت ورود")
    exit_price: Optional[float] = Field(default=None, description="قیمت خروج")
    stop_loss: Optional[float] = Field(default=None, description="حد ضرر")
    take_profit: Optional[float] = Field(default=None, description="حد سود")
    lot_size: float = Field(default=0.01, description="حجم")
    open_time: Optional[str] = Field(default=None, description="زمان ورود")
    close_time: Optional[str] = Field(default=None, description="زمان خروج")
    profit_money: Optional[float] = Field(default=None, description="سود/ضرر (پول)")
    profit_pips: Optional[float] = Field(default=None, description="سود/ضرر (پیپ)")
    signal_id: Optional[str] = Field(default=None, description="شناسه سیگنال مرتبط")
    notes: Optional[str] = Field(default=None, description="یادداشت")


class CloseTradeRequest(BaseModel):
    """درخواست بستن معامله"""
    exit_price: float = Field(..., description="قیمت خروج")
    close_reason: str = Field(default="manual", description="دلیل بستن")
    profit_money: Optional[float] = Field(default=None, description="سود/ضرر")


# =====================================================
# Endpoints
# =====================================================

@router.get("/")
async def list_trades(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
    user: dict = Depends(get_current_user)
):
    """
    لیست معاملات

    فیلترهای موجود:
    - status: open, closed
    - symbol: نماد
    - direction: buy, sell
    - from_date: از تاریخ (ISO format)
    - to_date: تا تاریخ (ISO format)
    """
    result = await trade_service.get_trades(
        user_id=user.get("id"),
        status=status,
        symbol=symbol,
        direction=direction,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset
    )

    return {
        "success": True,
        "data": result
    }


@router.get("/open")
async def get_open_positions(user: dict = Depends(get_current_user)):
    """
    دریافت معاملات باز
    """
    result = await trade_service.get_open_positions(user_id=user.get("id"))

    return {
        "success": True,
        "data": result
    }


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    user: dict = Depends(get_current_user)
):
    """
    جزئیات یک معامله
    """
    trade = await trade_service.get_trade(
        trade_id=trade_id,
        user_id=user.get("id")
    )

    if not trade:
        raise HTTPException(status_code=404, detail="معامله یافت نشد")

    return {
        "success": True,
        "data": trade
    }


@router.post("/report")
async def report_trade(
    request: Request,
    data: TradeReportRequest,
    user: dict = Depends(get_current_user)
):
    """
    ثبت گزارش معامله

    برای ثبت معامله از MT5 EA یا گزارش دستی.
    """
    logger.info(
        f"گزارش معامله: {data.symbol} {data.direction} "
        f"توسط {user.get('id')}"
    )

    ip_address = request.client.host if request.client else None

    result = await trade_service.report_trade(
        user_id=user.get("id"),
        symbol=data.symbol,
        direction=data.direction,
        entry_price=data.entry_price,
        exit_price=data.exit_price,
        stop_loss=data.stop_loss,
        take_profit=data.take_profit,
        lot_size=data.lot_size,
        open_time=data.open_time,
        close_time=data.close_time,
        profit_money=data.profit_money,
        profit_pips=data.profit_pips,
        signal_id=data.signal_id,
        notes=data.notes,
        ip_address=ip_address
    )

    return {
        "success": True,
        "message": "معامله ثبت شد",
        "data": result
    }


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    request: Request,
    data: CloseTradeRequest,
    user: dict = Depends(get_current_user)
):
    """
    بستن یک معامله
    """
    logger.info(f"درخواست بستن معامله {trade_id}")

    ip_address = request.client.host if request.client else None

    result = await trade_service.close_trade(
        trade_id=trade_id,
        user_id=user.get("id"),
        exit_price=data.exit_price,
        close_reason=data.close_reason,
        profit_money=data.profit_money,
        ip_address=ip_address
    )

    if not result:
        raise HTTPException(status_code=404, detail="معامله یافت نشد یا بسته شده")

    return {
        "success": True,
        "message": "معامله بسته شد",
        "data": result
    }


@router.post("/close-all")
async def close_all_trades(
    request: Request,
    direction: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    بستن همه معاملات
    """
    logger.info(f"درخواست بستن همه معاملات")

    ip_address = request.client.host if request.client else None

    result = await trade_service.close_all_trades(
        user_id=user.get("id"),
        direction=direction,
        ip_address=ip_address
    )

    return {
        "success": True,
        "data": result
    }


@router.get("/stats/summary")
async def get_trade_stats(
    days: int = Query(default=30, le=90),
    user: dict = Depends(get_current_user)
):
    """
    آمار معاملات
    """
    stats = await trade_service.get_trade_stats(
        user_id=user.get("id"),
        days=days
    )

    return {
        "success": True,
        "data": stats
    }


@router.get("/stats/daily")
async def get_daily_breakdown(
    days: int = Query(default=7, le=30),
    user: dict = Depends(get_current_user)
):
    """
    تفکیک روزانه
    """
    breakdown = await trade_service.get_daily_breakdown(
        user_id=user.get("id"),
        days=days
    )

    return {
        "success": True,
        "data": {
            "daily_breakdown": breakdown,
            "period_days": days
        }
    }
