"""
backend/services/audit_service_patch.py
Phase S - Audit Service Hardening
S-21: AuditAction.SIGNAL_CREATED missing (AttributeError fix)
S-22: log_async() genuine coroutine
S-23: _flush_buffer() retry on DB failure
S-24: AuditService started in lifespan
"""
from __future__ import annotations
import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger("services.audit_service_patch")

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
    SIGNAL_CREATED     = "signal_create"   # S-21: alias
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
    HEALTH_DEGRADED    = "health_degraded"


class AuditServiceV2:
    """Drop-in replacement with S-21..S-24 fixes."""

    def __init__(self) -> None:
        self._buffer: deque = deque(maxlen=_BUFFER_MAX)
        self._lock    = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._dropped = 0

    async def start(self) -> None:
        """S-24: Call in FastAPI lifespan startup."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._flush_loop(), name="audit_flush_v2")
        logger.info("AuditServiceV2 started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()

    def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> None:
        entry = {
            "action": action.value, "user_id": user_id,
            "ip_address": ip_address, "resource_id": resource_id,
            "details": details or {}, "severity": severity,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._buffer.append(entry)

    async def log_async(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> None:
        """S-22: genuine coroutine."""
        self.log(action, user_id, ip_address, resource_id, details, severity)

    async def log_decision(
        self, user_id: str, symbol: str, decision: str,
        confidence: float, ip_address: Optional[str] = None,
    ) -> None:
        self.log(
            action=AuditAction.DECISION_MADE, user_id=user_id,
            ip_address=ip_address,
            details={"symbol": symbol, "decision": decision, "confidence": confidence},
        )

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL_S)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[Audit] Flush loop error: %s", exc)

    async def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        async with self._lock:
            batch = []
            for _ in range(min(_FLUSH_BATCH, len(self._buffer))):
                if self._buffer:
                    batch.append(self._buffer.popleft())
        if not batch:
            return
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                from backend.database import db
                await asyncio.to_thread(
                    lambda b=batch: db._client.table("audit_logs").insert(b).execute()
                )
                return
            except Exception as exc:
                if attempt == _MAX_RETRIES:
                    logger.error("[Audit] Flush failed after %d attempts; dropping %d rows: %s", _MAX_RETRIES, len(batch), exc)
                    self._dropped += len(batch)
                    return
                await asyncio.sleep(0.5 * attempt)

    @property
    def dropped_count(self) -> int:
        return self._dropped

    def queue_size(self) -> int:
        return len(self._buffer)


audit_service_v2 = AuditServiceV2()
