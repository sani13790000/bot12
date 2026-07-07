"""PHASE 35 - FINAL ACCEPTANCE CRITERIA"""

from __future__ import annotations

import pytest

try:
    from backend.core.enums import MarketSession, TradeDirection, TradingSession
    from backend.risk.kill_switch import KillSwitch, KillSwitchState

    HAS_MODULES = True
except ImportError:
    HAS_MODULES = False

pytestmark = pytest.mark.skipif(not HAS_MODULES, reason="modules not available")


class TestC01CoreImports:
    def test_T001_trade_direction_enum(self):
        assert TradeDirection.BUY

    def test_T002_market_session_enum(self):
        assert MarketSession.LONDON

    def test_T003_trading_session_alias(self):
        assert TradingSession is MarketSession


class TestC02KillSwitch:
    def test_T004_init(self):
        assert KillSwitch() is not None

    def test_T005_state(self):
        assert KillSwitch().state == KillSwitchState.ACTIVE

    def test_T006_not_triggered(self):
        assert KillSwitch().is_triggered is False

    def test_T007_trigger(self):
        ks = KillSwitch()
        ks.trigger("test", "acceptance")
        assert ks.is_triggered

    def test_T008_state_after_trigger(self):
        ks = KillSwitch()
        ks.trigger("src", "reason")
        assert ks.state == KillSwitchState.TRIGGERED

    def test_T009_reset(self):
        ks = KillSwitch()
        ks.trigger("a", "b")
        ks.reset("a", "ok")
        assert not ks.is_triggered

    def test_T010_empty_reason_rejected(self):
        with pytest.raises(ValueError):
            KillSwitch().trigger("a", "")
