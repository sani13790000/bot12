"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 4: AI Prediction Agent
مسئولیت: پیش‌بینی XGBoost، probability، confidence
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class AIPredictionAgent(BaseAgent):
    """
    تحلیل هوش مصنوعی:
    - XGBoost Win Probability
    - Model Confidence (AUC-based)
    - Feature Quality Score
    - Model Availability Check
    """

    def __init__(self, weight: float = 0.20, enabled: bool = True) -> None:
        super().__init__(name="AI Prediction", weight=weight, enabled=enabled)

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        reasons = []

        # خروجی مستقیم PredictionService اگر موجود باشد
        ai_output = context.get("ai_prediction", {})
        probability = float(ai_output.get("probability", 0.0))
        ai_confidence = float(ai_output.get("confidence", 0.0))
        risk_level = ai_output.get("risk", "UNKNOWN")
        model_auc  = float(ai_output.get("model_auc", 0.0))

        if not ai_output:
            # بدون مدل — از decision_score استفاده می‌شود
            decision_score = float(context.get("decision_score", 50.0))
            score      = decision_score
            confidence = 40.0
            reasons.append(f"No ML model — using decision_score={decision_score:.1f}")
            return AgentVote(
                score=score, confidence=confidence,
                direction=context.get("direction", "NEUTRAL"),
                status=AgentStatus.WARNING,
                reason=" | ".join(reasons),
                metadata={"model_available": False},
            )

        # امتیاز از probability مدل
        score = probability  # 0–100

        # کاهش امتیاز بر اساس ریسک
        risk_penalty = {"LOW": 0.0, "MEDIUM": 5.0, "HIGH": 15.0, "EXTREME": 25.0}
        score -= risk_penalty.get(risk_level, 0.0)

        # confidence بر اساس AUC مدل
        if model_auc > 0.0:
            confidence = min(ai_confidence, model_auc * 100.0)
        else:
            confidence = ai_confidence

        reasons.append(f"XGBoost prob={probability:.1f}% risk={risk_level}")
        if model_auc > 0:
            reasons.append(f"Model AUC={model_auc:.3f}")

        score      = max(0.0, min(100.0, score))
        confidence = max(0.0, min(100.0, confidence))

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=AgentStatus.OK,
            reason=" | ".join(reasons),
            metadata={
                "probability": probability,
                "risk_level": risk_level,
                "model_auc": model_auc,
                "model_available": True,
            },
        )
