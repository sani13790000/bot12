"""backend/core/security.py — Security Fix F3 (Phase H + Enterprise)

Fixes applied:
  S3:  Token blacklist is now dual-layer:
         - Primary: in-memory (fast lookup)
         - Persistent: shelve file (survives restart, no Redis dependency)
       On startup the in-memory store is loaded from the shelve file.
  SEC-4: Request signing validation (unchanged)
  SEC-5: IP whitelist / blacklist (unchanged)
  SEC-6: Suspicious pattern detection (unchanged)
  SEC-7: Security event logging (unchanged)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import shelve
import threading
import time
from typing import Any, Dict, List, Optional, Set

from .config import get_settings
from .logger import get_logger

logger = get_logger("core.security")

# ── Token Blacklist (in-memory + persistent shelve) ──────────────────────────────

_TOKEN_BLACKLIST: Set[str] = set()
_BLACKLIST_TTL: Dict[str, float] = {}
_BLACKLIST_LOCK = threading.Lock()

_SHELVE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_blacklist_store",
)


def _load_blacklist_from_disk() -> None:
    try:
        with shelve.open(_SHELVE_PATH, flag="c") as db:
            now = time.monotonic()
            wall_now = time.time()
            for jti, (wall_exp,) in list(db.items()):
                if wall_exp > wall_now:
                    mono_exp = now + (wall_exp - wall_now)
                    _TOKEN_BLACKLIST.add(jti)
                    _BLACKLIST_TTL[jti] = mono_exp
                else:
                    del db[jti]
    except Exception as exc:
        logger.warning("blacklist shelve load failed (non-fatal): %s", exc)


def _persist_blacklist_entry(jti: str, wall_exp: float) -> None:
    try:
        with shelve.open(_SHELVE_PATH, flag="c") as db:
            db[jti] = (wall_exp,)
    except Exception as exc:
        logger.debug("blacklist shelve write failed: %s", exc)


def blacklist_token(jti: str, expires_in: float = 3600.0) -> None:
    wall_exp = time.time() + expires_in
    mono_exp = time.monotonic() + expires_in
    with _BLACKLIST_LOCK:
        _TOKEN_BLACKLIST.add(jti)
        _BLACKLIST_TTL[jti] = mono_exp
    _persist_blacklist_entry(jti, wall_exp)
    _cleanup_blacklist()


def is_token_blacklisted(jti: str) -> bool:
    _cleanup_blacklist()
    with _BLACKLIST_LOCK:
        return jti in _TOKEN_BLACKLIST


def _cleanup_blacklist() -> None:
    now = time.monotonic()
    with _BLACKLIST_LOCK:
        expired = [k for k, exp in _BLACKLIST_TTL.items() if exp < now]
        for k in expired:
            _TOKEN_BLACKLIST.discard(k)
            _BLACKLIST_TTL.pop(k, None)
    if expired:
        try:
            with shelve.open(_SHELVE_PATH, flag="c") as db:
                for k in expired:
                    db.pop(k, None)
        except Exception:
            pass


_load_blacklist_from_disk()


# ── Request Signature Validation ─────────────────────────────────────────────────────

def validate_request_signature(
    body: bytes,
    signature: str,
    secret: str,
    timestamp: Optional[str] = None,
    max_age_seconds: int = 300,
) -> bool:
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
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        result = hmac.compare_digest(expected, signature.lower().lstrip("sha256="))
        if not result:
            logger.warning("Request signature mismatch")
        return result
    except Exception as _exc:
        logger.debug("validate_request_signature error", error=str(_exc))
        return False


# ── IP Access Control ─────────────────────────────────────────────────────────────────────

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


# ── Suspicious Pattern Detection ─────────────────────────────────────────────────────

_SUSPICIOUS_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from)"),
    re.compile(r"(?i)(<script|javascript:|onerror=|onload=)"),
    re.compile(r"(?i)(\.\.[\\\\/ ]){2,}"),
    re.compile(r"(?i)(eval\s*\(|exec\s*\(|__import__)"),
]


def detect_suspicious_input(value: str) -> bool:
    try:
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(value):
                logger.warning("Suspicious input detected", pattern=pattern.pattern[:50])
                return True
        return False
    except Exception as _exc:
        logger.debug("detect_suspicious_input error", error=str(_exc))
        return False


# ── Security Event Logger ───────────────────────────────────────────────────────────────

def log_security_event(
    event_type: str,
    ip: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    logger.warning(
        "SECURITY_EVENT",
        event_type=event_type,
        ip=ip,
        user_id=user_id,
        details=details or {},
        ts=time.time(),
    )
