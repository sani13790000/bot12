"""
تست‌های واحد موتور Price Action

تست‌های جامع برای:
- الگوهای کندلی (Pin Bar, Engulfing, Fakey, etc.)
- ساختار قیمت (Breakout, Retest, Compression, Expansion)
- Context-aware تحلیل
- Scoring system

نویسنده: MT5 Trading Team
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import sys
import os

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.analysis.price_action_engine import (
    ContextAnalyzer,
    CandlePatternDetector,
    PriceStructureAnalyzer,
    PriceActionEngine,
    CandleData,
    MarketContext,
    PatternAnalysis,
    StandardPASignal,
    PatternReasonCode,
    PatternStrength,
    PatternType,
    PriceActionResult
)
from backend.core.enums import TrendDirection, TradingSession


# =====================================================
# Fixtures
# =====================================================

@pytest.fixture
def sample_ohlc_data():
    """داده نمونه OHLC برای تست"""
    n = 100
    base_price = 1.1000

    times = [datetime.utcnow() - timedelta(minutes=15 * (n - i)) for i in range(n)]

    # ایجاد روند صعودی با نوسانات
    trend = np.linspace(0, 0.02, n)
    noise = np.random.randn(n) * 0.001

    closes = base_price + trend + noise
    opens = closes + np.random.randn(n) * 0.0005
    highs = np.maximum(opens, closes) + np.random.rand(n) * 0.001
    lows = np.minimum(opens, closes) - np.random.rand(n) * 0.001

    return {
        'opens': list(opens),
        'highs': list(highs),
        'lows': list(lows),
        'closes': list(closes),
        'times': times
    }


@pytest.fixture
def pin_bar_candle_data():
    """کندل Pin Bar مصنوعی"""
    # Bullish Pin Bar
    return CandleData(
        index=0,
        time=datetime.utcnow(),
        open=1.1005,
        high=1.1010,
        low=1.0980,
        close=1.1003
    )


@pytest.fixture
def bearish_pin_bar_data():
    """کندل Bearish Pin Bar مصنوعی"""
    return CandleData(
        index=0,
        time=datetime.utcnow(),
        open=1.1000,
        high=1.1030,
        low=1.0998,
        close=1.1002
    )


@pytest.fixture
def engulfing_candles():
    """دو کندل Engulfing"""
    return [
        CandleData(
            index=0,
            time=datetime.utcnow() - timedelta(minutes=15),
            open=1.1010,
            high=1.1015,
            low=1.1000,
            close=1.1002,  # نزولی کوچک
        ),
        CandleData(
            index=1,
            time=datetime.utcnow(),
            open=1.1005,
            high=1.1025,
            low=1.1000,
            close=1.1020,  # صعودی بزرگ (engulfing)
        )
    ]


@pytest.fixture
def fakey_candles():
    """چهار کندل Fakey"""
    return [
        # Mother Bar
        CandleData(
            index=0,
            time=datetime.utcnow() - timedelta(minutes=60),
            open=1.1000,
            high=1.1025,
            low=1.0980,
            close=1.1010
        ),
        # Inside Bar
        CandleData(
            index=1,
            time=datetime.utcnow() - timedelta(minutes=45),
            open=1.1005,
            high=1.1015,
            low=1.0995,
            close=1.1008
        ),
        # False Break Candle
        CandleData(
            index=2,
            time=datetime.utcnow() - timedelta(minutes=30),
            open=1.1008,
            high=1.1030,  # Break above inside
            low=1.0990,
            close=1.1005
        ),
        # Signal Candle
        CandleData(
            index=3,
            time=datetime.utcnow() - timedelta(minutes=15),
            open=1.1005,
            high=1.1015,
            low=1.0985,
            close=1.0990  # Close below inside
        )
    ]


@pytest.fixture
def basic_context():
    """Context پایه برای تست‌ها"""
    context = MarketContext()
    context.trend = TrendDirection.NEUTRAL
    context.trend_strength = 50
    context.atr = 0.0015
    context.avg_range = 0.0020
    context.volatility_percentile = 50
    context.current_session = TradingSession.LONDON
    context.is_killzone = True
    context.support_levels = [1.0950, 1.0970, 1.0990]
    context.resistance_levels = [1.1050, 1.1070, 1.1090]
    context.current_price = 1.1000
    context.premium_discount = "equilibrium"
    return context


@pytest.fixture
def bullish_context():
    """Context با روند صعودی"""
    context = basic_context()
    context.trend = TrendDirection.BULLISH
    context.trend_strength = 70
    return context


@pytest.fixture
def smc_context():
    """Context از SMC Engine"""
    return {
        "liquidity_swept": True,
        "sweep_direction": "sell_side_hit",
        "active_blocks": [
            {
                "block_type": "order_block",
                "direction": "bullish",
                "high": 1.1010,
                "low": 1.0990,
                "mid": 1.1000,
                "score": 8
            }
        ],
        "active_fvgs": [
            {
                "fvg_type": "bullish_fvg",
                "high": 1.1005,
                "low": 1.0995,
                "mid": 1.1000
            }
        ],
        "premium_discount": "discount",
        "last_event_type": "choch"
    }


# =====================================================
# تست‌های CandleData
# =====================================================

class TestCandleData:
    """تست‌های ساختار CandleData"""

    def test_candle_data_creation(self):
        """تست ایجاد CandleData"""
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1005
        )

        assert candle.index == 0
        assert candle.open == 1.1000
        assert candle.high == 1.1010

    def test_candle_calculations(self):
        """تست محاسبات خودکار کندل"""
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1005
        )

        # Post-init calculations
        assert candle.body == 0.0005  # |close - open|
        assert candle.total_range == 0.0020  # high - low
        assert candle.is_bullish is True
        assert candle.upper_wick == 0.0005  # high - max(open, close)
        assert candle.lower_wick == 0.0010  # min(open, close) - low

    def test_bearish_candle(self):
        """تست کندل نزولی"""
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1010,
            high=1.1015,
            low=1.0990,
            close=1.0995
        )

        assert candle.is_bullish is False
        assert candle.body == 0.0015


# =====================================================
# تست‌های ContextAnalyzer
# =====================================================

class TestContextAnalyzer:
    """تست‌های تحلیلگر Context"""

    def test_initialization(self):
        """تست مقداردهی اولیه"""
        analyzer = ContextAnalyzer()

        assert analyzer.atr_period == 14
        assert analyzer.range_period == 20

    def test_analyze_basic(self, sample_ohlc_data):
        """تست تحلیل پایه"""
        analyzer = ContextAnalyzer()

        candles = [
            {
                'open': sample_ohlc_data['opens'][i],
                'high': sample_ohlc_data['highs'][i],
                'low': sample_ohlc_data['lows'][i],
                'close': sample_ohlc_data['closes'][i]
            }
            for i in range(len(sample_ohlc_data['opens']))
        ]

        context = analyzer.analyze(
            candles,
            sample_ohlc_data['times']
        )

        assert isinstance(context, MarketContext)
        assert context.atr > 0
        assert context.avg_range > 0

    def test_trend_detection(self, sample_ohlc_data):
        """تست تشخیص روند"""
        analyzer = ContextAnalyzer()

        candles = [
            {
                'open': sample_ohlc_data['opens'][i],
                'high': sample_ohlc_data['highs'][i],
                'low': sample_ohlc_data['lows'][i],
                'close': sample_ohlc_data['closes'][i]
            }
            for i in range(len(sample_ohlc_data['opens']))
        ]

        context = analyzer.analyze(
            candles,
            sample_ohlc_data['times']
        )

        # روند باید تشخیص داده شده باشد
        assert context.trend in (
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
            TrendDirection.NEUTRAL
        )
        assert 0 <= context.trend_strength <= 100

    def test_session_detection(self):
        """تست تشخیص سشن"""
        analyzer = ContextAnalyzer()

        # London session (8-17 UTC)
        london_time = datetime.utcnow().replace(hour=10, minute=0)

        candles = [{'open': 1.1, 'high': 1.1, 'low': 1.1, 'close': 1.1} for _ in range(30)]
        times = [london_time - timedelta(minutes=i*15) for i in range(30)]

        context = analyzer.analyze(candles, times)

        # باید در یکی از سشن‌ها باشد
        assert context.current_session in (
            TradingSession.LONDON,
            TradingSession.NEW_YORK,
            TradingSession.TOKYO,
            TradingSession.SYDNEY
        )

    def test_smc_context_extraction(self, sample_ohlc_data, smc_context):
        """تست استخراج SMC context"""
        analyzer = ContextAnalyzer()

        candles = [
            {
                'open': sample_ohlc_data['opens'][i],
                'high': sample_ohlc_data['highs'][i],
                'low': sample_ohlc_data['lows'][i],
                'close': sample_ohlc_data['closes'][i]
            }
            for i in range(len(sample_ohlc_data['opens']))
        ]

        context = analyzer.analyze(
            candles,
            sample_ohlc_data['times'],
            smc_context
        )

        assert context.liquidity_swept is True
        assert len(context.active_blocks) > 0
        assert len(context.active_fvgs) > 0
        assert context.premium_discount == "discount"


# =====================================================
# تست‌های Pin Bar
# =====================================================

class TestPinBarDetection:
    """تست‌های تشخیص Pin Bar"""

    def test_bullish_pin_bar_detection(self, pin_bar_candle_data, basic_context):
        """تست تشخیص Pin Bar صعودی"""
        detector = CandlePatternDetector()

        candles = [pin_bar_candle_data]
        analysis = detector.detect_pin_bar(candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "bullish"
        assert analysis.base_score == 8.0
        assert PatternReasonCode.WICK_REJECTION in analysis.reason_codes

    def test_bearish_pin_bar_detection(self, bearish_pin_bar_data, basic_context):
        """تست تشخیص Pin Bar نزولی"""
        detector = CandlePatternDetector()

        candles = [bearish_pin_bar_data]
        analysis = detector.detect_pin_bar(candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "bearish"
        assert PatternReasonCode.WICK_REJECTION in analysis.reason_codes

    def test_pin_bar_has_required_fields(self, pin_bar_candle_data, basic_context):
        """تست فیلدهای الزامی Pin Bar"""
        detector = CandlePatternDetector()

        candles = [pin_bar_candle_data]
        analysis = detector.detect_pin_bar(candles, basic_context)

        assert analysis.confidence_score > 0
        assert analysis.quality_score > 0
        assert analysis.invalidation_level > 0
        assert len(analysis.reason_codes) > 0
        assert "wick_level" in analysis.details

    def test_pin_bar_context_bonuses(self, pin_bar_candle_data, bullish_context):
        """تست context bonuses برای Pin Bar"""
        detector = CandlePatternDetector()

        # Pin Bar صعودی با روند صعودی
        candles = [pin_bar_candle_data]
        analysis = detector.detect_pin_bar(candles, bullish_context)

        if analysis.detected:
            # اگر در جهت روند باشد باید bonus بگیرد
            if "trend_aligned" in analysis.context_bonuses:
                assert analysis.context_bonuses["trend_aligned"] > 0

    def test_non_pin_bar_rejection(self, basic_context):
        """تست رد کندل غیر Pin Bar"""
        detector = CandlePatternDetector()

        # کندل معمولی
        normal_candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1005
        )

        analysis = detector.detect_pin_bar([normal_candle], basic_context)

        assert analysis.detected is False


# =====================================================
# تست‌های Engulfing
# =====================================================

class TestEngulfingDetection:
    """تست‌های تشخیص Engulfing"""

    def test_bullish_engulfing_detection(self, engulfing_candles, basic_context):
        """تست تشخیص Engulfing صعودی"""
        detector = CandlePatternDetector()

        analysis = detector.detect_engulfing(engulfing_candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "bullish"
        assert analysis.base_score == 10.0
        assert PatternReasonCode.BODY_ENGULF in analysis.reason_codes

    def test_engulfing_ratio(self, engulfing_candles, basic_context):
        """تست نسبت Engulfing"""
        detector = CandlePatternDetector()

        analysis = detector.detect_engulfing(engulfing_candles, basic_context)

        if analysis.detected:
            assert "engulf_ratio" in analysis.details
            assert analysis.details["engulf_ratio"] >= 1.2

    def test_bearish_engulfing(self, basic_context):
        """تست Engulfing نزولی"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,  # صعودی کوچک
                high=1.1010,
                low=1.0995,
                close=1.1008
            ),
            CandleData(
                index=1,
                time=datetime.utcnow(),
                open=1.1005,
                high=1.1008,
                low=1.0980,
                close=1.0985  # نزولی بزرگ (engulfing)
            )
        ]

        analysis = detector.detect_engulfing(candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "bearish"

    def test_non_engulfing_rejection(self, basic_context):
        """تست رد کندل‌های غیر Engulfing"""
        detector = CandlePatternDetector()

        # دو کندل همجهت
        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1010,
                low=1.0990,
                close=1.1005
            ),
            CandleData(
                index=1,
                time=datetime.utcnow(),
                open=1.1005,
                high=1.1015,
                low=1.1000,
                close=1.1010
            )
        ]

        analysis = detector.detect_engulfing(candles, basic_context)

        # نباید Engulfing باشد چون همجهت هستند
        assert analysis.detected is False


