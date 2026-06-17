"""
Decorator و Middleware برای Authorization

سیستم میان‌افزار و تزئین‌کننده برای بررسی دسترسی در هندلرهای تلگرام.

نویسنده: MT5 Trading Team
"""

from functools import wraps
from typing import Callable, Optional, Awaitable, Any
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import types, Dispatcher
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from ..telegram.rbac import (
    Permission, UserRole, has_permission,
    COMMAND_PERMISSIONS, get_permission_denied_message,
    get_min_role_for_permission
)
from ..services.rbac_service import rbac_service
from ..services.audit_service import audit_service, AuditAction
from ..core.logger import get_logger

logger = get_logger("telegram.auth")


# =====================================================
# Rate Limiting
# =====================================================

class RateLimiter:
    """
    محدودکننده نرخ درخواست

    جلوگیری از flood و spam
    """

    def __init__(self):
        self._requests: dict = defaultdict(list)
        self.limits = {
            "default": {"max": 30, "window": 60},      # 30 پیام در 60 ثانیه
            "command": {"max": 10, "window": 60},      # 10 دستور در 60 ثانیه
            "sensitive": {"max": 5, "window": 60},      # 5 دستور حساس در 60 ثانیه
        }

    def check(self, user_id: int, command_type: str = "default") -> bool:
        """
        بررسی محدودیت

        Args:
            user_id: شناسه کاربر
            command_type: نوع دستور

        Returns:
            True اگر مجاز باشد
        """
        now = datetime.utcnow()
        limit = self.limits.get(command_type, self.limits["default"])

        # پاک کردن درخواست‌های قدیمی
        user_requests = self._requests[user_id]
        window_start = now - timedelta(seconds=limit["window"])
        self._requests[user_id] = [
            r for r in user_requests
            if r > window_start
        ]

        # بررسی تعداد
        if len(self._requests[user_id]) >= limit["max"]:
            return False

        # ثبت درخواست جدید
        self._requests[user_id].append(now)
        return True

    def get_remaining_time(self, user_id: int, command_type: str = "default") -> int:
        """زمان باقی‌مانده تا آزاد شدن"""
        limit = self.limits.get(command_type, self.limits["default"])
        user_requests = self._requests.get(user_id, [])

        if len(user_requests) < limit["max"]:
            return 0

        oldest = min(user_requests)
        window_end = oldest + timedelta(seconds=limit["window"])
        remaining = (window_end - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))


# نمونه گلوبال
rate_limiter = RateLimiter()


# =====================================================
# Decorators
# =====================================================

def require_permission(permission: Permission) -> Callable:
    """
    Decorator برای بررسی دسترسی command

    Args:
        permission: دسترسی مورد نیاز

    Example:
        @require_permission(Permission.CLOSE_ALL_TRADES)
        async def close_all_trades(message: types.Message):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, *args, **kwargs):
            # استخراج telegram_user_id
            if isinstance(event, Message):
                telegram_user_id = event.from_user.id
                reply_func = event.answer
            elif isinstance(event, CallbackQuery):
                telegram_user_id = event.from_user.id
                reply_func = event.message.edit_text
                await event.answer()
            else:
                return await func(event, *args, **kwargs)

            # بررسی rate limit
            command_type = "sensitive" if permission in [
                Permission.CLOSE_ALL_TRADES,
                Permission.CLOSE_BUY_TRADES,
                Permission.CLOSE_SELL_TRADES,
                Permission.START_BOT,
                Permission.STOP_BOT,
            ] else "command"

            if not rate_limiter.check(telegram_user_id, command_type):
                remaining = rate_limiter.get_remaining_time(telegram_user_id, command_type)
                await reply_func(
                    f"⏳ لطفاً {remaining} ثانیه صبر کنید.",
                    parse_mode="HTML"
                )
                return

            # بررسی دسترسی
            check_result = await rbac_service.check_permission(
                telegram_user_id, permission
            )

            if not check_result.get("allowed"):
                # ثبت لاگ تلاش غیرمجاز
                logger.warning(
                    f"تلاش دسترسی غیرمجاز - User: {telegram_user_id}, "
                    f"Permission: {permission.value}"
                )

                await reply_func(
                    check_result.get("message", "🚫 دسترسی غیرمجاز"),
                    parse_mode="HTML"
                )
                return

            # ثبت audit log
            await audit_service.log(
                action=AuditAction.TRADE_CLOSE if "close" in permission.value else AuditAction.SETTINGS_CHANGE,
                user_id=check_result.get("user_id"),
                resource_type="telegram_command",
                resource_id=permission.value,
                details={"telegram_user_id": telegram_user_id}
            )

            # ذخیره info در event برای استفاده بعدی
            if isinstance(event, Message):
                event.user_role = check_result.get("role")
                event.db_user_id = check_result.get("user_id")

            # اجرای hندلر
            return await func(event, *args, **kwargs)

        return wrapper
    return decorator


def require_role(min_role: UserRole) -> Callable:
    """
    Decorator برای بررسی حداقل نقش

    Args:
        min_role: حداقل نقش مورد نیاز

    Example:
        @require_role(UserRole.ADMIN)
        async def manage_users(message: types.Message):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, *args, **kwargs):
            if isinstance(event, Message):
                telegram_user_id = event.from_user.id
                reply_func = event.answer
            elif isinstance(event, CallbackQuery):
                telegram_user_id = event.from_user.id
                reply_func = event.message.edit_text
                await event.answer()
            else:
                return await func(event, *args, **kwargs)

            # دریافت نقش کاربر
            user_role = await rbac_service.get_user_role(telegram_user_id)

            if not user_role:
                await reply_func(
                    get_permission_denied_message("not_registered"),
                    parse_mode="HTML"
                )
                return

            # مقایسه سطح نقش
            from ..telegram.rbac import get_role_level
            user_level = get_role_level(user_role)
            required_level = get_role_level(min_role)

            if user_level < required_level:
                await reply_func(
                    get_permission_denied_message("no_permission", user_role.value, min_role.value),
                    parse_mode="HTML"
                )
                return

            return await func(event, *args, **kwargs)

        return wrapper
    return decorator


