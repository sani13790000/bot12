"""backend/execution/order_state_machine.py
PHASE 3 — Production Order State Machine

P3-OSM-1: ALLOWED_TRANSITIONS guard — prevents illegal state bypasses
P3-OSM-2: Full lifecycle: PENDING->SUBMITTED->FILLED->CLOSING->CLOSED
P3-OSM-3: Every transition logged with timestamp + operator
P3-OSM-4: Idempotent transitions — safe to replay

NOTE: Restored from double-base64 encoded source with binary corruption.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class OrderState(str, Enum):
    PENDING    = "PENDING"
    SUBMITTED  = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED     = "FILLED"
    CLOSING    = "CLOSING"
    CLOSED     = "CLOSED"
    CANCELLED  = "CANCELLED"
    REJECTED   = "REJECTED"
    FAILED     = "FAILED"
    EXPIRED    = "EXPIRED"


ALLOWED_TRANSITIONS: Dict[OrderState, Set[OrderState]] = {
    OrderState.PENDING:           {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.SUBMITTED:         {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED:  {OrderState.FILLED, OrderState.CANCELLED},
    OrderState.FILLED:            {OrderState.CLOSING, OrderState.CLOSED},
    OrderState.CLOSING:           {OrderState.CLOSED, OrderState.FAILED},
    OrderState.CLOSED:            set(),
    OrderState.CANCELLED:         set(),
    OrderState.REJECTED:          set(),
    OrderState.FAILED:            {OrderState.PENDING},  # allow retry
    OrderState.EXPIRED:           set(),
}


@dataclass
class StateTransition:
    from_state: OrderState
    to_state: OrderState
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    operator: str = "system"
    reason: str = ""


@dataclass
class OrderStateMachine:
    order_id: str
    state: OrderState = OrderState.PENDING
    transitions: List[StateTransition] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def can_transition(self, to_state: OrderState) -> bool:
        """P3-OSM-1: Check if transition is allowed."""
        return to_state in ALLOWED_TRANSITIONS.get(self.state, set())

    def transition(self, to_state: OrderState, operator: str = "system", reason: str = "") -> bool:
        """Execute a state transition."""
        if not self.can_transition(to_state):
            logger.warning(
                "Illegal transition %s->%s for order %s",
                self.state, to_state, self.order_id
            )
            return False
        tr = StateTransition(
            from_state=self.state,
            to_state=to_state,
            operator=operator,
            reason=reason,
        )
        self.transitions.append(tr)
        self.state = to_state
        logger.info(
            "Order %s: %s->%s (by %s)",
            self.order_id, tr.from_state, to_state, operator
        )
        return True

    @property
    def is_terminal(self) -> bool:
        return self.state in {OrderState.CLOSED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED}

    @property
    def is_active(self) -> bool:
        return self.state in {OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CLOSING}

    def history(self) -> List[Dict]:
        return [
            {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "ts": t.timestamp.isoformat(),
                "operator": t.operator,
                "reason": t.reason,
            }
            for t in self.transitions
        ]


class OrderStateManager:
    """Manages state machines for all orders."""

    def __init__(self) -> None:
        self._orders: Dict[str, OrderStateMachine] = {}
        self._log = logging.getLogger(self.__class__.__name__)

    def create(self, order_id: str, **metadata) -> OrderStateMachine:
        osm = OrderStateMachine(order_id=order_id, metadata=metadata)
        self._orders[order_id] = osm
        return osm

    def get(self, order_id: str) -> Optional[OrderStateMachine]:
        return self._orders.get(order_id)

    def transition(self, order_id: str, to_state: OrderState, operator: str = "system", reason: str = "") -> bool:
        osm = self._orders.get(order_id)
        if not osm:
            self._log.error("Order not found: %s", order_id)
            return False
        return osm.transition(to_state, operator=operator, reason=reason)

    def get_order_journal(self) -> List[Dict]:
        return [
            {"order_id": oid, "state": osm.state.value, "transitions": osm.history()}
            for oid, osm in self._orders.items()
        ]

    def active_orders(self) -> List[OrderStateMachine]:
        return [osm for osm in self._orders.values() if osm.is_active]


_manager: Optional[OrderStateManager] = None


def get_order_state_manager() -> OrderStateManager:
    global _manager
    if _manager is None:
        _manager = OrderStateManager()
    return _manager
