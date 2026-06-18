"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: PredictionService

وظیفه:
  پیش‌بینی real-time برای هر سیگنال جدید.

  خروجی نهایی:
  {
    "probability": 84,   ← احتمال موفقیت (0-100)
    "confidence":  91,   ← اطمینان به پیش‌بینی (0-100)
    "risk":       "LOW"  ← سطح ریسک (LOW/MEDIUM/HIGH/VERY_HIGH)
  }

منطق:
  • probability  ← خروجی مستقیم XGBoost (calibrated)
  • confidence   ← ترکیب AUC مدل + تعداد samples + confluence score
  • risk         ← ترکیب spread_ratio + volatility + drawdown احتمالی
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from ..core.logger import get_logger
from .dataset_builder import DatasetBuilder
from .feature_extractor import SMCSignalInput
from .model_manager import ModelManager

logger = get_logger("ai_prediction.prediction_service")


class RiskLevel(str, Enum):
    LOW       = "LOW"
    MEDIUM    = "MEDIUM"
    HIGH      = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass
class PredictionResult:
    """
    خروجی نهایی سرویس پیش‌بینی.

    Attributes:
        probability: احتمال موفقیت معامله (0-100)
        confidence:  اطمینان به پیش‌بینی (0-100)
        risk:        سطح ریسک
        model_auc:   AUC مدل استفاده‌شده
        is_tradeable: آیا سیگنال قابل معامله است؟
        reason:      توضیح کوتاه
    """
    probability:  int
    confidence:   int
    risk:         RiskLevel
    model_auc:    float
    is_tradeable: bool
    reason:       str

    def to_dict(self) -> dict:
        return {
            "probability":  self.probability,
            "confidence":   self.confidence,
            "risk":         self.risk.value,
            "model_auc":    round(self.model_auc, 3),
            "is_tradeable": self.is_tradeable,
            "reason":       self.reason,
        }


