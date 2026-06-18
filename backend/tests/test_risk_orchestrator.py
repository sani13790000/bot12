"""
تست‌های RiskOrchestrator
"""
from __future__ import annotations
import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Stub RiskAssessment ────────────────────────────────────────────────────────────────
@dataclass
class RiskAssessment:
    approved: bool
    lot_size: float
    risk_usd: float
    risk_pct: float
    reason: str
    equity_gate: bool = True
    daily_gate: bool = True
    volatility_ok: bool = True
    correlation_ok: bool = True
    exposure_pct: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Minimal RiskOrchestrator stub ──────────────────────────────────────────────────
class RiskOrchestrator:

    def __init__(self):
        self._sizing_lock = asyncio.Lock()
        self._max_daily_loss_pct = 0.05
        self._max_equity_drawdown_pct = 0.10
        self._min_lot = 0.01
        self._max_lot = 5.0

    async def assess(self, signal, market_data) -> RiskAssessment:
        """Gate 1: equity check."""
        equity = market_data.get("equity", 10000.0)
        balance = market_data.get("balance", 10000.0)
        try:
            dd_pct = (balance - equity) / balance if balance > 0 else 0.0
            if dd_pct >= self._max_equity_drawdown_pct:
                return RiskAssessment(
                    approved=False, lot_size=0.0, risk_usd=0.0,
                    risk_pct=0.0, reason="Equity drawdown limit",
                    equity_gate=False,
                )
        except Exception as exc:
            return RiskAssessment(
                approved=False, lot_size=0.0, risk_usd=0.0,
                risk_pct=0.0, reason=f"Gate1 error: {exc}",
                equity_gate=False,
            )

        # Gate 2: daily loss
        try:
            daily_loss = market_data.get("daily_loss_pct", 0.0)
            if daily_loss >= self._max_daily_loss_pct:
                return RiskAssessment(
                    approved=False, lot_size=0.0, risk_usd=0.0,
                    risk_pct=0.0, reason="Daily loss limit",
                    daily_gate=False,
                )
        except Exception:
            pass

        # Gate 5: lot sizing with async lock
        async with self._sizing_lock:
            sl_pips = signal.get("sl_pips", 20.0)
            risk_pct = signal.get("risk_pct", 0.01)
            risk_usd = equity * risk_pct
            pip_value = 10.0  # XAUUSD
            lot = risk_usd / (sl_pips * pip_value) if sl_pips > 0 else self._min_lot
            lot = max(self._min_lot, min(self._max_lot, round(lot, 2)))

        return RiskAssessment(
            approved=True, lot_size=lot, risk_usd=risk_usd,
            risk_pct=risk_pct, reason="All gates passed",
        )


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestRiskOrchestratorGates:

    @pytest.mark.asyncio
    async def test_approved_normal_conditions(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.01}
        market = {"equity": 10000.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        result = await orch.assess(signal, market)
        assert result.approved is True
        assert result.lot_size > 0
        assert result.reason == "All gates passed"

    @pytest.mark.asyncio
    async def test_equity_gate_blocks_on_drawdown(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.01}
        # equity 15% زیر balance → drawdown 15% > 10%
        market = {"equity": 8500.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        result = await orch.assess(signal, market)
        assert result.approved is False
        assert result.equity_gate is False
        assert result.lot_size == 0.0

    @pytest.mark.asyncio
    async def test_daily_loss_gate_blocks(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.01}
        market = {"equity": 9900.0, "balance": 10000.0, "daily_loss_pct": 0.06}
        result = await orch.assess(signal, market)
        assert result.approved is False
        assert result.daily_gate is False

    @pytest.mark.asyncio
    async def test_lot_size_within_bounds(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.01}
        market = {"equity": 10000.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        result = await orch.assess(signal, market)
        assert orch._min_lot <= result.lot_size <= orch._max_lot

    @pytest.mark.asyncio
    async def test_lot_size_zero_sl_uses_min(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 0.0, "risk_pct": 0.01}
        market = {"equity": 10000.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        result = await orch.assess(signal, market)
        assert result.lot_size >= orch._min_lot

    @pytest.mark.asyncio
    async def test_concurrent_assess_no_race(self):
        """چند درخواست همزمان بدون race condition."""
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.01}
        market = {"equity": 10000.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        tasks = [orch.assess(signal, market) for _ in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(r.approved for r in results)
        lot_sizes = [r.lot_size for r in results]
        assert len(set(lot_sizes)) == 1  # همه یکسان

    @pytest.mark.asyncio
    async def test_risk_usd_correct(self):
        orch = RiskOrchestrator()
        signal = {"sl_pips": 20.0, "risk_pct": 0.02}
        market = {"equity": 10000.0, "balance": 10000.0, "daily_loss_pct": 0.0}
        result = await orch.assess(signal, market)
        assert abs(result.risk_usd - 200.0) < 1.0  # 10000 * 0.02


class TestRiskAssessment:

    def test_approved_fields(self):
        r = RiskAssessment(
            approved=True, lot_size=0.1, risk_usd=100.0,
            risk_pct=0.01, reason="ok"
        )
        assert r.approved is True
        assert r.equity_gate is True
        assert r.daily_gate is True

    def test_denied_fields(self):
        r = RiskAssessment(
            approved=False, lot_size=0.0, risk_usd=0.0,
            risk_pct=0.0, reason="dd limit", equity_gate=False
        )
        assert r.approved is False
        assert r.equity_gate is False
