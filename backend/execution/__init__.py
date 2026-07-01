"""Execution package — Phase 3.

Provides MT5 connector, order execution, semi-auto mode,
order state machine, and failure recovery.
"""
from __future__ import annotations

__all__ = [
    "SemiAutoEngine",
    "get_semi_auto_engine",
]

try:
    from .semi_auto import SemiAutoEngine, get_semi_auto_engine
except ImportError:
    pass
