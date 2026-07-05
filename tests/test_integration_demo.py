"""
tests/test_integration_demo.py
Integration-level demo tests (no real MT5 / DB required).

BUG-Q4 FIX: added @pytest.mark.integration markers.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestMT5ConnectorDemo:
    """MT5 connector in DEMO mode."""

    def test_import(self):
        from backend.execution.mt5_connector import MT5Connector
        assert MT5Connector is not None

    def test_demo_connect(self):
        from backend.execution.mt5_connector import MT5Connector
        conn = MT5Connector()
        # In DEMO mode connect() sets _connected = True without real MT5
        assert hasattr(conn, "is_connected")

    def test_get_positions_returns_list(self):
        from backend.execution.mt5_connector import MT5Connector
        import asyncio
        conn = MT5Connector()
        positions = asyncio.get_event_loop().run_until_complete(conn.get_positions())
        assert isinstance(positions, list)


@pytest.mark.integration
class TestSignalProcessorIntegration:
    """Signal processor pipeline integration."""

    def test_import(self):
        from backend.services.signal_processor import SignalProcessor
        assert SignalProcessor is not None

    def test_has_process(self):
        from backend.services.signal_processor import SignalProcessor
        sp = SignalProcessor()
        assert hasattr(sp, "process")

    def test_has_register_engines(self):
        from backend.services.signal_processor import SignalProcessor
        sp = SignalProcessor()
        assert hasattr(sp, "register_engines")

    def test_register_engines_none_safe(self):
        from backend.services.signal_processor import SignalProcessor
        sp = SignalProcessor()
        # Passing None engines should not raise
        try:
            sp.register_engines(
                smc_engine=None,
                ml_engine=None,
                pa_engine=None,
                smc_scoring_engine=None,
            )
        except Exception as exc:
            pytest.fail(f"register_engines raised: {exc}")
