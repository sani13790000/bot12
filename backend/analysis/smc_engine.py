"""
backend/analysis/smc_engine.py
Smart Money Concept (SMC) Engine

Performs comprehensive SMC analysis:
- Market structure (BOS, CHOCH, MSS)
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Liquidity pools
- Premium/Discount zones
- Confluence scoring

Version: 2.0.0 (Production-ready)
"""
from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: datetime
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float = 0.0


@dataclass
class OrderBlock:
    """Order Block zone."""
    high:       float
    low:        float
    direction:  str    # "bullish" | "bearish"
    strength:   float
    timestamp:  datetime
    tested:     bool  = False
    broken:     bool  = False


@dataclass
class FairValueGap:
    """Fair Value Gap (imbalance)."""
    high:       float
    low:        float
    direction:  str    # "bullish" | "bearish"
    timestamp:  datetime
    filled:     bool  = False


@dataclass
class LiquidityPool:
    """Liquidity pool above/below price."""
    price:     float
    direction: str     # "high" | "low"
    strength:  float
    timestamp: datetime
    swept:     bool  = False


@dataclass
class SMCAnalysis:
    """Result of full SMC analysis."""
    bias:           str    # "bullish" | "bearish" | "neutral"
    structure:      str    # "BOS" | "CHOCH" | "RANGE"
    order_blocks:   List[OrderBlock]     = field(default_factory=list)
    fvgs:           List[FairValueGap]   = field(default_factory=list)
    liquidity:      List[LiquidityPool]  = field(default_factory=list)
    premium_zone:   Optional[float]      = None
    discount_zone:  Optional[float]      = None
    equilibrium:    Optional[float]      = None
    confidence:     float = 0.0
    signals:        List[str] = field(default_factory=list)


class SMCEngine:
    """Full SMC analysis engine."""

    def __init__(self, lookback: int = 100):
        self._lookback = lookback
        self._cache: deque = deque(maxlen=lookback)

    def feed(self, candle: Candle) -> None:
        """Add a new candle to the engine."""
        self._cache.append(candle)

    def analyze(self, candles: List[Candle] | None = None) -> SMCAnalysis:
        """Perform full SMC analysis."""
        data = candles or list(self._cache)
        if len(data) < 10:
            return SMCAnalysis(bias="neutral", structure="RANGE", confidence=0.0)

        bias      = self._detect_bias(data)
        structure = self._detect_structure(data)
        obs       = self._find_order_blocks(data)
        fvgs      = self._find_fvgs(data)
        liquidity = self._find_liquidity(data)
        eq        = self._equilibrium(data)
        confidence = self._score(bias, obs, fvgs, liquidity)

        return SMCAnalysis(
            bias          = bias,
            structure     = structure,
            order_blocks  = obs,
            fvgs          = fvgs,
            liquidity     = liquidity,
            premium_zone  = eq * 1.02 if eq else None,
            discount_zone = eq * 0.98 if eq else None,
            equilibrium   = eq,
            confidence    = confidence,
        )

    def _detect_bias(self, candles: List[Candle]) -> str:
        """Detect overall market bias using HH/HL or LH/LL."""
        highs = [c.high for c in candles[-20:]]
        lows  = [c.low  for c in candles[-20:]]
        hh    = all(highs[i] >= highs[i-1] for i in range(1, len(highs)))
        hl    = all(lows[i]  >= lows[i-1]  for i in range(1, len(lows)))
        ll    = all(lows[i]  <= lows[i-1]  for i in range(1, len(lows)))
        lh    = all(highs[i] <= highs[i-1] for i in range(1, len(highs)))
        if hh and hl:
            return "bullish"
        if ll and lh:
            return "bearish"
        return "neutral"

    def _detect_structure(self, candles: List[Candle]) -> str:
        """Detect Break of Structure (BOS) or Change of Character (CHOCH)."""
        if len(candles) < 5:
            return "RANGE"
        recent = candles[-5:]
        closes = [c.close for c in recent]
        highs  = [c.high  for c in recent]
        lows   = [c.low   for c in recent]
        if closes[-1] > max(highs[:-1]):
            return "BOS"
        if closes[-1] < min(lows[:-1]):
            return "CHOCH"
        return "RANGE"

    def _find_order_blocks(self, candles: List[Candle]) -> List[OrderBlock]:
        """Find bullish and bearish order blocks."""
        obs = []
        for i in range(2, len(candles) - 1):
            c = candles[i]
            prev = candles[i - 1]
            nxt  = candles[i + 1]
            # Bullish OB: bearish candle before strong bullish move
            if (prev.close < prev.open and
                    nxt.close > prev.high and
                    nxt.close > c.high):
                obs.append(OrderBlock(
                    high=prev.high, low=prev.low,
                    direction="bullish",
                    strength=abs(nxt.close - prev.high) / prev.high,
                    timestamp=prev.timestamp,
                ))
            # Bearish OB: bullish candle before strong bearish move
            elif (prev.close > prev.open and
                    nxt.close < prev.low and
                    nxt.close < c.low):
                obs.append(OrderBlock(
                    high=prev.high, low=prev.low,
                    direction="bearish",
                    strength=abs(prev.low - nxt.close) / prev.low,
                    timestamp=prev.timestamp,
                ))
        return obs[-5:]  # Return last 5 OBs

    def _find_fvgs(self, candles: List[Candle]) -> List[FairValueGap]:
        """Find Fair Value Gaps (3-candle imbalance)."""
        fvgs = []
        for i in range(1, len(candles) - 1):
            a = candles[i - 1]
            c = candles[i + 1]
            # Bullish FVG: gap between high of [i-1] and low of [i+1]
            if c.low > a.high:
                fvgs.append(FairValueGap(
                    high=c.low, low=a.high,
                    direction="bullish",
                    timestamp=candles[i].timestamp,
                ))
            # Bearish FVG: gap between low of [i-1] and high of [i+1]
            elif c.high < a.low:
                fvgs.append(FairValueGap(
                    high=a.low, low=c.high,
                    direction="bearish",
                    timestamp=candles[i].timestamp,
                ))
        return fvgs[-3:]

    def _find_liquidity(self, candles: List[Candle]) -> List[LiquidityPool]:
        """Find liquidity pools above swing highs and below swing lows."""
        pools = []
        highs = [c.high for c in candles]
        lows  = [c.low  for c in candles]
        # Swing highs
        for i in range(2, len(candles) - 2):
            if highs[i] == max(highs[i-2:i+3]):
                pools.append(LiquidityPool(
                    price=highs[i], direction="high",
                    strength=1.0,
                    timestamp=candles[i].timestamp,
                ))
            if lows[i] == min(lows[i-2:i+3]):
                pools.append(LiquidityPool(
                    price=lows[i], direction="low",
                    strength=1.0,
                    timestamp=candles[i].timestamp,
                ))
        return pools[-6:]

    def _equilibrium(self, candles: List[Candle]) -> Optional[float]:
        """Calculate equilibrium (50% of range)."""
        if not candles:
            return None
        swing_high = max(c.high for c in candles[-50:])
        swing_low  = min(c.low  for c in candles[-50:])
        return (swing_high + swing_low) / 2.0

    def _score(self, bias, obs, fvgs, liquidity) -> float:
        """Calculate confidence score 0.0-1.0."""
        score = 0.0
        if bias != "neutral":       score += 0.3
        if obs:                     score += min(0.3, len(obs) * 0.1)
        if fvgs:                    score += min(0.2, len(fvgs) * 0.07)
        if liquidity:               score += min(0.2, len(liquidity) * 0.04)
        return min(score, 1.0)


smc_engine = SMCEngine()
