"""
backend/core/enums.py
Galaxy Vast AI - Core Enumerations

All trading enumerations used across the system.
TradingSession added as alias for MarketSession for backward compatibility.
"""
from __future__ import annotations
from enum import Enum


class TradeDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class MarketSession(str, Enum):
    SYDNEY = "SYDNEY"
    TOKYO = "TOKYO"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP_LONDON_NY = "OVERLAP_LONDON_NY"
    OVERLAP_TOKYO_LONDON = "OVERLAP_TOKYO_LONDON"
    CLOSED = "CLOSED"


# Backward-compatibility alias — many modules import TradingSession
TradingSession = MarketSession


class TimeFrame(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"


class SignalStrength(str, Enum):
    VERY_WEAK = "VERY_WEAK"
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AgentType(str, Enum):
    SMC = "SMC"
    PRICE_ACTION = "PRICE_ACTION"
    ML_PREDICTION = "ML_PREDICTION"
    RISK = "RISK"
    SENTIMENT = "SENTIMENT"


class TradeStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SubscriptionPlan(str, Enum):
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"     # normal operation
    OPEN = "OPEN"         # blocking requests
    HALF_OPEN = "HALF_OPEN"  # testing recovery


# Also export State as alias for CircuitBreakerState (backward compat)
State = CircuitBreakerState
