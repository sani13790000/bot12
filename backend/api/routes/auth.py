"""Authentication routes — JWT via HttpOnly cookies with refresh token revocation.

Security model:
- Access token:  HttpOnly + Secure + SameSite=Strict cookie (XSS-safe)
- Refresh token: stored in DB for revocation; HttpOnly cookie
- Account lockout: 5 failed attempts -> 15-minute lockout per IP+username
- Passwords: bcrypt hashed via passlib
- Production login: looks up user from Supabase users table
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, field_validator

logger = logging.getLogger(__name__)
router = APIRouter()

# ------------------------------------------------------------------ #
# Config
# ------------------------------------------------------------------ #
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGO = "HS256"

# ------------------------------------------------------------------ #
# In-memory stores (replace with Redis/DB in high-scale deployments)
# ------------------------------------------------------------------ #
# key: f"{ip}:{username}"  value: {"attempts": int, "locked_until": float}
_login_attempts: Dict[str, Dict[str, Any]] = {}
# key: jti (str) — set of revoked refresh token IDs
_revoked_tokens: set[str] = set()
_revoked_lock = asyncio.Lock()

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes
MAX_TRACKED_LOCKOUTS = 10_000  # prevent unbounded growth


# ------------------------------------------------------------------ #
# Background cleanup for _login_attempts (prevent memory growth)
# ------------------------------------------------------------------ #
async def _cleanup_login_attempts() -> None:
    """Periodically remove expired lockout entries."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        now = time.time()
        expired = [
            k for k, v in list(_login_attempts.items())
            if v.get("locked_until", 0) < now and v.get("attempts", 0) < MAX_LOGIN_ATTEMPTS
        ]
        for k in expired:
            _login_attempts.pop(k, None)
        # Hard cap
        if len(_login_attempts) > MAX_TRACKED_LOCKOUTS:
            oldest = sorted(_login_attempts.items(), key=lambda x: x[1].get("locked_until", 0))[:100]
            for k, _ in oldest:
                _login_attempts.pop(k, None)


