"""backend/risk/fail_mode.py
FIX #6 - Single source of truth for FailMode enum.

All risk gates (VolatilityFilter, CorrelationFilter, ExposureControlEngine,
PortfolioRiskManager, RiskOrchestrator) import from here.

Backward compat:
  - FailMode.FAIL_CLOSED / FailMode.FAIL_OPEN  (existing code unchanged)
  - str("FAIL_CLOSED") / str("FAIL_OPEN")  accepted everywhere via coerce()
"""
from __future__ import annotations
from enum import Enum


class FailMode(str, Enum):
    """
    Controls gate behavior on unexpected exceptions.

    FAIL_CLOSED (default, safe):
        Any exception inside a gate => block the trade.
        Ensures no unexamined state can silently allow a trade.

    FAIL_OPEN (permissive, use only for non-critical gates):
        Any exception inside a gate => allow the trade.
        Every exception is still logged at CRITICAL level.
    """
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


def coerce(value) -> FailMode:
    """Accept FailMode enum, 'FAIL_CLOSED', or 'FAIL_OPEN' string."""
    if isinstance(value, FailMode):
        return value
    if isinstance(value, str):
        upper = value.upper()
        if upper == "FAIL_CLOSED":
            return FailMode.FAIL_CLOSED
        if upper == "FAIL_OPEN":
            return FailMode.FAIL_OPEN
    raise ValueError(
        f"Invalid fail_mode {value!r}. Use FailMode.FAIL_CLOSED or FailMode.FAIL_OPEN"
    )
