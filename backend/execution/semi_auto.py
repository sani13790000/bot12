"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Auto Trading Mode

Allows the operator to manually approve or reject signals before execution.
Signals queue in Redis/memory; operator responds via Telegram or API.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    EXPIRED   = "expired"
    AUTO      = "auto"


@dataclass
class PendingSignal:
    signal_id:   str
    symbol:      str
    direction:   str
    confidence:  float
    lot_size:    float
    entry_price: float
    stop_loss:   float
    take_profit: float
    created_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status:      DecisionStatus = DecisionStatus.PENDING
    decided_by:  Optional[str] = None
    decided_at:  Optional[datetime] = None
    metadata:    Dict = field(default_factory=dict)


class SemiAutoEngine:
    """Queue-based semi-auto engine: signals wait for human approval."""

    def __init__(self, timeout_seconds: float = 300.0) -> None:
        self._timeout = timeout_seconds
        self._queue: Dict[str, PendingSignal] = {}
        self._callbacks: List[Callable] = []
        self._log = logging.getLogger(self.__class__.__name__)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the expiry watcher loop."""
        self._task = asyncio.create_task(self._expire_loop())
        self._log.info("SemiAutoEngine started (timeout=%.0fs)", self._timeout)

    async def stop(self) -> None:
        """Stop the expiry watcher."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def queue_signal(self, signal: PendingSignal) -> str:
        """Add a signal to the approval queue."""
        self._queue[signal.signal_id] = signal
        self._log.info("Queued signal %s (%s %s conf=%.2f)",
                       signal.signal_id, signal.direction, signal.symbol, signal.confidence)
        await self._notify(signal)
        return signal.signal_id

    async def approve(self, signal_id: str, operator: str = "operator") -> Optional[PendingSignal]:
        """Approve a queued signal."""
        sig = self._queue.get(signal_id)
        if not sig or sig.status != DecisionStatus.PENDING:
            return None
        sig.status = DecisionStatus.APPROVED
        sig.decided_by = operator
        sig.decided_at = datetime.now(timezone.utc)
        self._log.info("Signal %s APPROVED by %s", signal_id, operator)
        return sig

    async def reject(self, signal_id: str, operator: str = "operator") -> Optional[PendingSignal]:
        """Reject a queued signal."""
        sig = self._queue.get(signal_id)
        if not sig or sig.status != DecisionStatus.PENDING:
            return None
        sig.status = DecisionStatus.REJECTED
        sig.decided_by = operator
        sig.decided_at = datetime.now(timezone.utc)
        self._log.info("Signal %s REJECTED by %s", signal_id, operator)
        return sig

    def list_pending(self) -> List[PendingSignal]:
        """Return all pending signals."""
        return [s for s in self._queue.values() if s.status == DecisionStatus.PENDING]

    def add_callback(self, fn: Callable) -> None:
        """Register callback for new queued signals."""
        self._callbacks.append(fn)

    async def _notify(self, signal: PendingSignal) -> None:
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(signal)
                else:
                    cb(signal)
            except Exception as exc:
                self._log.error("Callback error: %s", exc)

    async def _expire_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            now = datetime.now(timezone.utc)
            for sig in list(self._queue.values()):
                if sig.status != DecisionStatus.PENDING:
                    continue
                age = (now - sig.created_at).total_seconds()
                if age > self._timeout:
                    sig.status = DecisionStatus.EXPIRED
                    self._log.warning("Signal %s expired after %.0fs", sig.signal_id, age)

    @property
    def queue_size(self) -> int:
        return len(self._queue)


_engine: Optional[SemiAutoEngine] = None


def get_semi_auto_engine() -> SemiAutoEngine:
    global _engine
    if _engine is None:
        _engine = SemiAutoEngine()
    return _engine
