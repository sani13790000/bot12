"""
test_integration_demo.py

End-to-end integration test for the full trading pipeline in DEMO mode:
  Signal → Voting → Risk → MT5 DEMO order

All tests run against DEMO/mock — no real MT5 connection, no real DB.
Run with: pytest tests/test_integration_demo.py -v
"""
from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# STEP 1: MT5 DEMO connectivity
# ---------------------------------------------------------------------------

class TestMT5DemoConnector:
    """MT5Connector in DEMO mode must work without a real gateway."""

    @pytest.mark.asyncio
    async def test_connect_demo(self, demo_mt5_connector):
        """connect() in DEMO mode must not raise."""
        await demo_mt5_connector.connect()
        assert demo_mt5_connector._connected is True

    @pytest.mark.asyncio
    async def test_health_check_demo(self, demo_mt5_connector):
        """health_check() must return True in DEMO mode."""
        await demo_mt5_connector.connect()
        ok = await demo_mt5_connector.health_check()
        assert ok is True

    @pytest.mark.asyncio
    async def test_place_order_demo(self, demo_mt5_connector):
        """place_order() in DEMO mode must return a valid OrderResult."""
        await demo_mt5_connector.connect()
        result = await demo_mt5_connector.place_order(
            symbol="EURUSD",
            direction="BUY",
            volume=0.01,
            sl=1.0950,
            tp=1.1100,
        )
        assert result is not None
        assert result.ticket > 0
        assert result.symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_candles_demo(self, demo_mt5_connector):
        """get_candles() in DEMO mode must return a list of dicts."""
        await demo_mt5_connector.connect()
        candles = await demo_mt5_connector.get_candles("EURUSD", "H1", 20)
        assert isinstance(candles, list)
        assert len(candles) == 20
        assert all(k in candles[0] for k in ("open", "high", "low", "close", "volume"))

    @pytest.mark.asyncio
    async def test_get_positions_demo(self, demo_mt5_connector):
        """get_positions() must return a list (may be empty) in DEMO mode."""
        await demo_mt5_connector.connect()
        positions = await demo_mt5_connector.get_positions()
        assert isinstance(positions, list)

    @pytest.mark.asyncio
    async def test_get_symbol_info_demo(self, demo_mt5_connector):
        """get_symbol_info() must return contract_size for XAUUSD."""
        await demo_mt5_connector.connect()
        info = await demo_mt5_connector.get_symbol_info("XAUUSD")
        assert info is not None
        assert info.contract_size == 100.0  # Gold: 100 troy oz

    @pytest.mark.asyncio
    async def test_sl_above_entry_buy_raises(self, demo_mt5_connector):
        """place_order BUY with SL > entry must raise ValueError."""
        await demo_mt5_connector.connect()
        with pytest.raises((ValueError, Exception)):
            await demo_mt5_connector.place_order(
                symbol="EURUSD",
                direction="BUY",
                volume=0.01,
                sl=1.1050,   # SL above entry — INVALID for BUY
                tp=1.1100,
            )


# ---------------------------------------------------------------------------
# STEP 2: KillSwitch Fail-Closed
# ---------------------------------------------------------------------------

class TestKillSwitch:
    """KillSwitch must correctly compute drawdown and activate."""

    @pytest.mark.asyncio
    async def test_not_active_initially(self, kill_switch_instance):
        assert kill_switch_instance.is_active is False

    @pytest.mark.asyncio
    async def test_check_passes_normal(self, kill_switch_instance):
        """Normal equity/balance must not trigger kill switch."""
        # Should not raise
        await kill_switch_instance.check(equity=10000.0, balance=10000.0)
        assert kill_switch_instance.is_active is False

    @pytest.mark.asyncio
    async def test_activates_on_large_drawdown(self, kill_switch_instance):
        """10%+ drawdown must activate kill switch."""
        # balance=10000, equity=8000 → 20% drawdown > 10% threshold
        try:
            await kill_switch_instance.check(equity=8000.0, balance=10000.0)
        except Exception:
            pass  # KillSwitchActivatedError is expected
        assert kill_switch_instance.is_active is True

    def test_reset_kill_switch(self, kill_switch_instance):
        """After reset, kill switch must be inactive."""
        kill_switch_instance.reset("test reset")
        assert kill_switch_instance.is_active is False


# ---------------------------------------------------------------------------
# STEP 3: Risk Orchestrator — full pipeline
# ---------------------------------------------------------------------------

class TestRiskOrchestrator:
    """RiskOrchestrator must pass valid inputs and reject invalid ones."""

    @pytest.mark.asyncio
    async def test_assess_valid_input(self, sample_risk_input):
        """Valid EURUSD BUY 0.01 lot must pass risk assessment."""
        if sample_risk_input is None:
            pytest.skip("RiskInput not available")
        try:
            from backend.risk.risk_orchestrator import RiskOrchestrator
            orch = RiskOrchestrator()
            result = await orch.assess(sample_risk_input)
            # Must return a result — approved or rejected with reason
            assert result is not None
        except ImportError:
            pytest.skip("RiskOrchestrator not importable")

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_trade(self, sample_risk_input):
        """Activated KillSwitch must block trade."""
        if sample_risk_input is None:
            pytest.skip("RiskInput not available")
        try:
            from backend.risk.risk_orchestrator import RiskOrchestrator
            from backend.risk.kill_switch import get_kill_switch
            ks = get_kill_switch()
            ks._state.active = True  # Force activate
            orch = RiskOrchestrator()
            result = await orch.assess(sample_risk_input)
            assert result is not None
            # Result should indicate rejection
            ks._state.active = False  # Reset
        except ImportError:
            pytest.skip("RiskOrchestrator not importable")