# =====================================================
# تست‌های Fakey
# =====================================================

class TestFakeyDetection:
    """تست‌های تشخیص Fakey"""

    def test_bullish_fakey_detection(self, basic_context):
        """تست تشخیص Fakey صعودی"""
        detector = CandlePatternDetector()

        # ساختار Fakey صعودی
        candles = [
            # Mother Bar
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=60),
                open=1.1000,
                high=1.1025,
                low=1.0980,
                close=1.1010
            ),
            # Inside Bar
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=45),
                open=1.1005,
                high=1.1015,
                low=1.0995,
                close=1.1008
            ),
            # False Break Down
            CandleData(
                index=2,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.1008,
                high=1.1010,
                low=1.0970,  # Break below inside
                close=1.0990
            ),
            # Signal Candle (bullish return)
            CandleData(
                index=3,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.0995,
                high=1.1015,
                low=1.0990,
                close=1.1010  # Close back inside
            )
        ]

        analysis = detector.detect_fakey(candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "bullish"
        assert analysis.base_score == 15.0
        assert PatternReasonCode.FALSE_BREAK in analysis.reason_codes

    def test_fakey_invalidation_level(self, fakey_candles, basic_context):
        """تست invalidation level برای Fakey"""
        detector = CandlePatternDetector()

        analysis = detector.detect_fakey(fakey_candles, basic_context)

        if analysis.detected:
            assert analysis.invalidation_level > 0

    def test_non_fakey_rejection(self, basic_context):
        """تست رد ساختار غیر Fakey"""
        detector = CandlePatternDetector()

        # بدون inside bar
        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=45),
                open=1.1000,
                high=1.1025,
                low=1.0980,
                close=1.1010
            ),
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.1005,
                high=1.1030,  # Outside mother
                low=1.0970,
                close=1.1015
            ),
            CandleData(
                index=2,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1015,
                high=1.1020,
                low=1.1000,
                close=1.1010
            ),
            CandleData(
                index=3,
                time=datetime.utcnow(),
                open=1.1010,
                high=1.1015,
                low=1.1000,
                close=1.1005
            )
        ]

        analysis = detector.detect_fakey(candles, basic_context)

        # نباید Fakey باشد چون inside نداریم
        assert analysis.detected is False


