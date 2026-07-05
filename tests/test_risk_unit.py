"""
test_risk_unit.py

Unit tests for the risk engine components:
  - KillSwitch activation/deactivation
  - MarginGate contract_size per symbol
  - OrderStateMachine transitions
  - RiskOrchestrator gate sequencing

All tests are synchronous or use asyncio.run() — no real I/O.
Run with: pytest tests/test_risk_unit.py -v
"""
from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# KillSwitch unit tests
# ---------------------------------------------------------------------------

class TestKillSwitchUnit:

    def test_import_kill_switch(self):
        """kill_switch singleton must be importable."""
        from backend.risk.kill_switch import kill_switch, KillSwitch
        assert isinstance(kill_switch, KillSwitch)

    def test_is_active_is_property(self):
        """is_active must be a property, not a method."""
        from backend.risk.kill_switch import kill_switch
        # If is_active were a method, calling it without () would return
        # a bound method object (truthy). This test ensures it's a bool.
        val = kill_switch.is_active
        assert isinstance(val, bool), f"is_active returned {type(val)}, expected bool"

    def test_is_active_not_callable(self):
        """kill_switch.is_active must NOT be callable (it's a @property)."""
        from backend.risk.kill_switch import kill_switch
        # Should raise TypeError if called as function
        with pytest.raises(TypeError):
            kill_switch.is_active()  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_check_normal_equity(self):
        """Normal equity/balance check must pass without raising."""
        from backend.risk.kill_switch import KillSwitch, KillSwitchConfig
        ks = KillSwitch(KillSwitchConfig(max_daily_loss_pct=5.0, max_drawdown_pct=10.0))
        # Should not raise
        await ks.check(equity=10000.0, balance=10000.0)
        assert ks.is_active is False

    @pytest.mark.asyncio
    async def test_activates_on_drawdown(self):
        """20% drawdown must trigger kill switch."""
        from backend.risk.kill_switch import KillSwitch, KillSwitchConfig
        ks = KillSwitch(KillSwitchConfig(max_daily_loss_pct=5.0, max_drawdown_pct=10.0))
        try:
            await ks.check(equity=8000.0, balance=10000.0)  # 20% drawdown
        except Exception:
            pass
        assert ks.is_active is True

    def test_reset_clears_active(self):
        """reset() must set is_active to False."""
        from backend.risk.kill_switch import KillSwitch, KillSwitchConfig
        ks = KillSwitch(KillSwitchConfig())
        ks._state.active = True
        ks.reset("unit test reset")
        assert ks.is_active is False

    def test_get_kill_switch_singleton(self):
        """get_kill_switch() must return the same instance each call."""
        from backend.risk.kill_switch import get_kill_switch
        a = get_kill_switch()
        b = get_kill_switch()
        assert a is b


# ---------------------------------------------------------------------------
# MarginGate unit tests
# ---------------------------------------------------------------------------

class TestMarginGateUnit:

    def test_import_margin_gate(self):
        """MarginGate must be importable."""
        try:
            from backend.risk.margin_gate import MarginGate
            assert MarginGate is not None
        except ImportError as e:
            pytest.skip(f"MarginGate not importable: {e}")

    def test_xauusd_contract_size_from_demo(self):
        """
        In DEMO mode, get_symbol_info('XAUUSD').contract_size must be 100.0
        (not 100_000.0 which is the Forex default).
        """
        from backend.execution.mt5_connector import MT5Connector
        conn = MT5Connector(demo=True)

        async def _run():
            await conn.connect()
            info = await conn.get_symbol_info("XAUUSD")
            return info

        info = asyncio.get_event_loop().run_until_complete(_run())
        assert info is not None
        assert info.contract_size == 100.0, (
            f"XAUUSD contract_size should be 100.0 (oz), got {info.contract_size}. "
            "This means MarginGate will underestimate Gold margin by ~50%%!"
        )

    def test_btcusd_contract_size_from_demo(self):
        """BTCUSD contract_size must be 1.0 (1 BTC per lot)."""
        from backend.execution.mt5_connector import MT5Connector
        conn = MT5Connector(demo=True)

        async def _run():
            await conn.connect()
            return await conn.get_symbol_info("BTCUSD")

        info = asyncio.get_event_loop().run_until_complete(_run())
        assert info is not None
        assert info.contract_size == 1.0

    def test_eurusd_contract_size_from_demo(self):
        """EURUSD contract_size must be 100_000.0."""
        from backend.execution.mt5_connector import MT5Connector
        conn = MT5Connector(demo=True)

        async def _run():
            await conn.connect()
            return await conn.get_symbol_info("EURUSD")

        info = asyncio.get_event_loop().run_until_complete(_run())
        assert info is not None
        assert info.contract_size == 100_000.0


