from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("services.audit")

_FLUSH_INTERVAL_S = 5
_FLUSH_BATCH = 50
_MAX_RETRIES = 3
_BUFFER_CAP = 5_000


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    SIGNAL_CREATE = "signal_create"
    SIGNAL_CREATED = "signal_create"  # alias — backward compat (patch S-21)
    SIGNAL_EXECUTE = "signal_execute"
    SIGNAL_CANCEL = "signal_cancel"
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    RISK_BLOCK = "risk_block"
    RISK_HALT = "risk_halt"
    RISK_RESUME = "risk_resume"
    SETTINGS_CHANGE = "settings_change"
    USER_DELETE = "user_delete"
    ADMIN_ACTION = "admin_action"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"


@dataclass
class AuditEntry:
    action: AuditAction
    user_id: Optional[str] = None
    resource: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    ip: Optional[str] = None
    success: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "user_id": self.user_id,
            "resource": self.resource,
            "detail": self.detail or {},
            "ip": self.ip,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
        }


class AuditService:
    """Async buffered audit log with DB flush."""

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._buffer: Deque[AuditEntry] = deque(maxlen=_BUFFER_CAP)
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self._flush_all()

    async def log(self, entry: AuditEntry) -> None:
        async with self._lock:
            self._buffer.append(entry)

    async def log_async(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """S-22: genuine coroutine (was sync returning coroutine)."""
        entry = AuditEntry(action, user_id, resource, detail, ip, success)
        await self.log(entry)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """S-23: retry on DB failure."""
        async with self._lock:
            batch: List[AuditEntry] = []
            for _ in range(min(_FLUSH_BATCH, len(self._buffer))):
                batch.append(self._buffer.popleft())

        if not batch or self._db is None:
            return

        rows = [e.to_dict() for e in batch]
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                await self._db.insert_many("audit_logs", rows)
                return
            except Exception as exc:
                logger.warning("[AuditService] flush attempt %d failed: %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(attempt)
                else:
                    logger.error(
                        "[AuditService] dropping %d entries after %d retries",
                        len(batch),
                        _MAX_RETRIES,
                    )

    async def _flush_all(self) -> None:
        """H-7 FIX: flush with error guard to prevent infinite loop on shutdown."""
        while True:
            async with self._lock:
                if not self._buffer:
                    break
            try:
                await self._flush_batch()
            except Exception:
                logger.error(
                    "[AuditService] _flush_all error — stopping flush to prevent data loss",
                    exc_info=True,
                )
                break

    async def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        async with self._lock:
            entries = list(self._buffer)[-limit:]
        return [e.to_dict() for e in reversed(entries)]


# ── singleton ──────────────────────────────────────────────────────────────
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