def rate_limit(limit_type: str = "command") -> Callable:
    """
    Decorator برای محدودیت نرخ

    Args:
        limit_type: نوع محدودیت
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, *args, **kwargs):
            if isinstance(event, Message):
                telegram_user_id = event.from_user.id
                reply_func = event.answer
            elif isinstance(event, CallbackQuery):
                telegram_user_id = event.from_user.id
                reply_func = event.message.edit_text
                await event.answer()
            else:
                return await func(event, *args, **kwargs)

            if not rate_limiter.check(telegram_user_id, limit_type):
                remaining = rate_limiter.get_remaining_time(telegram_user_id, limit_type)
                await reply_func(
                    f"⏳ لطفاً {remaining} ثانیه صبر کنید.",
                    parse_mode="HTML"
                )
                return

            return await func(event, *args, **kwargs)

        return wrapper
    return decorator


def audit_log(action_type: str) -> Callable:
    """
    Decorator برای ثبت لاگ عملیات

    Args:
        action_type: نوع عملیات
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, *args, **kwargs):
            # استخراج اطلاعات
            if isinstance(event, Message):
                telegram_user_id = event.from_user.id
                command = event.text or ""
            elif isinstance(event, CallbackQuery):
                telegram_user_id = event.from_user.id
                command = event.data or ""
                await event.answer()
            else:
                return await func(event, *args, **kwargs)

            # دریافت user_id از دیتابیس
            user = await rbac_service.get_user_by_telegram_id(telegram_user_id)
            db_user_id = user.get("id") if user else None

            # اجرای هندلر
            result = await func(event, *args, **kwargs)

            # ثبت لاگ
            await audit_service.log(
                action=AuditAction.SETTINGS_CHANGE,
                user_id=db_user_id,
                resource_type="telegram_command",
                resource_id=command[:50],
                details={"telegram_user_id": telegram_user_id, "action_type": action_type}
            )

            return result

        return wrapper
    return decorator


# =====================================================
# Filters
# =====================================================

class PermissionFilter(BaseFilter):
    """
    فیلتر برای بررسی دسترسی
    """

    def __init__(self, permission: Permission):
        self.permission = permission

    async def __call__(self, message: Message) -> bool:
        telegram_user_id = message.from_user.id

        check = await rbac_service.check_permission(
            telegram_user_id, self.permission
        )

        return check.get("allowed", False)


class RoleFilter(BaseFilter):
    """
    فیلتر برای بررسی نقش
    """

    def __init__(self, *roles: UserRole):
        self.roles = set(roles)

    async def __call__(self, message: Message) -> bool:
        telegram_user_id = message.from_user.id

        role = await rbac_service.get_user_role(telegram_user_id)

        return role in self.roles if role else False


class RegisteredUserFilter(BaseFilter):
    """
    فیلتر برای کاربران ثبت شده
    """

    async def __call__(self, message: Message) -> bool:
        telegram_user_id = message.from_user.id

        user = await rbac_service.get_user_by_telegram_id(telegram_user_id)

        return user is not None


# =====================================================
# Middleware
# =====================================================

class AuthorizationMiddleware:
    """
    میان‌افزار برای بررسی دسترسی همه پیام‌ها
    """

    def __init__(self):
        self.enabled = True

    async def __call__(self, handler, event, data):
        """اجرای میان‌افزار"""
        if not self.enabled:
            return await handler(event, data)

        # فقط برای Message و CallbackQuery
        if isinstance(event, Message):
            telegram_user_id = event.from_user.id
            command = event.text or ""

        elif isinstance(event, CallbackQuery):
            telegram_user_id = event.from_user.id
            command = event.data or ""
            await event.answer()

        else:
            return await handler(event, data)

        # بررسی rate limit عمومی
        if not rate_limiter.check(telegram_user_id, "default"):
            if isinstance(event, Message):
                await event.answer("⏳ تعداد درخواست‌ها زیاد است. کمی صبر کنید.")
            return

        # بررسی دسترسی اگر command است
        if command.startswith("/"):
            check = await rbac_service.check_command_permission(
                telegram_user_id, command
            )

            if not check.get("allowed"):
                logger.warning(
                    f"تلاش دسترسی غیرمجاز به command: {command} "
                    f"توسط {telegram_user_id}"
                )

                if isinstance(event, Message):
                    await event.answer(
                        check.get("message", "🚫 دسترسی غیرمجاز"),
                        parse_mode="HTML"
                    )
                return

        # اجرای هندلر
        return await handler(event, data)


# نمونه گلوبال
authorization_middleware = AuthorizationMiddleware()
