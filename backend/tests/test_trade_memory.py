"""
تست‌های TradeMemory
"""
from __future__ import annotations
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TradeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    OPEN = "OPEN"


@dataclass
class SMCContext:
    order_block_quality: float = 0.0
    fvg_present: bool = False
    liquidity_swept: bool = False
    bos_confirmed: bool = False
    choch_detected: bool = False
    institutional_bias: str = "NEUTRAL"


@dataclass
class PAContext:
    pattern_quality: float = 0.0
    confirmation_patterns: List[str] = field(default_factory=list)
    rejection_signals: List[str] = field(default_factory=list)


@dataclass
class RiskContext:
    risk_reward_ratio: float = 0.0
    lot_size: float = 0.01
    risk_pct: float = 0.01
    risk_usd: float = 100.0


@dataclass
class TradeContext:
    trade_id: str
    signal_id: str
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime]
    duration_minutes: float
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    direction: str
    outcome: TradeOutcome
    pnl_pips: float
    pnl_usd: float
    realized_rr: float
    confidence_score: float
    session: str
    market_condition: str
    smc: SMCContext
    price_action: PAContext
    risk: RiskContext
    news_active: bool = False
    previous_consecutive_losses: int = 0
    notes: str = ""

    def to_ml_features(self) -> Dict[str, float]:
        return {
            "confidence_score": self.confidence_score,
            "rr_ratio": self.risk.risk_reward_ratio,
            "duration_minutes": self.duration_minutes,
            "pnl_pips": self.pnl_pips,
            "smc_quality": self.smc.order_block_quality,
            "pa_quality": self.price_action.pattern_quality,
            "news_active": float(self.news_active),
            "consecutive_losses": float(self.previous_consecutive_losses),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "outcome": self.outcome.value,
            "pnl_usd": self.pnl_usd,
            "pnl_pips": self.pnl_pips,
        }


class TradeMemory:
    _DB_TABLE = "trade_memory"

    def __init__(self, max_memory: int = 500):
        self._memory: List[TradeContext] = []
        self._max_memory = max_memory
        self._db_available = False

    def record(self, context: TradeContext) -> None:
        self._memory.append(context)
        if len(self._memory) > self._max_memory:
            self._memory.pop(0)

    def get_recent(self, n: int = 20) -> List[TradeContext]:
        return list(self._memory[-n:])

    def get_average_rr(self, n: int = 20) -> float:
        recent = self.get_recent(n)
        closed = [t for t in recent
                  if t.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS)]
        if not closed:
            return 0.0
        return sum(t.realized_rr for t in closed) / len(closed)

    def get_win_rate(self, n: int = 20) -> float:
        recent = self.get_recent(n)
        closed = [t for t in recent
                  if t.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS)]
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.outcome == TradeOutcome.WIN)
        return wins / len(closed)

    def get_consecutive_losses(self) -> int:
        count = 0
        for trade in reversed(self._memory):
            if trade.outcome == TradeOutcome.LOSS:
                count += 1
            else:
                break
        return count

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._memory)
        wins  = sum(1 for t in self._memory if t.outcome == TradeOutcome.WIN)
        losses = sum(1 for t in self._memory if t.outcome == TradeOutcome.LOSS)
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total > 0 else 0.0,
            "avg_rr": self.get_average_rr(),
            "consecutive_losses": self.get_consecutive_losses(),
            "memory_usage": f"{total}/{self._max_memory}",
            "db_available": self._db_available,
        }

    def to_feature_matrix(self) -> Tuple[List[Dict], List[int]]:
        features, labels = [], []
        for trade in self._memory:
            if trade.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS):
                features.append(trade.to_ml_features())
                labels.append(1 if trade.outcome == TradeOutcome.WIN else 0)
        return features, labels


