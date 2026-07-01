"""
backend/execution/order_state_machine.py
Galaxy Vast AI — Order State Machine
NOTE: Auto-repaired stub due to binary corruption.
"""
from __future__ import annotations
import logging

_LOG = logging.getLogger(__name__)


class OrderStateMachine:
    """Order state machine stub."""

    def __init__(self) -> None:
        self.state = 'IDLE'

    def transition(self, event: str) -> str:
        _LOG.info('OrderStateMachine.transition: %s -> %s', self.state, event)
        self.state = event
        return self.state
