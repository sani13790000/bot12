"""
Authentication routes — Security hardened:
  - JWT in HttpOnly Cookie (not body) — prevents XSS token theft
  - Account lockout after MAX_ATTEMPTS failed logins (15 min)
  - SameSite=Lax cookie — CSRF protection
  - /logout clears cookie
  - /refresh issues new token from valid cookie
Author: MT5 Trading Team
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import jwt
import time

from ...core.config import settings
from ...core.logger import get_logger

logger = get_logger("api.auth")
router = APIRouter()
security = HTTPBearer(auto_error=False)

COOKIE_NAME = "galaxy_vast_token"
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes
_FAILED: dict = {}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class TokenResponse(BaseModel):
    message: str
    token_type: str = "cookie"


def _is_locked(email: str) -> bool:
    rec = _FAILED.get(email)
    if not rec:
        return False
    if rec.get("locked_until") and time.time() < rec["locked_until"]:
        return True
    return False


def _record_failure(email: str) -> None:
    rec = _FAILED.setdefault(email, {"count": 0, "locked_until": None})
    rec["count"] += 1
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = time.time() + LOCKOUT_SECONDS
        logger.warning("Account locked: %s", email)


def _clear(email: str) -> None:
    _FAILED.pop(email, None)


def _make_token(sub: str, role: str = "trader") -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": sub, "role": role, "exp": exp, "iat": datetime.utcnow()},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(settings.ENVIRONMENT == "production"),
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def _verify(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _verify(token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response):
    email = body.email.lower().strip()
    if _is_locked(email):
        raise HTTPException(
            status_code=429,
            detail=f"Account locked. Try again in {LOCKOUT_SECONDS // 60} minutes."
        )
    # TODO: replace with real DB lookup
    if body.password != "demo_password":
        _record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear(email)
    _set_cookie(response, _make_token(email))
    logger.info("Login OK: %s", email)
    return TokenResponse(message="Login successful")


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"message": "Logged out"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, user: dict = Depends(get_current_user)):
    _set_cookie(response, _make_token(user["sub"], user.get("role", "trader")))
    return TokenResponse(message="Token refreshed")


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"email": user.get("sub"), "role": user.get("role")}


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, response: Response):
    email = body.email.lower().strip()
    _set_cookie(response, _make_token(email))
    logger.info("Registered: %s", email)
    return TokenResponse(message="Registration successful")
