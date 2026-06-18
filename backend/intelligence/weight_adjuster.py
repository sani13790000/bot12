"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: WeightAdjuster — تنظیم وزن اندیکاتورها

قوانین سخت:
  ① هیچ استراتژی به طور کامل حذف نمی‌شود
  ② تنظیمات فقط بر اساس آمار قابل اطمینان
  ③ حداکثر تغییر وزن در هر چرخه: ±0.05
  ④ حداقل وزن هر فاکتور: 0.05 (هرگز صفر نمی‌شود)
  ⑤ حداقل ۵۰ معامله با این شرایط قبل از تنظیم
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from .trade_memory import TradeMemory, TradeContext, TradeOutcome
from .ml_engine import MLEngine, TrainingResult, ModelType
from ..core.logger import get_logger

logger = get_logger("intelligence.weight_adjuster")


@dataclass
class IndicatorWeights:
    """
    وزن‌های اندیکاتورهای Decision Engine.
    مجموع همه وزن‌ها باید ۱.۰ باشد.
    """
    smc_weight: float = 0.40          # وزن SMC Engine
    price_action_weight: float = 0.25  # وزن Price Action Engine
    htf_alignment_weight: float = 0.20 # وزن هم‌راستایی HTF
    session_weight: float = 0.10       # وزن فیلتر سشن
    ltf_weight: float = 0.05           # وزن LTF

    # وزن‌های داخلی SMC
    bos_weight: float = 0.25
    order_block_weight: float = 0.30
    fvg_weight: float = 0.20
    liquidity_weight: float = 0.15
    structure_weight: float = 0.10

    def normalize(self) -> "IndicatorWeights":
        """
        اطمینان از اینکه مجموع وزن‌های اصلی = 1.0
        و هیچ وزنی زیر حداقل نیست.
        """
        MIN_WEIGHT = 0.05
        MAX_WEIGHT = 0.70

        weights = [
            self.smc_weight,
            self.price_action_weight,
            self.htf_alignment_weight,
            self.session_weight,
            self.ltf_weight,
        ]

        # اعمال حداقل و حداکثر
        weights = [max(MIN_WEIGHT, min(MAX_WEIGHT, w)) for w in weights]

        # normalize
        total = sum(weights)
        weights = [w / total for w in weights]

        self.smc_weight = weights[0]
        self.price_action_weight = weights[1]
        self.htf_alignment_weight = weights[2]
        self.session_weight = weights[3]
        self.ltf_weight = weights[4]

        return self

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class WeightUpdate:
    """
    یک به‌روزرسانی وزن پیشنهادشده توسط سیستم.
    """
    factor: str                         # نام فاکتور
    old_weight: float                   # وزن قبلی
    new_weight: float                   # وزن جدید پیشنهادی
    delta: float                        # تغییر
    reason: str                         # دلیل تغییر
    confidence: float                   # اطمینان (0-1) از این پیشنهاد
    sample_size: int                    # تعداد معاملاتی که این پیشنهاد بر اساس آنهاست
    applied: bool = False               # آیا اعمال شده


