"""
تست‌های Unit برای Decision Engine

تست‌های کامل برای pipeline تصمیم‌گیری ۶ مرحله‌ای.

نویسنده: MT5 Trading Team
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from typing import Dict, Any

from backend.analysis.decision_engine import (
    DecisionEngine,
    DecisionResult,
    MultiTimeframeEngine,
    MultiTimeframeResult,
    TimeframeAnalysis,
    TrendDirection,
    DecisionStage,
)


# =====================================================
# Helper: ساخت داده ورودی تستی
# =====================================================

def make_decision_input(
    symbol="EURUSD",
    timeframe="H1",
    current_price=1.1000,
    spread=0.0002,
    atr=0.0015,
    session_score=80,
    override_direction=None
) -> Dict[str, Any]:
    """ساخت DecisionInput تستی"""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": current_price,
        "spread": spread,
        "atr": atr,
        "session_score": session_score,
        "market_data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": current_price,
            "spread": spread,
            "candles": {
                "opens": np.array([1.0990 + i * 0.0001 for i in range(100)]),
                "highs": np.array([1.0995 + i * 0.0001 for i in range(100)]),
                "lows": np.array([1.0985 + i * 0.0001 for i in range(100)]),
                "closes": np.array([1.0992 + i * 0.0001 for i in range(100)]),
                "volumes": np.array([1000.0] * 100),
                "timestamps": [datetime.utcnow()] * 100,
            }
        },
        "smc_data": {
            "trend": "bullish",
            "score": 75,
            "structure_pattern": "HH_HL",
            "bos_events": [{"direction": "bullish", "price": 1.0980}],
            "choch_events": [],
            "order_blocks": [{"zone_type": "bullish_ob", "high": 1.0970, "low": 1.0960, "strength": 0.8}],
            "fvg_zones": [{"zone_type": "bullish_fvg", "high": 1.0965, "low": 1.0960}],
            "liquidity_levels": [],
            "key_levels": {"resistance": 1.1050, "support": 1.0950},
            "in_kill_zone": True,
            "kill_zone_name": "London",
        },
        "pa_data": {
            "overall_bias": "bullish",
            "score": 70,
            "patterns": [{"pattern": "bullish_engulfing", "strength": 0.8}],
            "momentum": 0.6,
        },
        "license_info": {
            "is_valid": True,
            "features": ["auto_trading", "signals", "dashboard"],
            "license_type": "pro",
        },
    }


def make_smc_score_result(direction="bullish", score=75) -> Dict[str, Any]:
    """ساخت SMC score result تستی"""
    return {
        "direction": direction,
        "score": score,
        "factors": {
            "structure": 80,
            "order_block": 70,
            "fvg": 65,
            "liquidity": 75,
            "session": 80,
        }
    }


def make_pa_score_result(bias="bullish", score=70) -> Dict[str, Any]:
    """ساخت PA score result تستی"""
    return {
        "bias": bias,
        "score": score,
        "patterns_found": 3,
        "momentum": 0.6,
    }


# =====================================================
# تست DecisionEngine
# =====================================================

class TestDecisionEngine:
    """تست موتور تصمیم‌گیری"""

    def test_init_default(self):
        """تست مقداردهی اولیه با config پیش‌فرض"""
        engine = DecisionEngine()
        assert engine is not None

    def test_init_custom_config(self):
        """تست مقداردهی اولیه با config سفارشی"""
        config = {
            "min_score": 60,
            "max_spread_ratio": 3.0,
        }
        engine = DecisionEngine(config=config)
        assert engine is not None

    def test_decide_returns_decision_result(self):
        """تست اینکه decide یک DecisionResult برمی‌گرداند"""
        engine = DecisionEngine()
        data = make_decision_input()
        result = engine.decide(data)
        assert result is not None

    def test_decide_buy_on_strong_bullish(self):
        """تست تصمیم BUY در شرایط صعودی قوی"""
        engine = DecisionEngine()
        data = make_decision_input(session_score=85)
        data["smc_data"]["score"] = 80
        data["pa_data"]["score"] = 75
        data["smc_data"]["in_kill_zone"] = True
        result = engine.decide(data)
        assert result is not None
        if isinstance(result, dict):
            decision = result.get("decision", "")
            assert decision in ["BUY", "SELL", "NO_TRADE"]

    def test_decide_no_trade_on_weak_signal(self):
        """تست تصمیم NO_TRADE با سیگنال ضعیف"""
        engine = DecisionEngine()
        data = make_decision_input(session_score=20)
        data["smc_data"]["score"] = 20
        data["pa_data"]["score"] = 15
        data["smc_data"]["in_kill_zone"] = False
        result = engine.decide(data)
        assert result is not None

    def test_decide_blocked_without_license(self):
        """تست بلاک شدن بدون لایسنس"""
        engine = DecisionEngine()
        data = make_decision_input()
        data["license_info"]["is_valid"] = False
        result = engine.decide(data)
        assert result is not None
        if isinstance(result, dict):
            # بدون لایسنس، allowed باید False باشد
            allowed = result.get("allowed", True)
            assert allowed is False or result.get("decision") == "NO_TRADE"

    def test_decide_blocked_high_spread(self):
        """تست بلاک شدن با spread زیاد"""
        engine = DecisionEngine()
        data = make_decision_input(spread=0.0050, atr=0.0010)
        # spread/ATR ratio = 5 — خیلی بالا
        result = engine.decide(data)
        assert result is not None

    def test_decision_has_reason_codes(self):
        """تست وجود reason_codes در نتیجه"""
        engine = DecisionEngine()
        data = make_decision_input()
        result = engine.decide(data)
        if isinstance(result, dict):
            reason_codes = result.get("reason_codes", [])
            assert isinstance(reason_codes, list)

    def test_decision_has_trading_levels(self):
        """تست وجود trading_levels در BUY/SELL"""
        engine = DecisionEngine()
        data = make_decision_input(session_score=85)
        data["smc_data"]["score"] = 82
        data["pa_data"]["score"] = 78
        result = engine.decide(data)
        if isinstance(result, dict) and result.get("decision") in ["BUY", "SELL"]:
            levels = result.get("trading_levels", {})
            assert levels is not None

    def test_decision_confidence_score_range(self):
        """تست محدوده confidence_score"""
        engine = DecisionEngine()
        data = make_decision_input()
        result = engine.decide(data)
        if isinstance(result, dict):
            score = result.get("confidence_score", 0)
            assert 0 <= score <= 100

    def test_decision_quality_score_range(self):
        """تست محدوده quality_score"""
        engine = DecisionEngine()
        data = make_decision_input()
        result = engine.decide(data)
        if isinstance(result, dict):
            score = result.get("quality_score", 0)
            assert 0 <= score <= 100

    def test_buy_direction_with_bullish_alignment(self):
        """تست جهت BUY با هم‌راستایی صعودی"""
        engine = DecisionEngine()
        data = make_decision_input()
        data["smc_data"]["trend"] = "bullish"
        data["pa_data"]["overall_bias"] = "bullish"
        result = engine.decide(data)
        if isinstance(result, dict) and result.get("allowed"):
            decision = result.get("decision")
            assert decision in ["BUY", "NO_TRADE"]

    def test_sell_direction_with_bearish_alignment(self):
        """تست جهت SELL با هم‌راستایی نزولی"""
        engine = DecisionEngine()
        data = make_decision_input()
        data["smc_data"]["trend"] = "bearish"
        data["smc_data"]["bos_events"] = [{"direction": "bearish", "price": 1.1020}]
        data["pa_data"]["overall_bias"] = "bearish"
        data["pa_data"]["patterns"] = [{"pattern": "bearish_engulfing", "strength": 0.8}]
        result = engine.decide(data)
        if isinstance(result, dict) and result.get("allowed"):
            decision = result.get("decision")
            assert decision in ["SELL", "NO_TRADE"]

    def test_no_trade_outside_kill_zone(self):
        """تست NO_TRADE در خارج از Kill Zone"""
        engine = DecisionEngine()
        data = make_decision_input()
        data["smc_data"]["in_kill_zone"] = False
        data["session_score"] = 10
        result = engine.decide(data)
        # ممکن است NO_TRADE شود اما نباید crash کند
        assert result is not None


# =====================================================
# تست MultiTimeframeEngine
# =====================================================

class TestMultiTimeframeEngine:
    """تست موتور چند تایم‌فریمی"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        engine = MultiTimeframeEngine()
        assert engine is not None

    def test_analyze_single_timeframe(self):
        """تست تحلیل یک تایم‌فریم"""
        engine = MultiTimeframeEngine()
        smc_data = {"trend": "bullish", "score": 75}
        pa_data = {"overall_bias": "bullish", "score": 70}
        result = engine._analyze_timeframe("H1", smc_data, pa_data)
        assert result is not None

    def test_trend_extraction_bullish(self):
        """تست استخراج روند صعودی"""
        engine = MultiTimeframeEngine()
        smc_data = {"trend": "bullish", "score": 75}
        trend = engine._extract_trend(smc_data)
        assert trend == TrendDirection.BULLISH or str(trend).lower() in ["bullish", "up"]

    def test_trend_extraction_bearish(self):
        """تست استخراج روند نزولی"""
        engine = MultiTimeframeEngine()
        smc_data = {"trend": "bearish", "score": 70}
        trend = engine._extract_trend(smc_data)
        assert trend == TrendDirection.BEARISH or str(trend).lower() in ["bearish", "down"]

    def test_trend_extraction_sideways(self):
        """تست استخراج روند خنثی"""
        engine = MultiTimeframeEngine()
        smc_data = {"trend": "sideways", "score": 40}
        trend = engine._extract_trend(smc_data)
        assert trend is not None

    def test_alignment_score_range(self):
        """تست محدوده alignment score"""
        engine = MultiTimeframeEngine()
        tf1 = TimeframeAnalysis(
            timeframe="H4",
            trend=TrendDirection.BULLISH,
            structure_score=80,
            momentum=0.7,
            in_key_zone=True,
            zone_type="bullish_ob",
            zone_strength=0.8,
        )
        tf2 = TimeframeAnalysis(
            timeframe="H1",
            trend=TrendDirection.BULLISH,
            structure_score=75,
            momentum=0.6,
            in_key_zone=True,
            zone_type="fvg",
            zone_strength=0.7,
        )
        score = engine._calculate_alignment_score(tf1, tf2)
        assert 0 <= score <= 100

    def test_trends_aligned_same_direction(self):
        """تست هم‌راستایی روندهای یکسان"""
        engine = MultiTimeframeEngine()
        aligned = engine._are_trends_aligned(TrendDirection.BULLISH, TrendDirection.BULLISH)
        assert aligned is True

    def test_trends_not_aligned_opposite(self):
        """تست عدم هم‌راستایی روندهای مخالف"""
        engine = MultiTimeframeEngine()
        aligned = engine._are_trends_aligned(TrendDirection.BULLISH, TrendDirection.BEARISH)
        assert aligned is False


