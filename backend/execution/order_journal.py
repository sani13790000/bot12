"""order_journal.py - Hedge-Fund Grade Order Journal v2 (HF-5)

HF-5: Immutable append-only order journal
  Tracks full lifecycle: Signal -> Risk -> Execution -> Fill -> Close
  - frozen=True JournalEntry (immutable after creation)
  - 15 JournalEventType events
  - In-memory ring buffer deque(maxlen=10_000)
  - Async-safe asyncio.Lock
  - Persistent storage via optional DB callback
  - Query by signal_id, order_id, ticket, symbol
  - Stats: win_rate, net_pnl, avg_slippage, latency
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger("execution.order_journal")
_MAX_ENTRIES = 10_000


class JournalEventType(str, Enum):
    SIGNAL_RECEIVED = "signal_received"
    RISK_ASSESSED = "risk_assessed"
    RISK_BLOCKED = "risk_blocked"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIAL = "order_partial"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_CLOSED = "position_closed"
    RETRY_QUEUED = "retry_queued"
    RETRY_EXECUTED = "retry_executed"
    DEAD_LETTERED = "dead_lettered"
    CIRCUIT_OPENED = "circuit_opened"
    SLIPPAGE_RECORDED = "slippage_recorded"
    ERROR = "error"


@dataclass(frozen=True)
class JournalEntry:
    """Immutable journal entry. Created once, never modified."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: JournalEventType = JournalEventType.SIGNAL_RECEIVED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_id: Optional[str] = None
    order_id: Optional[str] = None
    mt5_ticket: Optional[int] = None
    user_id: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    lot_size: Optional[float] = None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_score: Optional[float] = None
    risk_allowed: Optional[bool] = None
    risk_reason: Optional[str] = None
    lot_multiplier: Optional[float] = None
    pip_value_used: Optional[float] = None
    fill_price: Optional[float] = None
    fill_volume: Optional[float] = None
    fill_latency_ms: Optional[float] = None
    requested_price: Optional[float] = None
    slippage_pips: Optional[float] = None
    slippage_usd: Optional[float] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    pnl_usd: Optional[float] = None
    duration_s: Optional[float] = None
    mt5_retcode: Optional[int] = None
    broker_comment: Optional[str] = None
    breaker_name: Optional[str] = None
    breaker_state: Optional[str] = None
    retry_attempt: Optional[int] = None
    max_retries: Optional[int] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["timestamp"] = self.timestamp.isoformat()
        return {k: v for k, v in d.items() if v is not None}


