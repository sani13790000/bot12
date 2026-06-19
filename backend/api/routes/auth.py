"""
backend/api/routes/auth.py
Authentication endpoints — secure implementation.

Security:
- bcrypt password hashing (12 rounds)
- JWT in HttpOnly + Secure + SameSite=Strict cookie
- Refresh token with jti stored in DB for revocation
- Account lockout after 5 failed attempts (15 min)
- Constant-time password comparison
- No user enumeration (same response for bad user/pass)
- Rate limiting handled by RateLimitMiddleware (/auth/login: 5/min)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.core.config import get_settings
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    validate_refresh_token,
    verify_password,
)
from backend.core.deps import get_current_user
from backend.database.connection import get_db_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])

# ---------------------------------------------------------------------------
# Account lockout (in-memory, per IP)
# ---------------------------------------------------------------------------
_LOCKOUT_MAX_ATTEMPTS = 5
_LOCKOUT_WINDOW_SEC = 15 * 60   # 15 minutes
_MAX_TRACKED_IPS = 50_000

_attempts: Dict[str, list[float]] = defaultdict(list)   # ip → [timestamps]
_lockout_until: Dict[str, float] = {}                   # ip → epoch unlock time
_lock = asyncio.Lock()


async def _record_failure(ip: str) -> None:
    async with _lock:
        now = time.monotonic()
        _attempts[ip] = [t for t in _attempts[ip] if now - t < _LOCKOUT_WINDOW_SEC]
        _attempts[ip].append(now)
        if len(_attempts[ip]) >= _LOCKOUT_MAX_ATTEMPTS:
            _lockout_until[ip] = now + _LOCKOUT_WINDOW_SEC
            log.warning("Auth lockout triggered for IP %s", ip)
        # Evict oldest if map too large
        if len(_attempts) > _MAX_TRACKED_IPS:
            oldest = min(_attempts, key=lambda k: _attempts[k][0] if _attempts[k] else 0)
            _attempts.pop(oldest, None)


async def _is_locked(ip: str) -> bool:
    async with _lock:
        until = _lockout_until.get(ip)
        if until and time.monotonic() < until:
            return True
        _lockout_until.pop(ip, None)
        return False


async def _clear_failures(ip: str) -> None:
    async with _lock:
        _attempts.pop(ip, None)
        _lockout_until.pop(ip, None)


# ---------------------------------------------------------------------------
# Cookie helper
# ---------------------------------------------------------------------------

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set both tokens as HttpOnly cookies."""
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"

    cookie_kwargs = dict(
        httponly=True,
        secure=is_prod,           # HTTPS only in production
        samesite="strict",        # CSRF protection
        path="/",
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400,
        **cookie_kwargs,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain an uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain a digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    # Body-based refresh (alternative to cookie)
    refresh_token: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db=Depends(get_db_client),
) -> dict:
    """Register a new user."""
    # Check duplicate email
    try:
        existing = (
            await db.table("users")
            .select("id")
            .eq("email", body.email)
            .maybe_single()
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB error during registration: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Registration failed") from exc

    # Hash password
    hashed = hash_password(body.password)

    # Insert user
    try:
        result = (
            await db.table("users")
            .insert({
                "email": body.email,
                "full_name": body.full_name,
                "password_hash": hashed,
                "role": "user",
                "is_active": True,
            })
            .execute()
        )
        user = result.data[0]
    except Exception as exc:
        log.error("DB insert error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Registration failed") from exc

    # Issue tokens
    access = create_access_token(user["id"], {"role": user["role"]})
    refresh, jti = create_refresh_token(user["id"])
    await _store_refresh_jti(db, user["id"], jti)
    _set_auth_cookies(response, access, refresh)

    settings = get_settings()
    return TokenResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"id": user["id"], "email": user["email"], "role": user["role"]},
    ).model_dump()


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db=Depends(get_db_client),
) -> dict:
    """Login — returns JWT in HttpOnly cookie."""
    ip = request.client.host if request.client else "unknown"

    # Lockout check
    if await _is_locked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again in 15 minutes.",
        )

    # Fetch user — same error message for user-not-found vs wrong-password
    # to prevent user enumeration
    _GENERIC_ERROR = "Invalid email or password"
    try:
        result = (
            await db.table("users")
            .select("id, email, password_hash, role, is_active")
            .eq("email", body.email)
            .maybe_single()
            .execute()
        )
        user = result.data
    except Exception as exc:
        log.error("DB error during login: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Login failed") from exc

    # Constant-time check even if user not found
    dummy_hash = "$2b$12$notarealhashjustpadding000000000000000000000000000"
    valid = verify_password(body.password, user["password_hash"] if user else dummy_hash)

    if not user or not valid or not user.get("is_active"):
        await _record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_ERROR,
        )

    await _clear_failures(ip)

    access = create_access_token(user["id"], {"role": user["role"]})
    refresh, jti = create_refresh_token(user["id"])
    await _store_refresh_jti(db, user["id"], jti)
    _set_auth_cookies(response, access, refresh)

    settings = get_settings()
    log.info("User %s logged in", user["id"])
    return TokenResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"id": user["id"], "email": user["email"], "role": user["role"]},
    ).model_dump()


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db=Depends(get_db_client),
) -> dict:
    """Rotate refresh token — old jti is revoked, new pair issued."""
    # Accept from cookie or body
    token = request.cookies.get("refresh_token")
    if not token:
        body_bytes = await request.body()
        try:
            import json
            body_data = json.loads(body_bytes)
            token = body_data.get("refresh_token")
        except Exception:
            token = None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )

    try:
        payload = validate_refresh_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    jti = payload["jti"]
    user_id = payload["sub"]

    # Verify jti exists in DB (not already revoked)
    try:
        row = (
            await db.table("refresh_tokens")
            .select("jti, user_id")
            .eq("jti", jti)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB error during token refresh: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Token refresh failed") from exc

    # Revoke old jti
    try:
        await db.table("refresh_tokens").delete().eq("jti", jti).execute()
    except Exception:
        pass  # Best effort

    # Issue new tokens
    new_access = create_access_token(user_id)
    new_refresh, new_jti = create_refresh_token(user_id)
    await _store_refresh_jti(db, user_id, new_jti)
    _set_auth_cookies(response, new_access, new_refresh)

    settings = get_settings()
    return {"token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_client),
) -> dict:
    """Revoke current access token jti + all refresh tokens for this user."""
    # Revoke access token
    token = request.cookies.get("access_token") or ""
    if token:
        try:
            from backend.core.security import validate_access_token
            payload = validate_access_token(token)
            await db.table("revoked_tokens").insert({
                "jti": payload["jti"],
                "user_id": current_user["id"],
                "expires_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass  # Best effort

    # Revoke all refresh tokens
    try:
        await db.table("refresh_tokens").delete().eq("user_id", current_user["id"]).execute()
    except Exception:
        pass

    # Clear cookies
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")

    return {"detail": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    """Return current user profile."""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "role": current_user["role"],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _store_refresh_jti(db, user_id: str, jti: str) -> None:
    """Persist refresh jti in DB so we can revoke it."""
    try:
        settings = get_settings()
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        ).isoformat()
        await db.table("refresh_tokens").insert({
            "jti": jti,
            "user_id": user_id,
            "expires_at": expires_at,
        }).execute()
    except Exception as exc:
        log.error("Failed to store refresh jti: %s", type(exc).__name__)