class WeightAdjuster:
    """
    تنظیم‌کننده وزن اندیکاتورها — Galaxy Vast.

    این کلاس بر اساس تحلیل آماری معاملات گذشته،
    وزن‌های Decision Engine را به صورت تدریجی تنظیم می‌کند.

    مهم:
      تنظیمات همیشه تدریجی و محدود هستند.
      هیچ‌گاه یک فاکتور به طور کامل غیرفعال نمی‌شود.
    """

    # حداکثر تغییر وزن در هر چرخه
    MAX_DELTA_PER_CYCLE = 0.05

    # حداقل وزن هر فاکتور
    MIN_WEIGHT = 0.05

    # حداقل نمونه برای تنظیم
    MIN_SAMPLES_FOR_ADJUSTMENT = 50

    # حداقل اختلاف win rate برای تغییر وزن
    MIN_WIN_RATE_DIFF = 0.08

    def __init__(
        self,
        weights_path: str = "models/weights.json",
    ) -> None:
        """
        Args:
            weights_path: مسیر فایل وزن‌ها
        """
        self._weights_path = weights_path
        self._weights = IndicatorWeights()
        self._update_history: List[WeightUpdate] = []
        self._load_weights()
        logger.info("WeightAdjuster راه‌اندازی شد")

    @property
    def current_weights(self) -> IndicatorWeights:
        """وزن‌های فعلی"""
        return self._weights

    def analyze_and_suggest(
        self, memory: TradeMemory, ml_engine: Optional[MLEngine] = None
    ) -> List[WeightUpdate]:
        """
        تحلیل حافظه معاملاتی و پیشنهاد تغییر وزن‌ها.

        Args:
            memory: حافظه معاملاتی
            ml_engine: مدل ML برای feature importance (اختیاری)

        Returns:
            لیست پیشنهادهای تغییر وزن
        """
        all_trades = memory.get_all()
        if len(all_trades) < self.MIN_SAMPLES_FOR_ADJUSTMENT:
            logger.info(
                f"داده کافی برای تنظیم وزن نیست: "
                f"{len(all_trades)} < {self.MIN_SAMPLES_FOR_ADJUSTMENT}"
            )
            return []

        suggestions: List[WeightUpdate] = []

        # تحلیل بر اساس SMC features
        suggestions.extend(self._analyze_smc_weights(all_trades))

        # تحلیل بر اساس Price Action
        suggestions.extend(self._analyze_pa_weights(all_trades))

        # تحلیل بر اساس ML feature importances
        if ml_engine and ml_engine._is_trained:
            suggestions.extend(
                self._analyze_ml_importances(ml_engine)
            )

        logger.info(f"{len(suggestions)} پیشنهاد تغییر وزن تولید شد")
        return suggestions

    def apply_updates(self, updates: List[WeightUpdate]) -> IndicatorWeights:
        """
        اعمال پیشنهادهای تغییر وزن با رعایت محدودیت‌ها.

        Args:
            updates: پیشنهادهای تغییر

        Returns:
            وزن‌های جدید
        """
        for update in updates:
            # فقط پیشنهادهای با اطمینان بالا اعمال می‌شوند
            if update.confidence < 0.6:
                logger.debug(
                    f"پیشنهاد {update.factor} رد شد — اطمینان پایین: {update.confidence:.2f}"
                )
                continue

            # اعمال محدودیت delta
            clamped_delta = max(
                -self.MAX_DELTA_PER_CYCLE,
                min(self.MAX_DELTA_PER_CYCLE, update.delta)
            )

            if hasattr(self._weights, update.factor):
                old = getattr(self._weights, update.factor)
                new = max(self.MIN_WEIGHT, old + clamped_delta)
                setattr(self._weights, update.factor, new)
                update.applied = True

                logger.info(
                    f"وزن تنظیم شد | {update.factor}: "
                    f"{old:.3f} → {new:.3f} ({clamped_delta:+.3f}) | "
                    f"{update.reason}"
                )

        # normalize کردن وزن‌ها
        self._weights.normalize()

        # ذخیره تاریخچه و وزن‌ها
        self._update_history.extend(updates)
        self._save_weights()

        return self._weights

    # ─── تحلیل‌های خصوصی ────────────────────────────────────────

    def _analyze_smc_weights(
        self, trades: List[TradeContext]
    ) -> List[WeightUpdate]:
        """تحلیل اثربخشی SMC features"""
        suggestions = []

        # بررسی تأثیر BOS
        bos_trades = [t for t in trades if t.smc.bos_detected]
        no_bos_trades = [t for t in trades if not t.smc.bos_detected]

        if len(bos_trades) >= self.MIN_SAMPLES_FOR_ADJUSTMENT // 2:
            bos_wr = self._win_rate(bos_trades)
            no_bos_wr = self._win_rate(no_bos_trades) if no_bos_trades else 0.5
            diff = bos_wr - no_bos_wr

            if abs(diff) >= self.MIN_WIN_RATE_DIFF:
                delta = 0.02 if diff > 0 else -0.02
                suggestions.append(WeightUpdate(
                    factor="bos_weight",
                    old_weight=self._weights.bos_weight,
                    new_weight=self._weights.bos_weight + delta,
                    delta=delta,
                    reason=f"BOS win rate: {bos_wr:.1%} vs no-BOS: {no_bos_wr:.1%}",
                    confidence=min(0.9, len(bos_trades) / 200),
                    sample_size=len(bos_trades),
                ))

        # بررسی تأثیر Order Block quality
        high_ob = [t for t in trades if t.smc.order_block_quality >= 0.7]
        low_ob = [t for t in trades if 0 < t.smc.order_block_quality < 0.7]

        if len(high_ob) >= 20 and len(low_ob) >= 20:
            high_wr = self._win_rate(high_ob)
            low_wr = self._win_rate(low_ob)
            diff = high_wr - low_wr

            if abs(diff) >= self.MIN_WIN_RATE_DIFF:
                delta = 0.02 if diff > 0 else -0.02
                suggestions.append(WeightUpdate(
                    factor="order_block_weight",
                    old_weight=self._weights.order_block_weight,
                    new_weight=self._weights.order_block_weight + delta,
                    delta=delta,
                    reason=f"High-OB win rate: {high_wr:.1%} vs Low-OB: {low_wr:.1%}",
                    confidence=min(0.85, len(high_ob) / 200),
                    sample_size=len(high_ob),
                ))

        return suggestions

    def _analyze_pa_weights(
        self, trades: List[TradeContext]
    ) -> List[WeightUpdate]:
        """تحلیل اثربخشی Price Action"""
        suggestions = []

        # معاملات با PA قوی vs ضعیف
        strong_pa = [t for t in trades if t.price_action.pattern_quality >= 0.7]
        weak_pa = [t for t in trades if 0 < t.price_action.pattern_quality < 0.7]

        if len(strong_pa) >= 30 and len(weak_pa) >= 30:
            strong_wr = self._win_rate(strong_pa)
            weak_wr = self._win_rate(weak_pa)
            diff = strong_wr - weak_wr

            if abs(diff) >= self.MIN_WIN_RATE_DIFF:
                delta = 0.02 if diff > 0.10 else (-0.02 if diff < -0.10 else 0.01)
                suggestions.append(WeightUpdate(
                    factor="price_action_weight",
                    old_weight=self._weights.price_action_weight,
                    new_weight=self._weights.price_action_weight + delta,
                    delta=delta,
                    reason=(
                        f"PA قوی win rate: {strong_wr:.1%} vs PA ضعیف: {weak_wr:.1%}"
                    ),
                    confidence=min(0.85, len(strong_pa) / 200),
                    sample_size=len(strong_pa),
                ))

        return suggestions

    def _analyze_ml_importances(self, ml_engine: MLEngine) -> List[WeightUpdate]:
        """
        استفاده از feature importances مدل ML برای پیشنهاد تغییر وزن.
        فقط feature‌هایی که مستقیماً به وزن‌ها map می‌شوند.
        """
        suggestions = []

        # بهترین مدل را انتخاب می‌کنیم
        if not ml_engine._training_results:
            return []

        best_mt = max(
            ml_engine._training_results,
            key=lambda mt: ml_engine._training_results[mt].auc_roc,
        )
        importances = ml_engine._training_results[best_mt].feature_importances

        # نگاشت feature → weight factor
        feature_to_weight = {
            "structure_score": "smc_weight",
            "order_block_quality": "order_block_weight",
            "fvg_quality": "fvg_weight",
            "htf_alignment": "htf_alignment_weight",
            "pattern_quality": "price_action_weight",
        }

        for feature, weight_factor in feature_to_weight.items():
            importance = importances.get(feature, 0.0)
            current = getattr(self._weights, weight_factor, None)
            if current is None:
                continue

            # اگر اهمیت ML با وزن فعلی تفاوت زیادی دارد
            # وزن فعلی (normalize شده) را با importance مقایسه می‌کنیم
            total_weight = (
                self._weights.smc_weight
                + self._weights.price_action_weight
                + self._weights.htf_alignment_weight
            )
            normalized_current = current / max(total_weight, 1e-9)

            diff = importance - normalized_current
            if abs(diff) > 0.05:
                delta = 0.01 * np.sign(diff)
                min_samples = min(
                    r.training_samples for r in ml_engine._training_results.values()
                )
                suggestions.append(WeightUpdate(
                    factor=weight_factor,
                    old_weight=current,
                    new_weight=current + delta,
                    delta=float(delta),
                    reason=(
                        f"ML feature importance {feature}: {importance:.3f} "
                        f"vs current normalized weight: {normalized_current:.3f}"
                    ),
                    confidence=min(0.75, min_samples / 500),
                    sample_size=min_samples,
                ))

        return suggestions

    def _win_rate(self, trades: List[TradeContext]) -> float:
        """محاسبه نرخ برنده از لیست معاملات"""
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.outcome == TradeOutcome.WIN)
        return wins / len(trades)

    def _save_weights(self) -> None:
        """ذخیره وزن‌های فعلی روی دیسک"""
        os.makedirs(os.path.dirname(self._weights_path) or ".", exist_ok=True)
        with open(self._weights_path, "w") as f:
            json.dump(self._weights.to_dict(), f, indent=2)

    def _load_weights(self) -> None:
        """بارگذاری وزن‌های ذخیره‌شده از دیسک"""
        if not os.path.exists(self._weights_path):
            logger.info("فایل وزن‌ها وجود ندارد — وزن‌های پیش‌فرض استفاده می‌شود")
            return
        try:
            with open(self._weights_path) as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self._weights, key):
                    setattr(self._weights, key, float(value))
            self._weights.normalize()
            logger.info(f"وزن‌ها بارگذاری شدند از {self._weights_path}")
        except Exception as e:
            logger.warning(f"خطا در بارگذاری وزن‌ها: {e} — پیش‌فرض استفاده می‌شود")
