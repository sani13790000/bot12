"""backend/core/enums.py — Central enum definitions for Galaxy Vast AI.

CONFLICT-FIX-2 (2026-06-25): TrendDirection.UNDEFINED added to match
  decision_engine.TrendDirection.UNDEFINED. Without this, 
  analysis/__init__.py’s `from .price_action_engine import PriceActionEngine`
  chain breaks the entire test-suite.
”P5-TZ” markers annotate Phase 5 Timezone-aware session helpers.
"""
from __future__ import annotations

from enum import Enum, auto


class TradeDirection(str, Enum):
    BUY     = "BUY"
    SELL    = "SELL"
    NEUTRAL = "NEUTRAL"
    LONG    = "LONG"
    SHORT   = "SHORT"
    FLAT    = "FLAT"


class TrendDirection(str, Enum):
    BULLISH   = "BULLISH"
    BEARISH   = "BEARISH"
    NEUTRAL   = "NEUTRAL"
    SIDEWAYS  = "SIDEWAYS"
    UNDEFINED = "UNDEFINED"


class SignalStrength(str, Enum):
    STRONG    = "STRONG"
    MODERATE  = "MODERATE"
    WEAK      = "WEAK"
    VERY_WEAK = "VERY_WEAK"
    NONE      = "NONE"


class TimeFrame(str, Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    M30 = "M30"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"
    W1  = "W1"
    MN1 = "MN1"


class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class OrderType(str, Enum):
    MARKET      = "MARKET"
    LIMIT       = "LIMIT"
    STOP        = "STOP"
    STOP_LIMIT  = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"
    OPEN      = "OPEN"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    EXPIRED   = "EXPIRED"
    PARTIAL   = "PARTIAL"


class MarketSession(str, Enum):
    """P5-TZ-1: Named trading sessions with UTC-hour boundaries."""
    ASIAN    = "ASIAN"
    LONDON   = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP  = "OVERLAP"
    OFF      = "OFF"
    UNKNOWN  = "UNKNOWN"


class AgentType(str, Enum):
    SMC         = "SMC"
    PRICE_ACTION = "PRICE_ACTION"
    LIQUIDITY   = "LIQUIDITY"
    ML          = "ML"
    NEWS        = "NEWS"
    MULTI       = "MULTI"


class AlertSeverity(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    ERROR    = "ERROR"
    CRITICAL = "CRITICAL"


class BacktestStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"


class LicenseStatus(str, Enum):
    ACTIVE    = "ACTIVE"
    EXPIRED   = "EXPIRED"
    REVOKED   = "REVOKED"
    SUSPENDED = "SUSPENDED"
    TRIAL     = "TRIAL"


class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    STAGING     = "staging"
    PRODUCTION  = "production"


# ── Backwards-compatibility aliases ────────────────────────────────────────
# TradingSession was referenced by 30+ modules but never defined.
# MarketSession is the canonical class; TradingSession is the alias.
TradingSession = MarketSession
