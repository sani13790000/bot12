"""Unit tests for backend/trading/market_regime.py.

Exercises the MarketRegimeDetector: bar buffering, insufficient-data
handling, trending / ranging / high-volatility classification, the
trading-multiplier and safety helpers, result caching, bulk detection
and the module-level singleton accessor.
"""
from __future__ import annotations

import pytest

from backend.trading.market_regime import (
    MarketRegime,
    MarketRegimeDetector,
    PriceBar,
    RegimeConfig,
    RegimeResult,
    get_regime_detector,
)


async def _feed(detector, symbol, bars):
    for bar in bars:
        await detector.add_bar(symbol, bar)


def _trending_up(n=60):
    return [PriceBar(high=100 + i + 0.5, low=100 + i - 0.5, close=100 + i) for i in range(n)]


def _ranging(n=60):
    out = []
    for i in range(n):
        x = 100 + (0.1 if i % 2 else -0.1)
        out.append(PriceBar(high=x + 0.05, low=x - 0.05, close=x))
    return out


def _volatile_spike(n=60):
    out = [PriceBar(high=100.1, low=99.9, close=100) for _ in range(n - 1)]
    out.append(PriceBar(high=110, low=90, close=105))
    return out


def _wide_range_choppy(n=60):
    """Consistent wide oscillation: no trend, wide BB, neutral ATR z-score."""
    out = []
    for i in range(n):
        px = 100 + (5 if i % 2 == 0 else -5)
        out.append(PriceBar(high=px + 2, low=px - 2, close=px))
    return out


def _low_vol_then_calm(n=60):
    """Historically wide-range oscillation followed by a tiny final bar."""
    out = []
    for i in range(n - 1):
        px = 100 + (8 if i % 2 == 0 else -8)
        out.append(PriceBar(high=px + 4, low=px - 4, close=px))
    out.append(PriceBar(high=100.01, low=99.99, close=100))
    return out


class TestConfigAndHelpers:
    def test_default_config(self):
        cfg = RegimeConfig()
        assert cfg.adx_trend_threshold == 25.0
        assert cfg.min_bars_required == 30

    @pytest.mark.parametrize(
        "regime,expected",
        [
            (MarketRegime.TRENDING_UP, 1.0),
            (MarketRegime.TRENDING_DOWN, 1.0),
            (MarketRegime.RANGING, 0.6),
            (MarketRegime.HIGH_VOL, 0.5),
            (MarketRegime.LOW_VOL, 0.8),
            (MarketRegime.UNKNOWN, 0.3),
        ],
    )
    def test_trading_multiplier(self, regime, expected):
        assert MarketRegimeDetector().get_trading_multiplier(regime) == expected

    def test_is_safe_to_trade(self):
        d = MarketRegimeDetector()
        assert d.is_safe_to_trade(MarketRegime.TRENDING_UP) is True
        assert d.is_safe_to_trade(MarketRegime.RANGING) is True
        assert d.is_safe_to_trade(MarketRegime.HIGH_VOL) is False
        assert d.is_safe_to_trade(MarketRegime.UNKNOWN) is False


class TestDetection:
    async def test_insufficient_bars_returns_unknown(self):
        d = MarketRegimeDetector()
        await _feed(d, "X", _trending_up(5))
        res = await d.detect("X")
        assert isinstance(res, RegimeResult)
        assert res.regime is MarketRegime.UNKNOWN
        assert res.confidence == 0.0
        assert res.bars_used == 5
        assert "need" in res.metadata["reason"]

    async def test_unknown_symbol_returns_unknown(self):
        d = MarketRegimeDetector()
        res = await d.detect("NEVER_SEEN")
        assert res.regime is MarketRegime.UNKNOWN
        assert res.bars_used == 0

    async def test_trending_up_detected(self):
        d = MarketRegimeDetector()
        await _feed(d, "UP", _trending_up())
        res = await d.detect("UP")
        assert res.regime is MarketRegime.TRENDING_UP
        assert res.adx >= d._cfg.adx_trend_threshold
        assert res.confidence > 0.5
        assert res.bars_used == 60

    async def test_ranging_detected(self):
        d = MarketRegimeDetector()
        await _feed(d, "R", _ranging())
        res = await d.detect("R")
        assert res.regime is MarketRegime.RANGING
        assert res.bb_width_pct <= d._cfg.bb_width_ranging

    async def test_high_volatility_detected(self):
        d = MarketRegimeDetector()
        await _feed(d, "V", _volatile_spike())
        res = await d.detect("V")
        assert res.regime is MarketRegime.HIGH_VOL
        assert res.atr_zscore >= d._cfg.vol_high_zscore

    async def test_low_volatility_detected(self):
        d = MarketRegimeDetector()
        await _feed(d, "L", _low_vol_then_calm())
        res = await d.detect("L")
        assert res.regime is MarketRegime.LOW_VOL
        assert res.atr_zscore <= d._cfg.vol_low_zscore

    async def test_choppy_falls_back_to_ranging(self):
        d = MarketRegimeDetector()
        await _feed(d, "M", _wide_range_choppy())
        res = await d.detect("M")
        # none of the trend/vol thresholds tripped -> default RANGING branch
        assert res.regime is MarketRegime.RANGING
        assert res.confidence == 0.4
        assert res.bb_width_pct > d._cfg.bb_width_ranging


class TestCachingAndBulk:
    async def test_result_cached_within_ttl(self):
        d = MarketRegimeDetector()
        await _feed(d, "UP", _trending_up())
        first = await d.detect("UP")
        second = await d.detect("UP")
        assert first is second  # served from cache, same object

    async def test_add_bar_invalidates_cache(self):
        d = MarketRegimeDetector()
        await _feed(d, "UP", _trending_up())
        first = await d.detect("UP")
        await d.add_bar("UP", PriceBar(high=161.5, low=160.5, close=161))
        second = await d.detect("UP")
        assert first is not second

    async def test_bulk_detect_multiple_symbols(self):
        d = MarketRegimeDetector()
        await _feed(d, "UP", _trending_up())
        await _feed(d, "R", _ranging())
        out = await d.bulk_detect(["UP", "R", "MISSING"])
        assert set(out) == {"UP", "R", "MISSING"}
        assert out["UP"].regime is MarketRegime.TRENDING_UP
        assert out["MISSING"].regime is MarketRegime.UNKNOWN

    async def test_bulk_detect_isolates_failures(self, monkeypatch):
        d = MarketRegimeDetector()
        await _feed(d, "OK", _trending_up())

        async def _boom(symbol):
            raise RuntimeError("detect exploded")

        monkeypatch.setattr(d, "detect", _boom)
        out = await d.bulk_detect(["OK"])
        # failure is caught and mapped to an UNKNOWN result, not raised
        assert out["OK"].regime is MarketRegime.UNKNOWN
        assert out["OK"].confidence == 0.0


class TestSingleton:
    async def test_get_regime_detector_is_singleton(self):
        a = await get_regime_detector()
        b = await get_regime_detector()
        assert a is b
        assert isinstance(a, MarketRegimeDetector)
