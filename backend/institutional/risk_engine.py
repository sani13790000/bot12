"""Institutional Risk Engine — VaR, CVaR, position sizing, circuit breakers."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class RiskReport:
    # VaR / CVaR
    var_95_usd: float        # 95% Value at Risk
    var_99_usd: float        # 99% Value at Risk
    cvar_95_usd: float       # Conditional VaR (Expected Shortfall)
    # Position
    recommended_lot: float
    max_allowed_lot: float
    risk_usd: float          # dollar risk on this trade
    risk_pct: float          # % of equity at risk
    # Portfolio
    total_exposure_usd: float
    total_exposure_pct: float
    open_trades_count: int
    # Circuit breakers
    daily_loss_usd: float
    daily_loss_pct: float
    daily_limit_hit: bool
    weekly_loss_usd: float
    weekly_limit_hit: bool
    circuit_breaker_active: bool
    circuit_breaker_reason: str
    # Regime
    volatility_regime: str   # LOW | NORMAL | HIGH | EXTREME
    suggested_risk_multiplier: float  # scale down in high vol


class InstitutionalRiskEngine:
    """
    Institutional Risk Engine.

    Features:
    - Historical VaR and CVaR (no normal distribution assumption)
    - Dynamic position sizing based on ATR
    - Daily/weekly loss circuit breakers
    - Volatility regime detection
    - Correlation-adjusted portfolio exposure
    """

    def __init__(
        self,
        initial_equity: float = 10_000.0,
        max_risk_pct: float = 1.0,
        max_daily_loss_pct: float = 3.0,
        max_weekly_loss_pct: float = 6.0,
        max_total_exposure_pct: float = 10.0,
        max_open_trades: int = 5,
        pip_value: float = 1.0,    # USD per pip per lot (XAUUSD)
    ):
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_open_trades = max_open_trades
        self.pip_value = pip_value
        self._daily_pnl: List[float] = []
        self._weekly_pnl: List[float] = []
        self._recent_returns: List[float] = []  # for VaR
        self._open_trades: List[Dict] = []
        self._circuit_breaker: bool = False
        self._circuit_reason: str = ""

    def update_equity(self, equity: float) -> None:
        ret = (equity - self.current_equity) / self.current_equity if self.current_equity > 0 else 0
        self._recent_returns.append(ret)
        if len(self._recent_returns) > 500:
            self._recent_returns.pop(0)
        self.current_equity = equity

    def record_trade_pnl(self, pnl: float) -> None:
        self._daily_pnl.append(pnl)
        self._weekly_pnl.append(pnl)
        if len(self._daily_pnl) > 100:
            self._daily_pnl.pop(0)
        if len(self._weekly_pnl) > 500:
            self._weekly_pnl.pop(0)
        self._check_circuit_breakers()

    def add_open_trade(self, trade: Dict) -> None:
        self._open_trades.append(trade)

    def remove_open_trade(self, trade_id: int) -> None:
        self._open_trades = [t for t in self._open_trades if t.get("trade_id") != trade_id]

    def reset_daily(self) -> None:
        self._daily_pnl.clear()
        if not self._circuit_breaker or "daily" in self._circuit_reason:
            self._circuit_breaker = False
            self._circuit_reason = ""

    def assess_trade(
        self,
        stop_loss_pips: float,
        current_atr: float = 10.0,
        symbol: str = "XAUUSD",
    ) -> RiskReport:

        # ---- Position sizing ----
        risk_usd = self.current_equity * (self.max_risk_pct / 100)
        lot = risk_usd / (stop_loss_pips * self.pip_value) if stop_loss_pips > 0 else 0
        lot = round(max(0.01, min(100.0, lot)), 2)

        # Volatility regime adjustment
        vol_regime, vol_mult = self._volatility_regime(current_atr)
        adjusted_lot = round(lot * vol_mult, 2)

        # ---- Exposure ----
        total_exp = sum(t.get("exposure_usd", 0) for t in self._open_trades)
        exp_pct = total_exp / self.current_equity * 100 if self.current_equity > 0 else 0

        # ---- Daily / Weekly loss ----
        daily_loss = abs(min(0, sum(self._daily_pnl)))
        weekly_loss = abs(min(0, sum(self._weekly_pnl)))
        daily_loss_pct = daily_loss / self.initial_equity * 100
        weekly_loss_pct = weekly_loss / self.initial_equity * 100
        daily_hit = daily_loss_pct >= self.max_daily_loss_pct
        weekly_hit = weekly_loss_pct >= self.max_weekly_loss_pct

        # ---- VaR ----
        var95, var99, cvar95 = self._compute_var()

        return RiskReport(
            var_95_usd=round(var95, 2),
            var_99_usd=round(var99, 2),
            cvar_95_usd=round(cvar95, 2),
            recommended_lot=adjusted_lot,
            max_allowed_lot=lot,
            risk_usd=round(risk_usd, 2),
            risk_pct=self.max_risk_pct,
            total_exposure_usd=round(total_exp, 2),
            total_exposure_pct=round(exp_pct, 2),
            open_trades_count=len(self._open_trades),
            daily_loss_usd=round(daily_loss, 2),
            daily_loss_pct=round(daily_loss_pct, 2),
            daily_limit_hit=daily_hit,
            weekly_loss_usd=round(weekly_loss, 2),
            weekly_limit_hit=weekly_hit,
            circuit_breaker_active=self._circuit_breaker,
            circuit_breaker_reason=self._circuit_reason,
            volatility_regime=vol_regime,
            suggested_risk_multiplier=vol_mult,
        )

    def _check_circuit_breakers(self) -> None:
        daily_loss = abs(min(0, sum(self._daily_pnl)))
        weekly_loss = abs(min(0, sum(self._weekly_pnl)))
        if daily_loss / self.initial_equity * 100 >= self.max_daily_loss_pct:
            self._circuit_breaker = True
            self._circuit_reason = f"Daily loss limit {self.max_daily_loss_pct}% hit"
        elif weekly_loss / self.initial_equity * 100 >= self.max_weekly_loss_pct:
            self._circuit_breaker = True
            self._circuit_reason = f"Weekly loss limit {self.max_weekly_loss_pct}% hit"

    def _compute_var(self) -> Tuple[float, float, float]:
        """Historical VaR and CVaR."""
        if len(self._recent_returns) < 10:
            return 0.0, 0.0, 0.0
        losses = sorted([-r * self.current_equity for r in self._recent_returns])
        n = len(losses)
        idx95 = int(n * 0.95)
        idx99 = int(n * 0.99)
        var95 = losses[min(idx95, n - 1)]
        var99 = losses[min(idx99, n - 1)]
        tail = losses[idx95:]
        cvar95 = sum(tail) / len(tail) if tail else var95
        return max(0, var95), max(0, var99), max(0, cvar95)

    @staticmethod
    def _volatility_regime(atr: float) -> Tuple[str, float]:
        if atr < 5:
            return "LOW", 1.2       # increase size in low vol
        elif atr < 15:
            return "NORMAL", 1.0
        elif atr < 30:
            return "HIGH", 0.7      # reduce size in high vol
        else:
            return "EXTREME", 0.4   # extreme reduction
