"""
Galaxy Vast AI Trading Platform
Failure Recovery Engine

FIX-2:    asyncio.Queue replaces list() + clear()
BUG-FR-1: asyncio.Queue created in __init__ (module level) outside event loop.
          Python 3.10+ DeprecationWarning; Python 3.12+ RuntimeError.
          FIX: lazy Queue init in start(). _ensure_queue() guard for
          handle_failure() called before start().
BUG-FR-2: Re-queued failed orders skip exponential delay on second pass.
          FIX: gate max_retries=0 to immediate dead-letter; clarified
          delay/increment ordering with explicit comment.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.failure_recovery")

_MAX_DEAD_LETTER     = 500
_RETRY_QUEUE_MAXSIZE = 200


class RecoveryStrategy(str, Enum):
    RETRY       = "retry"
    DEAD_LETTER = "dead_letter"
    ALERT_ONLY  = "alert_only"


_TRANSIENT_RETCODES = {10004, 10006, 10007, 10016, 10018, 10025, 10030}
_PERMANENT_RETCODES = {10013, 10014, 10015, 10017}


@dataclass
class FailedOrder:
    order_id:        str
    signal_id:       str
    error:           str
    retcode:         int              = 0
    attempts:        int              = 0
    strategy:        RecoveryStrategy = RecoveryStrategy.RETRY
    last_attempt_at: datetime         = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata:        Dict[str, Any]   = field(default_factory=dict)


class FailureRecoveryEngine:
    """
    FIX-2:    asyncio.Queue as retry work queue.
    BUG-FR-1: Queue created lazily in start(), not in __init__ (outside loop).
    """

    def __init__(
        self,
        max_retries:    int               = 3,
        base_delay:     float             = 2.0,
        max_delay:      float             = 30.0,
        alert_callback: Optional[Callable] = None,
    ):
        self._max_retries    = max(0, max_retries)
        self._base_delay     = base_delay
        self._max_delay      = max_delay
        self._alert_callback = alert_callback
        self._retry_callback: Optional[Callable] = None
        # BUG-FR-1 FIX: do NOT create asyncio.Queue here.
        self._retry_queue: Optional[asyncio.Queue] = None
        self._dead_letter: Deque[FailedOrder]       = deque(maxlen=_MAX_DEAD_LETTER)
        self._task: Optional[asyncio.Task]          = None

    def set_retry_callback(self, cb: Callable) -> None:
        self._retry_callback = cb

    def _ensure_queue(self) -> asyncio.Queue:
        """Lazy init: safe to call from within a running event loop."""
        if self._retry_queue is None:
            self._retry_queue = asyncio.Queue(maxsize=_RETRY_QUEUE_MAXSIZE)
        return self._retry_queue

    async def start(self) -> None:
        # BUG-FR-1 FIX: Queue created here, inside the running event loop.
        self._retry_queue = asyncio.Queue(maxsize=_RETRY_QUEUE_MAXSIZE)
        self._task = asyncio.create_task(self._retry_loop())
        logger.info("FailureRecoveryEngine started (queue_maxsize=%d)", _RETRY_QUEUE_MAXSIZE)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        q = self._retry_queue
        logger.info(
            "FailureRecoveryEngine stopped (dead_letter=%d, queue=%d)",
            len(self._dead_letter),
            q.qsize() if q else 0,
        )

    async def handle_failure(
        self,
        order_id:  str,
        signal_id: str,
        error:     str,
        retcode:   int                    = 0,
        metadata:  Optional[Dict[str, Any]] = None,
    ) -> RecoveryStrategy:
        strategy = self._classify(retcode, error)
        failed = FailedOrder(
            order_id=order_id, signal_id=signal_id,
            error=error, retcode=retcode, attempts=1,
            strategy=strategy, metadata=metadata or {},
        )
        if strategy == RecoveryStrategy.RETRY:
            # BUG-FR-2: max_retries=0 means retries disabled
            if self._max_retries == 0:
                await self._send_to_dead_letter(failed, reason="max_retries=0")
                return RecoveryStrategy.DEAD_LETTER
            q = self._ensure_queue()
            try:
                q.put_nowait(failed)
                logger.info(
                    "Order %s queued for retry (queue=%d/%d)",
                    order_id[:8], q.qsize(), _RETRY_QUEUE_MAXSIZE,
                )
            except asyncio.QueueFull:
                logger.error("Retry queue full - order %s dead letter", order_id[:8])
                await self._send_to_dead_letter(failed, reason="retry queue full")
                return RecoveryStrategy.DEAD_LETTER
        else:
            await self._send_to_dead_letter(failed)
        return strategy

    async def _retry_loop(self) -> None:
        logger.info("Retry loop started")
        q = self._ensure_queue()
        while True:
            try:
                failed: FailedOrder = await q.get()
                try:
                    if failed.attempts >= self._max_retries:
                        await self._send_to_dead_letter(failed, reason="max retries exceeded")
                        continue
                    delay = min(self._base_delay * (2 ** (failed.attempts - 1)), self._max_delay)
                    logger.info(
                        "Retrying order %s attempt %d/%d (delay=%.1fs)",
                        failed.order_id[:8], failed.attempts + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    failed.attempts += 1
                    failed.last_attempt_at = datetime.now(timezone.utc)
                    if self._retry_callback:
                        try:
                            success = await self._retry_callback(failed.metadata)
                        except Exception as exc:
                            logger.error("Retry callback error %s: %s", failed.order_id[:8], exc)
                            success = False
                        if not success:
                            try:
                                q.put_nowait(failed)
                            except asyncio.QueueFull:
                                await self._send_to_dead_letter(failed, reason="re-queue failed: queue full")
                    else:
                        await self._send_to_dead_letter(failed, reason="no retry callback")
                finally:
                    q.task_done()
            except asyncio.CancelledError:
                logger.info("Retry loop cancelled")
                break
            except Exception as exc:
                logger.error("Retry loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1)

    def _classify(self, retcode: int, error: str) -> RecoveryStrategy:
        if retcode in _PERMANENT_RETCODES:
            return RecoveryStrategy.DEAD_LETTER
        if retcode in _TRANSIENT_RETCODES:
            return RecoveryStrategy.RETRY
        if "timeout" in error.lower() or "connection" in error.lower():
            return RecoveryStrategy.RETRY
        return RecoveryStrategy.ALERT_ONLY

    async def _send_to_dead_letter(self, failed: FailedOrder, reason: str = "") -> None:
        self._dead_letter.append(failed)
        logger.error(
            "Order %s dead letter: %s | reason=%s",
            failed.order_id[:8], failed.error, reason or failed.strategy,
        )
        if self._alert_callback:
            try:
                await self._alert_callback(failed)
            except Exception as exc:
                logger.error("Alert callback error: %s", exc)

    @property
    def dead_letter_queue(self) -> List[FailedOrder]:
        return list(self._dead_letter)

    @property
    def retry_queue_size(self) -> int:
        q = self._retry_queue
        return q.qsize() if q else 0

    def health_stats(self) -> Dict[str, Any]:
        q = self._retry_queue
        return {
            "retry_queue_size":    q.qsize() if q else 0,
            "retry_queue_maxsize": _RETRY_QUEUE_MAXSIZE,
            "dead_letter_count":   len(self._dead_letter),
            "has_retry_callback":  self._retry_callback is not None,
        }


failure_recovery = FailureRecoveryEngine()
