"""Institutional Performance Metrics — all standard quant finance KPIs."""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class PerformanceReport:
    # Core
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float           # %
    profit_factor: float
    total_net_profit: float
    total_gross_profit: float
    total_gross_loss: float
    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_usd: float
    recovery_factor: float
    ulcer_index: float
    # Per-trade
    avg_win_usd: float
    avg_loss_usd: float
    avg_trade_usd: float
    expectancy_usd: float
    avg_risk_reward: float
    # Duration
    avg_trade_duration_bars: float
    longest_win_streak: int
    longest_loss_streak: int
    # Distribution
    skewness: float
    kurtosis: float
    # Equity
    initial_balance: float
    final_balance: float
    total_return_pct: float
    cagr_pct: float
    equity_curve: List[Tuple[float, float]]  # (timestamp, equity)
    monthly_returns: Dict[str, float]        # {"2024-01": 3.2, ...}


class PerformanceMetrics:
    """
    Computes all institutional performance metrics from a list of trade P&Ls.
    Pure Python — no external dependencies.
    """

    @staticmethod
    def compute(
        trades: List[Dict],  # [{net_profit, open_time, close_time, risk_reward}, ...]
        equity_curve: List[Tuple[float, float]],
        initial_balance: float,
        periods_per_year: int = 252,
    ) -> PerformanceReport:

        if not trades:
            return PerformanceMetrics._empty(initial_balance)

        pnls = [t["net_profit"] for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        gross_win = sum(winners)
        gross_loss = abs(sum(losers))
        total_net = sum(pnls)

        win_rate = len(winners) / len(pnls) * 100
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

        # Equity-based drawdown
        max_dd_usd, max_dd_pct = PerformanceMetrics._max_drawdown(equity_curve, initial_balance)
        peak = max(e for _, e in equity_curve) if equity_curve else initial_balance

        # Returns series
        returns = [p / initial_balance for p in pnls]
        avg_ret = sum(returns) / len(returns)
        std_ret = PerformanceMetrics._std(returns)
        downside_returns = [r for r in returns if r < 0]
        std_down = PerformanceMetrics._std(downside_returns) if downside_returns else std_ret

        sharpe = (avg_ret / std_ret * math.sqrt(periods_per_year)) if std_ret > 0 else 0
        sortino = (avg_ret / std_down * math.sqrt(periods_per_year)) if std_down > 0 else 0

        total_return_pct = (total_net / initial_balance) * 100
        n_years = len(trades) / periods_per_year if periods_per_year > 0 else 1
        cagr = ((initial_balance + total_net) / initial_balance) ** (1 / n_years) - 1 if n_years > 0 else 0
        calmar = (cagr * 100) / max_dd_pct if max_dd_pct > 0 else 0
        recovery = total_net / max_dd_usd if max_dd_usd > 0 else 0
        ulcer = PerformanceMetrics._ulcer_index(equity_curve)

        # Streaks
        win_streak, loss_streak = PerformanceMetrics._streaks(pnls)

        # Distribution
        skew = PerformanceMetrics._skewness(returns)
        kurt = PerformanceMetrics._kurtosis(returns)

        # Avg duration
        durations = []
        for t in trades:
            if "open_time" in t and "close_time" in t and t["close_time"]:
                durations.append(t["close_time"] - t["open_time"])
        avg_dur = sum(durations) / len(durations) if durations else 0

        # Monthly returns
        monthly = PerformanceMetrics._monthly_returns(trades)

        final_balance = initial_balance + total_net

        return PerformanceReport(
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=round(win_rate, 2),
            profit_factor=round(pf, 3),
            total_net_profit=round(total_net, 2),
            total_gross_profit=round(gross_win, 2),
            total_gross_loss=round(gross_loss, 2),
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            calmar_ratio=round(calmar, 3),
            max_drawdown_pct=round(max_dd_pct, 2),
            max_drawdown_usd=round(max_dd_usd, 2),
            recovery_factor=round(recovery, 3),
            ulcer_index=round(ulcer, 4),
            avg_win_usd=round(sum(winners) / len(winners), 2) if winners else 0,
            avg_loss_usd=round(sum(losers) / len(losers), 2) if losers else 0,
            avg_trade_usd=round(total_net / len(pnls), 2),
            expectancy_usd=round(total_net / len(pnls), 2),
            avg_risk_reward=round(sum(t.get("risk_reward", 0) for t in trades) / len(trades), 2),
            avg_trade_duration_bars=round(avg_dur / 900, 1),  # M15 bars
            longest_win_streak=win_streak,
            longest_loss_streak=loss_streak,
            skewness=round(skew, 4),
            kurtosis=round(kurt, 4),
            initial_balance=initial_balance,
            final_balance=round(final_balance, 2),
            total_return_pct=round(total_return_pct, 2),
            cagr_pct=round(cagr * 100, 2),
            equity_curve=equity_curve,
            monthly_returns=monthly,
        )

    # ------------------------------------------------------------------ #
    #  Statistical helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _std(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _max_drawdown(equity_curve: List[Tuple[float, float]], initial: float) -> Tuple[float, float]:
        if not equity_curve:
            return 0.0, 0.0
        peak = initial
        max_dd = 0.0
        for _, eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        peak_val = max(e for _, e in equity_curve)
        dd_pct = (max_dd / peak_val * 100) if peak_val > 0 else 0
        return max_dd, dd_pct

    @staticmethod
    def _ulcer_index(equity_curve: List[Tuple[float, float]]) -> float:
        if len(equity_curve) < 2:
            return 0.0
        equities = [e for _, e in equity_curve]
        peak = equities[0]
        drawdowns_sq = []
        for e in equities:
            if e > peak:
                peak = e
            dd_pct = (peak - e) / peak * 100 if peak > 0 else 0
            drawdowns_sq.append(dd_pct ** 2)
        return math.sqrt(sum(drawdowns_sq) / len(drawdowns_sq))

    @staticmethod
    def _streaks(pnls: List[float]) -> Tuple[int, int]:
        max_win = max_loss = cur_win = cur_loss = 0
        for p in pnls:
            if p > 0:
                cur_win += 1
                cur_loss = 0
                max_win = max(max_win, cur_win)
            else:
                cur_loss += 1
                cur_win = 0
                max_loss = max(max_loss, cur_loss)
        return max_win, max_loss

    @staticmethod
    def _skewness(values: List[float]) -> float:
        n = len(values)
        if n < 3:
            return 0.0
        mean = sum(values) / n
        std = PerformanceMetrics._std(values)
        if std == 0:
            return 0.0
        return sum(((v - mean) / std) ** 3 for v in values) * n / ((n - 1) * (n - 2))

    @staticmethod
    def _kurtosis(values: List[float]) -> float:
        n = len(values)
        if n < 4:
            return 0.0
        mean = sum(values) / n
        std = PerformanceMetrics._std(values)
        if std == 0:
            return 0.0
        return sum(((v - mean) / std) ** 4 for v in values) / n - 3

    @staticmethod
    def _monthly_returns(trades: List[Dict]) -> Dict[str, float]:
        import datetime
        monthly: Dict[str, float] = {}
        for t in trades:
            if "close_time" not in t or not t["close_time"]:
                continue
            try:
                dt = datetime.datetime.utcfromtimestamp(float(t["close_time"]))
                key = dt.strftime("%Y-%m")
                monthly[key] = monthly.get(key, 0) + t["net_profit"]
            except Exception:
                pass
        return monthly

    @staticmethod
    def _empty(initial_balance: float) -> PerformanceReport:
        return PerformanceReport(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0.0, profit_factor=0.0, total_net_profit=0.0,
            total_gross_profit=0.0, total_gross_loss=0.0,
            sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
            max_drawdown_pct=0.0, max_drawdown_usd=0.0,
            recovery_factor=0.0, ulcer_index=0.0,
            avg_win_usd=0.0, avg_loss_usd=0.0, avg_trade_usd=0.0,
            expectancy_usd=0.0, avg_risk_reward=0.0,
            avg_trade_duration_bars=0.0, longest_win_streak=0, longest_loss_streak=0,
            skewness=0.0, kurtosis=0.0,
            initial_balance=initial_balance, final_balance=initial_balance,
            total_return_pct=0.0, cagr_pct=0.0, equity_curve=[], monthly_returns={},
        )
