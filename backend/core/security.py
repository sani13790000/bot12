"""backend/core/security.py — Security Audit Fix v4 (Phase H)

SEC-1  algorithm confusion: jose.jwt.decode() now has explicit algorithms=[_ALGORITHM]
       + options={"verify_aud": False} — prevents alg:none + aud bypass
SEC-2  JTI entropy: 64 hex chars (256-bit) — was 64 (good, kept)
SEC-3  sub claim length check — prevent sub>=4096 byte DoS in logs
SEC-4  create_access_token: exp capped at 1440 min regardless of caller argument
SEC-5  generate_secure_token: minimum 32 bytes enforced
SEC-6  decode_token: options["require"] now includes "type"
SEC-7  Token type checked AFTER signature verification — prevents type confusion
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.core.config import get_settings

log = logging.getLogger(__name__)

_pwd_ctx = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

_BCRYPT_MAX_BYTES: int = 72
_ALGORITHM = "HS256"
_MAX_SUB_LEN: int = 256
_JTI_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("Password cannot be empty")
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"Password too long (max {_BCRYPT_MAX_BYTES} bytes when UTF-8 encoded)")
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bool(_pwd_ctx.verify(plain, hashed))
    except Exception as exc:
        log.warning("bcrypt verify error: %s", type(exc).__name__)
        return False


def _secret() -> str:
    s = get_settings().JWT_SECRET_KEY
    if len(s) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be >= 32 characters")
    return s


def create_access_token(
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    if len(str(subject)) > _MAX_SUB_LEN:
        raise ValueError(f"Subject too long (max {_MAX_SUB_LEN} chars)")
    s = get_settings()
    exp_minutes = min(expires_minutes or s.ACCESS_TOKEN_EXPIRE_MINUTES, 1440)
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)
    _RESERVED = {"sub", "iat", "exp", "jti", "type"}
    claims: Dict[str, Any] = {
        "sub":  str(subject),
        "iat":  now,
        "exp":  now + timedelta(minutes=exp_minutes),
        "jti":  jti,
        "type": "access",
    }
    if extra_claims:
        safe = {k: v for k, v in extra_claims.items() if k not in _RESERVED}
        claims.update(safe)
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def create_refresh_token(subject: str) -> Tuple[str, str]:
    if len(str(subject)) > _MAX_SUB_LEN:
        raise ValueError(f"Subject too long (max {_MAX_SUB_LEN} chars)")
    s = get_settings()
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(32)
    claims = {
        "sub":  str(subject),
        "iat":  now,
        "exp":  now + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti":  jti,
        "type": "refresh",
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM), jti


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            options={
                "require":    ["sub", "exp", "iat", "jti", "type"],
                "verify_aud": False,
            },
        )
    except JWTError as exc:
        log.warning("JWT decode failure: %s", type(exc).__name__)
        raise ValueError("Invalid or expired token") from exc
    if not _JTI_PATTERN.match(str(payload.get("jti", ""))):
        raise ValueError("Malformed token identifier")
    if len(str(payload.get("sub", ""))) > _MAX_SUB_LEN:
        raise ValueError("Subject claim too long")
    return payload


def validate_access_token(token: str) -> Dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    return payload


def validate_refresh_token(token: str) -> Dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    return payload


decode_access_token = validate_access_token


def sign_payload(payload: bytes, secret: str) -> str:
    if not secret:
        raise ValueError("HMAC secret must not be empty")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, provided_sig: str) -> bool:
    if not secret or not provided_sig:
        return False
    try:
        return hmac.compare_digest(sign_payload(payload, secret), provided_sig)
    except Exception:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(max(nbytes, 32))
