"""backend/core/enums.py — Central enum definitions for Galaxy Vast AI Trading Platform."""
from __future__ import annotations

from enum import Enum


class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketSession(str, Enum):
    ASIAN    = "ASIAN"
    EUROPEAN = "EUROPEAN"
    US       = "US"
    OVERLAP  = "OVERLAP"
    CLOSED   = "CLOSED"


# Backward-compat alias used by many modules
TradingSession = MarketSession


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"
    STOP   = "STOP"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"
    OPEN      = "OPEN"
    CLOSED    = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED    = "FAILED"


class RiskLevel(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    CRITICAL = "CRITICAL"


class SignalStrength(str, Enum):
    WEAK   = "WEAK"
    MEDIUM = "MEDIUM"
    STRONG = "STRONG"


class TimeFrame(str, Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    M30 = "M30"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"
    W1  = "W1"


class AgentType(str, Enum):
    TECHNICAL   = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    SENTIMENT   = "SENTIMENT"
    ML          = "ML"
    RISK        = "RISK"


class LicenseStatus(str, Enum):
    ACTIVE    = "ACTIVE"
    EXPIRED   = "EXPIRED"
    REVOKED   = "REVOKED"
    SUSPENDED = "SUSPENDED"
    TRIAL     = "TRIAL"


class NotificationChannel(str, Enum):
    TELEGRAM = "TELEGRAM"
    EMAIL    = "EMAIL"
    WEBHOOK  = "WEBHOOK"


class BacktestStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"


class HealthStatus(str, Enum):
    HEALTHY   = "HEALTHY"
    DEGRADED  = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING     = "staging"
    PRODUCTION  = "production"
