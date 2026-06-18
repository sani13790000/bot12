"""
===============================================================================
Galaxy Vast AI Trading Platform
هندلر تلگرام برای Semi-Auto Mode

این هندلر پیام‌های تأیید/رد سیگنال را از تلگرام مدیریت می‌کند.
کاربر با زدن ✅ معامله را تأیید یا با ❌ رد می‌کند.

نویسنده: Galaxy Vast Team
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ...execution.semi_auto import PendingSignal, semi_auto_manager
from ...core.logger import get_logger
from ..rbac import Permission, require_permission

logger = get_logger("telegram.handlers.semi_auto")
router = Router(name="semi_auto")


def build_signal_keyboard(signal_id: str) -> InlineKeyboardMarkup:
    """
    ساخت keyboard inline برای تأیید/رد سیگنال

    ورودی:
        signal_id: شناسه سیگنال

    خروجی:
        InlineKeyboardMarkup با دکمه‌های تأیید و رد
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید و اجرا",
                    callback_data=f"approve_signal:{signal_id}",
                ),
                InlineKeyboardButton(
                    text="❌ رد سیگنال",
                    callback_data=f"reject_signal:{signal_id}",
                ),
            ]
        ]
    )


def format_signal_message(signal: PendingSignal) -> str:
    """
    فرمت‌بندی پیام سیگنال برای نمایش در تلگرام

    ورودی:
        signal: سیگنال در انتظار تأیید

    خروجی:
        متن فارسی آماده برای ارسال
    """
    direction_emoji = "🟢" if signal.action == "BUY" else "🔴"
    direction_fa = "خرید" if signal.action == "BUY" else "فروش"

    return (
        f"🌌 <b>Galaxy Vast — سیگنال در انتظار تأیید</b>

"
        f"{direction_emoji} <b>جهت:</b> {direction_fa}
"
        f"📊 <b>نماد:</b> {signal.symbol}

"
        f"💰 <b>قیمت ورود:</b> {signal.entry_price:.5f}
"
        f"🛑 <b>استاپ لاس:</b> {signal.stop_loss:.5f}
"
        f"🎯 <b>تیک پرافیت ۱:</b> {signal.take_profit_1:.5f}
"
        f"🎯 <b>تیک پرافیت ۲:</b> {signal.take_profit_2:.5f}

"
        f"📦 <b>حجم:</b> {signal.lot_size:.2f} لات
"
        f"⚠️ <b>ریسک:</b> {signal.risk_percent:.1f}٪
"
        f"📐 <b>نسبت R:R:</b> 1:{signal.rr_ratio:.1f}
"
        f"🧠 <b>امتیاز اطمینان:</b> {signal.confidence_score:.0f}٪

"
        f"📝 <b>تحلیل:</b> {signal.market_context}

"
        f"⏰ <b>زمان باقی‌مانده:</b> {signal.remaining_seconds} ثانیه

"
        f"<i>برای اجرای معامله ✅ بزنید</i>"
    )


@router.callback_query(lambda c: c.data and c.data.startswith("approve_signal:"))
@require_permission(Permission.EXECUTE_SIGNAL)
async def handle_approve_signal(callback: CallbackQuery) -> None:
    """
    مدیریت تأیید سیگنال توسط کاربر

    وقتی کاربر ✅ می‌زند این تابع اجرا می‌شود.
    """
    signal_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    signal = await semi_auto_manager.approve_signal(signal_id, user_id)

    if signal is None:
        await callback.answer(
            "⚠️ سیگنال منقضی شده یا پیدا نشد",
            show_alert=True,
        )
        return

    # ویرایش پیام اصلی با وضعیت جدید
    await callback.message.edit_text(
        f"✅ <b>سیگنال تأیید شد</b>

"
        f"📊 {signal.symbol} {signal.action}
"
        f"💰 ورود: {signal.entry_price:.5f}
"
        f"👤 تأیید توسط: {callback.from_user.full_name}

"
        f"<i>در حال اجرا...</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer("✅ معامله در صف اجرا قرار گرفت")
    logger.info(f"سیگنال {signal_id[:8]} تأیید شد توسط {user_id}")


@router.callback_query(lambda c: c.data and c.data.startswith("reject_signal:"))
@require_permission(Permission.VIEW_SIGNALS)
async def handle_reject_signal(callback: CallbackQuery) -> None:
    """
    مدیریت رد سیگنال توسط کاربر

    وقتی کاربر ❌ می‌زند این تابع اجرا می‌شود.
    """
    signal_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    signal = await semi_auto_manager.reject_signal(signal_id, user_id)

    if signal is None:
        await callback.answer(
            "⚠️ سیگنال منقضی شده یا پیدا نشد",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        f"❌ <b>سیگنال رد شد</b>

"
        f"📊 {signal.symbol} {signal.action}
"
        f"👤 رد توسط: {callback.from_user.full_name}",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer("❌ سیگنال لغو شد")
    logger.info(f"سیگنال {signal_id[:8]} رد شد توسط {user_id}")


@router.message(Command("pending_signals"))
@require_permission(Permission.VIEW_SIGNALS)
async def show_pending_signals(message: Message) -> None:
    """
    نمایش لیست سیگنال‌های در انتظار تأیید
    """
    pending = await semi_auto_manager.get_pending_signals()

    if not pending:
        await message.answer("📭 هیچ سیگنال در انتظار تأییدی وجود ندارد")
        return

    text = f"📋 <b>سیگنال‌های در انتظار تأیید ({len(pending)})</b>\n\n"
    for sig in pending:
        direction_fa = "خرید 🟢" if sig.action == "BUY" else "فروش 🔴"
        text += (
            f"• {sig.symbol} — {direction_fa}\n"
            f"  امتیاز: {sig.confidence_score:.0f}٪ | "
            f"باقی: {sig.remaining_seconds}ث\n"
        )

    await message.answer(text, parse_mode="HTML")


def register_semi_auto_handlers(router_parent: Router) -> None:
    """
    ثبت هندلرهای Semi-Auto در router اصلی

    ورودی:
        router_parent: router اصلی dispatcher
    """
    router_parent.include_router(router)
    logger.info("هندلرهای Semi-Auto ثبت شدند")