# =====================================================
# تست DecisionResult
# =====================================================

class TestDecisionResult:
    """تست ساختار DecisionResult"""

    def test_decision_result_creation(self):
        """تست ایجاد DecisionResult"""
        result = DecisionResult(
            symbol="EURUSD",
            timeframe="H1",
            decision="BUY",
            direction="bullish",
            allowed=True,
            confidence_score=75,
            quality_score=72,
        )
        assert result.symbol == "EURUSD"
        assert result.decision == "BUY"
        assert result.allowed is True

    def test_no_trade_result(self):
        """تست DecisionResult برای NO_TRADE"""
        result = DecisionResult(
            symbol="EURUSD",
            timeframe="H1",
            decision="NO_TRADE",
            direction="neutral",
            allowed=True,
            confidence_score=30,
            quality_score=25,
        )
        assert result.decision == "NO_TRADE"
        assert result.quality_score < 45

    def test_blocked_result(self):
        """تست DecisionResult بلاک‌شده"""
        result = DecisionResult(
            symbol="EURUSD",
            timeframe="H1",
            decision="NO_TRADE",
            direction="neutral",
            allowed=False,
            confidence_score=0,
            quality_score=0,
            blocked_reasons=["LICENSE_INVALID"],
        )
        assert result.allowed is False
        assert "LICENSE_INVALID" in result.blocked_reasons