class OrderJournal:
    """HF-5: Append-only order journal with full lifecycle tracking."""

    def __init__(
        self, max_entries: int = _MAX_ENTRIES, persist_callback: Optional[Callable] = None
    ) -> None:
        self._entries: Deque[JournalEntry] = deque(maxlen=max_entries)
        self._persist = persist_callback
        self._lock = asyncio.Lock()
        self._total_recorded = 0
        self._total_persisted = 0
        self._persist_errors = 0

    async def record(self, event_type: JournalEventType, **kwargs: Any) -> JournalEntry:
        entry = JournalEntry(event_type=event_type, **kwargs)
        async with self._lock:
            self._entries.append(entry)
            self._total_recorded += 1
        logger.debug(
            "JOURNAL [%s] %s signal=%s",
            event_type.value,
            entry.symbol or "-",
            (entry.signal_id or "-")[:8],
        )
        if self._persist:
            asyncio.create_task(self._persist_entry(entry))
        return entry

    async def record_signal_received(
        self, signal_id: str, symbol: str, direction: str, **kw
    ) -> JournalEntry:
        return await self.record(
            JournalEventType.SIGNAL_RECEIVED,
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            **kw,
        )

    async def record_risk_assessed(
        self,
        signal_id: str,
        approved: bool,
        lot_size: float,
        risk_reason: str = "",
        pip_value_used: float = 0.0,
        **kw,
    ) -> JournalEntry:
        evt = JournalEventType.RISK_ASSESSED if approved else JournalEventType.RISK_BLOCKED
        return await self.record(
            evt,
            signal_id=signal_id,
            risk_allowed=approved,
            lot_size=lot_size,
            risk_reason=risk_reason or None,
            pip_value_used=pip_value_used or None,
            **kw,
        )

    async def record_order_submitted(
        self,
        signal_id: str,
        order_id: str,
        symbol: str,
        direction: str,
        lot_size: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        **kw,
    ) -> JournalEntry:
        return await self.record(
            JournalEventType.ORDER_SUBMITTED,
            signal_id=signal_id,
            order_id=order_id,
            symbol=symbol,
            direction=direction,
            lot_size=lot_size,
            price=price,
            stop_loss=stop_loss or None,
            take_profit=take_profit or None,
            **kw,
        )

    async def record_fill(
        self,
        signal_id: str,
        order_id: str,
        mt5_ticket: int,
        fill_price: float,
        fill_volume: float,
        requested_price: float = 0.0,
        pip_value: float = 10.0,
        fill_latency_ms: float = 0.0,
        **kw,
    ) -> JournalEntry:
        slippage_pips = slippage_usd = 0.0
        if requested_price and fill_price and pip_value:
            slippage_pips = abs(fill_price - requested_price) / 0.0001
            slippage_usd = slippage_pips * pip_value * fill_volume
        return await self.record(
            JournalEventType.ORDER_FILLED,
            signal_id=signal_id,
            order_id=order_id,
            mt5_ticket=mt5_ticket,
            fill_price=fill_price,
            fill_volume=fill_volume,
            requested_price=requested_price or None,
            slippage_pips=round(slippage_pips, 2) or None,
            slippage_usd=round(slippage_usd, 4) or None,
            fill_latency_ms=fill_latency_ms or None,
            **kw,
        )

    async def record_close(
        self,
        signal_id: str,
        order_id: str,
        mt5_ticket: int,
        close_price: float,
        pnl_usd: float,
        close_reason: str = "",
        duration_s: float = 0.0,
        **kw,
    ) -> JournalEntry:
        return await self.record(
            JournalEventType.POSITION_CLOSED,
            signal_id=signal_id,
            order_id=order_id,
            mt5_ticket=mt5_ticket,
            close_price=close_price,
            pnl_usd=round(pnl_usd, 2),
            close_reason=close_reason or None,
            duration_s=duration_s or None,
            **kw,
        )

    async def record_circuit_open(
        self, breaker_name: str, reason: str, signal_id: Optional[str] = None
    ) -> JournalEntry:
        return await self.record(
            JournalEventType.CIRCUIT_OPENED,
            signal_id=signal_id,
            breaker_name=breaker_name,
            error_message=reason,
        )

    async def record_error(
        self,
        error: Exception,
        signal_id: Optional[str] = None,
        order_id: Optional[str] = None,
        **kw,
    ) -> JournalEntry:
        return await self.record(
            JournalEventType.ERROR,
            signal_id=signal_id,
            order_id=order_id,
            error_message=str(error),
            error_type=type(error).__name__,
            **kw,
        )

    async def get_by_signal(self, signal_id: str) -> List[JournalEntry]:
        async with self._lock:
            return [e for e in self._entries if e.signal_id == signal_id]

    async def get_by_order(self, order_id: str) -> List[JournalEntry]:
        async with self._lock:
            return [e for e in self._entries if e.order_id == order_id]

    async def get_by_ticket(self, ticket: int) -> List[JournalEntry]:
        async with self._lock:
            return [e for e in self._entries if e.mt5_ticket == ticket]

    async def get_by_symbol(self, symbol: str, limit: int = 100) -> List[JournalEntry]:
        async with self._lock:
            return [e for e in reversed(self._entries) if e.symbol == symbol.upper()][:limit]

    async def get_by_event_type(
        self, event_type: JournalEventType, limit: int = 100
    ) -> List[JournalEntry]:
        async with self._lock:
            return [e for e in reversed(self._entries) if e.event_type == event_type][:limit]

    async def get_recent(self, limit: int = 50) -> List[JournalEntry]:
        async with self._lock:
            return list(reversed(list(self._entries)))[:limit]

    async def stats(self) -> Dict[str, Any]:
        async with self._lock:
            fills = [e for e in self._entries if e.event_type == JournalEventType.ORDER_FILLED]
            closes = [e for e in self._entries if e.event_type == JournalEventType.POSITION_CLOSED]
            blocked = [e for e in self._entries if e.event_type == JournalEventType.RISK_BLOCKED]
            errors = [e for e in self._entries if e.event_type == JournalEventType.ERROR]
            pnl_values = [e.pnl_usd for e in closes if e.pnl_usd is not None]
            slip_values = [e.slippage_pips for e in fills if e.slippage_pips is not None]
            latency_values = [e.fill_latency_ms for e in fills if e.fill_latency_ms is not None]
            wins = [p for p in pnl_values if p > 0]
            n = len(pnl_values)
            return {
                "total_entries": self._total_recorded,
                "buffer_size": len(self._entries),
                "fills": len(fills),
                "closes": len(closes),
                "blocked_by_risk": len(blocked),
                "errors": len(errors),
                "persisted": self._total_persisted,
                "persist_errors": self._persist_errors,
                "pnl": {
                    "total_trades": n,
                    "wins": len(wins),
                    "win_rate": round(len(wins) / n * 100, 1) if n else 0.0,
                    "net_usd": round(sum(pnl_values), 2) if pnl_values else 0.0,
                    "avg_usd": round(sum(pnl_values) / n, 2) if n else 0.0,
                },
                "slippage": {
                    "avg_pips": round(sum(slip_values) / len(slip_values), 2)
                    if slip_values
                    else 0.0,
                    "max_pips": round(max(slip_values), 2) if slip_values else 0.0,
                },
                "latency": {
                    "avg_ms": round(sum(latency_values) / len(latency_values), 1)
                    if latency_values
                    else 0.0,
                    "max_ms": round(max(latency_values), 1) if latency_values else 0.0,
                },
            }

    async def _persist_entry(self, entry: JournalEntry) -> None:
        try:
            await self._persist(entry.to_dict())
            self._total_persisted += 1
        except Exception as exc:
            self._persist_errors += 1
            logger.error("Journal persist error: %s", exc)


_journal: Optional[OrderJournal] = None


def get_order_journal() -> OrderJournal:
    global _journal
    if _journal is None:
        _journal = OrderJournal()
    return _journal
