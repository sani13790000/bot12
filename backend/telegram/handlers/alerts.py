"""
=====================================================================
فایل: backend/telegram/handlers/alerts.py

توضیح:
    این هندلر تمام هشدارهای Telegram را مدیریت می‌کند:
    - هشدار ورود به معامله
    - هشدار خروج از معامله
    - هشدار SL / TP زده شدن
    - هشدار باز شدن سشن معاملاتی
    - هشدار پایان سشن معاملاتی
    - هشدار فعال شدن Kill Zone
    - هشدار سیستم (خطا، اتصال، ...)

    اتصال به session_alert_service:
        این هندلر callback خود را به SessionAlertService ثبت می‌کند.
        وقتی سشن تغییر می‌کند → alert_callback() صدا زده می‌شود → پیام به ادمین‌ها ارسال می‌شود.

نویسنده: MT5 Trading Team
نسخه: 2.0.0
=====================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from aiogram import Bot
from aiogram.types import Message

from ..rbac import require_permission, Permission
from ...core.config import settings
from ...services.session_alert_service import session_alert_service, set_alert_callback
from ...core.logger import get_logger

logger = get_logger("telegram.alerts")


class AlertsHandler:
    """
    هندلر هشدارهای Telegram

    این کلاس تمام توابع ارسال هشدار را دارد.
    در bot.py نمونه‌سازی می‌شود و callback به SessionAlertService ثبت می‌شود.
    """

    def __init__(self, bot: Bot):
        """
        مقداردهی اولیه

        Args:
            bot: نمونه Bot از aiogram
        """
        self._bot = bot
        self._admin_ids: List[int] = settings.TELEGRAM_ADMIN_CHAT_IDS or []
        logger.info(f"AlertsHandler راه‌اندازی شد — {len(self._admin_ids)} ادمین")

        # ثبت callback برای session_alert_service
        set_alert_callback(self._session_alert_callback)
        logger.info("✅ Session alert callback ثبت شد")

    # ─────────────────────────────────────────────
    # هشدارهای معامله
    # ─────────────────────────────────────────────

    async def send_trade_open_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        lot_size: float,
        ticket: Optional[int] = None,
        score: Optional[float] = None,
        reason: Optional[str] = None
    ):
        """
        ارسال هشدار باز شدن معامله

        Args:
            symbol: نماد (مثل EURUSD)
            direction: جهت: BUY یا SELL
            entry_price: قیمت ورود
            sl_price: قیمت استاپ لاس
            tp_price: قیمت تیک پرافیت
            lot_size: حجم لات
            ticket: شماره تیکت MT5
            score: امتیاز تصمیم
            reason: دلیل ورود
        """
        emoji = "🟢" if direction == "BUY" else "🔴"
        direction_fa = "خرید" if direction == "BUY" else "فروش"

        sl_pips = abs(entry_price - sl_price) * 10000
        tp_pips = abs(tp_price - entry_price) * 10000
        rr = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0

        text = (
            f"{emoji} <b>معامله جدید باز شد</b>

"
            f"📊 <b>نماد:</b> {symbol}
"
            f"📍 <b>جهت:</b> {direction_fa}
"
            f"💰 <b>قیمت ورود:</b> {entry_price}
"
            f"🛑 <b>استاپ لاس:</b> {sl_price} ({sl_pips:.0f} پیپ)
"
            f"🎯 <b>تیک پرافیت:</b> {tp_price} ({tp_pips:.0f} پیپ)
"
            f"📦 <b>حجم لات:</b> {lot_size}
"
            f"⚖️ <b>ریسک/ریوارد:</b> 1:{rr}
"
        )
        if ticket:
            text += f"🎫 <b>تیکت:</b> #{ticket}
"
        if score:
            text += f"⭐ <b>امتیاز:</b> {score:.1f}/100
"
        if reason:
            text += f"📝 <b>دلیل:</b> {reason}
"
        text += f"
🕐 {self._now_fa()}"

        await self._broadcast(text)
        logger.info(f"📢 هشدار ورود ارسال شد: {symbol} {direction}")

    async def send_trade_close_alert(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        close_price: float,
        profit: float,
        profit_pips: float,
        lot_size: float,
        close_reason: str,
        ticket: Optional[int] = None
    ):
        """
        ارسال هشدار بسته شدن معامله

        Args:
            symbol: نماد
            direction: جهت اولیه معامله
            entry_price: قیمت ورود
            close_price: قیمت خروج
            profit: سود/ضرر به ارز
            profit_pips: سود/ضرر به پیپ
            lot_size: حجم لات
            close_reason: دلیل بستن: SL, TP, MANUAL, TRAILING
            ticket: شماره تیکت
        """
        direction_fa = "خرید" if direction == "BUY" else "فروش"

        if profit >= 0:
            emoji = "✅"
            profit_fa = f"+{profit:.2f}$"
            pips_fa = f"+{profit_pips:.1f} پیپ"
        else:
            emoji = "❌"
            profit_fa = f"{profit:.2f}$"
            pips_fa = f"{profit_pips:.1f} پیپ"

        reason_map = {
            "SL": "🛑 استاپ لاس",
            "TP": "🎯 تیک پرافیت",
            "MANUAL": "👤 دستی",
            "TRAILING": "📈 تریلینگ استاپ",
            "PARTIAL": "✂️ بستن جزئی"
        }
        reason_fa = reason_map.get(close_reason, close_reason)

        text = (
            f"{emoji} <b>معامله بسته شد</b>

"
            f"📊 <b>نماد:</b> {symbol}
"
            f"📍 <b>جهت:</b> {direction_fa}
"
            f"💰 <b>ورود:</b> {entry_price}  ←  <b>خروج:</b> {close_price}
"
            f"💵 <b>نتیجه:</b> {profit_fa} ({pips_fa})
"
            f"📦 <b>حجم:</b> {lot_size}
"
            f"📌 <b>دلیل:</b> {reason_fa}
"
        )
        if ticket:
            text += f"🎫 <b>تیکت:</b> #{ticket}
"
        text += f"
🕐 {self._now_fa()}"

        await self._broadcast(text)
        logger.info(f"📢 هشدار خروج ارسال شد: {symbol} سود={profit:.2f}")

    async def send_sl_hit_alert(self, symbol: str, ticket: int, loss: float, loss_pips: float):
        """هشدار زده شدن استاپ لاس"""
        text = (
            f"🛑 <b>استاپ لاس زده شد!</b>

"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎫 <b>تیکت:</b> #{ticket}
"
            f"💸 <b>ضرر:</b> {loss:.2f}$ ({loss_pips:.1f} پیپ)
"
            f"
🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def send_tp_hit_alert(self, symbol: str, ticket: int, profit: float, profit_pips: float):
        """هشدار زده شدن تیک پرافیت"""
        text = (
            f"🎯 <b>تیک پرافیت زده شد!</b>

"
            f"📊 <b>نماد:</b> {symbol}
"
            f"🎫 <b>تیکت:</b> #{ticket}
"
            f"💰 <b>سود:</b> +{profit:.2f}$ (+{profit_pips:.1f} پیپ)
"
            f"
🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    # ─────────────────────────────────────────────
    # هشدارهای سشن — ارسال می‌شوند از SessionAlertService
    # ─────────────────────────────────────────────

    async def send_session_open_alert(self, session_name: str, data: dict):
        """
        هشدار باز شدن سشن معاملاتی

        Args:
            session_name: نام سشن: London, New York, Tokyo, Sydney
            data: داده‌های کامل سشن از SessionAlertService
        """
        session_emojis = {
            "London": "🇬🇧",
            "New York": "🇺🇸",
            "Tokyo": "🇯🇵",
            "Sydney": "🇦🇺",
            "London/NY Overlap": "🌐"
        }
        emoji = session_emojis.get(session_name, "🔔")
        can_trade_fa = "✅ بله" if data.get("can_trade") else "❌ خیر"

        text = (
            f"{emoji} <b>سشن {session_name} باز شد</b>

"
            f"⏰ <b>زمان:</b> {data.get('utc_time', '')}
"
            f"📊 <b>امتیاز سشن:</b> {data.get('session_score', 0):.0f}/100
"
            f"💹 <b>قابل معامله:</b> {can_trade_fa}
"
        )

        if data.get("is_overlap"):
            text += "🌐 <b>Overlap لندن/نیویورک فعال است</b>
"

        if data.get("kill_zone") and data.get("kill_zone") != "بدون Kill Zone":
            text += f"🎯 <b>Kill Zone:</b> {data.get('kill_zone')}
"

        if data.get("minutes_to_london") and data.get("minutes_to_london") > 0:
            text += f"⏳ <b>تا لندن:</b> {data.get('minutes_to_london')} دقیقه
"

        if data.get("minutes_to_ny") and data.get("minutes_to_ny") > 0:
            text += f"⏳ <b>تا نیویورک:</b> {data.get('minutes_to_ny')} دقیقه
"

        text += f"
🕐 {self._now_fa()}"
        await self._broadcast(text)
        logger.info(f"📢 هشدار باز شدن سشن {session_name} ارسال شد")

    async def send_session_close_alert(self, session_name: str, data: dict):
        """
        هشدار پایان سشن معاملاتی

        Args:
            session_name: نام سشن بسته‌شده
            data: اطلاعات سشن‌های باقیمانده
        """
        session_emojis = {
            "London": "🇬🇧",
            "New York": "🇺🇸",
            "Tokyo": "🇯🇵",
            "Sydney": "🇦🇺",
            "London/NY Overlap": "🌐"
        }
        emoji = session_emojis.get(session_name, "🔕")
        remaining = data.get("remaining_sessions", [])
        remaining_fa = "، ".join(remaining) if remaining else "هیچ سشنی"

        text = (
            f"{emoji} <b>سشن {session_name} پایان یافت</b>

"
            f"⏰ <b>زمان:</b> {data.get('utc_time', '')}
"
            f"📋 <b>سشن‌های فعال:</b> {remaining_fa}
"
            f"
🕐 {self._now_fa()}"
        )
        await self._broadcast(text)
        logger.info(f"📢 هشدار پایان سشن {session_name} ارسال شد")

    async def send_kill_zone_alert(self, kz_name: str, data: dict):
        """هشدار فعال شدن Kill Zone"""
        can_trade_fa = "✅ بله" if data.get("can_trade") else "❌ خیر"
        text = (
            f"🎯 <b>Kill Zone فعال شد</b>

"
            f"📍 <b>نوع:</b> {kz_name}
"
            f"⏰ <b>زمان:</b> {data.get('utc_time', '')}
"
            f"📊 <b>امتیاز:</b> {data.get('session_score', 0):.0f}/100
"
            f"💹 <b>قابل معامله:</b> {can_trade_fa}
"
            f"
🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def send_kill_zone_close_alert(self, kz_name: str, data: dict):
        """هشدار پایان Kill Zone"""
        text = (
            f"⏰ <b>Kill Zone پایان یافت</b>

"
            f"📍 <b>نوع:</b> {kz_name}
"
            f"🕐 {data.get('utc_time', '')}
"
        )
        await self._broadcast(text)

    # ─────────────────────────────────────────────
    # هشدارهای سیستم
    # ─────────────────────────────────────────────

    async def send_system_alert(self, message: str, level: str = "INFO"):
        """
        ارسال هشدار سیستم

        Args:
            message: متن هشدار
            level: سطح: INFO, WARNING, ERROR, CRITICAL
        """
        level_emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨"
        }
        emoji = level_emojis.get(level.upper(), "📢")
        text = (
            f"{emoji} <b>هشدار سیستم [{level}]</b>

"
            f"{message}
"
            f"
🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def send_bot_started_alert(self):
        """هشدار شروع ربات"""
        text = (
            f"🟢 <b>ربات معاملاتی شروع به کار کرد</b>

"
            f"✅ تمام سرویس‌ها فعال شدند
"
            f"🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def send_bot_stopped_alert(self):
        """هشدار توقف ربات"""
        text = (
            f"🔴 <b>ربات معاملاتی متوقف شد</b>

"
            f"🕐 {self._now_fa()}"
        )
        await self._broadcast(text)

    # ─────────────────────────────────────────────
    # callback داخلی برای SessionAlertService
    # ─────────────────────────────────────────────

    async def _session_alert_callback(self, alert_type: str, data: dict):
        """
        callback که توسط SessionAlertService صدا زده می‌شود

        Args:
            alert_type: نوع هشدار: SESSION_OPEN, SESSION_CLOSE, KILL_ZONE_OPEN, KILL_ZONE_CLOSE
            data: داده‌های هشدار
        """
        try:
            if alert_type == "SESSION_OPEN":
                await self.send_session_open_alert(data.get("session_name", "ناشناس"), data)
            elif alert_type == "SESSION_CLOSE":
                await self.send_session_close_alert(data.get("session_name", "ناشناس"), data)
            elif alert_type == "KILL_ZONE_OPEN":
                await self.send_kill_zone_alert(data.get("kill_zone_name", "ناشناس"), data)
            elif alert_type == "KILL_ZONE_CLOSE":
                await self.send_kill_zone_close_alert(data.get("kill_zone_name", "ناشناس"), data)
            else:
                logger.warning(f"نوع هشدار ناشناس: {alert_type}")
        except Exception as e:
            logger.error(f"خطا در _session_alert_callback: {e}", exc_info=True)

    # ─────────────────────────────────────────────
    # توابع کمکی
    # ─────────────────────────────────────────────

    async def _broadcast(self, text: str):
        """
        ارسال پیام به تمام ادمین‌ها

        Args:
            text: متن پیام (HTML)
        """
        if not self._admin_ids:
            logger.warning("هیچ ادمینی برای ارسال هشدار تعریف نشده")
            return

        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"خطا در ارسال هشدار به ادمین {admin_id}: {e}")

    @staticmethod
    def _now_fa() -> str:
        """زمان فعلی به فرمت فارسی"""
        now = datetime.now(timezone.utc)
        return now.strftime("%Y/%m/%d — %H:%M UTC")
