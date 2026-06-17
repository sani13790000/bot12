"""
روت‌های احراز هویت

این فایل endpoint های مربوط به ورود، ثبت‌نام و مدیریت توکن را تعریف می‌کند.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import jwt

from ...core.config import settings
from ...core.logger import get_logger
from ...database import db
from ...core.exceptions import AuthenticationError, InvalidTokenError

logger = get_logger("api.auth")
router = APIRouter()
security = HTTPBearer()


# =====================================================
# مد‌های Pydantic
# =====================================================

class LoginRequest(BaseModel):
    """درخواست ورود"""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """درخواست ثبت‌نام"""
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    telegram_id: Optional[int] = None


class TokenResponse(BaseModel):
    """پاسخ توکن"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """پاسخ کاربر"""
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    status: str


# =====================================================
# توابع کمکی
# =====================================================

def create_access_token(user_id: str) -> str:
    """ایجاد توکن دسترسی"""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """ایجاد توکن تمدید"""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """اعتبارسنجی توکن"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("توکن منقضی شده است")
    except jwt.InvalidTokenError:
        raise InvalidTokenError("توکن نامعتبر است")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """دریافت کاربر جاری از توکن"""
    token = credentials.credentials
    payload = verify_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("توکن نامعتبر است")

    # دریافت کاربر از دیتابیس
    user = await db.select_one("user_profiles", {"user_id": user_id}, use_admin=True)

    if not user:
        raise AuthenticationError("کاربر یافت نشد")

    if user["status"] != "active":
        raise AuthenticationError("حساب کاربری غیرفعال است")

    return user


# =====================================================
# Endpoints
# =====================================================

@router.post("/register", response_model=dict)
async def register(request: RegisterRequest):
    """
    ثبت‌نام کاربر جدید

    این endpoint یک کاربر جدید ایجاد می‌کند.
    """
    logger.info(f"درخواست ثبت‌نام: {request.email}")

    # بررسی وجود کاربر
    existing = await db.select_one("user_profiles", {"email": request.email}, use_admin=True)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این ایمیل قبلاً ثبت شده است"
        )

    # ایجاد کاربر در Supabase Auth
    try:
        auth_response = db.admin.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "email_confirm": False
        })
    except Exception as e:
        logger.error(f"خطا در ایجاد کاربر: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="خطا در ایجاد حساب کاربری"
        )

    # ایجاد پروفایل
    profile = await db.insert("user_profiles", {
        "user_id": auth_response.user.id,
        "first_name": request.first_name,
        "last_name": request.last_name,
        "telegram_id": request.telegram_id
    }, use_admin=True)

    # ایجاد تنظیمات پیش‌فرض
    await db.insert("user_settings", {
        "user_id": profile["id"]
    }, use_admin=True)

    logger.info(f"کاربر جدید ثبت شد: {request.email}")

    return {
        "success": True,
        "message": "ثبت‌نام موفق بود. لطفاً ایمیل خود را تأیید کنید.",
        "data": {
            "user_id": profile["id"]
        }
    }


@router.post("/login", response_model=dict)
async def login(request: LoginRequest):
    """
    ورود به سیستم

    این endpoint توکن دسترسی و تمدید را برمی‌گرداند.
    """
    logger.info(f"درخواست ورود: {request.email}")

    try:
        # تأیید با Supabase
        auth_response = db.client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
    except Exception as e:
        logger.warning(f"ورود ناموفق برای {request.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ایمیل یا رمز عبور اشتباه است"
        )

    # دریافت پروفایل
    profile = await db.select_one("user_profiles", {"user_id": auth_response.user.id}, use_admin=True)

    # به‌روزرسانی آخرین ورود
    if profile:
        await db.update("user_profiles", {"id": profile["id"]}, {
            "last_login_at": datetime.utcnow().isoformat()
        }, use_admin=True)

    # ایجاد توکن‌ها
    access_token = create_access_token(auth_response.user.id)
    refresh_token = create_refresh_token(auth_response.user.id)

    logger.info(f"ورود موفق: {request.email}")

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": profile["id"] if profile else auth_response.user.id,
                "email": request.email,
                "first_name": profile.get("first_name") if profile else None,
                "last_name": profile.get("last_name") if profile else None,
                "role": profile.get("role", "user") if profile else "user",
                "status": profile.get("status", "active") if profile else "active"
            }
        }
    }


@router.post("/refresh", response_model=dict)
async def refresh_token(refresh_token: str):
    """
    تمدید توکن دسترسی

    این endpoint با استفاده از توکن تمدید، توکن دسترسی جدید برمی‌گرداند.
    """
    payload = verify_token(refresh_token)

    if payload.get("type") != "refresh":
        raise InvalidTokenError("توکن تمدید نامعتبر است")

    user_id = payload.get("sub")
    access_token = create_access_token(user_id)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """
    خروج از سیستم

    این endpoint session کاربر را پایان می‌دهد.
    """
    logger.info(f"خروج کاربر: {user.get('email')}")
    return {
        "success": True,
        "message": "با موفقیت خارج شدید"
    }


@router.get("/me", response_model=dict)
async def get_me(user: dict = Depends(get_current_user)):
    """
    دریافت اطلاعات کاربر جاری
    """
    return {
        "success": True,
        "data": user
    }
