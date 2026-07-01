"""backend/core/enums.py — Central enum definitions for Galaxy Vast AI."""
from __future__ import annotations
from enum import Enum, IntEnum


class PermissionLevel(IntEnum):
    READ = 10
    TRADE = 20
    ADMIN = 30
    SUPER_ADMIN = 40


class UserStatus(str, Enum):
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    PENDING = 'pending'
    DELETED = 'deleted'


class UserRole(str, Enum):
    VIEWER = 'viewer'
    TRADER = 'trader'
    ADMIN = 'admin'
    SUPER_ADMIN = 'super_admin'


class LicenseType(str, Enum):
    TRIAL = 'trial'
    BASIC = 'basic'
    PRO = 'pro'
    ENTERPRISE = 'enterprise'


class LicenseStatus(str, Enum):
    ACTIVE = 'active'
    EXPIRED = 'expired'
    SUSPENDED = 'suspended'
    REVOKED = 'revoked'


class LicenseFeature(str, Enum):
    BASIC_TRADING = 'basic_trading'
    AI_SIGNALS = 'ai_signals'
    MULTI_ACCOUNT = 'multi_account'
    ADVANCED_RISK = 'advanced_risk'


class TradeDirection(str, Enum):
    BUY = 'buy'
    SELL = 'sell'
    NEUTRAL = 'neutral'


class TradeType(str, Enum):
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'
    STOP_LIMIT = 'stop_limit'


class TradeStatus(str, Enum):
    PENDING = 'pending'
    OPEN = 'open'
    CLOSED = 'closed'
    CANCELLED = 'cancelled'
    FAILED = 'failed'


class SignalStatus(str, Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    TRIGGERED = 'triggered'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'


class SignalDirection(str, Enum):
    BUY = 'buy'
    SELL = 'sell'


class OrderType(str, Enum):
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'
    STOP_LIMIT = 'stop_limit'


class OrderStatus(str, Enum):
    PENDING = 'pending'
    FILLED = 'filled'
    PARTIALLY_FILLED = 'partially_filled'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'


class PositionSide(str, Enum):
    LONG = 'long'
    SHORT = 'short'


class MarketSession(str, Enum):
    SYDNEY = 'sydney'
    TOKYO = 'tokyo'
    LONDON = 'london'
    NEW_YORK = 'new_york'


# Compatibility alias — TradingSession is imported by many modules
TradingSession = MarketSession


class TimeframeCategory(str, Enum):
    SCALP = 'scalp'
    INTRADAY = 'intraday'
    SWING = 'swing'
    POSITION = 'position'


class MarketStructure(str, Enum):
    BULLISH = 'bullish'
    BEARISH = 'bearish'
    RANGING = 'ranging'
    UNDEFINED = 'undefined'


class LiquidityType(str, Enum):
    BSL = 'bsl'
    SSL = 'ssl'
    EQL = 'eql'


class FVGType(str, Enum):
    BULLISH = 'bullish'
    BEARISH = 'bearish'


class TrendDirection(str, Enum):
    UP = 'up'
    DOWN = 'down'
    SIDEWAYS = 'sideways'
    UNDEFINED = 'undefined'


class TradeQuality(str, Enum):
    A_PLUS = 'a_plus'
    A = 'a'
    B = 'b'
    C = 'c'


class ConfidenceLevel(str, Enum):
    VERY_HIGH = 'very_high'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class RiskLevel(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class AlertSeverity(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    INFO = 'info'


class AlertCategory(str, Enum):
    RISK = 'risk'
    PERFORMANCE = 'performance'
    SYSTEM = 'system'
    TRADE = 'trade'


class BacktestStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class HealthStatus(str, Enum):
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'
