"""backend/services/trade_service.py v2 - Phase T"""
from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("services.trade_service")
_now_utc = lambda: datetime.now(timezone.utc)
_TRADE_LOCKS: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class TradeService:
    def __init__(self, db) -> None:
        self._db = db

    async def create_trade(self, user_id, signal_id, symbol, direction,
                           lot_size, entry_price, stop_loss, take_profit, extra=None):
        try:
            r = await self._db_execute(self._db.table("trades").select("*")
                                       .eq("user_id", user_id).eq("signal_id", signal_id).limit(1).execute)
            if r.data:
                logger.info("create_trade: duplicate signal_id=%s", signal_id); return r.data[0]
        except Exception as exc:
            logger.warning("create_trade: idempotency check: %s", exc)
        trade_id = str(uuid4()); now = _now_utc()
        payload = {"id": trade_id, "user_id": user_id, "signal_id": signal_id,
                   "symbol": symbol.upper(), "direction": direction.upper(),
                   "lot_size": lot_size, "entry_price": entry_price,
                   "stop_loss": stop_loss, "take_profit": take_profit,
                   "status": "OPEN", "opened_at": now.isoformat(), "updated_at": now.isoformat(),
                   **(extra or {})}
        r = await self._db_execute(self._db.table("trades").insert(payload).execute)
        if not r.data: raise RuntimeError(f"insert empty trade_id={trade_id}")
        return r.data[0]

    async def get_trade(self, trade_id, user_id):
        r = await self._db_execute(self._db.table("trades").select("*")
                                   .eq("id", trade_id).eq("user_id", user_id).limit(1).execute)
        return r.data[0] if r.data else None

    async def get_open_trades(self, user_id):
        r = await self._db_execute(self._db.table("trades").select("*")
                                   .eq("user_id", user_id).eq("status", "OPEN")
                                   .order("opened_at", desc=True).execute)
        return r.data or []

    async def get_trade_history(self, user_id, page=1, page_size=50, symbol=None, status=None):
        page_size = min(max(1, page_size), 500); offset = (max(1, page) - 1) * page_size
        q = (self._db.table("trades").select("*", count="exact").eq("user_id", user_id)
             .order("opened_at", desc=True).range(offset, offset + page_size - 1))
        if symbol: q = q.eq("symbol", symbol.upper())
        if status: q = q.eq("status", status.upper())
        r = await self._db_execute(q.execute)
        return {"trades": r.data or [], "total": getattr(r, "count", 0),
                "page": page, "page_size": page_size}

    async def close_trade(self, trade_id, user_id, close_price, pnl, reason="MANUAL"):
        lock = _TRADE_LOCKS[trade_id]
        async with lock:
            trade = await self.get_trade(trade_id, user_id)
            if trade is None or trade.get("status") != "OPEN": return False
            now = _now_utc()
            r = await self._db_execute(
                self._db.table("trades").update({
                    "status": "CLOSED", "close_price": close_price, "pnl": pnl,
                    "close_reason": reason, "closed_at": now.isoformat(),
                    "updated_at": now.isoformat()})
                .eq("id", trade_id).eq("user_id", user_id).eq("status", "OPEN").execute
            )
            return bool(r.data)

    async def update_trade(self, trade_id, user_id, updates, current_updated_at=None):
        updates["updated_at"] = _now_utc().isoformat()
        q = self._db.table("trades").update(updates).eq("id", trade_id).eq("user_id", user_id)
        if current_updated_at is not None: q = q.eq("updated_at", current_updated_at.isoformat())
        r = await self._db_execute(q.execute)
        return bool(r.data)

    async def get_equity_state(self, user_id=None):
        try:
            q = self._db.table("trades").select("pnl, status")
            if user_id: q = q.eq("user_id", user_id)
            r   = await self._db_execute(q.execute)
            rows = r.data or []
            closed = sum(float(x.get("pnl") or 0) for x in rows if x.get("status") == "CLOSED")
            open_p = sum(float(x.get("pnl") or 0) for x in rows if x.get("status") == "OPEN")
            return {"balance": 10_000.0 + closed, "equity": 10_000.0 + closed + open_p, "open_pnl": open_p}
        except Exception as exc:
            logger.error("get_equity_state failed: %s", exc)
            return {"balance": 0.0, "equity": 0.0, "open_pnl": 0.0}

    @staticmethod
    async def _db_execute(fn): return await asyncio.to_thread(fn)


async def get_equity_state(user_id=None):
    """Module-level helper used by main.py startup."""
    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        return await TradeService(db).get_equity_state(user_id)
    except Exception as exc:
        logger.warning("module-level get_equity_state failed: %s", exc)
        return {"balance": 0.0, "equity": 0.0, "open_pnl": 0.0}