# =====================================================
# تست‌های Inside/Outside Bar
# =====================================================

class TestInsideOutsideBar:
    """تست‌های تشخیص Inside و Outside Bar"""

    def test_inside_bar_detection(self, basic_context):
        """تست تشخیص Inside Bar"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1020,
                low=1.0980,
                close=1.1010
            ),
            CandleData(
                index=1,
                time=datetime.utcnow(),
                open=1.1005,
                high=1.1015,  # داخل mother
                low=1.0990,   # داخل mother
                close=1.1008
            )
        ]

        analysis = detector.detect_inside_bar(candles, basic_context)

        assert analysis.detected is True
        assert analysis.direction == "neutral"
        assert "mother_high" in analysis.details
        assert "mother_low" in analysis.details

    def test_outside_bar_detection(self, basic_context):
        """تست تشخیص Outside Bar"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1015,
                low=1.0990,
                close=1.1010
            ),
            CandleData(
                index=1,
                time=datetime.utcnow(),
                open=1.1005,
                high=1.1020,  # خارج از mother
                low=1.0980,   # خارج از mother
                close=1.1015
            )
        ]

        analysis = detector.detect_outside_bar(candles, basic_context)

        assert analysis.detected is True
        assert PatternReasonCode.OUTSIDE_EXPANSION in analysis.reason_codes

    def test_inside_bar_compression_bonus(self, basic_context):
        """تست bonus compression برای Inside Bar"""
        detector = CandlePatternDetector()

        # Mother large, Inside very small
        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1030,
                low=1.0970,
                close=1.1015
            ),
            CandleData(
                index=1,
                time=datetime.utcnow(),
                open=1.1008,
                high=1.1010,
                low=1.1005,
                close=1.1009
            )
        ]

        analysis = detector.detect_inside_bar(candles, basic_context)

        if analysis.detected:
            # اگر compression مشخص باشد
            if "strong_compression" in analysis.context_bonuses:
                assert analysis.context_bonuses["strong_compression"] > 0


