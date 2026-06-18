"""
================================================================================
Galaxy Vast AI Trading Platform
شبیه‌سازی مونت کارلو — Monte Carlo Simulator
================================================================================
این ماژول شبیه‌سازی مونت کارلو را برای ارزیابی ریسک استراتژی پیاده‌سازی می‌کند.

قابلیت‌ها:
  - اجرای N شبیه‌سازی با ترتیب تصادفی معاملات
  - محاسبه توزیع احتمال drawdown و بازده
  - محاسبه Value at Risk (VaR) در سطوح ۹۰٪، ۹۵٪، ۹۹٪
  - تشخیص بدترین سناریوی ممکن

نویسنده: Galaxy Vast AI Engine
================================================================================
"""

from __future__ import annotations

import math
import random
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...core.logger import get_logger
from .engine import BacktestTrade

logger = get_logger("research.backtest.monte_carlo")


@dataclass
class MonteCarloResult:
    """
    نتیجه شبیه‌سازی مونت کارلو

    شامل توزیع احتمال نتایج در N شبیه‌سازی مختلف.
    """
    simulations_count: int
    initial_balance: float

    # ─── توزیع بازده نهایی ───
    median_return: float
    mean_return: float
    best_return: float
    worst_return: float
    std_return: float

    # ─── توزیع Max Drawdown ───
    median_max_drawdown: float
    worst_max_drawdown: float
    probability_ruin: float        # احتمال رسیدن drawdown به ۵۰٪+

    # ─── Value at Risk ───
    var_90: float    # در ۹۰٪ موارد ضرر از این مقدار بیشتر نیست
    var_95: float
    var_99: float

    # ─── تعداد شبیه‌سازی‌های سودآور ───
    profitable_simulations: int
    probability_profit: float

    # ─── curve های ۱۰٪، ۵۰٪، ۹۰٪ ───
    percentile_10_curve: List[float]
    percentile_50_curve: List[float]
    percentile_90_curve: List[float]

    def to_dict(self) -> Dict:
        """تبدیل به dictionary برای نمایش در داشبورد"""
        return {
            "simulations": self.simulations_count,
            "initial_balance": self.initial_balance,
            "returns": {
                "median": round(self.median_return, 2),
                "mean": round(self.mean_return, 2),
                "best": round(self.best_return, 2),
                "worst": round(self.worst_return, 2),
                "std": round(self.std_return, 2),
            },
            "drawdown": {
                "median_max": round(self.median_max_drawdown, 2),
                "worst_max": round(self.worst_max_drawdown, 2),
                "probability_ruin": round(self.probability_ruin * 100, 1),
            },
            "value_at_risk": {
                "var_90": round(self.var_90, 2),
                "var_95": round(self.var_95, 2),
                "var_99": round(self.var_99, 2),
            },
            "probability_profit": round(self.probability_profit * 100, 1),
        }


