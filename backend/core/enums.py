"""
backend/core/enums.py
Galaxy Vast AI — Core Enumerations

All Enum types used across the platform.
"""
from __future__ import annotations

from enum import Enum


class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"
    STOP   = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"
    OPEN      = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    EXPIRED   = "EXPIRED"


class SignalStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK   = "WEAK"
    NEUTRAL = "NEUTRAL"


class RiskLevel(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    CRITICAL = "critical"


class MarketSession(str, Enum):
    """Forex market session identifier."""
    ASIAN    = "asian"
    LONDON   = "london"
    NEW_YORK = "new_york"
    OVERLAP  = "overlap"
    CLOSED   = "closed"


class AgentType(str, Enum):
    TECHNICAL  = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT  = "sentiment"
    RISK       = "risk"
    ML         = "ml"


class LicensePlan(str, Enum):
    FREE       = "free"
    STARTER    = "starter"
    PRO        = "pro"
    ENTERPRISE = "enterprise"


class TradingMode(str, Enum):
    AUTO      = "auto"
    SEMI_AUTO = "semi_auto"
    MANUAL    = "manual"
    PAPER     = "paper"


class AlertSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class SystemHealth(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN   = "unknown"


# ────────────────────────────────────────────────────────────────────────
# Backward-compatibility aliases
# Many modules do: from backend.core.enums import TradingSession
# ────────────────────────────────────────────────────────────────────────
TradingSession = MarketSession
