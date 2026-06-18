"""
ربات تلگرام MT5 Trading

کلاس اصلی ربات با پشتیبانی RBAC و Authorization.

نویسنده: MT5 Trading Team
"""

import asyncio
from typing import Optional, Dict, Any, List

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
    - Role-Based Access Control (RBAC)
    - Rate Limiting
    - Authorization Middleware
    - AlertsHandler برای هشدارهای proactive
    """

    def __init__(self) -> None:
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._running: bool = False
        self._admin_ids: List[int] = []
        self._alerts_handler: Optional[Any] = None

    async def initialize(self) -> None:
        """
        راه‌اندازی اولیه ربات

        مراحل:
        1. ایجاد Bot و Dispatcher
        2. ثبت Authorization Middleware
        3. ثبت تمام هندلرها (۹ هندلر)
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

    def get_alerts_handler(self) -> Optional[Any]:
        """
        دریافت AlertsHandler برای ارسال هشدارهای proactive

        این متد توسط SessionAlertService و سایر سرویس‌ها استفاده می‌شود
        تا بتوانند هشدارها را به تلگرام ارسال کنند.

        Returns:
            AlertsHandler یا None در صورت راه‌اندازی نشدن
        """
        if self._alerts_handler is None:
            logger.error("AlertsHandler راه‌اندازی نشده — initialize() را صدا بزنید")
            return None
        return self._alerts_handler

    async def send_trade_open_alert(self, trade_data: Dict[str, Any]) -> None:
        """
        ارسال هشدار باز شدن معامله به تمام کاربران مجاز

        این متد از خارج ربات (مثلاً از TradeService) فراخوانی می‌شود.

        Args:
            trade_data: دیکشنری حاوی جزئیات معامله
        """
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_trade_open_alert(trade_data)

    async def send_trade_close_alert(self, trade_data: Dict[str, Any]) -> None:
        """
        ارسال هشدار بسته شدن معامله

        Args:
            trade_data: دیکشنری حاوی جزئیات معامله و نتیجه
        """
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_trade_close_alert(trade_data)

    async def send_sl_hit_alert(self, trade_data: Dict[str, Any]) -> None:
        """
        ارسال هشدار زده شدن Stop Loss

        Args:
            trade_data: دیکشنری حاوی جزئیات معامله و ضرر
        """
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_sl_hit_alert(trade_data)

    async def send_tp_hit_alert(self, trade_data: Dict[str, Any]) -> None:
        """
        ارسال هشدار رسیدن به Take Profit

        Args:
            trade_data: دیکشنری حاوی جزئیات معامله و سود
        """
        handler = self.get_alerts_handler()
        if handler:
            await handler.send_tp_hit_alert(trade_data)

    async def start(self) -> None:
        """
        شروع polling ربات

        اگر initialize() قبلاً صدا زده نشده، خودکار صدا می‌زند.
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

    async def stop(self) -> None:
        """
        توقف کامل ربات و آزاد کردن منابع
        """
        if self.dp:
            await self.dp.stop_polling()
        if self.bot:
            await self.bot.session.close()
        self._running = False
        logger.info("ربات تلگرام متوقف شد")

    async def _error_handler(self, update: Any, exception: Exception) -> bool:
        """
        مدیریت خطاهای کلی — با logging کامل

        Args:
            update: آپدیت تلگرام که خطا در پردازش آن رخ داد
            exception: خطای رخ داده

        Returns:
            True برای جلوگیری از propagate خطا
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
                logger.warning(f"نمی‌توان پیام خطا را ارسال کرد: {send_err}")

        return True

    async def _unknown_command_handler(self, message: Message) -> None:
        """
        مدیریت دستورات ناشناخته — پاسخ راهنما
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
        **kwargs: Any
    ) -> Optional[Any]:
        """
        ارسال پیام به یک chat

        Args:
            chat_id: شناسه چت مقصد
            text: متن پیام
            parse_mode: فرمت پارس متن (HTML یا Markdown)
            **kwargs: پارامترهای اضافی aiogram

        Returns:
            Message object یا None در صورت خطا
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
            logger.error(f"خطا در ارسال پیام به {chat_id}: {e}")
            return None

    async def broadcast_message(self, chat_ids: List[int], text: str) -> Dict[str, int]:
        """
        ارسال پیام به چندین چت با flood prevention

        Args:
            chat_ids: لیست شناسه‌های چت
            text: متن پیام

        Returns:
            دیکشنری با تعداد موفق و ناموفق
        """
        success_count = 0
        fail_count = 0

        for chat_id in chat_ids:
            try:
                await self.send_message(chat_id, text)
                success_count += 1
                await asyncio.sleep(0.05)  # جلوگیری از telegram flood limit
            except Exception as e:
                logger.warning(f"خطا در ارسال به {chat_id}: {e}")
                fail_count += 1

        logger.info(f"پیام گروهی ارسال شد — موفق: {success_count}، ناموفق: {fail_count}")
        return {"success": success_count, "fail": fail_count}

    async def notify_admins(self, text: str) -> None:
        """
        ارسال پیام به تمام ادمین‌های تعریف‌شده

        Args:
            text: متن پیام هشدار
        """
        if not self._admin_ids:
            logger.warning("هیچ ادمینی تعریف نشده — TELEGRAM_ADMIN_IDS را بررسی کنید")
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


# نمونه سراسری — Singleton pattern
telegram_bot = TelegramBot()


async def start_telegram_bot() -> None:
    """
    تابع شروع ربات (برای استفاده در API lifespan)
    """
    await telegram_bot.start()


async def stop_telegram_bot() -> None:
    """
    تابع توقف ربات (برای استفاده در API lifespan)
    """
    await telegram_bot.stop()
