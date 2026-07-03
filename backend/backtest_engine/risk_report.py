"""
Module: risk_report
Path: backend/backtest_engine/risk_report.py
Note: Stub with core risk metrics.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RiskReport:
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    expected_shortfall: float = 0.0
    volatility: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "var_95": self.var_95,
            "var_99": self.var_99,
            "expected_shortfall": self.expected_shortfall,
            "volatility": self.volatility,
        }
