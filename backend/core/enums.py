"""backend/core/enums.py -- Central enum definitions for Galaxy Vast AI.

CONFLICT-FIX-2 (2026-06-25): TrendDirection.UNDEFINED added to match
  decision_engine.TrendDirection.UNDEFINED. Without this, cross-module
  comparison fails with AttributeError.
"""
from __future__ import annotations
from enum import Enum, IntEnum


# Access control
class PermissionLevel(IntEnum):
    """Access level (numeric)"""
    SUPER_ADMIN = 100
    ADMIN       = 80
    OPERATOR    = 60
    ANALYST     = 40
    VIEWER      = 20
    GUEST       = 0


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN       = "admin"
    OPERATOR    = "operator"
    ANALYST     = "analyst"
    VIEWER      = "viewer"
    GUEST       = "guest"


# Market
class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketSession(str, Enum):
    LONDON   = "LONDON"
    NEW_YORK = "NEW_YORK"
    TOKYO    = "TOKYO"
    SYDNEY   = "SYDNEY"
    OVERLAP  = "OVERLAP"
    CLOSED   = "CLOSED"


# backward-compat alias
TradingSession = MarketSession


class TrendDirection(str, Enum):
    UP        = "UP"
    DOWN      = "DOWN"
    SIDEWAYS  = "SIDEWAYS"
    UNDEFINED = "UNDEFINED"


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


class SignalType(str, Enum):
    ENTRY  = "ENTRY"
    EXIT   = "EXIT"
    ALERT  = "ALERT"
    INFO   = "INFO"


class OrderType(str, Enum):
    MARKET     = "MARKET"
    LIMIT      = "LIMIT"
    STOP       = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED    = "FILLED"
    PARTIAL   = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    CLOSED    = "CLOSED"
    ERROR     = "ERROR"


class RiskLevel(str, Enum):
    MINIMAL      = "MINIMAL"
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE     = "MODERATE"
    AGGRESSIVE   = "AGGRESSIVE"
    EXTREME      = "EXTREME"


class AlertPriority(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class AnalysisType(str, Enum):
    SMC          = "SMC"
    PRICE_ACTION = "PRICE_ACTION"
    TECHNICAL    = "TECHNICAL"
    FUNDAMENTAL  = "FUNDAMENTAL"
    SENTIMENT    = "SENTIMENT"


class LicenseStatus(str, Enum):
    ACTIVE    = "active"
    EXPIRED   = "expired"
    SUSPENDED = "suspended"
    TRIAL     = "trial"
    INVALID   = "invalid"


class LicensePlan(str, Enum):
    TRIAL      = "trial"
    BASIC      = "basic"
    STANDARD   = "standard"
    ENTERPRISE = "enterprise"


class AgentType(str, Enum):
    SMC          = "smc"
    PRICE_ACTION = "price_action"
    RISK         = "risk"
    ML           = "ml"
    NEWS         = "news"
    LIQUIDITY    = "liquidity"
    SECURITY     = "security"


class BacktestStatus(str, Enum):
    QUEUED     = "QUEUED"
    RUNNING    = "RUNNING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"
