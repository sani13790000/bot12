"""
هندلر مدیریت کاربران — سطح Enterprise

مدیریت کامل کاربران از طریق تلگرام.
شامل: مشاهده، اضافه، حذف، تغییر نقش و مدیریت لایسنس.

دسترسی مورد نیاز:
- مشاهده کاربران: ADMIN و بالاتر
- اضافه/حذف کاربر: ADMIN و بالاتر
- تغییر نقش: SUPER_ADMIN و بالاتر
- مدیریت لایسنس: SUPER_ADMIN و بالاتر
- مدیریت اشتراک: OWNER

نویسنده: MT5 Trading Team
"""

import os
from typing import Optional
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..auth import require_permission, require_role
from ..rbac import Permission, UserRole, ROLE_NAMES_FA, get_role_level
from ...services.rbac_service import rbac_service
from ...services.audit_service import audit_service, AuditAction
from ...core.logger import get_logger

logger = get_logger("telegram.handlers.admin_users")

router = Router(name="admin_users")

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


# ═══════════════════════════════════════════════════════════════
# States برای FSM
# ═══════════════════════════════════════════════════════════════

class AddUserStates(StatesGroup):
    """حالت‌های FSM برای اضافه کردن کاربر"""
    waiting_for_chat_id = State()
    waiting_for_role = State()
    waiting_for_confirm = State()


class RemoveUserStates(StatesGroup):
    """حالت‌های FSM برای حذف کاربر"""
    waiting_for_chat_id = State()
    waiting_for_confirm = State()


class ChangeRoleStates(StatesGroup):
    """حالت‌های FSM برای تغییر نقش"""
    waiting_for_chat_id = State()
    waiting_for_new_role = State()
    waiting_for_confirm = State()


# ═══════════════════════════════════════════════════════════════
# Keyboards
# ═══════════════════════════════════════════════════════════════

