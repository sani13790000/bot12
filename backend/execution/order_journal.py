"""order_journal.py — Hedge-Fund Grade Order Journal

HF-5: Complete audit trail for every order lifecycle
  Signal -> Risk -> Execution -> Fill -> Close
  - Immutable append-only journal entries
  - Per-order full lifecycle tracking with timestamps
  - Persistent storage via DB callback
  - In-memory ring buffer (last 10k entries)
  - Async-safe with asyncio.Lock
  - Query by signal_id, order_id, symbol
  - Stats: win_rate, pnl, slippage, latency
"""
from __future__ import annotations
import asyncio
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional
import logging
logger = logging.getLogger("execution.order_journal")

_MAX_ENTRIES = 10_000


class JournalEventType(str, Enum):
    SIGNAL_RECEIVED   = "signal_received"
    RISK_ASSESSED     = "risk_assessed"
    RISK_BLOCKED      = "risk_blocked"
    ORDER_SUBMITTED   = "order_submitted"
    ORDER_REJECTED    = "order_rejected"
    ORDER_FILLED      = "order_filled"
    ORDER_PARTIAL     = "order_partial"
    ORDER_CANCELLED   = "order_cancelled"
    POSITION_CLOSED   = "position_closed"
    RETRY_QUEUED      = "retry_queued"
    RETRY_EXECUTED    = "retry_executed"
    DEAD_LETTERED     = "dead_lettered"
    CIRCUIT_OPENED    = "circuit_opened"
    SLIPPAGE_RECORDED = "slippage_recorded"
    ERROR             = "error"


@dataclass
class JournalEntry:
    """Immutable journal entry. Never modify after creation."""
    entry_id:      str              = field(default_factory=lambda: str(uuid.uuid4()))
    event_type:    JournalEventType = JournalEventType.SIGNAL_RECEIVED
    signal_id:     Optional[str]   = None
    order_id:      Optional[str]   = None
    symbol:        Optional[str]   = None
    direction:     Optional[str]   = None
    lot_size:      Optional[float] = None
    price:         Optional[float] = None
    stop_loss:     Optional[float] = None
    take_profit:   Optional[float] = None
    risk_score:    Optional[float] = None
    risk_allowed:  Optional[bool]  = None
    risk_reason:   Optional[str]   = None
    fill_price:    Optional[float] = None
    fill_volume:   Optional[float] = None
    slippage_pips: Optional[float] = None
    close_price:   Optional[float] = None
    close_reason:  Optional[str]   = None
    pnl_usd:       Optional[float] = None
    mt5_ticket:    Optional[int]   = None
    mt5_retcode:   Optional[int]   = None
    timestamp:     datetime        = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms:    Optional[float] = None
    message:       Optional[str]   = None
    metadata:      Dict[str, Any]  = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["timestamp"]  = self.timestamp.isoformat()
        return d


@dataclass
class OrderRecord:
    """Full lifecycle of one order, assembled from journal entries."""
    order_id:        str
    signal_id:       Optional[str]   = None
    symbol:          Optional[str]   = None
    direction:       Optional[str]   = None
    lot_size:        Optional[float] = None
    signal_ts:       Optional[datetime] = None
    risk_ts:         Optional[datetime] = None
    submitted_ts:    Optional[datetime] = None
    filled_ts:       Optional[datetime] = None
    closed_ts:       Optional[datetime] = None
    requested_price: Optional[float] = None
    fill_price:      Optional[float] = None
    close_price:     Optional[float] = None
    stop_loss:       Optional[float] = None
    take_profit:     Optional[float] = None
    slippage_pips:   Optional[float] = None
    pnl_usd:         Optional[float] = None
    mt5_ticket:      Optional[int]   = None
    risk_score:      Optional[float] = None
    risk_allowed:    Optional[bool]  = None
    final_state:     str             = "pending"
    entries:         List[str]       = field(default_factory=list)

    @property
    def total_latency_ms(self) -> Optional[float]:
        if self.signal_ts and self.filled_ts:
            return (self.filled_ts - self.signal_ts).total_seconds() * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id, "signal_id": self.signal_id,
            "symbol": self.symbol, "direction": self.direction, "lot_size": self.lot_size,
            "signal_ts":    self.signal_ts.isoformat()    if self.signal_ts    else None,
            "risk_ts":      self.risk_ts.isoformat()      if self.risk_ts      else None,
            "submitted_ts": self.submitted_ts.isoformat() if self.submitted_ts else None,
            "filled_ts":    self.filled_ts.isoformat()    if self.filled_ts    else None,
            "closed_ts":    self.closed_ts.isoformat()    if self.closed_ts    else None,
            "requested_price": self.requested_price, "fill_price": self.fill_price,
            "close_price": self.close_price, "stop_loss": self.stop_loss,
            "take_profit": self.take_profit, "slippage_pips": self.slippage_pips,
            "pnl_usd": self.pnl_usd, "mt5_ticket": self.mt5_ticket,
            "risk_score": self.risk_score, "risk_allowed": self.risk_allowed,
            "final_state": self.final_state, "total_latency_ms": self.total_latency_ms,
            "entries_count": len(self.entries),
        }


