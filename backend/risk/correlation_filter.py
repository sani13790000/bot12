"""
Galaxy Vast AI Trading Platform
Correlation Filter - FIX-4

FIX-4: Static correlation table -> Rolling correlation engine
  BEFORE: hardcoded dict {("EURUSD","GBPUSD"): 0.85, ...}
  AFTER:
    - RollingCorrelationEngine: Pearson on log-returns
    - Configurable window (default 50 bars)
    - TTL cache per pair (default 60s)
    - Static table retained as cold-start fallback
    - portfolio_correlation_matrix() for risk display
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from ..core.logger import get_logger

logger = get_logger("risk.correlation_filter")


# Static fallback table (cold-start / insufficient data)
_STATIC_CORRELATION_TABLE: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"):  0.85,
    ("EURUSD", "AUDUSD"):  0.72,
    ("EURUSD", "NZDUSD"):  0.70,
    ("EURUSD", "USDCHF"): -0.92,
    ("EURUSD", "USDCAD"): -0.78,
    ("GBPUSD", "AUDUSD"):  0.70,
    ("GBPUSD", "NZDUSD"):  0.68,
    ("GBPUSD", "USDCHF"): -0.88,
    ("AUDUSD", "NZDUSD"):  0.91,
    ("AUDUSD", "USDCAD"): -0.62,
    ("USDJPY", "EURJPY"):  0.75,
    ("USDJPY", "GBPJPY"):  0.72,
    ("USDJPY", "AUDJPY"):  0.70,
    ("XAUUSD", "XAGUSD"):  0.80,
    ("XAUUSD", "EURUSD"):  0.45,
    ("XAUUSD", "USDCHF"): -0.40,
    ("US30",   "US500"):   0.95,
    ("US30",   "NAS100"):  0.88,
    ("US500",  "NAS100"):  0.92,
    ("BTCUSD", "ETHUSD"):  0.88,
}


def _canonical(a: str, b: str) -> Tuple[str, str]:
    a, b = a.upper(), b.upper()
    return (a, b) if a < b else (b, a)


# --- Rolling correlation engine ---

@dataclass
class _PriceWindow:
    window:  int
    returns: Deque[float] = field(default_factory=deque)
    last_price: Optional[float] = None

    def add_price(self, price: float) -> None:
        if price <= 0: return
        if self.last_price is not None and self.last_price > 0:
            lr = math.log(price / self.last_price)
            self.returns.append(lr)
            if len(self.returns) > self.window:
                self.returns.popleft()
        self.last_price = price

    @property
    def ready(self) -> bool: return len(self.returns) >= 5
    def as_list(self) -> List[float]: return list(self.returns)


@dataclass
class _CacheEntry:
    correlation: float
    timestamp:   float


class RollingCorrelationEngine:
    """Computes Pearson correlation from rolling windows of log-returns."""

    def __init__(self, window: int = 50, cache_ttl: float = 60.0):
        self._window    = window
        self._cache_ttl = cache_ttl
        self._windows:  Dict[str, _PriceWindow]          = {}
        self._cache:    Dict[Tuple[str, str], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def add_price(self, symbol: str, price: float) -> None:
        sym = symbol.upper()
        async with self._lock:
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
            if entry and (time.monotonic() - entry.timestamp) < self._cache_ttl:
                return entry.correlation
            win_a = self._windows.get(key[0])
            win_b = self._windows.get(key[1])
            if win_a is None or win_b is None or not win_a.ready or not win_b.ready:
                return None
            corr = _pearson(win_a.as_list(), win_b.as_list())
            self._cache[key] = _CacheEntry(correlation=corr, timestamp=time.monotonic())
            return corr

    def get_tracked_symbols(self) -> List[str]: return list(self._windows.keys())

    async def cache_stats(self) -> Dict:
        async with self._lock:
            now = time.monotonic()
            return {"tracked_symbols": len(self._windows), "cache_entries": len(self._cache), "cache_live": sum(1 for e in self._cache.values() if now - e.timestamp < self._cache_ttl), "window_size": self._window, "cache_ttl": self._cache_ttl}


def _pearson(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 3: return 0.0
    x, y = x[-n:], y[-n:]
    mx = sum(x) / n; my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx  = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy  = math.sqrt(sum((v - my) ** 2 for v in y))
    return round(num / (dx * dy), 4) if dx * dy > 0 else 0.0


# --- FIX-4: updated CorrelationFilter ---

@dataclass
class CorrelationFilterConfig:
    max_correlated_exposure:       float = 0.80
    correlation_penalty_threshold: float = 0.60
    window:                        int   = 50
    cache_ttl:                     float = 60.0


@dataclass
class CorrPosition:
    symbol:       str
    direction:    str
    risk_percent: float


@dataclass
class CorrelationResult:
    can_trade:         bool
    risk_multiplier:   float
    correlation_score: float
    reason:            str
    source:            str  # "rolling" | "static" | "none"


class CorrelationFilter:
    """
    FIX-4: Rolling engine replaces static table.
    Lookup: rolling -> static table -> None (uncorrelated assumption)
    """

    def __init__(self, config: Optional[CorrelationFilterConfig] = None):
        self.config  = config or CorrelationFilterConfig()
        self._engine = RollingCorrelationEngine(window=self.config.window, cache_ttl=self.config.cache_ttl)

    async def add_price(self, symbol: str, price: float) -> None:
        await self._engine.add_price(symbol, price)

    async def check(self, new_symbol: str, new_direction: str, open_positions: List[CorrPosition], base_risk_percent: float) -> CorrelationResult:
        if not open_positions:
            return CorrelationResult(can_trade=True, risk_multiplier=1.0, correlation_score=0.0, reason="", source="none")

        max_corr = 0.0; max_pair = ""; net_exposure = 0.0; source = "none"
        for pos in open_positions:
            corr, src = await self._get_correlation(new_symbol, pos.symbol)
            if corr is None: continue
            direction_factor = 1.0 if new_direction == pos.direction else -1.0
            effective_corr = corr * direction_factor
            net_exposure  += effective_corr * pos.risk_percent
            if abs(corr) > abs(max_corr):
                max_corr = corr; max_pair = pos.symbol; source = src

        abs_net = abs(net_exposure)
        logger.debug("Correlation check %s %s: net=%.3f max_corr=%.3f(%s)", new_direction, new_symbol, net_exposure, max_corr, max_pair)

        if abs_net >= self.config.max_correlated_exposure:
            return CorrelationResult(can_trade=False, risk_multiplier=0.0, correlation_score=abs_net, reason=f"Correlated exposure {abs_net:.2f} >= max {self.config.max_correlated_exposure} (pair: {max_pair} corr={max_corr:.2f})", source=source)

        if abs_net >= self.config.correlation_penalty_threshold:
            penalty    = 1.0 - (abs_net - self.config.correlation_penalty_threshold) / (self.config.max_correlated_exposure - self.config.correlation_penalty_threshold)
            multiplier = round(max(0.3, penalty), 2)
            return CorrelationResult(can_trade=True, risk_multiplier=multiplier, correlation_score=abs_net, reason=f"Correlation penalty: net={abs_net:.2f} multiplier={multiplier}", source=source)

        return CorrelationResult(can_trade=True, risk_multiplier=1.0, correlation_score=abs_net, reason="", source=source)

    async def _get_correlation(self, sym_a: str, sym_b: str) -> Tuple[Optional[float], str]:
        try:
            corr = await self._engine.get_correlation(sym_a, sym_b)
            if corr is not None: return corr, "rolling"
        except Exception as exc:
            logger.warning("Rolling correlation error %s/%s: %s", sym_a, sym_b, exc)
        key = _canonical(sym_a, sym_b)
        if key in _STATIC_CORRELATION_TABLE: return _STATIC_CORRELATION_TABLE[key], "static"
        return None, "none"

    def get_correlation(self, sym_a: str, sym_b: str) -> Optional[float]:
        """Sync lookup via static table only (backward compat)."""
        if sym_a.upper() == sym_b.upper(): return 1.0
        return _STATIC_CORRELATION_TABLE.get(_canonical(sym_a, sym_b))

    async def portfolio_correlation_matrix(self, symbols: List[str]) -> Dict[Tuple[str, str], float]:
        """Full N*N correlation matrix for portfolio risk display."""
        matrix: Dict[Tuple[str, str], float] = {}
        for i, a in enumerate(symbols):
            for b in symbols[i:]:
                if a == b:
                    matrix[_canonical(a, b)] = 1.0
                else:
                    corr, _ = await self._get_correlation(a, b)
                    matrix[_canonical(a, b)] = corr if corr is not None else 0.0
        return matrix

    @property
    def rolling_engine(self) -> RollingCorrelationEngine: return self._engine
