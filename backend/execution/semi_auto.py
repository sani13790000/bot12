"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Automatic Trading Handler

Handles human-in-the-loop signal approval via Telegram.
Pending signals expire after a configurable timeout.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
__all__ = ["SemiAutoHandler", "PendingSignal", "get_semi_auto_handler"]


@dataclass
class PendingSignal:
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    approved: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def is_pending(self) -> bool:
        return self.approved is None and not self.is_expired()


class SemiAutoHandler:
    """Manages pending signals awaiting human approval."""

    def __init__(self, timeout_seconds: int = 300) -> None:
        self._timeout = timeout_seconds
        self._pending: Dict[str, PendingSignal] = {}
        self._callbacks: List[Callable] = []
        self._lock = asyncio.Lock()

    async def add_signal(self, signal: PendingSignal) -> str:
        signal.expires_at = time.time() + self._timeout
        async with self._lock:
            self._pending[signal.signal_id] = signal
        logger.info("Semi-auto signal pending: %s %s %s", signal.signal_id, signal.symbol, signal.direction)
        for cb in self._callbacks:
            try:
                await cb("pending", signal)
            except Exception:
                pass
        return signal.signal_id

    async def approve(self, signal_id: str) -> bool:
        async with self._lock:
            sig = self._pending.get(signal_id)
            if not sig or sig.is_expired():
                return False
            sig.approved = True
        logger.info("Signal approved: %s", signal_id)
        for cb in self._callbacks:
            try:
                await cb("approved", sig)
            except Exception:
                pass
        return True

    async def reject(self, signal_id: str) -> bool:
        async with self._lock:
            sig = self._pending.get(signal_id)
            if not sig:
                return False
            sig.approved = False
        logger.info("Signal rejected: %s", signal_id)
        return True

    def get_pending(self) -> List[PendingSignal]:
        now = time.time()
        return [s for s in self._pending.values() if s.approved is None and not s.is_expired()]

    def add_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired = [k for k, v in self._pending.items() if v.is_expired()]
            for k in expired:
                del self._pending[k]
        return len(expired)


_handler: Optional[SemiAutoHandler] = None

def get_semi_auto_handler() -> SemiAutoHandler:
    global _handler
    if _handler is None:
        _handler = SemiAutoHandler()
    return _handler