def _make_trade(outcome=TradeOutcome.WIN, pnl_usd=100.0, rr=2.0) -> TradeContext:
    now = datetime.now(timezone.utc)
    return TradeContext(
        trade_id="t1", signal_id="s1", symbol="XAUUSD",
        entry_time=now, exit_time=now, duration_minutes=30.0,
        entry_price=1950.0, exit_price=1960.0 if pnl_usd > 0 else 1940.0,
        stop_loss=1940.0, take_profit=1970.0,
        direction="BUY", outcome=outcome,
        pnl_pips=10.0 if pnl_usd > 0 else -10.0,
        pnl_usd=pnl_usd, realized_rr=rr,
        confidence_score=75.0, session="LONDON",
        market_condition="TRENDING",
        smc=SMCContext(order_block_quality=0.8),
        price_action=PAContext(pattern_quality=0.7),
        risk=RiskContext(risk_reward_ratio=rr),
        news_active=False, previous_consecutive_losses=0,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestTradeMemoryRecord:

    def test_record_adds_to_memory(self):
        mem = TradeMemory()
        mem.record(_make_trade())
        assert len(mem._memory) == 1

    def test_max_memory_evicts_oldest(self):
        mem = TradeMemory(max_memory=3)
        for _ in range(5):
            mem.record(_make_trade())
        assert len(mem._memory) == 3

    def test_get_recent_returns_last_n(self):
        mem = TradeMemory()
        for i in range(10):
            mem.record(_make_trade(pnl_usd=float(i)))
        recent = mem.get_recent(5)
        assert len(recent) == 5
        assert recent[-1].pnl_usd == 9.0


class TestTradeMemoryStats:

    def test_win_rate_all_wins(self):
        mem = TradeMemory()
        for _ in range(5):
            mem.record(_make_trade(outcome=TradeOutcome.WIN))
        assert mem.get_win_rate() == 1.0

    def test_win_rate_all_losses(self):
        mem = TradeMemory()
        for _ in range(5):
            mem.record(_make_trade(outcome=TradeOutcome.LOSS, pnl_usd=-50.0))
        assert mem.get_win_rate() == 0.0

    def test_win_rate_mixed(self):
        mem = TradeMemory()
        for _ in range(3):
            mem.record(_make_trade(outcome=TradeOutcome.WIN))
        for _ in range(2):
            mem.record(_make_trade(outcome=TradeOutcome.LOSS, pnl_usd=-50.0))
        wr = mem.get_win_rate()
        assert abs(wr - 0.6) < 0.001

    def test_consecutive_losses_zero(self):
        mem = TradeMemory()
        mem.record(_make_trade(outcome=TradeOutcome.WIN))
        assert mem.get_consecutive_losses() == 0

    def test_consecutive_losses_count(self):
        mem = TradeMemory()
        mem.record(_make_trade(outcome=TradeOutcome.WIN))
        for _ in range(3):
            mem.record(_make_trade(outcome=TradeOutcome.LOSS, pnl_usd=-50.0))
        assert mem.get_consecutive_losses() == 3

    def test_stats_keys(self):
        mem = TradeMemory()
        stats = mem.get_stats()
        for k in ("total_trades", "wins", "losses", "win_rate",
                  "avg_rr", "consecutive_losses", "memory_usage", "db_available"):
            assert k in stats

    def test_stats_empty(self):
        mem = TradeMemory()
        stats = mem.get_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_average_rr(self):
        mem = TradeMemory()
        mem.record(_make_trade(outcome=TradeOutcome.WIN, rr=2.0))
        mem.record(_make_trade(outcome=TradeOutcome.WIN, rr=3.0))
        avg = mem.get_average_rr()
        assert abs(avg - 2.5) < 0.001


class TestTradeContextFeatures:

    def test_to_ml_features_keys(self):
        t = _make_trade()
        f = t.to_ml_features()
        for k in ("confidence_score", "rr_ratio", "duration_minutes",
                  "pnl_pips", "smc_quality", "pa_quality",
                  "news_active", "consecutive_losses"):
            assert k in f

    def test_to_dict_keys(self):
        t = _make_trade()
        d = t.to_dict()
        for k in ("trade_id", "symbol", "direction", "outcome", "pnl_usd"):
            assert k in d

    def test_feature_matrix(self):
        mem = TradeMemory()
        mem.record(_make_trade(outcome=TradeOutcome.WIN))
        mem.record(_make_trade(outcome=TradeOutcome.LOSS, pnl_usd=-50.0))
        features, labels = mem.to_feature_matrix()
        assert len(features) == 2
        assert labels[0] == 1
        assert labels[1] == 0
