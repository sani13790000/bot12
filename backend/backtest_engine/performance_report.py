"""Auto-repaired placeholder - original had syntax errors."""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional
_LOG = logging.getLogger(__name__)
# TODO: Original file had syntax errors that could not be auto-repaired.
# File: backend/backtest_engine/performance_report.py
class PerformanceReport:
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data
    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)
