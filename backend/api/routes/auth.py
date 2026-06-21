"""backend/api/routes/auth.py — Security Audit Fix v5 (Phase H)

SEC-12 register: password max_length=72 (bcrypt limit) in Pydantic Field
SEC-13 login: identical error for wrong email AND wrong password
SEC-14 refresh: verify DB-stored expires_at
SEC-15 logout: revoke ALL refresh tokens for user
SEC-16 /me: JTI never exposed in API response
SEC-17 tokens ONLY in httpOnly cookie, never in response body
SEC-18 registration rate-limit: 5 per hour per IP
SEC-19 asyncio.Lock used properly for lockout
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
_REG_MAX:    int = 5
_REG_WINDOW: int = 3600

_attempts:      Dict[str, deque] = defaultdict(lambda: deque(maxlen=_LOCKOUT_MAX_ATTEMPTS))
_lockout_until: Dict[str, float] = {}
_reg_attempts:  Dict[str, deque] = defaultdict(lambda: deque(maxlen=_REG_MAX))
_lock = asyncio.Lock()

_DUMMY_HASH: str = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
assert len(_DUMMY_HASH) == 60
_GENERIC_ERROR = "Invalid credentials"


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


async def _is_reg_limited(ip: str) -> bool:
    async with _lock:
        now = time.monotonic()
        dq = _reg_attempts[ip]
        cutoff = now - _REG_WINDOW
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _REG_MAX:
            return True
        dq.append(now)
        return False


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
    password:  str = Field(min_length=8, max_length=72)
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
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int


async def _store_refresh_jti(db, user_id: str, jti: str) -> None:
    settings = get_settings()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    try:
        await db.upsert(
            "refresh_tokens",
            {"jti": jti, "user_id": user_id, "expires_at": expires_at},
        )
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
    request: Request,
    response: Response,
    db=Depends(get_db),
) -> dict:
    ip = get_client_ip(request)
    if await _is_reg_limited(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
        )
    try:
        existing = await db.select_one("users", {"email": body.email}, columns="id")
        if existing:
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
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.insert("users", {
            "email":         body.email,
            "password_hash": hashed,
            "full_name":     body.full_name,
            "role":          "user",
            "is_active":     True,
            "is_blocked":    False,
            "created_at":    now,
            "updated_at":    now,
        })
        user = result[0] if result else None
        if not user:
            raise HTTPException(status_code=500, detail="Registration failed")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB insert error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Registration failed") from exc

    access = create_access_token(user["id"], {"role": "user"})
    refresh, jti = create_refresh_token(user["id"])
    await _store_refresh_jti(db, user["id"], jti)
    _set_auth_cookies(response, access, refresh)
    settings = get_settings()
    log.info("user_registered user_id=%s", user["id"])
    return TokenResponse(expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60).model_dump()


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
            detail="Too many failed attempts. Try again later.",
        )
    try:
        user = await db.select_one(
            "users", {"email": body.email},
            columns="id,email,password_hash,role,is_active",
        )
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
    return TokenResponse(expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60).model_dump()


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

    jti = payload["jti"]
    user_id = payload["sub"]
    try:
        row = await db.select_one("refresh_tokens", {"jti": jti, "user_id": user_id}, columns="jti,user_id,expires_at")
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
        expires_at_str = row.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires_at:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
            except ValueError:
                pass
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB error during refresh: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Token refresh failed") from exc

    try:
        await db.delete("refresh_tokens", {"jti": jti})
        await db.insert("revoked_tokens", {"jti": jti})
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
            await db.insert("revoked_tokens", {"jti": jti})
        except Exception as exc:
            log.warning("Failed to revoke access jti: %s", type(exc).__name__)
    user_id = current_user.get("sub")
    if user_id:
        try:
            rows = await db.select_many("refresh_tokens", filters={"user_id": user_id}, columns="jti")
            for row in (rows or []):
                try:
                    await db.insert("revoked_tokens", {"jti": row["jti"]})
                except Exception:
                    pass
            await db.delete("refresh_tokens", {"user_id": user_id})
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
    }
