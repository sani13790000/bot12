"""position_reconciliation.py — Hedge-Fund Grade Pre-Retry Reconciliation

HF-4: Position reconciliation before every retry
  - verify_position_exists(ticket, symbol) before any retry order
  - check_symbol_already_open(symbol, direction) for duplicate detection
  - Configurable interval (default 10s, env RECONCILE_INTERVAL_SECONDS)
  - DB failure -> alert only, NEVER auto-close (FIX-5 preserved)
  - Async-safe with asyncio.Lock
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging
logger = logging.getLogger("execution.reconciliation")

_DEFAULT_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "10"))
_MIN_INTERVAL     = 5
_MAX_INTERVAL     = 300


def _clamp(n: int) -> int:
    c = max(_MIN_INTERVAL, min(n, _MAX_INTERVAL))
    if c != n: logger.warning("HF-4: interval %ds clamped to %ds", n, c)
    return c


class OrphanStatus(str, Enum):
    PENDING_REVIEW  = "pending_review"
    REVIEWED        = "reviewed"
    MANUALLY_CLOSED = "manually_closed"
    IGNORED         = "ignored"


@dataclass
class OrphanPosition:
    ticket:        int
    symbol:        str
    direction:     str
    volume:        float
    open_price:    float
    profit:        float
    discovered_at: datetime     = field(default_factory=lambda: datetime.now(timezone.utc))
    status:        OrphanStatus = OrphanStatus.PENDING_REVIEW
    review_note:   str          = ""
    closed_at:     Optional[datetime] = None


@dataclass
class ReconciliationResult:
    timestamp:     datetime
    mt5_count:     int
    db_count:      int
    matched:       int
    orphan_mt5:    List[OrphanPosition]
    orphan_db:     List[str]
    db_failure:    bool
    alert_sent:    bool
    interval_used: int

    @property
    def ok(self) -> bool:
        return not self.db_failure and not self.orphan_mt5 and not self.orphan_db


class PositionReconciliation:
    """HF-4: verify_position_exists() before every retry."""

    def __init__(self, mt5=None, interval_seconds: int = _DEFAULT_INTERVAL, auto_close_orphans: bool = False) -> None:
        self._mt5      = mt5
        self._interval = _clamp(interval_seconds)
        self._task:    Optional[asyncio.Task] = None
        self._last:    Optional[ReconciliationResult] = None
        self._alert_cb: Optional[Callable] = None
        self._db_cb:    Optional[Callable] = None
        self._orphans:  Dict[int, OrphanPosition] = {}
        self._lock      = asyncio.Lock()
        self._known_mt5_tickets: Set[int] = set()
        if auto_close_orphans:
            logger.warning("FIX-5: auto_close_orphans=True IGNORED. Use close_orphan_ticket() for explicit close.")
        logger.info("PositionReconciliation interval=%ds", self._interval)

    async def verify_position_exists(self, ticket: int, symbol: str) -> bool:
        """HF-4: Call BEFORE every retry. True=position exists, skip retry. False=safe to retry."""
        if self._mt5 is None:
            logger.warning("HF-4: MT5 not configured, cannot verify ticket=%d", ticket)
            return False
        try:
            positions = await asyncio.to_thread(self._mt5.positions_get_sync, ticket=ticket)
            if positions and len(positions) > 0:
                logger.info("HF-4: ticket=%d %s EXISTS in MT5 -- skip retry", ticket, symbol)
                return True
            logger.info("HF-4: ticket=%d %s NOT in MT5 -- retry safe", ticket, symbol)
            return False
        except Exception as exc:
            logger.error("HF-4: verify ticket=%d failed: %s -- blocking retry (conservative)", ticket, exc)
            return True

    async def check_symbol_already_open(self, symbol: str, direction: str) -> bool:
        """HF-4: True if open position for symbol+direction exists (duplicate check)."""
        if self._mt5 is None: return False
        try:
            positions = await asyncio.to_thread(self._mt5.positions_get_sync, symbol=symbol)
            if not positions: return False
            for pos in positions:
                pos_dir = "BUY" if getattr(pos, "type", -1) == 0 else "SELL"
                if pos_dir == direction.upper():
                    logger.warning("HF-4: duplicate %s %s already open ticket=%d", direction, symbol, pos.ticket)
                    return True
            return False
        except Exception as exc:
            logger.error("HF-4: check_symbol_already_open error: %s", exc)
            return False

    async def start(self) -> None:
        if self._task and not self._task.done(): return
        self._task = asyncio.create_task(self._loop())
        logger.info("Reconciliation loop started interval=%ds", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    def set_interval(self, seconds: int) -> None:
        self._interval = _clamp(seconds)

    def set_alert_callback(self, cb: Callable) -> None: self._alert_cb = cb
    def set_db_callback(self, cb: Callable) -> None:    self._db_cb    = cb

    async def _loop(self) -> None:
        while True:
            try:
                result = await self.run_once()
                if result.db_failure or result.orphan_mt5:
                    await self._send_alert(result)
            except asyncio.CancelledError: break
            except Exception as exc: logger.error("reconciliation loop: %s", exc)
            await asyncio.sleep(self._interval)

    async def run_once(self) -> ReconciliationResult:
        now = datetime.now(timezone.utc)
        mt5_positions: Dict[int, Any] = {}
        if self._mt5 is not None:
            try:
                positions = await asyncio.to_thread(self._mt5.positions_get_sync)
                if positions:
                    for p in positions: mt5_positions[p.ticket] = p
                async with self._lock: self._known_mt5_tickets = set(mt5_positions.keys())
            except Exception as exc: logger.error("MT5 positions fetch: %s", exc)
        db_tickets: List[str] = []
        db_failure = False
        if self._db_cb is not None:
            try: db_tickets = await self._db_cb()
            except Exception as exc:
                db_failure = True
                logger.error("FIX-5: DB fetch failed (%s) -- NO auto-close, alert only", exc)
        db_set  = set(db_tickets)
        mt5_set = set(mt5_positions.keys())
        matched = len(mt5_set & {int(t) for t in db_set if str(t).isdigit()})
        orphan_mt5: List[OrphanPosition] = []
        if not db_failure:
            for ticket, pos in mt5_positions.items():
                if str(ticket) not in db_set:
                    op = OrphanPosition(
                        ticket=ticket, symbol=getattr(pos, "symbol", "?"),
                        direction="BUY" if getattr(pos, "type", -1) == 0 else "SELL",
                        volume=getattr(pos, "volume", 0.0),
                        open_price=getattr(pos, "price_open", 0.0),
                        profit=getattr(pos, "profit", 0.0),
                    )
                    async with self._lock:
                        if ticket not in self._orphans:
                            self._orphans[ticket] = op
                            logger.warning("FIX-5: orphan ticket=%d %s %s -- ALERT only, manual review", ticket, op.symbol, op.direction)
                    orphan_mt5.append(op)
        orphan_db = [t for t in db_set if t.isdigit() and int(t) not in mt5_set]
        result = ReconciliationResult(
            timestamp=now, mt5_count=len(mt5_positions), db_count=len(db_tickets),
            matched=matched, orphan_mt5=orphan_mt5, orphan_db=orphan_db,
            db_failure=db_failure, alert_sent=False, interval_used=self._interval,
        )
        self._last = result
        return result

    async def _send_alert(self, result: ReconciliationResult) -> None:
        if self._alert_cb is None: return
        try:
            msg = (f"Position Reconciliation Alert\n"
                   f"MT5:{result.mt5_count} DB:{result.db_count} Orphans:{len(result.orphan_mt5)} DBFail:{result.db_failure}")
            if asyncio.iscoroutinefunction(self._alert_cb): await self._alert_cb(msg)
            else: self._alert_cb(msg)
            result.alert_sent = True
        except Exception as exc: logger.error("alert send: %s", exc)

    async def close_orphan_ticket(self, ticket: int) -> bool:
        """Explicit admin close only. NEVER called automatically."""
        async with self._lock: op = self._orphans.get(ticket)
        if op is None or self._mt5 is None: return False
        try:
            ok = await asyncio.to_thread(self._mt5.close_position_sync, ticket)
            if ok:
                async with self._lock:
                    self._orphans[ticket].status   = OrphanStatus.MANUALLY_CLOSED
                    self._orphans[ticket].closed_at = datetime.now(timezone.utc)
            return ok
        except Exception as exc:
            logger.error("close_orphan_ticket(%d): %s", ticket, exc)
            return False

    async def get_orphan_registry(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return [{"ticket": o.ticket, "symbol": o.symbol, "direction": o.direction,
                     "volume": o.volume, "profit": o.profit, "status": o.status.value,
                     "discovered_at": o.discovered_at.isoformat(),
                     "closed_at": o.closed_at.isoformat() if o.closed_at else None}
                    for o in self._orphans.values()]

    def get_last_result(self) -> Optional[ReconciliationResult]: return self._last


_instance: Optional[PositionReconciliation] = None


def get_reconciliation(mt5=None) -> PositionReconciliation:
    global _instance
    if _instance is None: _instance = PositionReconciliation(mt5=mt5)
    return _instance


position_reconciliation = get_reconciliation()
