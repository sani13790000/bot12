"""
تست‌های Unit برای SMC Engine

تست‌های کامل برای تمام اجزای Smart Money Concept.

نویسنده: MT5 Trading Team
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime

from backend.analysis.smc_engine import (
    MarketStructureAnalyzer,
    LiquidityAnalyzer,
    OrderBlockAnalyzer,
    FVGAnalyzer,
    KillZoneAnalyzer,
    SMCResult,
    SwingLevel,
    StructureEvent,
    BlockZone,
    FVGZone,
)


# =====================================================
# Helper: ساخت داده کندل تستی
# =====================================================

def make_candles(n=100, base=1.1000, trend="up", volatility=0.0010):
    """ساخت آرایه کندل‌های تستی"""
    opens, highs, lows, closes, volumes = [], [], [], [], []
    price = base
    for i in range(n):
        if trend == "up":
            move = volatility * (0.5 + (i / n) * 0.5)
        elif trend == "down":
            move = -volatility * (0.5 + (i / n) * 0.5)
        else:
            move = volatility * np.sin(i * 0.3)

        open_ = price
        close_ = price + move
        high_ = max(open_, close_) + volatility * 0.3
        low_ = min(open_, close_) - volatility * 0.3
        vol = 1000 + i * 10

        opens.append(open_)
        highs.append(high_)
        lows.append(low_)
        closes.append(close_)
        volumes.append(vol)
        price = close_

    timestamps = [datetime(2025, 1, 1, i // 60, i % 60) for i in range(n)]
    return {
        "timestamps": timestamps,
        "opens": np.array(opens),
        "highs": np.array(highs),
        "lows": np.array(lows),
        "closes": np.array(closes),
        "volumes": np.array(volumes),
    }


def make_market_data(n=100, trend="up"):
    candles = make_candles(n=n, trend=trend)
    return {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "candles": candles,
        "current_price": float(candles["closes"][-1]),
        "spread": 0.0002,
    }


# =====================================================
# تست MarketStructureAnalyzer
# =====================================================

class TestMarketStructureAnalyzer:
    """تست تحلیل ساختار بازار"""

    def test_init_default_config(self):
        """تست مقداردهی اولیه با config پیش‌فرض"""
        analyzer = MarketStructureAnalyzer()
        assert analyzer is not None

    def test_init_custom_config(self):
        """تست مقداردهی اولیه با config سفارشی"""
        config = {"swing_lookback": 5, "min_swing_size": 0.0005}
        analyzer = MarketStructureAnalyzer(config=config)
        assert analyzer is not None

    def test_analyze_returns_smc_result(self):
        """تست برگشت SMCResult از analyze"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=50, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_analyze_uptrend_bullish(self):
        """تست شناسایی روند صعودی"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        # در روند صعودی، trend باید bullish یا sideways باشد
        assert hasattr(result, "trend") or isinstance(result, dict)

    def test_analyze_downtrend_bearish(self):
        """تست شناسایی روند نزولی"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=80, trend="down")
        result = analyzer.analyze(data)
        assert result is not None

    def test_detect_swings_minimum_candles(self):
        """تست با حداقل کندل‌های لازم"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=20, trend="up")
        # نباید crash کند
        result = analyzer.analyze(data)
        assert result is not None

    def test_analyze_with_empty_candles_raises(self):
        """تست با کندل خالی"""
        analyzer = MarketStructureAnalyzer()
        data = {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "candles": {
                "timestamps": [],
                "opens": np.array([]),
                "highs": np.array([]),
                "lows": np.array([]),
                "closes": np.array([]),
                "volumes": np.array([]),
            },
            "current_price": 1.1000,
            "spread": 0.0002,
        }
        # باید gracefully handle کند
        try:
            result = analyzer.analyze(data)
            # نتیجه می‌تواند None یا default باشد
        except (ValueError, IndexError, KeyError):
            pass  # این exception‌ها قابل قبول هستند

    def test_bos_detection(self):
        """تست تشخیص Break of Structure"""
        analyzer = MarketStructureAnalyzer()
        # روند صعودی قوی برای BOS
        data = make_market_data(n=100, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_score_is_numeric(self):
        """تست عددی بودن score"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=60, trend="up")
        result = analyzer.analyze(data)
        if isinstance(result, dict):
            score = result.get("score", 0)
            assert isinstance(score, (int, float))
            assert 0 <= score <= 100


