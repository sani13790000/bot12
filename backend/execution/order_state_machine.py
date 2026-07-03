"""
backend/execution/order_state_machine.py
Galaxy Vast AI — Order State Machine

چرخه عمر سفارش:
  PENDING → FILLED → CLOSED
  PENDING → CANCELLED
  PENDING → REJECTED
  FILLED  → PARTIAL_CLOSE → CLOSED
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class OrderState(Enum):
    PENDING       = auto()
    FILLED        = auto()
    PARTIAL_CLOSE = auto()
    CANCELLED     = auto()
    REJECTED      = auto()
    CLOSED        = auto()


# انتقال‌های مجاز: از هر state به چه state‌هایی می‌توان رفت
_VALID_TRANSITIONS: Dict[OrderState, List[OrderState]] = {
    OrderState.PENDING:       [OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED],
    OrderState.FILLED:        [OrderState.PARTIAL_CLOSE, OrderState.CLOSED],
    OrderState.PARTIAL_CLOSE: [OrderState.CLOSED],
    OrderState.CANCELLED:     [],
    OrderState.REJECTED:      [],
    OrderState.CLOSED:        [],
}


class OrderStateMachine:
    """
    مدیریت state هر سفارش با validation انتقال.

    استفاده:
        osm = OrderStateMachine()
        osm.register(ticket=12345)
        osm.transition(12345, OrderState.FILLED)
        state = osm.get_state(12345)
    """

    def __init__(self) -> None:
        self._states: Dict[int, Tuple[OrderState, datetime]] = {}

    def register(self, ticket: int,
                 initial_state: OrderState = OrderState.PENDING) -> None:
        """یک سفارش جدید در PENDING ثبت کن."""
        if ticket in self._states:
            return
        self._states[ticket] = (initial_state, datetime.now(timezone.utc))

    def transition(self, ticket: int, new_state: OrderState) -> bool:
        """
        انتقال state یک سفارش.
        برمی‌گرداند True اگر موفق، False اگر نامعتبر.
        """
        if ticket not in self._states:
            self.register(ticket)
        current_state, _ = self._states[ticket]
        if new_state == current_state:
            return True
        allowed = _VALID_TRANSITIONS.get(current_state, [])
        if new_state not in allowed:
            logger.warning(
                "[OSM] invalid transition ticket=%d %s → %s (allowed: %s)",
                ticket, current_state.name, new_state.name,
                [s.name for s in allowed],
            )
            return False
        self._states[ticket] = (new_state, datetime.now(timezone.utc))
        logger.info("[OSM] ticket=%d %s → %s",
                    ticket, current_state.name, new_state.name)
        return True

    def get_state(self, ticket: int) -> Optional[OrderState]:
        entry = self._states.get(ticket)
        return entry[0] if entry else None

    def get_timestamp(self, ticket: int) -> Optional[datetime]:
        entry = self._states.get(ticket)
        return entry[1] if entry else None

    def get_open_tickets(self) -> List[int]:
        return [
            ticket for ticket, (state, _) in self._states.items()
            if state in (OrderState.FILLED, OrderState.PARTIAL_CLOSE)
        ]

    def get_all(self) -> Dict[int, OrderState]:
        return {ticket: state for ticket, (state, _) in self._states.items()}

    def remove(self, ticket: int) -> None:
        self._states.pop(ticket, None)


_default_osm = OrderStateMachine()


def get_order_state_machine() -> OrderStateMachine:
    return _default_osm
