"""backend/services/signal_service.py v2 - Phase T"""
from __future__ import annotations
import asyncio, logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("services.signal_service")
_now_utc = lambda: datetime.now(timezone.utc)


class SignalService:
    def __init__(self, db) -> None:
        self._db = db

    async def create_signal(self, user_id, symbol, direction, entry_price, stop_loss,
                            take_profit, signal_id=None, expires_in_seconds=3600, extra=None):
        sid = signal_id or str(uuid4())
        try:
            r = await self._db_execute(self._db.table("signals").select("*").eq("id", sid)
                                       .eq("user_id", user_id).limit(1).execute)
            if r.data:
                logger.info("create_signal: duplicate signal_id=%s", sid)
                return r.data[0]
        except Exception as exc:
            logger.warning("create_signal: idempotency check failed: %s", exc)
        now = _now_utc(); expires = now + timedelta(seconds=expires_in_seconds)
        payload = {"id": sid, "user_id": user_id, "symbol": symbol.upper(),
                   "direction": direction.upper(), "entry_price": entry_price,
                   "stop_loss": stop_loss, "take_profit": take_profit, "status": "ACTIVE",
                   "created_at": now.isoformat(), "expires_at": expires.isoformat(),
                   **(extra or {})}
        result = await self._db_execute(self._db.table("signals").insert(payload).execute)
        if not result.data: raise RuntimeError(f"insert empty for id={sid}")
        return result.data[0]

    async def get_signal_by_id(self, signal_id: str, user_id: str):  # T-19: user_id mandatory
        r = await self._db_execute(self._db.table("signals").select("*")
                                   .eq("id", signal_id).eq("user_id", user_id).limit(1).execute)
        return r.data[0] if r.data else None

    async def get_active_signals(self, user_id: str, symbol=None):
        now_iso = _now_utc().isoformat()
        q = (self._db.table("signals").select("*").eq("user_id", user_id)
             .eq("status", "ACTIVE").gt("expires_at", now_iso).order("created_at", desc=True))
        if symbol: q = q.eq("symbol", symbol.upper())
        r = await self._db_execute(q.execute)
        return r.data or []

    async def list_signals(self, user_id, status=None, symbol=None, direction=None,
                           min_score=None, page=1, page_size=50):
        page_size = min(max(1, page_size), 200); offset = (max(1, page) - 1) * page_size
        q = (self._db.table("signals").select("*", count="exact").eq("user_id", user_id)
             .order("created_at", desc=True).range(offset, offset + page_size - 1))
        if status:    q = q.eq("status",    status.upper())
        if symbol:    q = q.eq("symbol",    symbol.upper())
        if direction: q = q.eq("direction", direction.upper())
        r = await self._db_execute(q.execute)
        signals = r.data or []
        if min_score is not None:
            signals = [s for s in signals if float(s.get("score", 0)) >= min_score]
        return {"signals": signals, "total": getattr(r, "count", len(signals)),
                "page": page, "page_size": page_size}

    async def update_signal_status(self, signal_id, user_id, new_status, updated_at=None):
        now = _now_utc()
        q = (self._db.table("signals").update({"status": new_status.upper(),
             "updated_at": now.isoformat()}).eq("id", signal_id).eq("user_id", user_id))
        if updated_at is not None: q = q.eq("updated_at", updated_at.isoformat())
        r = await self._db_execute(q.execute)
        return bool(r.data)

    @staticmethod
    async def _db_execute(fn):
        return await asyncio.to_thread(fn)
