"""backend/core/enums.py — Central enum definitions for Galaxy Vast AI.

CONFLICT-FIX-2 (2026-06-25): TrendDirection.UNDEFINED added to match
  decision_engine.TrendDirection.UNDEFINED. Without this, cross-module
  comparison fails with AttributeError.
"""
from __future__ import annotations
from enum import Enum, IntEnum


# ─── Access control ──────────────────────────────────────────
class PermissionLevel(IntEnum):
    SUPER_ADMIN = 100
    ADMIN = 80
    TRADER = 60
    USER = 40
    GUEST = 20
    BANNED = 0


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    DELETED = "deleted"


class UserRole(str, Enum):
    USER = "user"
    TRADER = "trader"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# ─── License ─────────────────────────────────────────────────────────────────
class LicenseType(str, Enum):
    TRIAL = "trial"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    LIFETIME = "lifetime"
    DEVELOPER = "developer"


class LicenseStatus(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class LicenseFeature(str, Enum):
    # Analysis
    SMC_ENGINE = "smc_engine"
    PRICE_ACTION_ENGINE = "price_action_engine"
    DECISION_ENGINE = "decision_engine"

    # Features
    MULTI_TIMEFRAME = "multi_timeframe"
    KILLZONE_ALERTS = "killzone_alerts"
    LIQUIDITY_VIZ = "liquidity_visualization"
    ORDERBLOCK_VIZ = "orderblock_visualization"
    FVG_VIZ = "fvg_visualization"

    # Risk
    RISK_MANAGER = "risk_manager"
    CUSTOM_STRATEGIES = "custom_strategies"

    # Integrations
    TELEGRAM_BOT = "telegram_bot"
    DASHBOARD = "dashboard"

    # API
    API_ACCESS = "api_access"


# ─── Trading ─────────────────────────────────────────────────────────────────
class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class TradeType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TradeStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PARTIAL = "partial"


class SignalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SignalDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# ─── Analysis ────────────────────────────────────────────────────────────────
class MarketSession(str, Enum):
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP_LONDON_NY = "overlap_london_ny"
    OVERLAP_TOKYO_LONDON = "overlap_tokyo_london"
    CLOSED = "closed"


class TimeframeCategory(str, Enum):
    SCALP = "scalp"
    INTRADAY = "intraday"
    SWING = "swing"
    POSITION = "position"


class MarketStructure(str, Enum):
    BULLISH_BOS = "bullish_bos"
    BEARISH_BOS = "bearish_bos"
    BULLISH_CHOCH = "bullish_choch"
    BEARISH_CHOCH = "bearish_choch"
    RANGING = "ranging"
    UNDEFINED = "undefined"


class LiquidityType(str, Enum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"
    STOP_HUNT = "stop_hunt"


class FVGType(str, Enum):
    BULLISH = "bullish_fvg"
    BEARISH = "bearish_fvg"


# ─── Trend / Direction ───────────────────────────────────────────────────────
class TrendDirection(str, Enum):
    BULLISH   = "bullish"
    BEARISH   = "bearish"
    NEUTRAL   = "neutral"
    RANGING   = "ranging"
    UNDEFINED = "undefined"  # CONFLICT-FIX-2: added for decision_engine compatibility


class TradeQuality(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    LOW = "low"
    POOR = "poor"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


# ─── System ────────────────────────────────────────────────────────────────────
class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    TRADING = "trading"
    RISK = "risk"
    SYSTEM = "system"
    SECURITY = "security"
    PERFORMANCE = "performance"


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ───────────────────────────────────────────────────────────────────────────────
# Backward-compatibility aliases
# Many modules do: from backend.core.enums import TradingSession
TradingSession = MarketSession
