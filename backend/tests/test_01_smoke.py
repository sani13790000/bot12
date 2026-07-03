"""
Galaxy Vast AI Trading Platform
test_01_smoke.py -- بررسی import همه ماژول‌های کلیدی
"""
from __future__ import annotations
import pytest


class TestCoreImports:
    """همه import‌های اصلی باید بدون خطا کار کنند."""

    def test_enums_import(self) -> None:
        from backend.core.enums import Direction, OrderStatus, SignalStrength
        assert Direction.BUY.value == "BUY"

    def test_order_state_machine_import(self) -> None:
        from backend.execution.order_state_machine import (
            OrderStateMachine, OrderState, OrderEvent,
        )
        assert OrderStateMachine is not None

    def test_mt5_connector_import(self) -> None:
        from backend.execution.mt5_connector import MT5Connector, MT5Error
        assert MT5Connector is not None

    def test_execution_service_import(self) -> None:
        from backend.execution.execution_service import ExecutionService
        assert ExecutionService is not None

    def test_smc_engine_import(self) -> None:
        from backend.analysis.smc_engine import SMCEngine, Candle, SMCAnalysis
        assert SMCEngine is not None

    def test_decision_engine_import(self) -> None:
        from backend.analysis.decision_engine import (
            DecisionEngine, EngineVote, TradeDirection, DecisionReason,
        )
        assert DecisionEngine is not None

    def test_kill_switch_import(self) -> None:
        from backend.risk.kill_switch import KillSwitch
        assert KillSwitch is not None

    def test_position_reconciliation_import(self) -> None:
        from backend.execution.position_reconciliation import (
            PositionReconciliation, MismatchType,
        )
        assert MismatchType.GHOST is not None

    def test_license_engine_import(self) -> None:
        from backend.license.engine import LicenseEngine
        assert LicenseEngine is not None

    def test_voting_engine_import(self) -> None:
        from backend.agents.voting_engine import VotingEngine
        assert VotingEngine is not None
