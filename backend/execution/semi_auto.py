"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Automatic Trading Handler

Allows human confirmation before order execution.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class ConfirmationStatus(str, Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    EXPIRED   = "EXPIRED"


@dataclass
class PendingOrder:
    order_id: str
    signal: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    approved_by: Optional[str] = None


class SemiAutoEngine:
    """Human-in-the-loop order confirmation engine."""

    def __init__(self, timeout_s: float = 300.0) -> None:
        self._timeout   = timeout_s
        self._pending: Dict[str, PendingOrder] = {}
        self._callbacks: List[Callable] = []

    def add_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    async def submit(self, order_id: str, signal: Dict[str, Any]) -> PendingOrder:
        order = PendingOrder(
            order_id=order_id,
            signal=signal,
            expires_at=time.time() + self._timeout,
        )
        self._pending[order_id] = order
        log.info("semi_auto_pending order_id=%s", order_id)
        for cb in self._callbacks:
            try:
                await cb("pending", order)
            except Exception as exc:
                log.error("callback_error: %s", exc)
        return order

    async def approve(self, order_id: str, user: str) -> bool:
        order = self._pending.get(order_id)
        if not order or order.status != ConfirmationStatus.PENDING:
            return False
        if time.time() > order.expires_at:
            order.status = ConfirmationStatus.EXPIRED
            return False
        order.status = ConfirmationStatus.APPROVED
        order.approved_by = user
        log.info("semi_auto_approved order_id=%s by=%s", order_id, user)
        return True

    async def reject(self, order_id: str, user: str) -> bool:
        order = self._pending.get(order_id)
        if not order or order.status != ConfirmationStatus.PENDING:
            return False
        order.status = ConfirmationStatus.REJECTED
        order.approved_by = user
        log.info("semi_auto_rejected order_id=%s by=%s", order_id, user)
        return True

    def pending_orders(self) -> List[PendingOrder]:
        return [o for o in self._pending.values() if o.status == ConfirmationStatus.PENDING]


semi_auto_engine = SemiAutoEngine()
