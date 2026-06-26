"""
backend/core/exceptions.py
Galaxy Vast AI Trading Platform — Enterprise Exception Hierarchy

All application exceptions carry:
  - error_code: str  (machine-readable, for API responses)
  - http_status: int (HTTP status code mapping)
  - context: dict    (structured diagnostic data)
  - to_dict()        (serializable for API responses)

Retryable vs NonRetryable mix-ins integrate with core/retry.py.
FIX: Resolved MRO error in PredictionError and ModelNotFoundError
PHASE-4: Added InsufficientMarginError, KillSwitchActivatedError,
         DrawdownLimitError, TradingHaltedError
"""
from __future__ import annotations
from typing import Any, Dict, Optional


class AppError(Exception):
    error_code: str = 'APP_ERROR'
    http_status: int = 500

    def __init__(self, message: str, *, error_code: Optional[str] = None,
                 context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context or {}
        if error_code:
            self.error_code = error_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': self.error_code,
            'message': self.message,
            'context': self.context,
            'http_status': self.http_status,
        }


class RetryableError(AppError): pass
class NonRetryableError(AppError): pass


# ── Auth ────────────────────────────────────────────────────────────────────────────────
class AuthError(NonRetryableError):
    error_code = 'AUTH_ERROR'; http_status = 401
class TokenExpiredError(AuthError): error_code = 'TOKEN_EXPIRED'
class TokenInvalidError(AuthError): error_code = 'TOKEN_INVALID'
class InsufficientPermissionsError(NonRetryableError):
    error_code = 'INSUFFICIENT_PERMISSIONS'; http_status = 403
class LicenseError(NonRetryableError):
    error_code = 'LICENSE_ERROR'; http_status = 403


# ── Validation / Config ───────────────────────────────────────────────────────────────
class ValidationError(NonRetryableError):
    error_code = 'VALIDATION_ERROR'; http_status = 422
class ConfigurationError(NonRetryableError):
    error_code = 'CONFIGURATION_ERROR'; http_status = 500


# ── Risk ─────────────────────────────────────────────────────────────────────────────────
class RiskError(AppError):
    error_code = 'RISK_ERROR'; http_status = 500

class RiskGateError(RetryableError, RiskError):
    error_code = 'RISK_GATE_ERROR'

class RiskBlockedError(NonRetryableError, RiskError):
    error_code = 'RISK_BLOCKED'; http_status = 422

class CircuitOpenError(NonRetryableError, RiskError):
    error_code = 'CIRCUIT_OPEN'; http_status = 503

# PHASE-4: Margin errors
class InsufficientMarginError(NonRetryableError, RiskError):
    """Raised when free margin is below the required margin for an order."""
    error_code = 'INSUFFICIENT_MARGIN'; http_status = 422

    def __init__(self, symbol: str = "", required: float = 0.0,
                 available: float = 0.0, margin_level: float = 0.0,
                 **kwargs: Any) -> None:
        msg = (f"Insufficient margin: symbol={symbol} required={required:.2f} "
               f"available={available:.2f} margin_level={margin_level:.1f}%")
        super().__init__(msg, context={
            "symbol": symbol,
            "required_margin": required,
            "available_margin": available,
            "margin_level_pct": margin_level,
        })

# PHASE-4: Kill switch
class KillSwitchActivatedError(NonRetryableError, RiskError):
    """Raised when the emergency kill switch fires."""
    error_code = 'KILL_SWITCH_ACTIVATED'; http_status = 503

    def __init__(self, reason: str = "", equity: float = 0.0,
                 threshold_pct: float = 0.0, **kwargs: Any) -> None:
        msg = f"KILL SWITCH ACTIVATED: {reason} (equity={equity:.2f}, threshold={threshold_pct:.1f}%)"
        super().__init__(msg, context={
            "reason": reason,
            "equity": equity,
            "threshold_pct": threshold_pct,
        })

# PHASE-4: Drawdown
class DrawdownLimitError(NonRetryableError, RiskError):
    """Raised when daily/total drawdown limit is breached."""
    error_code = 'DRAWDOWN_LIMIT'; http_status = 422

    def __init__(self, drawdown_pct: float = 0.0, limit_pct: float = 0.0,
                 period: str = "daily", **kwargs: Any) -> None:
        msg = f"Drawdown limit breached: {drawdown_pct:.2f}% > {limit_pct:.2f}% ({period})"
        super().__init__(msg, context={
            "drawdown_pct": drawdown_pct,
            "limit_pct": limit_pct,
            "period": period,
        })

# PHASE-4: Trading halted
class TradingHaltedError(NonRetryableError, RiskError):
    """Raised when trading is halted."""
    error_code = 'TRADING_HALTED'; http_status = 503

    def __init__(self, reason: str = "", cooldown_remaining_min: float = 0.0,
                 **kwargs: Any) -> None:
        msg = f"Trading halted: {reason}"
        if cooldown_remaining_min > 0:
            msg += f" (cooldown: {cooldown_remaining_min:.0f}min remaining)"
        super().__init__(msg, context={
            "reason": reason,
            "cooldown_remaining_min": cooldown_remaining_min,
        })


# ── Execution ─────────────────────────────────────────────────────────────────────────────────
class ExecutionError(AppError):
    error_code = 'EXECUTION_ERROR'; http_status = 500

class OrderSubmissionError(RetryableError, ExecutionError):
    error_code = 'ORDER_SUBMISSION_ERROR'

    def __init__(self, symbol: str = "", order_id: str = "", *,
                 retcode: int = 0, reason: str = "", **kwargs: Any) -> None:
        msg = (f"Order submission failed: symbol={symbol} order_id={order_id} "
               f"retcode={retcode} reason={reason}")
        super().__init__(msg, context={
            "symbol": symbol,
            "order_id": order_id,
            "retcode": retcode,
            "reason": reason,
        })

class OrderDuplicateError(NonRetryableError, ExecutionError):
    error_code = 'ORDER_DUPLICATE'; http_status = 409
class BrokerConnectionError(RetryableError, ExecutionError):
    error_code = 'BROKER_CONNECTION_ERROR'
class OrderStateError(NonRetryableError, ExecutionError):
    error_code = 'ORDER_STATE_ERROR'
class ReconciliationError(RetryableError, ExecutionError):
    error_code = 'RECONCILIATION_ERROR'


# ── Database ─────────────────────────────────────────────────────────────────────────────────
class DatabaseError(RetryableError):
    error_code = 'DATABASE_ERROR'; http_status = 503
class DatabaseConnectionError(DatabaseError):
    error_code = 'DATABASE_CONNECTION_ERROR'
class QueryError(DatabaseError):
    error_code = 'QUERY_ERROR'


# ── ML ────────────────────────────────────────────────────────────────────────────────────
class MLError(RetryableError): error_code = 'ML_ERROR'
class ModelNotFoundError(MLError):
    error_code = 'MODEL_NOT_FOUND'; http_status = 404
class PredictionError(MLError): error_code = 'PREDICTION_ERROR'


# ── Service ─────────────────────────────────────────────────────────────────────────────────
class ServiceUnavailableError(RetryableError):
    error_code = 'SERVICE_UNAVAILABLE'; http_status = 503
class RateLimitError(NonRetryableError):
    error_code = 'RATE_LIMIT_EXCEEDED'; http_status = 429
class NotFoundError(NonRetryableError):
    error_code = 'NOT_FOUND'; http_status = 404
