"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 5: Risk Agent
مسئولیت: ریسک پرتفولیو، spread، ATR، drawdown، daily limits
"""
from __future__ import annotations

from typing import Any, Dict

from .base_agent import AgentVote, AgentStatus, BaseAgent


class RiskAgent(BaseAgent):
    """
    کنترل ریسک:
    - Portfolio Risk (cross-symbol)
    - Spread Filter
    - ATR / Volatility Filter
    - Daily Limits
    - Drawdown Guard

    ⚠️ این Agent می‌تواند score=0 بدهد و معامله را بلاک کند.
    """

    def __init__(self, weight: float = 0.15, enabled: bool = True,
                 max_portfolio_risk: float = 5.0,
                 max_spread_ratio: float = 2.0) -> None:
        super().__init__(name="Risk", weight=weight, enabled=enabled)
        self.max_portfolio_risk = max_portfolio_risk
        self.max_spread_ratio   = max_spread_ratio

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score      = 100.0
        confidence = 80.0
        reasons    = []
        blocked    = False

        # Portfolio Risk Check
        portfolio_risk = float(context.get("portfolio_risk_percent", 0.0))
        if portfolio_risk >= self.max_portfolio_risk:
            score   = 0.0
            blocked = True
            reasons.append(f"BLOCKED: Portfolio risk={portfolio_risk:.1f}% >= {self.max_portfolio_risk}%")
        elif portfolio_risk > self.max_portfolio_risk * 0.8:
            score -= 30.0
            reasons.append(f"High portfolio risk={portfolio_risk:.1f}%")
        else:
            reasons.append(f"Portfolio risk OK ({portfolio_risk:.1f}%)")

        # Spread Filter
        spread_ratio = float(context.get("spread_ratio", 1.0))
        if spread_ratio > self.max_spread_ratio * 1.5:
            score   = 0.0
            blocked = True
            reasons.append(f"BLOCKED: Spread ratio={spread_ratio:.2f} too high")
        elif spread_ratio > self.max_spread_ratio:
            score -= 20.0
            reasons.append(f"Elevated spread ratio={spread_ratio:.2f}")

        # ATR / Volatility
        atr_norm = float(context.get("atr_normalized", 1.0))
        if atr_norm > 3.0:
            score -= 15.0
            reasons.append(f"High volatility ATR={atr_norm:.2f}x")
        elif atr_norm < 0.3:
            score -= 10.0
            reasons.append(f"Low volatility ATR={atr_norm:.2f}x")

        # Daily Limits
        daily_trades = int(context.get("daily_trades_count", 0))
        max_daily    = int(context.get("max_daily_trades", 5))
        if daily_trades >= max_daily:
            score   = 0.0
            blocked = True
            reasons.append(f"BLOCKED: Daily limit reached ({daily_trades}/{max_daily})")

        # Daily Loss Check
        daily_loss_pct = float(context.get("daily_loss_percent", 0.0))
        max_daily_loss = float(context.get("max_daily_loss_percent", 3.0))
        if daily_loss_pct >= max_daily_loss:
            score   = 0.0
            blocked = True
            reasons.append(f"BLOCKED: Daily loss={daily_loss_pct:.1f}% >= {max_daily_loss}%")

        # Consecutive Losses
        consec_losses = int(context.get("consecutive_losses", 0))
        if consec_losses >= 3:
            score -= 25.0
            reasons.append(f"Consecutive losses={consec_losses}")

        score      = max(0.0, min(100.0, score))
        confidence = max(0.0, min(100.0, confidence))
        status     = AgentStatus.ERROR if blocked else AgentStatus.OK

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=status,
            reason=" | ".join(reasons),
            metadata={
                "blocked": blocked,
                "portfolio_risk": portfolio_risk,
                "spread_ratio": spread_ratio,
                "atr_norm": atr_norm,
                "daily_trades": daily_trades,
            },
        )
