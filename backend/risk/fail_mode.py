"""backend/risk/fail_mode.py
FIX #6 - Single source of truth for FailMode enum.

All risk gates import FailMode from here.
Backward compat: FailMode.FAIL_CLOSED == 'FAIL_CLOSED' (str Enum).
"""
from __future__ import annotations
from enum import Enum


class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


def coerce(value) -> FailMode:
    if isinstance(value, FailMode):
        return value
    return FailMode(str(value).upper().strip())
