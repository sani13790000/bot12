"""
Enum‌های سیستم

این فایل تمام Enumeration‌های مورد استفاده در سیستم را تعریف می‌کند.
استفاده از Enum باعث خوانایی بیشتر و کاهش خطا می‌شود.
"""

from enum import Enum, IntEnum


# =====================================================
# سطوح دسترسی
# =====================================================
class PermissionLevel(IntEnum):
    """
    سطوح دسترسی کاربران

    هر سطح عددی بالاتر از سطوح پایین‌تر دسترسی دارد.
    """
    SUPER_ADMIN = 100      # دسترسی کامل
    ADMIN = 80             # مدیریت کاربران
    TRADER = 60            # معامله‌گر حرفه‌ای
    USER = 40              # کاربر عادی
    GUEST = 20             # مهمان
    BANNED = 0             # مسدود شده


# =====================================================
# وضعیت کاربر
# =====================================================
class UserStatus(str, Enum):
    """وضعیت حساب کاربری"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    DELETED = "deleted"


class UserRole(str, Enum):
    """نقش کاربر"""
    USER = "user"
    TRADER = "trader"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# =====================================================
# لایسنس
# =====================================================
class LicenseType(str, Enum):
    """نوع لایسنس"""
    TRIAL = "trial"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    LIFETIME = "lifetime"
    DEVELOPER = "developer"


class LicenseStatus(str, Enum):
    """وضعیت لایسنس"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class LicenseFeature(str, Enum):
    """کدهای ویژگی‌های لایسنس"""
    # موتورهای تحلیل
    SMC_ENGINE = "smc_engine"
    PRICE_ACTION_ENGINE = "price_action_engine"
    DECISION_ENGINE = "decision_engine"

    # تحلیل پیشرفته
    MULTI_TIMEFRAME = "multi_timeframe"
    KILLZONE_ALERTS = "killzone_alerts"
    LIQUIDITY_VIZ = "liquidity_visualization"
    ORDERBLOCK_VIZ = "orderblock_visualization"
    FVG_VIZ = "fvg_visualization"

    # مدیریت
    RISK_MANAGER = "risk_manager"
    CUSTOM_STRATEGIES = "custom_strategies"

    # ارتباطات
    TELEGRAM_BOT = "telegram_bot"
    DASHBOARD = "dashboard"

    # API
    API_ACCESS = "api_access"


# =====================================================
# معاملات
# =====================================================
class TradeDirection(str, Enum):
    """جهت معامله"""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class TradeType(str, Enum):
    """نوع معامله"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TradeStatus(str, Enum):
    """وضعیت معامله"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CloseReason(str, Enum):
    """دلیل بسته شدن معامله"""
    MANUAL = "manual"
    SL = "sl"
    TP = "tp"
    TRAILING_STOP = "trailing_stop"
    STOP_OUT = "stop_out"
    SIGNAL_REVERSAL = "signal_reversal"
    TIMEOUT = "timeout"


# =====================================================
# سیگنال
# =====================================================
class SignalType(str, Enum):
    """نوع سیگنال"""
    ENTRY = "entry"
    EXIT = "exit"
    CLOSE = "close"
    MODIFY = "modify"


class SignalStrength(str, Enum):
    """قدرت سیگنال"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class SignalStatus(str, Enum):
    """وضعیت سیگنال"""
    GENERATED = "generated"
    SENT = "sent"
    EXECUTED = "executed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# =====================================================
# ساختار بازار (Smart Money)
# =====================================================
class MarketStructure(str, Enum):
    """نوع رویداد ساختار بازار"""
    BOS = "bos"                  # Break of Structure
    CHOCH = "choch"              # Change of Character
    MSS = "mss"                  # Market Structure Shift
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


class BlockType(str, Enum):
    """نوع بلاک"""
    ORDER_BLOCK = "order_block"
    MITIGATION_BLOCK = "mitigation_block"
    BREAKER_BLOCK = "breaker_block"
    REJECTION_BLOCK = "rejection_block"


class BlockStatus(str, Enum):
    """وضعیت بلاک"""
    ACTIVE = "active"
    TESTED = "tested"
    MITIGATED = "mitigated"
    BROKEN = "broken"
    EXPIRED = "expired"


class FVGType(str, Enum):
    """نوع Fair Value Gap"""
    BULLISH = "bullish_fvg"
    BEARISH = "bearish_fvg"
    IFVG = "ifvg"


class LiquidityType(str, Enum):
    """نوع نقدینگی"""
    BUY_SIDE = "buy_side_liq"
    SELL_SIDE = "sell_side_liq"
    INTERNAL = "internal_liq"
    EXTERNAL = "external_liq"
    SESSION = "session_liq"
    EQUIDISTANT = "equidistant_liq"


# =====================================================
# سشن‌های معاملاتی
# =====================================================
class TradingSession(str, Enum):
    """سشن‌های معاملاتی"""
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"


class SessionState(str, Enum):
    """وضعیت سشن"""
    INACTIVE = "inactive"
    PRE_OPEN = "pre_open"
    OPEN = "open"
    KILLZONE = "killzone"
    CLOSING = "closing"


# =====================================================
# تحلیل و امتیازدهی
# =====================================================
class TrendDirection(str, Enum):
    """جهت روند"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    RANGING = "ranging"


class TradeQuality(str, Enum):
    """کیفیت معامله"""
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    WEAK = "weak"
    REJECTED = "rejected"


class Confidence(str, Enum):
    """سطح اعتماد"""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NONE = "none"


class Decision(str, Enum):
    """تصمیم نهایی"""
    NO_TRADE = "no_trade"
    BUY = "buy"
    SELL = "sell"


# =====================================================
# لاگ
# =====================================================
class LogLevel(str, Enum):
    """سطح لاگ"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    """نوع فعالیت"""
    # احراز هویت
    LOGIN = "login"
    LOGOUT = "logout"
    REGISTER = "register"

    # معاملات
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    TRADE_MODIFY = "trade_modify"

    # سیگنال
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_EXECUTED = "signal_executed"

    # لایسنس
    LICENSE_ACTIVATED = "license_activated"
    LICENSE_VALIDATED = "license_validated"

    # تنظیمات
    SETTINGS_CHANGED = "settings_changed"


# =====================================================
# تایم‌فریم
# =====================================================
class TimeFrame(str, Enum):
    """تایم‌فریم‌های پشتیبانی شده"""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
