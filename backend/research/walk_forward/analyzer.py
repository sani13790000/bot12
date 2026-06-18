"""
================================================================================
Galaxy Vast AI Trading Platform
تحلیل Walk-Forward حرفه‌ای — Professional Walk-Forward Analyzer

این ماژول از overfitting جلوگیری می‌کند با تقسیم داده به سه بخش:
- Training: آموزش و بهینه‌سازی استراتژی
- Validation: اعتبارسنجی پارامترهای بهینه‌شده
- Testing: تست نهایی روی داده‌های دست‌نخورده

پنجره‌های rolling امکان آزمایش در شرایط مختلف بازار را می‌دهد.

نسخه: 3.0.0
================================================================================
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import get_logger
from ..backtest.engine import BacktestEngine, BacktestConfig, BacktestResult

logger = get_logger("research.walk_forward.analyzer")


@dataclass
class WalkForwardConfig:
    """
    تنظیمات تحلیل Walk-Forward

    نسبت‌های پیش‌فرض:
    - Training: ۶۰٪ داده
    - Validation: ۲۰٪ داده
    - Testing: ۲۰٪ داده
    """
    symbol              : str
    start_date          : datetime
    end_date            : datetime
    initial_balance     : float = 10_000.0
    risk_per_trade_pct  : float = 1.0
    min_confidence      : float = 80.0
    # نسبت‌های تقسیم داده
    train_ratio         : float = 0.60    # ۶۰٪ برای آموزش
    validation_ratio    : float = 0.20    # ۲۰٪ برای اعتبارسنجی
    test_ratio          : float = 0.20    # ۲۰٪ برای تست
    # تنظیمات پنجره rolling
    use_rolling_windows : bool  = True
    window_count        : int   = 5       # تعداد پنجره‌ها
    # تنظیمات بک‌تست
    backtest_timeframe  : int   = 60      # دقیقه
    pip_size            : float = 0.0001
    pip_value           : float = 10.0
    commission_per_lot  : float = 7.0


@dataclass
class WindowResult:
    """نتیجه یک پنجره Walk-Forward"""
    window_id          : int
    train_start        : datetime
    train_end          : datetime
    validation_start   : datetime
    validation_end     : datetime
    test_start         : datetime
    test_end           : datetime
    train_result       : Optional[BacktestResult]
    validation_result  : Optional[BacktestResult]
    test_result        : Optional[BacktestResult]
    # معیارهای کلیدی تست
    test_profit_pct    : float = 0.0
    test_win_rate      : float = 0.0
    test_profit_factor : float = 0.0
    test_max_drawdown  : float = 0.0
    passed             : bool  = False   # آیا معیارهای کیفیت را برآورد کرده؟


@dataclass
class WalkForwardResult:
    """
    نتیجه کامل تحلیل Walk-Forward

    شامل نتایج تمام پنجره‌ها و خلاصه آماری است.
    """
    config              : WalkForwardConfig
    windows             : List[WindowResult]
    # معیارهای تجمیعی
    avg_test_profit     : float    # میانگین سود تست در همه پنجره‌ها
    avg_win_rate        : float    # میانگین win rate
    avg_profit_factor   : float    # میانگین profit factor
    avg_max_drawdown    : float    # میانگین drawdown
    consistency_score   : float    # ۰-۱۰۰ — ثبات عملکرد در پنجره‌های مختلف
    pass_rate           : float    # درصد پنجره‌هایی که معیار کیفیت را برآورد کردند
    recommendation      : str      # توصیه نهایی: ROBUST / ACCEPTABLE / OVERFITTED
    summary             : str

    def to_dict(self) -> Dict:
        return {
            "windows_count"      : len(self.windows),
            "avg_test_profit"    : round(self.avg_test_profit, 2),
            "avg_win_rate"       : round(self.avg_win_rate * 100, 2),
            "avg_profit_factor"  : round(self.avg_profit_factor, 2),
            "avg_max_drawdown"   : round(self.avg_max_drawdown, 2),
            "consistency_score"  : round(self.consistency_score, 1),
            "pass_rate"          : round(self.pass_rate * 100, 1),
            "recommendation"     : self.recommendation,
            "summary"            : self.summary,
            "windows"            : [
                {
                    "id"                : w.window_id,
                    "test_start"        : w.test_start.isoformat(),
                    "test_end"          : w.test_end.isoformat(),
                    "test_profit_pct"   : round(w.test_profit_pct, 2),
                    "test_win_rate"     : round(w.test_win_rate * 100, 2),
                    "test_profit_factor": round(w.test_profit_factor, 2),
                    "test_max_drawdown" : round(w.test_max_drawdown, 2),
                    "passed"            : w.passed,
                }
                for w in self.windows
            ],
        }


class WalkForwardAnalyzer:
    """
    تحلیلگر Walk-Forward Galaxy Vast

    با اجرای بک‌تست روی پنجره‌های زمانی مجزا،
    overfitting را شناسایی می‌کند و استحکام استراتژی را اندازه می‌گیرد.
    """

    def __init__(self) -> None:
        """مقداردهی اولیه تحلیلگر"""
        self._backtest_engine = BacktestEngine()
        logger.info("🔬 Galaxy Vast Walk-Forward Analyzer آماده شد")

    async def analyze(
        self,
        config           : WalkForwardConfig,
        candles          : List[Any],
        signal_generator : Any,
    ) -> WalkForwardResult:
        """
        اجرای تحلیل Walk-Forward

        پارامترها:
            config: تنظیمات تحلیل
            candles: لیست کامل کندل‌ها
            signal_generator: تابع تولید سیگنال

        خروجی:
            WalkForwardResult — نتیجه کامل با توصیه
        """
        logger.info(
            f"🔬 شروع Walk-Forward | نماد: {config.symbol} | "
            f"پنجره‌ها: {config.window_count if config.use_rolling_windows else 1}"
        )

        # ── فیلتر کندل‌ها ─────────────────────────────────────────────────────
        candles_filtered = [
            c for c in candles
            if config.start_date <= c.timestamp <= config.end_date
        ]

        if len(candles_filtered) < 200:
            logger.warning("⚠️ داده کافی برای Walk-Forward (حداقل ۲۰۰ کندل)")
            return self._empty_result(config)

        # ── ساخت پنجره‌ها ─────────────────────────────────────────────────────
        windows_data = self._build_windows(candles_filtered, config)

        # ── اجرای بک‌تست برای هر پنجره ──────────────────────────────────────
        window_results: List[WindowResult] = []

        for idx, (train_c, val_c, test_c, dates) in enumerate(windows_data):
            logger.info(f"  پنجره {idx+1}/{len(windows_data)} ...")

            bt_config_base = BacktestConfig(
                symbol             = config.symbol,
                start_date         = dates["train_start"],
                end_date           = dates["train_end"],
                initial_balance    = config.initial_balance,
                risk_per_trade_pct = config.risk_per_trade_pct,
                min_confidence     = config.min_confidence,
                pip_size           = config.pip_size,
                pip_value          = config.pip_value,
                commission_per_lot = config.commission_per_lot,
            )

            # Training
            train_cfg    = self._make_config(bt_config_base, dates["train_start"], dates["train_end"])
            train_result = await self._backtest_engine.run(train_cfg, train_c, signal_generator)

            # Validation
            val_cfg      = self._make_config(bt_config_base, dates["val_start"], dates["val_end"])
            val_result   = await self._backtest_engine.run(val_cfg, val_c, signal_generator)

            # Test
            test_cfg     = self._make_config(bt_config_base, dates["test_start"], dates["test_end"])
            test_result  = await self._backtest_engine.run(test_cfg, test_c, signal_generator)

            # ── بررسی معیار کیفیت ─────────────────────────────────────────────
            passed = (
                test_result.profit_factor >= 1.2
                and test_result.win_rate >= 0.45
                and test_result.max_drawdown <= 15.0
            )

            window_results.append(WindowResult(
                window_id          = idx + 1,
                train_start        = dates["train_start"],
                train_end          = dates["train_end"],
                validation_start   = dates["val_start"],
                validation_end     = dates["val_end"],
                test_start         = dates["test_start"],
                test_end           = dates["test_end"],
                train_result       = train_result,
                validation_result  = val_result,
                test_result        = test_result,
                test_profit_pct    = test_result.net_profit_pct,
                test_win_rate      = test_result.win_rate,
                test_profit_factor = test_result.profit_factor,
                test_max_drawdown  = test_result.max_drawdown,
                passed             = passed,
            ))

        return self._aggregate_results(config, window_results)

    def _build_windows(
        self,
        candles: List[Any],
        config : WalkForwardConfig,
    ) -> List[Tuple]:
        """
        ساخت پنجره‌های rolling برای Walk-Forward

        هر پنجره شامل سه بخش train/validation/test است.
        """
        n          = len(candles)
        windows    = []
        count      = config.window_count if config.use_rolling_windows else 1
        step_size  = n // (count + 1)

        for i in range(count):
            start_idx  = i * step_size
            end_idx    = start_idx + step_size * 2
            end_idx    = min(end_idx, n - 1)
            window_len = end_idx - start_idx

            t_end  = start_idx + int(window_len * config.train_ratio)
            v_end  = t_end + int(window_len * config.validation_ratio)
            te_end = min(v_end + int(window_len * config.test_ratio), n - 1)

            train_c = candles[start_idx : t_end]
            val_c   = candles[t_end      : v_end]
            test_c  = candles[v_end      : te_end]

            if len(train_c) < 50 or len(test_c) < 20:
                continue

            dates = {
                "train_start": candles[start_idx].timestamp,
                "train_end"  : candles[t_end - 1].timestamp,
                "val_start"  : candles[t_end].timestamp,
                "val_end"    : candles[v_end - 1].timestamp,
                "test_start" : candles[v_end].timestamp,
                "test_end"   : candles[te_end - 1].timestamp,
            }
            windows.append((train_c, val_c, test_c, dates))

        return windows

    def _make_config(
        self,
        base      : BacktestConfig,
        start_date: datetime,
        end_date  : datetime,
    ) -> BacktestConfig:
        """ساخت BacktestConfig برای یک پنجره"""
        from dataclasses import replace
        return BacktestConfig(
            symbol             = base.symbol,
            start_date         = start_date,
            end_date           = end_date,
            initial_balance    = base.initial_balance,
            risk_per_trade_pct = base.risk_per_trade_pct,
            min_confidence     = base.min_confidence,
            pip_size           = base.pip_size,
            pip_value          = base.pip_value,
            commission_per_lot = base.commission_per_lot,
        )

    def _aggregate_results(
        self,
        config : WalkForwardConfig,
        windows: List[WindowResult],
    ) -> WalkForwardResult:
        """
        تجمیع نتایج تمام پنجره‌ها و محاسبه توصیه نهایی
        """
        if not windows:
            return self._empty_result(config)

        profits  = [w.test_profit_pct    for w in windows]
        wr       = [w.test_win_rate      for w in windows]
        pf       = [w.test_profit_factor for w in windows]
        dd       = [w.test_max_drawdown  for w in windows]
        passed   = [w.passed             for w in windows]

        avg_profit = statistics.mean(profits)
        avg_wr     = statistics.mean(wr)
        avg_pf     = statistics.mean(pf)
        avg_dd     = statistics.mean(dd)
        pass_rate  = sum(passed) / len(passed)

        # ── محاسبه consistency score ─────────────────────────────────────────
        # بر اساس انحراف معیار نتایج — هر چه کمتر، ثبات بیشتر
        if len(profits) > 1:
            std_profit = statistics.stdev(profits)
            consistency = max(0, 100 - std_profit * 5)
        else:
            consistency = 50.0

        # ── توصیه نهایی ──────────────────────────────────────────────────────
        if pass_rate >= 0.8 and avg_pf >= 1.5 and consistency >= 70:
            recommendation = "ROBUST"
            rec_fa = "✅ استراتژی قوی و قابل اعتماد — آماده معامله واقعی"
        elif pass_rate >= 0.6 and avg_pf >= 1.2:
            recommendation = "ACCEPTABLE"
            rec_fa = "⚠️ استراتژی قابل قبول — نیاز به بهینه‌سازی بیشتر"
        else:
            recommendation = "OVERFITTED"
            rec_fa = "❌ استراتژی احتمالاً بیش از حد بهینه‌شده — توصیه نمی‌شود"

        summary = (
            f"Walk-Forward ({len(windows)} پنجره) | "
            f"سود میانگین: {avg_profit:.1f}٪ | "
            f"PF: {avg_pf:.2f} | "
            f"Pass Rate: {pass_rate*100:.0f}٪ | "
            f"{rec_fa}"
        )

        logger.info(f"🔬 {summary}")

        return WalkForwardResult(
            config             = config,
            windows            = windows,
            avg_test_profit    = round(avg_profit, 2),
            avg_win_rate       = round(avg_wr, 4),
            avg_profit_factor  = round(avg_pf, 2),
            avg_max_drawdown   = round(avg_dd, 2),
            consistency_score  = round(consistency, 1),
            pass_rate          = round(pass_rate, 4),
            recommendation     = recommendation,
            summary            = summary,
        )

    def _empty_result(self, config: WalkForwardConfig) -> WalkForwardResult:
        """نتیجه خالی برای حالت خطا"""
        return WalkForwardResult(
            config             = config,
            windows            = [],
            avg_test_profit    = 0.0,
            avg_win_rate       = 0.0,
            avg_profit_factor  = 0.0,
            avg_max_drawdown   = 0.0,
            consistency_score  = 0.0,
            pass_rate          = 0.0,
            recommendation     = "INSUFFICIENT_DATA",
            summary            = "داده کافی برای تحلیل وجود ندارد",
        )


# ─── نمونه singleton ──────────────────────────────────────────────────────────
walk_forward_analyzer = WalkForwardAnalyzer()
