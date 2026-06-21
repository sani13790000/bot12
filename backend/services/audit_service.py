from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.logger import get_logger
from backend.database import db

logger = get_logger("audit_service")


class AuditAction(str, Enum):
    LOGIN         = "login"
    LOGOUT        = "logout"
    REGISTER      = "register"
    TOKEN_REFRESH = "token_refresh"
    DECISION      = "decision"
    SIGNAL        = "signal"
    TRADE_OPEN    = "trade_open"
    TRADE_CLOSE   = "trade_close"
    LICENSE       = "license"
    ADMIN         = "admin"
    SECURITY      = "security"
    ANOMALY       = "anomaly"


class AuditService:
    """
    Buffered audit logger with async-safe parallel flush.

    ARCH-3 FIX : asyncio.Lock guards _buffer (race-condition prevention).
    PERF-4 FIX : deque(maxlen=200) bounds memory even when DB is down.
    TECH-6 FIX : datetime.now(timezone.utc) replaces deprecated utcnow().
    F-3    FIX : get_action_logs() pushes filter to DB instead of N+1 Python fetch.
    G-1    FIX : _flush_locked() uses asyncio.gather() - parallel not sequential.
    G-2    FIX : entries re-queued on failure (no data loss on partial error).
    """

    _FLUSH_AT: int = 50
    _MAX_BUF:  int = 200

    def __init__(self) -> None:
        self._buffer: deque[Dict[str, Any]] = deque(maxlen=self._MAX_BUF)
        self._lock: asyncio.Lock = asyncio.Lock()

    async def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        *,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "action":        action.value,
            "user_id":       user_id,
            "ip_address":    ip_address,
            "details":       details or {},
            "success":       success,
            "error_message": error_message,
            "created_at":    datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= self._FLUSH_AT:
                await self._flush_locked()

    async def log_login(
        self,
        user_id: str,
        success: bool,
        ip_address: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        await self.log(
            AuditAction.LOGIN, user_id,
            ip_address=ip_address, success=success, error_message=error_message,
        )

    async def log_decision(
        self, user_id: str, symbol: str, decision: str,
        confidence: float, ip_address: Optional[str] = None,
    ) -> None:
        await self.log(
            AuditAction.DECISION, user_id, ip_address=ip_address,
            details={"symbol": symbol, "decision": decision, "confidence": confidence},
        )

    async def log_signal(
        self, user_id: str, signal_id: str, action: str,
        ip_address: Optional[str] = None,
    ) -> None:
        await self.log(
            AuditAction.SIGNAL, user_id, ip_address=ip_address,
            details={"signal_id": signal_id, "action": action},
        )

    async def log_trade(
        self, user_id: str, trade_id: str, action: str,
        symbol: str, lot_size: float, ip_address: Optional[str] = None,
    ) -> None:
        action_enum = AuditAction.TRADE_OPEN if action == "open" else AuditAction.TRADE_CLOSE
        await self.log(
            action_enum, user_id, ip_address=ip_address,
            details={"trade_id": trade_id, "symbol": symbol, "lot_size": lot_size},
        )

    async def log_license(
        self, user_id: str, action: str, success: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self.log(
            AuditAction.LICENSE, user_id,
            details={"action": action, **(details or {})}, success=success,
        )

    async def get_user_logs(
        self, user_id: str, limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            result = await db.select(
                "activity_logs",
                filters={"user_id": user_id},
                limit=limit + offset,
            )
            return result[offset: offset + limit]
        except Exception as exc:
            logger.error("get_user_logs failed: %s", exc)
            return []

    async def get_action_logs(
        self, action: AuditAction, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """F-3 FIX: DB-side filter replaces Python-side over-fetch."""
        try:
            return await db.select(
                "activity_logs",
                filters={"action": action.value},
                limit=limit,
            )
        except Exception as exc:
            logger.error("get_action_logs failed: %s", exc)
            return []

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        """
        G-1 FIX: parallel inserts via asyncio.gather() instead of sequential loop.
        G-2 FIX: entries re-queued on failure - no silent data loss.
        Buffer cleared BEFORE gather to prevent double-flush race.
        Failed entries put back into buffer (preserved via appendleft).
        """
        if not self._buffer:
            return
        entries = list(self._buffer)
        self._buffer.clear()

        async def _insert_one(entry: Dict[str, Any]) -> Optional[Exception]:
            try:
                await db.insert("activity_logs", entry, use_admin=True)
                return None
            except Exception as exc:
                return exc

        results = await asyncio.gather(*[_insert_one(e) for e in entries])

        failed = [entries[i] for i, r in enumerate(results) if r is not None]
        if failed:
            for entry in reversed(failed):
                self._buffer.appendleft(entry)
            logger.error(
                "Audit flush: %d/%d entries failed, %d re-queued.",
                len(failed), len(entries), len(failed),
            )
        else:
            logger.debug("Audit flush: %d entries written.", len(entries))


audit_service = AuditService()