def _role_selection_keyboard(prefix: str = "setrole") -> InlineKeyboardMarkup:
    """کیبورد انتخاب نقش"""
    buttons = []
    roles_to_show = [
        UserRole.VIEWER,
        UserRole.USER,
        UserRole.OPERATOR,
        UserRole.TRADER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ]
    row = []
    for i, role in enumerate(roles_to_show):
        row.append(InlineKeyboardButton(
            text=ROLE_NAMES_FA[role],
            callback_data=f"{prefix}:{role.value}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ لغو", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _confirm_keyboard(action: str, data: str) -> InlineKeyboardMarkup:
    """کیبورد تأیید عملیات"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید", callback_data=f"confirm:{action}:{data}"),
            InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel:{action}")
        ]
    ])


def _users_page_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """کیبورد صفحه‌بندی لیست کاربران"""
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"users_page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"users_page:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="users_page:0")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════════════════════════════════════════════════════
# /users — لیست کاربران
# ═══════════════════════════════════════════════════════════════

@router.message(Command("users"))
@require_permission(Permission.VIEW_ALL_USERS)
async def cmd_list_users(message: Message):
    """
    نمایش لیست کامل کاربران
    دسترسی: ADMIN و بالاتر
    """
    await _send_users_list(message, page=0)


@router.callback_query(F.data.startswith("users_page:"))
@require_permission(Permission.VIEW_ALL_USERS)
async def cb_users_page(callback: CallbackQuery):
    """صفحه‌بندی لیست کاربران"""
    page = int(callback.data.split(":")[1])
    await _send_users_list(callback.message, page=page, edit=True)
    await callback.answer()


async def _send_users_list(message: Message, page: int = 0, edit: bool = False):
    """ارسال لیست کاربران با صفحه‌بندی"""
    try:
        users = await rbac_service.get_all_users()
        per_page = 10
        total = len(users)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        start = page * per_page
        page_users = users[start:start + per_page]

        lines = [
            f"👥 <b>لیست کاربران</b> — صفحه {page+1}/{total_pages}",
            f"📊 مجموع: {total} کاربر\n",
        ]
        for u in page_users:
            role_fa = ROLE_NAMES_FA.get(UserRole(u.get("role", "user")), u.get("role", "?"))
            status_emoji = "✅" if u.get("is_active") else "❌"
            lines.append(
                f"{status_emoji} <code>{u.get('telegram_id', '?')}</code> "
                f"| {role_fa} "
                f"| {u.get('username', 'بدون نام')}"
            )

        text = "\n".join(lines)
        kb = _users_page_keyboard(page, total_pages)

        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        logger.error(f"خطا در دریافت لیست کاربران: {e}", exc_info=True)
        await message.answer("❌ خطا در دریافت لیست کاربران.")


# ═══════════════════════════════════════════════════════════════
# /add_user — اضافه کردن کاربر
# ═══════════════════════════════════════════════════════════════

@router.message(Command("add_user"))
@require_permission(Permission.ADD_USER)
async def cmd_add_user(message: Message, state: FSMContext):
    """
    شروع فرآیند اضافه کردن کاربر جدید
    دسترسی: ADMIN و بالاتر
    """
    await state.set_state(AddUserStates.waiting_for_chat_id)
    await message.answer(
        "➕ <b>اضافه کردن کاربر جدید</b>\n\n"
        "Chat ID تلگرام کاربر را وارد کنید:\n"
        "<i>مثال: 123456789</i>\n\n"
        "برای لغو: /cancel",
        parse_mode="HTML"
    )


@router.message(AddUserStates.waiting_for_chat_id)
async def add_user_get_id(message: Message, state: FSMContext):
    """دریافت Chat ID کاربر جدید"""
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Chat ID باید عدد باشد. دوباره وارد کنید:")
        return

    chat_id = int(text)
    await state.update_data(new_chat_id=chat_id)
    await state.set_state(AddUserStates.waiting_for_role)
    await message.answer(
        f"✅ Chat ID: <code>{chat_id}</code>\n\n"
        "نقش کاربر را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_role_selection_keyboard("adduserrole")
    )


@router.callback_query(F.data.startswith("adduserrole:"))
async def add_user_select_role(callback: CallbackQuery, state: FSMContext):
    """انتخاب نقش کاربر جدید"""
    role_val = callback.data.split(":")[1]
    if role_val == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ عملیات لغو شد.")
        await callback.answer()
        return

    try:
        role = UserRole(role_val)
    except ValueError:
        await callback.answer("نقش نامعتبر")
        return

    data = await state.get_data()
    new_chat_id = data["new_chat_id"]
    role_fa = ROLE_NAMES_FA[role]

    await state.update_data(new_role=role_val)
    await state.set_state(AddUserStates.waiting_for_confirm)
    await callback.message.edit_text(
        f"📋 <b>تأیید اضافه کردن کاربر</b>\n\n"
        f"🆔 Chat ID: <code>{new_chat_id}</code>\n"
        f"👤 نقش: {role_fa}\n\n"
        f"آیا مطمئن هستید؟",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard("add_user", f"{new_chat_id}:{role_val}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:add_user:"))
async def add_user_confirm(callback: CallbackQuery, state: FSMContext):
    """تأیید نهایی اضافه کردن کاربر"""
    _, _, payload = callback.data.split(":", 2)
    chat_id_str, role_val = payload.split(":", 1)
    chat_id = int(chat_id_str)
    role = UserRole(role_val)

    try:
        await rbac_service.add_user(
            telegram_id=chat_id,
            role=role,
            added_by=callback.from_user.id
        )
        await audit_service.log(
            action=AuditAction.USER_ADDED,
            performed_by=callback.from_user.id,
            target_user=chat_id,
            details={"role": role_val}
        )
        role_fa = ROLE_NAMES_FA[role]
        await callback.message.edit_text(
            f"✅ <b>کاربر اضافه شد</b>\n\n"
            f"🆔 <code>{chat_id}</code> با نقش {role_fa} اضافه شد.",
            parse_mode="HTML"
        )
        logger.info(f"کاربر {chat_id} با نقش {role_val} توسط {callback.from_user.id} اضافه شد")
    except Exception as e:
        logger.error(f"خطا در اضافه کردن کاربر {chat_id}: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ خطا: {str(e)}")

    await state.clear()
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# /remove_user — حذف کاربر
# ═══════════════════════════════════════════════════════════════

@router.message(Command("remove_user"))
@require_permission(Permission.REMOVE_USER)
async def cmd_remove_user(message: Message, state: FSMContext):
    """
    شروع فرآیند حذف کاربر
    دسترسی: ADMIN و بالاتر
    """
    await state.set_state(RemoveUserStates.waiting_for_chat_id)
    await message.answer(
        "🗑 <b>حذف کاربر</b>\n\n"
        "Chat ID کاربر را وارد کنید:\n"
        "برای لغو: /cancel",
        parse_mode="HTML"
    )


@router.message(RemoveUserStates.waiting_for_chat_id)
async def remove_user_get_id(message: Message, state: FSMContext):
    """دریافت Chat ID کاربر برای حذف"""
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Chat ID باید عدد باشد:")
        return

    chat_id = int(text)
    # بررسی وجود کاربر
    try:
        user = await rbac_service.get_user(chat_id)
        if not user:
            await message.answer(f"❌ کاربر <code>{chat_id}</code> یافت نشد.", parse_mode="HTML")
            await state.clear()
            return
        role_fa = ROLE_NAMES_FA.get(UserRole(user.get("role", "user")), "?")
        await state.update_data(remove_chat_id=chat_id)
        await state.set_state(RemoveUserStates.waiting_for_confirm)
        await message.answer(
            f"⚠️ <b>تأیید حذف کاربر</b>\n\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👤 نقش: {role_fa}\n"
            f"📛 نام: {user.get('username', 'بدون نام')}\n\n"
            f"این عملیات برگشت‌پذیر نیست!",
            parse_mode="HTML",
            reply_markup=_confirm_keyboard("remove_user", str(chat_id))
        )
    except Exception as e:
        logger.error(f"خطا در بررسی کاربر {chat_id}: {e}", exc_info=True)
        await message.answer("❌ خطا در دریافت اطلاعات کاربر.")
        await state.clear()


@router.callback_query(F.data.startswith("confirm:remove_user:"))
async def remove_user_confirm(callback: CallbackQuery, state: FSMContext):
    """تأیید نهایی حذف کاربر"""
    chat_id = int(callback.data.split(":", 2)[2])
    try:
        await rbac_service.remove_user(
            telegram_id=chat_id,
            removed_by=callback.from_user.id
        )
        await audit_service.log(
            action=AuditAction.USER_REMOVED,
            performed_by=callback.from_user.id,
            target_user=chat_id,
            details={}
        )
        await callback.message.edit_text(
            f"✅ کاربر <code>{chat_id}</code> حذف شد.",
            parse_mode="HTML"
        )
        logger.info(f"کاربر {chat_id} توسط {callback.from_user.id} حذف شد")
    except Exception as e:
        logger.error(f"خطا در حذف کاربر {chat_id}: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ خطا: {str(e)}")

    await state.clear()
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# /set_role — تغییر نقش کاربر
# ═══════════════════════════════════════════════════════════════

@router.message(Command("set_role"))
@require_permission(Permission.CHANGE_USER_ROLE)
async def cmd_set_role(message: Message, state: FSMContext):
    """
    شروع فرآیند تغییر نقش کاربر
    دسترسی: SUPER_ADMIN و بالاتر
    """
    await state.set_state(ChangeRoleStates.waiting_for_chat_id)
    await message.answer(
        "🔄 <b>تغییر نقش کاربر</b>\n\n"
        "Chat ID کاربر را وارد کنید:\n"
        "برای لغو: /cancel",
        parse_mode="HTML"
    )


@router.message(ChangeRoleStates.waiting_for_chat_id)
async def set_role_get_id(message: Message, state: FSMContext):
    """دریافت Chat ID برای تغییر نقش"""
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Chat ID باید عدد باشد:")
        return

    chat_id = int(text)
    try:
        user = await rbac_service.get_user(chat_id)
        if not user:
            await message.answer(f"❌ کاربر <code>{chat_id}</code> یافت نشد.", parse_mode="HTML")
            await state.clear()
            return
        current_role = UserRole(user.get("role", "user"))
        current_role_fa = ROLE_NAMES_FA.get(current_role, "?")
        await state.update_data(role_chat_id=chat_id, current_role=current_role.value)
        await state.set_state(ChangeRoleStates.waiting_for_new_role)
        await message.answer(
            f"🔄 <b>تغییر نقش</b>\n\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"نقش فعلی: {current_role_fa}\n\n"
            f"نقش جدید را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_role_selection_keyboard("changerole")
        )
    except Exception as e:
        logger.error(f"خطا در بررسی کاربر {chat_id}: {e}", exc_info=True)
        await message.answer("❌ خطا در دریافت اطلاعات کاربر.")
        await state.clear()


@router.callback_query(F.data.startswith("changerole:"))
async def set_role_select(callback: CallbackQuery, state: FSMContext):
    """انتخاب نقش جدید"""
    role_val = callback.data.split(":")[1]
    if role_val == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ عملیات لغو شد.")
        await callback.answer()
        return

    try:
        new_role = UserRole(role_val)
    except ValueError:
        await callback.answer("نقش نامعتبر")
        return

    data = await state.get_data()
    chat_id = data["role_chat_id"]
    current_role_fa = ROLE_NAMES_FA.get(UserRole(data["current_role"]), "?")
    new_role_fa = ROLE_NAMES_FA[new_role]

    await state.update_data(new_role_val=role_val)
    await state.set_state(ChangeRoleStates.waiting_for_confirm)
    await callback.message.edit_text(
        f"📋 <b>تأیید تغییر نقش</b>\n\n"
        f"🆔 <code>{chat_id}</code>\n"
        f"از: {current_role_fa}\n"
        f"به: {new_role_fa}\n\n"
        f"آیا مطمئن هستید؟",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard("set_role", f"{chat_id}:{role_val}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:set_role:"))
async def set_role_confirm(callback: CallbackQuery, state: FSMContext):
    """تأیید نهایی تغییر نقش"""
    _, _, payload = callback.data.split(":", 2)
    chat_id_str, role_val = payload.split(":", 1)
    chat_id = int(chat_id_str)
    new_role = UserRole(role_val)

    try:
        old_user = await rbac_service.get_user(chat_id)
        old_role = old_user.get("role", "user") if old_user else "unknown"

        await rbac_service.update_user_role(
            telegram_id=chat_id,
            new_role=new_role,
            changed_by=callback.from_user.id
        )
        await audit_service.log(
            action=AuditAction.USER_ROLE_CHANGED,
            performed_by=callback.from_user.id,
            target_user=chat_id,
            details={"old_role": old_role, "new_role": role_val}
        )
        new_role_fa = ROLE_NAMES_FA[new_role]
        await callback.message.edit_text(
            f"✅ نقش کاربر <code>{chat_id}</code> به {new_role_fa} تغییر یافت.",
            parse_mode="HTML"
        )
        logger.info(f"نقش کاربر {chat_id} از {old_role} به {role_val} توسط {callback.from_user.id} تغییر یافت")
    except Exception as e:
        logger.error(f"خطا در تغییر نقش کاربر {chat_id}: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ خطا: {str(e)}")

    await state.clear()
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# /cancel — لغو عملیات جاری
# ═══════════════════════════════════════════════════════════════

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """لغو هر عملیات جاری در FSM"""
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ عملیات لغو شد.")
    else:
        await message.answer("هیچ عملیاتی در جریان نیست.")


# ═══════════════════════════════════════════════════════════════
# Callback: لغو از inline keyboard
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """لغو از طریق inline keyboard"""
    await state.clear()
    await callback.message.edit_text("❌ عملیات لغو شد.")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    """callback بدون عملیات (برای دکمه‌های نمایشی)"""
    await callback.answer()
