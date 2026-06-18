"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 7: Execution Agent
مسئولیت: کیفیت اجرا، سشن، slippage، liquidity کافی
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class ExecutionAgent(BaseAgent):
    """
    کیفیت اجرای معامله:
    - Session Quality (London/NY/Asian)
    - Kill Zone تأیید
    - Slippage Risk
    - Market Liquidity
    - Mode Control (SIGNAL_ONLY / SEMI_AUTO / FULL_AUTO)
    """

    BEST_SESSIONS = {"LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"}

    def __init__(self, weight: float = 0.10, enabled: bool = True) -> None:
        super().__init__(name="Execution", weight=weight, enabled=enabled)

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score      = 50.0
        confidence = 60.0
        reasons    = []

        # Mode Check
        trading_mode = context.get("trading_mode", "SIGNAL_ONLY")
        if trading_mode == "SIGNAL_ONLY":
            # در این mode execution بررسی نمی‌شود
            return AgentVote(
                score=75.0, confidence=50.0,
                direction=context.get("direction", "NEUTRAL"),
                status=AgentStatus.OK,
                reason="Signal-only mode: execution check skipped",
                metadata={"mode": trading_mode},
            )

        # Session Quality
        session = str(context.get("session", "UNKNOWN")).upper()
        session_quality = float(context.get("session_quality", 0.5))
        if session in self.BEST_SESSIONS:
            score += 25.0 * session_quality
            confidence += 15.0
            reasons.append(f"Optimal session: {session} (q={session_quality:.2f})")
        elif session == "ASIAN":
            score += 10.0 * session_quality
            reasons.append(f"Asian session (lower liquidity)")
        else:
            score += 5.0
            reasons.append(f"Off-session: {session}")

        # Kill Zone
        in_kill_zone = context.get("in_kill_zone", False)
        if in_kill_zone:
            score += 15.0
            confidence += 10.0
            reasons.append("In Kill Zone")

        # Slippage Estimate
        expected_slippage = float(context.get("expected_slippage_pips", 0.0))
        if expected_slippage > 3.0:
            score -= 20.0
            reasons.append(f"High slippage risk: {expected_slippage:.1f} pips")
        elif expected_slippage > 1.0:
            score -= 8.0
            reasons.append(f"Moderate slippage: {expected_slippage:.1f} pips")

        # Market Liquidity
        market_depth = float(context.get("market_depth_score", 0.7))
        score += market_depth * 10.0

        score      = max(0.0, min(100.0, score))
        confidence = max(0.0, min(100.0, confidence))

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=AgentStatus.OK,
            reason=" | ".join(reasons) if reasons else "Execution OK",
            metadata={
                "session": session,
                "kill_zone": in_kill_zone,
                "slippage": expected_slippage,
                "mode": trading_mode,
            },
        )
