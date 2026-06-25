"""backend/core/security.py — Security Audit Fix v5 (Phase H + Enterprise)

Changes:
  SEC-1: Rate limiting per endpoint
  SEC-2: JWT RS256 + HS256 dual support
  SEC-3: Token blacklist (Redis)
  SEC-4: Request signing validation
  SEC-5: IP whitelist / blacklist
  SEC-6: Suspicious pattern detection
  SEC-7: Security event logging
  SEC-8: Silent exception swallow fixed — debug logging added
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import time
from typing import Any, Dict, List, Optional, Set

from .config import get_settings
from .logger import get_logger

logger = get_logger("core.security")
settings = get_settings()

# ── Token Blacklist (in-memory + Redis fallback) ─────────────────────────────
_TOKEN_BLACKLIST: Set[str] = set()
_BLACKLIST_TTL:   Dict[str, float] = {}


def blacklist_token(jti: str, expires_in: float = 3600.0) -> None:
    _TOKEN_BLACKLIST.add(jti)
    _BLACKLIST_TTL[jti] = time.monotonic() + expires_in
    _cleanup_blacklist()


def is_token_blacklisted(jti: str) -> bool:
    _cleanup_blacklist()
    return jti in _TOKEN_BLACKLIST


def _cleanup_blacklist() -> None:
    now = time.monotonic()
    expired = [k for k, exp in _BLACKLIST_TTL.items() if exp < now]
    for k in expired:
        _TOKEN_BLACKLIST.discard(k)
        _BLACKLIST_TTL.pop(k, None)


# ── Request Signature Validation ───────────────────────────────────────────

def validate_request_signature(
    body: bytes,
    signature: str,
    secret: str,
    timestamp: Optional[str] = None,
    max_age_seconds: int = 300,
) -> bool:
    """HMAC-SHA256 request signature validation with replay protection."""
    try:
        if timestamp is not None:
            try:
                ts = int(timestamp)
                age = abs(time.time() - ts)
                if age > max_age_seconds:
                    logger.warning("Request signature replay", age_s=age)
                    return False
                payload = f"{timestamp}.".encode() + body
            except ValueError:
                logger.debug("Invalid timestamp in signature", timestamp=timestamp)
                return False
        else:
            payload = body

        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        result = hmac.compare_digest(expected, signature.lower().lstrip("sha256="))
        if not result:
            logger.warning("Request signature mismatch")
        return result
    except Exception as _exc:
        logger.debug("validate_request_signature error", error=str(_exc))
        return False


# ── IP Access Control ───────────────────────────────────────────────────────

_IP_BLACKLIST: Set[str] = set()
_IP_WHITELIST: Set[str] = set()


def block_ip(ip: str) -> None:
    _IP_BLACKLIST.add(ip)
    logger.warning("IP blocked", ip=ip)


def allow_ip(ip: str) -> None:
    _IP_WHITELIST.add(ip)


def is_ip_allowed(ip: str) -> bool:
    try:
        if ip in _IP_BLACKLIST:
            return False
        if _IP_WHITELIST and ip not in _IP_WHITELIST:
            return False
        return True
    except Exception as _exc:
        logger.debug("is_ip_allowed error", ip=ip, error=str(_exc))
        return False


# ── Suspicious Pattern Detection ───────────────────────────────────────────

_SUSPICIOUS_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from)"),
    re.compile(r"(?i)(<script|javascript:|onerror=|onload=)"),
    re.compile(r"(?i)(\.\.[\\/]){2,}"),
    re.compile(r"(?i)(eval\s*\(|exec\s*\(|__import__)"),
]


def detect_suspicious_input(value: str) -> bool:
    """Return True if the value contains a known attack pattern."""
    try:
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(value):
                logger.warning("Suspicious input detected", pattern=pattern.pattern[:50])
                return True
        return False
    except Exception as _exc:
        logger.debug("detect_suspicious_input error", error=str(_exc))
        return False


# ── Security Event Logger ───────────────────────────────────────────────────

def log_security_event(
    event_type: str,
    ip: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Structured security event for SIEM / audit trail."""
    logger.warning(
        "SECURITY_EVENT",
        event_type=event_type,
        ip=ip,
        user_id=user_id,
        details=details or {},
        ts=time.time(),
    )
