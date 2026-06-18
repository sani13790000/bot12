"""
================================================================================
Galaxy Vast AI Trading Platform
شبیه‌سازی مونت‌کارلو — Monte Carlo Simulation

این ماژول با اجرای هزاران شبیه‌سازی تصادفی از دنباله معاملات،
توزیع احتمال نتایج را محاسبه می‌کند.

کاربرد:
- ارزیابی استحکام استراتژی در برابر تصادف
- محاسبه worst-case drawdown با اطمینان ۹۵٪ و ۹۹٪
- تخمین احتمال رسیدن به اهداف سود

نسخه: 3.0.0
================================================================================
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import List

from ...core.logger import get_logger
from .engine import BacktestTrade

logger = get_logger("research.backtest.monte_carlo")


@dataclass
class MonteCarloResult:
    """
    نتیجه شبیه‌سازی مونت‌کارلو

    شامل توزیع احتمال نتایج در N بار اجرا است.
    """
    simulations         : int
    # توزیع سود نهایی
    mean_final_return   : float     # میانگین بازده نهایی (درصد)
    median_final_return : float     # میانه بازده نهایی
    std_final_return    : float     # انحراف معیار بازده نهایی
    p5_final_return     : float     # پنجک ۵٪ (بدترین ۵٪)
    p95_final_return    : float     # پنجک ۹۵٪ (بهترین ۵٪)
    # توزیع drawdown
    mean_max_drawdown   : float     # میانگین بیشترین افت
    p95_max_drawdown    : float     # بدترین drawdown با اطمینان ۹۵٪
    p99_max_drawdown    : float     # بدترین drawdown با اطمینان ۹۹٪
    # احتمالات
    prob_profit         : float     # احتمال سودده بودن (۰-۱)
    prob_ruin           : float     # احتمال از دست دادن بیش از ۲۰٪ سرمایه
    # خلاصه برای نمایش
    summary             : str


class MonteCarloSimulator:
    """
    شبیه‌سازگر مونت‌کارلو

    از نتایج واقعی معاملات بک‌تست برای شبیه‌سازی استفاده می‌کند.
    """

    def __init__(self, simulations: int = 1000) -> None:
        """
        پارامترها:
            simulations: تعداد دفعات شبیه‌سازی (پیش‌فرض ۱۰۰۰)
        """
        self.simulations = simulations
        logger.info(f"🎲 Monte Carlo Simulator آماده | {simulations} شبیه‌سازی")

    def run(
        self,
        trades          : List[BacktestTrade],
        initial_balance : float = 10_000.0,
        risk_per_trade  : float = 1.0,
    ) -> MonteCarloResult:
        """
        اجرای شبیه‌سازی مونت‌کارلو

        پارامترها:
            trades: لیست معاملات واقعی از بک‌تست
            initial_balance: موجودی اولیه
            risk_per_trade: درصد ریسک هر معامله

        خروجی:
            MonteCarloResult — نتیجه توزیع احتمال
        """
        if len(trades) < 10:
            logger.warning("⚠️ تعداد معاملات برای مونت‌کارلو کافی نیست (حداقل ۱۰)")
            return self._empty_result()

        # استخراج نرخ سود/ضرر از معاملات واقعی
        pnl_list = [t.pnl_dollar for t in trades]

        final_returns   : List[float] = []
        max_drawdowns   : List[float] = []

        for _ in range(self.simulations):
            # ── شافل تصادفی دنباله معاملات ────────────────────────────────────
            shuffled = random.sample(pnl_list, len(pnl_list))

            balance      = initial_balance
            peak_balance = initial_balance
            max_dd       = 0.0

            for pnl in shuffled:
                # مقیاس‌بندی بر اساس موجودی فعلی (risk% ثابت)
                scale   = balance / initial_balance
                adj_pnl = pnl * scale
                balance = max(0.0, balance + adj_pnl)

                if balance > peak_balance:
                    peak_balance = balance
                dd = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0
                max_dd = max(max_dd, dd)

            final_return = (balance - initial_balance) / initial_balance * 100
            final_returns.append(final_return)
            max_drawdowns.append(max_dd)

        # ── محاسبه آمارها ──────────────────────────────────────────────────────
        final_returns.sort()
        max_drawdowns.sort()
        n = len(final_returns)

        mean_ret    = statistics.mean(final_returns)
        median_ret  = statistics.median(final_returns)
        std_ret     = statistics.stdev(final_returns) if n > 1 else 0.0
        p5_ret      = final_returns[int(n * 0.05)]
        p95_ret     = final_returns[int(n * 0.95)]

        mean_dd     = statistics.mean(max_drawdowns)
        p95_dd      = max_drawdowns[int(n * 0.95)]
        p99_dd      = max_drawdowns[int(n * 0.99)]

        prob_profit = sum(1 for r in final_returns if r > 0) / n
        prob_ruin   = sum(1 for r in final_returns if r < -20) / n

        summary = (
            f"Monte Carlo ({self.simulations} شبیه‌سازی) | "
            f"بازده میانگین: {mean_ret:.1f}٪ | "
            f"MaxDD 95٪: {p95_dd:.1f}٪ | "
            f"احتمال سود: {prob_profit*100:.0f}٪"
        )
        logger.info(f"🎲 {summary}")

        return MonteCarloResult(
            simulations         = self.simulations,
            mean_final_return   = round(mean_ret, 2),
            median_final_return = round(median_ret, 2),
            std_final_return    = round(std_ret, 2),
            p5_final_return     = round(p5_ret, 2),
            p95_final_return    = round(p95_ret, 2),
            mean_max_drawdown   = round(mean_dd, 2),
            p95_max_drawdown    = round(p95_dd, 2),
            p99_max_drawdown    = round(p99_dd, 2),
            prob_profit         = round(prob_profit, 4),
            prob_ruin           = round(prob_ruin, 4),
            summary             = summary,
        )

    def _empty_result(self) -> MonteCarloResult:
        """نتیجه خالی برای حالت خطا"""
        return MonteCarloResult(
            simulations=0, mean_final_return=0, median_final_return=0,
            std_final_return=0, p5_final_return=0, p95_final_return=0,
            mean_max_drawdown=0, p95_max_drawdown=0, p99_max_drawdown=0,
            prob_profit=0, prob_ruin=0,
            summary="داده کافی برای شبیه‌سازی وجود ندارد",
        )


# ─── نمونه singleton ──────────────────────────────────────────────────────────
monte_carlo_simulator = MonteCarloSimulator(simulations=1000)
