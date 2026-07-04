"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: SMCEngine  (Smart Money Concepts)

وظیفه:
  تشخیص ساختارهای قیمتی مبتنی بر مفاهیم Smart Money:
    • Order Blocks
    • Fair Value Gaps
    • Break of Structure
    • Change of Character
    • Liquidity Zones
    • Imbalance

ورودی:  لیست کندل‌ها به فرمت OHLCV
خروجی: سیگنال‌های ساختاری با سطح اطمینان
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class SMCBias(str, Enum):
    BULLISH  = "BULLISH"
    BEARISH  = "BEARISH"
    NEUTRAL  = "NEUTRAL"


class StructureEvent(str, Enum):
    BOS   = "BOS"
    CHoCH = "CHoCH"
    NONE  = "NONE"


@dataclass
class Candle:
    timestamp: str
    open:  float
    high:  float
    low:   float
    close: float
    volume: float = 0.0

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class OrderBlock:
    index:      int
    timestamp:  str
    high:       float
    low:        float
    direction:  str
    strength:   float
    mitigated:  bool = False

    def contains_price(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class FairValueGap:
    index:      int
    timestamp:  str
    top:        float
    bottom:     float
    direction:  str
    filled:     bool = False
    fill_pct:   float = 0.0

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class LiquidityZone:
    price:      float
    zone_type:  str
    strength:   float
    swept:      bool = False


@dataclass
class SMCAnalysis:
    bias:            SMCBias
    structure_event: StructureEvent
    order_blocks:    List[OrderBlock]
    fvgs:            List[FairValueGap]
    liquidity:       List[LiquidityZone]
    swing_high:      Optional[float]
    swing_low:       Optional[float]
    confidence:      float
    notes:           List[str] = field(default_factory=list)


class SMCEngine:
    """
    موتور تحلیل Smart Money Concepts.

    مثال:
        engine = SMCEngine(ob_lookback=5, fvg_min_size=0.0003)
        result = engine.analyse(candles)
        logger.debug("bias=%s confidence=%s", result.bias, result.confidence)
    """

    def __init__(self, ob_lookback: int = 5, fvg_min_size: float = 0.0002,
                 swing_lookback: int = 10, min_impulse: float = 0.0005) -> None:
        self.ob_lookback    = ob_lookback
        self.fvg_min_size   = fvg_min_size
        self.swing_lookback = swing_lookback
        self.min_impulse    = min_impulse

    def analyse(self, candles: List[Candle]) -> SMCAnalysis:
        if len(candles) < 20:
            raise ValueError(f"حداقل 20 کندل لازم است، {len(candles)} داده شد")
        swing_high, swing_low = self._find_swings(candles)
        bias            = self._determine_bias(candles, swing_high, swing_low)
        order_blocks    = self._find_order_blocks(candles)
        fvgs            = self._find_fvgs(candles)
        liquidity       = self._find_liquidity(candles)
        structure_event  = self._detect_structure_event(candles, swing_high, swing_low)
        confidence       = self._calculate_confidence(bias, order_blocks, fvgs, structure_event)
        notes            = self._generate_notes(bias, order_blocks, fvgs, structure_event, confidence)
        return SMCAnalysis(
            bias=bias, structure_event=structure_event, order_blocks=order_blocks,
            fvgs=fvgs, liquidity=liquidity, swing_high=swing_high,
            swing_low=swing_low, confidence=confidence, notes=notes,
        )

    def _find_swings(self, candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
        n = len(candles)
        lb = min(self.swing_lookback, n // 2)
        swing_high: Optional[float] = None
        swing_low:  Optional[float] = None
        for i in range(lb, n - lb):
            highs = [c.high for c in candles[i - lb: i + lb + 1]]
            lows  = [c.low  for c in candles[i - lb: i + lb + 1]]
            if candles[i].high == max(highs):
                if swing_high is None or candles[i].high > swing_high:
                    swing_high = candles[i].high
            if candles[i].low == min(lows):
                if swing_low is None or candles[i].low < swing_low:
                    swing_low = candles[i].low
        return swing_high, swing_low

    def _determine_bias(self, candles: List[Candle],
                        swing_high: Optional[float], swing_low: Optional[float]) -> SMCBias:
        recent = candles[-self.swing_lookback:]
        highs = [c.high for c in recent]
        lows  = [c.low  for c in recent]
        if highs[-1] > highs[0] and lows[-1] > lows[0]: return SMCBias.BULLISH
        if lows[-1] < lows[0] and highs[-1] < highs[0]: return SMCBias.BEARISH
        return SMCBias.NEUTRAL

    def _find_order_blocks(self, candles: List[Candle]) -> List[OrderBlock]:
        blocks: List[OrderBlock] = []
        n = len(candles)
        for i in range(1, n - self.ob_lookback):
            impulse = self._measure_impulse(candles, i + 1, i + self.ob_lookback)
            if abs(impulse) < self.min_impulse: continue
            c = candles[i]
            if impulse > 0 and c.is_bearish:
                blocks.append(OrderBlock(i, c.timestamp, c.high, c.low, "BULLISH",
                                         min(1.0, abs(impulse) / (self.min_impulse * 5))))
            elif impulse < 0 and c.is_bullish:
                blocks.append(OrderBlock(i, c.timestamp, c.high, c.low, "BEARISH",
                                         min(1.0, abs(impulse) / (self.min_impulse * 5))))
        last = candles[-1].close
        for ob in blocks:
            if ob.contains_price(last): ob.mitigated = True
        blocks.sort(key=lambda b: (b.strength, b.index), reverse=True)
        return blocks[:5]

    def _measure_impulse(self, candles: List[Candle], start: int, end: int) -> float:
        if start >= len(candles) or end > len(candles): return 0.0
        s = candles[start:end]
        return (s[-1].close - s[0].open) if s else 0.0

    def _find_fvgs(self, candles: List[Candle]) -> List[FairValueGap]:
        gaps: List[FairValueGap] = []
        last = candles[-1].close
        for i in range(1, len(candles) - 1):
            prev, mid, nxt = candles[i-1], candles[i], candles[i+1]
            if nxt.low > prev.high and (nxt.low - prev.high) >= self.fvg_min_size:
                fvg = FairValueGap(i, mid.timestamp, nxt.low, prev.high, "BULLISH")
                if last <= fvg.top:
                    pen = max(0.0, last - fvg.bottom)
                    fvg.fill_pct = min(1.0, pen / fvg.size) if fvg.size else 0
                    fvg.filled = fvg.fill_pct >= 0.5
                gaps.append(fvg)
            elif nxt.high < prev.low and (prev.low - nxt.high) >= self.fvg_min_size:
                fvg = FairValueGap(i, mid.timestamp, prev.low, nxt.high, "BEARISH")
                if last >= fvg.bottom:
                    pen = max(0.0, fvg.top - last)
                    fvg.fill_pct = min(1.0, pen / fvg.size) if fvg.size else 0
                    fvg.filled = fvg.fill_pct >= 0.5
                gaps.append(fvg)
        unfilled = [g for g in gaps if not g.filled]
        return unfilled[-5:]

    def _find_liquidity(self, candles: List[Candle]) -> List[LiquidityZone]:
        zones: List[LiquidityZone] = []
        highs: dict = {}; lows: dict = {}
        tol = 0.0002
        last = candles[-1].close
        for c in candles:
            found = any(abs(c.high - p) <= tol and (highs.__setitem__(p, highs[p]+1) or True) for p in highs)
            if not found: highs[c.high] = 1
            found = any(abs(c.low - p) <= tol and (lows.__setitem__(p, lows[p]+1) or True) for p in lows)
            if not found: lows[c.low] = 1
        for p, cnt in highs.items():
            if cnt >= 2: zones.append(LiquidityZone(p, "BSL", float(cnt), last > p))
        for p, cnt in lows.items():
            if cnt >= 2: zones.append(LiquidityZone(p, "SSL", float(cnt), last < p))
        zones.sort(key=lambda z: z.strength, reverse=True)
        return zones[:10]

    def _detect_structure_event(self, candles: List[Candle],
                                swing_high: Optional[float], swing_low: Optional[float]) -> StructureEvent:
        if swing_high is None or swing_low is None: return StructureEvent.NONE
        rh = max(c.high for c in candles[-5:])
        rl = min(c.low  for c in candles[-5:])
        if rh > swing_high or rl < swing_low: return StructureEvent.CHoCH
        mid = (swing_high + swing_low) / 2
        cur = candles[-1].close
        if cur > mid and rh > swing_high * 0.995: return StructureEvent.BOS
        if cur < mid and rl  < swing_low  * 1.005: return StructureEvent.BOS
        return StructureEvent.NONE

    def _calculate_confidence(self, bias: SMCBias, order_blocks: List[OrderBlock],
                               fvgs: List[FairValueGap], structure_event: StructureEvent) -> float:
        score = 0.0
        if bias != SMCBias.NEUTRAL: score += 0.30
        strong = [ob for ob in order_blocks if ob.strength > 0.6 and not ob.mitigated]
        if strong: score += min(0.25, 0.10 * len(strong))
        if fvgs:   score += min(0.20, 0.08 * len(fvgs))
        if structure_event == StructureEvent.BOS:   score += 0.15
        elif structure_event == StructureEvent.CHoCH: score += 0.25
        return min(1.0, score)

    def _generate_notes(self, bias: SMCBias, order_blocks: List[OrderBlock],
                        fvgs: List[FairValueGap], structure_event: StructureEvent,
                        confidence: float) -> List[str]:
        notes = [f"Bias بازار: {bias.value}"]
        if structure_event != StructureEvent.NONE:
            notes.append(f"رویداد ساختاری: {structure_event.value}")
        active = [ob for ob in order_blocks if not ob.mitigated]
        if active: notes.append(f"{len(active)} Order Block فعال")
        if fvgs:   notes.append(f"{len(fvgs)} FVG نزدیک")
        if confidence >= 0.75:   notes.append("✅ سیگنال با اطمینان بالا")
        elif confidence >= 0.50: notes.append("⚠️ سیگنال متوسط — تایید بیشتر توصیه می‌شود")
        else:                    notes.append("❌ اطمینان پایین — از معامله خودداری کنید")
        return notes
