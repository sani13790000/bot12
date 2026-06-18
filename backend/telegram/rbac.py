"""
سیستم نقش‌ها و دسترسی‌ها (RBAC) — نسخه Enterprise

مدیریت کامل نقش‌ها و سطوح دسترسی در ربات تلگرام.

نقش‌ها (از پایین به بالا):
- VIEWER     : فقط مشاهده گزارش‌ها (بدون هیچ کنترلی)
- USER       : کاربر عادی (گزارش‌ها + سیگنال‌ها)
- OPERATOR   : اپراتور (کنترل ربات، بدون تغییر تنظیمات)
- TRADER     : معامله‌گر (همه عملیات معاملاتی)
- ADMIN      : مدیر (مدیریت کاربران + تنظیمات)
- SUPER_ADMIN: مدیر کل (همه دسترسی‌ها)
- OWNER      : مالک سیستم (بالاترین سطح + مدیریت لایسنس و API)

نویسنده: Galaxy Vast Team
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from functools import wraps

from ..core.logger import get_logger

# لاگر اختصاصی برای سیستم RBAC
logger = get_logger("telegram.rbac")



class UserRole(str, Enum):
    """نقش‌های کاربری — ۷ سطح"""
    VIEWER = "viewer"           # فقط مشاهده
    USER = "user"               # کاربر عادی
    OPERATOR = "operator"       # اپراتور (کنترل بدون تنظیمات)
    TRADER = "trader"           # معامله‌گر
    ADMIN = "admin"             # مدیر
    SUPER_ADMIN = "super_admin" # مدیر کل
    OWNER = "owner"             # مالک سیستم


class Permission(str, Enum):
    """دسترسی‌های کامل سیستم"""

    # ─── گزارش‌ها ───────────────────────────────────────────
    VIEW_OWN_REPORTS = "view_own_reports"
    VIEW_DAILY_REPORT = "view_daily_report"
    VIEW_WEEKLY_REPORT = "view_weekly_report"
    VIEW_MONTHLY_REPORT = "view_monthly_report"
    VIEW_PROFIT_REPORT = "view_profit_report"
    VIEW_LOSS_REPORT = "view_loss_report"
    VIEW_WINRATE_REPORT = "view_winrate_report"
    VIEW_ALL_REPORTS = "view_all_reports"

    # ─── سیگنال‌ها ──────────────────────────────────────────
    VIEW_SIGNALS = "view_signals"
    VIEW_LATEST_SIGNAL = "view_latest_signal"
    VIEW_LATEST_DECISION = "view_latest_decision"
    VIEW_SIGNAL_HISTORY = "view_signal_history"

    # ─── معاملات — مشاهده ───────────────────────────────────
    VIEW_TRADES = "view_trades"
    VIEW_OPEN_POSITIONS = "view_open_positions"
    VIEW_TRADE_HISTORY = "view_trade_history"
    VIEW_TRADE_STATS = "view_trade_stats"

    # ─── معاملات — اجرا ─────────────────────────────────────
    CLOSE_ALL_TRADES = "close_all_trades"
    CLOSE_BUY_TRADES = "close_buy_trades"
    CLOSE_SELL_TRADES = "close_sell_trades"

    # ─── کنترل ربات ─────────────────────────────────────────
    START_BOT = "start_bot"
    STOP_BOT = "stop_bot"
    PAUSE_BOT = "pause_bot"
    RESUME_BOT = "resume_bot"
    RESTART_BOT = "restart_bot"
    VIEW_BOT_STATUS = "view_bot_status"

    # ─── مدیریت کاربران ─────────────────────────────────────
    VIEW_ALL_USERS = "view_all_users"
    MANAGE_USERS = "manage_users"
    ADD_USER = "add_user"
    REMOVE_USER = "remove_user"
    CHANGE_USER_ROLE = "change_user_role"

    # ─── لایسنس ─────────────────────────────────────────────
    MANAGE_LICENSES = "manage_licenses"
    VIEW_LICENSES = "view_licenses"
    REVOKE_LICENSE = "revoke_license"
    ISSUE_LICENSE = "issue_license"

    # ─── تنظیمات ────────────────────────────────────────────
    VIEW_SETTINGS = "view_settings"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_RISK_SETTINGS = "manage_risk_settings"
    MANAGE_SYMBOL_SETTINGS = "manage_symbol_settings"

    # ─── اعلان‌ها ────────────────────────────────────────────
    ENTRY_ALERT = "entry_alert"
    EXIT_ALERT = "exit_alert"
    SL_ALERT = "sl_alert"
    TP_ALERT = "tp_alert"
    SESSION_ALERT = "session_alert"
    SYSTEM_ALERT = "system_alert"

    # ─── سیستم — فقط OWNER ──────────────────────────────────
    MANAGE_API_KEYS = "manage_api_keys"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_SUBSCRIPTIONS = "manage_subscriptions"
    SYSTEM_MAINTENANCE = "system_maintenance"
    VIEW_SYSTEM_HEALTH = "view_system_health"


# ═══════════════════════════════════════════════════════════════
# دسترسی‌های هر نقش
# ═══════════════════════════════════════════════════════════════
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {

    # ─── VIEWER: فقط مشاهده گزارش ───────────────────────────
    UserRole.VIEWER: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_BOT_STATUS,
    },

    # ─── USER: کاربر عادی + سیگنال‌ها ──────────────────────
    UserRole.USER: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_BOT_STATUS,
    },

    # ─── OPERATOR: کنترل ربات بدون تغییر تنظیمات ───────────
    UserRole.OPERATOR: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_ALL_REPORTS,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_SIGNAL_HISTORY,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.VIEW_TRADE_STATS,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.PAUSE_BOT,
        Permission.RESUME_BOT,
        Permission.VIEW_BOT_STATUS,
        Permission.VIEW_SETTINGS,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
    },

    # ─── TRADER: همه عملیات معاملاتی ────────────────────────
    UserRole.TRADER: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_ALL_REPORTS,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_SIGNAL_HISTORY,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.VIEW_TRADE_STATS,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.PAUSE_BOT,
        Permission.RESUME_BOT,
        Permission.VIEW_BOT_STATUS,
        Permission.VIEW_SETTINGS,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.SYSTEM_ALERT,
    },

    # ─── ADMIN: مدیریت کاربران + تنظیمات ───────────────────
    UserRole.ADMIN: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_ALL_REPORTS,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_SIGNAL_HISTORY,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.VIEW_TRADE_STATS,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.PAUSE_BOT,
        Permission.RESUME_BOT,
        Permission.RESTART_BOT,
        Permission.VIEW_BOT_STATUS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_USERS,
        Permission.ADD_USER,
        Permission.REMOVE_USER,
        Permission.CHANGE_USER_ROLE,
        Permission.VIEW_LICENSES,
        Permission.VIEW_SETTINGS,
        Permission.MANAGE_SETTINGS,
        Permission.MANAGE_RISK_SETTINGS,
        Permission.MANAGE_SYMBOL_SETTINGS,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.SYSTEM_ALERT,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_SYSTEM_HEALTH,
    },

    # ─── SUPER_ADMIN: همه دسترسی‌های ADMIN + لایسنس ────────
    UserRole.SUPER_ADMIN: {
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_ALL_REPORTS,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_SIGNAL_HISTORY,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.VIEW_TRADE_STATS,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.PAUSE_BOT,
        Permission.RESUME_BOT,
        Permission.RESTART_BOT,
        Permission.VIEW_BOT_STATUS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_USERS,
        Permission.ADD_USER,
        Permission.REMOVE_USER,
        Permission.CHANGE_USER_ROLE,
        Permission.MANAGE_LICENSES,
        Permission.VIEW_LICENSES,
        Permission.REVOKE_LICENSE,
        Permission.ISSUE_LICENSE,
        Permission.VIEW_SETTINGS,
        Permission.MANAGE_SETTINGS,
        Permission.MANAGE_RISK_SETTINGS,
        Permission.MANAGE_SYMBOL_SETTINGS,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.SYSTEM_ALERT,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_SYSTEM_HEALTH,
    },

    # ─── OWNER: بالاترین سطح — همه چیز ─────────────────────
    UserRole.OWNER: {
        # همه دسترسی‌های SUPER_ADMIN
        Permission.VIEW_OWN_REPORTS,
        Permission.VIEW_DAILY_REPORT,
        Permission.VIEW_WEEKLY_REPORT,
        Permission.VIEW_MONTHLY_REPORT,
        Permission.VIEW_PROFIT_REPORT,
        Permission.VIEW_LOSS_REPORT,
        Permission.VIEW_WINRATE_REPORT,
        Permission.VIEW_ALL_REPORTS,
        Permission.VIEW_SIGNALS,
        Permission.VIEW_LATEST_SIGNAL,
        Permission.VIEW_LATEST_DECISION,
        Permission.VIEW_SIGNAL_HISTORY,
        Permission.VIEW_TRADES,
        Permission.VIEW_OPEN_POSITIONS,
        Permission.VIEW_TRADE_HISTORY,
        Permission.VIEW_TRADE_STATS,
        Permission.CLOSE_ALL_TRADES,
        Permission.CLOSE_BUY_TRADES,
        Permission.CLOSE_SELL_TRADES,
        Permission.START_BOT,
        Permission.STOP_BOT,
        Permission.PAUSE_BOT,
        Permission.RESUME_BOT,
        Permission.RESTART_BOT,
        Permission.VIEW_BOT_STATUS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_USERS,
        Permission.ADD_USER,
        Permission.REMOVE_USER,
        Permission.CHANGE_USER_ROLE,
        Permission.MANAGE_LICENSES,
        Permission.VIEW_LICENSES,
        Permission.REVOKE_LICENSE,
        Permission.ISSUE_LICENSE,
        Permission.VIEW_SETTINGS,
        Permission.MANAGE_SETTINGS,
        Permission.MANAGE_RISK_SETTINGS,
        Permission.MANAGE_SYMBOL_SETTINGS,
        Permission.ENTRY_ALERT,
        Permission.EXIT_ALERT,
        Permission.SL_ALERT,
        Permission.TP_ALERT,
        Permission.SESSION_ALERT,
        Permission.SYSTEM_ALERT,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_SYSTEM_HEALTH,
        # دسترسی‌های اختصاصی OWNER
        Permission.MANAGE_API_KEYS,
        Permission.MANAGE_SUBSCRIPTIONS,
        Permission.SYSTEM_MAINTENANCE,
    },
}


# ═══════════════════════════════════════════════════════════════
# نگاشت Command به Permission
# ═══════════════════════════════════════════════════════════════
COMMAND_PERMISSIONS: Dict[str, Permission] = {
    # گزارش‌ها
    "/daily":    Permission.VIEW_DAILY_REPORT,
    "/weekly":   Permission.VIEW_WEEKLY_REPORT,
    "/monthly":  Permission.VIEW_MONTHLY_REPORT,
    "/profit":   Permission.VIEW_PROFIT_REPORT,
    "/loss":     Permission.VIEW_LOSS_REPORT,
    "/winrate":  Permission.VIEW_WINRATE_REPORT,
    "/reports":  Permission.VIEW_ALL_REPORTS,

    # سیگنال‌ها
    "/signal":   Permission.VIEW_LATEST_SIGNAL,
    "/signals":  Permission.VIEW_SIGNALS,
    "/decision": Permission.VIEW_LATEST_DECISION,
    "/history_signals": Permission.VIEW_SIGNAL_HISTORY,

    # معاملات — مشاهده
    "/trades":    Permission.VIEW_TRADES,
    "/positions": Permission.VIEW_OPEN_POSITIONS,
    "/history":   Permission.VIEW_TRADE_HISTORY,
    "/stats":     Permission.VIEW_TRADE_STATS,

    # معاملات — اجرا
    "/close_all":  Permission.CLOSE_ALL_TRADES,
    "/close_buy":  Permission.CLOSE_BUY_TRADES,
    "/close_sell": Permission.CLOSE_SELL_TRADES,

    # کنترل ربات
    "/start_bot":  Permission.START_BOT,
    "/stop_bot":   Permission.STOP_BOT,
    "/pause":      Permission.PAUSE_BOT,
    "/resume":     Permission.RESUME_BOT,
    "/restart":    Permission.RESTART_BOT,
    "/status":     Permission.VIEW_BOT_STATUS,

    # مدیریت کاربران
    "/users":       Permission.VIEW_ALL_USERS,
    "/add_user":    Permission.ADD_USER,
    "/remove_user": Permission.REMOVE_USER,
    "/set_role":    Permission.CHANGE_USER_ROLE,

    # لایسنس
    "/licenses":       Permission.VIEW_LICENSES,
    "/revoke_license": Permission.REVOKE_LICENSE,
    "/issue_license":  Permission.ISSUE_LICENSE,

    # تنظیمات
    "/settings":      Permission.VIEW_SETTINGS,
    "/set_risk":      Permission.MANAGE_RISK_SETTINGS,
    "/set_symbol":    Permission.MANAGE_SYMBOL_SETTINGS,

    # سیستم
    "/audit":         Permission.VIEW_AUDIT_LOGS,
    "/health":        Permission.VIEW_SYSTEM_HEALTH,
    "/maintenance":   Permission.SYSTEM_MAINTENANCE,
    "/subscriptions": Permission.MANAGE_SUBSCRIPTIONS,
    "/api_keys":      Permission.MANAGE_API_KEYS,
}


# ═══════════════════════════════════════════════════════════════
# سطح عددی هر نقش (برای مقایسه)
# ═══════════════════════════════════════════════════════════════
ROLE_LEVELS: Dict[UserRole, int] = {
    UserRole.VIEWER:      0,
    UserRole.USER:        1,
    UserRole.OPERATOR:    2,
    UserRole.TRADER:      3,
    UserRole.ADMIN:       4,
    UserRole.SUPER_ADMIN: 5,
    UserRole.OWNER:       6,
}

# نام فارسی هر نقش
ROLE_NAMES_FA: Dict[UserRole, str] = {
    UserRole.VIEWER:      "بیننده",
    UserRole.USER:        "کاربر",
    UserRole.OPERATOR:    "اپراتور",
    UserRole.TRADER:      "معامله‌گر",
    UserRole.ADMIN:       "مدیر",
    UserRole.SUPER_ADMIN: "مدیر کل",
    UserRole.OWNER:       "مالک",
}


# ═══════════════════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════════════════

def get_role_permissions(role: UserRole) -> Set[Permission]:
    """
    دریافت مجموعه دسترسی‌های یک نقش

    Args:
        role: نقش کاربری

    Returns:
        مجموعه Permission‌ها
    """
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """
    بررسی اینکه آیا نقش دسترسی مشخصی دارد

    Args:
        role: نقش کاربری
        permission: دسترسی مورد بررسی

    Returns:
        True اگر دسترسی موجود باشد
    """
    return permission in get_role_permissions(role)


def get_role_level(role: UserRole) -> int:
    """
    دریافت سطح عددی نقش برای مقایسه

    Args:
        role: نقش

    Returns:
        عدد سطح (0=VIEWER ... 6=OWNER)
    """
    return ROLE_LEVELS.get(role, 0)


def is_role_at_least(role: UserRole, minimum: UserRole) -> bool:
    """
    بررسی اینکه آیا نقش حداقل برابر minimum است

    Args:
        role: نقش کاربر
        minimum: حداقل نقش مورد نیاز

    Returns:
        True اگر role >= minimum
    """
    return get_role_level(role) >= get_role_level(minimum)


def get_min_role_for_permission(permission: Permission) -> Optional[UserRole]:
    """
    یافتن حداقل نقشی که دسترسی مشخص را دارد

    Args:
        permission: دسترسی

    Returns:
        حداقل نقش یا None
    """
    ordered = [
        UserRole.VIEWER,
        UserRole.USER,
        UserRole.OPERATOR,
        UserRole.TRADER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
        UserRole.OWNER,
    ]
    for role in ordered:
        if permission in ROLE_PERMISSIONS[role]:
            return role
    return None


def get_role_fa_name(role: UserRole) -> str:
    """
    دریافت نام فارسی نقش

    Args:
        role: نقش

    Returns:
        نام فارسی
    """
    return ROLE_NAMES_FA.get(role, str(role.value))


# ═══════════════════════════════════════════════════════════════
# پیام‌های فارسی خطای دسترسی
# ═══════════════════════════════════════════════════════════════
PERMISSION_DENIED_MESSAGES = {
    "not_registered": """
