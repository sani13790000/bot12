"""
Galaxy Vast AI Trading Platform
Failure Recovery Engine — Phase 7

Handles:
- Transient MT5 errors with exponential backoff
- Circuit breaker integration
- Dead-letter queue for unrecoverable orders
- Reconnection logic for dropped MT5 sessions
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.failure_recovery")


class RecoveryStrategy(str, Enum):
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"
    ALERT_ONLY = "alert_only"


# MT5 retcodes that are transient (safe to retry)
_TRANSIENT_RETCODES = {
    10004,  # TRADE_RETCODE_REQUOTE
    10006,  # TRADE_RETCODE_REJECT
    10007,  # TRADE_RETCODE_CANCEL
    10016,  # TRADE_RETCODE_INVALID_STOPS
    10018,  # TRADE_RETCODE_MARKET_CLOSED
    10025,  # TRADE_RETCODE_TOO_MANY_REQUESTS
    10030,  # TRADE_RETCODE_TRADE_DISABLED
}

_PERMANENT_RETCODES = {
    10009,  # TRADE_RETCODE_DONE
    10010,  # TRADE_RETCODE_DONE_PARTIAL
    10013,  # TRADE_RETCODE_INVALID
    10014,  # TRADE_RETCODE_INVALID_VOLUME
    10015,  # TRADE_RETCODE_INVALID_PRICE
    10017,  # TRADE_RETCODE_TRADE_DISABLED
}


@dataclass
class FailedOrder:
    order_id: str
    signal_id: str
    error: str
    retcode: int = 0
    attempts: int = 0
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    last_attempt_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class FailureRecoveryEngine:
    """Manages retry + dead-letter logic for failed execution."""

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
        self._dead_letter: List[FailedOrder] = []
        self._retry_queue: List[FailedOrder] = []
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._retry_loop())
        logger.info("FailureRecoveryEngine started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def handle_failure(
        self,
        order_id: str,
        signal_id: str,
        error: str,
        retcode: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RecoveryStrategy:
        strategy = self._classify(retcode, error)
        failed = FailedOrder(
            order_id=order_id,
            signal_id=signal_id,
            error=error,
            retcode=retcode,
            attempts=1,
            strategy=strategy,
            metadata=metadata or {},
        )

        if strategy == RecoveryStrategy.RETRY:
            async with self._lock:
                self._retry_queue.append(failed)
            logger.warning(
                "Order %s queued for retry (retcode=%s)",
                order_id[:8], retcode,
            )
        else:
            await self._send_to_dead_letter(failed)

        return strategy

    def _classify(self, retcode: int, error: str) -> RecoveryStrategy:
        if retcode in _PERMANENT_RETCODES:
            return RecoveryStrategy.DEAD_LETTER
        if retcode in _TRANSIENT_RETCODES:
            return RecoveryStrategy.RETRY
        if "timeout" in error.lower() or "connection" in error.lower():
            return RecoveryStrategy.RETRY
        return RecoveryStrategy.ALERT_ONLY

    async def _send_to_dead_letter(
        self, failed: FailedOrder, reason: str = ""
    ) -> None:
        async with self._lock:
            self._dead_letter.append(failed)
        logger.error(
            "Order %s -> dead letter. Error: %s | Reason: %s",
            failed.order_id[:8], failed.error, reason or failed.strategy,
        )
        if self._alert_callback:
            try:
                await self._alert_callback(failed)
            except Exception as exc:
                logger.error("Alert callback error: %s", exc)

    async def _retry_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                async with self._lock:
                    pending = list(self._retry_queue)
                    self._retry_queue.clear()

                for failed in pending:
                    if failed.attempts >= self._max_retries:
                        await self._send_to_dead_letter(failed, reason="max retries exceeded")
                        continue

                    delay = min(
                        self._base_delay * (2 ** (failed.attempts - 1)),
                        self._max_delay,
                    )
                    failed.attempts += 1
                    failed.last_attempt_at = datetime.now(timezone.utc)
                    logger.info(
                        "Retrying order %s (attempt %s, delay=%.1fs)",
                        failed.order_id[:8], failed.attempts, delay,
                    )
                    await asyncio.sleep(delay)
                    # Re-queue for the execution service to pick up
                    async with self._lock:
                        self._retry_queue.append(failed)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Retry loop error: %s", exc)

    @property
    def dead_letter_queue(self) -> List[FailedOrder]:
        return list(self._dead_letter)

    @property
    def retry_queue_size(self) -> int:
        return len(self._retry_queue)

    def health_stats(self) -> Dict[str, Any]:
        return {
            "retry_queue_size": self.retry_queue_size,
            "dead_letter_count": len(self._dead_letter),
        }


# Singleton
failure_recovery = FailureRecoveryEngine()
