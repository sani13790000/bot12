"""
test_06_e2e.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های End-to-End کامل:
pipeline: Candles → SMC → Decision → VotingEngine → ExecutionService → DB → Result

این تست‌ها بدون MT5 واقعی و بدون Supabase اجرا می‌شوند.
"""

from __future__ import annotations

import pytest


class TestCandlesToSMCVote:
    """SMCEngine با کندل‌های مصنوعی."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from backend.analysis.smc_engine import Candle, SMCEngine

        self.engine = SMCEngine()
        self.candles = [
            Candle(
                time=1_700_000_000 + i * 3600,
                open=1.1000 + i * 0.0002,
                high=1.1015 + i * 0.0002,
                low=1.0990 + i * 0.0002,
                close=1.1010 + i * 0.0002,
                tick_volume=600 + i,
            )
            for i in range(200)
        ]

    def test_smc_analysis_complete(self) -> None:
        result = self.engine.analyse(self.candles)
        assert result is not None
        assert hasattr(result, "bias")
        assert hasattr(result, "confidence")
        assert hasattr(result, "order_blocks")
        assert hasattr(result, "fair_value_gaps")

    def test_smc_to_engine_vote(self) -> None:
        from backend.analysis.decision_engine import EngineVote, TradeDirection

        result = self.engine.analyse(self.candles)
        vote = EngineVote(
            engine_name="SMC",
            direction=TradeDirection.BUY if result.bias == "bullish" else TradeDirection.SELL,
            confidence=result.confidence,
            entry_price=self.candles[-1].close,
            sl_price=self.candles[-1].close - 0.0050,
            tp_price=self.candles[-1].close + 0.0100,
        )
        assert vote.engine_name == "SMC"
        assert vote.confidence >= 0.0


class TestVotesToDecision:
    """EngineVotes → DecisionEngine."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection

        self.de = DecisionEngine(min_confidence=0.65, min_votes=2, min_rr=1.5)
        self.EngineVote = EngineVote
        self.TradeDirection = TradeDirection

    def test_three_engine_consensus_buy(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.82, 1.1050, 1.1000, 1.1150),
            self.EngineVote("PA", self.TradeDirection.BUY, 0.78, 1.1052, 1.1002, 1.1152),
            self.EngineVote("XGB", self.TradeDirection.BUY, 0.85, 1.1048, 1.0998, 1.1148),
        ]
        decision = self.de.decide(votes, "EURUSD", "H1")
        assert decision.should_trade
        assert decision.direction == self.TradeDirection.BUY
        assert decision.confidence >= 0.65

    def test_two_engine_consensus_sell(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.SELL, 0.80, 1.1050, 1.1100, 1.0950),
            self.EngineVote("PA", self.TradeDirection.SELL, 0.75, 1.1050, 1.1100, 1.0950),
            self.EngineVote("XGB", self.TradeDirection.BUY, 0.55),
        ]
        decision = self.de.decide(votes, "EURUSD", "H1")
        assert decision.should_trade
        assert decision.direction == self.TradeDirection.SELL

    def test_no_trade_kill_switch(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.90, 1.1050, 1.1000, 1.1200),
            self.EngineVote("PA", self.TradeDirection.BUY, 0.88, 1.1050, 1.1000, 1.1200),
        ]
        decision = self.de.decide(votes, "EURUSD", "H1", kill_switch_active=True)
        assert not decision.should_trade

    def test_decision_to_dict_complete(self) -> None:
        votes = [
            self.EngineVote("SMC", self.TradeDirection.BUY, 0.82, 1.1050, 1.1000, 1.1150),
            self.EngineVote("PA", self.TradeDirection.BUY, 0.78, 1.1050, 1.1000, 1.1150),
        ]
        d = self.de.decide(votes, "EURUSD", "H1").to_dict()
        for key in [
            "direction",
            "confidence",
            "should_trade",
            "entry_price",
            "sl_price",
            "tp_price",
            "votes",
        ]:
            assert key in d, f"'{key}' در to_dict() نیست"