🚫 <b>دسترسی محدود</b>

⚠️ شما در سیستم ثبت نشده‌اید.

برای استفاده از ربات:
1️⃣ در داشبورد ثبت‌نام کنید
2️⃣ لایسنس معتبر تهیه کنید
3️⃣ اکانت تلگرام خود را متصل کنید

📞 پشتیبانی: @GalaxyVast_Support
    """,

    "no_permission": """
🚫 <b>دسترسی غیرمجاز</b>

⚠️ شما دسترسی به این بخش را ندارید.

نقش فعلی شما: {role}
حداقل نقش مورد نیاز: {required_role}

برای ارتقا با پشتیبانی تماس بگیرید.
📞 @GalaxyVast_Support
    """,

    "license_expired": """
🚫 <b>لایسنس منقضی</b>

⚠️ لایسنس شما منقضی شده است.

برای تمدید با پشتیبانی تماس بگیرید.
📞 @GalaxyVast_Support
    """,

    "license_invalid": """
🚫 <b>لایسنس نامعتبر</b>

⚠️ لایسنس شما معتبر نیست یا suspended شده.

برای حل مشکل با پشتیبانی تماس بگیرید.
📞 @GalaxyVast_Support
    """,

    "feature_not_allowed": """
🚫 <b>ویژگی مجاز نیست</b>

