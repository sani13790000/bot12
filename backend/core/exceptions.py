"""
استثنا‌های سفارشی سیستم

این فایل تمام استثنا‌های اختصاصی سیستم را تعریف می‌کند.
استخدام استثناهای سفارشی باعث مدیریت خطای بهتر می‌شود.
"""

from typing import Optional, Dict, Any


class MT5TradingError(Exception):
    """
    کلاس پایه برای تمام استثناهای سیستم

    تمام استثناهای سفارشی از این کلاس ارث‌بری می‌کنند.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        مقداردهی اولیه

        Args:
            message: پیام خطا
            error_code: کد خطا (اختیاری)
            details: جزئیات اضافی (اختیاری)
        """
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای پاسخ API"""
        return {
            "success": False,
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details
            }
        }


# =====================================================
# خطاهای احراز هویت
# =====================================================
class AuthenticationError(MT5TradingError):
    """خطای احراز هویت"""

    def __init__(self, message: str = "احراز هویت ناموفق"):
        super().__init__(message, "AUTH_FAILED")


class InvalidTokenError(MT5TradingError):
    """توکن نامعتبر"""

    def __init__(self, message: str = "توکن نامعتبر است"):
        super().__init__(message, "INVALID_TOKEN")


class TokenExpiredError(MT5TradingError):
    """توکن منقضی شده"""

    def __init__(self, message: str = "توکن منقضی شده است"):
        super().__init__(message, "TOKEN_EXPIRED")


class PermissionDeniedError(MT5TradingError):
    """دسترسی مجاز نیست"""

    def __init__(self, message: str = "شما دسترسی به این بخش را ندارید"):
        super().__init__(message, "PERMISSION_DENIED")


# =====================================================
# خطاهای لایسنس
# =====================================================
class LicenseError(MT5TradingError):
    """خطای پایه لایسنس"""
    pass


class LicenseNotFoundError(LicenseError):
    """لایسنس یافت نشد"""

    def __init__(self, license_key: str = ""):
        super().__init__(
            f"لایسنس {license_key} یافت نشد.",
            "LICENSE_NOT_FOUND"
        )


class LicenseExpiredError(LicenseError):
    """لایسنس منقضی شده"""

    def __init__(self, expires_at: str = ""):
        super().__init__(
            f"لایسنس شما در {expires_at} منقضی شده است.",
            "LICENSE_EXPIRED",
            {"expires_at": expires_at}
        )


class LicenseRevokedError(LicenseError):
    """لایسنس باطل شده"""

    def __init__(self):
        super().__init__(
            "لایسنس شما باطل شده است.",
            "LICENSE_REVOKED"
        )


class LicenseLimitExceededError(LicenseError):
    """محدودیت لایسنس پر شده"""

    def __init__(self, limit_type: str, limit_value: int):
        super().__init__(
            f"حداکثر {limit_type} ({limit_value}) پر شده است.",
            "LICENSE_LIMIT_EXCEEDED",
            {"limit_type": limit_type, "limit_value": limit_value}
        )


class FeatureNotLicensedError(LicenseError):
    """ویژگی مجاز نیست"""

    def __init__(self, feature: str):
        super().__init__(
            f"دسترسی به {feature} در لایسنس شما فعال نیست.",
            "FEATURE_NOT_LICENSED",
            {"feature": feature}
        )


# =====================================================
# خطاهای معاملات
# =====================================================
class TradingError(MT5TradingError):
    """خطای پایه معاملات"""
    pass


class TradeNotFoundError(TradingError):
    """معامله یافت نشد"""

    def __init__(self, trade_id: str = ""):
        super().__init__(
            f"معامله {trade_id} یافت نشد.",
            "TRADE_NOT_FOUND"
        )


class TradeExecutionError(TradingError):
    """خطای اجرای معامله"""

    def __init__(self, message: str, mt5_code: int = 0):
        super().__init__(
            message,
            "TRADE_EXECUTION_FAILED",
            {"mt5_code": mt5_code}
        )


class RiskLimitExceededError(TradingError):
    """محدودیت ریسک پر شده"""

    def __init__(self, limit_type: str, current: float, max_value: float):
        super().__init__(
            f"{limit_type} از حد عبور کرده است ({current} > {max_value}).",
            "RISK_LIMIT_EXCEEDED",
            {"limit_type": limit_type, "current": current, "max": max_value}
        )


class InsufficientMarginError(TradingError):
    """مارجین کافی نیست"""

    def __init__(self, required: float, available: float):
        super().__init__(
            f"مارجین کافی نیست (نیاز: {required}, موجود: {available}).",
            "INSUFFICIENT_MARGIN",
            {"required": required, "available": available}
        )


# =====================================================
# خطاهای تحلیل
# =====================================================
class AnalysisError(MT5TradingError):
    """خطای پایه تحلیل"""
    pass


class InsufficientDataError(AnalysisError):
    """داده کافی نیست"""

    def __init__(self, required: int, available: int):
        super().__init__(
            f"داده کافی نیست (نیاز: {required} کندل، موجود: {available}).",
            "INSUFFICIENT_DATA"
        )


class InvalidSymbolError(AnalysisError):
    """نماد نامعتبر"""

    def __init__(self, symbol: str):
        super().__init__(
            f"نماد {symbol} پشتیبانی نمی‌شود.",
            "INVALID_SYMBOL"
        )


class InvalidTimeframeError(AnalysisError):
    """تایم‌فریم نامعتبر"""

    def __init__(self, timeframe: str):
        super().__init__(
            f"تایم‌فریم {timeframe} نامعتبر است.",
            "INVALID_TIMEFRAME"
        )


# =====================================================
# خطاهای پایگاه داده
# =====================================================
class DatabaseError(MT5TradingError):
    """خطای پایگاه داده"""

    def __init__(self, message: str = "خطای پایگاه داده"):
        super().__init__(message, "DATABASE_ERROR")


class RecordNotFoundError(DatabaseError):
    """رکورد یافت نشد"""

    def __init__(self, table: str, record_id: str = ""):
        super().__init__(
            f"رکورد {record_id} در جدول {table} یافت نشد.",
            "RECORD_NOT_FOUND"
        )


class DuplicateRecordError(DatabaseError):
    """رکورد تکراری"""

    def __init__(self, table: str, field: str, value: str):
        super().__init__(
            f"رکورد با {field}={value} در جدول {table} قبلاً وجود دارد.",
            "DUPLICATE_RECORD"
        )


# =====================================================
# خطاهای تلگرام
# =====================================================
class TelegramError(MT5TradingError):
    """خطای تلگرام"""

    def __init__(self, message: str = "خطای ارتباط با تلگرام"):
        super().__init__(message, "TELEGRAM_ERROR")


class TelegramNotConfiguredError(TelegramError):
    """تلگرام پیکربندی نشده"""

    def __init__(self):
        super().__init__(
            "ربات تلگرام پیکربندی نشده است.",
            "TELEGRAM_NOT_CONFIGURED"
        )


class TelegramUserNotLinkedError(TelegramError):
    """کاربر به تلگرام متصل نیست"""

    def __init__(self):
        super().__init__(
            "حساب کاربری شما به تلگرام متصل نیست.",
            "TELEGRAM_NOT_LINKED"
        )


# =====================================================
# خطاهای اعتبارسنجی
# =====================================================
class ValidationError(MT5TradingError):
    """خطای اعتبارسنجی"""

    def __init__(self, field: str, message: str):
        super().__init__(
            f"اعتبارسنجی {field}: {message}",
            "VALIDATION_ERROR",
            {"field": field}
        )


class InvalidInputError(MT5TradingError):
    """ورودی نامعتبر"""

    def __init__(self, message: str = "ورودی نامعتبر"):
        super().__init__(message, "INVALID_INPUT")


# =====================================================
# خطاهای سیستم
# =====================================================
class SystemError(MT5TradingError):
    """خطای سیستم"""

    def __init__(self, message: str = "خطای داخلی سیستم"):
        super().__init__(message, "SYSTEM_ERROR")


class ServiceUnavailableError(MT5TradingError):
    """سرویس در دسترس نیست"""

    def __init__(self, service: str):
        super().__init__(
            f"سرویس {service} در حال حاضر در دسترس نیست.",
            "SERVICE_UNAVAILABLE",
            {"service": service}
        )


class RateLimitExceededError(MT5TradingError):
    """محدودیت نرخ"""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"تعداد درخواست‌ها از حد عبور کرد. لطفاً {retry_after} ثانیه espera کنید.",
            "RATE_LIMIT_EXCEEDED",
            {"retry_after": retry_after}
        )
