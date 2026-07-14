"""
Price Action Engine - Candlestick patterns and market structure analysis.

Identifies key price action patterns:
- Engulfing patterns
- Pin bars (Hammer, Hanging Man)
- Inside bars
- Breakout patterns
- Trend confirmation
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CandlePattern(Enum):
    """Candlestick patterns."""
    BULLISH_ENGULFING = "bullish_engulfing"
    BEARISH_ENGULFING = "bearish_engulfing"
    HAMMER = "hammer"
    HANGING_MAN = "hanging_man"
    INSIDE_BAR = "inside_bar"
    PIN_BAR_UP = "pin_bar_up"
    PIN_BAR_DOWN = "pin_bar_down"
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"


@dataclass
class PriceActionPattern:
    """Detected price action pattern."""
    pattern: CandlePattern
    timestamp: datetime
    confidence: float  # 0-1
    description: str
    entry_level: float
    stop_loss_level: float


class PriceActionEngine:
    """
    Analyzes price action patterns and market microstructure.
    
    Used to confirm signals from SMC and ML engines.
    """
    
    def __init__(self):
        """Initialize Price Action Engine."""
        self.patterns_history: List[PriceActionPattern] = []
    
    def detect_candlestick_patterns(
        self,
        df: pd.DataFrame,
        lookback: int = 50
    ) -> List[PriceActionPattern]:
        """
        Detect candlestick patterns in OHLC data.
        
        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns
            lookback: Number of bars to analyze
        
        Returns:
            List of detected patterns
        """
        try:
            if len(df) < 3:
                return []
            
            df = df.tail(lookback).copy()
            patterns = []
            
            # Analyze last 3 candles for patterns (need context)
            for i in range(1, len(df) - 1):
                # Current candle
                curr_open = df['open'].iloc[i]
                curr_high = df['high'].iloc[i]
                curr_low = df['low'].iloc[i]
                curr_close = df['close'].iloc[i]
                
                # Previous candle
                prev_open = df['open'].iloc[i-1]
                prev_high = df['high'].iloc[i-1]
                prev_low = df['low'].iloc[i-1]
                prev_close = df['close'].iloc[i-1]
                
                # Bullish Engulfing
                if (prev_close < prev_open and  # Previous was bearish
                    curr_close > curr_open and  # Current is bullish
                    curr_open < prev_close and  # Current opens below previous close
                    curr_close > prev_open):    # Current closes above previous open
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.BULLISH_ENGULFING,
                        timestamp=df.index[i],
                        confidence=0.75,
                        description="Bullish reversal pattern - buyer control confirmed",
                        entry_level=curr_close,
                        stop_loss_level=curr_low
                    )
                    patterns.append(pattern)
                
                # Bearish Engulfing
                if (prev_close > prev_open and  # Previous was bullish
                    curr_close < curr_open and  # Current is bearish
                    curr_open > prev_close and  # Current opens above previous close
                    curr_close < prev_open):    # Current closes below previous open
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.BEARISH_ENGULFING,
                        timestamp=df.index[i],
                        confidence=0.75,
                        description="Bearish reversal pattern - seller control confirmed",
                        entry_level=curr_close,
                        stop_loss_level=curr_high
                    )
                    patterns.append(pattern)
                
                # Hammer (bullish reversal at bottom)
                body_size = abs(curr_close - curr_open)
                lower_wick = min(curr_open, curr_close) - curr_low
                upper_wick = curr_high - max(curr_open, curr_close)
                
                if (lower_wick > body_size * 2 and  # Long lower wick
                    upper_wick < body_size and      # Small upper wick
                    curr_close > curr_open):        # Closed bullish
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.HAMMER,
                        timestamp=df.index[i],
                        confidence=0.65,
                        description="Hammer - buyers took control after rejection",
                        entry_level=curr_close,
                        stop_loss_level=curr_low
                    )
                    patterns.append(pattern)
                
                # Hanging Man (bearish reversal at top)
                if (lower_wick > body_size * 2 and  # Long lower wick
                    upper_wick < body_size and      # Small upper wick
                    curr_close < curr_open):        # Closed bearish
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.HANGING_MAN,
                        timestamp=df.index[i],
                        confidence=0.65,
                        description="Hanging Man - rejection after buyers tried",
                        entry_level=curr_close,
                        stop_loss_level=curr_high
                    )
                    patterns.append(pattern)
                
                # Inside Bar (consolidation/breakout preparation)
                if (curr_high < prev_high and
                    curr_low > prev_low):
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.INSIDE_BAR,
                        timestamp=df.index[i],
                        confidence=0.60,
                        description="Inside bar - consolidation before breakout",
                        entry_level=prev_high if curr_close > (curr_open + curr_close) / 2 else prev_low,
                        stop_loss_level=curr_low if curr_close > (curr_open + curr_close) / 2 else curr_high
                    )
                    patterns.append(pattern)
                
                # Pin Bar Up (bullish rejection)
                total_range = curr_high - curr_low
                body_range = abs(curr_close - curr_open)
                if (body_range < total_range * 0.3 and      # Small body
                    (curr_high - max(curr_open, curr_close)) > total_range * 0.5 and  # Long upper wick
                    min(curr_open, curr_close) > curr_low * 1.001):  # Close near low
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.PIN_BAR_UP,
                        timestamp=df.index[i],
                        confidence=0.70,
                        description="Pin bar up - rejection of higher prices",
                        entry_level=curr_close,
                        stop_loss_level=curr_high
                    )
                    patterns.append(pattern)
                
                # Pin Bar Down (bearish rejection)
                if (body_range < total_range * 0.3 and      # Small body
                    (min(curr_open, curr_close) - curr_low) > total_range * 0.5 and  # Long lower wick
                    max(curr_open, curr_close) < curr_high * 0.999):  # Close near high
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.PIN_BAR_DOWN,
                        timestamp=df.index[i],
                        confidence=0.70,
                        description="Pin bar down - rejection of lower prices",
                        entry_level=curr_close,
                        stop_loss_level=curr_low
                    )
                    patterns.append(pattern)
            
            self.patterns_history.extend(patterns)
            logger.info(f"Detected {len(patterns)} price action patterns")
            return patterns
        
        except Exception as e:
            logger.error(f"Error detecting patterns: {e}")
            return []
    
    def detect_breakout(
        self,
        df: pd.DataFrame,
        lookback: int = 50,
        breakout_pips: float = 10
    ) -> List[PriceActionPattern]:
        """
        Detect breakout patterns above resistance or below support.
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of bars to analyze
            breakout_pips: Minimum breakout distance in pips
        
        Returns:
            List of detected breakouts
        """
        try:
            if len(df) < 5:
                return []
            
            df = df.tail(lookback).copy()
            patterns = []
            
            for i in range(3, len(df)):
                # Find highest high and lowest low of last 20 bars
                window = df.iloc[max(0, i-20):i]
                prev_high = window['high'].max()
                prev_low = window['low'].min()
                
                current_bar = df.iloc[i]
                
                # Breakout above resistance
                if current_bar['close'] > prev_high and \
                   (current_bar['close'] - prev_high) >= breakout_pips and \
                   current_bar['volume'] > window['volume'].mean() * 1.2:
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.BREAKOUT_UP,
                        timestamp=df.index[i],
                        confidence=0.80,
                        description=f"Breakout above {prev_high:.5f} with volume",
                        entry_level=current_bar['close'],
                        stop_loss_level=prev_high
                    )
                    patterns.append(pattern)
                
                # Breakout below support
                if current_bar['close'] < prev_low and \
                   (prev_low - current_bar['close']) >= breakout_pips and \
                   current_bar['volume'] > window['volume'].mean() * 1.2:
                    
                    pattern = PriceActionPattern(
                        pattern=CandlePattern.BREAKOUT_DOWN,
                        timestamp=df.index[i],
                        confidence=0.80,
                        description=f"Breakout below {prev_low:.5f} with volume",
                        entry_level=current_bar['close'],
                        stop_loss_level=prev_low
                    )
                    patterns.append(pattern)
            
            self.patterns_history.extend(patterns)
            logger.info(f"Detected {len(patterns)} breakout patterns")
            return patterns
        
        except Exception as e:
            logger.error(f"Error detecting breakouts: {e}")
            return []
    
    def confirm_trend(
        self,
        df: pd.DataFrame,
        direction: str,  # 'up' or 'down'
        lookback: int = 20
    ) -> Tuple[bool, float]:
        """
        Confirm if trend is intact (higher highs for uptrend, lower lows for downtrend).
        
        Args:
            df: DataFrame with OHLCV data
            direction: 'up' or 'down'
            lookback: Number of bars to check
        
        Returns:
            Tuple of (trend_intact, strength) where strength is 0-1
        """
        try:
            if len(df) < lookback + 1:
                return False, 0.0
            
            df = df.tail(lookback + 1).copy()
            
            if direction.lower() == 'up':
                # Uptrend: check for higher highs
                highs = df['high'].values
                higher_highs = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
                strength = higher_highs / (len(highs) - 1)
                intact = higher_highs >= len(highs) * 0.5  # At least 50% higher highs
                
            elif direction.lower() == 'down':
                # Downtrend: check for lower lows
                lows = df['low'].values
                lower_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
                strength = lower_lows / (len(lows) - 1)
                intact = lower_lows >= len(lows) * 0.5  # At least 50% lower lows
            else:
                return False, 0.0
            
            return intact, strength
        
        except Exception as e:
            logger.error(f"Error confirming trend: {e}")
            return False, 0.0
    
    def get_recent_patterns(self, limit: int = 10) -> List[PriceActionPattern]:
        """Get most recent patterns detected."""
        return self.patterns_history[-limit:] if self.patterns_history else []
    
    def clear_history(self):
        """Clear pattern history."""
        self.patterns_history.clear()
        logger.info("PriceActionEngine history cleared")