# =====================================================
# تست‌های Doji
# =====================================================

class TestDojiDetection:
    """تست‌های تشخیص Doji"""

    def test_doji_detection(self, basic_context):
        """تست تشخیص Doji"""
        detector = CandlePatternDetector()

        # Doji candle
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1000,
            high=1.1015,
            low=1.0985,
            close=1.1001  # تقریباً برابر با open
        )

        analysis = detector.detect_doji([candle], basic_context)

        assert analysis.detected is True
        assert analysis.direction == "neutral"
        assert PatternReasonCode.INDECISION in analysis.reason_codes

    def test_doji_context_bonuses(self, basic_context):
        """تست context bonuses برای Doji"""
        detector = CandlePatternDetector()

        # Doji near support
        basic_context.support_levels = [1.1000]
        basic_context.atr = 0.0020

        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1000,
            high=1.1015,
            low=1.0985,
            close=1.1001
        )

        analysis = detector.detect_doji([candle], basic_context)

        if analysis.detected:
            # باید bonus بگیرد
            assert analysis.confidence_score > 20


# =====================================================
# تست‌های Star Patterns
# =====================================================

class TestStarPatterns:
    """تست‌های تشخیص Morning/Evening Star"""

    def test_morning_star_detection(self, basic_context):
        """تست تشخیص Morning Star"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.1010,
                high=1.1015,
                low=1.0990,
                close=1.0995  # نزولی
            ),
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.0995,
                high=1.1000,
                low=1.0990,
                close=1.0997  # کوچک
            ),
            CandleData(
                index=2,
                time=datetime.utcnow(),
                open=1.0997,
                high=1.1015,
                low=1.0995,
                close=1.1010  # صعودی بزرگ
            )
        ]

        analysis = detector.detect_star_pattern(candles, basic_context)

        assert analysis.detected is True
        assert analysis.pattern == PatternType.MORNING_STAR
        assert analysis.direction == "bullish"
        assert PatternReasonCode.REVERSAL_CANDIDATE in analysis.reason_codes

    def test_evening_star_detection(self, basic_context):
        """تست تشخیص Evening Star"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.0990,
                high=1.1010,
                low=1.0985,
                close=1.1005  # صعودی
            ),
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1005,
                high=1.1010,
                low=1.1000,
                close=1.1003  # کوچک
            ),
            CandleData(
                index=2,
                time=datetime.utcnow(),
                open=1.1003,
                high=1.1005,
                low=1.0980,
                close=1.0985  # نزولی بزرگ
            )
        ]

        analysis = detector.detect_star_pattern(candles, basic_context)

        assert analysis.detected is True
        assert analysis.pattern == PatternType.EVENING_STAR
        assert analysis.direction == "bearish"


