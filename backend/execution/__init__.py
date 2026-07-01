"""Execution package — Phase 3."""
from __future__ import annotations

__all__ = [
    "MT5Connector",
    "TradeExecutor",
    "PositionManager",
    "FailureRecovery",
    "SemiAutoHandler",
]

try:
    from .mt5_connector import MT5Connector, MT5Order, MT5Position
except ImportError:
    pass

try:
    from .trade_executor import TradeExecutor
except ImportError:
    pass

try:
    from .position_manager import PositionManager
except ImportError:
    pass

try:
    from .failure_recovery import FailureRecovery
except ImportError:
    pass

try:
    from .semi_auto import SemiAutoHandler, get_semi_auto_handler
except ImportError:
    pass
