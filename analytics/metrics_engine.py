"""Analytics metrics engine."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TradeRecord:
    """Trade record for analytics."""
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    lots: float
    profit_usd: float
    open_time: float = field(default_factory=time.time)
    close_time: float = field(default_factory=time.time)
    status: str = "closed"


class MetricsEngine:
    """Analytics metrics engine."""

    def __init__(self) -> None:
        self._trades: List[TradeRecord] = []

    def record_trade(self, trade: TradeRecord) -> None:
        self._trades.append(trade)

    def total_pnl(self) -> float:
        return sum(t.profit_usd for t in self._trades)

    def win_rate(self) -> float:
        wins = [t for t in self._trades if t.profit_usd > 0]
        return len(wins) / len(self._trades) if self._trades else 0.0

    def summary(self) -> dict:
        return {
            "total_trades": len(self._trades),
            "total_pnl": self.total_pnl(),
            "win_rate": self.win_rate(),
        }
