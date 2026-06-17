"""
=====================================================================
هندلرهای کنترل ربات - Production Ready
=====================================================================
این ماژول مسئول مدیریت دستورات کنترلی ربات است:
  /start  - شروع ربات
  /stop   - توقف ربات
  /status - وضعیت ربات
  /close_all    - بستن همه معاملات
  /close_buys   - بستن معاملات خرید
  /close_sells  - بستن معاملات فروش
  /pause  - مکث موقت
  /resume - ادامه

نویسنده: MT5 Trading Team
نسخه: 2.0.0
"""

import logging
import httpx
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..rbac import require_permission, UserPermission
from ..keyboards import get_main_keyboard, get_confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()

# آدرس API داخلی
API_BASE_URL = "http://localhost:8000/api/v1"


def _get_headers(user_id: int) -> dict:
    """ساخت هدر احراز هویت برای API"""
    return {"X-Telegram-User-Id": str(user_id), "Content-Type": "application/json"}


@router.message(Command("stop"))
@require_permission(UserPermission.ADMIN)
async def cmd_stop_bot(message: types.Message, state: FSMContext):
    """
    دستور /stop - توقف کامل ربات
    فقط ادمین‌ها می‌توانند ربات را متوقف کنند.
    قبل از توقف، تأیید درخواست می‌شود.
    """
    keyboard = get_confirm_keyboard(action="stop_bot")
    await message.answer(
        "⚠️ <b>تأیید توقف ربات</b>

"
        "آیا از توقف کامل ربات اطمینان دارید؟
"
        "⚠️ تمام تحلیل‌ها و معاملات جدید متوقف خواهند شد.
"
        "معاملات باز همچنان فعال می‌مانند.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_stop_bot")
@require_permission(UserPermission.ADMIN)
async def confirm_stop_bot(callback: types.CallbackQuery):
    """
    تأیید توقف ربات
    پس از تأیید، سیگنال توقف به سرور ارسال می‌شود.
    """
    await callback.answer()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/stop",
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                await callback.message.edit_text(
                    "🛑 <b>ربات متوقف شد</b>

"
                    "✅ تمام تحلیل‌های جدید متوقف شدند.
"
                    "📊 معاملات باز همچنان فعال هستند.
"
                    f"🕐 زمان توقف: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML"
                )
                logger.info(f"ربات توسط کاربر {callback.from_user.id} متوقف شد")
            else:
                await callback.message.edit_text(
                    f"❌ خطا در توقف ربات: {response.text}",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"خطا در توقف ربات: {e}")
        await callback.message.edit_text(
            f"❌ خطا در اتصال به سرور: {str(e)[:100]}",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "cancel_stop_bot")
async def cancel_stop_bot(callback: types.CallbackQuery):
    """لغو توقف ربات"""
    await callback.answer("❌ عملیات لغو شد")
    await callback.message.edit_text(
        "✅ توقف ربات لغو شد.",
        parse_mode="HTML"
    )


