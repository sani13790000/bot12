"""
test_phase22_incident.py -- PHASE 22: Incident Response & Kill-Switch Operations
Covers emergency stop, incident logging, and recovery procedures.
"""
from __future__ import annotations

import pytest
import time
from unittest.mock import patch, MagicMock

try:
    from backend.risk.kill_switch import KillSwitch, KillSwitchState, KillSwitchEvent
    HAS_KILL_SWITCH = True
except ImportError:
    HAS_KILL_SWITCH = False

pytestmark = pytest.mark.skipif(not HAS_KILL_SWITCH, reason="kill_switch module not available")


class TestKillSwitchBasic:
    def test_T001_initial_state(self):
        ks = KillSwitch()
        assert ks.state == KillSwitchState.ACTIVE
        assert not ks.is_triggered

    def test_T002_trigger_sets_state(self):
        ks = KillSwitch()
        ks.trigger("test", "unit test")
        assert ks.state == KillSwitchState.TRIGGERED
        assert ks.is_triggered

    def test_T003_empty_reason_raises(self):
        with pytest.raises(ValueError):
            KillSwitch().trigger("source", "")

    def test_T004_empty_source_raises(self):
        with pytest.raises(ValueError):
            KillSwitch().trigger("", "reason")

    def test_T005_reset_clears_trigger(self):
        ks = KillSwitch()
        ks.trigger("src", "reason")
        ks.reset("admin", "resolved")
        assert not ks.is_triggered
        assert ks.state == KillSwitchState.ACTIVE

    def test_T006_reset_not_triggered_raises(self):
        with pytest.raises(Exception):
            KillSwitch().reset("admin", "resolved")

    def test_T007_reset_empty_reason_raises(self):
        ks = KillSwitch()
        ks.trigger("src", "reason")
        with pytest.raises(ValueError):
            ks.reset("admin", "")


class TestKillSwitchCallbacks:
    def test_T010_callback_fires_on_trigger(self):
        ks = KillSwitch()
        fired = []
        ks.on_trigger(lambda e: fired.append(e.reason))
        ks.trigger("source", "test-reason")
        assert "test-reason" in fired

    def test_T011_multiple_callbacks(self):
        ks = KillSwitch()
        results = []
        ks.on_trigger(lambda e: results.append(1))
        ks.on_trigger(lambda e: results.append(2))
        ks.trigger("src", "reason")
        assert 1 in results and 2 in results

    def test_T012_callback_not_fired_on_reset(self):
        ks = KillSwitch()
        resets = []
        ks.on_trigger(lambda e: resets.append("trigger"))
        ks.trigger("src", "reason")
        resets.clear()
        ks.reset("admin", "ok")
        assert "trigger" not in resets


class TestKillSwitchEvent:
    def test_T020_event_has_source(self):
        ks = KillSwitch()
        events = []
        ks.on_trigger(events.append)
        ks.trigger("risk-engine", "drawdown exceeded")
        assert events[0].source == "risk-engine"

    def test_T021_event_has_reason(self):
        ks = KillSwitch()
        events = []
        ks.on_trigger(events.append)
        ks.trigger("risk-engine", "drawdown exceeded")
        assert "drawdown" in events[0].reason

    def test_T022_event_has_timestamp(self):
        ks = KillSwitch()
        events = []
        ks.on_trigger(events.append)
        ks.trigger("src", "reason")
        assert hasattr(events[0], "timestamp")
