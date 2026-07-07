from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOL = "HIGH_VOLATILITY"
    LOW_VOL = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeConfig:
    adx_trend_threshold: float = 25.0
    adx_strong_threshold: float = 40.0
    adx_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    vol_high_zscore: float = 1.5
    vol_low_zscore: float = -1.0
    bb_width_ranging: float = 0.03
    cache_ttl_seconds: float = 60.0
    min_bars_required: int = 30


@dataclass(frozen=True)
class RegimeResult:
    symbol: str
    regime: MarketRegime
    adx: float
    atr: float
    atr_zscore: float
    bb_width_pct: float
    confidence: float
    timestamp: float = field(default_factory=time.monotonic)
    bars_used: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class PriceBar:
    high: float
    low: float
    close: float
    timestamp: float = field(default_factory=time.time)


class MarketRegimeDetector:
    """Detects market regime: TRENDING|RANGING|HIGH_VOL|LOW_VOL. Async-safe."""

    def __init__(self, config=None):
        self._cfg = config or RegimeConfig()
        self._bars: Dict[str, deque] = {}
        self._cache: Dict[str, Tuple[RegimeResult, float]] = {}
        self._lock = asyncio.Lock()

    async def add_bar(self, symbol: str, bar: PriceBar) -> None:
        async with self._lock:
            if symbol not in self._bars:
                self._bars[symbol] = deque(maxlen=200)
            self._bars[symbol].append(bar)
            self._cache.pop(symbol, None)

    async def detect(self, symbol: str) -> RegimeResult:
        async with self._lock:
            if symbol in self._cache:
                result, ts = self._cache[symbol]
                if time.monotonic() - ts < self._cfg.cache_ttl_seconds:
                    return result
            bars = list(self._bars.get(symbol, []))
        if len(bars) < self._cfg.min_bars_required:
            return RegimeResult(
                symbol=symbol,
                regime=MarketRegime.UNKNOWN,
                adx=0.0,
                atr=0.0,
                atr_zscore=0.0,
                bb_width_pct=0.0,
                confidence=0.0,
                bars_used=len(bars),
                metadata={"reason": f"need {self._cfg.min_bars_required} bars, have {len(bars)}"},
            )
        result = self._compute(symbol, bars)
        async with self._lock:
            self._cache[symbol] = (result, time.monotonic())
        return result

    async def bulk_detect(self, symbols):
        tasks = {s: asyncio.create_task(self.detect(s)) for s in symbols}
        results = {}
        for sym, task in tasks.items():
            try:
                results[sym] = await task
            except Exception as exc:
                logger.error("regime detect failed for %s: %s", sym, exc)
                results[sym] = RegimeResult(
                    symbol=sym,
                    regime=MarketRegime.UNKNOWN,
                    adx=0.0,
                    atr=0.0,
                    atr_zscore=0.0,
                    bb_width_pct=0.0,
                    confidence=0.0,
                )
        return results

    def get_trading_multiplier(self, regime: MarketRegime) -> float:
        return {
            MarketRegime.TRENDING_UP: 1.0,
            MarketRegime.TRENDING_DOWN: 1.0,
            MarketRegime.RANGING: 0.6,
            MarketRegime.HIGH_VOL: 0.5,
            MarketRegime.LOW_VOL: 0.8,
            MarketRegime.UNKNOWN: 0.3,
        }[regime]

    def is_safe_to_trade(self, regime: MarketRegime) -> bool:
        return regime not in {MarketRegime.UNKNOWN, MarketRegime.HIGH_VOL}

    def _compute(self, symbol, bars):
        H = [b.high for b in bars]
        L = [b.low for b in bars]
        C = [b.close for b in bars]
        adx = self._calc_adx(H, L, C)
        atr = self._calc_atr(H, L, C)
        atr_z = self._calc_atr_zscore(H, L, C)
        bb_w = self._calc_bb_width(C)
        bb_wp = bb_w / C[-1] if C[-1] > 0 else 0.0
        regime, conf = self._classify(adx, atr_z, bb_wp)
        return RegimeResult(
            symbol=symbol,
            regime=regime,
            adx=adx,
            atr=atr,
            atr_zscore=atr_z,
            bb_width_pct=bb_wp,
            confidence=conf,
            bars_used=len(bars),
            metadata={"bb_width_abs": bb_w},
        )

    def _classify(self, adx, atr_z, bb_w):
        if atr_z >= self._cfg.vol_high_zscore:
            return MarketRegime.HIGH_VOL, min(1.0, 0.5 + (atr_z - self._cfg.vol_high_zscore) * 0.2)
        if adx >= self._cfg.adx_trend_threshold:
            return MarketRegime.TRENDING_UP, min(
                1.0, 0.5 + (adx - self._cfg.adx_trend_threshold) / 40.0
            )
        if bb_w <= self._cfg.bb_width_ranging:
            return MarketRegime.RANGING, min(1.0, 0.5 + (self._cfg.bb_width_ranging - bb_w) * 20.0)
        if atr_z <= self._cfg.vol_low_zscore:
            return MarketRegime.LOW_VOL, min(1.0, 0.5 + abs(atr_z - self._cfg.vol_low_zscore) * 0.2)
        return MarketRegime.RANGING, 0.4

    def _calc_atr(self, H, L, C):
        p = self._cfg.atr_period
        trs = [
            max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(H))
        ]
        if not trs:
            return 0.0
        w = trs[-p:] if len(trs) >= p else trs
        return sum(w) / len(w)

    def _calc_atr_zscore(self, H, L, C):
        trs = [
            max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(H))
        ]
        if len(trs) < 10:
            return 0.0
        m = sum(trs) / len(trs)
        v = sum((x - m) ** 2 for x in trs) / len(trs)
        s = math.sqrt(v) if v > 0 else 1e-9
        return (trs[-1] - m) / s

    def _calc_adx(self, H, L, C):
        p = self._cfg.adx_period
        if len(H) < p + 1:
            return 0.0
        pdm, mdm, tr = [], [], []
        for i in range(1, len(H)):
            u = H[i] - H[i - 1]
            d = L[i - 1] - L[i]
            pdm.append(u if u > d and u > 0 else 0.0)
            mdm.append(d if d > u and d > 0 else 0.0)
            tr.append(max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])))

        def sm(data, n):
            if len(data) < n:
                return []
            r = [sum(data[:n])]
            for i in range(n, len(data)):
                r.append(r[-1] - r[-1] / n + data[i])
            return r

        st = sm(tr, p)
        sp = sm(pdm, p)
        sm2 = sm(mdm, p)
        if not st or not sp or not sm2:
            return 0.0
        dx = []
        for s2, p2, m2 in zip(st, sp, sm2):
            if s2 == 0:
                continue
            pdi = 100 * p2 / s2
            mdi = 100 * m2 / s2
            den = pdi + mdi
            dx.append(100 * abs(pdi - mdi) / den if den else 0.0)
        if not dx:
            return 0.0
        w = dx[-p:] if len(dx) >= p else dx
        return sum(w) / len(w)

    def _calc_bb_width(self, closes):
        p = self._cfg.bb_period
        w = closes[-p:] if len(closes) >= p else closes
        if not w:
            return 0.0
        m = sum(w) / len(w)
        s = math.sqrt(sum((x - m) ** 2 for x in w) / len(w))
        return 2 * self._cfg.bb_std * s


_detector = None
_detector_lock = asyncio.Lock()


async def get_regime_detector(config=None):
    global _detector
    async with _detector_lock:
        if _detector is None:
            _detector = MarketRegimeDetector(config)
    return _detector
