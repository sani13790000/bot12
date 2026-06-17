"""
هندلرهای گزارش‌ها

با Authorization و Rate Limiting.

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
import httpx

from ..keyboards import get_reports_keyboard
from ..utils import format_report_summary
from ..auth import rate_limit, require_permission, Permission
from ..rbac_service import rbac_service
from ....core.logger import get_logger
from ....core.config import settings

logger = get_logger("telegram.handlers.reports")

API_BASE = f"http://localhost:{settings.API_PORT}{settings.API_PREFIX}"


def register_report_handlers(dp: Dispatcher):
    """ثبت هندلرهای گزارش‌ها"""

    @dp.message(F.text == "📋 گزارش‌ها")
    @rate_limit("command")
    async def menu_reports(message: types.Message):
        """نمایش منوی گزارش‌ها"""
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)

        if not user:
            await message.answer(
                "⚠️ برای مشاهده گزارش‌ها باید ثبت‌نام کنید.\n\n"
                "در داشبورد ثبت‌نام کنید و تلگرام خود را متصل کنید.",
                parse_mode="HTML"
            )
            return

        await message.answer(
            "📋 <b>گزارش‌ها</b>\n\n"
            "نوع گزارش را انتخاب کنید:",
            reply_markup=get_reports_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data == "report_daily")
    @rate_limit("command")
    async def show_daily_report(callback: types.CallbackQuery):
        """گزارش روزانه"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text(
                "⚠️ ثبت نشده",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # بررسی دسترسی
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.VIEW_DAILY_REPORT
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/reports/daily",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                summary = data.get("summary", {})

                total = summary.get("total_trades", 0)
                winning = summary.get("winning_trades", 0)
                losing = summary.get("losing_trades", 0)
                win_rate = summary.get("win_rate", 0)
                net_profit = summary.get("net_profit", 0)
                gross_profit = summary.get("gross_profit", 0)
                gross_loss = summary.get("gross_loss", 0)

                text = f"""
📅 <b>گزارش روزانه</b>
تاریخ: {data.get('date', '---')}</b>

📊 <b>خلاصه:</b>
• تعداد معاملات: {total}
• برنده: {winning} 🟢
• بازنده: {losing} 🔴
• وین ریت: {win_rate:.1f}%

💰 <b>مالی:</b>
• سود ناخالص: ${gross_profit:.2f}
• ضرر ناخالص: ${abs(gross_loss):.2f}
• سود/ضرر خالص: ${net_profit:.2f}

{'✅' if net_profit >= 0 else '📉'} <b>نتیجه:</b> {'سودده' if net_profit >= 0 else 'زیان‌ده'}
"""
                await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت گزارش",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت گزارش روزانه: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "report_weekly")
    @rate_limit("command")
    async def show_weekly_report(callback: types.CallbackQuery):
        """گزارش هفتگی"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text("⚠️ ثبت نشده", parse_mode="HTML")
            await callback.answer()
            return

        # بررسی دسترسی
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.VIEW_WEEKLY_REPORT
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/reports/weekly",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                summary = data.get("summary", {})
                breakdown = data.get("daily_breakdown", [])

                text = f"""
📆 <b>گزارش هفتگی</b>
از {data.get('week_start', '---')} تا {data.get('week_end', '---')}

📊 <b>خلاصه:</b>
• تعداد معاملات: {summary.get('total_trades', 0)}
• سود/ضرر کل: ${summary.get('total_profit', 0):.2f}
• وین ریت: {summary.get('win_rate', 0):.1f}%

