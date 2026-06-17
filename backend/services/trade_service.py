"""
سرویس معاملات

مدیریت معاملات و گزارش‌های معاملاتی.

نویسنده: MT5 Trading Team
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from ..core.logger import get_logger
from ..core.config import settings
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("trade_service")


class TradeAction(str, Enum):
    """عملیات معامله"""
    OPEN = "open"
    CLOSE = "close"
    MODIFY = "modify"


class TradeService:
    """
    سرویس معاملات

    مسئولیت‌ها:
    - ثبت و مدیریت معاملات
    - محاسبه سود/ضرر
    - گزارش‌گیری
    """

    async def get_trades(
        self,
        user_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        دریافت لیست معاملات

        Args:
            user_id: شناسه کاربر
            status: فیلتر وضعیت
            symbol: فیلتر نماد
            direction: فیلتر جهت
            from_date: از تاریخ
            to_date: تا تاریخ
            limit: حدمكثر تعداد
            offset: از چه رکوردی

        Returns:
            لیست معاملات
        """
        filters = {"user_id": user_id}

        if status:
            filters["status"] = status

        trades = await db.select_many(
            "trades",
            filters=filters,
            order_by="opened_at",
            order_desc=True,
            limit=limit * 2,
            offset=offset
        )

        # فیلترهای اضافی
        if symbol:
            trades = [t for t in trades if t.get("symbol") == symbol]
        if direction:
            trades = [t for t in trades if t.get("direction") == direction]
        if from_date:
            trades = [t for t in trades if t.get("opened_at") and t["opened_at"] >= from_date]
        if to_date:
            trades = [t for t in trades if t.get("opened_at") and t["opened_at"] <= to_date]

        trades = trades[:limit]

        # محاسبه مجموع سود
        total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)

        return {
            "trades": trades,
            "count": len(trades),
            "total_profit": total_profit,
            "limit": limit,
            "offset": offset
        }

    async def get_open_positions(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        دریافت معاملات باز

        Args:
            user_id: شناسه کاربر

        Returns:
            معاملات باز
        """
        trades = await db.select_many(
            "trades",
            filters={
                "user_id": user_id,
                "status": "open"
            },
            order_by="opened_at",
            order_desc=True,
            limit=50
        )

        total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)

        return {
            "positions": trades,
            "count": len(trades),
            "total_profit": total_profit
        }

    async def get_trade(
        self,
        trade_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        دریافت یک معامله

        Args:
            trade_id: شناسه معامله
            user_id: شناسه کاربر

        Returns:
            معامله یا None
        """
        return await db.select_one("trades", {
            "id": trade_id,
            "user_id": user_id
        })

    async def report_trade(
        self,
        user_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        lot_size: float = 0.01,
        open_time: Optional[str] = None,
        close_time: Optional[str] = None,
        profit_money: Optional[float] = None,
        profit_pips: Optional[float] = None,
        signal_id: Optional[str] = None,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ثبت گزارش معامله (از MT5 یا Manual)

        Args:
            user_id: شناسه کاربر
            symbol: نماد
            direction: جهت (buy/sell)
            entry_price: قیمت ورود
            exit_price: قیمت خروج
            stop_loss: حد ضرر
            take_profit: حد سود
            lot_size: حجم
            open_time: زمان باز شدن
            close_time: زمان بسته شدن
            profit_money: سود/ضرر (پول)
            profit_pips: سود/ضرر (پیپ)
            signal_id: شناسه سیگنال مرتبط
            notes: یادداشت
            ip_address: آدرس IP

        Returns:
            معامله ثبت شده
        """
        # تعیین وضعیت
        status = "closed" if exit_price and close_time else "open"

        trade_data = {
            "user_id": user_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "lot_size": lot_size,
            "status": status,
            "opened_at": open_time or datetime.utcnow().isoformat(),
            "closed_at": close_time,
            "profit_money": profit_money or 0,
            "profit_pips": profit_pips or 0,
            "signal_id": signal_id,
            "notes": notes,
            "source": "api"
        }

        result = await db.insert("trades", trade_data)

        # ثبت لاگ
        await audit_service.log_trade(
            user_id=user_id,
            trade_id=result["id"],
            action="open" if status == "open" else "close",
            symbol=symbol,
            direction=direction,
            profit=profit_money,
            ip_address=ip_address
        )

        logger.info(
            f"معامله ثبت شد: {symbol} {direction} - "
            f"ورود: {entry_price} - وضعیت: {status}"
        )

        return result

    async def close_trade(
        self,
        trade_id: str,
        user_id: str,
        exit_price: float,
        close_reason: str = "manual",
        profit_money: Optional[float] = None,
        profit_pips: Optional[float] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        بستن معامله

        Args:
            trade_id: شناسه معامله
            user_id: شناسه کاربر
            exit_price: قیمت خروج
            close_reason: دلیل بستن
            profit_money: سود/ضرر
            profit_pips: سود/ضرر (پیپ)
            ip_address: آدرس IP

        Returns:
            معامله به‌روز شده
        """
        trade = await self.get_trade(trade_id, user_id)
        if not trade:
            return None

        if trade.get("status") != "open":
            return {"error": "معامله در وضعیت باز نیست"}

        # محاسبه سود اگر داده نشده
        if profit_money is None and trade.get("entry_price"):
            direction = trade.get("direction", "buy")
            entry = trade["entry_price"]
            if direction == "buy":
                profit_pips_calc = (exit_price - entry) * 10000
            else:
                profit_pips_calc = (entry - exit_price) * 10000
            profit_pips = profit_pips or profit_pips_calc

        updated = await db.update(
            "trades",
            {"id": trade_id},
            {
                "status": "closed",
                "exit_price": exit_price,
                "closed_at": datetime.utcnow().isoformat(),
                "close_reason": close_reason,
                "profit_money": profit_money or 0,
                "profit_pips": profit_pips or 0
            }
        )

        # ثبت لاگ
        await audit_service.log_trade(
            user_id=user_id,
            trade_id=trade_id,
            action="close",
            symbol=trade.get("symbol", ""),
            direction=trade.get("direction", ""),
            profit=profit_money,
            ip_address=ip_address
        )

        logger.info(
            f"معامله {trade_id} بسته شد در قیمت {exit_price} - "
            f"سود: {profit_money}"
        )

        return updated[0] if updated else None

    async def close_all_trades(
        self,
        user_id: str,
        direction: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        بستن همه معاملات

        Args:
            user_id: شناسه کاربر
            direction: فیلتر جهت
            ip_address: آدرس IP

        Returns:
            نتیجه
        """
        filters = {
            "user_id": user_id,
            "status": "open"
        }

        trades = await db.select_many("trades", filters=filters, limit=100)

        if direction:
            trades = [t for t in trades if t.get("direction") == direction]

        closed_count = 0
        total_profit = 0

        for trade in trades:
            exit_price = trade.get("take_profit") or trade.get("entry_price", 0)

            result = await self.close_trade(
                trade_id=trade["id"],
                user_id=user_id,
                exit_price=exit_price,
                close_reason="close_all",
                ip_address=ip_address
            )

            if result:
                closed_count += 1
                total_profit += result.get("profit_money", 0)

        logger.info(f"{closed_count} معامله بسته شد - مجموع سود: {total_profit}")

        return {
            "closed_count": closed_count,
            "total_profit": total_profit
        }

    async def get_trade_stats(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        آمار معاملات

        Args:
            user_id: شناسه کاربر
            days: تعداد روز

        Returns:
            آمار
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        trades = await db.select_many(
            "trades",
            filters={"user_id": user_id},
            limit=1000
        )

        # فیلتر تاریخ
        trades = [t for t in trades if t.get("opened_at") and t["opened_at"] >= from_date]

        # محاسبه آمار
        total = len(trades)
        closed_trades = [t for t in trades if t.get("status") == "closed"]
        winning = [t for t in closed_trades if t.get("profit_money", 0) > 0]
        losing = [t for t in closed_trades if t.get("profit_money", 0) < 0]

        total_profit = sum(t.get("profit_money", 0) or 0 for t in closed_trades)
        gross_profit = sum(t.get("profit_money", 0) or 0 for t in winning)
        gross_loss = abs(sum(t.get("profit_money", 0) or 0 for t in losing))

        win_rate = len(winning) / len(closed_trades) * 100 if closed_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        avg_trade = total_profit / len(closed_trades) if closed_trades else 0

        return {
            "period_days": days,
            "total_trades": total,
            "open_trades": len([t for t in trades if t.get("status") == "open"]),
            "closed_trades": len(closed_trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(win_rate, 2),
            "total_profit": total_profit,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": round(profit_factor, 2),
            "average_trade": round(avg_trade, 2),
            "best_trade": max((t.get("profit_money", 0) or 0 for t in closed_trades), default=0),
            "worst_trade": min((t.get("profit_money", 0) or 0 for t in closed_trades), default=0)
        }

    async def get_daily_breakdown(
        self,
        user_id: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        تفکیک روزانه

        Args:
            user_id: شناسه کاربر
            days: تعداد روز

        Returns:
            لیست روزانه
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        trades = await db.select_many(
            "trades",
            filters={"user_id": user_id},
            limit=1000
        )

        # فیلتر و گروه‌بندی
        trades = [t for t in trades if t.get("closed_at") and t["closed_at"] >= from_date]

        daily_data = {}
        for trade in trades:
            date = trade["closed_at"][:10]
            if date not in daily_data:
                daily_data[date] = {"date": date, "trades": 0, "profit": 0}
            daily_data[date]["trades"] += 1
            daily_data[date]["profit"] += trade.get("profit_money", 0) or 0

        return sorted(daily_data.values(), key=lambda x: x["date"])


# نمونه گلوبال
trade_service = TradeService()
