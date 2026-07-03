"""
backend/execution/semi_auto.py
Galaxy Vast AI -- Semi-Auto Trading Mode

Allows the operator to approve/reject signals before execution.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    PENDING  = auto()
    APPROVED = auto()
    REJECTED = auto()
    EXPIRED  = auto()


@dataclass
class PendingSignal:
    signal_id:  str
    symbol:     str
    direction:  str
    volume:     float
    sl:         float
    tp:         float
    status:     ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_in: float = 300.0   # seconds


class SemiAutoManager:
    """Manages pending signals awaiting operator approval."""

    def __init__(self, timeout: float = 300.0) -> None:
        self._pending: dict[str, PendingSignal] = {}
        self._timeout = timeout

    def enqueue(self, signal_id: str, symbol: str, direction: str,
                volume: float, sl: float = 0.0, tp: float = 0.0) -> PendingSignal:
        sig = PendingSignal(
            signal_id=signal_id, symbol=symbol, direction=direction,
            volume=volume, sl=sl, tp=tp, expires_in=self._timeout,
        )
        self._pending[signal_id] = sig
        logger.info("Enqueued signal %s for approval (%s %s)", signal_id, direction, symbol)
        return sig

    def approve(self, signal_id: str) -> Optional[PendingSignal]:
        sig = self._pending.get(signal_id)
        if sig and sig.status == ApprovalStatus.PENDING:
            sig.status = ApprovalStatus.APPROVED
            logger.info("Signal %s approved", signal_id)
            return sig
        return None

    def reject(self, signal_id: str) -> Optional[PendingSignal]:
        sig = self._pending.get(signal_id)
        if sig and sig.status == ApprovalStatus.PENDING:
            sig.status = ApprovalStatus.REJECTED
            logger.info("Signal %s rejected", signal_id)
            return sig
        return None

    def list_pending(self) -> list[dict]:
        return [
            {
                "signal_id": s.signal_id,
                "symbol":    s.symbol,
                "direction": s.direction,
                "volume":    s.volume,
                "status":    s.status.name,
                "created_at": s.created_at,
            }
            for s in self._pending.values()
            if s.status == ApprovalStatus.PENDING
        ]


semi_auto_manager = SemiAutoManager()
