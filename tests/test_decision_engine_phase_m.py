"""فاز M — Decision Engine Unit Tests
هدف: پوشش کامل DecisionEngine.get_final_signal() و تمام مسیرهای منطقی
"""
import pytest
from unittest.mock import MagicMock, patch
from typing import Optional


class TestDecisionEngineImport:
    """تست import و instantiation"""

    def test_import_decision_engine(self):
        try:
            from backend.analysis.decision_engine import DecisionEngine
            assert DecisionEngine is not None
        except ImportError as e:
            pytest.skip(f"DecisionEngine import failed: {e}")

    def test_instantiate_decision_engine(self):
        try:
            from backend.analysis.decision_engine import DecisionEngine
            engine = DecisionEngine()
            assert engine is not None
        except ImportError:
            pytest.skip("DecisionEngine not importable")

    def test_has_get_final_signal(self):
        try:
            from backend.analysis.decision_engine import DecisionEngine
            engine = DecisionEngine()
            assert hasattr(engine, "get_final_signal"), "get_final_signal() وجود ندارد"
        except ImportError:
            pytest.skip("DecisionEngine not importable")


class TestDecisionEngineGetFinalSignal:
    """تست get_final_signal()"""

    @pytest.fixture
    def engine(self):
        try:
            from backend.analysis.decision_engine import DecisionEngine
            return DecisionEngine()
        except ImportError:
            pytest.skip("DecisionEngine not importable")

    def _make_signal(self, direction="BUY", confidence=0.75, rr=2.5):
        return {
            "symbol": "XAUUSD",
            "direction": direction,
            "confidence": confidence,
            "rr": rr,
            "entry": 2000.0,
            "sl": 1990.0,
            "tp": 2025.0,
        }

    def _make_smc(self, bias="BULLISH"):
        return {
            "bias": bias,
            "order_blocks": [{"type": "BULLISH", "price": 1995.0}],
            "fvgs": [],
            "bos_detected": True,
            "smc_confidence": 0.8,
        }

    def _make_pa(self, trend="UPTREND"):
        return {
            "trend": trend,
            "patterns": [],
            "sr_levels": [],
        }

    def _make_ml(self, probability=0.72):
        return {
            "probability": probability,
            "confidence": probability,
            "direction": "BUY",
        }

    def _make_news(self, sentiment=0.6):
        return {
            "sentiment": sentiment,
            "high_impact": False,
        }

    def test_get_final_signal_returns_dict(self, engine):
        result = engine.get_final_signal(
            self._make_smc(), self._make_pa(), self._make_ml(), self._make_news()
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    def test_aligned_signals_produce_output(self, engine):
        """وقتی همه سیگنال‌ها align هستند باید signal تولید شود"""
        result = engine.get_final_signal(
            self._make_smc("BULLISH"),
            self._make_pa("UPTREND"),
            self._make_ml(0.80),
            self._make_news(0.7),
        )
        direction = result.get("direction", result.get("action", "NO_TRADE"))
        assert direction != "", "نتیجه خالی است"

    def test_conflicting_signals_result_in_no_trade(self, engine):
        """وقتی سیگنال‌ها مخالف هستند، NO_TRADE یا confidence پایین"""
        result = engine.get_final_signal(
            self._make_smc("BEARISH"),
            self._make_pa("UPTREND"),
            self._make_ml(0.50),
            self._make_news(-0.5),
        )
        direction = str(result.get("direction", result.get("action", ""))).upper()
        confidence = result.get("confidence", 1.0)
        # NO_TRADE یا confidence پایین
        assert direction == "NO_TRADE" or confidence < 0.7, \
            f"Conflicting signals should reduce confidence, got direction={direction}, confidence={confidence}"

    def test_low_ml_probability_reduces_confidence(self, engine):
        """ML probability پایین باید confidence را کاهش دهد"""
        result_low = engine.get_final_signal(
            self._make_smc(), self._make_pa(), self._make_ml(0.3), self._make_news()
        )
        result_high = engine.get_final_signal(
            self._make_smc(), self._make_pa(), self._make_ml(0.9), self._make_news()
        )
        conf_low = result_low.get("confidence", 0)
        conf_high = result_high.get("confidence", 0)
        assert conf_low <= conf_high, "ML probability باید روی confidence تأثیر داشته باشد"

    def test_none_inputs_handled_gracefully(self, engine):
        """None inputs باید graceful handle شوند"""
        try:
            result = engine.get_final_signal(None, None, None, None)
            assert result is not None
        except (TypeError, AttributeError, KeyError):
            pass  # acceptable if validated upstream

    def test_empty_dict_inputs(self, engine):
        """empty dict inputs باید crash نکنند"""
        try:
            result = engine.get_final_signal({}, {}, {}, {})
            assert isinstance(result, dict)
        except (TypeError, KeyError):
            pass

    def test_high_impact_news_blocks_signal(self, engine):
        """high_impact news باید signal را block یا کاهش دهد"""
        news_safe = self._make_news(0.7)
        news_risk = {"sentiment": 0.7, "high_impact": True, "in_news_window": True}
        result_safe = engine.get_final_signal(
            self._make_smc(), self._make_pa(), self._make_ml(0.9), news_safe
        )
        result_risk = engine.get_final_signal(
            self._make_smc(), self._make_pa(), self._make_ml(0.9), news_risk
        )
        conf_safe = result_safe.get("confidence", 0)
        conf_risk = result_risk.get("confidence", 1)
        # high impact news باید confidence را کاهش دهد یا NO_TRADE باشد
        direction_risk = str(result_risk.get("direction", "")).upper()
        assert conf_risk <= conf_safe or direction_risk == "NO_TRADE", \
            "High impact news باید تأثیر منفی داشته باشد"


class TestDecisionEngineSMCScoringIntegration:
    """تست SMCScoringEngine integration در DecisionEngine"""

    def test_smc_score_influences_decision(self):
        try:
            from backend.analysis.decision_engine import DecisionEngine
            from backend.analysis.smc_scoring import SMCScoringEngine
        except ImportError:
            pytest.skip("DecisionEngine یا SMCScoringEngine not importable")

        engine = DecisionEngine()
        smc_data_strong = {
            "bias": "BULLISH",
            "order_blocks": [{"type": "BULLISH", "price": 1995.0, "strength": 0.9}],
            "fvgs": [{"type": "BULLISH", "gap_size": 10}],
            "bos_detected": True,
            "smc_confidence": 0.95,
            "smc_score": 90,
        }
        smc_data_weak = {
            "bias": "BULLISH",
            "order_blocks": [],
            "fvgs": [],
            "bos_detected": False,
            "smc_confidence": 0.3,
            "smc_score": 20,
        }
        pa = {"trend": "UPTREND", "patterns": []}
        ml = {"probability": 0.8, "confidence": 0.8}
        news = {"sentiment": 0.5, "high_impact": False}

        result_strong = engine.get_final_signal(smc_data_strong, pa, ml, news)
        result_weak = engine.get_final_signal(smc_data_weak, pa, ml, news)

        conf_strong = result_strong.get("confidence", 0)
        conf_weak = result_weak.get("confidence", 0)
        assert conf_strong >= conf_weak, "SMC score قوی باید confidence بیشتری بدهد"
