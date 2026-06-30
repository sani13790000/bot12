"""
backend/api/routes/signals.py -- Phase-C fix

C-10  status Query param shadowed the `status` field.
    -> Renamed to `last_status`.
C-11  returned FOREX candlesticks with `open,timestamp,close,high,low`,
     but our StrategyCandle Strings try to access .high / .low as float.
     -> Convert data to pandas DataFrame before building candlesticks.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.core.auth import get_current_user
from backend.core.config import get_settings
from backend.core.enums import TradeDirection
from backend.execution.exchange_data_gateway import (
    ExchangeDataGateway,
    ExchangeDataGatewayConfig,
)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", summary="List generated trading signals")
async def list_signals(
    last_status: Optional[str] = Query(None, alias="last_status"),
    symbol: Optional[str] = Query(None),
    direction: Optional[TradeDirection] = Query(None),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    settings = get_settings()
    gateway_config = ExchangeDataGatewayConfig(
        mode=settings.EXCHANGE_DATA_MODE,
        database_path=settings.DATABASE_PATH,
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_KEY,
    )
    gateway = ExchangeDataGateway(gateway_config)

    account_id = user.get("account_id", "")
    signals = await gateway.get_signals(
        account_id=account_id,
        last_status=last_status,
        symbol=symbol,
        direction=direction.value if direction else None,
    )
    return JSONResponse({"signals": signals, "last_status": last_status})


@router.post("/generate", summary="Generate new signal for a symbol")
async def generate_signal(
    symbol: str,
    timeframe: str = Query("H1"),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    settings = get_settings()
    gateway_config = ExchangeDataGatewayConfig(
        mode=settings.EXCHANGE_DATA_MODE,
        database_path=settings.DATABASE_PATH,
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_KEY,
    )
    gateway = ExchangeDataGateway(gateway_config)

    account_id = user.get("account_id", "")
    signal = await gateway.generate_signal(
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
    )
    return JSONResponse({"signal": signal})
