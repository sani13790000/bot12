"""Execution package — Phase 3.

Provides MT5 connector, order execution, semi-auto trading and
failure recovery with order journal.
"""
from .mt5_connector import (
    MT5Connector,
    MT5OrderRequest,
    MT5OrderResult,
    MT5Position,
    get_order_journal,
)
from .failure_recovery import (
    FailureRecoveryManager,
    RecoveryStrategy,
    get_recovery_manager,
)
from .semi_auto import (
    SemiAutoEngine,
    SemiAutoSignal,
    get_semi_auto_engine,
)
from .order_state_machine import (
    OrderStateMachine,
    OrderStateTransitionError,
    get_order_state_machine,
)

__all__ = [
    "MT5Connector",
    "MT5OrderRequest",
    "MT5OrderResult",
    "MT5Position",
    "get_order_journal",
    "FailureRecoveryManager",
    "RecoveryStrategy",
    "get_recovery_manager",
    "SemiAutoEngine",
    "SemiAutoSignal",
    "get_semi_auto_engine",
    "OrderStateMachine",
    "OrderStateTransitionError",
    "get_order_state_machine",
]
