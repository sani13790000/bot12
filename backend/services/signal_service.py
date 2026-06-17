"""
سرویس سیگنال‌ها

مدیریت سیگنال‌های معاملاتی.

نویسنده: MT5 Trading Team
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..core.logger import get_logger
from ..core.enums import SignalStatus
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("signal_service")


class SignalService:
    """
    سرویس سیگنال

    مسئولیت‌ها:
    - ایجاد و مدیریت سیگنال‌ها
    - ارسال نوتیفیکیشن
    - ردیابی وضعیت
    """

    async def get_signals(
        self,
        user_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        min_score: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        دریافت لیست سیگنال‌ها

        Args:
            user_id: شناسه کاربر
            status: فیلتر وضعیت
            symbol: فیلتر نماد
            direction: فیلتر جهت
            min_score: حداقل امتیاز
            limit: حدمكثر تعداد
            offset: از چه رکوردی

        Returns:
            لیست سیگنال‌ها
        """
        filters = {"user_id": user_id}

        if status:
            filters["status"] = status

        signals = await db.select_many(
            "signals",
            filters=filters,
            order_by="generated_at",
            order_desc=True,
            limit=limit * 2,
            offset=offset
        )

        # فیلترهای اضافی
        if symbol:
            signals = [s for s in signals if s.get("symbol") == symbol]
        if direction:
            signals = [s for s in signals if s.get("direction") == direction]
        if min_score:
            signals = [s for s in signals if s.get("total_score", 0) >= min_score]

        # محدود کردن نتیجه
        signals = signals[:limit]

        return {
            "signals": signals,
            "count": len(signals),
            "limit": limit,
            "offset": offset
        }

    async def get_active_signals(
        self,
        user_id: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        دریافت سیگنال‌های فعال

        Args:
            user_id: شناسه کاربر
            limit: حدم得其 تعداد

        Returns:
            سیگنال‌های فعال
        """
        now = datetime.utcnow().isoformat()

        signals = await db.select_many(
            "signals",
            filters={
                "user_id": user_id,
                "status": "generated"
            },
            order_by="generated_at",
            order_desc=True,
            limit=limit * 2
        )

        # فیلتر سیگنال‌های منقضی نشده
        active = [
            s for s in signals
            if s.get("valid_until") and s["valid_until"] > now
        ][:limit]

        return {
            "active_signals": active,
            "count": len(active)
        }

    async def get_signal(
        self,
        signal_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        دریافت یک سیگنال

        Args:
            signal_id: شناسه سیگنال
            user_id: شناسه کاربر

        Returns:
            سیگنال یا None
        """
        return await db.select_one("signals", {
            "id": signal_id,
            "user_id": user_id
        })

    async def mark_signal_sent(
        self,
        signal_id: str,
        user_id: str,
        sent_to: str = "telegram"
    ) -> Dict[str, Any]:
        """
        علامت‌گذاری سیگنال به عنوان ارسال شده

        Args:
            signal_id: شناسه سیگنال
            user_id: شناسه کاربر
            sent_to: مقصد ارسال

        Returns:
            سیگنال به‌روز شده
        """
        signal = await self.get_signal(signal_id, user_id)
        if not signal:
            return None

        # به‌روزرسانی وضعیت
        updated = await db.update(
            "signals",
            {"id": signal_id},
            {
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat(),
                "sent_to": sent_to
            }
        )

        logger.info(f"سیگنال {signal_id} به عنوان ارسال شده علامت‌گذاری شد")

        return updated[0] if updated else None

    async def mark_signal_executed(
        self,
        signal_id: str,
        user_id: str,
        execution_price: float,
        execution_type: str = "manual"
    ) -> Dict[str, Any]:
        """
        علامت‌گذاری سیگنال به عنوان اجرا شده

        Args:
            signal_id: شناسه سیگنال
            user_id: شناسه کاربر
            execution_price: قیمت اجرا
            execution_type: نوع اجرا

        Returns:
            سیگنال به‌روز شده
        """
        signal = await self.get_signal(signal_id, user_id)
        if not signal:
            return None

        updated = await db.update(
            "signals",
            {"id": signal_id},
            {
                "status": "executed",
                "executed_at": datetime.utcnow().isoformat(),
                "execution_price": execution_price,
                "execution_type": execution_type
            }
        )

        logger.info(f"سیگنال {signal_id} اجرا شد در قیمت {execution_price}")

        return updated[0] if updated else None

    async def expire_signals(self) -> int:
        """
        منقضی کردن سیگنال‌های قدیمی

        Returns:
            تعداد سیگنال‌های منقضی شده
        """
        now = datetime.utcnow().isoformat()

        # دریافت سیگنال‌های منقضی شده
        signals = await db.select_many(
            "signals",
            filters={"status": "generated"},
            limit=1000
        )

        expired_count = 0
        for signal in signals:
            if signal.get("valid_until") and signal["valid_until"] < now:
                await db.update(
                    "signals",
                    {"id": signal["id"]},
                    {"status": "expired", "expired_at": now}
                )
                expired_count += 1

        if expired_count > 0:
            logger.info(f"{expired_count} سیگنال منقضی شد")

        return expired_count

    async def get_signal_stats(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        آمار سیگنال‌ها

        Args:
            user_id: شناسه کاربر
            days: تعداد روز

        Returns:
            آمار
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        signals = await db.select_many(
            "signals",
            filters={"user_id": user_id},
            limit=1000
        )

        # فیلتر تاریخ
        signals = [s for s in signals if s.get("generated_at") and s["generated_at"] >= from_date]

        # محاسبه آمار
        total = len(signals)
        executed = len([s for s in signals if s.get("status") == "executed"])
        expired = len([s for s in signals if s.get("status") == "expired"])
        avg_score = sum(s.get("total_score", 0) for s in signals) / total if total > 0 else 0

        # توزیع جهت
        buy_count = len([s for s in signals if s.get("direction") == "bullish"])
        sell_count = len([s for s in signals if s.get("direction") == "bearish"])

        return {
            "period_days": days,
            "total_signals": total,
            "executed": executed,
            "expired": expired,
            "pending": total - executed - expired,
            "execution_rate": round(executed / total * 100, 2) if total > 0 else 0,
            "average_score": round(avg_score, 2),
            "direction_distribution": {
                "buy": buy_count,
                "sell": sell_count
            }
        }


# نمونه گلوبال
signal_service = SignalService()
