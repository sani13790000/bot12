"""
================================================================================
Galaxy Vast AI Trading Platform
آنالیز Walk-Forward — Walk-Forward Analyzer
================================================================================
این ماژول آنالیز Walk-Forward را برای ارزیابی واقعی استراتژی پیاده‌سازی می‌کند.

Walk-Forward چیست؟
  به جای یک بک‌تست کلی، داده‌ها به پنجره‌های زمانی تقسیم می‌شوند.
  هر پنجره شامل:
    - Training: بهینه‌سازی پارامترها
    - Validation: تست در‌جا
    - Testing: ارزیابی واقعی

  این روش از Overfitting جلوگیری می‌کند.

نویسنده: Galaxy Vast AI Engine
================================================================================
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import get_logger
from ..backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestMetrics,
    CandleData,
)

logger = get_logger("research.walk_forward.analyzer")


@dataclass
class WalkForwardConfig:
    """
    تنظیمات Walk-Forward Analysis

    پنجره‌های زمانی را و نحوه تقسیم داده‌ها تعریف می‌کند.
    """
    symbol: str = "XAUUSD"
    total_start: Optional[datetime] = None
    total_end: Optional[datetime] = None

    # ─── اندازه پنجره‌ها ───
    training_days: int = 90     # دوره آموزش: ۳ ماه
    validation_days: int = 30   # دوره اعتبارسنجی: ۱ ماه
    testing_days: int = 30      # دوره تست: ۱ ماه

    # ─── rolling window ───
    step_days: int = 30         # هر بار چقدر جلو برود

    # ─── تنظیمات بک‌تست ───
    initial_balance: float = 10000.0
    risk_per_trade: float = 1.0
    min_confidence: float = 70.0


@dataclass
class WindowResult:
    """
    نتیجه یک پنجره Walk-Forward

    شامل عملکرد در سه مرحله Training، Validation و Testing.
    """
    window_index: int
    training_start: datetime
    training_end: datetime
    validation_start: datetime
    validation_end: datetime
    testing_start: datetime
    testing_end: datetime

    training_metrics: Optional[BacktestMetrics] = None
    validation_metrics: Optional[BacktestMetrics] = None
    testing_metrics: Optional[BacktestMetrics] = None

    # آیا این پنجره قبول است؟ (اگر validation خوب بود)
    passed: bool = False
    pass_reason: str = ""
    fail_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary"""
        return {
            "window": self.window_index,
            "training": {
                "start": self.training_start.isoformat(),
                "end": self.training_end.isoformat(),
                "metrics": self.training_metrics.to_dict() if self.training_metrics else None,
            },
            "validation": {
                "start": self.validation_start.isoformat(),
                "end": self.validation_end.isoformat(),
                "metrics": self.validation_metrics.to_dict() if self.validation_metrics else None,
            },
            "testing": {
                "start": self.testing_start.isoformat(),
                "end": self.testing_end.isoformat(),
                "metrics": self.testing_metrics.to_dict() if self.testing_metrics else None,
            },
            "passed": self.passed,
            "reason": self.pass_reason if self.passed else self.fail_reason,
        }


