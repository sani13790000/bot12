"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: DatasetBuilder

وظیفه:
  ساخت dataset آموزشی از حافظه معاملاتی (TradeMemory).
  هر معامله به یک ردیف ویژگی + label تبدیل می‌شود.

قانون اصلی:
  label = 1 (موفق) اگر معامله با سود بسته شده باشد
  label = 0 (ناموفق) فقط اگر شرایط ورود هم معتبر بوده

برچسب‌گذاری:
  سیستم معاملات با نقض قوانین را از dataset حذف می‌کند
  تا مدل از اشتباهات واقعی، نه از زیان‌های معتبر یاد بگیرد.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from ..core.logger import get_logger
from ..intelligence.trade_memory import TradeMemory, TradeContext, TradeOutcome
from .feature_extractor import FeatureExtractor, SMCSignalInput, SMCFeatures
from .feature_extractor import MarketSession, TrendDirection, TradeDirection

logger = get_logger("ai_prediction.dataset_builder")


@dataclass
class TrainingDataset:
    """
    Dataset آماده برای XGBoost.

    Attributes:
        X: ماتریس ویژگی‌ها — شکل (n_samples, n_features)
        y: برچسب‌ها — 0 یا 1
        feature_names: نام ویژگی‌ها
        n_samples: تعداد نمونه‌ها
        n_positive: تعداد معاملات موفق
        n_negative: تعداد معاملات ناموفق
        class_weight_ratio: نسبت n_negative / n_positive (برای XGBoost scale_pos_weight)
    """
    X:                 np.ndarray
    y:                 np.ndarray
    feature_names:     List[str]
    n_samples:         int
    n_positive:        int
    n_negative:        int
    class_weight_ratio: float

    @property
    def is_balanced(self) -> bool:
        """آیا dataset متعادل است؟ (نسبت ≤ 2)"""
        return self.class_weight_ratio <= 2.0

    @property
    def win_rate(self) -> float:
        """نرخ موفقیت در dataset."""
        if self.n_samples == 0:
            return 0.0
        return self.n_positive / self.n_samples


class DatasetBuilder:
    """
    سازنده dataset از TradeMemory.

    ورودی:  TradeMemory — تاریخچه کامل معاملات
    خروجی: TrainingDataset — آماده برای XGBoostTrainer
    """

    # حداقل معاملات برای ساخت dataset معتبر
    MIN_SAMPLES: int = 30

    def __init__(self) -> None:
        self._extractor = FeatureExtractor()

    def build(
        self,
        memory: TradeMemory,
        exclude_rule_violations: bool = True,
    ) -> TrainingDataset:
        """
        ساخت dataset کامل از تاریخچه معاملات.

        Args:
            memory: حافظه معاملاتی
            exclude_rule_violations: اگر True، معاملاتی که قوانین را
                نقض کرده‌اند از dataset حذف می‌شوند.

        Returns:
            TrainingDataset آماده برای آموزش
        """
        trades = memory.get_closed_trades()
        logger.info("building dataset from %d closed trades", len(trades))

        rows: List[np.ndarray] = []
        labels: List[int] = []
        skipped = 0

        for ctx in trades:
            # فقط معاملاتی که outcome دارند
            if ctx.outcome is None:
                skipped += 1
                continue

            # حذف معاملات با نقض قوانین (اختیاری)
            if exclude_rule_violations and ctx.outcome.rule_violation_detected:
                skipped += 1
                continue

            signal = self._context_to_signal(ctx)
            features = self._extractor.extract(signal)
            label = 1 if ctx.outcome.pnl_pips > 0 else 0

            rows.append(features.to_numpy())
            labels.append(label)

        logger.info(
            "dataset built: %d samples (%d skipped), win_rate=%.1f%%",
            len(rows), skipped,
            100 * sum(labels) / max(len(labels), 1),
        )

        if len(rows) < self.MIN_SAMPLES:
            raise ValueError(
                f"dataset has only {len(rows)} samples — "
                f"minimum {self.MIN_SAMPLES} required for training"
            )

        X = np.array(rows, dtype=np.float32)
        y = np.array(labels, dtype=np.int32)

        n_pos = int(y.sum())
        n_neg = len(y) - n_pos
        ratio = n_neg / n_pos if n_pos > 0 else 1.0

        return TrainingDataset(
            X=X,
            y=y,
            feature_names=SMCFeatures.feature_names(),
            n_samples=len(y),
            n_positive=n_pos,
            n_negative=n_neg,
            class_weight_ratio=ratio,
        )

    def build_single(self, signal: SMCSignalInput) -> np.ndarray:
        """
        ساخت یک ردیف ویژگی برای پیش‌بینی real-time.

        Args:
            signal: سیگنال جدید

        Returns:
            آرایه numpy با شکل (1, n_features)
        """
        features = self._extractor.extract(signal)
        return features.to_numpy().reshape(1, -1)

    # ─── private ──────────────────────────────────────────────────────────────

    def _context_to_signal(self, ctx: TradeContext) -> SMCSignalInput:
        """
        تبدیل TradeContext (از TradeMemory) به SMCSignalInput.
        این mapping بین ماژول Intelligence و AI Prediction است.
        """
        smc = ctx.smc
        pa  = ctx.price_action
        mkt = ctx.market

        return SMCSignalInput(
            symbol        = ctx.symbol,
            direction     = TradeDirection(ctx.direction),
            entry_price   = ctx.entry_price,
            timestamp     = ctx.timestamp,

            # SMC
            bos_detected        = smc.bos_detected,
            choch_detected      = smc.choch_detected,
            bos_strength        = smc.bos_strength,
            choch_strength      = smc.choch_strength,
            order_block_present = smc.order_block_present,
            order_block_quality = smc.order_block_quality,
            order_block_tested  = smc.order_block_tested,
            breaker_block       = smc.breaker_block,
            fvg_present         = smc.fvg_present,
            fvg_quality         = smc.fvg_quality,
            ifvg_present        = smc.ifvg_present,
            liquidity_sweep     = smc.liquidity_sweep,
            liquidity_quality   = smc.liquidity_quality,
            internal_liquidity  = smc.internal_liquidity,
            external_liquidity  = smc.external_liquidity,
            in_premium_zone     = smc.in_premium_zone,
            in_discount_zone    = smc.in_discount_zone,
            equilibrium_dist    = smc.equilibrium_dist,

            # PA
            pa_pattern    = pa.primary_pattern,
            pa_quality    = pa.pattern_quality,
            pa_timeframe  = pa.timeframe,

            # بازار
            atr              = mkt.atr,
            spread           = mkt.spread,
            spread_ratio     = mkt.spread_ratio,
            volatility_ratio = mkt.volatility_ratio,
            trend_direction  = TrendDirection(mkt.trend_direction),
            trend_strength   = mkt.trend_strength,
            htf_alignment    = mkt.htf_alignment,
            htf_score        = mkt.htf_score,

            # زمان
            session      = MarketSession(ctx.session),
            in_kill_zone = ctx.in_kill_zone,
            hour_of_day  = ctx.timestamp.hour if ctx.timestamp else 0,
            day_of_week  = ctx.timestamp.weekday() if ctx.timestamp else 0,

            decision_score = ctx.confidence_score,
        )