@router.message(Command("status"))
@require_permission(UserPermission.VIEW_STATUS)
async def cmd_status(message: types.Message):
    """
    دستور /status - نمایش وضعیت فعلی ربات
    شامل: وضعیت اجرا، معاملات باز، موجودی، عملکرد امروز
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/control/status",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get("data", {})

                bot_status = "✅ فعال" if status.get("is_running") else "🛑 متوقف"
                analysis_status = "✅ فعال" if status.get("analysis_running") else "🛑 متوقف"

                text = (
                    f"📊 <b>وضعیت ربات</b>
"
                    f"{'─' * 30}
"
                    f"🤖 <b>ربات:</b> {bot_status}
"
                    f"🧠 <b>تحلیل:</b> {analysis_status}
"
                    f"📈 <b>معاملات باز:</b> {status.get('open_trades', 0)}
"
                    f"💰 <b>موجودی:</b> {status.get('balance', 0):.2f}$
"
                    f"📊 <b>سود امروز:</b> {status.get('daily_profit', 0):+.2f}$
"
                    f"🏆 <b>وین ریت هفته:</b> {status.get('weekly_winrate', 0):.1f}%
"
                    f"⚡ <b>سشن فعال:</b> {status.get('active_session', 'نامشخص')}
"
                    f"🕐 <b>آخرین بروزرسانی:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
                )

                await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                await message.answer("❌ خطا در دریافت وضعیت سرور", parse_mode="HTML")

    except Exception as e:
        logger.error(f"خطا در دریافت وضعیت: {e}")
        await message.answer(f"❌ خطا در اتصال به سرور", parse_mode="HTML")


@router.message(Command("close_all"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_all_trades(message: types.Message):
    """
    دستور /close_all - بستن همه معاملات باز
    برای جلوگیری از اشتباه، تأیید درخواست می‌شود.
    """
    keyboard = get_confirm_keyboard(action="close_all")
    await message.answer(
        "⚠️ <b>تأیید بستن همه معاملات</b>

"
        "آیا از بستن تمام معاملات باز اطمینان دارید؟
"
        "⚠️ این عملیات قابل بازگشت نیست.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_all")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_all_trades(callback: types.CallbackQuery):
    """تأیید و اجرای بستن همه معاملات"""
    await callback.answer()
    await callback.message.edit_text("⏳ در حال بستن معاملات...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-all",
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json()
                result = data.get("data", {})
                closed = result.get("closed_count", 0)
                total_pl = result.get("total_profit_loss", 0)
                pl_sign = "+" if total_pl >= 0 else ""

                await callback.message.edit_text(
                    f"✅ <b>همه معاملات بسته شدند</b>

"
                    f"📊 تعداد بسته شده: {closed}
"
                    f"💵 نتیجه کل: {pl_sign}{total_pl:.2f}$
"
                    f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    f"❌ خطا در بستن معاملات: {response.text[:100]}",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"خطا در بستن همه معاملات: {e}")
        await callback.message.edit_text(f"❌ خطا: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("close_buys"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_buy_trades(message: types.Message):
    """
    دستور /close_buys - بستن همه معاملات خرید
    """
    keyboard = get_confirm_keyboard(action="close_buys")
    await message.answer(
        "⚠️ <b>تأیید بستن معاملات خرید</b>

"
        "آیا از بستن تمام معاملات BUY اطمینان دارید؟",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_buys")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_buys(callback: types.CallbackQuery):
    """تأیید و اجرای بستن معاملات خرید"""
    await callback.answer()
    await callback.message.edit_text("⏳ در حال بستن معاملات خرید...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-by-direction",
                json={"direction": "BUY"},
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                await callback.message.edit_text(
                    f"✅ <b>معاملات خرید بسته شدند</b>

"
                    f"📊 تعداد: {data.get('closed_count', 0)}
"
                    f"💵 نتیجه: {data.get('total_profit_loss', 0):+.2f}$",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text("❌ خطا در بستن معاملات", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("close_sells"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_sell_trades(message: types.Message):
    """
    دستور /close_sells - بستن همه معاملات فروش
    """
    keyboard = get_confirm_keyboard(action="close_sells")
    await message.answer(
        "⚠️ <b>تأیید بستن معاملات فروش</b>

"
        "آیا از بستن تمام معاملات SELL اطمینان دارید؟",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_sells")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_sells(callback: types.CallbackQuery):
    """تأیید و اجرای بستن معاملات فروش"""
    await callback.answer()
    await callback.message.edit_text("⏳ در حال بستن معاملات فروش...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-by-direction",
                json={"direction": "SELL"},
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                await callback.message.edit_text(
                    f"✅ <b>معاملات فروش بسته شدند</b>

"
                    f"📊 تعداد: {data.get('closed_count', 0)}
"
                    f"💵 نتیجه: {data.get('total_profit_loss', 0):+.2f}$",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text("❌ خطا در بستن معاملات", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("pause"))
@require_permission(UserPermission.ADMIN)
async def cmd_pause_bot(message: types.Message):
    """
    دستور /pause - مکث موقت ربات (بدون بستن معاملات)
    ربات معاملات جدید نمی‌گیرد اما معاملات باز را مدیریت می‌کند.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/pause",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                await message.answer(
                    "⏸️ <b>ربات در حالت مکث</b>

"
                    "✅ معاملات جدید متوقف شدند.
"
                    "📊 مدیریت معاملات باز ادامه دارد.
"
                    "برای ادامه: /resume",
                    parse_mode="HTML"
                )
            else:
                await message.answer("❌ خطا در مکث ربات", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ خطا: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("resume"))
@require_permission(UserPermission.ADMIN)
async def cmd_resume_bot(message: types.Message):
    """
    دستور /resume - ادامه فعالیت ربات پس از مکث
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/resume",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                await message.answer(
                    "▶️ <b>ربات فعال شد</b>

"
                    "✅ سیستم در حال اسکن بازار است.
"
                    f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.answer("❌ خطا در فعال‌سازی ربات", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ خطا: {str(e)[:100]}", parse_mode="HTML")
