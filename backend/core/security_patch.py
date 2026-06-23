"""backend/core/security_patch.py -- Phase U
U-16: access token exp not capped - misconfiguration risk
U-17: JTI not checked against revocation list - stolen token reuse
U-18: bcrypt 72-byte silent truncation - password security hole
U-19: refresh token JTI not stored in DB - replay attack possible
U-20: access token accepted as refresh token
"""
from __future__ import annotations
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import jwt
from passlib.context import CryptContext
from backend.core.logger import get_logger
logger = get_logger("core.security_patch")

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_BCRYPT_MAX_BYTES = 72
_MAX_ACCESS_EXPIRE_MINUTES = 1440


def hash_password_safe(password: str) -> str:
    """U-18 FIX: pre-hash with SHA-256 if > 72 bytes to prevent silent truncation."""
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        encoded = hashlib.sha256(encoded).digest()
        password = encoded.hex()
    return _pwd_ctx.hash(password)


def verify_password_safe(plain: str, hashed: str) -> bool:
    """U-18 FIX: matching verify with same pre-hash logic."""
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        encoded = hashlib.sha256(encoded).digest()
        plain = encoded.hex()
    return _pwd_ctx.verify(plain, hashed)


class _JTIRevocationList:
    def __init__(self) -> None:
        self._revoked: Dict[str, float] = {}

    def revoke(self, jti: str, exp: float) -> None:
        self._revoked[jti] = exp

    def is_revoked(self, jti: str) -> bool:
        exp = self._revoked.get(jti)
        if exp is None:
            return False
        if time.time() > exp:
            del self._revoked[jti]
            return False
        return True

    def purge_expired(self) -> int:
        now = time.time()
        before = len(self._revoked)
        self._revoked = {k: v for k, v in self._revoked.items() if v > now}
        return before - len(self._revoked)


_jti_revocation_list = _JTIRevocationList()


def revoke_token(jti: str, exp: float) -> None:
    _jti_revocation_list.revoke(jti, exp)


def create_access_token_safe(data: Dict[str, Any], secret_key: str, algorithm: str = "HS256", expires_minutes: int = 30) -> str:
    """U-16 FIX: cap expires_minutes to 24h."""
    expires_minutes = min(max(expires_minutes, 1), _MAX_ACCESS_EXPIRE_MINUTES)
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload.update({"iat": now, "exp": now + timedelta(minutes=expires_minutes), "jti": secrets.token_hex(16)})
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def validate_access_token_safe(token: str, secret_key: str, algorithm: str = "HS256") -> Dict[str, Any]:
    """U-17 FIX: check JTI against revocation list."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")
    jti = payload.get("jti")
    if jti and _jti_revocation_list.is_revoked(jti):
        raise ValueError("Token has been revoked")
    return payload


def create_refresh_token_safe(user_id: str, secret_key: str, algorithm: str = "HS256", expires_days: int = 7) -> tuple[str, str]:
    """U-19 FIX: returns (token, jti) for DB storage."""
    jti = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "jti": jti, "type": "refresh", "iat": now, "exp": now + timedelta(days=expires_days)}
    return jwt.encode(payload, secret_key, algorithm=algorithm), jti


def validate_refresh_token_safe(token: str, secret_key: str, algorithm: str = "HS256") -> Dict[str, Any]:
    """U-19/U-20 FIX: validates type=refresh and returns payload with jti."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Refresh token expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid refresh token: {exc}")
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    if not payload.get("jti"):
        raise ValueError("Missing jti in refresh token")
    return payload
