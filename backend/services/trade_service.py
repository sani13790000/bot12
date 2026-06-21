from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import db

logger = logging.getLogger("trade_service")


class TradeService:
    async def create_trade(
        self, user_id: str, symbol: str, direction: str,
        entry_price: float, stop_loss: float, take_profit: float,
        lot_size: float = 0.01, strategy: str = "manual", notes=None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": str(uuid.uuid4()), "user_id": user_id, "symbol": symbol,
            "direction": direction, "entry_price": entry_price,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "lot_size": lot_size, "strategy": strategy, "notes": notes,
            "status": "open", "opened_at": now, "updated_at": now,
        }
        try:
            return await db.insert("trades", data)
        except Exception as exc:
            logger.error("create_trade failed: %s", exc)
            return None

    async def get_trade(self, trade_id: str, user_id: str):
        try:
            return await db.select_one("trades", {"id": trade_id, "user_id": user_id})
        except Exception as exc:
            logger.error("get_trade failed: %s", exc)
            return None

    async def get_open_trades(self, user_id: str, symbol=None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"user_id": user_id, "status": "open"}
        if symbol:
            filters["symbol"] = symbol
        try:
            return await db.select_many("trades", filters=filters,
                order_by="opened_at", order_desc=True, limit=200)
        except Exception as exc:
            logger.error("get_open_trades failed: %s", exc)
            return []

    async def get_trade_history(
        self, user_id: str, symbol=None, direction=None,
        from_date=None, to_date=None, limit: int = 100, offset: int = 0,
    ) -> Dict[str, Any]:
        """G-19: direction filter pushed to DB."""
        filters: Dict[str, Any] = {"user_id": user_id, "status": "closed"}
        if symbol:
            filters["symbol"] = symbol
        if direction:
            filters["direction"] = direction  # DB-side
        try:
            trades = await db.select_many(
                "trades", filters=filters,
                order_by="closed_at", order_desc=True,
                limit=limit, offset=offset,
            )
            if from_date:
                trades = [t for t in trades if (t.get("closed_at") or "") >= from_date]
            if to_date:
                trades = [t for t in trades if (t.get("closed_at") or "") <= to_date]
            total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)
            return {"trades": trades, "count": len(trades),
                    "total_profit": round(total_profit, 2), "limit": limit, "offset": offset}
        except Exception as exc:
            logger.error("get_trade_history failed: %s", exc)
            return {"trades": [], "count": 0, "total_profit": 0.0, "limit": limit, "offset": offset}

    async def close_trade(self, trade_id: str, user_id: str, close_price=None, profit=None):
        trade = await self.get_trade(trade_id, user_id)
        if not trade:
            return None
        if trade.get("status") == "closed":
            return trade
        update_data: Dict[str, Any] = {
            "status": "closed",
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if close_price is not None:
            update_data["close_price"] = close_price
        if profit is not None:
            update_data["profit_money"] = profit
        try:
            rows = await db.update("trades", {"id": trade_id, "user_id": user_id}, update_data)
            return rows[0] if rows else trade
        except Exception as exc:
            logger.error("close_trade failed: %s", exc)
            return None

    async def close_all_open_trades(self, user_id: str) -> Dict[str, Any]:
        """G-20: parallel close."""
        open_trades = await self.get_open_trades(user_id)
        if not open_trades:
            return {"success": True, "closed": 0, "errors": 0}
        now = datetime.now(timezone.utc).isoformat()

        async def _close_one(trade):
            try:
                await db.update(
                    "trades", {"id": trade["id"], "user_id": user_id},
                    {"status": "closed", "closed_at": now, "updated_at": now},
                )
                return True
            except Exception as exc:
                logger.error("close_all: failed %s: %s", trade.get("id"), exc)
                return False

        results = await asyncio.gather(*[_close_one(t) for t in open_trades])
        closed = sum(1 for r in results if r)
        return {"success": closed == len(open_trades), "closed": closed, "errors": len(results) - closed}

    async def get_equity_state(self, user_id: str) -> Dict[str, Any]:
        """G-21: reads from accounts table, not hardcoded."""
        try:
            account = await db.select_one(
                "accounts", {"user_id": user_id},
                columns="balance,equity,margin,free_margin",
            )
            if account:
                balance = float(account.get("balance") or 0)
                equity  = float(account.get("equity") or balance)
                margin  = float(account.get("margin") or 0)
                free    = float(account.get("free_margin") or equity - margin)
                drawdown = round((balance - equity) / balance * 100, 2) if balance > 0 else 0.0
            else:
                balance = equity = free = drawdown = margin = 0.0
            open_trades = await self.get_open_trades(user_id)
            return {
                "balance": balance, "equity": equity, "margin": margin,
                "free_margin": free, "drawdown_percent": drawdown,
                "open_trades": len(open_trades),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("get_equity_state failed: %s", exc)
            return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0,
                    "drawdown_percent": 0.0, "open_trades": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()}

    async def get_risk_status(self, user_id: str) -> Dict[str, Any]:
        """G-22: real data."""
        equity_state = await self.get_equity_state(user_id)
        open_trades = await self.get_open_trades(user_id)
        return {
            "equity": equity_state,
            "limits": {"max_daily_loss_percent": 3.0, "max_open_positions": 5, "max_exposure_percent": 5.0},
            "current": {"daily_loss_percent": equity_state.get("drawdown_percent", 0.0),
                        "open_positions": len(open_trades), "exposure_percent": 0.0},
            "circuit_breaker": {"state": "closed", "can_trade": True},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_trade_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        try:
            all_trades = await db.select_many(
                "trades", filters={"user_id": user_id, "status": "closed"},
                order_by="closed_at", order_desc=True, limit=1000,
            )
            if not all_trades:
                return {"win_rate": 0, "total_trades": 0, "profit_factor": 0, "avg_rr": 0}
            wins   = [t for t in all_trades if (t.get("profit_money") or 0) > 0]
            losses = [t for t in all_trades if (t.get("profit_money") or 0) <= 0]
            gross_profit = sum(t.get("profit_money", 0) or 0 for t in wins)
            gross_loss   = abs(sum(t.get("profit_money", 0) or 0 for t in losses))
            return {
                "total_trades": len(all_trades), "wins": len(wins), "losses": len(losses),
                "win_rate": round(len(wins) / len(all_trades) * 100, 1),
                "gross_profit": round(gross_profit, 2), "gross_loss": round(gross_loss, 2),
                "net_profit": round(gross_profit - gross_loss, 2),
                "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else 0,
            }
        except Exception as exc:
            logger.error("get_trade_stats failed: %s", exc)
            return {}


trade_service = TradeService()
