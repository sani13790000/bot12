"""Galaxy Vast AI Trading Platform — AI Explainability Engine.

Explains every trade decision using:
- BOS / CHOCH
- Order Block (OB)
- Fair Value Gap (FVG)
- Liquidity Sweep
- Premium / Discount
- AI confidence score per agent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.research.backtest.engine import CandleData


@dataclass
class SMCExplanation:
    bos_detected: bool = False
    choch_detected: bool = False
    order_block_count: int = 0
    fvg_count: int = 0
    liquidity_sweep: bool = False
    premium_discount_zone: Optional[str] = None
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bos_detected": self.bos_detected,
            "choch_detected": self.choch_detected,
            "order_block_count": self.order_block_count,
            "fvg_count": self.fvg_count,
            "liquidity_sweep": self.liquidity_sweep,
            "premium_discount_zone": self.premium_discount_zone,
            "score": round(self.score, 2),
        }


@dataclass
class TradeExplanation:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float
    smc: SMCExplanation = field(default_factory=SMCExplanation)
    reasons: List[str] = field(default_factory=list)
    agent_scores: Dict[str, float] = field(default_factory=dict)
    final_decision: str = "NO_TRADE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence_score": round(self.confidence_score, 2),
            "smc": self.smc.to_dict(),
            "reasons": self.reasons,
            "agent_scores": self.agent_scores,
            "final_decision": self.final_decision,
        }


class ExplainabilityEngine:
    """Generates human-readable explanations for AI trade decisions."""

    def __init__(self):
        self._smc_scorer = None
        try:
            from backend.analysis.smc_scoring import SMCScorer
            self._smc_scorer = SMCScorer()
        except Exception:
            self._smc_scorer = None

    def explain_signal(
        self,
        symbol: str,
        signal: Dict[str, Any],
        history: List[CandleData],
        agent_scores: Optional[Dict[str, float]] = None,
    ) -> TradeExplanation:
        direction = str(signal.get("direction", "NO_TRADE")).upper()
        explanation = TradeExplanation(
            symbol=symbol,
            direction=direction,
            entry_price=float(signal.get("entry_price", 0.0)),
            stop_loss=float(signal.get("stop_loss", 0.0)),
            take_profit=float(signal.get("take_profit", 0.0)),
            confidence_score=float(signal.get("confidence", 0.0)),
            agent_scores=agent_scores or {},
            final_decision=direction if direction in ("BUY", "SELL") else "NO_TRADE",
        )

        # SMC features
        smc = self._analyze_smc(history)
        explanation.smc = smc

        # Build human-readable reasons
        reasons = []
        if smc.bos_detected:
            reasons.append("BOS detected — structure continuation")
        if smc.choch_detected:
            reasons.append("CHOCH detected — structure reversal")
        if smc.order_block_count > 0:
            reasons.append(f"{smc.order_block_count} Order Block(s) identified")
        if smc.fvg_count > 0:
            reasons.append(f"{smc.fvg_count} Fair Value Gap(s) present")
        if smc.liquidity_sweep:
            reasons.append("Liquidity sweep detected")
        if smc.premium_discount_zone:
            reasons.append(f"Price in {smc.premium_discount_zone} zone")

        # Agent confidence summary
        if agent_scores:
            top_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            for name, score in top_agents:
                reasons.append(f"{name} confidence: {round(score, 1)}")

        explanation.reasons = reasons
        return explanation

    def _analyze_smc(self, history: List[CandleData]) -> SMCExplanation:
        if len(history) < 10:
            return SMCExplanation()

        smc = SMCExplanation()
        closes = [c.close for c in history]
        highs = [c.high for c in history]
        lows = [c.low for c in history]
        latest = history[-1]

        # BOS: price broke above recent swing high after bullish structure
        recent_high = max(highs[-10:-1])
        recent_low = min(lows[-10:-1])
        if latest.close > recent_high:
            smc.bos_detected = True
        elif latest.close < recent_low:
            smc.choch_detected = True

        # FVG: bullish or bearish gap between candles
        for i in range(2, min(len(history), 50)):
            prev, curr = history[-i - 1], history[-i]
            if prev.high < curr.low:
                smc.fvg_count += 1
            elif curr.high < prev.low:
                smc.fvg_count += 1

        # Order Block: strong impulse candle followed by retracement
        for i in range(3, min(len(history), 30)):
            c = history[-i]
            if abs(c.close - c.open) > 0.5 * (max(highs[-30:]) - min(lows[-30:])):
                smc.order_block_count += 1

        # Liquidity sweep: wick beyond recent high/low then reverse
        if latest.high > recent_high and latest.close < recent_high:
            smc.liquidity_sweep = True
        elif latest.low < recent_low and latest.close > recent_low:
            smc.liquidity_sweep = True

        # Premium / Discount relative to recent range
        range_min = min(lows[-20:])
        range_max = max(highs[-20:])
        if range_max > range_min:
            position = (latest.close - range_min) / (range_max - range_min)
            if position > 0.7:
                smc.premium_discount_zone = "premium"
            elif position < 0.3:
                smc.premium_discount_zone = "discount"
            else:
                smc.premium_discount_zone = "equilibrium"

        smc.score = (
            (10 if smc.bos_detected else 0)
            + (10 if smc.choch_detected else 0)
            + min(smc.order_block_count, 5) * 3
            + min(smc.fvg_count, 5) * 2
            + (8 if smc.liquidity_sweep else 0)
        )
        return smc