@dataclass
class WalkForwardResult:
    """
    نتیجه کامل Walk-Forward Analysis

    خلاصه عملکرد در تمام پنجره‌های زمانی.
    """
    config: WalkForwardConfig
    windows: List[WindowResult]

    # ─── آمار کلی ───
    total_windows: int = 0
    passed_windows: int = 0
    failed_windows: int = 0

    # ─── میانگین‌های testing ───
    avg_win_rate: float = 0.0
    avg_profit_factor: float = 0.0
    avg_sharpe_ratio: float = 0.0
    avg_max_drawdown: float = 0.0
    avg_return: float = 0.0

    # ─── ثبات استراتژی ───
    consistency_score: float = 0.0   # ۰ تا ۱۰۰ — هر چه بالاتر بهتر
    is_robust: bool = False          # آیا استراتژی robust است؟
    robustness_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary"""
        return {
            "summary": {
                "total_windows": self.total_windows,
                "passed_windows": self.passed_windows,
                "failed_windows": self.failed_windows,
                "pass_rate": round(
                    (self.passed_windows / self.total_windows * 100)
                    if self.total_windows > 0 else 0, 1
                ),
            },
            "performance": {
                "avg_win_rate": round(self.avg_win_rate, 1),
                "avg_profit_factor": round(self.avg_profit_factor, 2),
                "avg_sharpe_ratio": round(self.avg_sharpe_ratio, 3),
                "avg_max_drawdown": round(self.avg_max_drawdown, 1),
                "avg_return": round(self.avg_return, 2),
            },
            "robustness": {
                "score": round(self.consistency_score, 1),
                "is_robust": self.is_robust,
                "notes": self.robustness_notes,
            },
            "windows": [w.to_dict() for w in self.windows],
        }


class WalkForwardAnalyzer:
    """
    آنالیزگر Walk-Forward Galaxy Vast

    این کلاس استراتژی را در شرایط واقعی و بدون Overfitting ارزیابی می‌کند.
    با تقسیم داده‌ها به پنجره‌های rolling، اطمینان می‌دهد که
    نتایج training و testing با هم فاصله مناسبی دارند.

    نحوه استفاده:
        analyzer = WalkForwardAnalyzer()
        config = WalkForwardConfig(symbol="XAUUSD", training_days=90)
        result = await analyzer.run(candles, config)
    """

    def __init__(self) -> None:
        """مقداردهی اولیه"""
        self._backtest_engine = BacktestEngine()
        logger.info("Walk-Forward Analyzer راه‌اندازی شد")

    async def run(
        self,
        candles: List[CandleData],
        config: WalkForwardConfig,
        signal_generator: Optional[Any] = None,
    ) -> WalkForwardResult:
        """
        اجرای کامل Walk-Forward Analysis

        Args:
            candles: تمام داده‌های تاریخی
            config: تنظیمات
            signal_generator: موتور تولید سیگنال

        Returns:
            WalkForwardResult: نتیجه کامل
        """
        if not candles:
            raise ValueError("داده‌ای برای Walk-Forward وجود ندارد")

        start = config.total_start or candles[0].timestamp
        end = config.total_end or candles[-1].timestamp

        logger.info(
            f"Walk-Forward شروع شد | {config.symbol} | "
            f"از: {start.date()} تا: {end.date()}"
        )

        # ─── ساخت پنجره‌ها ───
        windows_config = self._build_windows(start, end, config)

        if not windows_config:
            raise ValueError("داده کافی برای حتی یک پنجره وجود ندارد")

        logger.info(f"تعداد پنجره‌ها: {len(windows_config)}")

        # ─── اجرای بک‌تست برای هر پنجره ───
        window_results: List[WindowResult] = []

        for idx, win_cfg in enumerate(windows_config):
            logger.info(
                f"پنجره {idx + 1}/{len(windows_config)} | "
                f"Training: {win_cfg['training_start'].date()} - "
                f"{win_cfg['training_end'].date()}"
            )

            win_result = await self._run_window(
                idx, win_cfg, candles, config, signal_generator
            )
            window_results.append(win_result)
            await asyncio.sleep(0)

        # ─── محاسبه آمار کلی ───
        result = self._calculate_overall(window_results, config)

        logger.info(
            f"Walk-Forward کامل | "
            f"پنجره‌ها: {result.total_windows} | "
            f"قبول: {result.passed_windows} | "
            f"Consistency: {result.consistency_score:.1f}"
        )

        return result

    def _build_windows(
        self,
        start: datetime,
        end: datetime,
        config: WalkForwardConfig,
    ) -> List[Dict[str, datetime]]:
        """
        ساخت پنجره‌های زمانی Rolling

        هر پنجره به سه بخش تقسیم می‌شود:
          Training → Validation → Testing
        """
        windows = []
        window_start = start
        total_days = (config.training_days + config.validation_days + config.testing_days)

        while True:
            train_start = window_start
            train_end = train_start + timedelta(days=config.training_days)
            val_start = train_end
            val_end = val_start + timedelta(days=config.validation_days)
            test_start = val_end
            test_end = test_start + timedelta(days=config.testing_days)

            if test_end > end:
                break

            windows.append({
                "training_start": train_start,
                "training_end": train_end,
                "validation_start": val_start,
                "validation_end": val_end,
                "testing_start": test_start,
                "testing_end": test_end,
            })

            window_start += timedelta(days=config.step_days)

        return windows

    def _filter_candles(
        self,
        candles: List[CandleData],
        start: datetime,
        end: datetime,
    ) -> List[CandleData]:
        """فیلتر کندل‌ها بر اساس بازه زمانی"""
        return [c for c in candles if start <= c.timestamp < end]

    async def _run_window(
        self,
        idx: int,
        win_cfg: Dict[str, datetime],
        all_candles: List[CandleData],
        config: WalkForwardConfig,
        signal_generator: Optional[Any],
    ) -> WindowResult:
        """
        اجرای بک‌تست برای یک پنجره

        هر سه مرحله Training، Validation و Testing را جداگانه اجرا می‌کند.
        """
        window = WindowResult(
            window_index=idx,
            training_start=win_cfg["training_start"],
            training_end=win_cfg["training_end"],
            validation_start=win_cfg["validation_start"],
            validation_end=win_cfg["validation_end"],
            testing_start=win_cfg["testing_start"],
            testing_end=win_cfg["testing_end"],
        )

        base_config = BacktestConfig(
            symbol=config.symbol,
            initial_balance=config.initial_balance,
            risk_per_trade_percent=config.risk_per_trade,
            min_confidence_score=config.min_confidence,
            start_date=datetime.min,
            end_date=datetime.max,
        )

        # ─── Training ───
        try:
            train_candles = self._filter_candles(
                all_candles, win_cfg["training_start"], win_cfg["training_end"]
            )
            if len(train_candles) >= 50:
                base_config.start_date = win_cfg["training_start"]
                base_config.end_date = win_cfg["training_end"]
                train_result = await self._backtest_engine.run(
                    train_candles, base_config, signal_generator
                )
                window.training_metrics = train_result.metrics
        except Exception as e:
            logger.warning(f"خطا در Training پنجره {idx}: {e}")

        # ─── Validation ───
        try:
            val_candles = self._filter_candles(
                all_candles, win_cfg["validation_start"], win_cfg["validation_end"]
            )
            if len(val_candles) >= 20:
                base_config.start_date = win_cfg["validation_start"]
                base_config.end_date = win_cfg["validation_end"]
                val_result = await self._backtest_engine.run(
                    val_candles, base_config, signal_generator
                )
                window.validation_metrics = val_result.metrics
        except Exception as e:
            logger.warning(f"خطا در Validation پنجره {idx}: {e}")

        # ─── Testing ───
        try:
            test_candles = self._filter_candles(
                all_candles, win_cfg["testing_start"], win_cfg["testing_end"]
            )
            if len(test_candles) >= 20:
                base_config.start_date = win_cfg["testing_start"]
                base_config.end_date = win_cfg["testing_end"]
                test_result = await self._backtest_engine.run(
                    test_candles, base_config, signal_generator
                )
                window.testing_metrics = test_result.metrics
        except Exception as e:
            logger.warning(f"خطا در Testing پنجره {idx}: {e}")

        # ─── قضاوت پنجره ───
        window.passed, window.pass_reason, window.fail_reason = (
            self._evaluate_window(window)
        )

        return window

    def _evaluate_window(self, window: WindowResult) -> Tuple[bool, str, str]:
        """
        ارزیابی یک پنجره

        پنجره قبول است اگر:
          - Validation profit factor > 1.2
          - Testing profit factor > 1.0
          - Max drawdown در testing < 20%

        Returns:
            Tuple[bool, str, str]: (قبول شد، دلیل قبول، دلیل رد)
        """
        if not window.validation_metrics or not window.testing_metrics:
            return False, "", "داده کافی وجود ندارد"

        vm = window.validation_metrics
        tm = window.testing_metrics

        # ─── بررسی Validation ───
        if vm.profit_factor < 1.2:
            return False, "", f"Validation PF ضعیف: {vm.profit_factor:.2f}"

        if vm.total_trades < 3:
            return False, "", "تعداد معاملات Validation کم است"

        # ─── بررسی Testing ───
        if tm.profit_factor < 1.0:
            return False, "", f"Testing PF منفی: {tm.profit_factor:.2f}"

        if tm.max_drawdown_percent > 20.0:
            return False, "", f"Testing Drawdown بالا: {tm.max_drawdown_percent:.1f}%"

        reason = (
            f"Val PF={vm.profit_factor:.2f}, "
            f"Test PF={tm.profit_factor:.2f}, "
            f"Test WR={tm.win_rate:.1f}%"
        )
        return True, reason, ""

    def _calculate_overall(
        self,
        windows: List[WindowResult],
        config: WalkForwardConfig,
    ) -> WalkForwardResult:
        """
        محاسبه آمار کلی از تمام پنجره‌ها

        معیار Consistency بر اساس ثبات نتایج در پنجره‌های مختلف محاسبه می‌شود.
        """
        result = WalkForwardResult(config=config, windows=windows)
        result.total_windows = len(windows)
        result.passed_windows = sum(1 for w in windows if w.passed)
        result.failed_windows = result.total_windows - result.passed_windows

        # ─── میانگین‌های testing ───
        test_metrics = [w.testing_metrics for w in windows if w.testing_metrics]
        if test_metrics:
            result.avg_win_rate = sum(m.win_rate for m in test_metrics) / len(test_metrics)
            result.avg_profit_factor = sum(m.profit_factor for m in test_metrics) / len(test_metrics)
            result.avg_sharpe_ratio = sum(m.sharpe_ratio for m in test_metrics) / len(test_metrics)
            result.avg_max_drawdown = sum(m.max_drawdown_percent for m in test_metrics) / len(test_metrics)
            result.avg_return = sum(m.return_percent for m in test_metrics) / len(test_metrics)

        # ─── Consistency Score (0-100) ───
        if result.total_windows > 0:
            pass_rate = result.passed_windows / result.total_windows

            # ثبات Profit Factor در بین پنجره‌ها
            pf_values = [m.profit_factor for m in test_metrics if m and m.total_trades > 0]
            if len(pf_values) > 1:
                pf_mean = sum(pf_values) / len(pf_values)
                pf_var = sum((v - pf_mean) ** 2 for v in pf_values) / len(pf_values)
                pf_std = math.sqrt(pf_var)
                pf_cv = pf_std / pf_mean if pf_mean > 0 else 1.0  # Coefficient of Variation
                stability_score = max(0, 1 - pf_cv)  # ۱ = کاملاً ثابت
            else:
                stability_score = 0.5

            result.consistency_score = (pass_rate * 0.6 + stability_score * 0.4) * 100

        # ─── تعیین Robust بودن ───
        notes = []
        if result.total_windows >= 3 and result.passed_windows / result.total_windows >= 0.6:
            result.is_robust = True
            notes.append("✅ بیش از ۶۰٪ پنجره‌ها قبول شدند")
        else:
            result.is_robust = False
            notes.append("⚠️ کمتر از ۶۰٪ پنجره‌ها قبول شدند")

        if result.avg_profit_factor >= 1.5:
            notes.append("✅ Profit Factor میانگین مناسب است")
        elif result.avg_profit_factor >= 1.2:
            notes.append("⚠️ Profit Factor میانگین قابل قبول است")
        else:
            notes.append("❌ Profit Factor میانگین ضعیف است")

        if result.avg_max_drawdown <= 15:
            notes.append("✅ Drawdown میانگین در محدوده امن است")
        elif result.avg_max_drawdown <= 25:
            notes.append("⚠️ Drawdown میانگین قابل توجه است")
        else:
            notes.append("❌ Drawdown میانگین بالا است")

        result.robustness_notes = notes
        return result