class TestDecisionToExecution:
    """TradeDecision → ExecutionService → نتیجه."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_broker, mock_db):
        self.broker = mock_broker
        self.db = mock_db

    @pytest.mark.asyncio
    async def test_full_e2e_buy_pipeline(self) -> None:
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        from backend.analysis.smc_engine import Candle, SMCEngine
        from backend.execution.execution_service import ExecutionService, TradeSignal

        candles = [
            Candle(
                time=1_700_000_000 + i * 3600,
                open=1.1000 + i * 0.0002,
                high=1.1015 + i * 0.0002,
                low=1.0990 + i * 0.0002,
                close=1.1010 + i * 0.0002,
                tick_volume=600 + i,
            )
            for i in range(200)
        ]

        smc = SMCEngine()
        analysis = smc.analyse(candles)
        assert analysis is not None

        de = DecisionEngine(min_confidence=0.60, min_votes=2, min_rr=1.0)
        votes = [
            EngineVote("SMC", TradeDirection.BUY, 0.82, 1.1050, 1.1000, 1.1150),
            EngineVote("PA", TradeDirection.BUY, 0.78, 1.1050, 1.1000, 1.1150),
        ]
        decision = de.decide(votes, "EURUSD", "H1")
        assert decision.should_trade

        svc = ExecutionService(connector=self.broker, db=self.db)
        sig = TradeSignal(
            symbol=decision.symbol,
            direction=decision.direction.value.lower(),
            volume=0.10,
            sl=decision.sl_price,
            tp=decision.tp_price,
            confidence=decision.confidence,
            source="e2e_test",
        )
        result = await svc.execute(sig)
        assert result.success
        assert result.ticket > 0
        self.broker.place_order.assert_called_once()
        self.db.insert.assert_called()

    @pytest.mark.asyncio
    async def test_full_e2e_sell_pipeline(self) -> None:
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        from backend.execution.execution_service import ExecutionService, TradeSignal

        de = DecisionEngine(min_confidence=0.60, min_votes=2, min_rr=1.0)
        votes = [
            EngineVote("SMC", TradeDirection.SELL, 0.80, 1.1050, 1.1100, 1.0950),
            EngineVote("PA", TradeDirection.SELL, 0.75, 1.1050, 1.1100, 1.0950),
        ]
        decision = de.decide(votes, "GBPUSD", "H4")
        assert decision.should_trade

        svc = ExecutionService(connector=self.broker, db=self.db)
        sig = TradeSignal(
            symbol="GBPUSD",
            direction="sell",
            volume=0.05,
            sl=decision.sl_price,
            tp=decision.tp_price,
            confidence=decision.confidence,
            source="e2e_test",
        )
        result = await svc.execute(sig)
        assert result.success

    @pytest.mark.asyncio
    async def test_e2e_open_then_close(self) -> None:
        from backend.execution.execution_service import ExecutionService, TradeSignal

        svc = ExecutionService(connector=self.broker, db=self.db)
        sig = TradeSignal(
            symbol="EURUSD",
            direction="buy",
            volume=0.10,
            sl=1.1000,
            tp=1.1150,
            confidence=0.80,
            source="e2e_test",
        )
        open_result = await svc.execute(sig)
        assert open_result.success
        ticket = open_result.ticket
        close_result = await svc.close(ticket)
        assert close_result.success
        self.broker.close_position.assert_called_with(ticket)


class TestKillSwitchInPipeline:
    @pytest.mark.asyncio
    async def test_kill_switch_blocks_execution(self) -> None:
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        from backend.risk.kill_switch import KillSwitch

        ks = KillSwitch()
        ks.activate("test: E2E")
        assert ks.is_active

        de = DecisionEngine()
        votes = [
            EngineVote("SMC", TradeDirection.BUY, 0.90, 1.1050, 1.1000, 1.1200),
            EngineVote("PA", TradeDirection.BUY, 0.88, 1.1050, 1.1000, 1.1200),
        ]
        decision = de.decide(votes, "EURUSD", "H1", kill_switch_active=ks.is_active)
        assert not decision.should_trade
        ks.deactivate()
        assert not ks.is_active


class TestOSMInPipeline:
    def test_full_trade_lifecycle(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine

        osm = OrderStateMachine()
        ticket = 55001
        osm.register(ticket)
        assert osm.get_state(ticket) == "PENDING"
        osm.transition(ticket, "OPEN")
        assert osm.get_state(ticket) == "OPEN"
        assert not osm.is_terminal(ticket)
        osm.transition(ticket, "CLOSED")
        assert osm.get_state(ticket) == "CLOSED"
        assert osm.is_terminal(ticket)

    def test_rejected_trade_lifecycle(self) -> None:
        from backend.execution.order_state_machine import OrderStateMachine

        osm = OrderStateMachine()
        osm.register(55002)
        osm.transition(55002, "REJECTED")
        assert osm.is_terminal(55002)
        with pytest.raises(Exception):
            osm.transition(55002, "OPEN")

    def test_concurrent_tickets(self) -> None:
        import threading

        from backend.execution.order_state_machine import OrderStateMachine

        osm = OrderStateMachine()
        errors = []

        def worker(ticket: int) -> None:
            try:
                osm.register(ticket)
                osm.transition(ticket, "OPEN")
                osm.transition(ticket, "CLOSED")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(66000 + i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"خطاهای concurrent: {errors}"