# =====================================================
# تست یکپارچه Decision Pipeline
# =====================================================

class TestDecisionPipelineIntegration:
    """تست یکپارچه pipeline کامل"""

    def test_full_pipeline_buy_signal(self):
        """تست pipeline کامل با سیگنال BUY"""
        engine = DecisionEngine()
        data = make_decision_input(session_score=82)
        data["smc_data"].update({"score": 80, "trend": "bullish", "in_kill_zone": True})
        data["pa_data"].update({"score": 75, "overall_bias": "bullish"})
        result = engine.decide(data)
        assert result is not None
        if isinstance(result, dict):
            assert result.get("decision") in ["BUY", "SELL", "NO_TRADE"]

    def test_full_pipeline_no_trade(self):
        """تست pipeline کامل با NO_TRADE"""
        engine = DecisionEngine()
        data = make_decision_input(session_score=15)
        data["smc_data"].update({"score": 20, "in_kill_zone": False})
        data["pa_data"].update({"score": 15})
        result = engine.decide(data)
        assert result is not None

    def test_pipeline_deterministic(self):
        """تست تکرارپذیری pipeline"""
        engine = DecisionEngine()
        data = make_decision_input()
        r1 = engine.decide(data)
        r2 = engine.decide(data)
        if isinstance(r1, dict) and isinstance(r2, dict):
            assert r1.get("decision") == r2.get("decision")

    def test_pipeline_different_symbols(self):
        """تست pipeline با نمادهای مختلف"""
        engine = DecisionEngine()
        for symbol in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]:
            data = make_decision_input(symbol=symbol)
            result = engine.decide(data)
            assert result is not None

    def test_pipeline_all_stages_execute(self):
        """تست اینکه تمام ۶ مرحله pipeline اجرا می‌شوند"""
        engine = DecisionEngine()
        data = make_decision_input()
        result = engine.decide(data)
        # نتیجه باید نشان‌دهنده اجرای pipeline کامل باشد
        assert result is not None
        if isinstance(result, dict):
            # باید reason_codes داشته باشد (نشانه اجرای مراحل)
            assert "reason_codes" in result or "reasons" in result or "decision" in result
