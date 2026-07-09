"""
Price Action Engine - Candlestick patterns and market structure analysis.

Identifies key price action patterns:
- Engulfing patterns
- Pin bars (Hammer, Hanging Man)
- Inside bars
- Breakout patterns
- Trend direction
- Support/Resistance validation

Usage:
    engine = PriceActionEngine()
    patterns = engine.detect_patterns(candles)
    trend = engine.detect_trend(candles)
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class PatternType(StrEnum):
    ENGULFING_BULL = "ENGULFING_BULL"
    ENGULFING_BEAR = "ENGULFING_BEAR"
    HAMMER = "HAMMER"
    HANGING_MAN = "HANGING_MAN"
    INSIDE_BAR = "INSIDE_BAR"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    PIN_BAR_HIGH = "PIN_BAR_HIGH"
    PIN_BAR_LOW = "PIN_BAR_LOW"


class TrendDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"


@dataclass
class Pattern:
    """Detected price action pattern."""
    type: PatternType
    strength: float  # 0-1
    candle_index: int
    description: str


@dataclass
class Trend:
    """Market trend analysis."""
    direction: TrendDirection
    strength: float  # 0-1
    recent_higher_highs: int
    recent_higher_lows: int
    ema_slope: float


class PriceActionEngine:
    """Price action pattern and trend detection engine."""

    def __init__(self, lookback: int = 20, breakout_threshold: float = 0.01):
        """
        Initialize Price Action Engine.

        Args:
            lookback: Number of candles to analyze
            breakout_threshold: Percentage above/below previous high/low for breakout
        """
        self.lookback = lookback
        self.breakout_threshold = breakout_threshold

    def detect_patterns(
        self,
        candles: List[dict],
        lookback: Optional[int] = None
    ) -> List[Pattern]:
        """
        Detect price action patterns in recent candles.

        Args:
            candles: List of candle dicts with 'open', 'high', 'low', 'close'
            lookback: Override default lookback

        Returns:
            List of detected Pattern objects
        """
        if not candles or len(candles) < 3:
            return []

        lookback = lookback or self.lookback
        window = candles[-lookback:] if len(candles) > lookback else candles
        patterns = []

        # Check last 3 candles for patterns
        if len(window) >= 2:
            # Two-candle patterns
            patterns.extend(self._check_engulfing(window))
            patterns.extend(self._check_breakout(window))

        if len(window) >= 1:
            # Single candle patterns
            patterns.extend(self._check_hammer_hanging_man(window))
            patterns.extend(self._check_pin_bars(window))

        # Three-candle patterns
        if len(window) >= 3:
            patterns.extend(self._check_inside_bar(window))

        return sorted(patterns, key=lambda p: p.strength, reverse=True)

    def detect_trend(
        self,
        candles: List[dict]
    ) -> Trend:
        """
        Detect current market trend.

        Args:
            candles: List of candle dicts

        Returns:
            Trend object with direction and strength
        """
        if not candles or len(candles) < 5:
            return Trend(
                direction=TrendDirection.RANGING,
                strength=0.0,
                recent_higher_highs=0,
                recent_higher_lows=0,
                ema_slope=0.0
            )

        closes = np.array([c['close'] for c in candles])
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])

        # Check for higher highs and higher lows (bullish)
        higher_highs = sum(1 for i in range(1, len(highs[-10:])) if highs[-10+i] > highs[-10+i-1])
        higher_lows = sum(1 for i in range(1, len(lows[-10:])) if lows[-10+i] > lows[-10+i-1])

        # Check for lower highs and lower lows (bearish)
        lower_highs = sum(1 for i in range(1, len(highs[-10:])) if highs[-10+i] < highs[-10+i-1])
        lower_lows = sum(1 for i in range(1, len(lows[-10:])) if lows[-10+i] < lows[-10+i-1])

        # Calculate EMA slope
        ema_12 = self._calculate_ema(closes, 12)
        ema_26 = self._calculate_ema(closes, 26)
        ema_slope = (ema_12[-1] - ema_12[-5]) / ema_12[-5] if len(ema_12) > 5 else 0.0

        # Determine trend
        if higher_highs >= 3 and higher_lows >= 2 and ema_slope > 0:
            return Trend(
                direction=TrendDirection.BULLISH,
                strength=min(1.0, (higher_highs + higher_lows) / 10.0),
                recent_higher_highs=higher_highs,
                recent_higher_lows=higher_lows,
                ema_slope=ema_slope
            )
        elif lower_highs >= 3 and lower_lows >= 2 and ema_slope < 0:
            return Trend(
                direction=TrendDirection.BEARISH,
                strength=min(1.0, (lower_highs + lower_lows) / 10.0),
                recent_higher_highs=0,
                recent_higher_lows=0,
                ema_slope=ema_slope
            )
        else:
            return Trend(
                direction=TrendDirection.RANGING,
                strength=0.3,
                recent_higher_highs=0,
                recent_higher_lows=0,
                ema_slope=ema_slope
            )

    @staticmethod
    def _check_engulfing(candles: List[dict]) -> List[Pattern]:
        """Check for bullish/bearish engulfing patterns."""
        patterns = []
        if len(candles) < 2:
            return patterns

        curr = candles[-1]
        prev = candles[-2]

        # Bullish engulfing
        if prev['close'] < prev['open'] and curr['close'] > curr['open']:
            if curr['open'] < prev['close'] and curr['close'] > prev['open']:
                patterns.append(Pattern(
                    type=PatternType.ENGULFING_BULL,
                    strength=0.8,
                    candle_index=len(candles) - 1,
                    description="Bullish engulfing pattern detected"
                ))

        # Bearish engulfing
        if prev['close'] > prev['open'] and curr['close'] < curr['open']:
            if curr['open'] > prev['close'] and curr['close'] < prev['open']:
                patterns.append(Pattern(
                    type=PatternType.ENGULFING_BEAR,
                    strength=0.8,
                    candle_index=len(candles) - 1,
                    description="Bearish engulfing pattern detected"
                ))

        return patterns

    def _check_breakout(self, candles: List[dict]) -> List[Pattern]:
        """Check for breakout patterns."""
        patterns = []
        if len(candles) < 3:
            return patterns

        curr = candles[-1]
        prev_high = max(c['high'] for c in candles[:-1])
        prev_low = min(c['low'] for c in candles[:-1])

        # Breakout up
        if curr['close'] > prev_high * (1 + self.breakout_threshold):
            patterns.append(Pattern(
                type=PatternType.BREAKOUT_UP,
                strength=0.7,
                candle_index=len(candles) - 1,
                description="Bullish breakout detected"
            ))

        # Breakout down
        if curr['close'] < prev_low * (1 - self.breakout_threshold):
            patterns.append(Pattern(
                type=PatternType.BREAKOUT_DOWN,
                strength=0.7,
                candle_index=len(candles) - 1,
                description="Bearish breakout detected"
            ))

        return patterns

    @staticmethod
    def _check_hammer_hanging_man(candles: List[dict]) -> List[Pattern]:
        """Check for hammer and hanging man patterns."""
        patterns = []
        if not candles:
            return patterns

        curr = candles[-1]
        body_height = abs(curr['close'] - curr['open'])
        lower_wick = min(curr['open'], curr['close']) - curr['low']
        upper_wick = curr['high'] - max(curr['open'], curr['close'])

        # Hammer (small body, long lower wick, at bottom)
        if lower_wick > body_height * 2 and upper_wick < body_height:
            patterns.append(Pattern(
                type=PatternType.HAMMER,
                strength=0.65,
                candle_index=len(candles) - 1,
                description="Hammer pattern (potential reversal up)"
            ))

        # Hanging man (small body, long lower wick, at top)
        if lower_wick > body_height * 2 and upper_wick < body_height and curr['close'] > curr['open']:
            patterns.append(Pattern(
                type=PatternType.HANGING_MAN,
                strength=0.65,
                candle_index=len(candles) - 1,
                description="Hanging man pattern (potential reversal down)"
            ))

        return patterns

    @staticmethod
    def _check_pin_bars(candles: List[dict]) -> List[Pattern]:
        """Check for pin bar patterns."""
        patterns = []
        if not candles:
            return patterns

        curr = candles[-1]
        total_range = curr['high'] - curr['low']
        body_height = abs(curr['close'] - curr['open'])

        if total_range == 0 or body_height / total_range < 0.3:
            return patterns

        lower_wick = min(curr['open'], curr['close']) - curr['low']
        upper_wick = curr['high'] - max(curr['open'], curr['close'])

        # Pin bar high (rejection from highs)
        if upper_wick > total_range * 0.6 and lower_wick < total_range * 0.2:
            patterns.append(Pattern(
                type=PatternType.PIN_BAR_HIGH,
                strength=0.75,
                candle_index=len(candles) - 1,
                description="Pin bar at resistance (reversal signal)"
            ))

        # Pin bar low (rejection from lows)
        if lower_wick > total_range * 0.6 and upper_wick < total_range * 0.2:
            patterns.append(Pattern(
                type=PatternType.PIN_BAR_LOW,
                strength=0.75,
                candle_index=len(candles) - 1,
                description="Pin bar at support (reversal signal)"
            ))

        return patterns

    @staticmethod
    def _check_inside_bar(candles: List[dict]) -> List[Pattern]:
        """Check for inside bar pattern (consolidation)."""
        patterns = []
        if len(candles) < 2:
            return patterns

        curr = candles[-1]
        prev = candles[-2]

        # Inside bar: current high < prev high AND current low > prev low
        if curr['high'] < prev['high'] and curr['low'] > prev['low']:
            patterns.append(Pattern(
                type=PatternType.INSIDE_BAR,
                strength=0.5,
                candle_index=len(candles) - 1,
                description="Inside bar pattern (consolidation)"
            ))

        return patterns

    @staticmethod
    def _calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA for given period."""
        if len(prices) < period:
            return prices

        ema = np.zeros(len(prices))
        multiplier = 2.0 / (period + 1)
        ema[period - 1] = np.mean(prices[:period])

        for i in range(period, len(prices)):
            ema[i] = (prices[i] * multiplier) + (ema[i - 1] * (1 - multiplier))

        return ema
