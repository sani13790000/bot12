"""
SMC (Smart Money Concepts) Engine - Support/Resistance, Fair Value Gaps, Order Blocks.

Detects key market structure elements:
- Support and Resistance levels from swing highs/lows
- Fair Value Gaps (FVG) for potential reversals
- Order Blocks for institutional order placement areas
- Market Structure Breaks (MSB) for trend confirmation

Usage:
    engine = SMCEngine(lookback=50)
    levels = engine.detect_support_resistance(candles)
    fvgs = engine.detect_fair_value_gaps(candles)
    order_blocks = engine.detect_order_blocks(candles)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Level:
    """Support/Resistance level."""
    price: float
    type: str  # 'support' or 'resistance'
    strength: int  # Number of touches
    confirmed: bool = False


@dataclass
class FVG:
    """Fair Value Gap."""
    price_start: float
    price_end: float
    type: str  # 'bullish' or 'bearish'
    candle_index: int


@dataclass
class OrderBlock:
    """Order block - area of institutional buying/selling."""
    price_high: float
    price_low: float
    type: str  # 'buy' or 'sell'
    strength: float  # 0-1 based on volume and momentum


class SMCEngine:
    """Smart Money Concepts detection engine."""

    def __init__(self, lookback: int = 50, tolerance: float = 0.0005):
        """
        Initialize SMC Engine.

        Args:
            lookback: Number of candles to look back for levels
            tolerance: Price tolerance for level matching (default 0.05%)
        """
        self.lookback = lookback
        self.tolerance = tolerance

    def detect_support_resistance(
        self,
        candles: List[dict],
        min_touches: int = 2,
        lookback: Optional[int] = None
    ) -> List[Level]:
        """
        Detect support and resistance levels from swing highs/lows.

        Args:
            candles: List of candle dicts with 'high', 'low', 'close' keys
            min_touches: Minimum number of touches to confirm level
            lookback: Override default lookback window

        Returns:
            List of detected Level objects
        """
        if not candles or len(candles) < 5:
            return []

        lookback = lookback or self.lookback
        window = candles[-lookback:] if len(candles) > lookback else candles

        levels = []
        highs = np.array([c['high'] for c in window])
        lows = np.array([c['low'] for c in window])

        # Find swing highs and lows
        for i in range(1, len(window) - 1):
            # Swing high
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                price = float(highs[i])
                # Count touches within tolerance
                touches = self._count_touches(highs, price, self.tolerance * price)
                if touches >= min_touches:
                    levels.append(Level(
                        price=price,
                        type='resistance',
                        strength=touches,
                        confirmed=touches > min_touches
                    ))

            # Swing low
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                price = float(lows[i])
                # Count touches within tolerance
                touches = self._count_touches(lows, price, self.tolerance * price)
                if touches >= min_touches:
                    levels.append(Level(
                        price=price,
                        type='support',
                        strength=touches,
                        confirmed=touches > min_touches
                    ))

        return self._deduplicate_levels(levels)

    def detect_fair_value_gaps(
        self,
        candles: List[dict]
    ) -> List[FVG]:
        """
        Detect Fair Value Gaps (FVG) - Price gaps without fill.

        Args:
            candles: List of candle dicts

        Returns:
            List of FVG objects
        """
        if not candles or len(candles) < 3:
            return []

        fvgs = []
        for i in range(1, len(candles) - 1):
            curr_high = candles[i]['high']
            curr_low = candles[i]['low']
            next_low = candles[i+1]['low']
            next_high = candles[i+1]['high']
            prev_high = candles[i-1]['high']
            prev_low = candles[i-1]['low']

            # Bullish FVG (gap up)
            if next_low > curr_high and curr_low > prev_high:
                fvgs.append(FVG(
                    price_start=curr_high,
                    price_end=next_low,
                    type='bullish',
                    candle_index=i
                ))

            # Bearish FVG (gap down)
            if next_high < curr_low and curr_high < prev_low:
                fvgs.append(FVG(
                    price_start=curr_low,
                    price_end=next_high,
                    type='bearish',
                    candle_index=i
                ))

        return fvgs

    def detect_order_blocks(
        self,
        candles: List[dict],
        volume_threshold: float = 1.5
    ) -> List[OrderBlock]:
        """
        Detect order blocks - areas of institutional concentration.

        Args:
            candles: List of candle dicts with 'high', 'low', 'close', 'volume'
            volume_threshold: Volume multiplier for significance

        Returns:
            List of OrderBlock objects
        """
        if not candles or len(candles) < 5:
            return []

        order_blocks = []
        volumes = np.array([c.get('volume', 1) for c in candles])
        avg_volume = np.mean(volumes)
        threshold = avg_volume * volume_threshold

        for i in range(1, len(candles) - 1):
            if volumes[i] > threshold:
                # Check if candle is significant in price movement
                curr = candles[i]
                prev = candles[i-1]
                next_c = candles[i+1]

                # Buy order block (rejection from lows)
                if curr['close'] > prev['close'] and next_c['close'] > curr['close']:
                    order_blocks.append(OrderBlock(
                        price_high=curr['high'],
                        price_low=curr['low'],
                        type='buy',
                        strength=min(1.0, volumes[i] / threshold)
                    ))

                # Sell order block (rejection from highs)
                if curr['close'] < prev['close'] and next_c['close'] < curr['close']:
                    order_blocks.append(OrderBlock(
                        price_high=curr['high'],
                        price_low=curr['low'],
                        type='sell',
                        strength=min(1.0, volumes[i] / threshold)
                    ))

        return order_blocks

    def detect_market_structure_breaks(
        self,
        candles: List[dict]
    ) -> Tuple[Optional[str], float]:
        """
        Detect breaks in market structure (trend confirmation).

        Returns:
            Tuple of (direction: 'bullish'/'bearish'/None, confidence: 0-1)
        """
        if not candles or len(candles) < 5:
            return None, 0.0

        highs = np.array([c['high'] for c in candles[-20:]])
        lows = np.array([c['low'] for c in candles[-20:]])

        # Higher highs and higher lows = bullish
        if len(highs) >= 2:
            higher_highs = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
            higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])

            if higher_highs >= 3 and higher_lows >= 3:
                return 'bullish', min(1.0, (higher_highs + higher_lows) / 10.0)

            # Lower highs and lower lows = bearish
            lower_highs = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
            lower_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])

            if lower_highs >= 3 and lower_lows >= 3:
                return 'bearish', min(1.0, (lower_highs + lower_lows) / 10.0)

        return None, 0.0

    @staticmethod
    def _count_touches(prices: np.ndarray, target: float, tolerance: float) -> int:
        """Count how many times price touches a level within tolerance."""
        return int(np.sum((prices >= target - tolerance) & (prices <= target + tolerance)))

    @staticmethod
    def _deduplicate_levels(levels: List[Level], tolerance: float = 0.001) -> List[Level]:
        """Remove duplicate levels that are too close together."""
        if not levels:
            return []

        sorted_levels = sorted(levels, key=lambda x: x.strength, reverse=True)
        deduped = []

        for level in sorted_levels:
            is_duplicate = False
            for existing in deduped:
                if abs(level.price - existing.price) / existing.price < tolerance:
                    is_duplicate = True
                    existing.strength = max(existing.strength, level.strength)
                    break
            if not is_duplicate:
                deduped.append(level)

        return sorted(deduped, key=lambda x: x.price)
