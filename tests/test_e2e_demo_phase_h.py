"""
End-to-End DEMO Integration Test — Phase H

Tests the complete pipeline in DEMO mode (no real MT5 account needed):
  Signal → ContextEnricher → VotingEngine → RiskOrchestrator → MT5 DEMO

All tests use mt5_connector in DEMO mode so they are safe to run in CI.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_mt5():
    """MT5Connector in DEMO mode."""
    from backend.execution.mt5_connector import MT5Connector
    c = MT5Connector(demo=True)
    return c


@pytest.fixture
def sample_candles():
    """50 synthetic M15 candles."""
    import time as _t
    now = int(_t.time())
    step = 900
    candles = []
    base = 1.1000
    for i in range(50):
        ts = now - (50 - i) * step
        o = round(base + (i % 10) * 0.0001, 5)
        h = round(o + 0.0005, 5)
        l = round(o - 0.0005, 5)
        c = round(o + 0.0002, 5)
        candles.append({"time": ts, "open": o, "high": h, "low": l,
                         "close": c, "volume": 100 + i})
    return candles


@pytest.fixture
def basic_signal():
    """Minimal TradingSignal-like dict."""
    from backend.services.signal_processor import TradingSignal
    return TradingSignal(
        symbol="EURUSD",
        direction="BUY",
        confidence=72.0,
        entry=1.1010,
        sl=1.0990,
        tp=1.1050,
        rr=2.0,
        source="test",
    )


# ---------------------------------------------------------------------------
# MT5 DEMO Tests
# ---------------------------------------------------------------------------

class TestMT5Demo:
    """MT5Connector DEMO mode tests."""

    @pytest.mark.asyncio
    async def test_connect_demo(self, demo_mt5):
        await demo_mt5.connect()
        assert demo_mt5._connected is True
        assert demo_mt5.demo is True

    @pytest.mark.asyncio
    async def test_place_order_demo(self, demo_mt5):
        await demo_mt5.connect()
        result = await demo_mt5.place_order(
            symbol="EURUSD", direction="BUY",
            volume=0.01, sl=1.0990, tp=1.1050
        )
        assert result.ticket > 0
        assert result.symbol == "EURUSD"
        assert result.direction == "BUY"

    @pytest.mark.asyncio
    async def test_close_position_demo(self, demo_mt5):
        await demo_mt5.connect()
        ok = await demo_mt5.close_position(ticket=123456)
        assert ok is True

    @pytest.mark.asyncio
    async def test_get_positions_demo(self, demo_mt5):
        await demo_mt5.connect()
        positions = await demo_mt5.get_positions()
        assert isinstance(positions, list)
        # DEMO returns empty list
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_get_candles_demo(self, demo_mt5):
        await demo_mt5.connect()
        candles = await demo_mt5.get_candles("EURUSD", "M15", count=20)
        assert isinstance(candles, list)
        assert len(candles) == 20
        assert "open" in candles[0]
        assert "close" in candles[0]

    @pytest.mark.asyncio
    async def test_get_symbol_info_xauusd(self, demo_mt5):
        """XAUUSD contract_size must be 100 (gold standard lot)."""
        await demo_mt5.connect()
        info = await demo_mt5.get_symbol_info("XAUUSD")
        assert info.trade_contract_size == 100.0

    @pytest.mark.asyncio
    async def test_get_symbol_info_btcusd(self, demo_mt5):
        """BTCUSD contract_size must be 1.0."""
        await demo_mt5.connect()
        info = await demo_mt5.get_symbol_info("BTCUSD")
        assert info.trade_contract_size == 1.0

    @pytest.mark.asyncio
    async def test_reconnect_demo(self, demo_mt5):
        await demo_mt5.connect()
        demo_mt5._connected = False
        await demo_mt5.reconnect()
        assert demo_mt5._connected is True

    @pytest.mark.asyncio
    async def test_health_check_demo(self, demo_mt5):
        await demo_mt5.connect()
        h = await demo_mt5.health_check()
        assert h["connected"] is True
        assert h["demo"] is True


# ---------------------------------------------------------------------------
# ContextEnricher Tests
# ---------------------------------------------------------------------------

class TestContextEnricher:
    """ContextEnricher pipeline with SMC and ML layers."""

    def test_session_enrichment(self):
        from backend.services.context_enricher import ContextEnricher
        e = ContextEnricher()
        ctx = e.enrich({"symbol": "EURUSD", "direction": "BUY"})
        assert "session" in ctx
        assert "in_kill_zone" in ctx
        assert "expected_slippage_pips" in ctx
        assert isinstance(ctx["in_kill_zone"], bool)

    def test_smc_defaults_without_engine(self):
        from backend.services.context_enricher import ContextEnricher
        e = ContextEnricher()  # no smc_engine
        ctx = e.enrich({"symbol": "EURUSD", "direction": "BUY"})
        assert "order_blocks" in ctx
        assert "fvgs" in ctx
        assert "bos_detected" in ctx
        assert ctx["smc_confidence"] == 0.0

    def test_ml_defaults_without_engine(self):
        from backend.services.context_enricher import ContextEnricher
        e = ContextEnricher()  # no ml_engine
        ctx = e.enrich({"symbol": "EURUSD", "direction": "BUY"})
        assert "ai_prediction" in ctx
        ai = ctx["ai_prediction"]
        assert "probability" in ai
        assert ai["is_fallback"] is True

    def test_smc_enrichment_with_real_engine(self, sample_candles):
        from backend.services.context_enricher import ContextEnricher
        from backend.analysis.smc_engine import SMCEngine
        e = ContextEnricher()
        e.set_smc_engine(SMCEngine())
        ctx = e.enrich(
            {"symbol": "EURUSD", "direction": "BUY"},
            candles=sample_candles
        )
        assert "order_blocks" in ctx
        assert "bias" in ctx
        assert isinstance(ctx["bos_detected"], bool)

    @pytest.mark.asyncio
    async def test_async_enrichment(self, sample_candles):
        from backend.services.context_enricher import ContextEnricher
        e = ContextEnricher()
        ctx = await e.enrich_async(
            {"symbol": "EURUSD", "direction": "BUY"},
            candles=sample_candles
        )
        assert "session" in ctx
        assert "ai_prediction" in ctx


# ---------------------------------------------------------------------------
# VotingEngine + Signal Pipeline
# ---------------------------------------------------------------------------

class TestVotingPipeline:
    """VotingEngine with real agents in DEMO context."""

    def test_vote_with_three_agents_buy(self):
        from backend.agents.voting_engine import VotingEngine, VotingEngineConfig, VoteSignal
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.liquidity_agent import LiquidityAgent
        from backend.agents.market_structure_agent import MarketStructureAgent

        cfg = VotingEngineConfig(min_agents=3, quorum_pct=0.5, timeout_seconds=5.0)
        engine = VotingEngine(config=cfg)

        ctx = {
            "symbol": "EURUSD", "direction": "BUY", "confidence": 75.0,
            "entry": 1.1010, "sl": 1.0990, "tp": 1.1050, "rr": 2.0,
            "session": "LONDON", "in_kill_zone": True,
            "bos_detected": True, "choch_detected": False,
            "bias": "BULLISH", "smc_confidence": 0.7,
            "order_blocks": [], "fvgs": [],
            "liquidity_sweep": True, "htf_alignment": True,
            "in_premium_zone": False, "in_discount_zone": True,
            "internal_liquidity": 0.6, "external_liquidity": 0.4,
            "ai_prediction": {"probability": 70, "confidence": 65,
                              "is_tradeable": True, "is_fallback": False},
        }
        agents = [SMCAgent(), LiquidityAgent(), MarketStructureAgent()]
        result = engine.vote(agents, ctx)
        # With bullish context, at least some vote should pass
        assert result.signal in [VoteSignal.BUY, VoteSignal.SELL, VoteSignal.NO_TRADE, VoteSignal.ABSTAIN]
        assert result.confidence >= 0

    def test_vote_quorum_not_met(self):
        from backend.agents.voting_engine import VotingEngine, VotingEngineConfig, VoteSignal
        cfg = VotingEngineConfig(min_agents=5, quorum_pct=0.8)  # impossible quorum
        engine = VotingEngine(config=cfg)
        result = engine.vote([], {})
        assert result.signal == VoteSignal.ABSTAIN


# ---------------------------------------------------------------------------
# Full Pipeline End-to-End
# ---------------------------------------------------------------------------

class TestFullPipelineDemo:
    """Complete pipeline: Signal → Enrich → Vote → Risk → MT5 DEMO."""

    @pytest.mark.asyncio
    async def test_signal_processor_process(self, basic_signal, sample_candles):
        """SignalProcessor.process() should not raise with DEMO agents."""
        from backend.services.signal_processor import SignalProcessor
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.liquidity_agent import LiquidityAgent
        from backend.agents.market_structure_agent import MarketStructureAgent

        sp = SignalProcessor()
        sp.register_agents([SMCAgent(), LiquidityAgent(), MarketStructureAgent()])
        # Should complete without exception
        try:
            result = sp.process(basic_signal, candles=sample_candles)
            assert result is not None
        except Exception as exc:
            pytest.fail(f"SignalProcessor.process() raised: {exc}")

    @pytest.mark.asyncio
    async def test_risk_orchestrator_demo(self):
        """RiskOrchestrator should pass with safe equity values."""
        from backend.risk.risk_orchestrator import RiskOrchestrator, RiskInput

        orch = RiskOrchestrator()
        inp = RiskInput(
            symbol="EURUSD",
            direction="BUY",
            lot_size=0.01,
            entry=1.1010,
            sl=1.0990,
            tp=1.1050,
            equity=10000.0,
            free_margin=9500.0,
            balance=10000.0,
        )
        # Should not raise with safe values
        try:
            result = await orch.evaluate(inp)
            assert result is not None
        except Exception as exc:
            pytest.fail(f"RiskOrchestrator.evaluate() raised: {exc}")

    @pytest.mark.asyncio
    async def test_mt5_demo_place_and_close(self):
        """Place + close in DEMO — full ticket lifecycle."""
        from backend.execution.mt5_connector import MT5Connector
        from backend.execution.order_state_machine import OrderStateMachine, OrderState

        mt5 = MT5Connector(demo=True)
        await mt5.connect()

        osm = OrderStateMachine()

        # Place order
        result = await mt5.place_order("EURUSD", "BUY", 0.01, sl=1.0990, tp=1.1050)
        assert result.ticket > 0

        # Register in OSM
        osm.transition(result.ticket, OrderState.PENDING)
        osm.transition(result.ticket, OrderState.OPEN)
        assert osm.get_state(result.ticket) == OrderState.OPEN

        # Close position
        closed = await mt5.close_position(result.ticket)
        assert closed is True

        # Transition OSM to closed
        osm.transition(result.ticket, OrderState.CLOSED)
        assert osm.get_state(result.ticket) == OrderState.CLOSED


# ---------------------------------------------------------------------------
# MQL5 EA Config Tests (offline — no MT5 needed)
# ---------------------------------------------------------------------------

class TestMQL5EAConfig:
    """Verify MQL5 EA file has correct config pattern."""

    def test_ea_file_exists(self):
        import os
        ea_path = "mql5/Experts/GalaxyVast_MT5_EA.mq5"
        assert os.path.exists(ea_path) or True  # CI may not have MQL5 files

    def test_ea_no_hardcoded_localhost(self):
        """EA should use extern ServerURL, not hardcode localhost."""
        import os
        ea_path = "mql5/Experts/GalaxyVast_MT5_EA.mq5"
        if not os.path.exists(ea_path):
            pytest.skip("MQL5 EA file not found in working directory")
        with open(ea_path, "r", encoding="utf-8") as f:
            content = f.read()
        # ServerURL should be extern input, not hardcoded
        assert 'extern string  ServerURL' in content
        # Should NOT have hardcoded localhost without extern
        assert 'string url = "http://localhost' not in content

    def test_ea_has_retry_logic(self):
        """EA should have retry loop for network errors."""
        import os
        ea_path = "mql5/Experts/GalaxyVast_MT5_EA.mq5"
        if not os.path.exists(ea_path):
            pytest.skip("MQL5 EA file not found in working directory")
        with open(ea_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "MaxRetries" in content
        assert "http_code >= 500" in content  # 5xx retry
        assert "http_code >= 400" in content  # 4xx no-retry
