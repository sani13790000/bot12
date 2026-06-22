"""
Galaxy Vast AI Trading Platform
Position Reconciliation -- FIX-5

FIX-5: Auto-close orphan positions replaced with Alert -> Manual Review -> Optional Close
  BEFORE: auto_close_orphans=True -> closes positions automatically after DB failures
  AFTER:
    - Orphan detected -> Telegram alert with details
    - Manual review flag set
    - Optional close only via explicit API call
    - DB failure NEVER triggers auto-close
    - Complete audit trail

Backward compatibility: auto_close_orphans param kept but IGNORED with warning.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger
from .mt5_connector import MT5Connector, mt5_connector as _default_mt5

logger = get_logger("execution.reconciliation")


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
    orphan_in_mt5: List[OrphanPosition]
    orphan_in_db:  List[str]
    db_failure:    bool
    alert_sent:    bool

    @property
    def has_discrepancy(self) -> bool:
        return bool(self.orphan_in_mt5 or self.orphan_in_db)


class PositionReconciliation:
    """
    FIX-5: Orphan positions are NEVER auto-closed.

    Workflow:
      1. run_once() compares MT5 vs DB
      2. Orphans -> alert via _alert_callback
      3. Orphans stored in _orphan_registry for admin review
      4. close_orphan_ticket() -> explicit manual close only
      5. DB failures -> alert only, no position changes
    """

    def __init__(self, mt5=None, interval_seconds: int = 60, auto_close_orphans: bool = False):
        self._mt5      = mt5 or _default_mt5
        self._interval = interval_seconds
        self._task:    Optional[asyncio.Task] = None
        self._last_result: Optional[ReconciliationResult] = None
        self._alert_callback: Optional[Callable] = None
        self._db_callback:    Optional[Callable] = None
        self._orphan_registry: Dict[int, OrphanPosition] = {}
        self._registry_lock = asyncio.Lock()

        if auto_close_orphans:
            logger.warning(
                "FIX-5: auto_close_orphans=True is IGNORED. "
                "Orphans require manual review via close_orphan_ticket(). "
                "This prevents accidental closes after DB failures."
            )

    def set_alert_callback(self, cb: Callable) -> None:
        self._alert_callback = cb

    def set_db_callback(self, cb: Callable) -> None:
        self._db_callback = cb

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("PositionReconciliation started (interval=%ds, auto_close=DISABLED)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run_once(self, db_tickets: Optional[List[int]] = None) -> ReconciliationResult:
        """
        FIX-5 guarantees:
          - DB failures -> result.db_failure=True, no position changes
          - Orphans -> alert only, stored in registry
          - Zero auto-closes under any circumstances
        """
        now = datetime.now(timezone.utc)
        db_failure = False

        try:
            mt5_positions = await self._mt5.get_positions()
        except Exception as exc:
            logger.error("Failed to get MT5 positions: %s", exc)
            return ReconciliationResult(timestamp=now, mt5_count=0, db_count=0, matched=0, orphan_in_mt5=[], orphan_in_db=[], db_failure=False, alert_sent=False)

        mt5_map: Dict[int, Any] = {getattr(p, "ticket", 0): p for p in mt5_positions}

        if db_tickets is None:
            try:
                db_tickets = await self._get_db_open_tickets()
            except Exception as exc:
                # FIX-5: DB failure -> alert only, never auto-close
                logger.error("DB read failed during reconciliation: %s -- NO positions modified (FIX-5)", exc)
                db_failure = True
                db_tickets = []

        db_ticket_set    = set(db_tickets)
        mt5_tickets      = set(mt5_map.keys()) - {0}
        orphan_tickets_mt5 = sorted(mt5_tickets - db_ticket_set)
        orphan_tickets_db  = sorted(db_ticket_set - mt5_tickets)

        orphan_positions: List[OrphanPosition] = []
        async with self._registry_lock:
            for ticket in orphan_tickets_mt5:
                if ticket in self._orphan_registry:
                    pos = mt5_map[ticket]
                    self._orphan_registry[ticket].profit = getattr(pos, "profit", 0.0)
                    orphan_positions.append(self._orphan_registry[ticket])
                    continue
                pos = mt5_map[ticket]
                orphan = OrphanPosition(
                    ticket=ticket, symbol=getattr(pos, "symbol", "UNKNOWN"),
                    direction="BUY" if getattr(pos, "type", 0) == 0 else "SELL",
                    volume=getattr(pos, "volume", 0.0), open_price=getattr(pos, "price_open", 0.0),
                    profit=getattr(pos, "profit", 0.0),
                )
                self._orphan_registry[ticket] = orphan
                orphan_positions.append(orphan)
                logger.warning("FIX-5 ORPHAN: ticket=%d symbol=%s vol=%.2f pnl=%.2f -- ALERT ONLY, no auto-close", ticket, orphan.symbol, orphan.volume, orphan.profit)

        result = ReconciliationResult(timestamp=now, mt5_count=len(mt5_tickets), db_count=len(db_ticket_set), matched=len(mt5_tickets & db_ticket_set), orphan_in_mt5=orphan_positions, orphan_in_db=[str(t) for t in orphan_tickets_db], db_failure=db_failure, alert_sent=False)

        if result.has_discrepancy or db_failure:
            logger.warning("Reconciliation: orphan_mt5=%d orphan_db=%d matched=%d db_failure=%s", len(orphan_positions), len(orphan_tickets_db), result.matched, db_failure)
            await self._send_alert(result)
            result.alert_sent = True

        self._last_result = result
        return result

    async def close_orphan_ticket(self, ticket: int, review_note: str = "", requester: str = "admin") -> Dict[str, Any]:
        """FIX-5: The ONLY path to closing an orphan -- explicit admin action."""
        async with self._registry_lock:
            orphan = self._orphan_registry.get(ticket)
            if orphan is None:
                return {"success": False, "error": f"Ticket {ticket} not found in orphan registry"}
            if orphan.status == OrphanStatus.MANUALLY_CLOSED:
                return {"success": False, "error": f"Ticket {ticket} already closed"}

        logger.info("Manual orphan close: ticket=%d symbol=%s requester=%s note=%s", ticket, orphan.symbol, requester, review_note)
        try:
            result = await self._mt5.close_position(ticket)
            async with self._registry_lock:
                orphan.status      = OrphanStatus.MANUALLY_CLOSED
                orphan.review_note = review_note
                orphan.closed_at   = datetime.now(timezone.utc)
            logger.info("Orphan ticket=%d manually closed", ticket)
            return {"success": True, "ticket": ticket, "symbol": orphan.symbol, "closed_at": orphan.closed_at.isoformat(), "requester": requester}
        except Exception as exc:
            logger.error("Failed to close orphan ticket=%d: %s", ticket, exc)
            return {"success": False, "error": str(exc)}

    async def mark_orphan_reviewed(self, ticket: int, note: str = "", action: str = "ignore") -> bool:
        async with self._registry_lock:
            orphan = self._orphan_registry.get(ticket)
            if orphan is None: return False
            orphan.status      = OrphanStatus.IGNORED if action == "ignore" else OrphanStatus.REVIEWED
            orphan.review_note = note
        logger.info("Orphan ticket=%d marked %s: %s", ticket, action, note)
        return True

    async def get_orphan_registry(self) -> List[Dict[str, Any]]:
        async with self._registry_lock:
            return [{"ticket": o.ticket, "symbol": o.symbol, "direction": o.direction, "volume": o.volume, "open_price": o.open_price, "profit": o.profit, "status": o.status.value, "discovered_at": o.discovered_at.isoformat(), "review_note": o.review_note, "closed_at": o.closed_at.isoformat() if o.closed_at else None} for o in self._orphan_registry.values()]

    @property
    def last_result(self) -> Optional[ReconciliationResult]: return self._last_result

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Reconciliation loop error: %s", exc, exc_info=True)

    async def _get_db_open_tickets(self) -> List[int]:
        if self._db_callback:
            return await self._db_callback()
        try:
            from ..database import get_database
            db = await get_database()
            rows = await db.select("execution_orders", filters={"status": "filled"}, columns="mt5_ticket")
            return [int(r["mt5_ticket"]) for r in rows if r.get("mt5_ticket")]
        except Exception as exc:
            logger.error("DB ticket fetch failed: %s", exc)
            raise

    async def _send_alert(self, result: ReconciliationResult) -> None:
        if not self._alert_callback: return
        try: await self._alert_callback(result)
        except Exception as exc: logger.error("Alert callback error: %s", exc)


# singleton
position_reconciliation = PositionReconciliation()
