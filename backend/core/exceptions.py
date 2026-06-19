"""
backend/core/exceptions.py
Custom exception hierarchy for Galaxy Vast AI Trading Platform.

Fix applied:
- RateLimitExceededError: removed 'espera' (Spanish word) from Persian message
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class GalaxyVastError(Exception):
    """
    Base exception for all Galaxy Vast system errors.
    Replaces MT5TradingError for clearer naming.
    Backward-compatible alias MT5TradingError preserved.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message    = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details    = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to API-compatible dict."""
        return {
            "success": False,
            "error": {
                "code":    self.error_code,
                "message": self.message,
                "details": self.details,
            },
        }


# Backward-compat alias
MT5TradingError = GalaxyVastError


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class AuthenticationError(GalaxyVastError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, "AUTH_FAILED")


class InvalidTokenError(GalaxyVastError):
    def __init__(self, message: str = "Invalid token") -> None:
        super().__init__(message, "INVALID_TOKEN")


class TokenExpiredError(GalaxyVastError):
    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message, "TOKEN_EXPIRED")


class PermissionDeniedError(GalaxyVastError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, "PERMISSION_DENIED")


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------
class LicenseError(GalaxyVastError):
    """Base license error."""


class LicenseNotFoundError(LicenseError):
    def __init__(self, license_key: str = "") -> None:
        super().__init__(f"License '{license_key}' not found.", "LICENSE_NOT_FOUND")


class LicenseExpiredError(LicenseError):
    def __init__(self, expires_at: str = "") -> None:
        super().__init__(
            f"License expired at {expires_at}.",
            "LICENSE_EXPIRED",
            {"expires_at": expires_at},
        )


class LicenseRevokedError(LicenseError):
    def __init__(self) -> None:
        super().__init__("License has been revoked.", "LICENSE_REVOKED")


class LicenseLimitExceededError(LicenseError):
    def __init__(self, limit_type: str, limit_value: int) -> None:
        super().__init__(
            f"License limit exceeded: {limit_type} (max {limit_value}).",
            "LICENSE_LIMIT_EXCEEDED",
            {"limit_type": limit_type, "limit_value": limit_value},
        )


class FeatureNotLicensedError(LicenseError):
    def __init__(self, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is not licensed.",
            "FEATURE_NOT_LICENSED",
            {"feature": feature},
        )


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------
class TradingError(GalaxyVastError):
    """Base trading error."""


class TradeNotFoundError(TradingError):
    def __init__(self, trade_id: str = "") -> None:
        super().__init__(f"Trade '{trade_id}' not found.", "TRADE_NOT_FOUND")


class TradeExecutionError(TradingError):
    def __init__(self, message: str, mt5_code: int = 0) -> None:
        super().__init__(message, "TRADE_EXECUTION_FAILED", {"mt5_code": mt5_code})


class RiskLimitExceededError(TradingError):
    def __init__(self, limit_type: str, current: float, max_value: float) -> None:
        super().__init__(
            f"{limit_type} limit exceeded ({current:.4f} > {max_value:.4f}).",
            "RISK_LIMIT_EXCEEDED",
            {"limit_type": limit_type, "current": current, "max": max_value},
        )


class InsufficientMarginError(TradingError):
    def __init__(self, required: float, available: float) -> None:
        super().__init__(
            f"Insufficient margin (required: {required:.2f}, available: {available:.2f}).",
            "INSUFFICIENT_MARGIN",
            {"required": required, "available": available},
        )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class AnalysisError(GalaxyVastError):
    """Base analysis error."""


class InsufficientDataError(AnalysisError):
    def __init__(self, required: int, available: int) -> None:
        super().__init__(
            f"Insufficient data: need {required} candles, have {available}.",
            "INSUFFICIENT_DATA",
        )


class InvalidSymbolError(AnalysisError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"Symbol '{symbol}' is not supported.", "INVALID_SYMBOL")


class InvalidTimeframeError(AnalysisError):
    def __init__(self, timeframe: str) -> None:
        super().__init__(f"Timeframe '{timeframe}' is invalid.", "INVALID_TIMEFRAME")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class DatabaseError(GalaxyVastError):
    def __init__(self, message: str = "Database error") -> None:
        super().__init__(message, "DATABASE_ERROR")


class RecordNotFoundError(DatabaseError):
    def __init__(self, table: str, record_id: str = "") -> None:
        super().__init__(
            f"Record '{record_id}' not found in table '{table}'.",
            "RECORD_NOT_FOUND",
        )


class DuplicateRecordError(DatabaseError):
    def __init__(self, table: str, field: str, value: str) -> None:
        super().__init__(
            f"Duplicate record in '{table}': {field}={value}.",
            "DUPLICATE_RECORD",
        )


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class TelegramError(GalaxyVastError):
    def __init__(self, message: str = "Telegram communication error") -> None:
        super().__init__(message, "TELEGRAM_ERROR")


class TelegramNotConfiguredError(TelegramError):
    def __init__(self) -> None:
        super().__init__("Telegram bot is not configured.", "TELEGRAM_NOT_CONFIGURED")


class TelegramUserNotLinkedError(TelegramError):
    def __init__(self) -> None:
        super().__init__("Account is not linked to Telegram.", "TELEGRAM_NOT_LINKED")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class ValidationError(GalaxyVastError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"Validation error on '{field}': {message}", "VALIDATION_ERROR", {"field": field})


class InvalidInputError(GalaxyVastError):
    def __init__(self, message: str = "Invalid input") -> None:
        super().__init__(message, "INVALID_INPUT")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class SystemError(GalaxyVastError):  # noqa: A001 (shadows builtin intentionally)
    def __init__(self, message: str = "Internal system error") -> None:
        super().__init__(message, "SYSTEM_ERROR")


class ServiceUnavailableError(GalaxyVastError):
    def __init__(self, service: str) -> None:
        super().__init__(
            f"Service '{service}' is currently unavailable.",
            "SERVICE_UNAVAILABLE",
            {"service": service},
        )


class RateLimitExceededError(GalaxyVastError):
    """
    Fix: removed 'espera' (Spanish word accidentally left in Persian codebase).
    """
    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            f"Request rate exceeded. Please wait {retry_after} seconds and try again.",
            "RATE_LIMIT_EXCEEDED",
            {"retry_after": retry_after},
        )
