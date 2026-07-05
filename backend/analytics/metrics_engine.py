"""backend/analytics/metrics_engine.py
Galaxy Vast AI Trading Platform
MetricsEngine — Professional Quant Metrics Calculator

Calculates:
  - Sharpe Ratio        (risk-adjusted return)
  - Sortino Ratio       (downside-risk-adjusted return)
  - Calmar Ratio        (return / max drawdown)
  - Profit Factor       (gross profit / gross loss)
  - Recovery Factor     (net profit / max drawdown)
  - Expectancy          (avg R per trade)
  - Max Drawdown        (peak-to-trough)
  - Win Rate            (% winning trades)
  - Average RR          (average risk:reward)
  - CAGR                (compound annual growth rate)
  - Agent Performance   (via AgentPerformanceTracker — Phase L)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


# ------------------------------------------------------------------ #
# Data types
# ------------------------------------------------------------------ #

@dataclass
class TradeRecord:
    """Minimal trade record for metric calculations."""
    pnl:          float
    entry_price:  float
    exit_price:   float
    stop_loss:    float
    take_profit:  float
    direction:    str          # "BUY" | "SELL"
    opened_at:    datetime
    closed_at:    datetime
    symbol:       str = ""
    commission:   float = 0.0


@dataclass
class MetricResult:
    sharpe_ratio:    Optional[float] = None
    sortino_ratio:   Optional[float] = None
    calmar_ratio:    Optional[float] = None
    profit_factor:   Optional[float] = None
    recovery_factor: Optional[float] = None
    expectancy:      Optional[float] = None
    max_drawdown:    Optional[float] = None
    win_rate:        Optional[float] = None
    avg_rr:          Optional[float] = None
    cagr:            Optional[float] = None
    total_trades:    int = 0
    total_pnl:       float = 0.0
    gross_profit:    float = 0.0
    gross_loss:      float = 0.0
    winning_trades:  int = 0
    losing_trades:   int = 0
    avg_win:         Optional[float] = None
    avg_loss:        Optional[float] = None
    errors:          List[str] = field(default_factory=list)


# ------------------------------------------------------------------ #
# Engine
# ------------------------------------------------------------------ #

class MetricsEngine:
    """Stateless metrics calculator."""

    RISK_FREE_RATE_ANNUAL: float = 0.05   # 5% annual
    TRADING_DAYS_YEAR:     int   = 252

    # ---------------------------------------------------------------- #
    # Main entry point
    # ---------------------------------------------------------------- #

    def calculate(self, trades: Sequence[TradeRecord]) -> MetricResult:
        """Calculate all metrics from a list of closed trades."""
        result = MetricResult()
        if not trades:
            result.errors.append("no_trades")
            return result

        result.total_trades = len(trades)
        pnls = [t.pnl - t.commission for t in trades]
        result.total_pnl   = sum(pnls)
        result.gross_profit = sum(p for p in pnls if p > 0)
        result.gross_loss   = abs(sum(p for p in pnls if p < 0))

        wins  = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        result.winning_trades = len(wins)
        result.losing_trades  = len(losses)
        result.avg_win  = sum(wins)   / len(wins)   if wins   else None
        result.avg_loss = sum(losses) / len(losses) if losses else None

        result.win_rate      = self._win_rate(pnls)
        result.profit_factor = self._profit_factor(result.gross_profit, result.gross_loss)
        result.max_drawdown  = self._max_drawdown(pnls)
        result.expectancy    = self._expectancy(trades)
        result.avg_rr        = self._avg_rr(trades)
        result.sharpe_ratio  = self._sharpe(pnls)
        result.sortino_ratio = self._sortino(pnls)
        result.calmar_ratio  = self._calmar(pnls, result.max_drawdown, trades)
        result.recovery_factor = self._recovery(result.total_pnl, result.max_drawdown)
        result.cagr          = self._cagr(pnls, trades)

        return result

    # ---------------------------------------------------------------- #
    # Individual metric calculators
    # ---------------------------------------------------------------- #

    def _win_rate(self, pnls: List[float]) -> float:
        if not pnls:
            return 0.0
        return len([p for p in pnls if p > 0]) / len(pnls)

    def _profit_factor(self, gross_profit: float, gross_loss: float) -> Optional[float]:
        if gross_loss == 0:
            return None if gross_profit == 0 else float("inf")
        return gross_profit / gross_loss

    def _max_drawdown(self, pnls: List[float]) -> float:
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for pnl in pnls:
            equity += pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _expectancy(self, trades: Sequence[TradeRecord]) -> Optional[float]:
        if not trades:
            return None
        pnls = [t.pnl - t.commission for t in trades]
        wins  = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        if not losses:
            return sum(wins) / len(trades) if wins else 0.0
        win_rate   = len(wins) / len(pnls)
        avg_win    = sum(wins) / len(wins) if wins else 0.0
        avg_loss   = abs(sum(losses) / len(losses))
        return win_rate * avg_win - (1 - win_rate) * avg_loss

    def _avg_rr(self, trades: Sequence[TradeRecord]) -> Optional[float]:
        rrs: List[float] = []
        for t in trades:
            risk   = abs(t.entry_price - t.stop_loss)
            reward = abs(t.exit_price - t.entry_price)
            if risk > 0:
                rrs.append(reward / risk)
        return sum(rrs) / len(rrs) if rrs else None

    def _sharpe(self, pnls: List[float]) -> Optional[float]:
        if len(pnls) < 2:
            return None
        n = len(pnls)
        mean = sum(pnls) / n
        variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
        std = math.sqrt(variance)
        if std == 0:
            return None
        daily_rf = self.RISK_FREE_RATE_ANNUAL / self.TRADING_DAYS_YEAR
        return (mean - daily_rf) / std * math.sqrt(self.TRADING_DAYS_YEAR)

    def _sortino(self, pnls: List[float]) -> Optional[float]:
        if len(pnls) < 2:
            return None
        n = len(pnls)
        mean = sum(pnls) / n
        downside = [p for p in pnls if p < 0]
        if not downside:
            return None
        downside_var = sum(p ** 2 for p in downside) / n
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return None
        daily_rf = self.RISK_FREE_RATE_ANNUAL / self.TRADING_DAYS_YEAR
        return (mean - daily_rf) / downside_std * math.sqrt(self.TRADING_DAYS_YEAR)

    def _calmar(self, pnls: List[float], max_dd: float,
                trades: Sequence[TradeRecord]) -> Optional[float]:
        if max_dd == 0 or not trades:
            return None
        # Annualise total PnL
        total_pnl = sum(pnls)
        days = max((trades[-1].closed_at - trades[0].opened_at).days, 1)
        annual_return = total_pnl * (365 / days)
        return annual_return / max_dd

    def _recovery(self, total_pnl: float, max_dd: float) -> Optional[float]:
        if max_dd == 0:
            return None
        return total_pnl / max_dd

    def _cagr(self, pnls: List[float], trades: Sequence[TradeRecord]) -> Optional[float]:
        if not trades or len(trades) < 2:
            return None
        days = max((trades[-1].closed_at - trades[0].opened_at).days, 1)
        years = days / 365.0
        start_equity = 10_000.0   # normalised base
        end_equity   = start_equity + sum(pnls)
        if end_equity <= 0 or start_equity <= 0:
            return None
        return (end_equity / start_equity) ** (1 / years) - 1

    # ---------------------------------------------------------------- #
    # Agent performance — Phase L: real data via AgentPerformanceTracker
    # ---------------------------------------------------------------- #

    async def get_agent_performance(self) -> Dict[str, Any]:
        """Real agent voting stats from AgentPerformanceTracker ring buffer."""
        try:
            from backend.analytics.agent_performance_tracker import agent_tracker
            return await agent_tracker.get_agent_performance()
        except Exception as e:
            return {
                "agents": [],
                "total_votes": 0,
                "consensus_rate": 0.0,
                "error": str(e),
            }

    # ---------------------------------------------------------------- #
    # Convenience: metrics from raw DB trade rows
    # ---------------------------------------------------------------- #

    def from_db_rows(self, rows: List[Dict[str, Any]]) -> MetricResult:
        """Convert raw Supabase trade rows to MetricResult."""
        trades: List[TradeRecord] = []
        for row in rows:
            try:
                trades.append(TradeRecord(
                    pnl=float(row.get("pnl", 0)),
                    entry_price=float(row.get("entry_price", 0)),
                    exit_price=float(row.get("exit_price", 0)),
                    stop_loss=float(row.get("stop_loss", 0)),
                    take_profit=float(row.get("take_profit", 0)),
                    direction=row.get("direction", "BUY"),
                    opened_at=datetime.fromisoformat(row["opened_at"]) if row.get("opened_at") else datetime.now(timezone.utc),
                    closed_at=datetime.fromisoformat(row["closed_at"]) if row.get("closed_at") else datetime.now(timezone.utc),
                    symbol=row.get("symbol", ""),
                    commission=float(row.get("commission", 0)),
                ))
            except Exception:
                continue
        return self.calculate(trades)


# Module-level singleton
metrics_engine = MetricsEngine()
