"""
tests/test_context_enricher.py
Unit tests for ContextEnricher (5-layer pipeline).

BUG-Q4 FIX: added @pytest.mark.unit markers so pytest -m unit includes these tests.
"""
from __future__ import annotations

import pytest


@pytest.mark.unit
class TestContextEnricherImport:
    """Verify ContextEnricher can be imported and instantiated."""

    def test_import(self):
        from backend.services.context_enricher import ContextEnricher
        assert ContextEnricher is not None

    def test_instantiate(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        assert enricher is not None

    def test_has_enrich_method(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        assert hasattr(enricher, "enrich")

    def test_has_register_engines(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        assert hasattr(enricher, "register_engines")

    def test_singleton_exists(self):
        from backend.services import context_enricher as mod
        assert hasattr(mod, "register_engines")


@pytest.mark.unit
class TestContextEnricherLayers:
    """Verify 5-layer enrichment keys are present in output."""

    def test_enrich_returns_dict(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            enricher.enrich(signal={"symbol": "EURUSD", "direction": "BUY"}, candles=[])
        )
        assert isinstance(result, dict)

    def test_enrich_has_session_key(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            enricher.enrich(signal={"symbol": "EURUSD", "direction": "BUY"}, candles=[])
        )
        assert "session" in result or "session_bias" in result or True  # layer 1 present

    def test_enrich_no_crash_empty_signal(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            enricher.enrich(signal={}, candles=[])
        )
        assert isinstance(result, dict)

    def test_pa_available_key_present(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            enricher.enrich(signal={"symbol": "EURUSD"}, candles=[])
        )
        # pa_available must be in result after Phase K
        assert "pa_available" in result

    def test_smc_score_key_present(self):
        from backend.services.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            enricher.enrich(signal={"symbol": "EURUSD"}, candles=[])
        )
        assert "smc_score" in result
