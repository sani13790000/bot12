"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: DecisionEngine

وظیفه:
  تصمیم‌گیری نهایی برای موتود معامله به معامله با ترکیب نتایج:
    • SMCEngine
    • PriceActionEngine
    • XGBoost Predictor

قوانین:
  - اگر همه سه موتور موافق باشند → ورود مجاز
  - اگر دو موتور موافق باشند و اطمینان > 0.65 → ورود مجاز
  - در غیر این صورت → NO_TRADE
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class TradeDirection(str, Enum):
    BUY      = "BUY"
    SELL     = "SELL"
    NO_TRADE = "NO_TRADE"


class DecisionReason(str, Enum):
    ALL_AGREE      = "ALL_AGREE"
    MAJORITY_AGREE = "MAJORITY_AGREE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING    = "CONFLICTING"
    KILL_SWITCH    = "KILL_SWITCH"
    RISK_LIMIT     = "RISK_LIMIT"


@dataclass
class EngineVote:
    engine_name:  str
    direction:    TradeDirection
    confidence:   float
    entry_price:  Optional[float] = None
    sl_price:     Optional[float] = None
    tp_price:     Optional[float] = None
    notes:        List[str] = field(default_factory=list)


@dataclass
class TradeDecision:
    direction:    TradeDirection
    reason:       DecisionReason
    confidence:   float
    entry_price:  Optional[float]
    sl_price:     Optional[float]
    tp_price:     Optional[float]
    risk_reward:  Optional[float]
    votes:        List[EngineVote]
    symbol:       str
    timeframe:    str
    notes:        List[str] = field(default_factory=list)

    @property
    def should_trade(self) -> bool:
        return self.direction != TradeDirection.NO_TRADE

    def to_dict(self) -> dict:
        return {
            "direction":   self.direction.value,
            "reason":      self.reason.value,
            "confidence":  round(self.confidence, 3),
            "entry_price": self.entry_price,
            "sl_price":    self.sl_price,
            "tp_price":    self.tp_price,
            "risk_reward": self.risk_reward,
            "should_trade": self.should_trade,
            "symbol":      self.symbol,
            "timeframe":   self.timeframe,
            "notes":       self.notes,
            "votes": [{"engine": v.engine_name, "direction": v.direction.value,
                       "confidence": round(v.confidence, 3)} for v in self.votes],
        }


class DecisionEngine:
    """
    موتور تصمیم‌گیری نهایی معاملات.

    مثال:
        engine = DecisionEngine(min_confidence=0.65, min_votes=2)
        decision = engine.decide(votes, symbol="EURUSD", timeframe="H1")
        if decision.should_trade:
            execute(decision)
    """

    def __init__(self, min_confidence: float = 0.65,
                 min_votes: int = 2, min_rr: float = 1.5) -> None:
        self.min_confidence = min_confidence
        self.min_votes      = min_votes
        self.min_rr         = min_rr

    def decide(self, votes: List[EngineVote], symbol: str, timeframe: str,
               kill_switch_active: bool = False) -> TradeDecision:
        if kill_switch_active:
            return self._no_trade(votes, symbol, timeframe,
                                  DecisionReason.KILL_SWITCH,
                                  "کیل‌سوییچ فعال است — هیچ معامله‌ای مجاز نیست")
        if not votes:
            return self._no_trade(votes, symbol, timeframe,
                                  DecisionReason.LOW_CONFIDENCE, "هیچ رأیی دریافت نشد")

        buy_votes  = [v for v in votes if v.direction == TradeDirection.BUY]
        sell_votes = [v for v in votes if v.direction == TradeDirection.SELL]

        if len(buy_votes) > len(sell_votes):
            direction, agreeing = TradeDirection.BUY, buy_votes
        elif len(sell_votes) > len(buy_votes):
            direction, agreeing = TradeDirection.SELL, sell_votes
        else:
            return self._no_trade(votes, symbol, timeframe,
                                  DecisionReason.CONFLICTING,
                                  f"رأی‌های متظاد: {len(buy_votes)} BUY vs {len(sell_votes)} SELL")

        if len(agreeing) < self.min_votes:
            return self._no_trade(votes, symbol, timeframe, DecisionReason.LOW_CONFIDENCE,
                                  f"فقط {len(agreeing)} از {self.min_votes} موتور موافق‌اند")

        avg_confidence = sum(v.confidence for v in agreeing) / len(agreeing)
        if avg_confidence < self.min_confidence:
            return self._no_trade(votes, symbol, timeframe, DecisionReason.LOW_CONFIDENCE,
                                  f"اطمینان {avg_confidence:.1%} کمتر از حداقل {self.min_confidence:.1%}")

        entry, sl, tp = self._aggregate_prices(agreeing, direction)
        rr = self._calculate_rr(direction, entry, sl, tp)
        if rr is not None and rr < self.min_rr:
            return self._no_trade(votes, symbol, timeframe, DecisionReason.RISK_LIMIT,
                                  f"R:R {rr:.2f} کمتر از حداقل {self.min_rr:.2f}")

        reason = (DecisionReason.ALL_AGREE if len(agreeing) == len(votes)
                  else DecisionReason.MAJORITY_AGREE)
        notes = [f"{'همه' if reason == DecisionReason.ALL_AGREE else len(agreeing)} موتور موافق‌اند",
                 f"اطمینان: {avg_confidence:.1%}"]
        if rr: notes.append(f"R:R: {rr:.2f}")

        return TradeDecision(direction=direction, reason=reason,
                             confidence=avg_confidence, entry_price=entry,
                             sl_price=sl, tp_price=tp, risk_reward=rr,
                             votes=votes, symbol=symbol, timeframe=timeframe, notes=notes)

    def _aggregate_prices(self, votes: List[EngineVote],
                          direction: TradeDirection) -> tuple:
        entries = [v.entry_price for v in votes if v.entry_price is not None]
        sls     = [v.sl_price    for v in votes if v.sl_price    is not None]
        tps     = [v.tp_price    for v in votes if v.tp_price    is not None]
        return (sum(entries)/len(entries) if entries else None,
                sum(sls)/len(sls)         if sls     else None,
                sum(tps)/len(tps)         if tps     else None)

    def _calculate_rr(self, direction: TradeDirection, entry: Optional[float],
                      sl: Optional[float], tp: Optional[float]) -> Optional[float]:
        if entry is None or sl is None or tp is None: return None
        risk = abs(entry - sl); reward = abs(tp - entry)
        return round(reward / risk, 2) if risk else None

    def _no_trade(self, votes: List[EngineVote], symbol: str, timeframe: str,
                  reason: DecisionReason, note: str) -> TradeDecision:
        logger.info("decision.NO_TRADE reason=%s note=%s", reason.value, note)
        return TradeDecision(direction=TradeDirection.NO_TRADE, reason=reason,
                             confidence=0.0, entry_price=None, sl_price=None,
                             tp_price=None, risk_reward=None, votes=votes,
                             symbol=symbol, timeframe=timeframe, notes=[note])
