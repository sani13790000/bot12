"""Galaxy Vast AI Trading Platform — Institutional Risk Engine.

- Value at Risk (VaR)
- Conditional VaR (CVaR)
- Position sizing
- Drawdown circuit breaker
- Exposure limits
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class RiskAssessment:
    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    recommended_position_size: float
    exposure_pct: float
    within_limits: bool
    drawdown_pct: float
    circuit_breaker_open: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "var_95": round(self.var_95, 2),
            "cvar_95": round(self.cvar_95, 2),
            "var_99": round(self.var_99, 2),
            "cvar_99": round(self.cvar_99, 2),
            "recommended_position_size": round(self.recommended_position_size, 2),
            "exposure_pct": round(self.exposure_pct, 4),
            "within_limits": self.within_limits,
            "drawdown_pct": round(self.drawdown_pct, 4),
            "circuit_breaker_open": self.circuit_breaker_open,
        }


class InstitutionalRiskEngine:
    """Advanced risk engine for institutional trading."""

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        max_risk_per_trade_pct: float = 1.0,
        max_daily_risk_pct: float = 3.0,
        max_drawdown_pct: float = 10.0,
        max_correlated_exposure_pct: float = 5.0,
    ):
        self.initial_balance = initial_balance
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_risk_pct = max_daily_risk_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_correlated_exposure_pct = max_correlated_exposure_pct
        self.daily_risk_used_pct = 0.0

    def assess(
        self,
        returns: List[float],
        current_balance: float,
        equity_curve: List[float],
        current_exposure_pct: float = 0.0,
    ) -> RiskAssessment:
        arr = np.array(returns) if returns else np.array([0.0])
        var_95 = float(np.percentile(arr, 5))
        var_99 = float(np.percentile(arr, 1))
        cvar_95 = float(arr[arr <= var_95].mean()) if any(arr <= var_95) else var_95
        cvar_99 = float(arr[arr <= var_99].mean()) if any(arr <= var_99) else var_99

        drawdown = self._current_drawdown(equity_curve)
        circuit_open = drawdown >= self.max_drawdown_pct

        available_risk = self.max_daily_risk_pct - self.daily_risk_used_pct
        recommended = current_balance * (min(available_risk, self.max_risk_per_trade_pct) / 100.0)

        within_limits = (
            not circuit_open
            and self.daily_risk_used_pct < self.max_daily_risk_pct
            and current_exposure_pct < self.max_correlated_exposure_pct
        )

        return RiskAssessment(
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            recommended_position_size=recommended,
            exposure_pct=current_exposure_pct,
            within_limits=within_limits,
            drawdown_pct=drawdown,
            circuit_breaker_open=circuit_open,
        )

    def add_daily_risk(self, risk_usd: float, balance: float) -> None:
        self.daily_risk_used_pct += (risk_usd / balance) * 100.0

    def reset_daily_risk(self) -> None:
        self.daily_risk_used_pct = 0.0

    @staticmethod
    def _current_drawdown(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def kelly_position_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        balance: float,
        fraction: float = 0.25,
    ) -> float:
        """Fractional Kelly position size in USD."""
        if avg_loss == 0:
            return 0.0
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss
        kelly = max(0.0, kelly) * fraction
        return balance * kelly
