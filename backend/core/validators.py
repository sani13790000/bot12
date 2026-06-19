"""Validation layer for Galaxy Vast AI Trading Platform.

All user-supplied data passes through these validators before
reaching business logic. Centralizes:
- Symbol validation
- Timeframe validation
- Date range validation
- Numeric range guards
- Pagination validation
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_SYMBOLS: frozenset[str] = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY",
    "GBPJPY", "BTCUSD", "ETHUSD", "XAGUSD",
})

ALLOWED_TIMEFRAMES: frozenset[str] = frozenset({
    "M1", "M5", "M15", "M30",
    "H1", "H4", "H12",
    "D1", "W1", "MN1",
})

_SYMBOL_RE = re.compile(r'^[A-Z]{3,10}(USD|EUR|GBP|JPY|CHF|CAD|AUD|NZD)?$')

MAX_PAGE_SIZE = 1000
MAX_DATE_RANGE_DAYS = 365 * 5  # 5 years


# ---------------------------------------------------------------------------
# Helper validators
# ---------------------------------------------------------------------------
def validate_symbol(symbol: str) -> str:
    """Validate and normalize trading symbol."""
    s = symbol.upper().strip()
    if s not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid symbol '{s}'. Allowed: {sorted(ALLOWED_SYMBOLS)}",
        )
    return s


def validate_timeframe(timeframe: str) -> str:
    """Validate timeframe string."""
    tf = timeframe.upper().strip()
    if tf not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid timeframe '{tf}'. Allowed: {sorted(ALLOWED_TIMEFRAMES)}",
        )
    return tf


def validate_pagination(
    page: int = 1,
    page_size: int = 50,
) -> tuple[int, int]:
    """Validate and clamp pagination params."""
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---------------------------------------------------------------------------
# Pydantic models for request bodies
# ---------------------------------------------------------------------------
class SymbolRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=12, examples=["XAUUSD"])
    timeframe: str = Field("H1", examples=["H1"])

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        s = v.upper().strip()
        if s not in ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{s}' not in allowed list")
        return s

    @field_validator("timeframe")
    @classmethod
    def _check_timeframe(cls, v: str) -> str:
        tf = v.upper().strip()
        if tf not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"Timeframe '{tf}' not allowed")
        return tf


class DateRangeRequest(BaseModel):
    start_date: Optional[str] = Field(None, examples=["2024-01-01"])
    end_date: Optional[str] = Field(None, examples=["2024-12-31"])

    @model_validator(mode="after")
    def _check_range(self) -> "DateRangeRequest":
        if self.start_date and self.end_date:
            try:
                s = datetime.strptime(self.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                e = datetime.strptime(self.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError(f"Invalid date format: {exc}") from exc
            if s >= e:
                raise ValueError("start_date must be before end_date")
            delta = (e - s).days
            if delta > MAX_DATE_RANGE_DAYS:
                raise ValueError(f"Date range too large: {delta} days (max {MAX_DATE_RANGE_DAYS})")
        return self


class BacktestRequest(SymbolRequest, DateRangeRequest):
    initial_balance: float = Field(10_000.0, ge=100.0, le=10_000_000.0)
    risk_pct: float = Field(1.0, ge=0.01, le=10.0)
    strategy: str = Field("smc", pattern=r'^[a-z_]+$')
    leverage: float = Field(1.0, ge=1.0, le=500.0)


class RiskRequest(BaseModel):
    account_balance: float = Field(..., ge=0.0, le=100_000_000.0)
    risk_pct: float = Field(1.0, ge=0.01, le=10.0)
    symbol: str = Field("XAUUSD")
    entry_price: float = Field(..., gt=0.0)
    stop_loss: float = Field(..., gt=0.0)

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        s = v.upper().strip()
        if s not in ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{s}' not allowed")
        return s
