"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 2: Liquidity Agent
مسئولیت: تحلیل نقدینگی، Sweep، Internal/External Liquidity
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class LiquidityAgent(BaseAgent):
    """
    تحلیل نقدینگی:
    - Liquidity Sweep (جارو کردن استاپ‌ها)
    - Internal Liquidity
    - External Liquidity
    - Session Liquidity
    """

    def __init__(self, weight: float = 0.15, enabled: bool = True) -> None:
        super().__init__(name="Liquidity", weight=weight, enabled=enabled)

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score      = 30.0
        confidence = 50.0
        reasons    = []
        direction  = context.get("direction", "NEUTRAL")

        # Liquidity Sweep
        sweep = context.get("liquidity_sweep", False)
        sweep_quality = float(context.get("sweep_quality", 0.0))
        if sweep:
            score += 30.0
            score += sweep_quality * 15.0
            confidence += 20.0
            reasons.append(f"Liquidity sweep (quality={sweep_quality:.2f})")

        # Internal Liquidity
        internal_liq = float(context.get("internal_liquidity", 0.0))
        if internal_liq > 0.5:
            score += internal_liq * 10.0
            reasons.append(f"Internal liq={internal_liq:.2f}")

        # External Liquidity
        external_liq = float(context.get("external_liquidity", 0.0))
        if external_liq > 0.5:
            score += external_liq * 10.0
            reasons.append(f"External liq={external_liq:.2f}")

        # موقعیت قیمت: Discount vs Premium
        in_discount = context.get("in_discount_zone", False)
        in_premium  = context.get("in_premium_zone", False)
        dir_ok = (direction == "BUY" and in_discount) or (direction == "SELL" and in_premium)
        if dir_ok:
            score += 10.0
            confidence += 10.0
            reasons.append("Price in optimal zone for direction")

        score      = min(score, 100.0)
        confidence = min(confidence, 100.0)

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=direction,
            status=AgentStatus.OK,
            reason=" | ".join(reasons) if reasons else "No liquidity signal",
            metadata={
                "sweep": sweep,
                "sweep_quality": sweep_quality,
                "in_discount": in_discount,
                "in_premium": in_premium,
            },
        )
