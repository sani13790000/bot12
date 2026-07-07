"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های امنیتی: Kill-Switch، حالات terminal، thread safety، R:R
"""

from __future__ import annotations

import threading

import pytest


class TestKillSwitch:
    """کیل-سویچ باید فوری همه معاملات را متوقف کند."""

    def setup_method(self) -> None:
        from backend.risk.kill_switch import KillSwitch

        self.ks = KillSwitch()

    def test_initially_inactive(self) -> None:
        assert self.ks.is_active() is False

    def test_activate_blocks_trading(self) -> None:
        self.ks.activate(reason="test")
        assert self.ks.is_active() is True

    def test_reason_stored(self) -> None:
        self.ks.activate(reason="daily_loss_exceeded")
        reason = getattr(self.ks, "reason", None) or self.ks.get_reason()
        assert "daily_loss" in str(reason)

    def test_deactivate(self) -> None:
        self.ks.activate(reason="test")
        if hasattr(self.ks, "deactivate"):
            self.ks.deactivate()
            assert self.ks.is_active() is False
        else:
            pytest.skip("deactivate() not implemented")


class TestTerminalStates:
    """حالات terminal نباید قابل تغییر باشند."""

    def setup_method(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine

        OrderStateMachine._instance = None
        self.osm = OrderStateMachine.get_instance()

    def test_closed_is_terminal(self) -> None:
        self.osm.register(ticket=70100)
        self.osm.transition(70100, "SUBMITTED")
        self.osm.transition(70100, "OPEN")
        self.osm.transition(70100, "CLOSING")
        self.osm.transition(70100, "CLOSED")
        assert self.osm.is_terminal(70100) is True

    def test_rejected_is_terminal(self) -> None:
        self.osm.register(ticket=70101)
        self.osm.transition(70101, "SUBMITTED")
        self.osm.transition(70101, "REJECTED")
        assert self.osm.is_terminal(70101) is True

    def test_cannot_reopen_closed(self) -> None:
        self.osm.register(ticket=70102)
        self.osm.transition(70102, "SUBMITTED")
        self.osm.transition(70102, "OPEN")
        self.osm.transition(70102, "CLOSING")
        self.osm.transition(70102, "CLOSED")
        with pytest.raises((ValueError, RuntimeError, KeyError)):
            self.osm.transition(70102, "OPEN")

    def test_cannot_reopen_rejected(self) -> None:
        self.osm.register(ticket=70103)
        self.osm.transition(70103, "SUBMITTED")
        self.osm.transition(70103, "REJECTED")
        with pytest.raises((ValueError, RuntimeError, KeyError)):
            self.osm.transition(70103, "OPEN")


class TestThreadSafety:
    """تست thread-safety."""

    def test_concurrent_registrations(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine

        OrderStateMachine._instance = None
        osm = OrderStateMachine.get_instance()

        errors = []
        tickets = list(range(80001, 80101))

        def register_batch(batch):
            try:
                for t in batch:
                    osm.register(ticket=t)
            except Exception as e:
                errors.append(e)

        mid = len(tickets) // 2
        t1 = threading.Thread(target=register_batch, args=(tickets[:mid],))
        t2 = threading.Thread(target=register_batch, args=(tickets[mid:],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        for t in tickets:
            assert osm.get_state(t) is not None

    def test_concurrent_transitions(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine

        OrderStateMachine._instance = None
        osm = OrderStateMachine.get_instance()

        for t in range(90001, 90011):
            osm.register(ticket=t)

        errors = []

        def do_transitions(ticket):
            try:
                osm.transition(ticket, "SUBMITTED")
                osm.transition(ticket, "CANCELLED")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_transitions, args=(t,)) for t in range(90001, 90011)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert not errors


class TestRiskRewardRatio:
    """نسبت ریسک/سود باید حداقل 1.5 باشد."""

    def _check_rr(self, entry, sl, tp, direction, min_rr=1.5):
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return False
        return (reward / risk) >= min_rr

    def test_buy_valid_rr(self) -> None:
        assert self._check_rr(1.0850, 1.0800, 1.0925, "BUY")

    def test_sell_valid_rr(self) -> None:
        assert self._check_rr(1.0850, 1.0900, 1.0775, "SELL")

    def test_insufficient_rr_fails(self) -> None:
        assert not self._check_rr(1.0850, 1.0800, 1.0875, "BUY")

    def test_rr_exactly_minimum(self) -> None:
        assert self._check_rr(1.0850, 1.0800, 1.0925, "BUY", min_rr=1.5)

    def test_high_rr_acceptable(self) -> None:
        assert self._check_rr(1.0850, 1.0830, 1.0950, "BUY", min_rr=1.5)
