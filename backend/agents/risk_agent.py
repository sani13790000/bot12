"""Galaxy Vast AI Trading Platform
RiskAgent v2 — Highest Priority Safety Engine
===============================================
MS-1 Safety Invariants:
  - score=0.0 + status=ERROR = absolute BLOCK (veto)
  - No other agent can override this decision
  - All risk checks run even if earlier ones already blocked
  - Timeout-safe: each sub-check is independent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base_agent import AgentStatus, AgentVote, BaseAgent

logger = logging.getLogger("agents.risk")

_DEFAULT_MAX_PORTFOLIO_RISK = 5.0
_DEFAULT_MAX_SPREAD_RATIO = 2.0
_DEFAULT_MAX_ATR_MULTIPLIER = 3.5
_DEFAULT_MIN_ATR_MULTIPLIER = 0.25
_DEFAULT_MAX_DAILY_TRADES = 10
_DEFAULT_MAX_DAILY_LOSS_PCT = 3.0
_DEFAULT_MAX_CONSEC_LOSSES = 3
_DEFAULT_MAX_DRAWDOWN_PCT = 8.0


class RiskAgent(BaseAgent):
    """
    Risk Engine — highest priority in the multi-agent system.

    Blocking rules (score=0.0, status=ERROR):
      B-1  Portfolio risk >= max_portfolio_risk %
      B-2  Spread ratio  >= max_spread_ratio x 1.5 (extreme spread)
      B-3  Daily trade count >= max_daily_trades
      B-4  Daily loss % >= max_daily_loss_pct
      B-5  Drawdown % >= max_drawdown_pct
      B-6  Circuit breaker OPEN

    MS-1 guarantee: VotingEngine checks this agent FIRST and returns
    BLOCKED immediately if score==0 and status==ERROR.
    """

    _AGENT_NAME = "Risk"

    def __init__(
        self,
        weight: float = 0.15,
        enabled: bool = True,
        max_portfolio_risk: float = _DEFAULT_MAX_PORTFOLIO_RISK,
        max_spread_ratio: float = _DEFAULT_MAX_SPREAD_RATIO,
        max_atr_multiplier: float = _DEFAULT_MAX_ATR_MULTIPLIER,
        min_atr_multiplier: float = _DEFAULT_MIN_ATR_MULTIPLIER,
        max_daily_trades: int = _DEFAULT_MAX_DAILY_TRADES,
        max_daily_loss_pct: float = _DEFAULT_MAX_DAILY_LOSS_PCT,
        max_consec_losses: int = _DEFAULT_MAX_CONSEC_LOSSES,
        max_drawdown_pct: float = _DEFAULT_MAX_DRAWDOWN_PCT,
    ) -> None:
        super().__init__(name=self._AGENT_NAME, weight=weight, enabled=enabled)
        self.max_portfolio_risk = max_portfolio_risk
        self.max_spread_ratio = max_spread_ratio
        self.max_atr_multiplier = max_atr_multiplier
        self.min_atr_multiplier = min_atr_multiplier
        self.max_daily_trades = max_daily_trades
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consec_losses = max_consec_losses
        self.max_drawdown_pct = max_drawdown_pct
        logger.info(
            "RiskAgent v2 init | max_risk=%.1f%% max_spread=%.1f "
            "max_daily_loss=%.1f%% max_dd=%.1f%%",
            max_portfolio_risk,
            max_spread_ratio,
            max_daily_loss_pct,
            max_drawdown_pct,
        )

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        score = 100.0
        blocked = False
        blocks: List[str] = []
        warnings: List[str] = []
        meta: Dict[str, Any] = {}

        # B-6: Circuit Breaker
        if context.get("circuit_breaker_open", False):
            blocked = True
            blocks.append("BLOCKED: Circuit breaker OPEN")
            meta["circuit_breaker"] = True

        # B-1 / W-1: Portfolio Risk
        portfolio_risk = float(context.get("portfolio_risk_percent", 0.0))
        meta["portfolio_risk"] = portfolio_risk
        if portfolio_risk >= self.max_portfolio_risk:
            blocked = True
            blocks.append(
                f"BLOCKED: Portfolio risk={portfolio_risk:.2f}% >= {self.max_portfolio_risk}%"
            )
        elif portfolio_risk > self.max_portfolio_risk * 0.8:
            score -= 30.0
            warnings.append(f"High portfolio risk={portfolio_risk:.2f}%")

        # B-2 / W-2: Spread
        spread_ratio = float(context.get("spread_ratio", 1.0))
        meta["spread_ratio"] = spread_ratio
        extreme_spread = self.max_spread_ratio * 1.5
        if spread_ratio >= extreme_spread:
            blocked = True
            blocks.append(f"BLOCKED: Spread ratio={spread_ratio:.2f} >= {extreme_spread:.2f}")
        elif spread_ratio > self.max_spread_ratio:
            score -= 20.0
            warnings.append(f"Elevated spread ratio={spread_ratio:.2f}")

        # W-3 / W-4: ATR
        atr_norm = float(context.get("atr_normalized", 1.0))
        meta["atr_normalized"] = atr_norm
        if atr_norm > self.max_atr_multiplier:
            score -= 20.0
            warnings.append(f"Extreme volatility ATR x={atr_norm:.2f}")
        elif atr_norm < self.min_atr_multiplier:
            score -= 10.0
            warnings.append(f"Dead market ATR x={atr_norm:.2f}")

        # B-3: Daily Trades
        daily_trades = int(context.get("daily_trades_count", 0))
        max_daily = int(context.get("max_daily_trades", self.max_daily_trades))
        meta["daily_trades"] = daily_trades
        if daily_trades >= max_daily:
            blocked = True
            blocks.append(f"BLOCKED: Daily trade limit ({daily_trades}/{max_daily})")

        # B-4: Daily Loss
        daily_loss_pct = float(context.get("daily_loss_percent", 0.0))
        max_daily_loss = float(context.get("max_daily_loss_percent", self.max_daily_loss_pct))
        meta["daily_loss_pct"] = daily_loss_pct
        if daily_loss_pct >= max_daily_loss:
            blocked = True
            blocks.append(f"BLOCKED: Daily loss={daily_loss_pct:.2f}% >= {max_daily_loss}%")

        # B-5: Drawdown
        drawdown_pct = float(context.get("drawdown_percent", 0.0))
        meta["drawdown_pct"] = drawdown_pct
        if drawdown_pct >= self.max_drawdown_pct:
            blocked = True
            blocks.append(f"BLOCKED: Drawdown={drawdown_pct:.2f}% >= {self.max_drawdown_pct}%")
        elif drawdown_pct > self.max_drawdown_pct * 0.7:
            score -= 25.0
            warnings.append(f"Elevated drawdown={drawdown_pct:.2f}%")

        # W-5: Consecutive Losses
        consec = int(context.get("consecutive_losses", 0))
        meta["consecutive_losses"] = consec
        if consec >= self.max_consec_losses:
            score -= 30.0
            warnings.append(f"Consecutive losses={consec}")
        elif consec >= 2:
            score -= 10.0

        score = max(0.0, min(100.0, score))
        all_reasons = blocks + warnings

        if blocked:
            return AgentVote(
                score=0.0,
                confidence=100.0,
                direction=context.get("direction", "NEUTRAL"),
                status=AgentStatus.ERROR,
                reason=" | ".join(all_reasons),
                metadata={**meta, "blocked": True, "block_reasons": blocks},
            )

        confidence = 90.0 if not warnings else (65.0 if len(warnings) >= 3 else 80.0)
        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=AgentStatus.OK,
            reason=" | ".join(all_reasons) if all_reasons else "All risk checks passed",
            metadata={**meta, "blocked": False},
        )
