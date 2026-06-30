"""backend/core/enums.py — Central enum definitions for Galaxy Vast AI.

CONFLICT-FIX-2 (2026-06-25): TrendDirection.UNDEFINED added to match
  decision_engine.TrendDirection.UNDEFINED. Without this, cross-module
  comparison fails with AttributeError.
"""
from __future__ import annotations
from enum import Enum, IntEnum


# ─── Access control ───────────────────────────────────────────────────────────
class PermissionLevel(IntEnum):
    """سطح دسترسی عددی"""
    SUPER_ADMIN = 100      # دسترسی کامل
    ADMIN = 80             # مدیر سیستم
    SUPPORT = 50           # پشتیبانی
    USER = 20              # کاربر عادی
    READONLY = 10          # فقط مشاهده


# ─── Trading directions ───────────────────────────────────────────────────────
class TradeDirection(str, Enum):
    """جهت معامله"""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


# ─── Trend directions ─────────────────────────────────────────────────────────
class TrendDirection(str, Enum):
    """جهت روند"""
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"
    UNDEFINED = "UNDEFINED"


# ─── Signal confidence ────────────────────────────────────────────────────────
class SignalConfidence(str, Enum):
    """سطح اطمینان سیگنال"""
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


# ─── Order status ─────────────────────────────────────────────────────────────
class OrderStatus(str, Enum):
    """وضعیت سفارش"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# ─── Risk modes ─────────────────────────────────────────────────────────────────
class RiskMode(str, Enum):
    """حالت ریسک"""
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


# ─── Fail closed / open ───────────────────────────────────────────────────────
class FailMode(str, Enum):
    """حالت خطا"""
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN = "FAIL_OPEN"


# ─── Agent vote ─────────────────────────────────────────────────────────────────
class AgentVote(str, Enum):
    """رأی عامل"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    ABSTAIN = "ABSTAIN"


# ─── License status ─────────────────────────────────────────────────────────────
class LicenseStatus(str, Enum):
    """وضعیت لایسنس"""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


# ─── Device status ──────────────────────────────────────────────────────────────
class DeviceStatus(str, Enum):
    """وضعیت دستگاه"""
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"
    BLOCKED = "BLOCKED"


# ─── Subscription tier ──────────────────────────────────────────────────────────
class SubscriptionTier(str, Enum):
    """سطح اشتراک"""
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


# ─── Alert severity ─────────────────────────────────────────────────────────────
class AlertSeverity(str, Enum):
    """شدت هشدار"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ─── Environment ────────────────────────────────────────────────────────────────
class Environment(str, Enum):
    """محیط اجرا"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ─── Trading sessions ─────────────────────────────────────────────────────────
class TradingSession(Enum):
    """Forex trading sessions by city."""
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
