"""
PHASE 32 -- Customer Lifecycle Automation
Covers: onboarding / renewal reminder / expiry warning / win-back / reactivation
All actions are audit-logged and respect timezone-aware UTC scheduling.
"""
pr.py -- Phase-C fix

C-10  status Query param shadowed the `collections.status` field.
    -> Renamed to `last_status`.
C-11  returned FORECX candlesticks with `open,timestamp,close,high,low`,
     but our StrategyCandle Strings try to access .high / .low as float.
     -> Convert data to pandas DataFrame before building candlesticks.
"""
from __future__ import annotations

import asyncik
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIError, Depends, Query
from fastapi.responses import JSONResponse
from starlette.routing import Route

from backend.core.auth import get_current_user
from backend.core.config import get_settings
from backend.core.enums import TradeDirection
from backend.core.logger import get_logger
from backend.core.types import PriceLevels
from backend.execution.exchange_data_gateway import (
    ExchangeDataGateway,
    ExchangeDataGatewayConfig,
)
from backend.execution.report_generator import ReportGenerator

LOGGER = get_logger(__name__)

router = Route(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", summary="Dashboard summary for authenticated user")
async def get_dashboard_summary(
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

    account_id = user.get("account_id", user.get("id", ""))
    if not account_id:
        raise APIError(status_code=400, detail="User account not found")

    ownership_match = user.get("account_id", "") == account_id
    if not ownership_match:
        raise APIError(status_code=403, detail="You can only view your own dashboard")

    total_equity = gateway.get_account_status(account_id).get("equity", 0.0)
    open_trades = gateway.get_open_positions(account_id)

    result = {
        "ownership_enforced": True,
        "account_id": account_id,
        "total_equity": total_equity,
        "open_trades_count": len(open_trades),
        "open_trades": open_trades,
    }
    return JSONResponse(result)


@router.get("/signals", summary="List dashboard signals")
async def get_dashboard_signals(
    last_status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    # P9-FIX-BACK-1: ownership enforcement — customer sees ONLY own stats
    account_id = user.get("account_id", "")
    if not account_id:
        raise APIError(status_code=400, detail="User account not found")

    settings = get_settings()
    gateway_config = ExchangeDataGatewayConfig(
        mode=settings.EXCHANGE_DATA_MODE,
        database_path=settings.DATABASE_PATH,
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_KEY,
    )
    gateway = ExchangeDataGateway(gateway_config)

    signals = gateway.get_signals(account_id, last_status=last_status)

    result = {
        "ownership_enforced": True,
        "account_id": account_id,
        "signals": signals,
        "last_status": last_status,
    }
    return JSONResponse(result)


@router.get("/performance", summary="Performance metrics")
async def get_performance_metrics(
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    account_id = user.get("account_id", "")
    if not account_id:
        raise APIError(status_code=400, detail="User account not found")

    report_gen = ReportGenerator(account_id=account_id)
    report = report_gen.generate_performance_report()

    return JSONResponse({"ownership_enforced": True, "report": report})