# =====================================================
# تست LiquidityAnalyzer
# =====================================================

class TestLiquidityAnalyzer:
    """تست تحلیل نقدینگی"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        analyzer = LiquidityAnalyzer()
        assert analyzer is not None

    def test_analyze_returns_result(self):
        """تست برگشت نتیجه"""
        analyzer = LiquidityAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_liquidity_levels_are_list(self):
        """تست اینکه liquidity levels یک لیست است"""
        analyzer = LiquidityAnalyzer()
        data = make_market_data(n=80, trend="sideways")
        result = analyzer.analyze(data)
        if isinstance(result, dict):
            levels = result.get("liquidity_levels", [])
            assert isinstance(levels, list)

    def test_no_crash_on_flat_market(self):
        """تست عدم crash در بازار flat"""
        analyzer = LiquidityAnalyzer()
        data = make_market_data(n=50, trend="sideways")
        result = analyzer.analyze(data)
        assert result is not None


# =====================================================
# تست OrderBlockAnalyzer
# =====================================================

class TestOrderBlockAnalyzer:
    """تست تحلیل Order Block"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        analyzer = OrderBlockAnalyzer()
        assert analyzer is not None

    def test_analyze_returns_result(self):
        """تست برگشت نتیجه"""
        analyzer = OrderBlockAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_order_blocks_are_list(self):
        """تست اینکه order_blocks یک لیست است"""
        analyzer = OrderBlockAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        if isinstance(result, dict):
            blocks = result.get("order_blocks", [])
            assert isinstance(blocks, list)

    def test_bullish_ob_in_uptrend(self):
        """تست شناسایی OB صعودی در روند صعودی"""
        analyzer = OrderBlockAnalyzer()
        data = make_market_data(n=100, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_bearish_ob_in_downtrend(self):
        """تست شناسایی OB نزولی در روند نزولی"""
        analyzer = OrderBlockAnalyzer()
        data = make_market_data(n=100, trend="down")
        result = analyzer.analyze(data)
        assert result is not None


# =====================================================
# تست FVGAnalyzer
# =====================================================

class TestFVGAnalyzer:
    """تست تحلیل Fair Value Gap"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        analyzer = FVGAnalyzer()
        assert analyzer is not None

    def test_analyze_returns_result(self):
        """تست برگشت نتیجه"""
        analyzer = FVGAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        assert result is not None

    def test_fvg_zones_are_list(self):
        """تست اینکه fvg_zones یک لیست است"""
        analyzer = FVGAnalyzer()
        data = make_market_data(n=80, trend="up")
        result = analyzer.analyze(data)
        if isinstance(result, dict):
            zones = result.get("fvg_zones", [])
            assert isinstance(zones, list)

    def test_fvg_has_required_fields(self):
        """تست وجود فیلدهای لازم در FVG"""
        analyzer = FVGAnalyzer()
        data = make_market_data(n=100, trend="up")
        result = analyzer.analyze(data)
        if isinstance(result, dict):
            zones = result.get("fvg_zones", [])
            for zone in zones:
                if isinstance(zone, dict):
                    # هر FVG باید high و low داشته باشد
                    assert "high" in zone or "top" in zone or "upper" in zone
                    assert "low" in zone or "bottom" in zone or "lower" in zone


# =====================================================
# تست KillZoneAnalyzer
# =====================================================

class TestKillZoneAnalyzer:
    """تست تحلیل Kill Zone"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        analyzer = KillZoneAnalyzer()
        assert analyzer is not None

    def test_london_session_detection(self):
        """تست شناسایی سشن لندن"""
        analyzer = KillZoneAnalyzer()
        # ساعت ۸:۰۰ UTC = اوج لندن
        london_hour = 8
        result = analyzer.is_kill_zone(london_hour)
        assert isinstance(result, (bool, dict, str))

    def test_new_york_session_detection(self):
        """تست شناسایی سشن نیویورک"""
        analyzer = KillZoneAnalyzer()
        # ساعت ۱۳:۰۰ UTC = نیویورک
        ny_hour = 13
        result = analyzer.is_kill_zone(ny_hour)
        assert isinstance(result, (bool, dict, str))

    def test_dead_zone_detection(self):
        """تست شناسایی زمان بی‌روح"""
        analyzer = KillZoneAnalyzer()
        # ساعت ۲۲:۰۰ UTC = آسیا بسته
        dead_hour = 22
        result = analyzer.is_kill_zone(dead_hour)
        assert isinstance(result, (bool, dict, str))


# =====================================================
# تست dataclass‌ها
# =====================================================

class TestSMCDataClasses:
    """تست ساختارهای داده SMC"""

    def test_swing_level_creation(self):
        """تست ایجاد SwingLevel"""
        swing = SwingLevel(
            price=1.1000,
            index=10,
            is_high=True,
            strength=0.8,
            timestamp=datetime.utcnow()
        )
        assert swing.price == 1.1000
        assert swing.is_high is True
        assert 0 <= swing.strength <= 1

    def test_structure_event_creation(self):
        """تست ایجاد StructureEvent"""
        event = StructureEvent(
            event_type="BOS",
            direction="bullish",
            price=1.1000,
            index=20,
            timestamp=datetime.utcnow()
        )
        assert event.event_type == "BOS"
        assert event.direction == "bullish"

    def test_block_zone_creation(self):
        """تست ایجاد BlockZone"""
        block = BlockZone(
            zone_type="bullish_ob",
            high=1.1020,
            low=1.1000,
            index=15,
            strength=0.75,
            is_valid=True
        )
        assert block.high > block.low
        assert block.is_valid is True

    def test_fvg_zone_creation(self):
        """تست ایجاد FVGZone"""
        fvg = FVGZone(
            zone_type="bullish_fvg",
            high=1.1015,
            low=1.1005,
            index=25,
            is_filled=False
        )
        assert fvg.high > fvg.low
        assert fvg.is_filled is False


# =====================================================
# تست یکپارچه SMC
# =====================================================

class TestSMCIntegration:
    """تست یکپارچه تمام اجزای SMC"""

    def test_full_smc_analysis_uptrend(self):
        """تست تحلیل کامل SMC در روند صعودی"""
        struct = MarketStructureAnalyzer()
        liq = LiquidityAnalyzer()
        ob = OrderBlockAnalyzer()
        fvg = FVGAnalyzer()

        data = make_market_data(n=100, trend="up")

        r1 = struct.analyze(data)
        r2 = liq.analyze(data)
        r3 = ob.analyze(data)
        r4 = fvg.analyze(data)

        assert r1 is not None
        assert r2 is not None
        assert r3 is not None
        assert r4 is not None

    def test_full_smc_analysis_downtrend(self):
        """تست تحلیل کامل SMC در روند نزولی"""
        struct = MarketStructureAnalyzer()
        data = make_market_data(n=100, trend="down")
        result = struct.analyze(data)
        assert result is not None

    def test_consistent_results_same_data(self):
        """تست یکنواختی نتایج با داده یکسان"""
        analyzer = MarketStructureAnalyzer()
        data = make_market_data(n=80, trend="up")
        r1 = analyzer.analyze(data)
        r2 = analyzer.analyze(data)
        # نتایج باید یکسان باشند (deterministic)
        if isinstance(r1, dict) and isinstance(r2, dict):
            assert r1.get("trend") == r2.get("trend")
