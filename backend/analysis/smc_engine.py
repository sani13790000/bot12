"""
SMC (Smart Money Concepts) Engine - Support/Resistance, Fair Value Gaps, Order Blocks.

Detects key market structure elements:
- Support and Resistance levels from swing highs/lows
- Fair Value Gaps (FVG) - imbalances in price
- Order Blocks - accumulation/distribution zones
- Market Structure Breaks (MSB)
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SupportResistance:
    """Support/Resistance level."""
    level: float
    type: str  # 'support' or 'resistance'
    strength: float  # 0-1, how many times touched
    first_touch: datetime
    last_touch: datetime
    touches: int


@dataclass
class FairValueGap:
    """Fair Value Gap (price imbalance)."""
    gap_start: float
    gap_end: float
    direction: str  # 'up' or 'down'
    size_pips: float
    time_formed: datetime
    mitigated: bool = False
    mitigation_time: Optional[datetime] = None


@dataclass
class OrderBlock:
    """Order Block (accumulation/distribution zone)."""
    high: float
    low: float
    direction: str  # 'bullish' or 'bearish'
    time_formed: datetime
    strength: float  # based on volume/time spent


class SMCEngine:
    """Smart Money Concepts analysis engine."""
    
    def __init__(self, min_swing_points: int = 5, fvg_threshold_pips: float = 2.0):
        """
        Initialize SMC Engine.
        
        Args:
            min_swing_points: Minimum bars between swing highs/lows
            fvg_threshold_pips: Minimum gap size to consider as FVG
        """
        self.min_swing_points = min_swing_points
        self.fvg_threshold_pips = fvg_threshold_pips
        self.support_resistance_levels: List[SupportResistance] = []
        self.fair_value_gaps: List[FairValueGap] = []
        self.order_blocks: List[OrderBlock] = []
    
    def detect_support_resistance(
        self,
        df: pd.DataFrame,
        lookback: int = 50,
        tolerance_pips: float = 5.0
    ) -> List[SupportResistance]:
        """
        Detect support and resistance levels from swing highs/lows.
        
        Args:
            df: DataFrame with 'high', 'low', 'close' columns and datetime index
            lookback: Number of bars to analyze
            tolerance_pips: Pip tolerance to group near levels
        
        Returns:
            List of detected S/R levels
        """
        try:
            if len(df) < self.min_swing_points * 2:
                logger.warning(f"Not enough data: {len(df)} bars < {self.min_swing_points * 2}")
                return []
            
            df = df.tail(lookback).copy()
            
            # Find swing highs and lows
            swing_highs = []
            swing_lows = []
            
            for i in range(self.min_swing_points, len(df) - self.min_swing_points):
                # Swing high: peak with lower highs on both sides
                if (df['high'].iloc[i] == df['high'].iloc[i-self.min_swing_points:i].max() and
                    df['high'].iloc[i] == df['high'].iloc[i+1:i+self.min_swing_points+1].max()):
                    swing_highs.append((df.index[i], df['high'].iloc[i]))
                
                # Swing low: valley with higher lows on both sides
                if (df['low'].iloc[i] == df['low'].iloc[i-self.min_swing_points:i].min() and
                    df['low'].iloc[i] == df['low'].iloc[i+1:i+self.min_swing_points+1].min()):
                    swing_lows.append((df.index[i], df['low'].iloc[i]))
            
            # Group levels by tolerance
            levels = []
            for swing_list, level_type in [(swing_highs, 'resistance'), (swing_lows, 'support')]:
                if not swing_list:
                    continue
                
                grouped = {}
                for timestamp, price in swing_list:
                    found_group = False
                    for level_key in list(grouped.keys()):
                        if abs(level_key - price) <= tolerance_pips:
                            grouped[level_key].append((timestamp, price))
                            found_group = True
                            break
                    if not found_group:
                        grouped[price] = [(timestamp, price)]
                
                # Create S/R objects
                for level_price, occurrences in grouped.items():
                    strength = min(1.0, len(occurrences) / 5.0)  # Normalize by 5 touches
                    sr = SupportResistance(
                        level=level_price,
                        type=level_type,
                        strength=strength,
                        first_touch=occurrences[0][0],
                        last_touch=occurrences[-1][0],
                        touches=len(occurrences)
                    )
                    levels.append(sr)
            
            self.support_resistance_levels = levels
            logger.info(f"Detected {len(levels)} S/R levels: {len(swing_highs)} highs, {len(swing_lows)} lows")
            return levels
        
        except Exception as e:
            logger.error(f"Error detecting S/R: {e}")
            return []
    
    def detect_fair_value_gaps(
        self,
        df: pd.DataFrame,
        lookback: int = 50
    ) -> List[FairValueGap]:
        """
        Detect Fair Value Gaps (price imbalances).
        
        FVG occurs when price gaps over support/resistance without touching.
        
        Args:
            df: DataFrame with 'high', 'low', 'open', 'close' columns
            lookback: Number of bars to analyze
        
        Returns:
            List of detected FVGs
        """
        try:
            if len(df) < 3:
                return []
            
            df = df.tail(lookback).copy()
            fvgs = []
            
            for i in range(1, len(df) - 1):
                # Bullish FVG: current low > previous high
                if df['low'].iloc[i] > df['high'].iloc[i-1]:
                    gap_size = df['low'].iloc[i] - df['high'].iloc[i-1]
                    if gap_size >= self.fvg_threshold_pips:
                        fvg = FairValueGap(
                            gap_start=df['high'].iloc[i-1],
                            gap_end=df['low'].iloc[i],
                            direction='up',
                            size_pips=gap_size,
                            time_formed=df.index[i]
                        )
                        fvgs.append(fvg)
                
                # Bearish FVG: current high < previous low
                if df['high'].iloc[i] < df['low'].iloc[i-1]:
                    gap_size = df['low'].iloc[i-1] - df['high'].iloc[i]
                    if gap_size >= self.fvg_threshold_pips:
                        fvg = FairValueGap(
                            gap_start=df['low'].iloc[i-1],
                            gap_end=df['high'].iloc[i],
                            direction='down',
                            size_pips=gap_size,
                            time_formed=df.index[i]
                        )
                        fvgs.append(fvg)
            
            self.fair_value_gaps = fvgs
            logger.info(f"Detected {len(fvgs)} Fair Value Gaps")
            return fvgs
        
        except Exception as e:
            logger.error(f"Error detecting FVGs: {e}")
            return []
    
    def detect_order_blocks(
        self,
        df: pd.DataFrame,
        lookback: int = 50
    ) -> List[OrderBlock]:
        """
        Detect Order Blocks (accumulation/distribution zones).
        
        Order blocks form where smart money accumulates/distributes before major moves.
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of bars to analyze
        
        Returns:
            List of detected order blocks
        """
        try:
            if len(df) < 10:
                return []
            
            df = df.tail(lookback).copy()
            
            # Add volume-weighted strength
            if 'volume' not in df.columns:
                df['volume'] = 1.0
            
            df['volume_norm'] = df['volume'] / df['volume'].max()
            
            blocks = []
            
            # Detect consecutive bars with similar characteristics (potential order blocks)
            for i in range(2, len(df) - 2):
                # Bullish order block: strong rejection at low, volume on up move
                if (df['close'].iloc[i] > df['open'].iloc[i] and  # Up candle
                    df['volume_norm'].iloc[i] > 0.6):  # High volume
                    
                    # Check if price respects this level later
                    block_low = df['low'].iloc[i]
                    block_high = df['high'].iloc[i]
                    
                    block = OrderBlock(
                        high=block_high,
                        low=block_low,
                        direction='bullish',
                        time_formed=df.index[i],
                        strength=df['volume_norm'].iloc[i]
                    )
                    blocks.append(block)
                
                # Bearish order block
                elif (df['close'].iloc[i] < df['open'].iloc[i] and  # Down candle
                      df['volume_norm'].iloc[i] > 0.6):  # High volume
                    
                    block_high = df['high'].iloc[i]
                    block_low = df['low'].iloc[i]
                    
                    block = OrderBlock(
                        high=block_high,
                        low=block_low,
                        direction='bearish',
                        time_formed=df.index[i],
                        strength=df['volume_norm'].iloc[i]
                    )
                    blocks.append(block)
            
            # Remove duplicate/overlapping blocks
            blocks = self._consolidate_blocks(blocks)
            
            self.order_blocks = blocks
            logger.info(f"Detected {len(blocks)} Order Blocks")
            return blocks
        
        except Exception as e:
            logger.error(f"Error detecting order blocks: {e}")
            return []
    
    def _consolidate_blocks(self, blocks: List[OrderBlock]) -> List[OrderBlock]:
        """Consolidate overlapping order blocks."""
        if not blocks:
            return []
        
        consolidated = []
        blocks = sorted(blocks, key=lambda b: b.time_formed)
        
        current_block = blocks[0]
        for block in blocks[1:]:
            # If blocks overlap and same direction, merge them
            if (block.direction == current_block.direction and
                block.low <= current_block.high and
                block.high >= current_block.low):
                
                current_block.low = min(current_block.low, block.low)
                current_block.high = max(current_block.high, block.high)
            else:
                consolidated.append(current_block)
                current_block = block
        
        consolidated.append(current_block)
        return consolidated
    
    def get_nearest_support_resistance(
        self,
        current_price: float,
        distance_pips: float = 100
    ) -> Dict[str, Optional[SupportResistance]]:
        """
        Get nearest support and resistance to current price.
        
        Args:
            current_price: Current market price
            distance_pips: Maximum distance in pips
        
        Returns:
            Dict with 'support' and 'resistance' keys
        """
        support = None
        resistance = None
        
        for level in self.support_resistance_levels:
            # Nearest support below price
            if level.type == 'support' and level.level < current_price:
                if current_price - level.level <= distance_pips:
                    if support is None or level.level > support.level:
                        support = level
            
            # Nearest resistance above price
            elif level.type == 'resistance' and level.level > current_price:
                if level.level - current_price <= distance_pips:
                    if resistance is None or level.level < resistance.level:
                        resistance = level
        
        return {'support': support, 'resistance': resistance}
    
    def clear(self):
        """Clear all detected levels."""
        self.support_resistance_levels.clear()
        self.fair_value_gaps.clear()
        self.order_blocks.clear()
        logger.info("SMCEngine cleared")
