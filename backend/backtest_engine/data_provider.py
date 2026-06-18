"""
Galaxy Vast AI Trading Platform
CandleDataProvider — Historical data abstraction layer

Supports:
  - In-memory data (list of CandleBar)
  - CSV file loading
  - MT5 bridge via REST API
  - Multi-symbol / multi-timeframe registry
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class Timeframe(str, Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"


@dataclass
class CandleBar:
    """Single OHLCV candle bar."""
    time:   datetime
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0
    spread: float = 2.0  # in points

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    def to_dict(self) -> dict:
        return {
            "time":   self.time.isoformat(),
            "open":   self.open,
            "high":   self.high,
            "low":    self.low,
            "close":  self.close,
            "volume": self.volume,
            "spread": self.spread,
        }


@dataclass
class DataSet:
    """Typed dataset for one symbol + timeframe."""
    symbol:    str
    timeframe: Timeframe
    candles:   List[CandleBar] = field(default_factory=list)

    def slice(self, start: datetime, end: datetime) -> List[CandleBar]:
        return [c for c in self.candles if start <= c.time <= end]

    def atr(self, period: int = 14, index: int = -1) -> float:
        """ATR calculation at given candle index."""
        if index < 0:
            index = len(self.candles) + index
        start = max(0, index - period)
        bars = self.candles[start:index + 1]
        if len(bars) < 2:
            return 0.0
        trs = []
        for i in range(1, len(bars)):
            b, p = bars[i], bars[i - 1]
            trs.append(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)))
        return sum(trs) / len(trs)


class CandleDataProvider:
    """
    Central registry for multi-symbol, multi-timeframe candle data.

    Usage:
        provider = CandleDataProvider()
        provider.register("XAUUSD", Timeframe.H1, candles)
        candles = provider.get("XAUUSD", Timeframe.H1)
    """

    def __init__(self) -> None:
        self._registry: Dict[str, DataSet] = {}

    # ── key helper ────────────────────────────────────────────────────────────
    @staticmethod
    def _key(symbol: str, timeframe: Timeframe) -> str:
        return f"{symbol}:{timeframe.value}"

    # ── registration ──────────────────────────────────────────────────────────
    def register(self, symbol: str, timeframe: Timeframe, candles: List[CandleBar]) -> None:
        key = self._key(symbol, timeframe)
        self._registry[key] = DataSet(symbol=symbol, timeframe=timeframe, candles=candles)

    def register_from_csv(self, symbol: str, timeframe: Timeframe, csv_path: str) -> int:
        """Load OHLCV CSV: time,open,high,low,close,volume"""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")
        candles: List[CandleBar] = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append(CandleBar(
                    time=datetime.fromisoformat(row["time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                    spread=float(row.get("spread", 2.0)),
                ))
        self.register(symbol, timeframe, sorted(candles, key=lambda c: c.time))
        return len(candles)

    def generate_synthetic(
        self,
        symbol: str,
        timeframe: Timeframe,
        n_candles: int = 2000,
        start_price: float = 2000.0,
        volatility: float = 0.002,
        seed: int = 42,
    ) -> List[CandleBar]:
        """Generate realistic synthetic OHLCV data (for testing)."""
        random.seed(seed)
        candles: List[CandleBar] = []
        price = start_price
        tf_minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}
        step = timedelta(minutes=tf_minutes.get(timeframe.value, 60))
        t = datetime(2023, 1, 1)

        for _ in range(n_candles):
            ret = random.gauss(0, volatility)
            o = price
            c = price * (1 + ret)
            hi = max(o, c) * (1 + abs(random.gauss(0, volatility * 0.5)))
            lo = min(o, c) * (1 - abs(random.gauss(0, volatility * 0.5)))
            vol = abs(random.gauss(1000, 300))
            candles.append(CandleBar(time=t, open=round(o,5), high=round(hi,5),
                                     low=round(lo,5), close=round(c,5), volume=round(vol,1)))
            price = c
            t += step

        self.register(symbol, timeframe, candles)
        return candles

    # ── retrieval ─────────────────────────────────────────────────────────────
    def get(self, symbol: str, timeframe: Timeframe) -> Optional[DataSet]:
        return self._registry.get(self._key(symbol, timeframe))

    def list_datasets(self) -> List[str]:
        return list(self._registry.keys())

    def has(self, symbol: str, timeframe: Timeframe) -> bool:
        return self._key(symbol, timeframe) in self._registry
