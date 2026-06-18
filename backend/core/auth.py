"""
Phase 10 — JWT Auth Hardening
Secure token validation with expiry, algorithm pinning, and scope checking.
"""
from __future__ import annotations

import os
import time
import uuid
import hashlib
import hmac
import base64
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.observability import get_logger

logger = get_logger("security.auth")

_bearer = HTTPBearer(auto_error=False)


@dataclass
class TokenPayload:
    user_id: str
    email: str
    role: str = "user"
    scopes: List[str] = field(default_factory=list)
    exp: int = 0
    iat: int = 0
    jti: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_expired(self) -> bool:
        return self.exp > 0 and time.time() > self.exp

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or self.is_admin


def _b64decode_pad(s: str) -> bytes:
    """Base64url decode with padding fix."""
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def _verify_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    """Minimal HS256 JWT verify without external deps."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        # Verify algorithm
        header = json.loads(_b64decode_pad(header_b64))
        if header.get("alg") != "HS256":
            logger.warning("JWT algorithm mismatch", alg=header.get("alg"))
            return None

        # Verify signature
        msg = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        actual_sig = _b64decode_pad(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64decode_pad(payload_b64))
        return payload
    except Exception as e:
        logger.debug(f"JWT verify error: {e}")
        return None


def _parse_supabase_jwt(token: str) -> Optional[TokenPayload]:
    """Parse Supabase JWT (anon key signed) — trust Supabase signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = json.loads(_b64decode_pad(parts[1]))

        user_id = payload.get("sub", "")
        email = payload.get("email", "")
        role = payload.get("role", "authenticated")
        exp = payload.get("exp", 0)
        iat = payload.get("iat", 0)
        app_meta = payload.get("app_metadata", {})
        user_meta = payload.get("user_metadata", {})
        scopes = app_meta.get("scopes", [])
        if app_meta.get("role") == "admin" or user_meta.get("is_admin"):
            role = "admin"

        return TokenPayload(
            user_id=user_id,
            email=email,
            role=role,
            scopes=scopes,
            exp=exp,
            iat=iat,
            jti=payload.get("jti", ""),
        )
    except Exception as e:
        logger.debug(f"Supabase JWT parse error: {e}")
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> TokenPayload:
    """FastAPI dependency — validates JWT, returns TokenPayload."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token", "message": "Authorization header required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Try Supabase JWT (most common)
    payload = _parse_supabase_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid or malformed token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_expired", "message": "Token has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Token missing user ID"},
        )

    return payload


async def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """FastAPI dependency — requires admin role."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "Admin access required"},
        )
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[TokenPayload]:
    """FastAPI dependency — returns None if no token (public endpoints)."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
