"""Tests for ContextEnricher — Phase F."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from typing import List, Dict, Any

from backend.services.context_enricher import (
    ContextEnricher,
    _get_session_context,
    _extract_smc_context,
    _extract_ml_context,
    get_context_enricher,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(n: int = 20) -> List[Dict[str, Any]]:
    candles = []
    price = 1.1000
    for i in range(n):
        candles.append({
            "open":  round(price, 5),
            "high":  round(price + 0.0010, 5),
            "low":   round(price - 0.0010, 5),
            "close": round(price + 0.0005, 5),
            "volume": 1000 + i * 10,
        })
        price += 0.0001
    return candles


def _mock_smc_result(
    bias="BULLISH",
    bos=True,
    choch=False,
    swing_high=1.1100,
    swing_low=1.0900,
):
    r = MagicMock()
    r.bias = bias
    r.bos_detected = bos
    r.choch_detected = choch
    r.swing_high = swing_high
    r.swing_low  = swing_low
    r.order_blocks = [
        MagicMock(high=1.1050, low=1.1020, direction="BULLISH",
                  strength=0.8, mitigated=False),
    ]
    r.fair_value_gaps = [
        MagicMock(high=1.1060, low=1.1040, direction="BULLISH", filled=False),
    ]
    r.liquidity_levels = []
    r.liquidity_sweep  = True
    r.internal_liquidity = False
    r.htf_alignment = "BULLISH"
    return r


# ---------------------------------------------------------------------------
# Session context tests
# ---------------------------------------------------------------------------

class TestSessionContext:
    def test_returns_required_keys(self):
        ctx = _get_session_context("EURUSD")
        assert "session" in ctx
        assert "in_kill_zone" in ctx
        assert "expected_slippage_pips" in ctx
        assert "trading_hour_utc" in ctx
        assert "active_sessions" in ctx
        assert "kill_zone_name" in ctx

    def test_slippage_is_positive(self):
        ctx = _get_session_context("GBPUSD")
        assert ctx["expected_slippage_pips"] > 0

    def test_high_impact_pair_lower_slippage(self):
        major = _get_session_context("EURUSD")["expected_slippage_pips"]
        exotic = _get_session_context("EURTRY")["expected_slippage_pips"]
        # major should be <= exotic (or at most equal for same session)
        assert major <= exotic

    def test_in_kill_zone_is_bool(self):
        ctx = _get_session_context("XAUUSD")
        assert isinstance(ctx["in_kill_zone"], bool)


# ---------------------------------------------------------------------------
# SMC context tests
# ---------------------------------------------------------------------------

class TestSMCContext:
    def test_none_result_returns_safe_defaults(self):
        ctx = _extract_smc_context(None)
        assert ctx["order_blocks"] == []
        assert ctx["fvgs"] == []
        assert ctx["bos_detected"] is False
        assert ctx["bias"] == "NEUTRAL"
        assert ctx["smc_confidence"] == 0.0

    def test_real_result_populates_keys(self):
        smc = _mock_smc_result()
        ctx = _extract_smc_context(smc, candles=_candles())
        assert ctx["bos_detected"] is True
        assert ctx["bias"] == "BULLISH"
        assert len(ctx["order_blocks"]) == 1
        assert len(ctx["fvgs"]) == 1
        assert ctx["smc_confidence"] > 0
        assert ctx["liquidity_sweep"] is True

    def test_premium_discount_zones_calculated(self):
        smc = _mock_smc_result(swing_high=1.1100, swing_low=1.0900)
        ctx = _extract_smc_context(smc)
        assert ctx["premium_zone"]  is not None
        assert ctx["discount_zone"] is not None
        assert ctx["premium_zone"]  > ctx["discount_zone"]

    def test_ob_to_dict_conversion(self):
        smc = _mock_smc_result()
        ctx = _extract_smc_context(smc)
        ob = ctx["order_blocks"][0]
        assert "high" in ob and "low" in ob
        assert "direction" in ob


# ---------------------------------------------------------------------------
# ML context tests
# ---------------------------------------------------------------------------

class TestMLContext:
    def test_none_engine_returns_safe_defaults(self):
        ctx = _extract_ml_context(None, {})
        pred = ctx["ai_prediction"]
        assert pred["probability"]  == 0.0
        assert pred["available"]    is False
        assert pred["direction"]    == "NEUTRAL"

    def test_real_engine_returns_prediction(self):
        engine = MagicMock()
        engine.predict.return_value = {"probability": 0.72, "model_auc": 0.83}
        signal_ctx = {
            "confidence": 0.8, "rr": 2.5, "smc_confidence": 0.6,
            "bos_detected": True, "in_kill_zone": True,
        }
        ctx = _extract_ml_context(engine, signal_ctx)
        pred = ctx["ai_prediction"]
        assert pred["available"]   is True
        assert pred["probability"] == pytest.approx(0.72, abs=0.001)
        assert pred["direction"]   == "BUY"
        assert pred["model_auc"]   == pytest.approx(0.83, abs=0.001)

    def test_engine_exception_returns_safe_defaults(self):
        engine = MagicMock()
        engine.predict.side_effect = RuntimeError("model not loaded")
        ctx = _extract_ml_context(engine, {})
        pred = ctx["ai_prediction"]
        assert pred["available"] is False
        assert "error" in pred


# ---------------------------------------------------------------------------
# ContextEnricher integration tests
# ---------------------------------------------------------------------------

class TestContextEnricher:
    def test_enrich_with_no_engines(self):
        enricher = ContextEnricher()
        base = {"symbol": "EURUSD", "direction": "BUY", "confidence": 0.7}
        ctx = enricher.enrich(base)
        # Session layer
        assert "session" in ctx
        assert "in_kill_zone" in ctx
        # SMC layer (empty but present)
        assert "order_blocks" in ctx
        assert "bos_detected" in ctx
        # ML layer (unavailable)
        assert ctx["ai_prediction"]["available"] is False

    def test_enrich_does_not_mutate_input(self):
        enricher = ContextEnricher()
        base = {"symbol": "GBPUSD", "direction": "SELL"}
        original = dict(base)
        enricher.enrich(base)
        assert base == original

    def test_enrich_with_smc_engine(self):
        smc_mock = MagicMock()
        smc_mock.analyse.return_value = _mock_smc_result()
        enricher = ContextEnricher(smc_engine=smc_mock)
        ctx = enricher.enrich(
            {"symbol": "EURUSD", "direction": "BUY"},
            candles=_candles(),
        )
        assert ctx["bos_detected"] is True
        assert len(ctx["order_blocks"]) == 1
        smc_mock.analyse.assert_called_once()

    def test_enrich_with_ml_engine(self):
        ml_mock = MagicMock()
        ml_mock.predict.return_value = {"probability": 0.65, "model_auc": 0.75}
        enricher = ContextEnricher(ml_engine=ml_mock)
        ctx = enricher.enrich({"symbol": "XAUUSD", "direction": "BUY"})
        assert ctx["ai_prediction"]["available"]   is True
        assert ctx["ai_prediction"]["probability"]  == pytest.approx(0.65, abs=0.001)

    def test_enrich_with_both_engines(self):
        smc_mock = MagicMock()
        smc_mock.analyse.return_value = _mock_smc_result(bos=True)
        ml_mock  = MagicMock()
        ml_mock.predict.return_value  = {"probability": 0.80, "model_auc": 0.90}
        enricher = ContextEnricher(smc_engine=smc_mock, ml_engine=ml_mock)
        ctx = enricher.enrich(
            {"symbol": "EURUSD", "direction": "BUY", "confidence": 0.75},
            candles=_candles(),
        )
        assert ctx["bos_detected"]                         is True
        assert ctx["ai_prediction"]["available"]           is True
        assert ctx["ai_prediction"]["probability"]         == pytest.approx(0.80, abs=0.001)
        assert ctx["ai_prediction"]["direction"]           == "BUY"
        assert "session" in ctx

    def test_set_engines_after_init(self):
        enricher = ContextEnricher()
        ml_mock  = MagicMock()
        ml_mock.predict.return_value = {"probability": 0.55}
        enricher.set_ml_engine(ml_mock)
        ctx = enricher.enrich({"symbol": "USDJPY", "direction": "SELL"})
        assert ctx["ai_prediction"]["available"] is True

    def test_singleton(self):
        e1 = get_context_enricher()
        e2 = get_context_enricher()
        assert e1 is e2
