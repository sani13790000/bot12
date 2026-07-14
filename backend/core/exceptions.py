"""backend/core/exceptions.py — shared exceptions and error handling."""


class KillSwitchActivatedError(Exception):
    """Raised when kill switch is active and trading attempt is made."""
    pass


class LicenseError(Exception):
    """License-related errors."""
    pass


class PermissionDeniedError(Exception):
    """Permission denied error."""
    pass


class ConfigError(Exception):
    """Configuration error."""
    pass


class ValidationError(Exception):
    """Validation error."""
    pass


class DatabaseError(Exception):
    """Database operation error."""
    pass


class APIError(Exception):
    """API error."""
    pass


class AuthenticationError(Exception):
    """Authentication error."""
    pass


class TimeoutError(Exception):
    """Operation timeout."""
    pass


class PaymentError(Exception):
    """Payment processing error."""
    pass


class WebhookError(Exception):
    """Webhook processing error."""
    pass


class DataError(Exception):
    """Data processing error."""
    pass
