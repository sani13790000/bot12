"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: LearningService — سرویس یادگیری مرکزی

این سرویس همه اجزای یادگیری را به هم متصل می‌کند:
  ① بعد از هر معامله: ذخیره در TradeMemory
  ② بعد از هر ۵۰ معامله: Failure Analysis
  ③ بعد از هر ۱۰۰ معامله: بازآموزی ML
  ④ بعد از هر ۲۰۰ معامله: تنظیم وزن‌ها
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .trade_memory import TradeMemory, TradeContext, TradeOutcome
from .failure_analyzer import FailureAnalyzer, FailureReport
from .ml_engine import MLEngine, MLPrediction
from .weight_adjuster import WeightAdjuster, WeightUpdate, IndicatorWeights
from ..core.logger import get_logger

logger = get_logger("intelligence.learning_service")


@dataclass
class LearningCycleResult:
    """نتیجه یک چرخه یادگیری"""
    timestamp: datetime
    trades_analyzed: int
    failure_reports: int
    valid_losses: int
    rule_violations: int
    ml_retrained: bool
    weights_adjusted: bool
    weight_updates: List[WeightUpdate]
    top_violation_types: List[str]
    summary: str


class LearningService:
    """
    سرویس یادگیری مرکزی Galaxy Vast.

    این سرویس orchestrator کل pipeline یادگیری است.
    """

    # هر چند معامله یک بار Failure Analysis اجرا شود
    FAILURE_ANALYSIS_INTERVAL = 50

    # هر چند معامله یک بار ML بازآموزی شود
    ML_RETRAIN_INTERVAL = 100

    # هر چند معامله یک بار وزن‌ها تنظیم شوند
    WEIGHT_ADJUST_INTERVAL = 200

    def __init__(
        self,
        model_dir: str = "models",
        on_weights_updated: Optional[Callable[[IndicatorWeights], None]] = None,
    ) -> None:
        """
        Args:
            model_dir: مسیر ذخیره مدل‌ها
            on_weights_updated: callback وقتی وزن‌ها تغییر کردند
        """
        self._memory = TradeMemory(max_memory=10_000)
        self._failure_analyzer = FailureAnalyzer()
        self._ml_engine = MLEngine(model_dir=f"{model_dir}/ml")
        self._weight_adjuster = WeightAdjuster(weights_path=f"{model_dir}/weights.json")
        self._on_weights_updated = on_weights_updated
        self._trade_counter = 0

        # بارگذاری مدل‌های ذخیره‌شده
        if self._ml_engine.load_models():
            logger.info("مدل‌های ML از فایل بارگذاری شدند")

        logger.info("LearningService راه‌اندازی شد")

    async def record_trade(self, context: TradeContext) -> Optional[FailureReport]:
        """
        ثبت یک معامله و اجرای چرخه یادگیری در صورت نیاز.

        Args:
            context: context کامل معامله

        Returns:
            FailureReport اگر معامله زیان‌ده بود
        """
        # ثبت در حافظه
        self._memory.record(context)
        self._trade_counter += 1

        failure_report = None

        # تحلیل شکست برای معاملات زیان‌ده
        if context.outcome == TradeOutcome.LOSS:
            failure_report = self._failure_analyzer.analyze(context)

        # چرخه Failure Analysis جمعی
        if self._trade_counter % self.FAILURE_ANALYSIS_INTERVAL == 0:
            asyncio.create_task(self._run_failure_analysis_cycle())

        # چرخه بازآموزی ML
        if self._trade_counter % self.ML_RETRAIN_INTERVAL == 0:
            asyncio.create_task(self._run_ml_training_cycle())

        # چرخه تنظیم وزن
        if self._trade_counter % self.WEIGHT_ADJUST_INTERVAL == 0:
            asyncio.create_task(self._run_weight_adjustment_cycle())

        return failure_report

    async def predict_signal_quality(
        self, features: Dict[str, float]
    ) -> MLPrediction:
        """
        پیش‌بینی کیفیت یک سیگنال با ML.

        Args:
            features: feature vector از TradeContext.to_ml_features()

        Returns:
            MLPrediction با احتمال موفقیت
        """
        return self._ml_engine.predict(features)

    def get_current_weights(self) -> IndicatorWeights:
        """وزن‌های فعلی Decision Engine"""
        return self._weight_adjuster.current_weights

    def get_memory_stats(self) -> Dict[str, Any]:
        """آمار حافظه معاملاتی"""
        return self._memory.get_stats()

    async def run_full_learning_cycle(self) -> LearningCycleResult:
        """
        اجرای چرخه کامل یادگیری دستی.
        برای trigger کردن از dashboard یا telegram.
        """
        logger.info("چرخه کامل یادگیری شروع شد")
        start = datetime.utcnow()

        # Failure Analysis
        losing_trades = self._memory.get_by_outcome(TradeOutcome.LOSS)
        reports = self._failure_analyzer.analyze_batch(losing_trades)
        valid_losses = sum(1 for r in reports if r.is_valid_loss)
        rule_violations = sum(1 for r in reports if not r.is_valid_loss)

        # فراوانی نقض‌ها
        freq = self._failure_analyzer.get_violation_frequency(reports)
        top_violations = sorted(freq, key=freq.get, reverse=True)[:3]

        # بازآموزی ML
        ml_results = self._ml_engine.train(self._memory)
        ml_retrained = len(ml_results) > 0
        if ml_retrained:
            self._ml_engine.save_models()

        # تنظیم وزن‌ها
        suggestions = self._weight_adjuster.analyze_and_suggest(
            self._memory, self._ml_engine
        )
        new_weights = self._weight_adjuster.apply_updates(suggestions)
        weights_adjusted = any(u.applied for u in suggestions)

        if weights_adjusted and self._on_weights_updated:
            self._on_weights_updated(new_weights)

        result = LearningCycleResult(
            timestamp=start,
            trades_analyzed=len(self._memory.get_all()),
            failure_reports=len(reports),
            valid_losses=valid_losses,
            rule_violations=rule_violations,
            ml_retrained=ml_retrained,
            weights_adjusted=weights_adjusted,
            weight_updates=[u for u in suggestions if u.applied],
            top_violation_types=[v.value for v in top_violations],
            summary=(
                f"{len(reports)} معامله تحلیل شد | "
                f"{valid_losses} زیان معتبر | "
                f"{rule_violations} نقض قوانین | "
                f"ML: {'✅' if ml_retrained else '⏸'} | "
                f"وزن‌ها: {'✅' if weights_adjusted else '⏸'}"
            ),
        )

        logger.info(f"چرخه یادگیری کامل شد: {result.summary}")
        return result

    # ─── متدهای خصوصی ───────────────────────────────────────────

    async def _run_failure_analysis_cycle(self) -> None:
        """اجرای Failure Analysis روی معاملات اخیر"""
        try:
            recent = self._memory.get_recent(self.FAILURE_ANALYSIS_INTERVAL)
            losing = [t for t in recent if t.outcome == TradeOutcome.LOSS]
            if losing:
                reports = self._failure_analyzer.analyze_batch(losing)
                violations = sum(1 for r in reports if not r.is_valid_loss)
                logger.info(
                    f"Failure Analysis | {len(losing)} زیان | "
                    f"{violations} نقض قوانین"
                )
        except Exception as e:
            logger.error(f"خطا در Failure Analysis cycle: {e}")

    async def _run_ml_training_cycle(self) -> None:
        """بازآموزی مدل‌های ML"""
        try:
            results = self._ml_engine.train(self._memory)
            if results:
                self._ml_engine.save_models()
                best = max(results, key=lambda mt: results[mt].auc_roc)
                logger.info(
                    f"ML بازآموزی شد | بهترین: {best.value} | "
                    f"AUC: {results[best].auc_roc:.3f}"
                )
        except Exception as e:
            logger.error(f"خطا در ML training cycle: {e}")

    async def _run_weight_adjustment_cycle(self) -> None:
        """تنظیم وزن‌های Decision Engine"""
        try:
            suggestions = self._weight_adjuster.analyze_and_suggest(
                self._memory, self._ml_engine
            )
            if suggestions:
                new_weights = self._weight_adjuster.apply_updates(suggestions)
                applied = [u for u in suggestions if u.applied]
                if applied and self._on_weights_updated:
                    self._on_weights_updated(new_weights)
                logger.info(
                    f"وزن‌ها تنظیم شدند | {len(applied)} تغییر اعمال شد"
                )
        except Exception as e:
            logger.error(f"خطا در weight adjustment cycle: {e}")
