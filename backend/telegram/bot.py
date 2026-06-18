"""
ربات تلگرام MT5 Trading

کلاس اصلی ربات با پشتیبانی RBAC و Authorization.

نویسنده: MT5 Trading Team
"""

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from .handlers import setup_handlers
from .keyboards import get_main_keyboard
from .auth import authorization_middleware, rate_limiter
from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("telegram.bot")


class TelegramBot:
    """
    کلاس اصلی ربات تلگرام

    با پشتیبانی:
    - Role-Based Access Control
    - Rate Limiting
    - Authorization Middleware
    """

    def __init__(self):
        self.bot: Bot = None
        self.dp: Dispatcher = None
        self._running = False
        self._admin_ids: list = []

    async def initialize(self):
        """
        راه‌اندازی اولیه ربات

        مراحل:
        1. ایجاد Bot و Dispatcher
        2. ثبت Authorization Middleware
        3. ثبت تمام هندلرها
        4. ثبت هندلر خطا
        5. ایجاد AlertsHandler برای ارسال هشدارهای proactive
        """
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("توکن ربات تلگرام تنظیم نشده است")
            return

        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()

        # تنظیم admin IDs
        self._admin_ids = settings.TELEGRAM_ADMIN_IDS or []

        # ثبت middleware authorization
        self.dp.message.middleware.register(authorization_middleware)
        self.dp.callback_query.middleware.register(authorization_middleware)

        # ثبت هندلرها (شامل control، alerts، admin_users)
        setup_handlers(self.dp)

        # ثبت هندلر خطا
        self.dp.error.register(self._error_handler)

        # ثبت هندلر not_found
        self.dp.message.register(self._unknown_command_handler)

        # --- ایجاد AlertsHandler با bot instance ---
        # این هندلر برای ارسال proactive alerts (trade/session/system) استفاده می‌شود
        from .handlers.alerts import AlertsHandler
        self._alerts_handler = AlertsHandler(bot=self.bot)

        logger.info("ربات تلگرام راه‌اندازی شد با پشتیبانی RBAC + AlertsHandler")

    def get_alerts_handler(self):
        """
        دریافت AlertsHandler برای ارسال هشدارهای proactive

        این متد توسط SessionAlertService و سایر سرویس‌ها استفاده می‌شود
        تا بتوانند هشدارها را به تلگرام ارسال کنند.
        """
        if not hasattr(self, '_alerts_handler') or self._alerts_handler is None:
            logger.error("AlertsHandler راه‌اندازی نشده — initialize() را صدا بزنید")
            return None
        return self._alerts_handler

    async def send_trade_open_alert(self, trade_data: dict):
        """
        ارسال هشدار باز شدن معامله به تمام کاربران مجاز

        این متد از خارج ربات (مثلاً از TradeService) فراخوانی می‌شود.
        """
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_trade_open_alert(trade_data)

    async def send_trade_close_alert(self, trade_data: dict):
        """ارسال هشدار بسته شدن معامله"""
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_trade_close_alert(trade_data)

    async def send_sl_hit_alert(self, trade_data: dict):
        """ارسال هشدار زده شدن Stop Loss"""
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_sl_hit_alert(trade_data)

    async def send_tp_hit_alert(self, trade_data: dict):
        """ارسال هشدار رسیدن به Take Profit"""
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_tp_hit_alert(trade_data)

    async def start(self):
        """
        شروع ربات
        """
        if not self.bot:
            await self.initialize()

        if not self.bot:
            logger.error("نمی‌توان ربات را بدون توکن راه‌اندازی کرد")
            return

        self._running = True

        try:
            # دریافت اطلاعات ربات
            me = await self.bot.get_me()
            logger.info(f"ربات @{me.username} راه‌اندازی شد")

            # شروع polling
            logger.info("شروع polling ربات تلگرام")
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["message", "callback_query"]
            )

        except Exception as e:
            logger.error(f"خطا در اجرای ربات: {e}")
            self._running = False

    async def stop(self):
        """
        توقف ربات
        """
        if self.bot:
            await self.bot.session.close()
        if self.dp:
            await self.dp.stop_polling()
        self._running = False
        logger.info("ربات تلگرام متوقف شد")

    async def _error_handler(self, update, exception):
        """
        مدیریت خطاهای کلی — با logging کامل (بدون بلع خاموش)
        """
        logger.error(
            f"خطا در پردازش آپدیت: {type(exception).__name__}: {exception}",
            exc_info=exception,
        )

        # اطلاع به ادمین‌ها در صورت خطای بحرانی
        if not isinstance(exception, TelegramAPIError):
            try:
                await self.notify_admins(
                    f"⚠️ خطای بحرانی ربات:\n"
                    f"نوع: {type(exception).__name__}\n"
                    f"پیام: {str(exception)[:200]}"
                )
            except Exception as notify_err:
                logger.error(f"خطا در اطلاع به ادمین: {notify_err}")

        # ارسال پیام خطا به کاربر
        if hasattr(update, 'message') and update.message:
            try:
                await update.message.answer(
                    "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.",
                    parse_mode="HTML"
                )
            except TelegramAPIError as send_err:
                # اگر ارسال پیام خطا هم fail شد، فقط log می‌کنیم
                logger.warning(f"نمی‌توان پیام خطا را ارسال کرد: {send_err}")

        return True

    async def _unknown_command_handler(self, message: Message):
        """
        مدیریت دستورات ناشناخته
        """
        await message.answer(
            "❌ دستور نامعتبر است.\n\n"
            "برای مشاهده دستورات موجود از /help استفاده کنید.",
            parse_mode="HTML"
        )

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        **kwargs
    ):
        """
        ارسال پیام
        """
        if not self.bot:
            logger.error("ربات راه‌اندازی نشده است")
            return None

        try:
            return await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
        except TelegramAPIError as e:
            logger.error(f"خطا در ارسال پیام: {e}")
            return None

    async def send_signal_alert(self, chat_id: int, signal_data: dict):
        """
        ارسال اعلان سیگنال جدید
        """
        from .utils import format_signal_card
        from .keyboards import get_signal_action_keyboard

        text = format_signal_card(signal_data)
        keyboard = get_signal_action_keyboard(signal_data.get("id"))

        return await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard
        )

    async def send_trade_alert(self, chat_id: int, trade_data: dict):
        """
        ارسال اعلان معاملاه جدید
        """
        from .utils import format_trade_detail

        text = format_trade_detail(trade_data)

        return await self.send_message(
            chat_id=chat_id,
            text=text
        )

    async def send_daily_report(self, chat_id: int, report_data: dict):
        """
        ارسال گزارش روزانه
        """
        from .utils import format_report_summary

        text = format_report_summary(report_data)

        return await self.send_message(
            chat_id=chat_id,
            text=text
        )

    async def broadcast_message(self, chat_ids: list, text: str):
        """
        ارسال پیام به چندین چت
        """
        success_count = 0
        fail_count = 0

        for chat_id in chat_ids:
            try:
                await self.send_message(chat_id, text)
                success_count += 1
                await asyncio.sleep(0.05)  # جلوگیری از flood
            except Exception as e:
                logger.warning(f"خطا در ارسال به {chat_id}: {e}")
                fail_count += 1

        logger.info(f"پیام گروهی ارسال شد - موفق: {success_count}, ناموفق: {fail_count}")
        return {"success": success_count, "fail": fail_count}

    async def notify_admins(self, text: str):
        """
        اطلاع به ادمین‌ها
        """
        if not self._admin_ids:
            return

        for admin_id in self._admin_ids:
            try:
                await self.send_message(admin_id, text)
            except Exception as e:
                logger.warning(f"خطا در اطلاع به ادمین {admin_id}: {e}")

    @property
    def is_running(self) -> bool:
        """بررسی وضعیت اجرای ربات"""
        return self._running


# نمونه سراسری
telegram_bot = TelegramBot()


async def start_telegram_bot():
    """
    تابع شروع ربات (برای استفاده در main)
    """
    await telegram_bot.start()


async def stop_telegram_bot():
    """
    تابع توقف ربات
    """
    await telegram_bot.stop()