# =====================================================
# تست‌های Three Soldiers/Crows
# =====================================================

class TestThreePattern:
    """تست‌های تشخیص Three Soldiers/Crows"""

    def test_three_soldiers_detection(self, basic_context):
        """تست تشخیص Three White Soldiers"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.0990,
                high=1.1005,
                low=1.0985,
                close=1.1000  # صعودی 1
            ),
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1010,
                low=1.0995,
                close=1.1008  # صعودی 2
            ),
            CandleData(
                index=2,
                time=datetime.utcnow(),
                open=1.1008,
                high=1.1020,
                low=1.1005,
                close=1.1015  # صعودی 3
            )
        ]

        analysis = detector.detect_three_soldiers_crows(candles, basic_context)

        assert analysis.detected is True
        assert analysis.pattern == PatternType.THREE_SOLDIERS
        assert analysis.direction == "bullish"

    def test_three_crows_detection(self, basic_context):
        """تست تشخیص Three Black Crows"""
        detector = CandlePatternDetector()

        candles = [
            CandleData(
                index=0,
                time=datetime.utcnow() - timedelta(minutes=30),
                open=1.1010,
                high=1.1015,
                low=1.0995,
                close=1.1000  # نزولی 1
            ),
            CandleData(
                index=1,
                time=datetime.utcnow() - timedelta(minutes=15),
                open=1.1000,
                high=1.1005,
                low=1.0990,
                close=1.0992  # نزولی 2
            ),
            CandleData(
                index=2,
                time=datetime.utcnow(),
                open=1.0992,
                high=1.0995,
                low=1.0980,
                close=1.0985  # نزولی 3
            )
        ]

        analysis = detector.detect_three_soldiers_crows(candles, basic_context)

        assert analysis.detected is True
        assert analysis.pattern == PatternType.THREE_CROWS
        assert analysis.direction == "bearish"


# =====================================================
# تست‌های Price Structure
# =====================================================

class TestPriceStructure:
    """تست‌های تشخیص ساختار قیمت"""

    def test_breakout_detection(self, basic_context):
        """تست تشخیص Breakout"""
        analyzer = PriceStructureAnalyzer()

        # ساخت breakout
        candles = []
        for i in range(25):
            candle = CandleData(
                index=i,
                time=datetime.utcnow() - timedelta(minutes=15 * (25 - i)),
                open=1.1000 - 0.0005 * np.sin(i),
                high=1.1005 - 0.0005 * np.sin(i),
                low=1.0995 - 0.0005 * np.sin(i),
                close=1.1000 - 0.0005 * np.sin(i)
            )
            candles.append(candle)

        # آخرین کندل break بالا
        candles[-1] = CandleData(
            index=24,
            time=datetime.utcnow(),
            open=1.1005,
            high=1.1080,
            low=1.1000,
            close=1.1075
        )

        times = [c.time for c in candles]

        structures = analyzer.analyze(candles, basic_context, times)

        # اگر شرایط برقرار باشد
        breakouts = [s for s in structures if s.pattern == PatternType.BREAKOUT]
        if breakouts:
            assert breakouts[0].detected is True

    def test_compression_detection(self, basic_context):
        """تست تشخیص Compression"""
        analyzer = PriceStructureAnalyzer()

        # ساخت compression
        candles = []
        # 10 کندل با رنج بزرگ
        for i in range(10):
            candle = CandleData(
                index=i,
                time=datetime.utcnow() - timedelta(minutes=15 * (20 - i)),
                open=1.1000,
                high=1.1030,
                low=1.0970,
                close=1.1010 + 0.0005 * i
            )
            candles.append(candle)

        # 10 کندل با رنج کوچک (compression)
        for i in range(10):
            candle = CandleData(
                index=10 + i,
                time=datetime.utcnow() - timedelta(minutes=15 * (10 - i)),
                open=1.1005,
                high=1.1010,
                low=1.1000,
                close=1.1007
            )
            candles.append(candle)

        times = [c.time for c in candles]

        structures = analyzer.analyze(candles, basic_context, times)

        compressions = [s for s in structures if s.pattern == PatternType.COMPRESSION]
        if compressions:
            assert compressions[0].detected is True
            assert "compression_ratio" in compressions[0].details


# =====================================================
# تست‌های Engine کامل
# =====================================================

class TestPriceActionEngine:
    """تست‌های یکپارچه موتور Price Action"""

    def test_initialization(self):
        """تست مقداردهی اولیه"""
        engine = PriceActionEngine()

        assert engine.context_analyzer is not None
        assert engine.pattern_detector is not None
        assert engine.structure_analyzer is not None

    def test_full_analysis(self, sample_ohlc_data):
        """تست تحلیل کامل"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        assert isinstance(result, PriceActionResult)
        assert result.symbol == "EURUSD"
        assert result.timeframe == "H1"
        assert result.total_score >= 0
        assert result.direction in ("bullish", "bearish", "neutral")

    def test_analysis_with_smc_context(self, sample_ohlc_data, smc_context):
        """تست تحلیل با SMC context"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1",
            smc_context
        )

        assert result.context.liquidity_swept is True
        assert len(result.context.active_blocks) > 0

    def test_standard_signals_generation(self, sample_ohlc_data):
        """تست تولید سیگنال‌های استاندارد"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        assert isinstance(result.standard_signals, list)

        for signal in result.standard_signals:
            assert isinstance(signal, StandardPASignal)
            assert signal.symbol == "EURUSD"
            assert signal.timeframe == "H1"
            assert signal.direction in ("bullish", "bearish", "neutral")
            assert 0 <= signal.confidence_score <= 100
            assert 0 <= signal.quality_score <= 100
            assert signal.invalidation_level > 0

    def test_get_entry_signals(self, sample_ohlc_data):
        """تست فیلتر سیگنال‌های ورود"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        entry_signals = result.get_entry_signals(min_confidence=40.0)

        for signal in entry_signals:
            assert signal.confidence_score >= 40.0
            assert signal.direction != "neutral"

    def test_get_strongest_signal(self, sample_ohlc_data):
        """تست دریافت قوی‌ترین سیگنال"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        strongest = result.get_strongest_signal()

        if strongest:
            assert isinstance(strongest, StandardPASignal)

    def test_insufficient_data_handling(self):
        """تست مدیریت داده ناکافی"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            {
                'opens': [1.1000],
                'highs': [1.1005],
                'lows': [1.0995],
                'closes': [1.1002],
                'times': [datetime.utcnow()]
            },
            "H1"
        )

        assert result.total_score == 0
        assert result.direction == "neutral"

    def test_key_levels_extraction(self, sample_ohlc_data):
        """تست استخراج سطوح کلیدی"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        assert "supports" in result.key_levels
        assert "resistances" in result.key_levels

    def test_to_dict_serialization(self, sample_ohlc_data):
        """تست سریالایزیشن"""
        engine = PriceActionEngine()

        result = engine.analyze(
            "EURUSD",
            sample_ohlc_data,
            "H1"
        )

        serialized = result.to_dict()

        assert isinstance(serialized, dict)
        assert serialized["symbol"] == "EURUSD"
        assert "signals" in serialized
        assert "key_levels" in serialized


