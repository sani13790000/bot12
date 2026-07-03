"""
backend/analysis/smc_engine.py
Galaxy Vast AI — Smart Money Concept Engine

این موتور تحلیل جامع SMC را انجام می‌دهد:
  - ساختار بازار: BOS (Break of Structure)، CHOCH (Change of Character)
  - Order Blocks: Bullish OB، Bearish OB، Mitigation Block
  - Fair Value Gap (FVG / Imbalance)
  - نقاط نقدینگی: Equal Highs/Lows، Liquidity Sweep
  - Premium/Discount Zones
  - امتیازدهی ترکیبی برای confluence

اصلاح اعمال‌شده:
  STRESS-TH_FIX: times[-1] on empty times list
  → همه جاها: times[-1] if times else datetime.now(timezone.utc)
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.enums import (
    BlockStatus,
    BlockType,
    FVGType,
    LiquidityType,
    MarketStructure,
    TradingSession,
    TrendDirection,
)
from ..core.logger import get_logger
from ..core.config import settings

logger = get_logger("smc_engine")


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrderBlock:
    """یک Order Block در نمودار."""

    block_type:  BlockType
    high:        float
    low:         float
    open_price:  float
    close_price: float
    created_at:  datetime
    status:      BlockStatus = BlockStatus.ACTIVE
    mitigation:  float       = 0.0
    touches:     int         = 0
    score:       float       = 0.0

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    @property
    def size(self) -> float:
        return self.high - self.low

    def is_price_inside(self, price: float) -> bool:
        return self.low <= price <= self.high

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type":       self.block_type.value,
            "high":       self.high,
            "low":        self.low,
            "midpoint":   self.midpoint,
            "status":     self.status.value,
            "score":      self.score,
            "touches":    self.touches,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class FairValueGap:
    """یک Fair Value Gap (ناکارایی بازار)."""

    fvg_type:   FVGType
    high:       float
    low:        float
    created_at: datetime
    filled:     bool  = False
    fill_pct:   float = 0.0

    @property
    def size(self) -> float:
        return self.high - self.low

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type":       self.fvg_type.value,
            "high":       self.high,
            "low":        self.low,
            "size":       self.size,
            "filled":     self.filled,
            "fill_pct":   self.fill_pct,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class LiquidityLevel:
    """یک سطح نقدینگی (Equal High/Low)."""

    liq_type:  LiquidityType
    price:     float
    strength:  int       = 1
    swept:     bool      = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.liq_type.value, "price": self.price,
                "strength": self.strength, "swept": self.swept}


@dataclass
class MarketStructureEvent:
    """یک رویداد تغییر ساختار بازار."""

    event_type:  MarketStructure
    price:       float
    direction:   TrendDirection
    timestamp:   datetime
    confirmed:   bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event":     self.event_type.value,
            "price":     self.price,
            "direction": self.direction.value,
            "confirmed": self.confirmed,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SMCAnalysis:
    """نتیجه کامل تحلیل SMC."""

    symbol:           str
    timeframe:        str
    trend:            TrendDirection
    market_structure: List[MarketStructureEvent] = field(default_factory=list)
    order_blocks:     List[OrderBlock]            = field(default_factory=list)
    fvgs:             List[FairValueGap]          = field(default_factory=list)
    liquidity:        List[LiquidityLevel]        = field(default_factory=list)
    premium_zone:     Optional[float]             = None
    discount_zone:    Optional[float]             = None
    confluence_score: float                       = 0.0
    session:          Optional[TradingSession]    = None
    analyzed_at:      datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol":           self.symbol,
            "timeframe":        self.timeframe,
            "trend":            self.trend.value,
            "confluence_score": self.confluence_score,
            "order_blocks":     [ob.to_dict() for ob in self.order_blocks
                                  if ob.status == BlockStatus.ACTIVE],
            "fvgs":             [f.to_dict() for f in self.fvgs if not f.filled],
            "liquidity":        [lv.to_dict() for lv in self.liquidity if not lv.swept],
            "premium_zone":     self.premium_zone,
            "discount_zone":    self.discount_zone,
            "analyzed_at":      self.analyzed_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

class SMCEngine:
    """
    موتور تحلیل Smart Money Concept.

    استفاده:
        engine = SMCEngine()
        analysis = engine.analyze(
            symbol="EURUSD", timeframe="H1",
            highs=highs_array, lows=lows_array, closes=closes_array,
        )
    """

    _OB_LOOKBACK      = 10
    _FVG_MIN_SIZE_PCT = 0.0005
    _LIQ_TOLERANCE    = 0.0002
    _SWING_LOOKBACK   = 5

    def __init__(self) -> None:
        self._cache: deque = deque(maxlen=100)

    def analyze(
        self,
        symbol:    str,
        timeframe: str,
        highs:     np.ndarray,
        lows:      np.ndarray,
        closes:    np.ndarray,
        opens:     Optional[np.ndarray] = None,
        times:     Optional[List[datetime]] = None,
        session:   Optional[TradingSession] = None,
    ) -> SMCAnalysis:
        """
        تحلیل کامل SMC.

        highs/lows/closes/opens: آرایه‌های numpy به ترتیب زمانی (قدیمی → جدید)
        """
        if len(highs) < 10:
            logger.warning("[SMC] insufficient data: %d bars", len(highs))
            return SMCAnalysis(symbol=symbol, timeframe=timeframe,
                               trend=TrendDirection.UNDEFINED)

        # STRESS-TH_FIX: اگر times خالی بود
        now = times[-1] if times else datetime.now(timezone.utc)

        result = SMCAnalysis(
            symbol=symbol, timeframe=timeframe,
            trend=TrendDirection.UNDEFINED,
            session=session, analyzed_at=now,
        )

        result.trend            = self._detect_trend(highs, lows, closes)
        result.market_structure = self._find_market_structure(highs, lows, closes, times)
        result.order_blocks     = self._find_order_blocks(
            highs, lows, closes, opens if opens is not None else highs, times
        )
        result.fvgs             = self._find_fvgs(highs, lows, closes, times)
        result.liquidity        = self._find_liquidity(highs, lows, times)
        result.premium_zone, result.discount_zone = self._calc_premium_discount(highs, lows)
        result.confluence_score = self._calc_confluence(result)

        logger.debug(
            "[SMC] %s %s trend=%s obs=%d fvgs=%d score=%.1f",
            symbol, timeframe, result.trend.value,
            len(result.order_blocks), len(result.fvgs), result.confluence_score,
        )
        return result

    def _detect_trend(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> TrendDirection:
        if len(closes) < 20:
            return TrendDirection.UNDEFINED
        recent = closes[-20:]
        ma5    = float(np.mean(recent[-5:]))
        ma20   = float(np.mean(recent))
        swing_highs = [float(highs[i]) for i in range(2, len(highs) - 2)
                       if highs[i] == max(highs[i-2:i+3])]
        swing_lows  = [float(lows[i]) for i in range(2, len(lows) - 2)
                       if lows[i] == min(lows[i-2:i+3])]
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
                return TrendDirection.BULLISH
            if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
                return TrendDirection.BEARISH
        if ma5 > ma20 * 1.0003:
            return TrendDirection.BULLISH
        if ma5 < ma20 * 0.9997:
            return TrendDirection.BEARISH
        return TrendDirection.SIDEWAYS

    def _find_market_structure(
        self,
        highs:  np.ndarray,
        lows:   np.ndarray,
        closes: np.ndarray,
        times:  Optional[List[datetime]],
    ) -> List[MarketStructureEvent]:
        events: List[MarketStructureEvent] = []
        n = len(highs)
        if n < 10:
            return events
        prev_high = prev_low = None
        direction = TrendDirection.UNDEFINED
        lb = self._SWING_LOOKBACK
        for i in range(lb, n):
            ts = times[i] if times and i < len(times) else datetime.now(timezone.utc)
            is_swing_high = float(highs[i]) == float(max(highs[max(0, i-lb):i+1]))
            is_swing_low  = float(lows[i])  == float(min(lows[max(0, i-lb):i+1]))
            if is_swing_high:
                if prev_high is not None:
                    if highs[i] > prev_high:
                        events.append(MarketStructureEvent(
                            event_type=MarketStructure.BOS, price=float(highs[i]),
                            direction=TrendDirection.BULLISH, timestamp=ts, confirmed=True,
                        ))
                    elif highs[i] < prev_high and direction == TrendDirection.BULLISH:
                        events.append(MarketStructureEvent(
                            event_type=MarketStructure.CHOCH, price=float(highs[i]),
                            direction=TrendDirection.BEARISH, timestamp=ts, confirmed=False,
                        ))
                        direction = TrendDirection.BEARISH
                prev_high = float(highs[i])
                direction = TrendDirection.BULLISH
            if is_swing_low:
                if prev_low is not None:
                    if lows[i] < prev_low:
                        events.append(MarketStructureEvent(
                            event_type=MarketStructure.BOS, price=float(lows[i]),
                            direction=TrendDirection.BEARISH, timestamp=ts, confirmed=True,
                        ))
                    elif lows[i] > prev_low and direction == TrendDirection.BEARISH:
                        events.append(MarketStructureEvent(
                            event_type=MarketStructure.CHOCH, price=float(lows[i]),
                            direction=TrendDirection.BULLISH, timestamp=ts, confirmed=False,
                        ))
                        direction = TrendDirection.BULLISH
                prev_low = float(lows[i])
        return events[-20:]

    def _find_order_blocks(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
        opens: np.ndarray, times: Optional[List[datetime]],
    ) -> List[OrderBlock]:
        obs: List[OrderBlock] = []
        n   = len(highs)
        if n < self._OB_LOOKBACK + 3:
            return obs
        for i in range(self._OB_LOOKBACK, n - 2):
            ts = times[i] if times and i < len(times) else datetime.now(timezone.utc)
            # Bearish OB
            if (closes[i] > opens[i] and closes[i+1] < opens[i+1]
                    and closes[i+1] < lows[i] * 0.9995):
                obs.append(OrderBlock(
                    block_type=BlockType.BEARISH_OB,
                    high=float(highs[i]), low=float(lows[i]),
                    open_price=float(opens[i]), close_price=float(closes[i]),
                    created_at=ts,
                    score=self._score_ob(highs, lows, i),
                ))
            # Bullish OB
            if (closes[i] < opens[i] and closes[i+1] > opens[i+1]
                    and closes[i+1] > highs[i] * 1.0005):
                obs.append(OrderBlock(
                    block_type=BlockType.BULLISH_OB,
                    high=float(highs[i]), low=float(lows[i]),
                    open_price=float(opens[i]), close_price=float(closes[i]),
                    created_at=ts,
                    score=self._score_ob(highs, lows, i),
                ))
        obs.sort(key=lambda x: x.score, reverse=True)
        return obs[:10]

    def _find_fvgs(
        self, highs: np.ndarray, lows: np.ndarray,
        closes: np.ndarray, times: Optional[List[datetime]],
    ) -> List[FairValueGap]:
        fvgs: List[FairValueGap] = []
        n    = len(highs)
        if n < 3:
            return fvgs
        for i in range(1, n - 1):
            ts = times[i] if times and i < len(times) else datetime.now(timezone.utc)
            # Bullish FVG
            if lows[i+1] > highs[i-1]:
                gap = float(lows[i+1] - highs[i-1])
                if gap / float(highs[i-1]) >= self._FVG_MIN_SIZE_PCT:
                    fvgs.append(FairValueGap(
                        fvg_type=FVGType.BULLISH,
                        high=float(lows[i+1]), low=float(highs[i-1]),
                        created_at=ts,
                    ))
            # Bearish FVG
            if highs[i+1] < lows[i-1]:
                gap = float(lows[i-1] - highs[i+1])
                if gap / float(lows[i-1]) >= self._FVG_MIN_SIZE_PCT:
                    fvgs.append(FairValueGap(
                        fvg_type=FVGType.BEARISH,
                        high=float(lows[i-1]), low=float(highs[i+1]),
                        created_at=ts,
                    ))
        return fvgs[-15:]

    def _find_liquidity(
        self, highs: np.ndarray, lows: np.ndarray,
        times: Optional[List[datetime]],
    ) -> List[LiquidityLevel]:
        levels: List[LiquidityLevel] = []
        tol    = self._LIQ_TOLERANCE
        n      = len(highs)
        for i in range(n):
            for j in range(i + 1, min(i + 20, n)):
                if abs(highs[i] - highs[j]) / float(highs[i]) < tol:
                    levels.append(LiquidityLevel(
                        liq_type=LiquidityType.EQUAL_HIGHS,
                        price=float((highs[i] + highs[j]) / 2), strength=2,
                    ))
                if float(lows[i]) > 0 and abs(lows[i] - lows[j]) / float(lows[i]) < tol:
                    levels.append(LiquidityLevel(
                        liq_type=LiquidityType.EQUAL_LOWS,
                        price=float((lows[i] + lows[j]) / 2), strength=2,
                    ))
        unique: List[LiquidityLevel] = []
        for lvl in levels:
            if not any(abs(u.price - lvl.price) / lvl.price < tol for u in unique):
                unique.append(lvl)
        return unique[:20]

    def _calc_premium_discount(
        self, highs: np.ndarray, lows: np.ndarray
    ) -> Tuple[float, float]:
        if len(highs) < 2:
            return 0.0, 0.0
        last = min(50, len(highs))
        sh   = float(np.max(highs[-last:]))
        sl   = float(np.min(lows[-last:]))
        mid  = (sh + sl) / 2
        return round(mid + (sh - mid) * 0.5, 5), round(mid - (mid - sl) * 0.5, 5)

    def _score_ob(self, highs: np.ndarray, lows: np.ndarray, index: int) -> float:
        size    = float(highs[index] - lows[index])
        start   = max(0, index - 10)
        avg_rng = float(np.mean(highs[start:index] - lows[start:index])) if index > start else size
        if avg_rng == 0:
            return 50.0
        return round(min(size / avg_rng * 30 + 10, 100), 1)

    def _calc_confluence(self, analysis: SMCAnalysis) -> float:
        score = 0.0
        if analysis.trend in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            score += 20
        high_obs = [ob for ob in analysis.order_blocks if ob.score >= 70]
        score += min(len(high_obs) * 15, 30)
        open_fvgs = [f for f in analysis.fvgs if not f.filled]
        score += min(len(open_fvgs) * 10, 20)
        score += min(len(analysis.liquidity) * 5, 20)
        confirmed_bos = [e for e in analysis.market_structure
                         if e.event_type == MarketStructure.BOS and e.confirmed]
        score += min(len(confirmed_bos) * 5, 10)
        return round(min(score, 100.0), 1)


# Singleton
smc_engine = SMCEngine()
