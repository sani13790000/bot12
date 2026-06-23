"""backend/services/trade_service.py
Galaxy Vast AI Trading Platform

Phase Q Fixes:
  Q-1: get_trade_history — limit/offset now pushed to DB (was Python-side)
  Q-2: close_trade — asyncio.Lock prevents race-condition double-close
  Q-3: create_trade — idempotency via signal_id dedup key
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import db

logger = logging.getLogger("trade_service")

# Q-2: per-trade close locks  (ticket_id -> Lock)
_close_locks: Dict[str, asyncio.Lock] = {}
_close_locks_meta: asyncio.Lock = asyncio.Lock()

# Q-3: idempotency registry
_IDEMPOTENCY_TTL_S = 3600


async def _get_close_lock(trade_id: str) -> asyncio.Lock:
    async with _close_locks_meta:
        if trade_id not in _close_locks:
            _close_locks[trade_id] = asyncio.Lock()
        return _close_locks[trade_id]


class TradeService:

    async def create_trade(
        self,
        user_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float = 0.01,
        strategy: str = "manual",
        notes: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        # Q-3: duplicate check via signal_id
        if signal_id:
            try:
                existing = await db.select_one("trades", {"signal_id": signal_id, "user_id": user_id})
                if existing:
                    logger.warning("Duplicate trade suppressed signal_id=%s existing=%s", signal_id, existing.get("id"))
                    return existing
            except Exception as exc:
                logger.error("Idempotency check failed signal_id=%s: %s", signal_id, exc)

        now = datetime.now(timezone.utc).isoformat()
        data: Dict[str, Any] = {
            "id": str(uuid.uuid4()), "user_id": user_id, "symbol": symbol,
            "direction": direction, "entry_price": entry_price,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "lot_size": lot_size, "strategy": strategy, "notes": notes,
            "status": "open", "opened_at": now, "updated_at": now,
        }
        if signal_id:
            data["signal_id"] = signal_id
        try:
            result = await db.insert("trades", data)
            logger.info("Trade created id=%s symbol=%s", data["id"], symbol)
            return result
        except Exception as exc:
            logger.error("create_trade failed: %s", exc)
            return None

    async def get_trade(self, trade_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await db.select_one("trades", {"id": trade_id, "user_id": user_id})
        except Exception as exc:
            logger.error("get_trade failed: %s", exc)
            return None

    async def get_open_trades(self, user_id: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"user_id": user_id, "status": "open"}
        if symbol:
            filters["symbol"] = symbol
        try:
            return await db.select_many("trades", filters=filters, order_by="opened_at", order_desc=True, limit=200)
        except Exception as exc:
            logger.error("get_open_trades failed: %s", exc)
            return []

    async def get_trade_history(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"user_id": user_id, "status": "closed"}
        if symbol:
            filters["symbol"] = symbol
        if direction:
            filters["direction"] = direction.upper()
        try:
            # Q-1: limit + offset pushed to DB
            results = await db.select_many(
                "trades", filters=filters,
                order_by="closed_at", order_desc=True,
                limit=limit, offset=offset,
            )
            if from_date or to_date:
                results = [t for t in results if _in_date_range(t.get("closed_at") or t.get("opened_at"), from_date, to_date)]
            return results
        except Exception as exc:
            logger.error("get_trade_history failed: %s", exc)
            return []

    async def close_trade(
        self,
        trade_id: str,
        user_id: str,
        close_price: float,
        close_reason: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        lock = await _get_close_lock(trade_id)
        async with lock:  # Q-2: only one close attempt at a time
            try:
                trade = await db.select_one("trades", {"id": trade_id, "user_id": user_id})
            except Exception as exc:
                logger.error("close_trade DB read failed trade_id=%s: %s", trade_id, exc)
                return None

            if not trade:
                logger.warning("close_trade: not found trade_id=%s", trade_id)
                return None

            if trade.get("status") == "closed":
                logger.warning("close_trade: already closed trade_id=%s (Q-2 double-close prevented)", trade_id)
                return trade

            entry = float(trade.get("entry_price") or 0.0)
            lot = float(trade.get("lot_size") or 0.01)
            direction = trade.get("direction", "BUY").upper()
            pnl_pips = (close_price - entry) if direction == "BUY" else (entry - close_price)
            pnl_usd = round(pnl_pips * lot * 10.0, 2)
            now = datetime.now(timezone.utc).isoformat()
            updates: Dict[str, Any] = {
                "status": "closed", "close_price": close_price,
                "close_reason": close_reason, "pnl_usd": pnl_usd,
                "closed_at": now, "updated_at": now,
            }
            try:
                result = await db.update("trades", {"id": trade_id, "user_id": user_id}, updates)
                logger.info("Trade closed trade_id=%s pnl=%.2f", trade_id, pnl_usd)
                async with _close_locks_meta:
                    _close_locks.pop(trade_id, None)
                return result
            except Exception as exc:
                logger.error("close_trade DB update failed: %s", exc)
                return None

    async def get_risk_status(self, user_id: str) -> Dict[str, Any]:
        try:
            open_trades = await self.get_open_trades(user_id)
            total_exposure = sum(float(t.get("lot_size", 0.01)) * float(t.get("entry_price", 0)) for t in open_trades)
            return {"open_positions": len(open_trades), "total_exposure": round(total_exposure, 2), "circuit_breaker": "CLOSED", "daily_loss_pct": 0.0, "can_trade": True}
        except Exception as exc:
            logger.error("get_risk_status failed: %s", exc)
            return {"open_positions": 0, "total_exposure": 0.0, "can_trade": False}

    async def get_statistics(self, user_id: str) -> Dict[str, Any]:
        try:
            history = await self.get_trade_history(user_id, limit=500)
            if not history:
                return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
            total = len(history)
            wins = sum(1 for t in history if float(t.get("pnl_usd") or 0) > 0)
            pnl = sum(float(t.get("pnl_usd") or 0) for t in history)
            return {"total_trades": total, "win_rate": round(wins / total * 100, 1) if total else 0.0, "total_pnl": round(pnl, 2), "avg_pnl": round(pnl / total, 2) if total else 0.0}
        except Exception as exc:
            logger.error("get_statistics failed: %s", exc)
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}


def _in_date_range(ts: Optional[str], from_date: Optional[str], to_date: Optional[str]) -> bool:
    if ts is None:
        return True
    try:
        t = ts[:10]
        if from_date and t < from_date[:10]:
            return False
        if to_date and t > to_date[:10]:
            return False
        return True
    except Exception:
        return True


trade_service = TradeService()
