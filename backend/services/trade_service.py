"""
backend/services/trade_service.py

FIX: datetime.utcnow() x4 replaced with datetime.now(timezone.utc)
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from enum import Enum

from ..core.logger import get_logger
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("trade_service")


class TradeAction(str, Enum):
    OPEN   = "open"
    CLOSE  = "close"
    MODIFY = "modify"


class TradeService:
    async def get_trades(
        self,
        user_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {"user_id": user_id}
        if status:
            filters["status"] = status

        trades = await db.select_many(
            "trades",
            filters=filters,
            order_by="opened_at",
            order_desc=True,
            limit=limit * 2,
            offset=offset,
        )

        if symbol:
            trades = [t for t in trades if t.get("symbol") == symbol]
        if direction:
            trades = [t for t in trades if t.get("direction") == direction]
        if from_date:
            trades = [t for t in trades if (t.get("opened_at") or "") >= from_date]
        if to_date:
            trades = [t for t in trades if (t.get("opened_at") or "") <= to_date]

        trades = trades[:limit]
        total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)

        return {
            "trades":       trades,
            "count":        len(trades),
            "total_profit": total_profit,
            "limit":        limit,
            "offset":       offset,
        }

    async def get_open_positions(self, user_id: str) -> Dict[str, Any]:
        trades = await db.select_many(
            "trades",
            filters={"user_id": user_id, "status": "open"},
            order_by="opened_at",
            order_desc=True,
            limit=50,
        )
        return {
            "positions":    trades,
            "count":        len(trades),
            "total_profit": sum(t.get("profit_money", 0) or 0 for t in trades),
        }

    async def get_trade(self, trade_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await db.select_one("trades", {"id": trade_id, "user_id": user_id})

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
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        status = "closed" if exit_price and close_time else "open"
        # FIX: was datetime.utcnow()
        now_iso = datetime.now(timezone.utc).isoformat()

        trade_data = {
            "user_id":     user_id,
            "symbol":      symbol,
            "direction":   direction,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "lot_size":    lot_size,
            "status":      status,
            "opened_at":   open_time or now_iso,
            "closed_at":   close_time,
            "profit_money": profit_money or 0,
            "profit_pips":  profit_pips or 0,
            "signal_id":   signal_id,
            "notes":       notes,
            "source":      "api",
        }

        result = await db.insert("trades", trade_data)
        await audit_service.log_trade(
            user_id=user_id,
            trade_id=result["id"],
            action="open" if status == "open" else "close",
            symbol=symbol,
            direction=direction,
            profit=profit_money,
            ip_address=ip_address,
        )
        logger.info("trade_reported symbol=%s direction=%s status=%s", symbol, direction, status)
        return result

    async def close_trade(
        self,
        trade_id: str,
        user_id: str,
        exit_price: float,
        close_reason: str = "manual",
        profit_money: Optional[float] = None,
        profit_pips: Optional[float] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        trade = await self.get_trade(trade_id, user_id)
        if not trade:
            return None
        if trade.get("status") != "open":
            return {"error": "trade is not open"}

        if profit_pips is None and trade.get("entry_price"):
            direction = trade.get("direction", "buy")
            entry = trade["entry_price"]
            profit_pips = (
                (exit_price - entry) if direction == "buy" else (entry - exit_price)
            ) * 10000

        # FIX: was datetime.utcnow()
        updated = await db.update(
            "trades",
            {"id": trade_id},
            {
                "status":      "closed",
                "exit_price":  exit_price,
                "closed_at":   datetime.now(timezone.utc).isoformat(),
                "close_reason": close_reason,
                "profit_money": profit_money or 0,
                "profit_pips":  profit_pips or 0,
            },
        )
        await audit_service.log_trade(
            user_id=user_id,
            trade_id=trade_id,
            action="close",
            symbol=trade.get("symbol", ""),
            direction=trade.get("direction", ""),
            profit=profit_money,
            ip_address=ip_address,
        )
        logger.info("trade_closed trade_id=%s exit=%s profit=%s", trade_id, exit_price, profit_money)
        return updated[0] if updated else None

    async def close_all_trades(
        self,
        user_id: str,
        direction: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        trades = await db.select_many(
            "trades",
            filters={"user_id": user_id, "status": "open"},
            limit=100,
        )
        if direction:
            trades = [t for t in trades if t.get("direction") == direction]

        closed_count = 0
        total_profit = 0.0
        for trade in trades:
            exit_price = trade.get("take_profit") or trade.get("entry_price", 0)
            result = await self.close_trade(
                trade_id=trade["id"],
                user_id=user_id,
                exit_price=exit_price,
                close_reason="close_all",
                ip_address=ip_address,
            )
            if result and "error" not in result:
                closed_count += 1
                total_profit += result.get("profit_money", 0) or 0

        return {"closed_count": closed_count, "total_profit": total_profit}

    async def get_trade_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        # FIX: was datetime.utcnow()
        from_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        trades = await db.select_many("trades", filters={"user_id": user_id}, limit=1000)
        trades = [t for t in trades if (t.get("opened_at") or "") >= from_date]

        closed  = [t for t in trades if t.get("status") == "closed"]
        winning = [t for t in closed  if (t.get("profit_money") or 0) > 0]
        losing  = [t for t in closed  if (t.get("profit_money") or 0) < 0]

        total_profit = sum(t.get("profit_money", 0) or 0 for t in closed)
        gross_profit = sum(t.get("profit_money", 0) or 0 for t in winning)
        gross_loss   = abs(sum(t.get("profit_money", 0) or 0 for t in losing))

        win_rate      = len(winning) / len(closed) * 100 if closed else 0.0
        profit_factor = gross_profit / gross_loss         if gross_loss else 0.0
        avg_trade     = total_profit / len(closed)        if closed else 0.0

        return {
            "period_days":    days,
            "total_trades":   len(trades),
            "open_trades":    len([t for t in trades if t.get("status") == "open"]),
            "closed_trades":  len(closed),
            "winning_trades": len(winning),
            "losing_trades":  len(losing),
            "win_rate":       round(win_rate, 2),
            "total_profit":   total_profit,
            "gross_profit":   gross_profit,
            "gross_loss":     gross_loss,
            "profit_factor":  round(profit_factor, 2),
            "average_trade":  round(avg_trade, 2),
            "best_trade":     max((t.get("profit_money") or 0 for t in closed), default=0),
            "worst_trade":    min((t.get("profit_money") or 0 for t in closed), default=0),
        }

    async def get_daily_breakdown(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        # FIX: was datetime.utcnow()
        from_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        trades = await db.select_many("trades", filters={"user_id": user_id}, limit=1000)
        trades = [t for t in trades if (t.get("closed_at") or "") >= from_date]

        daily: Dict[str, Dict[str, Any]] = {}
        for t in trades:
            date = (t["closed_at"] or "")[:10]
            if not date:
                continue
            if date not in daily:
                daily[date] = {"date": date, "trades": 0, "profit": 0.0}
            daily[date]["trades"] += 1
            daily[date]["profit"] += t.get("profit_money", 0) or 0

        return sorted(daily.values(), key=lambda x: x["date"])


trade_service = TradeService()
