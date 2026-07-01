"""
backend/execution/semi_auto.py
Galaxy Vast AI - Semi-Auto Execution (repaired)
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class PendingOrder:
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    direction: str = "BUY"
    lots: float = 0.01
    signal_confidence: float = 0.0
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

class SemiAutoEngine:
    def __init__(self, approval_timeout_s: float = 300.0) -> None:
        self._timeout = approval_timeout_s
        self._queue: dict[str, PendingOrder] = {}

    def submit(self, order: PendingOrder) -> str:
        self._queue[order.order_id] = order
        return order.order_id

    def approve(self, order_id: str) -> bool:
        order = self._queue.get(order_id)
        if not order or order.status != ApprovalStatus.PENDING:
            return False
        order.status = ApprovalStatus.APPROVED
        return True

    def reject(self, order_id: str, reason: str = "") -> bool:
        order = self._queue.get(order_id)
        if not order or order.status != ApprovalStatus.PENDING:
            return False
        order.status = ApprovalStatus.REJECTED
        return True

    def list_pending(self) -> list[PendingOrder]:
        return [o for o in self._queue.values() if o.status == ApprovalStatus.PENDING]

    def get_order(self, order_id: str) -> PendingOrder | None:
        return self._queue.get(order_id)

__all__ = ["SemiAutoEngine", "PendingOrder", "ApprovalStatus"]
