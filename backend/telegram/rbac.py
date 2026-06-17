"""
سیستم نقش‌ها و دسترسی‌ها (RBAC)

مدیریت نقش‌ها و سطوح دسترسی در ربات تلگرام.

نقش‌ها:
- user: کاربر عادی (فقط گزارش‌ها و اطلاعات)
- trader: معامله‌گر (commandهای معاملاتی)
- admin: مدیر (مدیریت کاربران و تنظیمات)
- super_admin: مدیر کل (دسترسی کامل)

نویسنده: MT5 Trading Team
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from functools import wraps


class UserRole(str, Enum):
    """نقش‌های کاربری"""
    USER = "user"
    TRADER = "trader"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class Permission(str, Enum):
    """دسترسی‌ها"""
    # گزارش‌ها (برای همه به جز user محدود)
    VIEW_OWN_REPORTS = "view_own_reports"
    VIEW_DAILY_REPORT = "view_daily_report"
    VIEW_WEEKLY_REPORT = "view_weekly_report"
    VIEW_MONTHLY_REPORT = "view_monthly_report"

    # سیگنال‌ها
    VIEW_SIGNALS = "view_signals"
    VIEW_LATEST_SIGNAL = "view_latest_signal"
    VIEW_LATEST_DECISION = "view_latest_decision"

    # معاملات - مشاهده
    VIEW_TRADES = "view_trades"
    VIEW_OPEN_POSITIONS = "view_open_positions"
    VIEW_TRADE_HISTORY = "view_trade_history"

    # معاملات - اجرا
    CLOSE_ALL_TRADES = "close_all_trades"
    CLOSE_BUY_TRADES = "close_buy_trades"
    CLOSE_SELL_TRADES = "close_sell_trades"

    # مدیریت
    START_BOT = "start_bot"
    STOP_BOT = "stop_bot"
    MANAGE_USERS = "manage_users"
    MANAGE_LICENSES = "manage_licenses"
    VIEW_ALL_USERS = "view_all_users"

    # اعلان‌ها
    ENTRY_ALERT = "entry_alert"
    EXIT_ALERT = "exit_alert"
    SL_ALERT = "sl_alert"
    TP_ALERT = "tp_alert"
    SESSION_ALERT = "session_alert"

    # تنظیمات
    MANAGE_SETTINGS = "manage_settings"


# دسترسی‌های هر نقش
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.USER: {
        # کاربر عادی فقط گزارش‌های خود را می‌بیند
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
    },

    UserRole.TRADER: {
        # معامله‌گر همه دسترسی‌های معاملاتی
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
    },

    UserRole.ADMIN: {
        # مدیر همه دسترسی‌های trader + مدیریت
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.MANAGE_USERS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_SETTINGS,
    },

    UserRole.SUPER_ADMIN: {
        # مدیر کل دسترسی کامل
        # همه دسترسی‌ها
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.MANAGE_USERS,
        Permission.MANAGE_LICENSES,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_SETTINGS,
    },
}


# Commandها و دسترسی مورد نیاز
COMMAND_PERMISSIONS: Dict[str, Permission] = {
    # گزارش‌ها
    "/daily": Permission.VIEW_DAILY_REPORT,
    "/weekly": Permission.VIEW_WEEKLY_REPORT,
    "/monthly": Permission.VIEW_MONTHLY_REPORT,
    "/profit": Permission.VIEW_OWN_REPORTS,
    "/loss": Permission.VIEW_OWN_REPORTS,
    "/winrate": Permission.VIEW_OWN_REPORTS,

    # سیگنال‌ها
    "/signal": Permission.VIEW_LATEST_SIGNAL,
    "/decision": Permission.VIEW_LATEST_DECISION,

    # معاملات
    "/trades": Permission.VIEW_TRADES,
    "/positions": Permission.VIEW_OPEN_POSITIONS,
    "/history": Permission.VIEW_TRADE_HISTORY,
    "/close_all": Permission.CLOSE_ALL_TRADES,
    "/close_buy": Permission.CLOSE_BUY_TRADES,
    "/close_sell": Permission.CLOSE_SELL_TRADES,

    # مدیریت
    "/start_bot": Permission.START_BOT,
    "/stop_bot": Permission.STOP_BOT,
    "/users": Permission.VIEW_ALL_USERS,

    # اعلان‌ها
    "/alert_entry": Permission.ENTRY_ALERT,
    "/alert_exit": Permission.EXIT_ALERT,
    "/alert_sl": Permission.SL_ALERT,
    "/alert_tp": Permission.TP_ALERT,
    "/alert_session": Permission.SESSION_ALERT,
}


def get_role_permissions(role: UserRole) -> Set[Permission]:
    """
    دریافت دسترسی‌های یک نقش

    Args:
        role: نقش کاربری

    Returns:
        مجموعه دسترسی‌ها
    """
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """
    بررسی دسترسی

    Args:
        role: نقش کاربری
        permission: دسترسی مورد نظر

    Returns:
        True اگر دسترسی باشد
    """
    return permission in get_role_permissions(role)


def get_role_level(role: UserRole) -> int:
    """
    دریافت سطح نقش (برای مقایسه)

    Args:
        role: نقش

    Returns:
        سطح (عدد)
    """
    levels = {
        UserRole.USER: 0,
        UserRole.TRADER: 1,
        UserRole.ADMIN: 2,
        UserRole.SUPER_ADMIN: 3
    }
    return levels.get(role, 0)


def get_min_role_for_permission(permission: Permission) -> Optional[UserRole]:
    """
    دریافت حداقل نقش برای یک دسترسی

    Args:
        permission: دسترسی

    Returns:
        حداقل نقش
    """
    for role in [UserRole.USER, UserRole.TRADER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        if permission in ROLE_PERMISSIONS[role]:
            return role
    return None


# پیام‌های فارسی برای خطای دسترسی
PERMISSION_DENIED_MESSAGES = {
    "not_registered": """
