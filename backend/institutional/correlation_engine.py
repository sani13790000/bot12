"""correlation_engine.py - Hedge-Fund Grade Dynamic Correlation Engine v2 (HF-2)

HF-2: Rolling correlation replaces static dict
  - Pearson on log-returns (window-based, configurable)
  - Per-pair TTL cache (invalidated on new price tick)
  - 20-pair static cold-start fallback
  - portfolio_correlation_matrix() for risk display
  - Async-safe with asyncio.Lock
  - Volatility regime detection
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("correlation_engine")

_STATIC: Dict[Tuple[str, str], float] = {
    ("AUDUSD", "EURUSD"): 0.72,
    ("AUDUSD", "GBPUSD"): 0.70,
    ("AUDUSD", "NZDUSD"): 0.91,
    ("AUDUSD", "USDCAD"): -0.62,
    ("BTCUSD", "ETHUSD"): 0.88,
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "NZDUSD"): 0.70,
    ("EURUSD", "USDCAD"): -0.78,
    ("EURUSD", "USDCHF"): -0.92,
    ("EURUSD", "XAUUSD"): 0.45,
    ("GBPUSD", "NZDUSD"): 0.68,
    ("GBPUSD", "USDCHF"): -0.88,
    ("NAS100", "US30"): 0.88,
    ("NAS100", "US500"): 0.92,
    ("US30", "US500"): 0.95,
    ("USDJPY", "AUDJPY"): 0.70,
    ("USDJPY", "EURJPY"): 0.75,
    ("USDJPY", "GBPJPY"): 0.72,
    ("USDCHF", "XAUUSD"): -0.40,
    ("XAGUSD", "XAUUSD"): 0.80,
}
_DEFAULT_WINDOW = 50
_DEFAULT_TTL_S = 60.0
_HIGH_VOLA_MULT = 1.5


def _canonical(a: str, b: str) -> Tuple[str, str]:
    a, b = a.upper().strip(), b.upper().strip()
    return (a, b) if a <= b else (b, a)


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 5:
        return 0.0
    xs, ys = xs[-n:], ys[-n:]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-10 or dy < 1e-10:
        return 0.0
    return max(-1.0, min(1.0, num / (dx * dy)))


@dataclass
class _PriceWindow:
    window: int
    returns: Deque[float] = field(default_factory=deque)
    last_price: Optional[float] = None

    def add_price(self, price: float) -> None:
        if price <= 0:
            return
        if self.last_price is not None and self.last_price > 0:
            lr = math.log(price / self.last_price)
            self.returns.append(lr)
            if len(self.returns) > self.window:
                self.returns.popleft()
        self.last_price = price

    @property
    def ready(self) -> bool:
        return len(self.returns) >= 5

    def as_list(self) -> List[float]:
        return list(self.returns)

    def volatility(self) -> float:
        xs = self.as_list()
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


@dataclass
class _CacheEntry:
    correlation: float
    timestamp: float
    source: str


@dataclass
class CorrelationResult:
    symbol_a: str
    symbol_b: str
    correlation: float
    source: str
    window_bars: int
    cached: bool
    high_vol_a: bool = False
    high_vol_b: bool = False

    @property
    def is_highly_correlated(self) -> bool:
        return abs(self.correlation) >= 0.75

    @property
    def regime(self) -> str:
        return "HIGH_VOLATILITY" if (self.high_vol_a or self.high_vol_b) else "NORMAL"


class RollingCorrelationEngine:
    """HF-2: Dynamic rolling Pearson correlation engine."""

    def __init__(self, window: int = _DEFAULT_WINDOW, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._window = window
        self._ttl_s = ttl_s
        self._prices: Dict[str, _PriceWindow] = {}
        self._cache: Dict[Tuple[str, str], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    def add_price_tick(self, symbol: str, price: float) -> None:
        sym = symbol.upper().strip()
        if sym not in self._prices:
            self._prices[sym] = _PriceWindow(window=self._window)
        self._prices[sym].add_price(price)
        stale = [k for k in self._cache if sym in k]
        for k in stale:
            del self._cache[k]

    async def get_correlation(self, a: str, b: str) -> CorrelationResult:
        key = _canonical(a, b)
        async with self._lock:
            return self._get_or_compute(key)

    def _get_or_compute(self, key: Tuple[str, str]) -> CorrelationResult:
        a, b = key
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and (now - cached.timestamp) < self._ttl_s:
            pw_a = self._prices.get(a)
            pw_b = self._prices.get(b)
            return CorrelationResult(
                symbol_a=a,
                symbol_b=b,
                correlation=cached.correlation,
                source=cached.source,
                window_bars=self._window,
                cached=True,
                high_vol_a=pw_a.volatility() > _HIGH_VOLA_MULT * 0.001 if pw_a else False,
                high_vol_b=pw_b.volatility() > _HIGH_VOLA_MULT * 0.001 if pw_b else False,
            )
        pw_a = self._prices.get(a)
        pw_b = self._prices.get(b)
        if pw_a and pw_b and pw_a.ready and pw_b.ready:
            corr = _pearson(pw_a.as_list(), pw_b.as_list())
            self._cache[key] = _CacheEntry(correlation=corr, timestamp=now, source="rolling")
            return CorrelationResult(
                symbol_a=a,
                symbol_b=b,
                correlation=corr,
                source="rolling",
                window_bars=self._window,
                cached=False,
                high_vol_a=pw_a.volatility() > _HIGH_VOLA_MULT * 0.001,
                high_vol_b=pw_b.volatility() > _HIGH_VOLA_MULT * 0.001,
            )
        static = _STATIC.get(key, _STATIC.get((b, a), 0.0))
        source = "static" if static != 0.0 else "none"
        self._cache[key] = _CacheEntry(correlation=static, timestamp=now, source=source)
        return CorrelationResult(
            symbol_a=a, symbol_b=b, correlation=static, source=source, window_bars=0, cached=False
        )

    async def portfolio_correlation_matrix(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        matrix: Dict[str, Dict[str, float]] = {}
        async with self._lock:
            for a in symbols:
                matrix[a] = {}
                for b in symbols:
                    matrix[a][b] = (
                        1.0 if a == b else self._get_or_compute(_canonical(a, b)).correlation
                    )
        return matrix

    async def get_high_correlation_pairs(
        self, symbols: List[str], threshold: float = 0.75
    ) -> List[Tuple[str, str, float]]:
        pairs = []
        for i, a in enumerate(symbols):
            for b in symbols[i + 1 :]:
                res = await self.get_correlation(a, b)
                if abs(res.correlation) >= threshold:
                    pairs.append((a, b, res.correlation))
        return sorted(pairs, key=lambda x: abs(x[2]), reverse=True)

    def stats(self) -> Dict[str, int]:
        return {
            "tracked_symbols": len(self._prices),
            "cache_entries": len(self._cache),
            "window_bars": self._window,
            "ttl_s": int(self._ttl_s),
        }


_engine: Optional[RollingCorrelationEngine] = None
_engine_lock = asyncio.Lock()


async def get_correlation_engine(
    window: int = _DEFAULT_WINDOW, ttl_s: float = _DEFAULT_TTL_S
) -> RollingCorrelationEngine:
    global _engine
    if _engine is None:
        async with _engine_lock:
            if _engine is None:
                _engine = RollingCorrelationEngine(window=window, ttl_s=ttl_s)
                logger.info(
                    "RollingCorrelationEngine initialized (window=%d, ttl=%.0fs)", window, ttl_s
                )
    return _engine