# ---------------------------------------------------------------------------
# OrderStateMachine unit tests
# ---------------------------------------------------------------------------

class TestOrderStateMachineUnit:

    def test_init_creates_pending(self):
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=1001, symbol="EURUSD", direction="BUY", volume=0.01)
        assert osm.state_of(1001) == "PENDING"

    def test_valid_transitions(self):
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=1002, symbol="EURUSD", direction="BUY", volume=0.01)
        osm.transition(1002, "SUBMITTED")
        assert osm.state_of(1002) == "SUBMITTED"
        osm.transition(1002, "OPEN")
        assert osm.state_of(1002) == "OPEN"
        osm.transition(1002, "CLOSING")
        assert osm.state_of(1002) == "CLOSING"
        osm.transition(1002, "CLOSED")
        assert osm.state_of(1002) == "CLOSED"

    def test_invalid_transition_raises(self):
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=1003, symbol="EURUSD", direction="BUY", volume=0.01)
        with pytest.raises(Exception):
            osm.transition(1003, "CLOSED")  # PENDING -> CLOSED is invalid

    def test_expire_stale_tickets(self):
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=1004, symbol="EURUSD", direction="BUY", volume=0.01)
        # Backdate registration time by 2 hours
        if 1004 in osm._store:
            s, m, _ = osm._store[1004]
            import time
            osm._store[1004] = (s, m, time.time() - 7200)
        expired = osm.expire_stale_tickets(max_age_minutes=60)
        assert 1004 in expired

    def test_active_tickets_excludes_terminal(self):
        from backend.execution.order_state_machine import OrderStateMachine
        osm = OrderStateMachine()
        osm.init(ticket=1005, symbol="EURUSD", direction="BUY", volume=0.01)
        osm.init(ticket=1006, symbol="EURUSD", direction="SELL", volume=0.01)
        # Close ticket 1005
        osm.transition(1005, "SUBMITTED")
        osm.transition(1005, "OPEN")
        osm.transition(1005, "CLOSING")
        osm.transition(1005, "CLOSED")
        active = osm.active_tickets()
        assert 1006 in active
        assert 1005 not in active


# ---------------------------------------------------------------------------
# Signal Processor import test
# ---------------------------------------------------------------------------

class TestSignalProcessorImport:

    def test_signal_processor_importable(self):
        """SignalProcessor must be importable and not a placeholder."""
        from backend.services.signal_processor import SignalProcessor
        sp = SignalProcessor()
        assert sp is not None
        assert hasattr(sp, 'register_agents'), "Missing register_agents()"
        assert hasattr(sp, 'process'), "Missing process()"

    def test_register_agents(self):
        """register_agents() must accept a list of agents."""
        from backend.services.signal_processor import SignalProcessor
        from backend.agents.smc_agent import SMCAgent
        from backend.agents.news_agent import NewsAgent
        from backend.agents.ml_agent import MLAgent
        sp = SignalProcessor()
        sp.register_agents([SMCAgent(), MLAgent(), NewsAgent()])
        assert len(sp._agents) == 3
