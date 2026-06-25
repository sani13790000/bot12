from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("services.audit")

_FLUSH_INTERVAL_S = 5
_BUFFER_MAX       = 500
_FLUSH_BATCH      = 100
_MAX_RETRIES      = 3


class AuditAction(str, Enum):
    LOGIN              = "login"
    LOGOUT             = "logout"
    TOKEN_REFRESH      = "token_refresh"
    TOKEN_REVOKED      = "token_revoked"
    TRADE_OPEN         = "trade_open"
    TRADE_CLOSE        = "trade_close"
    TRADE_MODIFY       = "trade_modify"
    SIGNAL_CREATE      = "signal_create"
    SIGNAL_CREATED     = "signal_create"   # alias — backward compat (patch S-21)
    SIGNAL_EXECUTE     = "signal_execute"
    SIGNAL_EXPIRE      = "signal_expire"
    DECISION_MADE      = "decision_made"
    RISK_BLOCKED       = "risk_blocked"
    CIRCUIT_OPEN       = "circuit_open"
    CIRCUIT_CLOSE      = "circuit_close"
    ADMIN_ACTION       = "admin_action"
    CONFIG_CHANGE      = "config_change"
    USER_CREATED       = "user_created"
    USER_DELETED       = "user_deleted"
    ROLE_CHANGED       = "role_changed"
    SECURITY_EVENT     = "security_event"
    RATE_LIMIT_HIT     = "rate_limit_hit"
    SUSPICIOUS_REQUEST = "suspicious_request"
    SYSTEM_STARTUP     = "system_startup"
    SYSTEM_SHUTDOWN    = "system_shutdown"


class AuditEntry:
    __slots__ = ("action", "user_id", "resource", "detail", "ip", "ts", "success")

    def __init__(
        self,
        action:   AuditAction,
        user_id:  Optional[str]       = None,
        resource: Optional[str]       = None,
        detail:   Optional[Dict[str, Any]] = None,
        ip:       Optional[str]       = None,
        success:  bool                = True,
    ) -> None:
        self.action   = action
        self.user_id  = user_id
        self.resource = resource
        self.detail   = detail or {}
        self.ip       = ip
        self.ts       = datetime.now(timezone.utc).isoformat()
        self.success  = success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action":   self.action.value,
            "user_id":  self.user_id,
            "resource": self.resource,
            "detail":   self.detail,
            "ip":       self.ip,
            "timestamp": self.ts,
            "success":  self.success,
        }


class AuditService:
    """Buffered async audit logger with retry-on-failure flush."""

    def __init__(self) -> None:
        self._buffer: deque = deque(maxlen=_BUFFER_MAX)
        self._lock   = asyncio.Lock()
        self._task:  Optional[asyncio.Task] = None
        self._db:    Any = None

    def set_db(self, db: Any) -> None:
        self._db = db

    async def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop(), name="audit_flush")
        logger.info("[AuditService] started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self._flush_all()

    async def log(self, entry: AuditEntry) -> None:
        async with self._lock:
            self._buffer.append(entry)

    async def log_async(
        self,
        action:   AuditAction,
        user_id:  Optional[str]       = None,
        resource: Optional[str]       = None,
        detail:   Optional[Dict[str, Any]] = None,
        ip:       Optional[str]       = None,
        success:  bool                = True,
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
                    logger.error("[AuditService] dropping %d entries after %d retries", len(batch), _MAX_RETRIES)

    async def _flush_all(self) -> None:
        while True:
            async with self._lock:
                if not self._buffer:
                    break
            await self._flush_batch()

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


async def log_audit(
    action:   AuditAction,
    user_id:  Optional[str]       = None,
    resource: Optional[str]       = None,
    detail:   Optional[Dict[str, Any]] = None,
    ip:       Optional[str]       = None,
    success:  bool                = True,
) -> None:
    """Module-level convenience wrapper."""
    svc = get_audit_service()
    await svc.log_async(action, user_id, resource, detail, ip, success)
