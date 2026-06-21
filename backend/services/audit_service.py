from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ..database import db

logger = logging.getLogger("audit_service")

_FLUSH_INTERVAL_S = 5
_BUFFER_MAX = 200
_FLUSH_BATCH = 50


class AuditAction(str, Enum):
    LOGIN          = "login"
    LOGOUT         = "logout"
    TRADE_OPEN     = "trade_open"
    TRADE_CLOSE    = "trade_close"
    SIGNAL_CREATE  = "signal_create"
    SIGNAL_EXECUTE = "signal_execute"
    DECISION_MADE  = "decision_made"
    RISK_BLOCKED   = "risk_blocked"
    ADMIN_ACTION   = "admin_action"
    SECURITY_EVENT = "security_event"
    CONFIG_CHANGE  = "config_change"


class AuditService:
    """
    Non-blocking buffered audit log.

    ARCH-3: asyncio.Lock prevents concurrent flushes
    PERF-4: deque(maxlen=200) prevents unbounded growth
    G-13:   get_action_logs() filter pushed to DB
    G-14:   failed rows re-queued instead of dropped
    G-15:   log_decision() added
    """

    def __init__(self) -> None:
        self._buffer: deque = deque(maxlen=_BUFFER_MAX)
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._flush_loop(), name="audit_flush")
        logger.info("AuditService started (interval=%ds)", _FLUSH_INTERVAL_S)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()
        logger.info("AuditService stopped")

    def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> None:
        entry = {
            "action": action.value,
            "user_id": user_id,
            "ip_address": ip_address,
            "details": details or {},
            "severity": severity,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._buffer.append(entry)

    async def log_async(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> None:
        self.log(action, user_id, ip_address, details, severity)

    async def log_decision(
        self,
        user_id: str,
        symbol: str,
        decision: str,
        confidence: float,
        ip_address: Optional[str] = None,
    ) -> None:
        """G-15: was missing -> AttributeError in decision_service."""
        self.log(
            AuditAction.DECISION_MADE,
            user_id=user_id,
            ip_address=ip_address,
            details={"symbol": symbol, "decision": decision, "confidence": round(confidence, 4)},
        )

    async def log_security_event(
        self,
        event_type: str,
        ip_address: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.log(
            AuditAction.SECURITY_EVENT,
            user_id=user_id,
            ip_address=ip_address,
            details={"event_type": event_type, **(details or {})},
            severity="warning",
        )

    async def get_action_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """G-13: action filter pushed to DB."""
        filters: Dict[str, Any] = {}
        if user_id:
            filters["user_id"] = user_id
        if action:
            filters["action"] = action
        try:
            return await db.select_many(
                "audit_logs",
                filters=filters,
                order_by="created_at",
                order_desc=True,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            logger.error("get_action_logs failed: %s", exc)
            return []

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
            try:
                await self._flush_buffer()
            except Exception as exc:
                logger.error("Flush loop error: %s", exc)

    async def _flush_buffer(self) -> None:
        """ARCH-3: Lock prevents concurrent flushes. G-14: failed rows re-queued."""
        if not self._buffer:
            return

        async with self._lock:
            batch: List[Dict[str, Any]] = []
            while self._buffer and len(batch) < _FLUSH_BATCH:
                batch.append(self._buffer.popleft())

        if not batch:
            return

        try:
            await db.insert_many("audit_logs", batch)
            logger.debug("AuditService flushed %d rows", len(batch))
        except Exception as exc:
            logger.error("AuditService flush failed (%d rows): %s", len(batch), exc)
            # G-14: re-queue failed rows
            async with self._lock:
                for row in reversed(batch):
                    self._buffer.appendleft(row)


audit_service = AuditService()
