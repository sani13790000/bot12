"""
=====================================================================
سیستم هشدارهای تلگرام - Production Ready
=====================================================================
این ماژول مسئول ارسال تمام هشدارهای خودکار سیستم به تلگرام است:
  - هشدار ورود به معامله
  - هشدار خروج از معامله
  - هشدار فعال شدن Stop Loss
  - هشدار رسیدن به Take Profit
  - هشدار باز شدن سشن معاملاتی
  - هشدار پایان سشن معاملاتی
  - هشدار خطاهای سیستمی

نویسنده: MT5 Trading Team
نسخه: 2.0.0
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """انواع هشدارهای سیستم"""
    TRADE_ENTRY = "trade_entry"
    TRADE_EXIT = "trade_exit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    SESSION_OPEN = "session_open"
    SESSION_CLOSE = "session_close"
    SYSTEM_ERROR = "system_error"
    SIGNAL_GENERATED = "signal_generated"
    RISK_WARNING = "risk_warning"
    LICENSE_WARNING = "license_warning"


class AlertPriority(Enum):
    """اولویت هشدارها"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TelegramAlertManager:
    """
    مدیریت کامل هشدارهای تلگرام

    این کلاس مسئول ارسال تمام هشدارهای خودکار سیستم است.
    هر نوع هشدار با فرمت‌بندی مناسب و اطلاعات کامل ارسال می‌شود.
    """

    def __init__(self, bot, admin_chat_ids: list[int]):
        """
        مقداردهی اولیه مدیر هشدار

        پارامترها:
            bot: نمونه ربات تلگرام (aiogram Bot)
            admin_chat_ids: لیست شناسه چت ادمین‌ها
        """
        self.bot = bot
        self.admin_chat_ids = admin_chat_ids
        self._alert_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def start(self):
        """شروع پردازش صف هشدارها"""
        self._running = True
        asyncio.create_task(self._process_alert_queue())
        logger.info("سیستم هشدار تلگرام شروع به کار کرد")

    async def stop(self):
        """توقف پردازش هشدارها"""
        self._running = False
        logger.info("سیستم هشدار تلگرام متوقف شد")

    async def _process_alert_queue(self):
        """پردازش صف هشدارها به صورت ناهمزمان"""
        while self._running:
            try:
                if not self._alert_queue.empty():
                    alert = await self._alert_queue.get()
                    await self._send_alert_to_all(alert["message"], alert["chat_ids"])
                    self._alert_queue.task_done()
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"خطا در پردازش صف هشدار: {e}")

    async def _send_alert_to_all(self, message: str, chat_ids: list[int]):
        """ارسال هشدار به تمام چت‌های مشخص شده"""
        for chat_id in chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.05)  # جلوگیری از Rate Limit
            except Exception as e:
                logger.error(f"خطا در ارسال هشدار به {chat_id}: {e}")

    async def send_trade_entry_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float,
        score: float,
        strategy: str,
        timeframe: str,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار ورود به معامله

        پارامترها:
            symbol: نماد معاملاتی
            direction: جهت معامله (BUY/SELL)
            entry_price: قیمت ورود
            stop_loss: قیمت استاپ لاس
            take_profit: قیمت تارگت
            lot_size: حجم معامله
            score: امتیاز کیفیت معامله
            strategy: نام استراتژی
            timeframe: تایم‌فریم
            chat_ids: لیست چت‌های هدف (اختیاری)
        """
        direction_emoji = "🟢📈" if direction.upper() == "BUY" else "🔴📉"
        risk_reward = abs(take_profit - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0

        message = (
            f"{direction_emoji} <b>ورود به معامله</b>
"
            f"{'─' * 30}
"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎯 <b>جهت:</b> {'خرید (BUY)' if direction.upper() == 'BUY' else 'فروش (SELL)'}
"
            f"💰 <b>قیمت ورود:</b> {entry_price:.5f}
"
            f"🛑 <b>استاپ لاس:</b> {stop_loss:.5f}
"
            f"✅ <b>تارگت:</b> {take_profit:.5f}
"
            f"📦 <b>حجم:</b> {lot_size:.2f} لات
"
            f"⚖️ <b>ریسک/ریوارد:</b> 1:{risk_reward:.2f}
"
            f"⭐ <b>امتیاز کیفیت:</b> {score:.1f}/100
"
            f"🔧 <b>استراتژی:</b> {strategy}
"
            f"⏱ <b>تایم‌فریم:</b> {timeframe}
"
            f"🕐 <b>زمان:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_trade_exit_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        profit: float,
        profit_pips: float,
        lot_size: float,
        duration_minutes: int,
        exit_reason: str,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار خروج از معامله

        پارامترها:
            symbol: نماد معاملاتی
            direction: جهت معامله
            entry_price: قیمت ورود
            exit_price: قیمت خروج
            profit: سود/ضرر دلاری
            profit_pips: سود/ضرر به پیپ
            lot_size: حجم معامله
            duration_minutes: مدت زمان معامله به دقیقه
            exit_reason: دلیل خروج
            chat_ids: لیست چت‌های هدف
        """
        result_emoji = "💰✅" if profit >= 0 else "💸❌"
        profit_sign = "+" if profit >= 0 else ""

        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        duration_str = f"{hours}ساعت {minutes}دقیقه" if hours > 0 else f"{minutes}دقیقه"

        message = (
            f"{result_emoji} <b>خروج از معامله</b>
"
            f"{'─' * 30}
"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎯 <b>جهت:</b> {'خرید' if direction.upper() == 'BUY' else 'فروش'}
"
            f"📥 <b>ورود:</b> {entry_price:.5f}
"
            f"📤 <b>خروج:</b> {exit_price:.5f}
"
            f"📦 <b>حجم:</b> {lot_size:.2f} لات
"
            f"💵 <b>نتیجه:</b> {profit_sign}{profit:.2f}$
"
            f"📏 <b>پیپ:</b> {profit_sign}{profit_pips:.1f} پیپ
"
            f"⏱ <b>مدت:</b> {duration_str}
"
            f"📌 <b>دلیل خروج:</b> {exit_reason}
"
            f"🕐 <b>زمان:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_stop_loss_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_price: float,
        loss: float,
        loss_pips: float,
        lot_size: float,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار فعال شدن استاپ لاس

        پارامترها:
            symbol: نماد
            direction: جهت معامله
            entry_price: قیمت ورود
            stop_price: قیمت استاپ
            loss: ضرر دلاری
            loss_pips: ضرر به پیپ
            lot_size: حجم
            chat_ids: لیست چت‌ها
        """
        message = (
            f"🛑 <b>استاپ لاس فعال شد</b>
"
            f"{'─' * 30}
"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎯 <b>جهت:</b> {'خرید' if direction.upper() == 'BUY' else 'فروش'}
"
            f"📥 <b>ورود:</b> {entry_price:.5f}
"
            f"🛑 <b>استاپ:</b> {stop_price:.5f}
"
            f"📦 <b>حجم:</b> {lot_size:.2f} لات
"
            f"💸 <b>ضرر:</b> -{abs(loss):.2f}$
"
            f"📏 <b>پیپ:</b> -{abs(loss_pips):.1f} پیپ
"
            f"🕐 <b>زمان:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_take_profit_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        tp_price: float,
        profit: float,
        profit_pips: float,
        lot_size: float,
        tp_level: int = 1,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار رسیدن به تارگت

        پارامترها:
            symbol: نماد
            direction: جهت
            entry_price: قیمت ورود
            tp_price: قیمت تارگت
            profit: سود دلاری
            profit_pips: سود به پیپ
            lot_size: حجم
            tp_level: شماره تارگت (1، 2 یا 3)
            chat_ids: لیست چت‌ها
        """
        message = (
            f"🎯✅ <b>تارگت {tp_level} رسید!</b>
"
            f"{'─' * 30}
"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎯 <b>جهت:</b> {'خرید' if direction.upper() == 'BUY' else 'فروش'}
"
            f"📥 <b>ورود:</b> {entry_price:.5f}
"
            f"✅ <b>تارگت {tp_level}:</b> {tp_price:.5f}
"
            f"📦 <b>حجم:</b> {lot_size:.2f} لات
"
            f"💰 <b>سود:</b> +{profit:.2f}$
"
            f"📏 <b>پیپ:</b> +{profit_pips:.1f} پیپ
"
            f"🕐 <b>زمان:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_session_open_alert(
        self,
        session_name: str,
        session_time: str,
        active_pairs: list[str],
        expected_volatility: str,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار باز شدن سشن معاملاتی

        پارامترها:
            session_name: نام سشن (London, New York, Tokyo, Sydney)
            session_time: زمان سشن
            active_pairs: جفت‌ارزهای فعال در این سشن
            expected_volatility: نوسانات انتظاری (Low/Medium/High)
            chat_ids: لیست چت‌ها
        """
        session_emojis = {
            "London": "🇬🇧",
            "New York": "🗽",
            "Tokyo": "🇯🇵",
            "Sydney": "🇦🇺",
            "London/New York": "🌍",
        }
        emoji = session_emojis.get(session_name, "🌐")

        volatility_emoji = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}.get(expected_volatility, "⚪")
        pairs_str = " | ".join(active_pairs[:6])

        message = (
            f"{emoji} <b>سشن {session_name} باز شد</b>
"
            f"{'─' * 30}
"
            f"⏰ <b>زمان:</b> {session_time}
"
            f"📊 <b>نمادهای فعال:</b> {pairs_str}
"
            f"{volatility_emoji} <b>نوسانات انتظاری:</b> {expected_volatility}
"
            f"🤖 <b>ربات:</b> در حال اسکن بازار...
"
            f"🕐 <b>زمان سیستم:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_session_close_alert(
        self,
        session_name: str,
        trades_count: int,
        profit_loss: float,
        win_rate: float,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار پایان سشن معاملاتی

        پارامترها:
            session_name: نام سشن
            trades_count: تعداد معاملات در سشن
            profit_loss: سود/ضرر کل سشن
            win_rate: نرخ برد سشن
            chat_ids: لیست چت‌ها
        """
        result_emoji = "✅" if profit_loss >= 0 else "❌"
        profit_sign = "+" if profit_loss >= 0 else ""

        message = (
            f"🔔 <b>پایان سشن {session_name}</b>
"
            f"{'─' * 30}
"
            f"📊 <b>معاملات:</b> {trades_count} معامله
"
            f"{result_emoji} <b>نتیجه کل:</b> {profit_sign}{profit_loss:.2f}$
"
            f"🏆 <b>وین ریت:</b> {win_rate:.1f}%
"
            f"🕐 <b>زمان:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_signal_alert(
        self,
        symbol: str,
        signal_type: str,
        score: float,
        timeframe: str,
        smc_score: float,
        pa_score: float,
        liq_score: float,
        confluence_details: list[str],
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار سیگنال جدید تحلیل

        پارامترها:
            symbol: نماد
            signal_type: نوع سیگنال (BUY/SELL/WAIT)
            score: امتیاز کلی
            timeframe: تایم‌فریم
            smc_score: امتیاز SMC
            pa_score: امتیاز Price Action
            liq_score: امتیاز Liquidity
            confluence_details: لیست دلایل سیگنال
            chat_ids: لیست چت‌ها
        """
        type_emoji = {"BUY": "🟢📈", "SELL": "🔴📉", "WAIT": "⏸️"}.get(signal_type, "⚪")
        confluence_str = "
".join([f"  • {d}" for d in confluence_details[:5]])

        message = (
            f"{type_emoji} <b>سیگنال جدید - {signal_type}</b>
"
            f"{'─' * 30}
"
            f"📊 <b>نماد:</b> {symbol} | ⏱ {timeframe}
"
            f"⭐ <b>امتیاز کل:</b> {score:.1f}/100
"
            f"{'─' * 20}
"
            f"🧠 <b>SMC:</b> {smc_score:.1f} | 📈 <b>PA:</b> {pa_score:.1f} | 💧 <b>Liq:</b> {liq_score:.1f}
"
            f"{'─' * 20}
"
            f"🔍 <b>دلایل کنفلوئنس:</b>
{confluence_str}
"
            f"{'─' * 20}
"
            f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_risk_warning(
        self,
        warning_type: str,
        current_value: float,
        limit_value: float,
        description: str,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار ریسک

        پارامترها:
            warning_type: نوع هشدار ریسک
            current_value: مقدار فعلی
            limit_value: حد مجاز
            description: توضیح هشدار
            chat_ids: لیست چت‌ها
        """
        message = (
            f"⚠️ <b>هشدار ریسک - {warning_type}</b>
"
            f"{'─' * 30}
"
            f"📊 <b>مقدار فعلی:</b> {current_value:.2f}
"
            f"🚧 <b>حد مجاز:</b> {limit_value:.2f}
"
            f"📝 <b>توضیح:</b> {description}
"
            f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})

    async def send_system_error(
        self,
        error_type: str,
        error_message: str,
        module: str,
        chat_ids: Optional[list[int]] = None
    ):
        """
        ارسال هشدار خطای سیستمی

        پارامترها:
            error_type: نوع خطا
            error_message: متن خطا
            module: ماژول خطادهنده
            chat_ids: لیست چت‌ها
        """
        message = (
            f"🚨 <b>خطای سیستمی</b>
"
            f"{'─' * 30}
"
            f"⚙️ <b>ماژول:</b> {module}
"
            f"🔴 <b>نوع خطا:</b> {error_type}
"
            f"📝 <b>پیام:</b> {error_message[:200]}
"
            f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        targets = chat_ids or self.admin_chat_ids
        await self._alert_queue.put({"message": message, "chat_ids": targets})


# نمونه singleton برای استفاده در سراسر برنامه
_alert_manager: Optional[TelegramAlertManager] = None


def get_alert_manager() -> Optional[TelegramAlertManager]:
    """دریافت نمونه singleton مدیر هشدار"""
    return _alert_manager


def init_alert_manager(bot, admin_chat_ids: list[int]) -> TelegramAlertManager:
    """
    مقداردهی اولیه مدیر هشدار

    پارامترها:
        bot: نمونه ربات تلگرام
        admin_chat_ids: لیست شناسه ادمین‌ها
    """
    global _alert_manager
    _alert_manager = TelegramAlertManager(bot, admin_chat_ids)
    return _alert_manager
