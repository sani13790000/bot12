"""
Module: order_state_machine
Path: backend/execution/order_state_machine.py
Note: Stub - original had unrecoverable corruption.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional


class OrderState(str, Enum):
    PENDING   = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL   = "PARTIAL"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    FAILED    = "FAILED"


class OrderStateMachine:
    """Tracks and validates order state transitions."""

    TRANSITIONS = {
        OrderState.PENDING:   [OrderState.SUBMITTED, OrderState.CANCELLED],
        OrderState.SUBMITTED: [OrderState.PARTIAL, OrderState.FILLED, OrderState.REJECTED],
        OrderState.PARTIAL:   [OrderState.FILLED, OrderState.CANCELLED],
    }

    def __init__(self, initial: OrderState = OrderState.PENDING) -> None:
        self.state = initial

    def transition(self, new_state: OrderState) -> bool:
        allowed = self.TRANSITIONS.get(self.state, [])
        if new_state in allowed:
            self.state = new_state
            return True
        return False
