from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SMCBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SMCStructureEvent(str, Enum):
    """Enum اصلی — برای استفاده داخلی SMCEngine."""
    BOS   = "BOS"
    CHoCH = "CHoCH"
    NONE  = "NONE"


@dataclass
class SwingLevel:
    """PHASE2-S1: نقطه swing در ساختار بازار."""
    price:     float
    index:     int
    is_high:   bool
    strength:  float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.strength = max(0.0, min(1.0, self.strength))


@dataclass
class StructureEvent:
    """PHASE2-S2: رویداد ساختاری بازار."""
    event_type: str
    direction:  str
    price:      float    = 0.0
    index:      int      = 0
    timestamp:  datetime = field(default_factory=datetime.utcnow)


@dataclass
class BlockZone:
    """PHASE2-S1: Order Block zone."""
    zone_type: str
    high:      float
    low:       float
    index:     int
    strength:  float = 0.5
    is_valid:  bool  = True
    mitigated: bool  = False

    def __post_init__(self):
        self.strength = max(0.0, min(1.0, self.strength))

    def contains_price(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class FVGZone:
    """PHASE2-S1: Fair Value Gap zone."""
    zone_type: str
    high:      float
    low:       float
    index:     int
    is_filled: bool  = False
    fill_pct:  float = 0.0

    @property
    def size(self) -> float:
        return max(0.0, self.high - self.low)

    def contains_price(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class SMCResult:
    """PHASE2-S1: نتیجه کامل تحلیل SMC."""
    trend:            str
    bias:             str
    structure_events: List[StructureEvent]   = field(default_factory=list)
    swing_highs:      List[SwingLevel]       = field(default_factory=list)
    swing_lows:       List[SwingLevel]       = field(default_factory=list)
    order_blocks:     List[BlockZone]        = field(default_factory=list)
    fvg_zones:        List[FVGZone]          = field(default_factory=list)
    liquidity_levels: List[Dict[str, Any]]   = field(default_factory=list)
    score:            float                  = 0.0
    confidence:       float                  = 0.0
    notes:            List[str]              = field(default_factory=list)
    symbol:           str                    = ""
    timeframe:        str                    = ""


@dataclass
class Candle:
    timestamp: str
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float = 0.0

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
    index:     int
    timestamp: str
    high:      float
    low:       float
    direction: str
    strength:  float
    mitigated: bool = False

    def contains_price(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class FairValueGap:
    index:     int
    timestamp: str
    top:       float
    bottom:    float
    direction: str
    filled:    bool  = False
    fill_pct:  float = 0.0

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class LiquidityZone:
    price:     float
    zone_type: str
    strength:  float
    swept:     bool = False


@dataclass
class SMCAnalysis:
    bias:             SMCBias
    structure_event:  SMCStructureEvent
    order_blocks:     List[OrderBlock]
    fvgs:             List[FairValueGap]
    liquidity:        List[LiquidityZone]
    swing_high:       Optional[float]
    swing_low:        Optional[float]
    confidence:       float
    notes:            List[str] = field(default_factory=list)


class SMCEngine:
    """موتور تحلیل Smart Money Concepts — API داخلی."""

    def __init__(self, ob_lookback: int = 5, fvg_min_size: float = 0.0002,
                 swing_lookback: int = 10, min_impulse: float = 0.0005) -> None:
        self.ob_lookback    = ob_lookback
        self.fvg_min_size   = fvg_min_size
        self.swing_lookback = swing_lookback
        self.min_impulse    = min_impulse

    def analyse(self, candles: List[Candle]) -> SMCAnalysis:
        if len(candles) < 20:
            raise ValueError(f"حداقل ۲۰ کندل لازم است، {len(candles)} داده شد")
        swing_high, swing_low = self._find_swings(candles)
        bias            = self._determine_bias(candles, swing_high, swing_low)
        order_blocks    = self._find_order_blocks(candles)
        fvgs            = self._find_fvgs(candles)
        liquidity       = self._find_liquidity(candles)
        structure_event = self._detect_structure_event(candles, swing_high, swing_low)
        confidence      = self._calculate_confidence(bias, order_blocks, fvgs, structure_event)
        notes           = self._generate_notes(bias, order_blocks, fvgs, structure_event, confidence)
        return SMCAnalysis(
            bias=bias, structure_event=structure_event,
            order_blocks=order_blocks, fvgs=fvgs, liquidity=liquidity,
            swing_high=swing_high, swing_low=swing_low,
            confidence=confidence, notes=notes,
        )

    def _find_swings(self, candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
        n  = len(candles)
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

    def _determine_bias(self, candles, swing_high, swing_low) -> SMCBias:
        recent = candles[-self.swing_lookback:]
        highs  = [c.high for c in recent]
        lows   = [c.low  for c in recent]
        if highs[-1] > highs[0] and lows[-1] > lows[0]:
            return SMCBias.BULLISH
        if lows[-1] < lows[0] and highs[-1] < highs[0]:
            return SMCBias.BEARISH
        return SMCBias.NEUTRAL

    def _find_order_blocks(self, candles: List[Candle]) -> List[OrderBlock]:
        blocks: List[OrderBlock] = []
        n = len(candles)
        for i in range(1, n - self.ob_lookback):
            impulse = self._measure_impulse(candles, i + 1, i + self.ob_lookback)
            if abs(impulse) < self.min_impulse:
                continue
            c = candles[i]
            if impulse > 0 and c.is_bearish:
                blocks.append(OrderBlock(i, c.timestamp, c.high, c.low, "BULLISH",
                    min(1.0, abs(impulse) / (self.min_impulse * 5))))
            elif impulse < 0 and c.is_bullish:
                blocks.append(OrderBlock(i, c.timestamp, c.high, c.low, "BEARISH",
                    min(1.0, abs(impulse) / (self.min_impulse * 5))))
        last = candles[-1].close
        for ob in blocks:
            if ob.contains_price(last):
                ob.mitigated = True
        blocks.sort(key=lambda b: (b.strength, b.index), reverse=True)
        return blocks[:5]

    def _measure_impulse(self, candles, start, end) -> float:
        if start >= len(candles) or end > len(candles):
            return 0.0
        s = candles[start:end]
        return (s[-1].close - s[0].open) if s else 0.0

    def _find_fvgs(self, candles: List[Candle]) -> List[FairValueGap]:
        gaps: List[FairValueGap] = []
        last = candles[-1].close
        for i in range(1, len(candles) - 1):
            prev, mid, nxt = candles[i - 1], candles[i], candles[i + 1]
            if nxt.low > prev.high and (nxt.low - prev.high) >= self.fvg_min_size:
                fvg = FairValueGap(i, mid.timestamp, nxt.low, prev.high, "BULLISH")
                if last <= fvg.top:
                    pen = max(0.0, last - fvg.bottom)
                    fvg.fill_pct = min(1.0, pen / fvg.size) if fvg.size else 0.0
                    fvg.filled = fvg.fill_pct >= 0.5
                gaps.append(fvg)
            elif nxt.high < prev.low and (prev.low - nxt.high) >= self.fvg_min_size:
                fvg = FairValueGap(i, mid.timestamp, prev.low, nxt.high, "BEARISH")
                if last >= fvg.bottom:
                    pen = max(0.0, fvg.top - last)
                    fvg.fill_pct = min(1.0, pen / fvg.size) if fvg.size else 0.0
                    fvg.filled = fvg.fill_pct >= 0.5
                gaps.append(fvg)
        unfilled = [g for g in gaps if not g.filled]
        return unfilled[-5:]

    def _find_liquidity(self, candles: List[Candle]) -> List[LiquidityZone]:
        zones: List[LiquidityZone] = []
        highs: Dict[float, int] = {}
        lows:  Dict[float, int] = {}
        tol  = 0.0002
        last = candles[-1].close
        for c in candles:
            matched = False
            for p in list(highs):
                if abs(c.high - p) <= tol:
                    highs[p] += 1
                    matched = True
                    break
            if not matched:
                highs[c.high] = 1
            matched = False
            for p in list(lows):
                if abs(c.low - p) <= tol:
                    lows[p] += 1
                    matched = True
                    break
            if not matched:
                lows[c.low] = 1
        for p, cnt in highs.items():
            if cnt >= 2:
                zones.append(LiquidityZone(p, "BSL", float(cnt), last > p))
        for p, cnt in lows.items():
            if cnt >= 2:
                zones.append(LiquidityZone(p, "SSL", float(cnt), last < p))
        zones.sort(key=lambda z: z.strength, reverse=True)
        return zones[:10]

    def _detect_structure_event(self, candles, swing_high, swing_low) -> SMCStructureEvent:
        if swing_high is None or swing_low is None:
            return SMCStructureEvent.NONE
        rh = max(c.high for c in candles[-5:])
        rl = min(c.low  for c in candles[-5:])
        if rh > swing_high or rl < swing_low:
            return SMCStructureEvent.CHoCH
        mid = (swing_high + swing_low) / 2
        cur = candles[-1].close
        if cur > mid and rh > swing_high * 0.995:
            return SMCStructureEvent.BOS
        if cur < mid and rl < swing_low * 1.005:
            return SMCStructureEvent.BOS
        return SMCStructureEvent.NONE

    def _calculate_confidence(self, bias, order_blocks, fvgs, structure_event) -> float:
        score = 0.0
        if bias != SMCBias.NEUTRAL:
            score += 0.30
        strong = [ob for ob in order_blocks if ob.strength > 0.6 and not ob.mitigated]
        if strong:
            score += min(0.25, 0.10 * len(strong))
        if fvgs:
            score += min(0.20, 0.08 * len(fvgs))
        if structure_event == SMCStructureEvent.BOS:
            score += 0.15
        elif structure_event == SMCStructureEvent.CHoCH:
            score += 0.25
        return min(1.0, score)

    def _generate_notes(self, bias, order_blocks, fvgs, structure_event, confidence) -> List[str]:
        notes = [f"Bias بازار: {bias.value}"]
        if structure_event != SMCStructureEvent.NONE:
            notes.append(f"رویداد ساختاری: {structure_event.value}")
        active = [ob for ob in order_blocks if not ob.mitigated]
        if active:
            notes.append(f"{len(active)} Order Block فعال")
        if fvgs:
            notes.append(f"{len(fvgs)} FVG نزدیک")
        if confidence >= 0.75:
            notes.append("✅ سیگنال با اطمینان بالا")
        elif confidence >= 0.50:
            notes.append("⚠️ سیگنال متوسط — تایید بیشتر توصیه می‌شود")
        else:
            notes.append("❌ اطمینان پایین — از معامله خودداری کنید")
        return notes


def _market_data_to_candles(market_data: Dict[str, Any]) -> List[Candle]:
    raw = market_data.get("candles", {})
    if not isinstance(raw, dict):
        return []
    timestamps = raw.get("timestamps", [])
    opens      = raw.get("opens",      [])
    highs      = raw.get("highs",      [])
    lows       = raw.get("lows",       [])
    closes     = raw.get("closes",     [])
    volumes    = raw.get("volumes",    [])
    n = min(len(opens), len(highs), len(lows), len(closes))
    if n == 0:
        return []
    candles = []
    for i in range(n):
        ts = str(timestamps[i]) if i < len(timestamps) else str(i)
        candles.append(Candle(
            timestamp=ts,
            open=float(opens[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            close=float(closes[i]),
            volume=float(volumes[i]) if i < len(volumes) else 0.0,
        ))
    return candles


def _smc_analysis_to_result(analysis: SMCAnalysis, candles: List[Candle],
                             symbol: str = "", timeframe: str = "") -> SMCResult:
    bias_map = {SMCBias.BULLISH: "bullish", SMCBias.BEARISH: "bearish", SMCBias.NEUTRAL: "sideways"}
    trend = bias_map.get(analysis.bias, "sideways")
    structure_events: List[StructureEvent] = []
    if analysis.structure_event != SMCStructureEvent.NONE:
        direction = "bullish" if analysis.bias == SMCBias.BULLISH else "bearish"
        price = candles[-1].close if candles else 0.0
        structure_events.append(StructureEvent(
            event_type=analysis.structure_event.value,
            direction=direction, price=price, index=len(candles) - 1,
        ))
    swing_highs = [SwingLevel(price=analysis.swing_high, index=0, is_high=True, strength=0.8)] \
        if analysis.swing_high is not None else []
    swing_lows  = [SwingLevel(price=analysis.swing_low,  index=0, is_high=False, strength=0.8)] \
        if analysis.swing_low  is not None else []
    block_zones = [
        BlockZone(zone_type="bullish_ob" if ob.direction == "BULLISH" else "bearish_ob",
                  high=ob.high, low=ob.low, index=ob.index, strength=ob.strength,
                  is_valid=not ob.mitigated, mitigated=ob.mitigated)
        for ob in analysis.order_blocks
    ]
    fvg_zones = [
        FVGZone(zone_type="bullish_fvg" if f.direction == "BULLISH" else "bearish_fvg",
                high=f.top, low=f.bottom, index=f.index,
                is_filled=f.filled, fill_pct=f.fill_pct)
        for f in analysis.fvgs
    ]
    liquidity_levels = [
        {"price": z.price, "type": z.zone_type, "strength": z.strength, "swept": z.swept}
        for z in analysis.liquidity
    ]
    return SMCResult(
        trend=trend, bias=analysis.bias.value,
        structure_events=structure_events, swing_highs=swing_highs, swing_lows=swing_lows,
        order_blocks=block_zones, fvg_zones=fvg_zones, liquidity_levels=liquidity_levels,
        score=round(analysis.confidence * 100, 1), confidence=analysis.confidence,
        notes=analysis.notes, symbol=symbol, timeframe=timeframe,
    )


class MarketStructureAnalyzer:
    """PHASE2-S3: تحلیل‌گر ساختار بازار با Public API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._engine = SMCEngine(
            swing_lookback=cfg.get("swing_lookback", 10),
            min_impulse=cfg.get("min_swing_size", 0.0005),
            ob_lookback=cfg.get("ob_lookback", 5),
            fvg_min_size=cfg.get("fvg_min_size", 0.0002),
        )

    def analyze(self, market_data: Dict[str, Any]) -> SMCResult:
        symbol    = market_data.get("symbol", "")
        timeframe = market_data.get("timeframe", "")
        candles   = _market_data_to_candles(market_data)
        if len(candles) < 5:
            return SMCResult(trend="sideways", bias="NEUTRAL", symbol=symbol, timeframe=timeframe,
                             notes=["داده ناکافی برای تحلیل"])
        if len(candles) < 20:
            closes = [c.close for c in candles]
            if closes[-1] > closes[0]:
                trend, bias = "bullish", "BULLISH"
            elif closes[-1] < closes[0]:
                trend, bias = "bearish", "BEARISH"
            else:
                trend, bias = "sideways", "NEUTRAL"
            return SMCResult(trend=trend, bias=bias, symbol=symbol, timeframe=timeframe,
                             score=30.0, confidence=0.3,
                             notes=[f"تحلیل محدود: {len(candles)} کندل"])
        try:
            analysis = self._engine.analyse(candles)
            return _smc_analysis_to_result(analysis, candles, symbol, timeframe)
        except Exception as exc:
            logger.warning("[MarketStructureAnalyzer] %s", exc)
            return SMCResult(trend="sideways", bias="NEUTRAL", symbol=symbol, timeframe=timeframe,
                             notes=[f"خطا: {exc}"])


class LiquidityAnalyzer:
    """PHASE2-S4: تحلیل‌گر نقدینگی."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._cfg = config or {}
        self._min_touches = self._cfg.get("min_touches", 2)

    def analyze(self, market_data: Dict[str, Any]) -> SMCResult:
        symbol    = market_data.get("symbol", "")
        timeframe = market_data.get("timeframe", "")
        candles   = _market_data_to_candles(market_data)
        if len(candles) < 5:
            return SMCResult(trend="sideways", bias="NEUTRAL", symbol=symbol, timeframe=timeframe)
        levels = self._find_levels(candles)
        closes = [c.close for c in candles]
        mid    = len(closes) // 2
        if closes[-1] > closes[mid]:  trend, bias = "bullish", "BULLISH"
        elif closes[-1] < closes[mid]: trend, bias = "bearish", "BEARISH"
        else:                          trend, bias = "sideways", "NEUTRAL"
        return SMCResult(trend=trend, bias=bias, liquidity_levels=levels,
                         symbol=symbol, timeframe=timeframe,
                         score=min(100.0, len(levels) * 10.0),
                         confidence=min(1.0, len(levels) * 0.1))

    def _find_levels(self, candles: List[Candle]) -> List[Dict[str, Any]]:
        highs: Dict[float, int] = {}
        lows:  Dict[float, int] = {}
        tol  = 0.0002
        last = candles[-1].close
        for c in candles:
            matched = False
            for p in list(highs):
                if abs(c.high - p) <= tol:
                    highs[p] += 1; matched = True; break
            if not matched: highs[c.high] = 1
            matched = False
            for p in list(lows):
                if abs(c.low - p) <= tol:
                    lows[p] += 1; matched = True; break
            if not matched: lows[c.low] = 1
        levels = []
        for p, cnt in highs.items():
            if cnt >= self._min_touches:
                levels.append({"price": p, "type": "BSL", "strength": float(cnt), "swept": last > p})
        for p, cnt in lows.items():
            if cnt >= self._min_touches:
                levels.append({"price": p, "type": "SSL", "strength": float(cnt), "swept": last < p})
        levels.sort(key=lambda x: x["strength"], reverse=True)
        return levels[:10]


class OrderBlockAnalyzer:
    """PHASE2-S5: تحلیل‌گر Order Block."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._engine = SMCEngine(ob_lookback=cfg.get("ob_lookback", 5),
                                  min_impulse=cfg.get("min_impulse", 0.0005))

    def analyze(self, market_data: Dict[str, Any]) -> SMCResult:
        symbol    = market_data.get("symbol", "")
        timeframe = market_data.get("timeframe", "")
        candles   = _market_data_to_candles(market_data)
        if len(candles) < 10:
            return SMCResult(trend="sideways", bias="NEUTRAL", symbol=symbol, timeframe=timeframe)
        blocks = self._engine._find_order_blocks(candles)
        bias   = self._engine._determine_bias(candles, None, None)
        block_zones = [
            BlockZone(zone_type="bullish_ob" if ob.direction == "BULLISH" else "bearish_ob",
                      high=ob.high, low=ob.low, index=ob.index, strength=ob.strength,
                      is_valid=not ob.mitigated, mitigated=ob.mitigated)
            for ob in blocks
        ]
        trend_map = {SMCBias.BULLISH: "bullish", SMCBias.BEARISH: "bearish", SMCBias.NEUTRAL: "sideways"}
        return SMCResult(trend=trend_map.get(bias, "sideways"), bias=bias.value,
                         order_blocks=block_zones, symbol=symbol, timeframe=timeframe,
                         score=min(100.0, len(block_zones) * 20.0),
                         confidence=min(1.0, len(block_zones) * 0.2))


class FVGAnalyzer:
    """PHASE2-S6: تحلیل‌گر Fair Value Gap."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._engine = SMCEngine(fvg_min_size=cfg.get("fvg_min_size", 0.0002))

    def analyze(self, market_data: Dict[str, Any]) -> SMCResult:
        symbol    = market_data.get("symbol", "")
        timeframe = market_data.get("timeframe", "")
        candles   = _market_data_to_candles(market_data)
        if len(candles) < 3:
            return SMCResult(trend="sideways", bias="NEUTRAL", symbol=symbol, timeframe=timeframe)
        fvgs = self._engine._find_fvgs(candles)
        bias = self._engine._determine_bias(candles, None, None) if len(candles) >= 10 else SMCBias.NEUTRAL
        fvg_zones = [
            FVGZone(zone_type="bullish_fvg" if f.direction == "BULLISH" else "bearish_fvg",
                    high=f.top, low=f.bottom, index=f.index,
                    is_filled=f.filled, fill_pct=f.fill_pct)
            for f in fvgs
        ]
        trend_map = {SMCBias.BULLISH: "bullish", SMCBias.BEARISH: "bearish", SMCBias.NEUTRAL: "sideways"}
        return SMCResult(trend=trend_map.get(bias, "sideways"), bias=bias.value,
                         fvg_zones=fvg_zones, symbol=symbol, timeframe=timeframe,
                         score=min(100.0, len(fvg_zones) * 15.0),
                         confidence=min(1.0, len(fvg_zones) * 0.15))


_KILL_ZONES: Dict[str, Tuple[int, int]] = {
    "asian_open":    (0,  3),
    "london_open":   (6,  10),
    "new_york_open": (12, 16),
    "london_close":  (15, 17),
}
_DEAD_HOURS = [(17, 24), (0, 1)]


class KillZoneAnalyzer:
    """PHASE2-S7: تحلیل‌گر Kill Zone."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._kill_zones = cfg.get("kill_zones", _KILL_ZONES)

    def is_kill_zone(self, hour_utc: int) -> Dict[str, Any]:
        for zone_name, (start, end) in self._kill_zones.items():
            if start <= hour_utc < end:
                return {"is_active": True, "zone_name": zone_name, "hour": hour_utc,
                        "description": f"Kill Zone: {zone_name} ({start}:00–{end}:00 UTC)"}
        for start, end in _DEAD_HOURS:
            if start <= hour_utc < end:
                return {"is_active": False, "zone_name": "dead_zone", "hour": hour_utc,
                        "description": f"Dead Zone: {hour_utc}:00 UTC"}
        return {"is_active": False, "zone_name": "transition", "hour": hour_utc,
                "description": f"ساعت انتقال: {hour_utc}:00 UTC"}

    def get_current_zone(self, hour_utc: int) -> str:
        return self.is_kill_zone(hour_utc).get("zone_name", "unknown")

    def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        from datetime import datetime, timezone
        hour = market_data.get("hour_utc", datetime.now(timezone.utc).hour)
        return self.is_kill_zone(hour)


smc_engine = SMCEngine()