class OrderJournal:
    """HF-5: Append-only order journal. Every lifecycle event recorded with full context."""

    def __init__(self, persist_callback: Optional[Callable] = None, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: Deque[JournalEntry]   = deque(maxlen=max_entries)
        self._orders:  Dict[str, OrderRecord] = {}
        self._lock     = asyncio.Lock()
        self._persist  = persist_callback
        logger.info("OrderJournal initialized max_entries=%d", max_entries)

    async def record_signal(self, signal_id: str, symbol: str, direction: str,
                             lot_size: float, price: float, stop_loss: float,
                             take_profit: float, metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.SIGNAL_RECEIVED,
            signal_id=signal_id, symbol=symbol, direction=direction,
            lot_size=lot_size, price=price, stop_loss=stop_loss, take_profit=take_profit,
            metadata=metadata or {})
        await self._append(entry)
        return entry

    async def record_risk(self, signal_id: str, order_id: str, risk_score: float,
                           allowed: bool, reason: str = "", metadata: Optional[Dict] = None) -> JournalEntry:
        event = JournalEventType.RISK_ASSESSED if allowed else JournalEventType.RISK_BLOCKED
        entry = JournalEntry(event_type=event, signal_id=signal_id, order_id=order_id,
            risk_score=risk_score, risk_allowed=allowed, risk_reason=reason, metadata=metadata or {})
        await self._append(entry)
        async with self._lock:
            rec = self._orders.get(order_id)
            if rec:
                rec.risk_ts = entry.timestamp; rec.risk_score = risk_score; rec.risk_allowed = allowed
                if not allowed: rec.final_state = "risk_blocked"
        return entry

    async def record_submission(self, order_id: str, signal_id: str, symbol: str,
                                 direction: str, lot_size: float, price: float,
                                 stop_loss: float, take_profit: float,
                                 mt5_ticket: Optional[int] = None,
                                 latency_ms: Optional[float] = None,
                                 metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.ORDER_SUBMITTED,
            order_id=order_id, signal_id=signal_id, symbol=symbol, direction=direction,
            lot_size=lot_size, price=price, stop_loss=stop_loss, take_profit=take_profit,
            mt5_ticket=mt5_ticket, latency_ms=latency_ms, metadata=metadata or {})
        await self._append(entry)
        async with self._lock:
            if order_id not in self._orders:
                self._orders[order_id] = OrderRecord(order_id=order_id, signal_id=signal_id,
                    symbol=symbol, direction=direction, lot_size=lot_size)
            rec = self._orders[order_id]
            rec.submitted_ts    = entry.timestamp
            if rec.signal_ts is None: rec.signal_ts = entry.timestamp
            rec.requested_price = price; rec.stop_loss = stop_loss; rec.take_profit = take_profit
            rec.mt5_ticket      = mt5_ticket; rec.final_state = "submitted"
            rec.entries.append(entry.entry_id)
        return entry

    async def record_fill(self, order_id: str, fill_price: float, fill_volume: float,
                           slippage_pips: Optional[float] = None,
                           mt5_ticket: Optional[int] = None,
                           latency_ms: Optional[float] = None,
                           metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.ORDER_FILLED,
            order_id=order_id, fill_price=fill_price, fill_volume=fill_volume,
            slippage_pips=slippage_pips, mt5_ticket=mt5_ticket,
            latency_ms=latency_ms, metadata=metadata or {})
        await self._append(entry)
        async with self._lock:
            rec = self._orders.get(order_id)
            if rec:
                rec.filled_ts = entry.timestamp; rec.fill_price = fill_price
                rec.slippage_pips = slippage_pips; rec.mt5_ticket = mt5_ticket or rec.mt5_ticket
                rec.final_state = "filled"; rec.entries.append(entry.entry_id)
        logger.info("JOURNAL fill order=%s price=%.5f slip=%.2fpips", order_id, fill_price, slippage_pips or 0)
        return entry

    async def record_close(self, order_id: str, close_price: float, pnl_usd: float,
                            reason: str = "", mt5_ticket: Optional[int] = None,
                            metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.POSITION_CLOSED,
            order_id=order_id, close_price=close_price, close_reason=reason,
            pnl_usd=pnl_usd, mt5_ticket=mt5_ticket, metadata=metadata or {})
        await self._append(entry)
        async with self._lock:
            rec = self._orders.get(order_id)
            if rec:
                rec.closed_ts = entry.timestamp; rec.close_price = close_price
                rec.pnl_usd = pnl_usd; rec.final_state = "closed"; rec.entries.append(entry.entry_id)
        logger.info("JOURNAL close order=%s pnl=%.2f reason=%s", order_id, pnl_usd, reason)
        return entry

    async def record_rejection(self, order_id: str, reason: str,
                                mt5_retcode: Optional[int] = None,
                                metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.ORDER_REJECTED,
            order_id=order_id, risk_reason=reason, mt5_retcode=mt5_retcode, metadata=metadata or {})
        await self._append(entry)
        async with self._lock:
            rec = self._orders.get(order_id)
            if rec: rec.final_state = "rejected"; rec.entries.append(entry.entry_id)
        return entry

    async def record_error(self, order_id: Optional[str], signal_id: Optional[str],
                            message: str, metadata: Optional[Dict] = None) -> JournalEntry:
        entry = JournalEntry(event_type=JournalEventType.ERROR,
            order_id=order_id, signal_id=signal_id, message=message, metadata=metadata or {})
        await self._append(entry)
        return entry

    async def get_order(self, order_id: str) -> Optional[OrderRecord]:
        async with self._lock: return self._orders.get(order_id)

    async def get_entries_for_order(self, order_id: str) -> List[JournalEntry]:
        async with self._lock: return [e for e in self._entries if e.order_id == order_id]

    async def get_entries_for_signal(self, signal_id: str) -> List[JournalEntry]:
        async with self._lock: return [e for e in self._entries if e.signal_id == signal_id]

    async def get_recent_entries(self, n: int = 100) -> List[JournalEntry]:
        async with self._lock: entries = list(self._entries)
        return entries[-n:]

    async def get_recent_orders(self, n: int = 50) -> List[Dict[str, Any]]:
        async with self._lock: orders = list(self._orders.values())
        orders.sort(key=lambda o: o.submitted_ts or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return [o.to_dict() for o in orders[:n]]

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock: orders = list(self._orders.values())
        filled    = [o for o in orders if o.final_state == "closed" and o.pnl_usd is not None]
        wins      = [o for o in filled if (o.pnl_usd or 0) > 0]
        total_pnl = sum(o.pnl_usd for o in filled if o.pnl_usd)
        slips     = [o.slippage_pips for o in filled if o.slippage_pips is not None]
        lats      = [o.total_latency_ms for o in filled if o.total_latency_ms]
        return {
            "total_orders":      len(orders),
            "total_entries":     len(self._entries),
            "closed_orders":     len(filled),
            "win_rate":          round(len(wins) / max(len(filled), 1) * 100, 2),
            "total_pnl_usd":     round(total_pnl, 2),
            "avg_slippage_pips": round(sum(slips) / max(len(slips), 1), 4) if slips else 0.0,
            "avg_latency_ms":    round(sum(lats) / max(len(lats), 1), 2) if lats else None,
        }

    async def _append(self, entry: JournalEntry) -> None:
        async with self._lock: self._entries.append(entry)
        if self._persist is not None:
            try:
                if asyncio.iscoroutinefunction(self._persist): await self._persist(entry.to_dict())
                else: self._persist(entry.to_dict())
            except Exception as exc: logger.error("journal persist: %s", exc)


_journal: Optional[OrderJournal] = None


def get_order_journal(persist_callback: Optional[Callable] = None) -> OrderJournal:
    global _journal
    if _journal is None: _journal = OrderJournal(persist_callback=persist_callback)
    return _journal


order_journal = get_order_journal()
