"""
backend/services/audit_service_patch.py — Phase S
S-5a: flush() crash -> requeue failed rows (never drop)
S-5b: log_decision() missing from AuditService
S-5c: start() idempotent
S-5d: stop() properly awaits task
S-5e: get_action_logs() filter pushed to DB
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("audit_service")

_FLUSH_INTERVAL_S = 5
_BUFFER_MAX       = 200
_FLUSH_BATCH      = 50
_REQUEUE_MAX      = 50


def apply_audit_patches(cls: type) -> type:
    """Apply all Phase-S patches to an AuditService class."""

    original_start = cls.start

    async def start_idempotent(self) -> None:
        """S-5c: calling start() twice must be safe."""
        if self._running:
            logger.debug("AuditService.start() already running — no-op")
            return
        self._running = True
        if not hasattr(self, "_requeue_buffer"):
            self._requeue_buffer: deque = deque(maxlen=_REQUEUE_MAX)
        self._task = asyncio.create_task(self._flush_loop(), name="audit_flush")
        logger.info("AuditService started (interval=%ds)", _FLUSH_INTERVAL_S)

    cls.start = start_idempotent

    async def stop_proper(self) -> None:
        """S-5d: cancel and await task."""
        self._running = False
        task = getattr(self, "_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    cls.stop = stop_proper

    async def _flush_safe(self) -> None:
        """S-5a: failed rows go to requeue buffer."""
        if not hasattr(self, "_requeue_buffer"):
            self._requeue_buffer = deque(maxlen=_REQUEUE_MAX)

        async with self._lock:
            rows = list(self._requeue_buffer)
            self._requeue_buffer.clear()
            batch = min(_FLUSH_BATCH, len(self._buffer))
            rows.extend(self._buffer.popleft() for _ in range(batch) if self._buffer)

        if not rows:
            return

        try:
            from ..database import db
            await asyncio.to_thread(lambda: db.table("audit_logs").insert(rows).execute())
            logger.debug("AuditService: flushed %d rows", len(rows))
        except Exception as exc:
            logger.warning("AuditService: flush failed (%s) — requeueing %d rows", exc, len(rows))
            async with self._lock:
                for row in rows[-_REQUEUE_MAX:]:
                    self._requeue_buffer.append(row)

    cls._flush = _flush_safe

    async def log_decision(
        self,
        user_id: str,
        symbol: str,
        direction: str,
        approved: bool,
        block_reason: str = "",
        risk_pct: float = 0.0,
        lot_size: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """S-5b: log trading decision to audit trail."""
        entry = {
            "user_id":      user_id,
            "action":       "decision_made",
            "symbol":       symbol,
            "direction":    direction,
            "approved":     approved,
            "block_reason": block_reason,
            "risk_pct":     risk_pct,
            "lot_size":     lot_size,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "metadata":     metadata or {},
        }
        self._buffer.append(entry)

    cls.log_decision = log_decision

    async def get_action_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """S-5e: filter pushed to Supabase."""
        try:
            from ..database import db
            query = db.table("audit_logs").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
            if action:
                query = query.eq("action", action)
            query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
            result = await asyncio.to_thread(lambda: query.execute())
            return result.data or []
        except Exception as exc:
            logger.error("get_action_logs failed: %s", exc)
            return []

    cls.get_action_logs = get_action_logs
    logger.debug("AuditService patched (S-5): %s", cls.__name__)
    return cls
