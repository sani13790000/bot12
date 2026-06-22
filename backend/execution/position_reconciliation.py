"""
Galaxy Vast AI Trading Platform
Position Reconciliation — Production Reliability v2

FIXES:
  R-4: Configurable reconciliation interval (default 10s, was hardcoded 60s)
  FIX-5: DB failure NEVER triggers auto-close (preserved)
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger
from .mt5_connector import MT5Connector, mt5_connector as _default_mt5

logger = get_logger("execution.reconciliation")

_DEFAULT_INTERVAL: int = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "10"))
_MIN_INTERVAL:     int = 5
_MAX_INTERVAL:     int = 300


def _clamp_interval(seconds: int) -> int:
    clamped = max(_MIN_INTERVAL, min(seconds, _MAX_INTERVAL))
    if clamped != seconds:
        logger.warning("R-4: interval %ds clamped to %ds", seconds, clamped)
    return clamped


class OrphanStatus(str, Enum):
    PENDING_REVIEW   = "pending_review"
    REVIEWED         = "reviewed"
    MANUALLY_CLOSED  = "manually_closed"
    IGNORED          = "ignored"


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
    timestamp:      datetime
    mt5_count:      int
    db_count:       int
    matched:        int
    orphan_in_mt5:  List[OrphanPosition]
    orphan_in_db:   List[str]
    db_failure:     bool
    alert_sent:     bool
    interval_used:  int

    @property
    def has_discrepancy(self) -> bool:
        return bool(self.orphan_in_mt5 or self.orphan_in_db)


class PositionReconciliation:
    """
    R-4: interval_seconds configurable via env RECONCILE_INTERVAL_SECONDS (default 10s).
    FIX-5: Orphans -> alert + manual review. DB failure -> alert only. Never auto-close.
    """

    def __init__(self, mt5=None, interval_seconds: int = _DEFAULT_INTERVAL, auto_close_orphans: bool = False):
        self._mt5      = mt5 or _default_mt5
        self._interval = _clamp_interval(interval_seconds)
        self._task:    Optional[asyncio.Task] = None
        self._last_result: Optional[ReconciliationResult] = None
        self._alert_callback: Optional[Callable] = None
        self._db_callback:    Optional[Callable] = None
        self._orphan_registry: Dict[int, OrphanPosition] = {}
        self._registry_lock = asyncio.Lock()
        if auto_close_orphans:
            logger.warning("FIX-5: auto_close_orphans=True IGNORED. Use close_orphan_ticket() for explicit close.")
        logger.info("PositionReconciliation: interval=%ds", self._interval)

    def set_interval(self, seconds: int) -> None:
        """R-4: Change interval at runtime. Loop picks up next iteration."""
        old = self._interval
        self._interval = _clamp_interval(seconds)
        logger.info("R-4: interval changed %ds -> %ds", old, self._interval)

    @property
    def interval_seconds(self) -> int:
        return self._interval

    def set_alert_callback(self, cb: Callable) -> None: self._alert_callback = cb
    def set_db_callback(self, cb: Callable)    -> None: self._db_callback    = cb

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("PositionReconciliation started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def _loop(self) -> None:
        while True:
            try: await self.run_once()
            except asyncio.CancelledError: break
            except Exception as exc: logger.error("Reconciliation loop error: %s", exc)
            try: await asyncio.sleep(self._interval)   # R-4: live interval
            except asyncio.CancelledError: break

    async def run_once(self) -> ReconciliationResult:
        timestamp  = datetime.now(timezone.utc)
        db_failure = False
        db_tickets: List[str] = []

        try: mt5_positions = await self._mt5.get_positions()
        except Exception as exc:
            logger.error("MT5 get_positions failed: %s", exc)
            mt5_positions = []

        mt5_tickets = {str(getattr(p, "ticket", 0)) for p in mt5_positions}

        try:
            if self._db_callback:
                db_tickets = await self._db_callback() or []
        except Exception as exc:
            db_failure = True
            logger.error("FIX-5: DB callback failed (%s). No position changes.", exc)
            await self._send_alert(f"\u26a0\ufe0f DB FAILURE in reconciliation: {exc}\nManual review required.")
            result = ReconciliationResult(
                timestamp=timestamp, mt5_count=len(mt5_tickets), db_count=0,
                matched=0, orphan_in_mt5=[], orphan_in_db=[],
                db_failure=True, alert_sent=True, interval_used=self._interval,
            )
            self._last_result = result
            return result

        db_ticket_set  = {str(t) for t in db_tickets}
        orphan_tickets = mt5_tickets - db_ticket_set
        orphan_in_db   = list(db_ticket_set - mt5_tickets)
        orphan_in_mt5: List[OrphanPosition] = []
        alert_sent = False

        for pos in mt5_positions:
            ticket = str(getattr(pos, "ticket", 0))
            if ticket not in orphan_tickets:
                continue
            orphan = OrphanPosition(
                ticket=int(ticket), symbol=getattr(pos, "symbol", "UNKNOWN"),
                direction="BUY" if getattr(pos, "type", 0) == 0 else "SELL",
                volume=getattr(pos, "volume", 0.0), open_price=getattr(pos, "price_open", 0.0),
                profit=getattr(pos, "profit", 0.0),
            )
            orphan_in_mt5.append(orphan)
            async with self._registry_lock:
                if int(ticket) not in self._orphan_registry:
                    self._orphan_registry[int(ticket)] = orphan
                    msg = (f"\U0001f6a8 Orphan Position: ticket={ticket} symbol={orphan.symbol} "
                           f"vol={orphan.volume} profit={orphan.profit:.2f}\n"
                           f"Use /orphan close {ticket} or /orphan ignore {ticket}")
                    await self._send_alert(msg)
                    alert_sent = True
                    logger.warning("FIX-5: Orphan ticket=%s awaiting manual review", ticket)

        matched = len(mt5_tickets & db_ticket_set)
        result  = ReconciliationResult(
            timestamp=timestamp, mt5_count=len(mt5_tickets), db_count=len(db_ticket_set),
            matched=matched, orphan_in_mt5=orphan_in_mt5, orphan_in_db=orphan_in_db,
            db_failure=db_failure, alert_sent=alert_sent, interval_used=self._interval,
        )
        self._last_result = result
        return result

    async def _send_alert(self, message: str) -> None:
        if self._alert_callback:
            try: await self._alert_callback(message)
            except Exception as exc: logger.error("Alert callback failed: %s", exc)

    async def close_orphan_ticket(self, ticket: int, reason: str = "") -> bool:
        async with self._registry_lock:
            orphan = self._orphan_registry.get(ticket)
            if not orphan: return False
            if orphan.status == OrphanStatus.MANUALLY_CLOSED: return True
        result = await self._mt5.close_position(ticket)
        async with self._registry_lock:
            orphan = self._orphan_registry.get(ticket)
            if orphan:
                if result.success:
                    orphan.status = OrphanStatus.MANUALLY_CLOSED
                    orphan.review_note = reason
                    orphan.closed_at   = datetime.now(timezone.utc)
                    logger.info("Orphan ticket %d manually closed. Reason: %s", ticket, reason)
                else:
                    logger.error("Failed to close orphan ticket %d: %s", ticket, result.error)
        return result.success

    async def mark_orphan_reviewed(self, ticket: int, action: str = "ignore", note: str = "") -> bool:
        async with self._registry_lock:
            orphan = self._orphan_registry.get(ticket)
            if not orphan: return False
            orphan.status = OrphanStatus.IGNORED if action == "ignore" else OrphanStatus.REVIEWED
            orphan.review_note = note
            return True

    async def get_orphan_registry(self) -> Dict[int, OrphanPosition]:
        async with self._registry_lock: return dict(self._orphan_registry)

    def get_last_result(self) -> Optional[ReconciliationResult]:
        return self._last_result


position_reconciliation = PositionReconciliation()
