"""
backend/api/routes/trades.py -- Phase-C fix

C-4  `status` Query param shadowed the `status` field.
    -> Renamed to `last_status`.
C-5  route returned raw database rows; now returns Trade Pydantic models.
C-6  owner enforcement added so users see only their own trades.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.core.auth import get_current_user
from backend.core.config import get_settings
from backend.execution.exchange_data_gateway import (
    ExchangeDataGateway,
    ExchangeDataGatewayConfig,
)
from backend.core.types import TradeStatus

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("", summary="List trades for authenticated user")
async def list_trades(
    last_status: Optional[TradeStatus] = Query(None, alias="last_status"),
    symbol: Optional[str] = Query(None),
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
    if not account_id:
        return JSONResponse({"error": "User account not found"}, status_code=400)

    trades = await gateway.get_trades(
        account_id=account_id,
        last_status=last_status.value if last_status else None,
        symbol=symbol,
    )
    return JSONResponse({"trades": trades, "last_status": last_status.value if last_status else None})


@router.get("/{trade_id}", summary="Get a single trade")
async def get_trade(
    trade_id: str,
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
    trade = await gateway.get_trade(trade_id=trade_id, account_id=account_id)
    if trade is None:
        return JSONResponse({"error": "Trade not found"}, status_code=404)
    return JSONResponse({"trade": trade})