⚠️ این ویژگی در پلن شما موجود نیست.

برای دسترسی پلن خود را ارتقا دهید.
📞 @GalaxyVast_Support
    """,

    "operator_only": """
🔒 <b>فقط اپراتور و بالاتر</b>

⚠️ این عملیات نیاز به سطح دسترسی اپراتور دارد.

نقش فعلی: {role}
    """,

    "owner_only": """
👑 <b>فقط مالک سیستم</b>

⚠️ این عملیات فقط توسط مالک سیستم قابل انجام است.
    """,
}


def get_permission_denied_message(
    reason: str,
    role: Optional[str] = None,
    required_role: Optional[str] = None
) -> str:
    """
    دریافت پیام فارسی خطای دسترسی

    Args:
        reason: دلیل رد شدن دسترسی
        role: نقش فعلی کاربر
        required_role: نقش مورد نیاز

    Returns:
        پیام آماده برای ارسال به تلگرام
    """
    template = PERMISSION_DENIED_MESSAGES.get(reason, "🚫 خطای دسترسی")

    role_display = ROLE_NAMES_FA.get(
        UserRole(role) if role else None,
        role or "نامشخص"
    ) if role else "نامشخص"

    required_display = ROLE_NAMES_FA.get(
        UserRole(required_role) if required_role else None,
        required_role or "نامشخص"
    ) if required_role else "نامشخص"

    try:
        return template.format(role=role_display, required_role=required_display)
    except (KeyError, AttributeError):
        return template