# =====================================================
# تست‌های Context Bonuses
# =====================================================

class TestContextBonuses:
    """تست‌های bonuses بر اساس context"""

    def test_trend_aligned_bonus(self, bullish_context):
        """تست bonus هماهنگی با روند"""
        detector = CandlePatternDetector()

        # Pin Bar صعودی
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1005,
            high=1.1010,
            low=1.0980,
            close=1.1003
        )

        analysis = detector.detect_pin_bar([candle], bullish_context)

        if analysis.detected:
            # روند صعودی و pin bar صعودی = bonus
            assert "trend_aligned" in analysis.context_bonuses

    def test_support_resistance_bonus(self, basic_context):
        """تست bonus در support/resistance"""
        detector = CandlePatternDetector()

        # تنظیم سطح حمایت نزدیک
        basic_context.support_levels = [1.1000]

        # Pin Bar در حمایت
        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1005,
            high=1.1010,
            low=1.0970,
            close=1.1003
        )

        analysis = detector.detect_pin_bar([candle], basic_context)

        if analysis.detected and analysis.direction == "bullish":
            # باید bonus بگیرد
            total_bonus = sum(analysis.context_bonuses.values())
            assert total_bonus > 0

    def test_killzone_bonus(self, basic_context):
        """تست bonus در kill zone"""
        detector = CandlePatternDetector()

        basic_context.is_killzone = True

        candle = CandleData(
            index=0,
            time=datetime.utcnow(),
            open=1.1005,
            high=1.1010,
            low=1.0980,
            close=1.1003
        )

        analysis = detector.detect_pin_bar([candle], basic_context)

        if analysis.detected:
            if PatternReasonCode.IN_KILLZONE in analysis.reason_codes:
                assert "killzone" in analysis.context_bonuses


