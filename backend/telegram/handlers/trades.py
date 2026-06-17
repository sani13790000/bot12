"""
هندلرهای معاملات

با Authorization و Rate Limiting.

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
import httpx

from ..keyboards import get_trades_keyboard, get_confirm_keyboard, get_back_keyboard
from ..utils import format_trade_list, format_trade_detail, format_error_message
from ..auth import (
    require_permission, require_role,
    Permission, UserRole
)
from ..rbac_service import rbac_service
from ....core.logger import get_logger
from ....core.config import settings
from ....services.audit_service import audit_service, AuditAction

logger = get_logger("telegram.handlers.trades")


# API endpoint پایه
API_BASE = f"http://localhost:{settings.API_PORT}{settings.API_PREFIX}"


def register_trade_handlers(dp: Dispatcher):
    """ثبت هندلرهای معاملات"""

    # --------------------------------------------------
    # منوی معاملات
    # --------------------------------------------------

    @dp.message(F.text == "📈 معاملات من")
    async def menu_trades(message: types.Message):
        """نمایش منوی معاملات"""
        # بررسی ثبت کاربر
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer(
                "⚠️ برای دسترسی به معاملات باید ثبت‌نام کنید.",
                parse_mode="HTML"
            )
            return

        # منوی مناسب برای نقش
        role = await rbac_service.get_user_role(message.from_user.id)

        if role and role.value in ["trader", "admin", "super_admin"]:
            await message.answer(
                "📈 <b>مدیریت معاملات</b>\n\n"
                "گزینه مورد نظر را انتخاب کنید:",
                reply_markup=get_trades_keyboard(full=True),
                parse_mode="HTML"
            )
        else:
            # فقط مشاهده برای user
            await message.answer(
                "📈 <b>مشاهده معاملات</b>\n\n"
                "شما فقط می‌توانید معاملات را مشاهده کنید.\n"
                "برای معامله به نقش trader ارتقا یابید.",
                reply_markup=get_trades_keyboard(full=False),
                parse_mode="HTML"
            )

    # --------------------------------------------------
    # مشاهده معاملات باز
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_open")
    async def show_open_trades(callback: types.CallbackQuery):
        """نمایش معاملات باز"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "⚠️ ثبت نشده",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/open",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trades = result.get("data", {}).get("positions", [])

                if not trades:
                    await callback.message.edit_text(
                        "📭 <b>معاملات باز</b>\n\n"
                        "هیچ معامله‌ای باز نیست.",
                        parse_mode="HTML"
                    )
                else:
                    text = format_trade_list(trades, "معاملات باز")
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML"
                    )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت معاملات: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # تاریخچه معاملات
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_history")
    async def show_trade_history(callback: types.CallbackQuery):
        """نمایش تاریخچه معاملات"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "⚠️ ثبت نشده",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/",
                    params={"limit": 20},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trades = result.get("data", {}).get("trades", [])

                if not trades:
                    await callback.message.edit_text(
                        "📭 <b>تاریخچه معاملات</b>\n\n"
                        "هیچ معامله‌ای ثبت نشده.",
                        parse_mode="HTML"
                    )
                else:
                    text = format_trade_list(trades, "تاریخچه معاملات")
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML"
                    )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت تاریخچه: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # بستن همه معاملات (حساس - نیاز به permission)
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_all")
    async def confirm_close_all(callback: types.CallbackQuery):
        """تأیید بستن همه معاملات"""
        # بررسی دسترسی
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_ALL_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "⚠️ <b>هشدار!</b>\n\n"
            "آیا مطمئن هستید که می‌خواهید\n"
            "همه معاملات باز را ببندید؟\n\n"
            "این عملیات قابل بازگشت نیست!",
            reply_markup=get_confirm_keyboard("close_all"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_all")
    async def execute_close_all(callback: types.CallbackQuery):
        """بستن همه معاملات"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "⚠️ خطا در احراز هویت",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # ثبت audit log
        await audit_service.log_trade(
            user_id=user.get("id"),
            trade_id="all",
            action="close",
            symbol="ALL",
            direction="all"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                closed_count = data.get("closed_count", 0)
                total_profit = data.get("total_profit", 0)

                await callback.message.edit_text(
                    f"✅ <b>معاملات بسته شدند</b>\n\n"
                    f"📊 تعداد: {closed_count}\n"
                    f"💰 سود/ضرر: ${total_profit:.2f}",
                    parse_mode="HTML"
                )

                logger.info(
                    f"{closed_count} معامله توسط {user.get('id')} بسته شد"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در بستن معاملات: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "cancel_close_all")
    async def cancel_close_all(callback: types.CallbackQuery):
        """لغو بستن معاملات"""
        await callback.message.edit_text(
            "❌ عملیات لغو شد.",
            parse_mode="HTML"
        )
        await callback.answer()

    # --------------------------------------------------
    # بستن معاملات خرید
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_buy")
    async def confirm_close_buy(callback: types.CallbackQuery):
        """تأیید بستن معاملات خرید"""
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_BUY_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "⚠️ <b>بستن معاملات خرید</b>\n\n"
            "آیا مطمئن هستید؟",
            reply_markup=get_confirm_keyboard("close_buy"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_buy")
    async def execute_close_buy(callback: types.CallbackQuery):
        """بستن معاملات خرید"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text("⚠️ خطا", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    params={"direction": "buy"},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                await callback.message.edit_text(
                    f"✅ <b>معاملات خرید بسته شدند</b>\n\n"
                    f"📊 تعداد: {data.get('closed_count', 0)}\n"
                    f"💰 سود/ضرر: ${data.get('total_profit', 0):.2f}",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در بستن خریدها: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # بستن معاملات فروش
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_sell")
    async def confirm_close_sell(callback: types.CallbackQuery):
        """تأیید بستن معاملات فروش"""
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_SELL_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "⚠️ <b>بستن معاملات فروش</b>\n\n"
            "آیا مطمئن هستید؟",
            reply_markup=get_confirm_keyboard("close_sell"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_sell")
    async def execute_close_sell(callback: types.CallbackQuery):
        """بستن معاملات فروش"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text("⚠️ خطا", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    params={"direction": "sell"},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                await callback.message.edit_text(
                    f"✅ <b>معاملات فروش بسته شدند</b>\n\n"
                    f"📊 تعداد: {data.get('closed_count', 0)}\n"
                    f"💰 سود/ضرر: ${data.get('total_profit', 0):.2f}",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در بستن فروش‌ها: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # جزئیات معامله
    # --------------------------------------------------

    @dp.callback_query(F.data.startswith("trade_"))
    async def show_trade_detail(callback: types.CallbackQuery):
        """جزئیات معامله"""
        trade_id = callback.data.split("_")[1]
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text("⚠️ خطا", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/{trade_id}",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trade = result.get("data", {})

                text = format_trade_detail(trade)
                await callback.message.edit_text(
                    text,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "❌ معامله یافت نشد",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت جزئیات: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # دستورات متنی
    # --------------------------------------------------

    @dp.message(F.text.regexp(r"^/close_all"))
    async def cmd_close_all(message: types.Message):
        """دستور بستن همه معاملات"""
        check = await rbac_service.check_permission(
            message.from_user.id,
            Permission.CLOSE_ALL_TRADES
        )

        if not check.get("allowed"):
            await message.answer(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            return

        # نمایش تأیید
        await message.answer(
            "⚠️ <b>هشدار!</b>\n\n"
            "آیا مطمئن هستید که می‌خواهید همه معاملات را ببندید؟\n\n"
            "برای تأیید /yes را بفرستید.",
            parse_mode="HTML"
        )
