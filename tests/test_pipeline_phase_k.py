"""
Phase K Tests — PriceAction + SMCScoring Pipeline Integration
24 test cases covering:
- Layer 4 PA enrichment (with/without engine)
- Layer 5 SMCScoring enrichment (with/without engine)
- Full 5-layer enrichment integration
- SignalProcessor with candles
- Context keys presence and types
- Fail-safe (no engine → defaults not crash)
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Any, Dict, List


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def sample_candles() -> List[Dict]:
 """20 synthetic OHLCV candles."""
 base = 2000.0
 candles = []
 for i in range(20):
 o = base + i * 0.5
 h = o + 1.2
 l = o - 0.8
 c = o + 0.3
 candles.append({"open": o, "high": h, "low": l, "close": c, "volume": 100 + i * 5})
 return candles


@pytest.fixture
def base_ctx() -> Dict[str, Any]:
 return {
 "symbol": "XAUUSD",
 "direction": "BUY",
 "confidence": 0.72,
 "rr": 2.5,
 "entry": 2010.0,
 "sl": 2005.0,
 "tp": 2022.5,
 "timeframe": "H1",
 }


@pytest.fixture
def mock_pa_result() -> Dict:
 return {
 "trend": "BULLISH",
 "patterns": ["hammer", "engulfing"],
 "support_resistance": [2005.0, 2015.0, 2025.0],
 "momentum": 0.65,
 "volatility": 1.2,
 }


@pytest.fixture
def mock_smc_score_result() -> Dict:
 return {
 "score": 78.5,
 "quality": "GOOD",
 "components": {
 "order_block": 25.0,
 "fvg": 15.0,
 "bos": 20.0,
 "liquidity": 18.5,
 },
 }


# ── Layer 4: Price Action Tests ───────────────────────────────────────────────
class TestPAEnrichmentLayer:

 def test_pa_no_engine_sets_defaults(self, base_ctx, sample_candles):
 """Without PA engine, context gets safe defaults — no crash."""
 from backend.services import context_enricher as ce
 original = ce._pa_engine
 ce._pa_engine = None
 try:
 result = ce._enrich_pa(dict(base_ctx), sample_candles)
 assert result["pa_trend"] == "NEUTRAL"
 assert result["pa_patterns"] == []
 assert result["pa_sr_levels"] == []
 assert result["pa_momentum"] == 0.0
 assert result["pa_available"] is False
 finally:
 ce._pa_engine = original

 def test_pa_engine_result_populates_context(self, base_ctx, sample_candles, mock_pa_result):
 """PA engine result correctly mapped to context keys."""
 from backend.services import context_enricher as ce

 mock_engine = MagicMock()
 mock_engine.analyze.return_value = mock_pa_result

 original = ce._pa_engine
 ce._pa_engine = mock_engine
 try:
 result = ce._enrich_pa(dict(base_ctx), sample_candles)
 assert result["pa_trend"] == "BULLISH"
 assert "hammer" in result["pa_patterns"]
 assert len(result["pa_sr_levels"]) == 3
 assert result["pa_momentum"] == pytest.approx(0.65)
 assert result["pa_volatility"] == pytest.approx(1.2)
 assert result["pa_available"] is True
 assert "pa_result" in result
 finally:
 ce._pa_engine = original

 def test_pa_engine_exception_sets_defaults(self, base_ctx, sample_candles):
 """PA engine exception → safe defaults, no crash."""
 from backend.services import context_enricher as ce

 mock_engine = MagicMock()
 mock_engine.analyze.side_effect = RuntimeError("PA engine error")

 original = ce._pa_engine
 ce._pa_engine = mock_engine
 try:
 result = ce._enrich_pa(dict(base_ctx), sample_candles)
 assert result["pa_trend"] == "NEUTRAL"
 assert result["pa_available"] is False
 finally:
 ce._pa_engine = original

 def test_pa_trend_enum_value_normalised(self, base_ctx, sample_candles):
 """Enum trend value is converted to string."""
 from backend.services import context_enricher as ce
 from unittest.mock import MagicMock

 class FakeTrend:
 value = "BEARISH"

 mock_engine = MagicMock()
 mock_engine.analyze.return_value = {"trend": FakeTrend(), "patterns": [], "momentum": 0.0, "volatility": 0.0}

 original = ce._pa_engine
 ce._pa_engine = mock_engine
 try:
 result = ce._enrich_pa(dict(base_ctx), sample_candles)
 assert result["pa_trend"] == "BEARISH"
 finally:
 ce._pa_engine = original

 def test_pa_no_candles_sets_defaults(self, base_ctx):
 """Empty candles list → PA defaults regardless of engine."""
 from backend.services import context_enricher as ce
 mock_engine = MagicMock()
 original = ce._pa_engine
 ce._pa_engine = mock_engine
 try:
 result = ce._enrich_pa(dict(base_ctx), [])
 assert result["pa_available"] is False
 mock_engine.analyze.assert_not_called()
 finally:
 ce._pa_engine = original


# ── Layer 5: SMC Scoring Tests ───────────────────────────────────────────────
class TestSMCScoringLayer:

 def test_scoring_no_engine_sets_defaults(self, base_ctx):
 """Without scoring engine, context gets safe defaults."""
 from backend.services import context_enricher as ce
 original = ce._smc_scoring_engine
 ce._smc_scoring_engine = None
 try:
 result = ce._enrich_smc_scoring(dict(base_ctx))
 assert result["smc_score"] == 0.0
 assert result["smc_quality"] == "POOR"
 assert result["smc_components"] == {}
 finally:
 ce._smc_scoring_engine = original

 def test_scoring_engine_result_populates_context(self, base_ctx, mock_smc_score_result):
 """SMCScoring engine result correctly mapped to context."""
 from backend.services import context_enricher as ce

 mock_engine = MagicMock()
 mock_engine.score.return_value = mock_smc_score_result

 original = ce._smc_scoring_engine
 ce._smc_scoring_engine = mock_engine
 try:
 result = ce._enrich_smc_scoring(dict(base_ctx))
 assert result["smc_score"] == pytest.approx(78.5)
 assert result["smc_quality"] == "GOOD"
 assert "order_block" in result["smc_components"]
 finally:
 ce._smc_scoring_engine = original

 def test_scoring_uses_smc_analysis_if_present(self, base_ctx, mock_smc_score_result):
 """Scoring engine receives smc_analysis when present."""
 from backend.services import context_enricher as ce

 mock_engine = MagicMock()
 mock_engine.score.return_value = mock_smc_score_result

 ctx = dict(base_ctx)
 ctx["smc_analysis"] = {"bias": "BULLISH", "bos_detected": True}

 original = ce._smc_scoring_engine
 ce._smc_scoring_engine = mock_engine
 try:
 ce._enrich_smc_scoring(ctx)
 call_args = mock_engine.score.call_args[0][0]
 assert "bias" in call_args
 finally:
 ce._smc_scoring_engine = original

 def test_scoring_exception_sets_defaults(self, base_ctx):
 """Scoring engine exception → safe defaults."""
 from backend.services import context_enricher as ce

 mock_engine = MagicMock()
 mock_engine.score.side_effect = ValueError("scoring error")

 original = ce._smc_scoring_engine
 ce._smc_scoring_engine = mock_engine
 try:
 result = ce._enrich_smc_scoring(dict(base_ctx))
 assert result["smc_score"] == 0.0
 assert result["smc_quality"] == "POOR"
 finally:
 ce._smc_scoring_engine = original


# ── Full 5-Layer Enrichment Tests ────────────────────────────────────────────
class TestFull5LayerEnrichment:

 @pytest.mark.asyncio
 async def test_all_5_layers_keys_present(self, base_ctx, sample_candles):
 """After enrich(), all 5 layer keys must be present."""
 from backend.services import context_enricher as ce

 # Patch ML prediction to avoid real model
 with patch("backend.services.context_enricher._enrich_ml", new_callable=AsyncMock) as mock_ml:
 mock_ml.side_effect = lambda ctx: asyncio.coroutine(lambda: {
 **ctx,
 "ai_prediction": {"probability": 0.7, "confidence": 0.8, "direction": "BUY", "model_auc": 0.85, "available": True}
 })()

 result = await ce.enrich(base_ctx, sample_candles)

 # Layer 1 — Session
 assert "session" in result
 assert "in_kill_zone" in result
 assert "expected_slippage_pips" in result

 # Layer 2 — SMC
 assert "order_blocks" in result
 assert "bos_detected" in result
 assert "smc_analysis" in result

 # Layer 3 — ML
 assert "ai_prediction" in result

 # Layer 4 — PA
 assert "pa_trend" in result
 assert "pa_patterns" in result
 assert "pa_sr_levels" in result

 # Layer 5 — SMC Scoring
 assert "smc_score" in result
 assert "smc_quality" in result
 assert "smc_components" in result

 @pytest.mark.asyncio
 async def test_enrich_does_not_mutate_base_ctx(self, base_ctx, sample_candles):
 """enrich() returns a copy; original base_ctx is not mutated."""
 from backend.services import context_enricher as ce
 original_keys = set(base_ctx.keys())

 with patch("backend.services.context_enricher._enrich_ml", new_callable=AsyncMock) as mock_ml:
 mock_ml.side_effect = lambda ctx: asyncio.coroutine(lambda: ctx)()
 await ce.enrich(base_ctx, sample_candles)

 assert set(base_ctx.keys()) == original_keys

 @pytest.mark.asyncio
 async def test_enrich_with_empty_candles(self, base_ctx):
 """enrich() with no candles — must not crash, PA/SMC get defaults."""
 from backend.services import context_enricher as ce

 with patch("backend.services.context_enricher._enrich_ml", new_callable=AsyncMock) as mock_ml:
 mock_ml.side_effect = lambda ctx: asyncio.coroutine(lambda: ctx)()
 result = await ce.enrich(base_ctx, [])

 assert result["pa_available"] is False
 assert result["order_blocks"] == []


# ── SignalProcessor Integration Tests ──────────────────────────────────────────
class TestSignalProcessorPhaseK:

 def _make_signal(self, **kwargs):
 class Sig:
 symbol = kwargs.get("symbol", "XAUUSD")
 direction = kwargs.get("direction", "BUY")
 confidence = kwargs.get("confidence", 0.72)
 rr = kwargs.get("rr", 2.5)
 entry = kwargs.get("entry", 2010.0)
 sl = kwargs.get("sl", 2005.0)
 tp = kwargs.get("tp", 2022.5)
 timeframe = kwargs.get("timeframe", "H1")
 return Sig()

 @pytest.mark.asyncio
 async def test_process_returns_pa_fields(self, sample_candles):
 """ProcessedSignal must include pa_trend and smc_score keys."""
 from backend.services.signal_processor import SignalProcessor

 sp = SignalProcessor()

 with patch("backend.services.signal_processor.enrich", new_callable=AsyncMock) as mock_enrich, \
 patch.object(sp._voting, "vote", new_callable=AsyncMock) as mock_vote:

 mock_enrich.return_value = {
 "symbol": "XAUUSD", "direction": "BUY",
 "confidence": 0.72, "rr": 2.5,
 "entry": 2010.0, "sl": 2005.0, "tp": 2022.5,
 "timeframe": "H1",
 "session": "london", "in_kill_zone": True,
 "pa_trend": "BULLISH", "pa_patterns": ["hammer"],
 "pa_sr_levels": [2005.0], "pa_momentum": 0.6,
 "pa_available": True,
 "smc_score": 75.0, "smc_quality": "GOOD", "smc_components": {},
 "ai_prediction": {"probability": 0.72, "confidence": 0.8,
 "direction": "BUY", "model_auc": 0.85, "available": True},
 "order_blocks": [], "fvgs": [], "bos_detected": True,
 }
 mock_vote.return_value = {"decision": "BUY", "score": 80}

 sig = self._make_signal()
 result = await sp.process(sig, sample_candles)

 assert result["pa_trend"] == "BULLISH"
 assert result["smc_score"] == 75.0
 assert result["smc_quality"] == "GOOD"
 assert result["decision"] == "BUY"
 assert result["ai_probability"] == pytest.approx(0.72)

 @pytest.mark.asyncio
 async def test_process_low_rr_rejected(self):
 """Signal with RR < 1.5 is rejected before enrichment."""
 from backend.services.signal_processor import SignalProcessor
 sp = SignalProcessor()
 sig = self._make_signal(rr=1.0)
 result = await sp.process(sig)
 assert result["decision"] == "NO_TRADE"
 assert result.get("rejection_reason") == "validation_failed"

 @pytest.mark.asyncio
 async def test_register_engines_module_level(self):
 """register_engines() sets module-level vars."""
 from backend.services import signal_processor as sp_module
 mock_pa = MagicMock()
 sp_module.register_engines(pa_engine=mock_pa)
 assert sp_module._pa_engine is mock_pa
 # cleanup
 sp_module._pa_engine = None


# ── register_engines Tests ──────────────────────────────────────────────────────────
class TestRegisterEngines:

 def test_register_all_5_engines(self):
 """register_engines() accepts all 5 engine params."""
 from backend.services import context_enricher as ce

 mock_smc = MagicMock()
 mock_ml = MagicMock()
 mock_pa = MagicMock()
 mock_scoring = MagicMock()

 ce.register_engines(
 smc_engine=mock_smc,
 ml_engine=mock_ml,
 pa_engine=mock_pa,
 smc_scoring_engine=mock_scoring,
 )

 assert ce._smc_engine is mock_smc
 assert ce._ml_engine is mock_ml
 assert ce._pa_engine is mock_pa
 assert ce._smc_scoring_engine is mock_scoring

 # cleanup
 ce._smc_engine = None
 ce._ml_engine = None
 ce._pa_engine = None
 ce._smc_scoring_engine = None

 def test_register_partial_engines(self):
 """register_engines() with only some engines — no error."""
 from backend.services import context_enricher as ce
 mock_pa = MagicMock()
 ce.register_engines(pa_engine=mock_pa)
 assert ce._pa_engine is mock_pa
 ce._pa_engine = None

 def test_get_enricher_singleton(self):
 """get_enricher() returns same instance."""
 from backend.services.context_enricher import get_enricher
 a = get_enricher()
 b = get_enricher()
 assert a is b
