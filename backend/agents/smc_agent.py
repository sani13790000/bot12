"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 3: SMC Agent
مسئولیت: Order Block، FVG، Breaker Block، Mitigation
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class SMCAgent(BaseAgent):
    """
    تحلیل Smart Money Concepts:
    - Order Block (OB)
    - Fair Value Gap (FVG / IFVG)
    - Breaker Block
    - Mitigation Block
    - Kill Zone
    """

    def __init__(self, weight: float = 0.20, enabled: bool = True) -> None:
        super().__init__(name="SMC", weight=weight, enabled=enabled)

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score      = 20.0
        confidence = 50.0
        reasons    = []
        confluence = 0

        # Order Block
        ob_present = context.get("order_block_present", False)
        ob_quality = float(context.get("order_block_quality", 0.0))
        ob_tested  = context.get("order_block_tested", False)
        if ob_present:
            score += 25.0 * ob_quality
            confluence += 1
            reasons.append(f"OB quality={ob_quality:.2f}")
            if ob_tested:
                score += 5.0
                reasons.append("OB tested")

        # Breaker Block
        breaker = context.get("breaker_block", False)
        if breaker:
            score += 15.0
            confluence += 1
            reasons.append("Breaker block")

        # FVG
        fvg_present = context.get("fvg_present", False)
        fvg_quality = float(context.get("fvg_quality", 0.0))
        ifvg        = context.get("ifvg_present", False)
        if fvg_present:
            score += 15.0 * fvg_quality
            confluence += 1
            reasons.append(f"FVG quality={fvg_quality:.2f}")
        if ifvg:
            score += 8.0
            confluence += 1
            reasons.append("IFVG present")

        # Kill Zone
        in_kill_zone = context.get("in_kill_zone", False)
        session_quality = float(context.get("session_quality", 0.5))
        if in_kill_zone:
            score += 10.0 * session_quality
            confidence += 15.0
            reasons.append(f"Kill Zone (session_q={session_quality:.2f})")

        # Confluence bonus
        if confluence >= 3:
            score += 10.0
            confidence += 15.0
            reasons.append(f"High confluence ({confluence} signals)")
        elif confluence >= 2:
            score += 5.0
            confidence += 8.0

        score      = min(score, 100.0)
        confidence = min(confidence, 100.0)

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=AgentStatus.OK,
            reason=" | ".join(reasons) if reasons else "No SMC signal",
            metadata={
                "ob_present": ob_present, "fvg": fvg_present,
                "breaker": breaker, "confluence": confluence,
                "kill_zone": in_kill_zone,
            },
        )