📈 <b>تفکیک روزانه:</b>
"""
                for day in breakdown:
                    profit_emoji = "🟢" if day.get("profit", 0) >= 0 else "🔴"
                    text += f"\n{profit_emoji} {day.get('date', '---')}: {day.get('trades', 0)} معامله | ${day.get('profit', 0):.2f}"

                await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت گزارش",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت گزارش هفتگی: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "report_monthly")
    @rate_limit("command")
    async def show_monthly_report(callback: types.CallbackQuery):
        """گزارش ماهانه"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text("⚠️ ثبت نشده", parse_mode="HTML")
            await callback.answer()
            return

        # بررسی دسترسی
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.VIEW_MONTHLY_REPORT
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/reports/monthly",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                summary = data.get("summary", {})

                text = f"""
🗓 <b>گزارش ماهانه</b>
ماه: {data.get('month', '---')}

📊 <b>خلاصه:</b>
• تعداد معاملات: {summary.get('total_trades', 0)}
• برنده: {summary.get('winning_trades', 0)} 🟢
• بازنده: {summary.get('losing_trades', 0)} 🔴
• وین ریت: {summary.get('win_rate', 0):.1f}%

💰 <b>سود/ضرر خالص:</b> ${summary.get('net_profit', 0):.2f}
"""
                await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت گزارش",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت گزارش ماهانه: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "report_performance")
    @rate_limit("command")
    async def show_performance(callback: types.CallbackQuery):
        """عملکرد کلی"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text("⚠️ ثبت نشده", parse_mode="HTML")
            await callback.answer()
            return

        # بررسی دسترسی
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.VIEW_OWN_REPORTS
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/reports/performance",
                    params={"period": "all"},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                metrics = data.get("metrics", {})

                profit_factor = metrics.get("profit_factor", 0)
                pf_status = "عالی" if profit_factor > 2 else "خوب" if profit_factor > 1.5 else "نیاز به بهبود"

                text = f"""
📊 <b>عملکرد کلی</b>

📈 <b>معیارهای عملکرد:</b>
• تعداد کل معاملات: {metrics.get('total_trades', 0)}
• برنده: {metrics.get('winning_trades', 0)} 🟢
• بازنده: {metrics.get('losing_trades', 0)} 🔴

🎯 <b>نرخ موفقیت:</b>
• وین ریت: {metrics.get('win_rate', 0):.1f}%
• فاکتور سود: {profit_factor:.2f} ({pf_status})

💰 <b>سود و ضرر:</b>
• سود ناخالص: ${metrics.get('gross_profit', 0):.2f}
• ضرر ناخالص: ${metrics.get('gross_loss', 0):.2f}
• سود خالص: ${metrics.get('net_profit', 0):.2f}
• میانگین هر معامله: ${metrics.get('avg_trade', 0):.2f}
"""
                await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت عملکرد",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت عملکرد: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    # دستورات متنی
    @dp.message(F.text.regexp(r"^/daily$"))
    @rate_limit("command")
    async def cmd_daily(message: types.Message):
        """دستور /daily"""
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer(
                "⚠️ برای استفاده از این دستور ثبت‌نام کنید.",
                parse_mode="HTML"
            )
            return

        # براس دسترسی
        check = await rbac_service.check_permission(
            message.from_user.id,
            Permission.VIEW_DAILY_REPORT
        )

        if not check.get("allowed"):
            await message.answer(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            return

        await message.answer("📊 گزارش روزانه در حال دریافت...", parse_mode="HTML")

    @dp.message(F.text.regexp(r"^/weekly$"))
    @rate_limit("command")
    async def cmd_weekly(message: types.Message):
        """دستور /weekly"""
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("⚠️ ثبت‌نام کنید.", parse_mode="HTML")
            return

        check = await rbac_service.check_permission(
            message.from_user.id,
            Permission.VIEW_WEEKLY_REPORT
        )

        if not check.get("allowed"):
            await message.answer(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            return

        await message.answer("📊 گزارش هفتگی...", parse_mode="HTML")

    @dp.message(F.text.regexp(r"^/monthly$"))
    @rate_limit("command")
    async def cmd_monthly(message: types.Message):
        """دستور /monthly"""
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("⚠️ ثبت‌نام کنید.", parse_mode="HTML")
            return

        check = await rbac_service.check_permission(
            message.from_user.id,
            Permission.VIEW_MONTHLY_REPORT
        )

        if not check.get("allowed"):
            await message.answer(
                check.get("message", "🚫 دسترسی غیرمجاز"),
                parse_mode="HTML"
            )
            return

        await message.answer("📊 گزارش ماهانه...", parse_mode="HTML")
