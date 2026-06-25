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
"""
from __future__ import annotations
from typing import Any, Dict, Optional


class AppError(Exception):
    error_code: str = 'APP_ERROR'
    http_status: int = 500
    def __init__(self, message: str, *, error_code: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context or {}
        if error_code: self.error_code = error_code
    def to_dict(self) -> Dict[str, Any]:
        return {'error': self.error_code, 'message': self.message, 'context': self.context, 'http_status': self.http_status}

class RetryableError(AppError): pass
class NonRetryableError(AppError): pass

class AuthError(NonRetryableError):
    error_code = 'AUTH_ERROR'; http_status = 401
class TokenExpiredError(AuthError): error_code = 'TOKEN_EXPIRED'
class TokenInvalidError(AuthError): error_code = 'TOKEN_INVALID'
class InsufficientPermissionsError(NonRetryableError):
    error_code = 'INSUFFICIENT_PERMISSIONS'; http_status = 403
class LicenseError(NonRetryableError):
    error_code = 'LICENSE_ERROR'; http_status = 403

class ValidationError(NonRetryableError):
    error_code = 'VALIDATION_ERROR'; http_status = 422
class ConfigurationError(NonRetryableError):
    error_code = 'CONFIGURATION_ERROR'; http_status = 500

class RiskError(AppError):
    error_code = 'RISK_ERROR'; http_status = 500
class RiskGateError(RetryableError, RiskError): error_code = 'RISK_GATE_ERROR'
class RiskBlockedError(NonRetryableError, RiskError):
    error_code = 'RISK_BLOCKED'; http_status = 422
class CircuitOpenError(NonRetryableError, RiskError):
    error_code = 'CIRCUIT_OPEN'; http_status = 503

class ExecutionError(AppError):
    error_code = 'EXECUTION_ERROR'; http_status = 500
class OrderSubmissionError(RetryableError, ExecutionError): error_code = 'ORDER_SUBMISSION_ERROR'
class OrderDuplicateError(NonRetryableError, ExecutionError):
    error_code = 'ORDER_DUPLICATE'; http_status = 409
class BrokerConnectionError(RetryableError, ExecutionError): error_code = 'BROKER_CONNECTION_ERROR'
class OrderStateError(NonRetryableError, ExecutionError): error_code = 'ORDER_STATE_ERROR'
class ReconciliationError(RetryableError, ExecutionError): error_code = 'RECONCILIATION_ERROR'

class DatabaseError(RetryableError):
    error_code = 'DATABASE_ERROR'; http_status = 503
class DatabaseConnectionError(DatabaseError): error_code = 'DATABASE_CONNECTION_ERROR'
class QueryError(DatabaseError): error_code = 'QUERY_ERROR'

class MLError(RetryableError): error_code = 'ML_ERROR'
# FIX: Removed duplicate RetryableError base to fix MRO error
class ModelNotFoundError(MLError):
    error_code = 'MODEL_NOT_FOUND'; http_status = 404
class PredictionError(MLError): error_code = 'PREDICTION_ERROR'

class ServiceUnavailableError(RetryableError):
    error_code = 'SERVICE_UNAVAILABLE'; http_status = 503
class RateLimitError(NonRetryableError):
    error_code = 'RATE_LIMIT_EXCEEDED'; http_status = 429
class NotFoundError(NonRetryableError):
    error_code = 'NOT_FOUND'; http_status = 404
