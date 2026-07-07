"""
Galaxy Vast AI Trading Platform
Failure Recovery Engine
FIX: Converted all logger.xxz(\"msg %s\", arg) to logger.xxx(f\"msg {arg}\")
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, Optional

from ..core.logger import get_logger

logger = get_logger("execution.failure_recovery")

_RETRY_QUEUE_MAXSIZE = 200


class RecoveryStrategy(str, Enum):
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"
    ALERT_ONLY = "alert_only"


@dataclass
class FailedOrder:
    order_id: str
    signal_id: str = ""
    error: str = ""
    retcode: int = 0
    attempts: int = 0
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    last_attempt_at: Optional[datetime] = None
    metadata: Dict[any, Any] = field(default_factory=dict)


class FailureRecoveryEngine:
    """
    Retries failed orders with exponential backoff.
    Orders that exhaust retries are sent to a bounded dead-letter queue.
    """

    _MAX_DEAD_LETTER = 500

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        alert_callback: Optional[Callable] = None,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._alert_callback = alert_callback
        self._retry_queue: Optional[asyncio.Queue] = None
        self._task: Optional[asyncio.Task] = None
        self._stopped: bool = False
        self._retry_callback: Optional[Callable] = None
        self._dead_letter: Deque[FailedOrder] = deque(maxlen=self._MAX_DEAD_LETTER)

    def set_retry_callback(self, cb: Callable) -> None:
        self._retry_callback = cb

    def _ensure_queue(self) -> asyncio.Queue:
        if self._retry_queue is None:
            self._retry_queue = asyncio.Queue(maxsize=_RETRY_QUEUE_MAXSIZE)
        return self._retry_queue

    async def start(self) -> None:
        self._stopped = False
        self._ensure_queue()
        logger.info(f"FailureRecoveryEngine started (queue_maxsize={_RETRY_QUEUE_MAXSIZE})")
        self._task = asyncio.create_task(self._retry_loop(), name="fre:retry_loop")
        self._task.add_done_callback(
            lambda t: (
                logger.debug(f"FRE task done: {t.exception()}")
                if not t.cancelled() and t.exception()
                else None
            )
        )

    async def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        q = self._retry_queue
        logger.info(
            f"FailureRecoveryEngine stopped (dead_letter={len(self._dead_letter)}, queue={q.qsize() if q else 0})"
        )

    async def handle_failure(
        self,
        order_id: str,
        signal_id: str,
        error: str,
        retcode: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RecoveryStrategy:
        failed = FailedOrder(
            order_id=order_id,
            signal_id=signal_id,
            error=error,
            retcode=retcode,
            metadata=metadata or {},
        )
        q = self._ensure_queue()
        if self._max_retries > 0:
            try:
                q.put_nowait(failed)
                logger.info(
                    f"Order {order_id[:8]} queued for retry (queue={q.qsize()}/{_RETRY_QUEUE_MAXSIZE})"
                )
            except asyncio.QueueFull:
                logger.error(f"Retry queue full - order {order_id[:8]} dead letter")
                await self._send_to_dead_letter(failed, reason="retry queue full")
                return RecoveryStrategy.DEAD_LETTER
        else:
            await self._send_to_dead_letter(failed, reason="max_retries=0")
            return RecoveryStrategy.DEAD_LETTER
        return RecoveryStrategy.RETRY

    async def _retry_loop(self) -> None:
        logger.info("Retry loop started")
        q = self._ensure_queue()
        while not self._stopped:
            try:
                failed = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                if failed.attempts >= self._max_retries:
                    await self._send_to_dead_letter(failed, reason="max retries exceeded")
                    continue
                delay = min(self._base_delay * (2 ** (failed.attempts - 1)), self._max_delay)
                logger.info(
                    f"Retrying order {failed.order_id[:8]} attempt {failed.attempts + 1}/{self._max_retries} (delay={delay:.1f}s)"
                )
                await asyncio.sleep(delay)
                failed.attempts += 1
                failed.last_attempt_at = datetime.now(timezone.utc)
                if self._retry_callback:
                    try:
                        success = await self._retry_callback(failed.metadata)
                    except Exception as exc:
                        logger.error(f"Retry callback error {failed.order_id[:8]}: {exc}")
                        success = False
                    if not success:
                        if failed.attempts < self._max_retries:
                            try:
                                q.put_nowait(failed)
                            except asyncio.QueueFull:
                                await self._send_to_dead_letter(
                                    failed, reason="re-queue failed: queue full"
                                )
                        else:
                            await self._send_to_dead_letter(failed, reason="no retry callback")
                else:
                    await self._send_to_dead_letter(failed, reason="no retry callback")
            finally:
                q.task_done()
        logger.info("Retry loop cancelled")

    async def _send_to_dead_letter(self, failed: FailedOrder, reason: str = "") -> None:
        self._dead_letter.append(failed)
        logger.error(
            f"Order {failed.order_id[:8]} dead letter: {failed.error} | reason={reason or failed.strategy}"
        )
        if self._alert_callback:
            try:
                await self._alert_callback(failed)
            except Exception as exc:
                logger.error(f"Alert callback error: {exc}")

    @property
    def dead_letter_count(self) -> int:
        return len(self._dead_letter)

    @property
    def queue_size(self) -> int:
        q = self._retry_queue
        return q.qsize() if q else 0
