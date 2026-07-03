"""backend/backtest_engine/performance_report.py"""
from __future__ import annotations
import logging
from typing import Any
logger = logging.getLogger(__name__)

class PerformanceReport:
    def __init__(self, trades: list | None = None) -> None:
        self.trades = trades or []

    def generate(self) -> dict[str, Any]:
        return {"trades": len(self.trades), "pnl": 0.0, "win_rate": 0.0}

    def to_dict(self) -> dict[str, Any]:
        return self.generate()

__all__ = ["PerformanceReport"]
