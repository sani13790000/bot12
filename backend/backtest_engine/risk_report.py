"""backend/backtest_engine/risk_report.py"""
from __future__ import annotations
from typing import Any

class RiskReport:
    def __init__(self, equity_curve: list | None = None) -> None:
        self.equity_curve = equity_curve or []

    def generate(self) -> dict[str, Any]:
        return {"max_drawdown": 0.0, "sharpe": 0.0, "var_95": 0.0}

    def to_dict(self) -> dict[str, Any]:
        return self.generate()

__all__ = ["RiskReport"]
