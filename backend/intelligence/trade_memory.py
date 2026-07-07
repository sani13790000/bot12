"""
backend/intelligence/trade_memory.py
Galaxy Vast AI Trading Platform — Trade Memory and ML Feedback Loop

Stores completed trade context for self-learning pipeline.
Uses single source-of-truth SMCContext/RiskContext from decision_engine.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("intelligence.trade_memory")

# ── Import canonical context classes (single source of truth) ────────────────
try:
    from ..analysis.decision_engine import RiskContext, SMCContext  # type: ignore[attr-defined]
except ImportError:

    @dataclass
    class SMCContext:  # type: ignore[no-redef]
        trend: Any = "ranging"
        trend_score: float = 0.0
        structure_event: Optional[str] = None
        structure_direction: Optional[str] = None
        structure_level: Optional[float] = None
        liquidity_swept: bool = False
        order_blocks: List[Any] = field(default_factory=list)
        fvgs: List[Any] = field(default_factory=list)
        swing_high: Optional[float] = None
        swing_low: Optional[float] = None

    @dataclass
    class RiskContext:  # type: ignore[no-redef]
        equity: float = 0.0
        balance: float = 0.0
        drawdown_pct: float = 0.0
        daily_pnl_usd: float = 0.0


@dataclass
class PAContext:
    """Price Action context — defined only here."""

    pattern: Optional[str] = None
    confidence: float = 0.0
    direction: Optional[str] = None
    levels: List[float] = field(default_factory=list)


@dataclass
class TradeContext:
    """Complete context snapshot for a single trade — stored for ML training."""

    signal_id: str
    symbol: str
    direction: str
    timestamp: float = field(default_factory=time.time)
    smc: Optional[Any] = None
    risk: Optional[Any] = None
    pa: Optional[Any] = None
    outcome: Optional[str] = None  # "WIN" | "LOSS" | "BREAKEVEN"
    pnl_usd: float = 0.0
    pnl_pips: float = 0.0
    lot_size: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    duration_s: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "outcome": self.outcome,
            "pnl_usd": self.pnl_usd,
            "pnl_pips": self.pnl_pips,
            "lot_size": self.lot_size,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "duration_s": self.duration_s,
            "smc": vars(self.smc) if self.smc else {},
            "risk": vars(self.risk) if self.risk else {},
            "pa": vars(self.pa) if self.pa else {},
            "metadata": self.metadata,
        }


class TradeMemory:
    """
    In-memory ring buffer of completed TradeContext records.
    Thread-safe via asyncio.Lock (lazy init — no module-level lock).
    """

    def __init__(self, max_size: int = 10_000) -> None:
        self._max_size = max_size
        self._records: List[TradeContext] = []
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def record(self, ctx: TradeContext) -> None:
        """Store a completed trade context."""
        async with self._get_lock():
            self._records.append(ctx)
            if len(self._records) > self._max_size:
                self._records = self._records[-self._max_size :]
        logger.debug(
            "TradeMemory.record",
            signal_id=ctx.signal_id,
            outcome=ctx.outcome,
            total=len(self._records),
        )

    async def get_recent(self, n: int = 1000) -> List[TradeContext]:
        """Return the most recent n records."""
        async with self._get_lock():
            return list(self._records[-n:])

    async def get_all(self) -> List[TradeContext]:
        async with self._get_lock():
            return list(self._records)

    async def clear(self) -> None:
        async with self._get_lock():
            self._records.clear()
        logger.info("TradeMemory cleared")

    async def size(self) -> int:
        async with self._get_lock():
            return len(self._records)

    async def win_rate(self) -> float:
        """Calculate win rate from stored records."""
        async with self._get_lock():
            closed = [r for r in self._records if r.outcome in ("WIN", "LOSS")]
            if not closed:
                return 0.0
            wins = sum(1 for r in closed if r.outcome == "WIN")
            return wins / len(closed)

    async def export_for_training(self) -> List[Dict[str, Any]]:
        """Export all records as plain dicts for ML pipeline."""
        async with self._get_lock():
            return [r.to_dict() for r in self._records]


# ── Module-level singleton ────────────────────────────────────────────────────
_trade_memory: Optional[TradeMemory] = None


def get_trade_memory() -> TradeMemory:
    global _trade_memory
    if _trade_memory is None:
        _trade_memory = TradeMemory()
    return _trade_memory