class PredictionService:
    """
    سرویس پیش‌بینی real-time Galaxy Vast.

    استفاده:
        service = PredictionService()
        result = await service.predict(signal)
        # result.probability = 84
        # result.confidence  = 91
        # result.risk        = "LOW"
    """

    # حداقل احتمال برای قابل معامله بودن (پیش‌فرض — از config می‌آید)
    DEFAULT_MIN_PROBABILITY: int = 60
    DEFAULT_MIN_CONFIDENCE:  int = 50

    def __init__(
        self,
        min_probability: int = DEFAULT_MIN_PROBABILITY,
        min_confidence:  int = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self._manager = ModelManager()
        self._builder = DatasetBuilder()
        self._min_probability = min_probability
        self._min_confidence  = min_confidence

    def predict(self, signal: SMCSignalInput) -> PredictionResult:
        """
        پیش‌بینی برای یک سیگنال جدید.

        Args:
            signal: سیگنال SMC از Decision Engine

        Returns:
            PredictionResult با probability، confidence، risk
        """
        # بارگذاری بهترین مدل
        model = self._manager.load_best_model(signal.symbol)
        if model is None:
            logger.warning(
                "no trained model for %s — returning neutral prediction",
                signal.symbol,
            )
            return self._neutral_prediction("no trained model available")

        # استخراج ویژگی‌ها
        X = self._builder.build_single(signal)

        # پیش‌بینی احتمال
        raw_prob = float(model.predict_proba(X)[0, 1])

        # دریافت متادیتای مدل
        meta = self._manager.get_best_metadata(signal.symbol)
        model_auc = meta.auc_roc if meta else 0.60

        # محاسبه probability (0-100)
        probability = self._calc_probability(raw_prob)

        # محاسبه confidence (0-100)
        confidence = self._calc_confidence(
            raw_prob   = raw_prob,
            model_auc  = model_auc,
            n_samples  = meta.n_samples if meta else 0,
            confluence = signal.decision_score / 100.0,
        )

        # محاسبه risk level
        risk = self._calc_risk(signal, probability)

        # آیا قابل معامله است؟
        is_tradeable = (
            probability >= self._min_probability
            and confidence >= self._min_confidence
            and risk != RiskLevel.VERY_HIGH
        )

        reason = self._build_reason(probability, confidence, risk, is_tradeable)

        logger.info(
            "prediction for %s: prob=%d confidence=%d risk=%s tradeable=%s",
            signal.symbol, probability, confidence, risk.value, is_tradeable,
        )

        return PredictionResult(
            probability  = probability,
            confidence   = confidence,
            risk         = risk,
            model_auc    = model_auc,
            is_tradeable = is_tradeable,
            reason       = reason,
        )

    def has_model(self, symbol: str) -> bool:
        """آیا مدل آموزش‌دیده‌ای برای این نماد وجود دارد؟"""
        return self._manager.has_model(symbol)

    # ─── private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_probability(raw_prob: float) -> int:
        """
        تبدیل احتمال خام XGBoost به عدد 0-100.
        Calibration: احتمال‌های نزدیک به 0.5 به سمت مرکز کشیده می‌شوند.
        """
        # isotonic calibration ساده: تقویت سیگنال‌های قوی
        if raw_prob >= 0.70:
            calibrated = 0.70 + (raw_prob - 0.70) * 1.2
        elif raw_prob <= 0.30:
            calibrated = 0.30 - (0.30 - raw_prob) * 1.2
        else:
            calibrated = raw_prob
        calibrated = max(0.01, min(0.99, calibrated))
        return int(round(calibrated * 100))

    @staticmethod
    def _calc_confidence(
        raw_prob:  float,
        model_auc: float,
        n_samples: int,
        confluence: float,
    ) -> int:
        """
        محاسبه اطمینان به پیش‌بینی.

        4 عامل:
          1. قدرت سیگنال مدل (فاصله از 0.5)
          2. کیفیت مدل (AUC)
          3. کافی بودن داده آموزشی
          4. سطح confluence سیگنال SMC
        """
        # عامل ۱: قدرت سیگنال (0-1)
        signal_strength = abs(raw_prob - 0.50) * 2.0  # 0=کاملاً بی‌طرف, 1=کاملاً مطمئن

        # عامل ۲: کیفیت مدل (0-1) — AUC از 0.5 تا 1.0 → 0 تا 1
        model_quality = max(0.0, (model_auc - 0.50) / 0.50)

        # عامل ۳: کافی بودن داده (0-1)
        if n_samples >= 500:
            data_score = 1.00
        elif n_samples >= 200:
            data_score = 0.80
        elif n_samples >= 100:
            data_score = 0.60
        elif n_samples >= 50:
            data_score = 0.40
        else:
            data_score = 0.20

        # عامل ۴: confluence (0-1)
        confluence_score = max(0.0, min(1.0, confluence))

        # وزن‌دهی
        confidence_raw = (
            signal_strength  * 0.35 +
            model_quality    * 0.30 +
            data_score       * 0.20 +
            confluence_score * 0.15
        )

        return int(round(confidence_raw * 100))

    @staticmethod
    def _calc_risk(signal: SMCSignalInput, probability: int) -> RiskLevel:
        """
        محاسبه سطح ریسک بر اساس شرایط بازار.

        عوامل:
          • spread_ratio (spread نسبت به ATR)
          • volatility_ratio (ATR فعلی نسبت به میانگین)
          • session (سشن‌های بی‌کیفیت = ریسک بیشتر)
          • probability (پیش‌بینی ضعیف = ریسک بیشتر)
        """
        risk_score = 0.0

        # spread risk
        if signal.spread_ratio >= 0.30:
            risk_score += 3.0
        elif signal.spread_ratio >= 0.20:
            risk_score += 2.0
        elif signal.spread_ratio >= 0.10:
            risk_score += 1.0

        # volatility risk
        if signal.volatility_ratio >= 2.5:
            risk_score += 3.0
        elif signal.volatility_ratio >= 1.8:
            risk_score += 2.0
        elif signal.volatility_ratio >= 1.3:
            risk_score += 1.0

        # session risk
        from .feature_extractor import MarketSession
        if signal.session == MarketSession.OFF:
            risk_score += 2.0
        elif signal.session == MarketSession.ASIAN:
            risk_score += 1.0

        # probability risk
        if probability < 55:
            risk_score += 2.0
        elif probability < 65:
            risk_score += 1.0

        if risk_score >= 6.0:
            return RiskLevel.VERY_HIGH
        elif risk_score >= 4.0:
            return RiskLevel.HIGH
        elif risk_score >= 2.0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    @staticmethod
    def _build_reason(
        probability: int,
        confidence:  int,
        risk:        RiskLevel,
        tradeable:   bool,
    ) -> str:
        if not tradeable:
            reasons = []
            if probability < 60:
                reasons.append(f"low probability ({probability}%)")
            if confidence < 50:
                reasons.append(f"low confidence ({confidence}%)")
            if risk == RiskLevel.VERY_HIGH:
                reasons.append("very high market risk")
            return "NOT TRADEABLE — " + ", ".join(reasons)

        if probability >= 80 and confidence >= 80:
            return f"HIGH QUALITY signal — prob={probability}% conf={confidence}% risk={risk.value}"
        return f"VALID signal — prob={probability}% conf={confidence}% risk={risk.value}"

    @staticmethod
    def _neutral_prediction(reason: str) -> PredictionResult:
        return PredictionResult(
            probability  = 50,
            confidence   = 0,
            risk         = RiskLevel.HIGH,
            model_auc    = 0.0,
            is_tradeable = False,
            reason       = reason,
        )
