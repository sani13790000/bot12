"""
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
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TradeRecord:
    """Single closed trade record."""
    ticket: int
    symbol: str
    direction: str                  # BUY | SELL
    entry_price: float
    exit_price: float
    stop_loss: float
    lot_size: float
    profit_loss: float              # in account currency
    open_time: datetime
    close_time: datetime
    pips: float = 0.0
    risk_amount: float = 0.0        # risk in account currency
    reward_amount: float = 0.0      # reward in account currency
    confidence_score: float = 0.0
    session: str = "UNKNOWN"
    strategy_tags: List[str] = field(default_factory=list)

    @property
    def is_winner(self) -> bool:
        return self.profit_loss > 0

    @property
    def rr_ratio(self) -> float:
        """Risk:Reward realized."""
        if self.risk_amount and self.risk_amount != 0:
            return abs(self.profit_loss) / abs(self.risk_amount)
        return 0.0

    @property
    def hold_minutes(self) -> float:
        return (self.close_time - self.open_time).total_seconds() / 60


@dataclass
class DrawdownPoint:
    timestamp: datetime
    equity: float
    drawdown_pct: float
    drawdown_amount: float


@dataclass
class AnalyticsResult:
    """Complete analytics snapshot."""
    # ── Core Stats ──────────────────────────────────────────────
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0

    # ── Profitability ────────────────────────────────────────────
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0

    # ── Ratios ───────────────────────────────────────────────────
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0

    # ── Expectancy ───────────────────────────────────────────────
    expectancy: float = 0.0           # in account currency
    expectancy_r: float = 0.0         # in R multiples
    average_win: float = 0.0
    average_loss: float = 0.0
    average_rr: float = 0.0

    # ── Drawdown ─────────────────────────────────────────────────
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: float = 0.0
    avg_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    # ── Growth ───────────────────────────────────────────────────
    cagr: float = 0.0
    initial_balance: float = 0.0
    final_balance: float = 0.0

    # ── Time ─────────────────────────────────────────────────────
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    trading_days: int = 0
    avg_hold_minutes: float = 0.0

    # ── Symbol Breakdown ─────────────────────────────────────────
    by_symbol: dict = field(default_factory=dict)
    by_session: dict = field(default_factory=dict)
    by_direction: dict = field(default_factory=dict)

    # ── Equity Curve ─────────────────────────────────────────────
    equity_curve: List[dict] = field(default_factory=list)
    drawdown_curve: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "break_even_trades": self.break_even_trades,
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "net_profit": round(self.net_profit, 2),
            "profit_factor": round(self.profit_factor, 4),
            "win_rate": round(self.win_rate, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "recovery_factor": round(self.recovery_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "expectancy_r": round(self.expectancy_r, 4),
            "average_win": round(self.average_win, 2),
            "average_loss": round(self.average_loss, 2),
            "average_rr": round(self.average_rr, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "max_drawdown_amount": round(self.max_drawdown_amount, 2),
            "avg_drawdown_pct": round(self.avg_drawdown_pct, 4),
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_consecutive_wins": self.max_consecutive_wins,
            "cagr": round(self.cagr, 4),
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.final_balance, 2),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "trading_days": self.trading_days,
            "avg_hold_minutes": round(self.avg_hold_minutes, 1),
            "by_symbol": self.by_symbol,
            "by_session": self.by_session,
            "by_direction": self.by_direction,
            "equity_curve": self.equity_curve,
            "drawdown_curve": self.drawdown_curve,
        }


class MetricsEngine:
    """
    Institutional-grade quantitative metrics calculator.

    SOLID: Single Responsibility — only calculates metrics.
    No I/O, no DB access.
    """

    RISK_FREE_RATE_ANNUAL: float = 0.05        # 5% annual risk-free rate
    TRADING_DAYS_PER_YEAR: int = 252
    MINUTES_PER_YEAR: float = 252 * 6.5 * 60  # ~98,280

    def calculate(
        self,
        trades: List[TradeRecord],
        initial_balance: float = 10_000.0,
        risk_free_rate: Optional[float] = None,
    ) -> AnalyticsResult:
        """
        Full analytics pass over a list of closed trades.

        Args:
            trades:          List of closed TradeRecord objects (chronological order)
            initial_balance: Starting account balance
            risk_free_rate:  Annual risk-free rate (overrides default)
        Returns:
            AnalyticsResult with all metrics populated
        """
        result = AnalyticsResult(initial_balance=initial_balance)

        if not trades:
            return result

        rfr = risk_free_rate if risk_free_rate is not None else self.RISK_FREE_RATE_ANNUAL
        trades_sorted = sorted(trades, key=lambda t: t.open_time)

        # ── Basic counts ─────────────────────────────────────────
        result.total_trades = len(trades_sorted)
        result.winning_trades = sum(1 for t in trades_sorted if t.profit_loss > 0)
        result.losing_trades = sum(1 for t in trades_sorted if t.profit_loss < 0)
        result.break_even_trades = result.total_trades - result.winning_trades - result.losing_trades
        result.win_rate = result.winning_trades / result.total_trades

        # ── P&L ──────────────────────────────────────────────────
        result.gross_profit = sum(t.profit_loss for t in trades_sorted if t.profit_loss > 0)
        result.gross_loss = abs(sum(t.profit_loss for t in trades_sorted if t.profit_loss < 0))
        result.net_profit = result.gross_profit - result.gross_loss
        result.final_balance = initial_balance + result.net_profit

        # ── Profit Factor ─────────────────────────────────────────
        result.profit_factor = (
            result.gross_profit / result.gross_loss
            if result.gross_loss > 0 else float("inf")
        )

        # ── Averages ─────────────────────────────────────────────
        winners = [t.profit_loss for t in trades_sorted if t.profit_loss > 0]
        losers  = [t.profit_loss for t in trades_sorted if t.profit_loss < 0]
        result.average_win  = (sum(winners) / len(winners)) if winners else 0.0
        result.average_loss = (sum(losers) / len(losers)) if losers else 0.0
        result.average_rr = (
            abs(result.average_win / result.average_loss)
            if result.average_loss != 0 else 0.0
        )
        result.avg_hold_minutes = sum(t.hold_minutes for t in trades_sorted) / len(trades_sorted)

        # ── Expectancy ───────────────────────────────────────────
        result.expectancy = (
            result.win_rate * result.average_win
            + (1 - result.win_rate) * result.average_loss
        )
        # Expectancy in R multiples
        r_multiples = []
        for t in trades_sorted:
            if t.risk_amount and t.risk_amount > 0:
                r_multiples.append(t.profit_loss / t.risk_amount)
        result.expectancy_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

        # ── Equity Curve + Drawdown ───────────────────────────────
        equity_curve = self._build_equity_curve(trades_sorted, initial_balance)
        result.equity_curve = [
            {"time": str(p["time"]), "equity": round(p["equity"], 2)}
            for p in equity_curve
        ]

        dd_points = self._calculate_drawdown_series(equity_curve)
        result.max_drawdown_pct    = max((p.drawdown_pct for p in dd_points), default=0.0)
        result.max_drawdown_amount = max((p.drawdown_amount for p in dd_points), default=0.0)
        result.avg_drawdown_pct    = (
            sum(p.drawdown_pct for p in dd_points) / len(dd_points) if dd_points else 0.0
        )
        result.drawdown_curve = [
            {"time": str(p.timestamp), "drawdown_pct": round(p.drawdown_pct * 100, 4)}
            for p in dd_points
        ]

        # ── Recovery Factor ───────────────────────────────────────
        result.recovery_factor = (
            result.net_profit / result.max_drawdown_amount
            if result.max_drawdown_amount > 0 else float("inf")
        )

        # ── Period ───────────────────────────────────────────────
        result.period_start = trades_sorted[0].open_time
        result.period_end   = trades_sorted[-1].close_time
        delta_days = (result.period_end - result.period_start).days
        result.trading_days = max(delta_days, 1)

        # ── CAGR ─────────────────────────────────────────────────
        result.cagr = self._cagr(initial_balance, result.final_balance, result.trading_days)

        # ── Sharpe Ratio ─────────────────────────────────────────
        daily_returns = self._daily_returns(equity_curve)
        result.sharpe_ratio  = self._sharpe(daily_returns, rfr)
        result.sortino_ratio = self._sortino(daily_returns, rfr)

        # ── Calmar Ratio ─────────────────────────────────────────
        result.calmar_ratio = (
            result.cagr / result.max_drawdown_pct
            if result.max_drawdown_pct > 0 else float("inf")
        )

        # ── Consecutive Streaks ───────────────────────────────────
        result.max_consecutive_wins, result.max_consecutive_losses = (
            self._consecutive_streaks(trades_sorted)
        )

        # ── Breakdowns ───────────────────────────────────────────
        result.by_symbol    = self._group_breakdown(trades_sorted, "symbol")
        result.by_session   = self._group_breakdown(trades_sorted, "session")
        result.by_direction = self._group_breakdown(trades_sorted, "direction")

        return result

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_equity_curve(
        self, trades: List[TradeRecord], initial_balance: float
    ) -> List[dict]:
        curve = [{"time": trades[0].open_time, "equity": initial_balance}]
        equity = initial_balance
        for t in trades:
            equity += t.profit_loss
            curve.append({"time": t.close_time, "equity": equity})
        return curve

    def _calculate_drawdown_series(self, equity_curve: List[dict]) -> List[DrawdownPoint]:
        points = []
        peak = equity_curve[0]["equity"]
        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            drawdown_amount = peak - eq
            drawdown_pct    = drawdown_amount / peak if peak > 0 else 0.0
            points.append(DrawdownPoint(
                timestamp=point["time"],
                equity=eq,
                drawdown_pct=drawdown_pct,
                drawdown_amount=drawdown_amount,
            ))
        return points

    def _daily_returns(self, equity_curve: List[dict]) -> List[float]:
        """Compute daily percentage returns from equity curve."""
        returns = []
        # group by date
        daily: dict = {}
        for pt in equity_curve:
            d = pt["time"].date() if hasattr(pt["time"], "date") else pt["time"]
            daily[d] = pt["equity"]
        dates = sorted(daily.keys())
        for i in range(1, len(dates)):
            prev = daily[dates[i - 1]]
            curr = daily[dates[i]]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    def _sharpe(self, daily_returns: List[float], annual_rfr: float) -> float:
        if len(daily_returns) < 2:
            return 0.0
        n   = len(daily_returns)
        avg = sum(daily_returns) / n
        var = sum((r - avg) ** 2 for r in daily_returns) / (n - 1)
        std = math.sqrt(var)
        if std == 0:
            return 0.0
        daily_rfr = annual_rfr / self.TRADING_DAYS_PER_YEAR
        excess    = avg - daily_rfr
        return (excess / std) * math.sqrt(self.TRADING_DAYS_PER_YEAR)

    def _sortino(self, daily_returns: List[float], annual_rfr: float) -> float:
        if len(daily_returns) < 2:
            return 0.0
        n         = len(daily_returns)
        avg       = sum(daily_returns) / n
        daily_rfr = annual_rfr / self.TRADING_DAYS_PER_YEAR
        excess    = avg - daily_rfr
        # downside deviation (semi-variance)
        neg = [r for r in daily_returns if r < daily_rfr]
        if not neg:
            return float("inf")
        downside_var = sum((r - daily_rfr) ** 2 for r in neg) / len(neg)
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return (excess / downside_std) * math.sqrt(self.TRADING_DAYS_PER_YEAR)

    def _cagr(self, initial: float, final: float, trading_days: int) -> float:
        if initial <= 0 or trading_days <= 0:
            return 0.0
        years = trading_days / self.TRADING_DAYS_PER_YEAR
        if years < 1e-6:
            return 0.0
        return ((final / initial) ** (1 / years)) - 1

    def _consecutive_streaks(self, trades: List[TradeRecord]):
        max_wins = max_losses = 0
        cur_wins = cur_losses = 0
        for t in trades:
            if t.is_winner:
                cur_wins  += 1
                cur_losses = 0
            elif t.profit_loss < 0:
                cur_losses += 1
                cur_wins   = 0
            else:
                cur_wins = cur_losses = 0
            max_wins   = max(max_wins,   cur_wins)
            max_losses = max(max_losses, cur_losses)
        return max_wins, max_losses

    def _group_breakdown(self, trades: List[TradeRecord], attr: str) -> dict:
        groups: dict = {}
        for t in trades:
            key = getattr(t, attr, "UNKNOWN")
            if key not in groups:
                groups[key] = {
                    "trades": 0, "wins": 0, "losses": 0,
                    "profit": 0.0, "win_rate": 0.0,
                }
            g = groups[key]
            g["trades"] += 1
            g["profit"] = round(g["profit"] + t.profit_loss, 2)
            if t.profit_loss > 0:
                g["wins"] += 1
            elif t.profit_loss < 0:
                g["losses"] += 1
        for g in groups.values():
            g["win_rate"] = round(g["wins"] / g["trades"], 4) if g["trades"] > 0 else 0.0
        return groups
