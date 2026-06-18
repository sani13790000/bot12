"""Galaxy Vast AI Trading Platform — Institutional Performance Metrics.

Includes:
- Win rate, profit factor, net profit
- Sharpe ratio, Sortino ratio, Calmar ratio
- Max drawdown (pct & USD)
- Recovery factor, expectancy, avg R:R
- CAGR, annualized volatility
- Ulcer index, skewness, kurtosis
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.research.backtest.engine import BacktestTrade, SharedBacktestMetrics


@dataclass
class PerformanceResult:
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_usd: float
    recovery_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    avg_rr: float
    total_return_pct: float
    cagr_pct: float
    volatility_annual_pct: float
    calmar_ratio: float
    ulcer_index: float
    skewness: float
    kurtosis: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    gross_profit: float
    gross_loss: float
    net_profit: float

    def to_dict(self) -> Dict[str, Any]:
        def _safe(value: Any) -> Any:
            if isinstance(value, float):
                return 0.0 if not math.isfinite(value) else round(value, 6)
            return value
        return {k: _safe(v) for k, v in self.__dict__.items()}


class PerformanceMetrics:
    def __init__(
        self,
        trades: List[BacktestTrade],
        initial_balance: float,
        final_balance: Optional[float] = None,
    ):
        self.trades = trades
        self.initial_balance = initial_balance
        self.final_balance = final_balance or initial_balance + sum(t.pnl_usd for t in trades)

    def calculate(self) -> PerformanceResult:
        if not self.trades:
            return PerformanceResult(
                win_rate=0.0, profit_factor=0.0, sharpe_ratio=0.0, sortino_ratio=0.0,
                max_drawdown_pct=0.0, max_drawdown_usd=0.0, recovery_factor=0.0,
                expectancy=0.0, avg_win=0.0, avg_loss=0.0, avg_rr=0.0,
                total_return_pct=0.0, cagr_pct=0.0, volatility_annual_pct=0.0,
                calmar_ratio=0.0, ulcer_index=0.0, skewness=0.0, kurtosis=0.0,
                total_trades=0, winning_trades=0, losing_trades=0, break_even_trades=0,
                gross_profit=0.0, gross_loss=0.0, net_profit=0.0,
            )

        wins = [t for t in self.trades if t.pnl_usd > 0]
        losses = [t for t in self.trades if t.pnl_usd < 0]
        be = [t for t in self.trades if t.pnl_usd == 0]

        total = len(self.trades)
        win_count = len(wins)
        loss_count = len(losses)
        be_count = len(be)

        gross_profit = sum(t.pnl_usd for t in wins)
        gross_loss = abs(sum(t.pnl_usd for t in losses))
        net_profit = gross_profit - gross_loss

        win_rate = win_count / total * 100.0 if total else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

        returns = [t.pnl_usd / self.initial_balance for t in self.trades]
        sharpe = SharedBacktestMetrics.sharpe_ratio(returns)
        sortino = SharedBacktestMetrics.sortino_ratio(returns)

        equity = self._equity_curve()
        max_dd_pct, max_dd_usd = SharedBacktestMetrics.max_drawdown([e[1] for e in equity])
        recovery_factor = net_profit / max_dd_usd if max_dd_usd > 0 else float("inf")

        avg_win = statistics.mean([t.pnl_usd for t in wins]) if wins else 0.0
        avg_loss = statistics.mean([t.pnl_usd for t in losses]) if losses else 0.0
        avg_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        expectancy = ((win_count / total) * avg_win) - ((loss_count / total) * abs(avg_loss)) if total else 0.0

        total_return_pct = (self.final_balance - self.initial_balance) / self.initial_balance * 100.0
        cagr_pct = self._cagr(equity)
        volatility_annual_pct = statistics.stdev(returns) * math.sqrt(252) * 100.0 if len(returns) > 1 else 0.0
        calmar = SharedBacktestMetrics.calmar_ratio(returns)

        ulcer = self._ulcer_index([e[1] for e in equity])
        skew = self._skewness(returns)
        kurt = self._kurtosis(returns)

        return PerformanceResult(
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 4) if math.isfinite(profit_factor) else 0.0,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_usd=max_dd_usd,
            recovery_factor=round(recovery_factor, 4) if math.isfinite(recovery_factor) else 0.0,
            expectancy=round(expectancy, 4),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            avg_rr=round(avg_rr, 4),
            total_return_pct=round(total_return_pct, 4),
            cagr_pct=round(cagr_pct, 4),
            volatility_annual_pct=round(volatility_annual_pct, 4),
            calmar_ratio=calmar,
            ulcer_index=round(ulcer, 4),
            skewness=round(skew, 4),
            kurtosis=round(kurt, 4),
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            break_even_trades=be_count,
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            net_profit=round(net_profit, 2),
        )

    def _equity_curve(self) -> List[Tuple[datetime, float]]:
        equity = self.initial_balance
        curve = []
        first_ts = None
        for t in self.trades:
            equity += t.pnl_usd
            exit_ts = t.exit_time
            if isinstance(exit_ts, str):
                try:
                    exit_ts = datetime.fromisoformat(exit_ts)
                except Exception:
                    exit_ts = datetime.utcnow()
            first_ts = first_ts or exit_ts
            curve.append((exit_ts, equity))
        if not curve:
            curve.append((datetime.utcnow(), self.initial_balance))
        return curve

    def _cagr(self, equity: List[Tuple[datetime, float]]) -> float:
        if len(equity) < 2:
            return 0.0
        start = equity[0][0]
        end = equity[-1][0]
        days = max((end - start).total_seconds() / 86400.0, 1.0)
        years = days / 365.25
        return (((self.final_balance / self.initial_balance) ** (1.0 / years)) - 1.0) * 100.0

    @staticmethod
    def _ulcer_index(equity: List[float]) -> float:
        if not equity:
            return 0.0
        peak = equity[0]
        sq_dd = []
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            sq_dd.append(dd ** 2)
        return math.sqrt(sum(sq_dd) / len(sq_dd)) * 100.0

    @staticmethod
    def _skewness(data: List[float]) -> float:
        n = len(data)
        if n < 3:
            return 0.0
        mean = sum(data) / n
        m3 = sum((x - mean) ** 3 for x in data) / n
        m2 = sum((x - mean) ** 2 for x in data) / n
        if m2 == 0:
            return 0.0
        return m3 / (m2 ** 1.5)

    @staticmethod
    def _kurtosis(data: List[float]) -> float:
        n = len(data)
        if n < 4:
            return 0.0
        mean = sum(data) / n
        m4 = sum((x - mean) ** 4 for x in data) / n
        m2 = sum((x - mean) ** 2 for x in data) / n
        if m2 == 0:
            return 0.0
        return m4 / (m2 ** 2) - 3.0

    def to_dict(self) -> Dict[str, Any]:
        return self.calculate().to_dict()
