"""correlation_engine.py — Hedge-Fund Grade Dynamic Correlation Engine

HF-2: Rolling correlation replaces static dict
  - Pearson on log-returns (window-based)
  - Per-pair TTL cache (invalidated on new price)
  - Static cold-start fallback
  - Portfolio correlation matrix
  - Async-safe with asyncio.Lock
  - Volatility regime detection
"""
from __future__ import annotations
import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
import logging
logger = logging.getLogger("correlation_engine")

_STATIC: Dict[Tuple[str, str], float] = {
    ("AUDUSD", "EURUSD"):  0.72, ("AUDUSD", "GBPUSD"):  0.70,
    ("AUDUSD", "NZDUSD"):  0.91, ("AUDUSD", "USDCAD"): -0.62,
    ("BTCUSD", "ETHUSD"):  0.88, ("EURUSD", "GBPUSD"):  0.85,
    ("EURUSD", "NZDUSD"):  0.70, ("EURUSD", "USDCAD"): -0.78,
    ("EURUSD", "USDCHF"): -0.92, ("EURUSD", "XAUUSD"):  0.45,
    ("GBPUSD", "NZDUSD"):  0.68, ("GBPUSD", "USDCHF"): -0.88,
    ("NAS100", "US30"):    0.88, ("NAS100", "US500"):   0.92,
    ("US30",   "US500"):   0.95, ("USDJPY", "AUDJPY"):  0.70,
    ("USDJPY", "EURJPY"):  0.75, ("USDJPY", "GBPJPY"):  0.72,
    ("USDCHF", "XAUUSD"): -0.40, ("XAGUSD", "XAUUSD"):  0.80,
}


def _canonical(a: str, b: str) -> Tuple[str, str]:
    a, b = a.upper().strip(), b.upper().strip()
    return (a, b) if a <= b else (b, a)


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 5: return 0.0
    xs, ys = xs[-n:], ys[-n:]
    mx = sum(xs) / n; my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-10 or dy < 1e-10: return 0.0
    return max(-1.0, min(1.0, num / (dx * dy)))


@dataclass
class _PriceWindow:
    window:     int
    returns:    Deque[float] = field(default_factory=deque)
    last_price: Optional[float] = None

    def add_price(self, price: float) -> None:
        if price <= 0: return
        if self.last_price is not None and self.last_price > 0:
            lr = math.log(price / self.last_price)
            self.returns.append(lr)
            if len(self.returns) > self.window: self.returns.popleft()
        self.last_price = price

    @property
    def ready(self) -> bool: return len(self.returns) >= 5
    def as_list(self) -> List[float]: return list(self.returns)

    @property
    def volatility(self) -> float:
        rs = self.as_list()
        if len(rs) < 5: return 0.0
        mean = sum(rs) / len(rs)
        var  = sum((r - mean) ** 2 for r in rs) / len(rs)
        return math.sqrt(var) * math.sqrt(252)


@dataclass
class _CacheEntry:
    correlation: float
    ts:          float


class RollingCorrelationEngine:
    """HF-2: Dynamic rolling correlation with static cold-start fallback."""

    def __init__(self, window: int = 50, cache_ttl: float = 60.0) -> None:
        self._window    = window
        self._cache_ttl = cache_ttl
        self._windows:  Dict[str, _PriceWindow]            = {}
        self._cache:    Dict[Tuple[str, str], _CacheEntry] = {}
        self._lock      = asyncio.Lock()
        logger.info("RollingCorrelationEngine window=%d ttl=%.0fs", window, cache_ttl)

    async def add_price_tick(self, symbol: str, price: float) -> None:
        sym = symbol.upper()
        async with self._lock:
            if sym not in self._windows:
                self._windows[sym] = _PriceWindow(window=self._window)
            self._windows[sym].add_price(price)
            stale = [k for k in self._cache if sym in k]
            for k in stale: del self._cache[k]

    def add_price_tick_sync(self, symbol: str, price: float) -> None:
        sym = symbol.upper()
        if sym not in self._windows:
            self._windows[sym] = _PriceWindow(window=self._window)
        self._windows[sym].add_price(price)
        stale = [k for k in self._cache if sym in k]
        for k in stale: del self._cache[k]

    async def get_correlation(self, a: str, b: str) -> Optional[float]:
        key = _canonical(a, b)
        if key[0] == key[1]: return 1.0
        async with self._lock:
            entry = self._cache.get(key)
            if entry and (time.monotonic() - entry.ts) < self._cache_ttl:
                return entry.correlation
            win_a = self._windows.get(key[0])
            win_b = self._windows.get(key[1])
            if win_a and win_b and win_a.ready and win_b.ready:
                corr = _pearson(win_a.as_list(), win_b.as_list())
                self._cache[key] = _CacheEntry(correlation=corr, ts=time.monotonic())
                return corr
        return _STATIC.get(key)

    def get_correlation_sync(self, a: str, b: str) -> Optional[float]:
        key = _canonical(a, b)
        if key[0] == key[1]: return 1.0
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry.ts) < self._cache_ttl:
            return entry.correlation
        win_a = self._windows.get(key[0])
        win_b = self._windows.get(key[1])
        if win_a and win_b and win_a.ready and win_b.ready:
            corr = _pearson(win_a.as_list(), win_b.as_list())
            self._cache[key] = _CacheEntry(correlation=corr, ts=time.monotonic())
            return corr
        return _STATIC.get(key)

    async def portfolio_correlation_matrix(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        matrix: Dict[str, Dict[str, float]] = {}
        for s in symbols:
            matrix[s] = {}
            for t in symbols:
                if s == t: matrix[s][t] = 1.0
                else:
                    c = await self.get_correlation(s, t)
                    matrix[s][t] = round(c, 4) if c is not None else 0.0
        return matrix

    def get_regime(self, symbol: str) -> str:
        win = self._windows.get(symbol.upper())
        if not win or not win.ready: return "unknown"
        vol = win.volatility
        return "low" if vol < 0.10 else "medium" if vol < 0.20 else "high"

    def tracked_symbols(self) -> List[str]: return list(self._windows.keys())
    def cache_size(self) -> int: return len(self._cache)

    async def invalidate_cache(self) -> None:
        async with self._lock: self._cache.clear()


_engine: Optional[RollingCorrelationEngine] = None


def get_correlation_engine() -> RollingCorrelationEngine:
    global _engine
    if _engine is None: _engine = RollingCorrelationEngine()
    return _engine
