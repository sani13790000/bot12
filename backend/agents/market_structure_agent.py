"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 1: Market Structure Agent
مسئولیت: تحلیل BOS، CHOCH، روند کلی بازار
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class MarketStructureAgent(BaseAgent):
    """
    تحلیل ساختار بازار:
    - BOS (Break of Structure)
    - CHOCH (Change of Character)
    - روند HTF و LTF
    - هم‌راستایی Multi-Timeframe
    """

    def __init__(self, weight: float = 0.20, enabled: bool = True) -> None:
        super().__init__(name="Market Structure", weight=weight, enabled=enabled)

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score      = 0.0
        confidence = 50.0
        reasons    = []
        direction  = "NEUTRAL"

        # BOS تشخیص
        bos = context.get("bos_detected", False)
        bos_strength = float(context.get("bos_strength", 0.0))
        if bos:
            score += 25.0
            score += bos_strength * 10.0
            reasons.append(f"BOS detected (strength={bos_strength:.2f})")

        # CHOCH تشخیص
        choch = context.get("choch_detected", False)
        choch_strength = float(context.get("choch_strength", 0.0))
        if choch:
            score += 20.0
            score += choch_strength * 8.0
            reasons.append(f"CHOCH detected (strength={choch_strength:.2f})")

        # هم‌راستایی HTF
        htf_aligned = context.get("htf_alignment", False)
        htf_score   = float(context.get("htf_score", 0.5))
        if htf_aligned:
            score += 20.0 * htf_score
            confidence += 15.0
            reasons.append(f"HTF aligned (score={htf_score:.2f})")

        # تعداد تأییدیه‌های ساختار
        structure_count = int(context.get("structure_count", 0))
        score += min(structure_count * 5.0, 15.0)

        # جهت‌گیری
        direction_raw = context.get("direction", "NEUTRAL")
        if direction_raw in ("BUY", "SELL"):
            direction = direction_raw
            confidence += 10.0

        # اگر هیچ سیگنال ساختاری نباشد
        if not bos and not choch:
            score = 20.0
            confidence = 30.0
            reasons.append("No structural break detected")

        score      = min(score, 100.0)
        confidence = min(confidence, 100.0)

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=direction,
            status=AgentStatus.OK,
            reason=" | ".join(reasons) if reasons else "No structure",
            metadata={
                "bos": bos, "choch": choch,
                "bos_strength": bos_strength,
                "htf_aligned": htf_aligned,
            },
        )
