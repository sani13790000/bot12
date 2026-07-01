"""Execution package - Phase 3."""
from .mt5_connector import MT5Connector, MT5OrderRequest, MT5OrderResult, mt5_connector
from .order_state_machine import (
    ManagedOrder,
    OrderState,
    OrderStateMachine,
    OrderTransition,
    SignalIdempotencyGuard,
    get_order_state_machine,
)
from .position_reconciliation import PositionReconciliation
from .failure_recovery import FailedOrder, FailureRecoveryEngine, RecoveryStrategy
from .execution_service import ExecutionService, get_execution_service
from .order_journal import OrderJournal, JournalEventType, get_order_journal

__all__ = [
    "MT5Connector", "MT5OrderRequest", "MT5OrderResult", "mt5_connector",
    "ManagedOrder", "OrderState", "OrderStateMachine", "OrderTransition",
    "SignalIdempotencyGuard", "get_order_state_machine",
    "PositionReconciliation",
    "FailedOrder", "FailureRecoveryEngine", "RecoveryStrategy",
    "ExecutionService", "get_execution_service",
    "OrderJournal", "JournalEventType", "get_order_journal",
]
