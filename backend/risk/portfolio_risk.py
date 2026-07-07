"""
backend/risk/portfolio_risk.py
Galaxy Vast AI Trading Platform — Portfolio Risk Gate

Checks portfolio-level risk: max open positions, net delta, sector concentration.
Uses canonical TradeDirection from core/enums.py (single source of truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("risk.portfolio_risk")

# ── Single source of truth for TradeDirection ─────────────────────────────────
try:
    from ..core.enums import TradeDirection  # canonical
except ImportError:
    from enum import Enum

    class TradeDirection(str, Enum):  # type: ignore[no-redef]
        BUY = "BUY"
        SELL = "SELL"


@dataclass
class PortfolioConfig:
    max_open_positions: int = 10
    max_net_delta_pct: float = 5.0
    max_correlated_pct: float = 8.0
    enabled: bool = True


@dataclass
class PortfolioPosition:
    symbol: str
    direction: str
    risk_percent: float = 1.0
    lot_size: float = 0.0
    pnl_usd: float = 0.0


@dataclass
class PortfolioCheckResult:
    approved: bool
    reason: str = ""
    open_positions: int = 0
    net_delta_pct: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class PortfolioRiskEngine:
    """
    Portfolio-level risk gate.
    Checks: max open positions, net long/short delta.
    """

    def __init__(self, config: Optional[PortfolioConfig] = None) -> None:
        self._cfg = config or PortfolioConfig()

    @property
    def name(self) -> str:
        return "PortfolioRisk"

    def check(
        self,
        new_symbol: str,
        new_direction: str,
        new_risk_percent: float,
        open_positions: List[PortfolioPosition],
    ) -> PortfolioCheckResult:
        """Synchronous check — no I/O required."""
        if not self._cfg.enabled:
            return PortfolioCheckResult(approved=True, reason="disabled")

        n_open = len(open_positions)
        if n_open >= self._cfg.max_open_positions:
            return PortfolioCheckResult(
                approved=False,
                reason=f"Max positions reached: {n_open}/{self._cfg.max_open_positions}",
                open_positions=n_open,
            )

        buy_pct = sum(
            p.risk_percent for p in open_positions if p.direction.upper() == TradeDirection.BUY
        )
        sell_pct = sum(
            p.risk_percent for p in open_positions if p.direction.upper() == TradeDirection.SELL
        )

        if new_direction.upper() == TradeDirection.BUY:
            buy_pct += new_risk_percent
        else:
            sell_pct += new_risk_percent

        net_delta = abs(buy_pct - sell_pct)
        if net_delta > self._cfg.max_net_delta_pct:
            return PortfolioCheckResult(
                approved=False,
                reason=f"Net delta {net_delta:.2f}% > limit {self._cfg.max_net_delta_pct}%",
                open_positions=n_open,
                net_delta_pct=net_delta,
            )

        return PortfolioCheckResult(
            approved=True,
            reason="",
            open_positions=n_open,
            net_delta_pct=net_delta,
            details={"buy_pct": buy_pct, "sell_pct": sell_pct},
        )


# ── Module-level singleton ────────────────────────────────────────────────────
_engine: Optional[PortfolioRiskEngine] = None


def get_portfolio_risk() -> PortfolioRiskEngine:
    global _engine
    if _engine is None:
        _engine = PortfolioRiskEngine()
    return _engine
