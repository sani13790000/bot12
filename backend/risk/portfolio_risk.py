"""portfolio_risk.py -- Phase P Fix P-9a/b/c/d."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from ..core.config import settings
from ..core.logger import get_logger
from .correlation_filter import RollingCorrelationEngine

logger = get_logger("risk.portfolio")

# FIX P-9b: static fallback when rolling data insufficient
_STATIC_CORRELATIONS: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"):  0.85, ("EURUSD", "AUDUSD"):  0.72,
    ("EURUSD", "NZDUSD"):  0.68, ("GBPUSD", "AUDUSD"):  0.70,
    ("USDCHF", "EURUSD"): -0.92, ("USDCHF", "GBPUSD"): -0.88,
    ("XAUUSD", "EURUSD"):  0.45, ("XAUUSD", "USDCHF"): -0.55,
    ("USDJPY", "XAUUSD"): -0.40,
}

class RiskLevel(str, Enum):
    SAFE     = "SAFE"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"
    BLOCKED  = "BLOCKED"

class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"

@dataclass
class OpenTradeRisk:
    symbol: str
    direction: TradeDirection
    lot_size: float
    entry_price: float
    stop_loss: float
    account_balance: float
    risk_percent: float = field(init=False)
    risk_amount: float  = field(init=False)
    base_currency: str  = field(init=False)

    def __post_init__(self) -> None:
        pip_distance = abs(self.entry_price - self.stop_loss)
        self.risk_amount = pip_distance * self.lot_size * 100_000 * 0.0001
        self.risk_percent = (
            (self.risk_amount / self.account_balance * 100)
            if self.account_balance > 0 else 0.0
        )
        self.base_currency = self.symbol[:3] if len(self.symbol) >= 3 else self.symbol

@dataclass
class PortfolioRiskSnapshot:
    total_risk_percent: float
    risk_level: RiskLevel
    correlated_risk: float
    open_trades: int
    can_add_new: bool
    block_reason: str
    correlation_source: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PortfolioRiskManager:
    MAX_TOTAL_RISK_PCT    = 5.0
    WARNING_RISK_PCT      = 3.0
    CRITICAL_RISK_PCT     = 4.0

    def __init__(self) -> None:
        self._corr_engine = RollingCorrelationEngine(window=50, cache_ttl=60)
        self._lock = asyncio.Lock()

    def add_price_tick(self, symbol: str, price: float) -> None:
        """FIX P-9d: push new price into rolling engine."""
        self._corr_engine.add_price(symbol, price)

    def _get_correlation(self, sym_a: str, sym_b: str) -> Tuple[float, str]:
        """FIX P-9a/b: rolling first, static fallback."""
        rolling = self._corr_engine.get_correlation(sym_a, sym_b)
        if rolling is not None:
            return rolling, "rolling"
        key, rev = (sym_a, sym_b), (sym_b, sym_a)
        if key in _STATIC_CORRELATIONS:
            return _STATIC_CORRELATIONS[key], "static"
        if rev in _STATIC_CORRELATIONS:
            return _STATIC_CORRELATIONS[rev], "static"
        return 0.0, "unknown"

    def check(
        self,
        new_trade: OpenTradeRisk,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioRiskSnapshot:
        all_trades = open_trades + [new_trade]
        base_risk = sum(t.risk_percent for t in all_trades)
        corr_risk = 0.0
        corr_source = "none"
        seen: set = set()
        for i, t1 in enumerate(all_trades):
            for t2 in all_trades[i + 1:]:
                pair = tuple(sorted([t1.symbol, t2.symbol]))
                if pair in seen:
                    continue
                seen.add(pair)
                corr, src = self._get_correlation(t1.symbol, t2.symbol)
                if corr_source == "none":
                    corr_source = src
                if abs(corr) >= 0.6:
                    direction_match = (t1.direction == t2.direction)
                    sign = 1 if direction_match else -1
                    extra = abs(corr) * min(t1.risk_percent, t2.risk_percent) * sign
                    corr_risk += extra
        total = base_risk + max(0.0, corr_risk)
        if total >= self.MAX_TOTAL_RISK_PCT:
            level, can_add = RiskLevel.BLOCKED, False
            block_reason = f"total_risk {total:.2f}% >= {self.MAX_TOTAL_RISK_PCT}%"
        elif total >= self.CRITICAL_RISK_PCT:
            level, can_add = RiskLevel.CRITICAL, False
            block_reason = f"total_risk {total:.2f}% >= {self.CRITICAL_RISK_PCT}%"
        elif total >= self.WARNING_RISK_PCT:
            level, can_add = RiskLevel.WARNING, True
            block_reason = ""
        else:
            level, can_add = RiskLevel.SAFE, True
            block_reason = ""
        return PortfolioRiskSnapshot(
            total_risk_percent=round(total, 4),
            risk_level=level,
            correlated_risk=round(corr_risk, 4),
            open_trades=len(all_trades),
            can_add_new=can_add,
            block_reason=block_reason,
            correlation_source=corr_source,
        )