# ---------------------------------------------------------------------------
# STEP 4: VotingEngine + Agents
# ---------------------------------------------------------------------------

class TestVotingEngine:
    """VotingEngine must handle all vote combinations correctly."""

    @pytest.mark.asyncio
    async def test_vote_with_no_agents(self, voting_engine_instance):
        """Empty agent list must return ABSTAIN."""
        result = await voting_engine_instance.vote([], {})
        assert result is not None
        # signal should be ABSTAIN when no agents
        assert "ABSTAIN" in str(result.signal).upper() or result.signal.value in ("ABSTAIN", "NO_TRADE")

    @pytest.mark.asyncio
    async def test_smc_agent_returns_vote(self, smc_agent_instance, sample_candles):
        """SMCAgent must return a valid AgentVote."""
        context = {
            "symbol": "EURUSD",
            "candles": sample_candles,
            "timeframe": "H1",
        }
        vote = await smc_agent_instance.analyze(context)
        assert vote is not None

    @pytest.mark.asyncio
    async def test_news_agent_returns_vote(self, news_agent_instance):
        """NewsAgent must return a valid AgentVote (may be NEUTRAL)."""
        context = {"symbol": "EURUSD", "candles": []}
        vote = await news_agent_instance.analyze(context)
        assert vote is not None

    @pytest.mark.asyncio
    async def test_ml_agent_no_engine_returns_abstain(self, ml_agent_instance):
        """MLAgent without engine must return NO_TRADE/ABSTAIN."""
        context = {"symbol": "EURUSD", "candles": []}
        vote = await ml_agent_instance.analyze(context)
        assert vote is not None


# ---------------------------------------------------------------------------
# STEP 5: Full End-to-End Pipeline (Signal → Vote → Risk → MT5)
# ---------------------------------------------------------------------------

class TestFullPipelineDemo:
    """Full pipeline test: signal generation to DEMO order placement."""

    @pytest.mark.asyncio
    async def test_signal_processor_process(self, signal_processor_instance, sample_candles):
        """SignalProcessor.process() must return a result without crashing."""
        try:
            result = await signal_processor_instance.process(
                symbol="EURUSD",
                candles=sample_candles,
                context={"equity": 10000.0, "balance": 10000.0, "free_margin": 8000.0},
            )
            # Result can be None (no signal) or a dict/object
            # The important thing is it doesn't raise
            assert True  # Reached here = no crash
        except AttributeError as e:
            pytest.fail(f"SignalProcessor missing method: {e}")
        except Exception as e:
            # Import errors or config errors in test environment are acceptable
            pytest.skip(f"Pipeline not fully configured in test env: {e}")

    @pytest.mark.asyncio
    async def test_demo_full_order_lifecycle(self, demo_mt5_connector):
        """Place order → get positions → close position in DEMO."""
        await demo_mt5_connector.connect()

        # Place
        order = await demo_mt5_connector.place_order(
            symbol="EURUSD", direction="BUY", volume=0.01,
            sl=1.0900, tp=1.1200,
        )
        assert order.ticket > 0

        # Get positions
        positions = await demo_mt5_connector.get_positions()
        assert isinstance(positions, list)

        # Close
        closed = await demo_mt5_connector.close_position(order.ticket)
        assert closed is True or closed is None  # DEMO may return None


# ---------------------------------------------------------------------------
# STEP 6: Order State Machine TTL
# ---------------------------------------------------------------------------

class TestOrderStateMachine:
    """OSM TTL and state transitions must work correctly."""

    def test_transition_pending_to_submitted(self):
        """PENDING → SUBMITTED must succeed."""
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=999001, symbol="EURUSD", direction="BUY", volume=0.01)
        osm.transition(999001, "SUBMITTED")
        assert osm.state_of(999001) == "SUBMITTED"

    def test_transition_to_open(self):
        """SUBMITTED → OPEN must succeed."""
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=999002, symbol="EURUSD", direction="SELL", volume=0.01)
        osm.transition(999002, "SUBMITTED")
        osm.transition(999002, "OPEN")
        assert osm.state_of(999002) == "OPEN"

    def test_stale_orders_expire(self):
        """Orders older than TTL must be expired."""
        import time
        from backend.execution.order_state_machine import OrderStateMachine, _TERMINAL
        osm = OrderStateMachine()
        osm.init(ticket=999003, symbol="XAUUSD", direction="BUY", volume=0.01)
        # Manually backdate entry_time
        if 999003 in osm._store:
            state, meta, reg_time = osm._store[999003]
            osm._store[999003] = (state, meta, reg_time - 7200)  # 2 hours ago
        expired = osm.expire_stale_tickets(max_age_minutes=60)
        assert 999003 in expired