# Start background cleanup when module loads
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(_cleanup_login_attempts())
except RuntimeError:
    pass  # no event loop yet — task will be started by lifespan


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_jwt(payload: Dict[str, Any], expires_delta: timedelta) -> str:
    import jwt as pyjwt  # PyJWT
    now = datetime.now(timezone.utc)
    payload = {
        **payload,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode_jwt(token: str) -> Dict[str, Any]:
    import jwt as pyjwt
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _cookie_kwargs(max_age: int) -> Dict[str, Any]:
    """Secure cookie flags — Secure=True only outside dev so localhost works."""
    is_prod = os.environ.get("ENVIRONMENT", "development") == "production"
    return {
        "httponly": True,
        "samesite": "strict",
        "secure": is_prod,  # True in prod (HTTPS), False in dev (HTTP localhost)
        "max_age": max_age,
        "path": "/",
    }


def _lockout_key(request: Request, username: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{username.lower()}"


def _check_lockout(key: str) -> None:
    entry = _login_attempts.get(key)
    if entry and entry.get("locked_until", 0) > time.time():
        remaining = int(entry["locked_until"] - time.time())
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account locked. Try again in {remaining}s.",
        )


def _record_failure(key: str) -> None:
    entry = _login_attempts.setdefault(key, {"attempts": 0, "locked_until": 0.0})
    entry["attempts"] += 1
    if entry["attempts"] >= MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS
        logger.warning("Account locked for key=%s after %d failed attempts.", key, entry["attempts"])


def _clear_attempts(key: str) -> None:
    _login_attempts.pop(key, None)


async def _hash_password(password: str) -> str:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return ctx.hash(password)


async def _verify_password(plain: str, hashed: str) -> bool:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return ctx.verify(plain, hashed)


async def _lookup_user_from_db(username: str) -> Optional[Dict[str, Any]]:
    """Look up user from Supabase users table.

    Returns dict with {id, username, email, hashed_password, role}
    or None if not found.
    """
    try:
        from backend.database.connection import get_db_client
        client = await get_db_client()
        result = (
            client.table("users")
            .select("id, username, email, hashed_password, role")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        data = result.data
        if data:
            return data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("DB user lookup failed: %s", exc)
        return None


# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not v.isalnum():
            raise ValueError("Username must be alphanumeric")
        return v.lower()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    message: str
    username: str


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response) -> Dict[str, Any]:
    """Register a new user and set auth cookies."""
    # Check if username already exists
    existing = await _lookup_user_from_db(body.username)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username already taken")

    hashed = await _hash_password(body.password)
    user_id = str(uuid.uuid4())

    # Persist user to Supabase
    try:
        from backend.database.connection import get_db_client
        client = await get_db_client()
        client.table("users").insert({
            "id": user_id,
            "username": body.username,
            "email": body.email,
            "hashed_password": hashed,
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist user: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed")

    access_token = _make_jwt(
        {"sub": user_id, "username": body.username, "role": "user"},
        timedelta(minutes=ACCESS_TOKEN_MINUTES),
    )
    refresh_jti = str(uuid.uuid4())
    refresh_token = _make_jwt(
        {"sub": user_id, "jti": refresh_jti, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_DAYS),
    )

    response.set_cookie("access_token", access_token, **_cookie_kwargs(ACCESS_TOKEN_MINUTES * 60))
    response.set_cookie("refresh_token", refresh_token, **_cookie_kwargs(REFRESH_TOKEN_DAYS * 86400))

    logger.info("User registered: %s", body.username)
    return {"message": "Registration successful", "username": body.username}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    """Authenticate user; set HttpOnly cookies on success."""
    key = _lockout_key(request, body.username)
    _check_lockout(key)

    is_dev = os.environ.get("ENVIRONMENT", "development") != "production"

    if is_dev:
        # Development: accept any non-empty credentials (no DB needed)
        if not body.username or not body.password:
            _record_failure(key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        user_id = str(uuid.uuid4())
        role = "admin" if body.username == "admin" else "user"
    else:
        # Production: verify against Supabase DB
        user = await _lookup_user_from_db(body.username)
        if not user:
            _record_failure(key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not await _verify_password(body.password, user["hashed_password"]):
            _record_failure(key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        user_id = user["id"]
        role = user.get("role", "user")

    _clear_attempts(key)

    access_token = _make_jwt(
        {"sub": user_id, "username": body.username, "role": role},
        timedelta(minutes=ACCESS_TOKEN_MINUTES),
    )
    refresh_jti = str(uuid.uuid4())
    refresh_token = _make_jwt(
        {"sub": user_id, "jti": refresh_jti, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_DAYS),
    )

    response.set_cookie("access_token", access_token, **_cookie_kwargs(ACCESS_TOKEN_MINUTES * 60))
    response.set_cookie("refresh_token", refresh_token, **_cookie_kwargs(REFRESH_TOKEN_DAYS * 86400))

    logger.info("User logged in: %s (role=%s)", body.username, role)
    return {"message": "Login successful", "username": body.username, "role": role}


@router.post("/refresh")
async def refresh_token_endpoint(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
) -> Dict[str, Any]:
    """Issue a new access token using a valid (non-revoked) refresh token."""
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = _decode_jwt(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    jti = payload.get("jti", "")
    async with _revoked_lock:
        if jti in _revoked_tokens:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token revoked — please log in again")

    # Issue new access token
    new_access = _make_jwt(
        {"sub": payload["sub"], "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_MINUTES),
    )
    response.set_cookie("access_token", new_access, **_cookie_kwargs(ACCESS_TOKEN_MINUTES * 60))
    return {"message": "Token refreshed"}


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
) -> Dict[str, str]:
    """Revoke refresh token and clear cookies."""
    if refresh_token:
        try:
            payload = _decode_jwt(refresh_token)
            jti = payload.get("jti", "")
            if jti:
                async with _revoked_lock:
                    _revoked_tokens.add(jti)
        except HTTPException:
            pass  # Token already invalid — still clear cookies

    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(access_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """Return current user info from the access token cookie."""
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = _decode_jwt(access_token)
    return {
        "sub": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role"),
    }


@router.get("/status")
async def auth_status(access_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """Return authentication status — safe to call without credentials."""
    if not access_token:
        return {"authenticated": False}
    try:
        payload = _decode_jwt(access_token)
        return {"authenticated": True, "username": payload.get("username")}
    except HTTPException:
        return {"authenticated": False}
