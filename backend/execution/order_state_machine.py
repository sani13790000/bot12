"""backend/execution/order_state_machine.py"""
from __future__ import annotations
from enum import Enum
import logging
logger = logging.getLogger(__name__)

class OrderState(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"

class OrderStateMachine:
    TRANSITIONS: dict[OrderState, set[OrderState]] = {
        OrderState.PENDING:    {OrderState.SUBMITTED, OrderState.CANCELLED},
        OrderState.SUBMITTED:  {OrderState.FILLED, OrderState.PARTIAL, OrderState.CANCELLED, OrderState.REJECTED},
        OrderState.PARTIAL:    {OrderState.FILLED, OrderState.CANCELLED},
        OrderState.FILLED:     set(),
        OrderState.CANCELLED:  set(),
        OrderState.REJECTED:   set(),
        OrderState.FAILED:     set(),
    }

    def __init__(self, initial: OrderState = OrderState.PENDING) -> None:
        self._state = initial
        self._history: list[OrderState] = [initial]

    @property
    def state(self) -> OrderState:
        return self._state

    def transition(self, new_state: OrderState) -> bool:
        if new_state in self.TRANSITIONS.get(self._state, set()):
            self._history.append(new_state)
            self._state = new_state
            return True
        logger.warning(f"Invalid transition {self._state} → {new_state}")
        return False

    def history(self) -> list[OrderState]:
        return list(self._history)

__all__ = ["OrderState", "OrderStateMachine"]
