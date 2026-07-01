"""
backend/execution/semi_auto.py
Galaxy Vast AI - Semi-Automatic Trading Handler
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class PendingSignal:
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    lots: float
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    approved: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at


class SemiAutoHandler:
    """Human-in-the-loop signal approval handler."""

    def __init__(self, timeout: float = 300.0) -> None:
        self._pending: Dict[str, PendingSignal] = {}
        self._timeout = timeout
        self._lock = asyncio.Lock()

    async def submit(self, signal_id: str, symbol: str, direction: str,
                     entry_price: float, lots: float,
                     metadata: Optional[Dict[str, Any]] = None) -> PendingSignal:
        async with self._lock:
            ps = PendingSignal(
                signal_id=signal_id,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                lots=lots,
                expires_at=time.time() + self._timeout,
                metadata=metadata or {},
            )
            self._pending[signal_id] = ps
            _LOG.info("Signal submitted for approval: %s %s %s @ %.5f",
                      signal_id, symbol, direction, entry_price)
            return ps

    async def approve(self, signal_id: str) -> bool:
        async with self._lock:
            ps = self._pending.get(signal_id)
            if ps is None:
                return False
            if ps.is_expired():
                del self._pending[signal_id]
                return False
            ps.approved = True
            _LOG.info("Signal approved: %s", signal_id)
            return True

    async def reject(self, signal_id: str) -> bool:
        async with self._lock:
            ps = self._pending.get(signal_id)
            if ps is None:
                return False
            ps.approved = False
            del self._pending[signal_id]
            _LOG.info("Signal rejected: %s", signal_id)
            return True

    async def get_pending(self) -> List[PendingSignal]:
        async with self._lock:
            self._purge_expired()
            return list(self._pending.values())

    def _purge_expired(self) -> None:
        expired = [k for k, v in self._pending.items() if v.is_expired()]
        for k in expired:
            del self._pending[k]
            _LOG.info("Signal expired: %s", k)

    async def wait_for_decision(self, signal_id: str, poll_interval: float = 1.0) -> Optional[bool]:
        while True:
            async with self._lock:
                ps = self._pending.get(signal_id)
                if ps is None:
                    return None
                if ps.is_expired():
                    del self._pending[signal_id]
                    return None
                if ps.approved is not None:
                    approved = ps.approved
                    if signal_id in self._pending:
                        del self._pending[signal_id]
                    return approved
            await asyncio.sleep(poll_interval)


_handler: Optional[SemiAutoHandler] = None


def get_semi_auto_handler() -> SemiAutoHandler:
    global _handler
    if _handler is None:
        _handler = SemiAutoHandler()
    return _handler