🚫 <b>دسترسی محدود</b>

⚠️ شما در سیستم ثبت نشده‌اید.

برای استفاده از ربات:
1️⃣ در داشبورد ثبت‌نام کنید
2️⃣ لایسنس معتبر تهیه کنید
3️⃣ اکانت تلگرام خود را متصل کنید

📞 پشتیبانی: @MT5Trading_Support
    """,

    "no_permission": """
🚫 <b>دسترسی غیرمجاز</b>

⚠️ شما دسترسی به این بخش را ندارید.

نقش فعلی شما: {role}
دسترسی مورد نیاز: {required_role}

برای ارتقا به نقش بالاتر با پشتیبانی تماس بگیرید.
    """,

    "license_expired": """
🚫 <b>لایسنس منقضی</b>

⚠️ لایسنس شما منقضی شده است.

برای تمدید با پشتیبانی تماس بگیرید.
    """,

    "license_invalid": """
🚫 <b>لایسنس نامعتبر</b>

⚠️ لایسنس شما معتبر نیست یا suspended شده.

برای حل مشکل با پشتیبانی تماس بگیرید.
    """,

    "feature_not_allowed": """
🚫 <b>ویژگی مجاز نیست</b>

⚠️ این ویژگی در پلن شما موجود نیست.

برای دسترسی به این ویژگی پلن خود را ارتقا دهید.
    """,
}


def get_permission_denied_message(
    reason: str,
    role: Optional[str] = None,
    required_role: Optional[str] = None
) -> str:
    """
    دریافت پیام خطای دسترسی

    Args:
        reason: دلیل خطا
        role: نقش فعلی
        required_role: نقش مورد نیاز

    Returns:
        پیام خطا
    """
    template = PERMISSION_DENIED_MESSAGES.get(reason, "🚫 خطای دسترسی")

    if role and required_role:
        role_names = {
            "user": "کاربر",
            "trader": "معامله‌گر",
            "admin": "مدیر",
            "super_admin": "مدیر کل"
        }
        template = template.format(
            role=role_names.get(role, role),
            required_role=role_names.get(required_role, required_role)
        )

    return template