# =====================================================
# تست‌های Scoring System
# =====================================================

class TestScoringSystem:
    """تست‌های سیستم امتیازدهی"""

    def test_confidence_calculation(self, pin_bar_candle_data, basic_context):
        """تست محاسبه confidence"""
        detector = CandlePatternDetector()

        analysis = detector.detect_pin_bar([pin_bar_candle_data], basic_context)

        if analysis.detected:
            # confidence باید بین 0-100 باشد
            assert 0 <= analysis.confidence_score <= 100
            # و از base_score بیشتر باشد (با context)
            assert analysis.confidence_score >= analysis.base_score * 4

    def test_quality_calculation(self, pin_bar_candle_data, basic_context):
        """تست محاسبه quality"""
        detector = CandlePatternDetector()

        analysis = detector.detect_pin_bar([pin_bar_candle_data], basic_context)

        if analysis.detected:
            assert 0 <= analysis.quality_score <= 100

    def test_strength_assignment(self, pin_bar_candle_data, bullish_context):
        """تست تعیین strength"""
        detector = CandlePatternDetector()

        analysis = detector.detect_pin_bar([pin_bar_candle_data], bullish_context)

        if analysis.detected:
            assert "strength" in analysis.details
            assert analysis.details["strength"] in (
                PatternStrength.WEAK.value,
                PatternStrength.MODERATE.value,
                PatternStrength.STRONG.value,
                PatternStrength.VERY_STRONG.value
            )


# اجرای تست‌ها
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
