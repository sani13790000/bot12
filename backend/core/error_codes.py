"""backend/core/error_codes.py — Phase 12
Standardized API error codes for all routes.

P12-FIX-ERR-1: هر error یک machine-readable code + HTTP status دارد
P12-FIX-ERR-2: هیچ internal detail به client نمی‌رسد
P12-FIX-ERR-3: request_id در هر error response
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


class EC:
    # Auth
    AUTH_MISSING          = "AUTH_MISSING"
    AUTH_INVALID          = "AUTH_INVALID"
    AUTH_EXPIRED          = "AUTH_EXPIRED"
    AUTH_BLACKLISTED      = "AUTH_BLACKLISTED"
    AUTH_LOCKED           = "AUTH_LOCKED"
    # Permission
    PERM_DENIED           = "PERM_DENIED"
    PERM_ROLE_REQUIRED    = "PERM_ROLE_REQUIRED"
    PERM_OWNER_REQUIRED   = "PERM_OWNER_REQUIRED"
    # Validation
    VALIDATION_ERROR      = "VALIDATION_ERROR"
    VALIDATION_FIELD      = "VALIDATION_FIELD"
    VALIDATION_SYMBOL     = "VALIDATION_SYMBOL"
    VALIDATION_LOT        = "VALIDATION_LOT"
    VALIDATION_PRICE      = "VALIDATION_PRICE"
    VALIDATION_PAGINATION = "VALIDATION_PAGINATION"
    # Resource
    NOT_FOUND             = "NOT_FOUND"
    CONFLICT              = "CONFLICT"
    ALREADY_EXISTS        = "ALREADY_EXISTS"
    # Rate limit
    RATE_LIMITED          = "RATE_LIMITED"
    RATE_LIMITED_IP       = "RATE_LIMITED_IP"
    RATE_LIMITED_USER     = "RATE_LIMITED_USER"
    # Risk
    RISK_BLOCKED          = "RISK_BLOCKED"
    RISK_GATE_FAIL        = "RISK_GATE_FAIL"
    RISK_KILL_SWITCH      = "RISK_KILL_SWITCH"
    RISK_MARGIN           = "RISK_MARGIN"
    RISK_DRAWDOWN         = "RISK_DRAWDOWN"
    RISK_DAILY_LIMIT      = "RISK_DAILY_LIMIT"
    RISK_EXPOSURE         = "RISK_EXPOSURE"
    # Execution
    ORDER_DUPLICATE       = "ORDER_DUPLICATE"
    ORDER_STATE           = "ORDER_STATE"
    ORDER_SUBMIT_FAIL     = "ORDER_SUBMIT_FAIL"
    ORDER_TIMEOUT         = "ORDER_TIMEOUT"
    BROKER_CONNECTION     = "BROKER_CONNECTION"
    # License
    LICENSE_INVALID       = "LICENSE_INVALID"
    LICENSE_EXPIRED       = "LICENSE_EXPIRED"
    LICENSE_DEVICE_LIMIT  = "LICENSE_DEVICE_LIMIT"
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED"
    PAYMENT_FAILED        = "PAYMENT_FAILED"
    # Server
    INTERNAL_ERROR        = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE   = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR        = "DATABASE_ERROR"
    TIMEOUT               = "TIMEOUT"
    # Security
    SECURITY_INJECTION    = "SECURITY_INJECTION"
    SECURITY_PATH_TRAVERSAL = "SECURITY_PATH_TRAVERSAL"
    SECURITY_REPLAY       = "SECURITY_REPLAY"
    SECURITY_SIGNATURE    = "SECURITY_SIGNATURE"


_CODE_TO_HTTP: Dict[str, int] = {
    EC.AUTH_MISSING: 401, EC.AUTH_INVALID: 401, EC.AUTH_EXPIRED: 401,
    EC.AUTH_BLACKLISTED: 401, EC.AUTH_LOCKED: 429,
    EC.PERM_DENIED: 403, EC.PERM_ROLE_REQUIRED: 403, EC.PERM_OWNER_REQUIRED: 403,
    EC.VALIDATION_ERROR: 422, EC.VALIDATION_FIELD: 422, EC.VALIDATION_SYMBOL: 422,
    EC.VALIDATION_LOT: 422, EC.VALIDATION_PRICE: 422, EC.VALIDATION_PAGINATION: 422,
    EC.NOT_FOUND: 404, EC.CONFLICT: 409, EC.ALREADY_EXISTS: 409,
    EC.RATE_LIMITED: 429, EC.RATE_LIMITED_IP: 429, EC.RATE_LIMITED_USER: 429,
    EC.RISK_BLOCKED: 422, EC.RISK_GATE_FAIL: 422, EC.RISK_KILL_SWITCH: 503,
    EC.RISK_MARGIN: 422, EC.RISK_DRAWDOWN: 422, EC.RISK_DAILY_LIMIT: 422, EC.RISK_EXPOSURE: 422,
    EC.ORDER_DUPLICATE: 409, EC.ORDER_STATE: 409, EC.ORDER_SUBMIT_FAIL: 500,
    EC.ORDER_TIMEOUT: 504, EC.BROKER_CONNECTION: 503,
    EC.LICENSE_INVALID: 403, EC.LICENSE_EXPIRED: 403, EC.LICENSE_DEVICE_LIMIT: 403,
    EC.SUBSCRIPTION_REQUIRED: 402, EC.PAYMENT_FAILED: 402,
    EC.INTERNAL_ERROR: 500, EC.SERVICE_UNAVAILABLE: 503, EC.DATABASE_ERROR: 503, EC.TIMEOUT: 504,
    EC.SECURITY_INJECTION: 400, EC.SECURITY_PATH_TRAVERSAL: 400,
    EC.SECURITY_REPLAY: 400, EC.SECURITY_SIGNATURE: 400,
}

_CODE_TO_MSG: Dict[str, str] = {
    EC.AUTH_MISSING: "Authentication required",
    EC.AUTH_INVALID: "Invalid or expired credentials",
    EC.AUTH_EXPIRED: "Session expired — please log in again",
    EC.AUTH_BLACKLISTED: "Token has been revoked",
    EC.AUTH_LOCKED: "Account temporarily locked",
    EC.PERM_DENIED: "Permission denied",
    EC.PERM_ROLE_REQUIRED: "Insufficient role for this action",
    EC.PERM_OWNER_REQUIRED: "Access denied — resource belongs to another user",
    EC.VALIDATION_ERROR: "Request validation failed",
    EC.VALIDATION_FIELD: "Invalid field value",
    EC.VALIDATION_SYMBOL: "Symbol not supported",
    EC.VALIDATION_LOT: "Lot size out of range",
    EC.VALIDATION_PRICE: "Price value out of range",
    EC.VALIDATION_PAGINATION: "Pagination parameters invalid",
    EC.NOT_FOUND: "Resource not found",
    EC.CONFLICT: "Resource conflict",
    EC.ALREADY_EXISTS: "Resource already exists",
    EC.RATE_LIMITED: "Too many requests — slow down",
    EC.RATE_LIMITED_IP: "IP rate limit exceeded",
    EC.RATE_LIMITED_USER: "User rate limit exceeded",
    EC.RISK_BLOCKED: "Trade blocked by risk management",
    EC.RISK_GATE_FAIL: "Risk gate check failed",
    EC.RISK_KILL_SWITCH: "Trading halted by system",
    EC.RISK_MARGIN: "Insufficient margin",
    EC.RISK_DRAWDOWN: "Drawdown limit reached",
    EC.RISK_DAILY_LIMIT: "Daily loss limit reached",
    EC.RISK_EXPOSURE: "Exposure limit reached",
    EC.ORDER_DUPLICATE: "Duplicate order detected",
    EC.ORDER_STATE: "Invalid order state transition",
    EC.ORDER_SUBMIT_FAIL: "Order submission failed",
    EC.ORDER_TIMEOUT: "Order timed out",
    EC.BROKER_CONNECTION: "Broker connection error",
    EC.LICENSE_INVALID: "License is invalid",
    EC.LICENSE_EXPIRED: "License has expired",
    EC.LICENSE_DEVICE_LIMIT: "Device limit reached",
    EC.SUBSCRIPTION_REQUIRED: "Active subscription required",
    EC.PAYMENT_FAILED: "Payment could not be processed",
    EC.INTERNAL_ERROR: "An internal error occurred",
    EC.SERVICE_UNAVAILABLE: "Service temporarily unavailable",
    EC.DATABASE_ERROR: "Database temporarily unavailable",
    EC.TIMEOUT: "Request timed out",
    EC.SECURITY_INJECTION: "Request blocked by security filter",
    EC.SECURITY_PATH_TRAVERSAL: "Request blocked by security filter",
    EC.SECURITY_REPLAY: "Request blocked — replay detected",
    EC.SECURITY_SIGNATURE: "Request signature invalid",
}


@dataclass
class APIError:
    code:        str
    http_status: int           = field(init=False)
    message:     str           = field(init=False)
    detail:      Optional[str] = None
    request_id:  str           = field(default_factory=lambda: str(uuid.uuid4()))
    context:     Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.http_status = _CODE_TO_HTTP.get(self.code, 500)
        self.message     = _CODE_TO_MSG.get(self.code, "An error occurred")

    def to_response(self) -> Dict[str, Any]:
        resp: Dict[str, Any] = {
            "error":      self.code,
            "message":    self.message,
            "request_id": self.request_id,
        }
        if self.detail and self.http_status < 500:
            resp["detail"] = self.detail[:200]
        return resp


def api_error(
    code: str,
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
    **context: Any,
) -> APIError:
    err = APIError(code=code, detail=detail, context=context)
    if request_id:
        err.request_id = request_id
    return err


def http_status(code: str) -> int:
    return _CODE_TO_HTTP.get(code, 500)
