"""
backend/core/deps.py
FastAPI dependency-injection helpers — authentication, authorization.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.security import validate_access_token
from backend.database.connection import get_db_client

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _extract_token(request: Request) -> Optional[str]:
    """
    Extract JWT from (in priority order):
    1. HttpOnly cookie  `access_token`
    2. Authorization: Bearer <token> header

    Never reads token from query string for REST endpoints
    (WS endpoints use ?token= with one-time-use validation).
    """
    # 1. Cookie (preferred — not accessible to JS)
    cookie_token: Optional[str] = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    # 2. Bearer header (for API clients / MQL5)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


async def get_current_user(
    request: Request,
    db=Depends(get_db_client),
) -> dict:
    """
    FastAPI dependency: extract + validate JWT, check revocation in DB.
    Returns user dict with at least {id, email, role}.
    Raises HTTP 401 on any auth failure.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = validate_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload["sub"]
    jti = payload["jti"]

    # Check revocation list
    try:
        row = (
            await db.table("revoked_tokens")
            .select("jti")
            .eq("jti", jti)
            .maybe_single()
            .execute()
        )
        if row.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
    except HTTPException:
        raise
    except Exception:  # DB unavailable — fail open with warning
        log.warning("Could not check token revocation for user %s", user_id)

    # Fetch user from DB
    try:
        user_row = (
            await db.table("users")
            .select("id, email, role, is_active")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as exc:
        log.error("DB error fetching user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        ) from exc

    user = user_row.data
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or deleted user",
        )

    return user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require role == 'admin'."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_active(current_user: dict = Depends(get_current_user)) -> dict:
    """Require is_active == True (already checked in get_current_user)."""
    return current_user
