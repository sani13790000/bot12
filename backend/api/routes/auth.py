"""backend/api/routes/auth.py — production-hardened v4.

FIX-1  _DUMMY_HASH was 57 chars (malformed bcrypt) — passlib ValueError
        — timing protection was BROKEN. Now valid 60-char hash.
FIX-2  _safe_verify(): always returns bool, never raises.
FIX-3  deque(maxlen=5) for O(1) lockout eviction.
FIX-4  get_client_ip() for IP extraction — spoof-resistant.
FIX-5  _store_refresh_jti: upsert on_conflict=jti.
FIX-6  Refresh body limited to 4KB.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
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
from backend.core.deps import get_current_user, get_db
from backend.core.client_ip import get_client_ip

log = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])

_LOCKOUT_MAX_ATTEMPTS: int = 5
_LOCKOUT_WINDOW_SEC:   int = 15 * 60
_MAX_TRACKED_IPS:      int = 50_000

_attempts:      Dict[str, deque] = defaultdict(lambda: deque(maxlen=_LOCKOUT_MAX_ATTEMPTS))
_lockout_until: Dict[str, float] = {}
_lock = asyncio.Lock()

_DUMMY_HASH: str = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
assert len(_DUMMY_HASH) == 60, "Dummy hash must be exactly 60 chars for valid bcrypt"


async def _record_failure(ip: str) -> None:
    async with _lock:
        now = time.monotonic()
        dq = _attempts[ip]
        dq.append(now)
        if len(dq) >= _LOCKOUT_MAX_ATTEMPTS:
            oldest = dq[0]
            if now - oldest <= _LOCKOUT_WINDOW_SEC:
                _lockout_until[ip] = now + _LOCKOUT_WINDOW_SEC
                log.warning("Auth lockout triggered for IP %s", ip)
        if len(_attempts) > _MAX_TRACKED_IPS:
            try:
                del _attempts[next(iter(_attempts))]
            except StopIteration:
                pass


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


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"
    kw = dict(httponly=True, secure=is_prod, samesite="strict", path="/")
    response.set_cookie(
        key="access_token", value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, **kw,
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400, **kw,
    )


class RegisterRequest(BaseModel):
    email:     EmailStr
    password:  str = Field(min_length=8, max_length=128)
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
    email:    EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int
    user: dict


async def _store_refresh_jti(db, user_id: str, jti: str) -> None:
    settings = get_settings()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    try:
        await db.table("refresh_tokens").upsert(
            {"jti": jti, "user_id": user_id, "expires_at": expires_at},
            on_conflict="jti",
        ).execute()
    except Exception as exc:
        log.error("Failed to store refresh jti: %s", type(exc).__name__)


def _safe_verify(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bool(verify_password(plain, hashed))
    except Exception as exc:
        log.error("bcrypt verify error: %s", type(exc).__name__)
        return False


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db=Depends(get_db),
) -> dict:
    try:
        existing = (
            await db.table("users")
            .select("id").eq("email", body.email)
            .maybe_single().execute()
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

    hashed = hash_password(body.password)
    try:
        result = await db.table("users").insert({
            "email": body.email,
            "full_name": body.full_name,
            "password_hash": hashed,
            "role": "user",
            "is_active": True,
        }).execute()
        user = result.data[0]
    except Exception as exc:
        log.error("DB insert error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Registration failed") from exc

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
    db=Depends(get_db),
) -> dict:
    ip = get_client_ip(request)
    if await _is_locked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again in 15 minutes.",
        )
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

    hash_to_check = user["password_hash"] if user else _DUMMY_HASH
    valid = _safe_verify(body.password, hash_to_check)
    if not user or not valid or not user.get("is_active"):
        await _record_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_ERROR)

    await _clear_failures(ip)
    access = create_access_token(user["id"], {"role": user["role"]})
    refresh, jti = create_refresh_token(user["id"])
    await _store_refresh_jti(db, user["id"], jti)
    _set_auth_cookies(response, access, refresh)
    settings = get_settings()
    log.info("user_login user_id=%s", user["id"])
    return TokenResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"id": user["id"], "email": user["email"], "role": user["role"]},
    ).model_dump()


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db=Depends(get_db),
) -> dict:
    token = request.cookies.get("refresh_token")
    if not token:
        try:
            body_bytes = await request.body()
            if len(body_bytes) > 4096:
                raise HTTPException(status_code=400, detail="Request body too large")
            import json as _json
            body_data = _json.loads(body_bytes)
            token = body_data.get("refresh_token")
        except HTTPException:
            raise
        except Exception:
            token = None
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    try:
        payload = validate_refresh_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    jti     = payload["jti"]
    user_id = payload["sub"]
    try:
        row = (
            await db.table("refresh_tokens")
            .select("jti, user_id").eq("jti", jti).eq("user_id", user_id)
            .maybe_single().execute()
        )
        if not row.data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB error during refresh: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Token refresh failed") from exc
    try:
        await db.table("refresh_tokens").delete().eq("jti", jti).execute()
        await db.table("revoked_tokens").insert({"jti": jti}).execute()
    except Exception as exc:
        log.error("Failed to revoke old refresh jti: %s", type(exc).__name__)
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
    db=Depends(get_db),
) -> dict:
    jti = current_user.get("jti")
    if jti:
        try:
            await db.table("revoked_tokens").insert({"jti": jti}).execute()
        except Exception as exc:
            log.warning("Failed to revoke access jti: %s", type(exc).__name__)
    user_id = current_user.get("sub")
    if user_id:
        try:
            rows = await db.table("refresh_tokens").select("jti").eq("user_id", user_id).execute()
            for row in (rows.data or []):
                try:
                    await db.table("revoked_tokens").insert({"jti": row["jti"]}).execute()
                except Exception:
                    pass
            await db.table("refresh_tokens").delete().eq("user_id", user_id).execute()
        except Exception as exc:
            log.error("Failed to revoke refresh tokens: %s", type(exc).__name__)
    for cookie in ("access_token", "refresh_token"):
        response.delete_cookie(cookie, path="/", samesite="strict")
    log.info("user_logout user_id=%s", user_id)
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    return {
        "user_id": current_user.get("sub"),
        "role":    current_user.get("role"),
        "jti":     current_user.get("jti"),
    }