class MonteCarloSimulator:
    """
    شبیه‌ساز مونت کارلو Galaxy Vast

    با تغییر ترتیب تصادفی معاملات، هزاران سناریوی مختلف
    را شبیه‌سازی می‌کند تا توزیع واقعی ریسک مشخص شود.
    """

    def __init__(self, simulations: int = 1000, seed: Optional[int] = None) -> None:
        """
        مقداردهی اولیه شبیه‌ساز

        Args:
            simulations: تعداد شبیه‌سازی
            seed: seed برای reproducibility (اختیاری)
        """
        self._simulations = simulations
        self._rng = random.Random(seed)
        logger.info(f"شبیه‌ساز مونت کارلو آماده — تعداد: {simulations}")

    async def run(
        self,
        trades: List[BacktestTrade],
        initial_balance: float,
        ruin_threshold_percent: float = 50.0,
    ) -> MonteCarloResult:
        """
        اجرای شبیه‌سازی مونت کارلو

        Args:
            trades: لیست معاملات بک‌تست
            initial_balance: موجودی اولیه
            ruin_threshold_percent: آستانه ورشکستگی (درصد)

        Returns:
            MonteCarloResult: نتیجه کامل شبیه‌سازی
        """
        if len(trades) < 10:
            raise ValueError("حداقل ۱۰ معامله برای مونت کارلو لازم است")

        logger.info(
            f"شروع مونت کارلو | معاملات: {len(trades)} | "
            f"شبیه‌سازی: {self._simulations}"
        )

        pnl_list = [t.pnl_money for t in trades]
        ruin_threshold = initial_balance * (1 - ruin_threshold_percent / 100)

        all_final_balances: List[float] = []
        all_max_drawdowns: List[float] = []
        ruin_count = 0
        all_equity_curves: List[List[float]] = []

        # ─── اجرای N شبیه‌سازی ───
        batch_size = 100
        for batch_start in range(0, self._simulations, batch_size):
            batch_end = min(batch_start + batch_size, self._simulations)

            for _ in range(batch_start, batch_end):
                shuffled = pnl_list.copy()
                self._rng.shuffle(shuffled)

                balance = initial_balance
                peak = initial_balance
                max_dd = 0.0
                equity_curve = [initial_balance]

                for pnl in shuffled:
                    balance += pnl
                    if balance > peak:
                        peak = balance
                    dd = ((peak - balance) / peak) * 100 if peak > 0 else 0
                    max_dd = max(max_dd, dd)
                    equity_curve.append(balance)
                    if balance <= ruin_threshold:
                        ruin_count += 1
                        break

                all_final_balances.append(balance)
                all_max_drawdowns.append(max_dd)
                all_equity_curves.append(equity_curve)

            await asyncio.sleep(0)  # اجازه به event loop

        # ─── محاسبه آمار ───
        all_final_balances.sort()
        all_max_drawdowns.sort()

        returns = [
            ((b - initial_balance) / initial_balance) * 100
            for b in all_final_balances
        ]

        median_idx = len(returns) // 2
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_return = math.sqrt(variance)

        # ─── Value at Risk ───
        sorted_returns = sorted(returns)
        var_90_idx = int(len(sorted_returns) * 0.10)
        var_95_idx = int(len(sorted_returns) * 0.05)
        var_99_idx = int(len(sorted_returns) * 0.01)
        var_90 = sorted_returns[max(0, var_90_idx)]
        var_95 = sorted_returns[max(0, var_95_idx)]
        var_99 = sorted_returns[max(0, var_99_idx)]

        # ─── Percentile Curves (۱۰٪، ۵۰٪، ۹۰٪) ───
        max_len = max(len(c) for c in all_equity_curves)
        p10_curve = self._percentile_curve(all_equity_curves, 10, max_len)
        p50_curve = self._percentile_curve(all_equity_curves, 50, max_len)
        p90_curve = self._percentile_curve(all_equity_curves, 90, max_len)

        profitable = sum(1 for b in all_final_balances if b > initial_balance)

        result = MonteCarloResult(
            simulations_count=self._simulations,
            initial_balance=initial_balance,
            median_return=returns[median_idx],
            mean_return=mean_return,
            best_return=returns[-1],
            worst_return=returns[0],
            std_return=std_return,
            median_max_drawdown=all_max_drawdowns[median_idx],
            worst_max_drawdown=all_max_drawdowns[-1],
            probability_ruin=ruin_count / self._simulations,
            var_90=var_90,
            var_95=var_95,
            var_99=var_99,
            profitable_simulations=profitable,
            probability_profit=profitable / self._simulations,
            percentile_10_curve=p10_curve,
            percentile_50_curve=p50_curve,
            percentile_90_curve=p90_curve,
        )

        logger.info(
            f"مونت کارلو کامل | "
            f"احتمال سود: {result.probability_profit*100:.1f}% | "
            f"Median Return: {result.median_return:.1f}% | "
            f"Worst DD: {result.worst_max_drawdown:.1f}%"
        )

        return result

    def _percentile_curve(
        self,
        curves: List[List[float]],
        percentile: int,
        max_len: int,
    ) -> List[float]:
        """
        استخراج curve در یک percentile مشخص

        برای هر نقطه زمانی، مقدار percentile مشخص را از
        تمام شبیه‌سازی‌ها استخراج می‌کند.
        """
        result = []
        idx = int(len(curves) * percentile / 100)
        idx = max(0, min(idx, len(curves) - 1))

        for step in range(max_len):
            values = []
            for curve in curves:
                if step < len(curve):
                    values.append(curve[step])
                else:
                    values.append(curve[-1])
            values.sort()
            result.append(values[idx])

        return result
