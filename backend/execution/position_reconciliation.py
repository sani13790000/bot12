"""position_reconciliation.py - Hedge-Fund Grade Pre-Retry Reconciliation v2 (HF-4)

HF-4: Position reconciliation BEFORE every retry
BUG-PR-1 FIX: Added public run_once() wrapper for private _run_once().
BUG-PR-2 FIX: Added set_mt5(connector) injection method.
"""
from __future__ import annotations
import asyncio, os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging
logger = logging.getLogger("execution.reconciliation")
_DEFAULT_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "10"))
_MIN_INTERVAL = 5
_MAX_INTERVAL = 300


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
    ticket: int; symbol: str; direction: str
    volume: float; open_price: float; profit: float
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: OrphanStatus = OrphanStatus.PENDING_REVIEW
    review_note: str = ""
    closed_at: Optional[datetime] = None


@dataclass
class PreRetryCheck:
    ticket: int; symbol: str; already_filled: bool
    mt5_volume: float = 0.0; mt5_profit: float = 0.0
    direction: str = ""; error: Optional[str] = None

    @property
    def should_skip_retry(self) -> bool: return self.already_filled


@dataclass
class DuplicateCheck:
    symbol: str; direction: str; has_duplicate: bool
    existing_tickets: List[int] = field(default_factory=list)
    existing_volume: float = 0.0


@dataclass
class ReconciliationResult:
    timestamp: datetime; mt5_count: int; db_count: int; matched: int
    orphan_mt5: List[OrphanPosition]; orphan_db: List[str]
    db_failure: bool; alert_sent: bool; interval_used: int

    @property
    def ok(self) -> bool:
        return not self.db_failure and not self.orphan_mt5 and not self.orphan_db


class PositionReconciliation:
    """HF-4: verify_position_exists() before every retry. NEVER auto-closes."""

    def __init__(self, mt5=None, interval_seconds: int = _DEFAULT_INTERVAL,
                 auto_close_orphans: bool = False, alert_callback: Optional[Callable] = None) -> None:
        self._mt5 = mt5
        self._interval = _clamp(interval_seconds)
        self._alert = alert_callback
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._orphans: Dict[int, OrphanPosition] = {}
        if auto_close_orphans:
            logger.warning("HF-4: auto_close_orphans=True DISABLED. Orphans require manual review.")

    def set_mt5(self, connector: Any) -> None:
        """BUG-PR-2 FIX: Wire MT5Connector after singleton creation. Call from ExecutionService.start()."""
        self._mt5 = connector
        logger.info("HF-4: MT5 connector injected into PositionReconciliation")

    async def verify_position_exists(self, ticket: int, symbol: str) -> PreRetryCheck:
        if self._mt5 is None:
            logger.warning("HF-4: MT5 not set - cannot verify ticket %d", ticket)
            return PreRetryCheck(ticket=ticket, symbol=symbol, already_filled=False, error="mt5_not_configured")
        try:
            positions = await asyncio.to_thread(self._mt5.positions_get, ticket=ticket)
            if positions is None: positions = []
            if len(positions) > 0:
                pos = positions[0]
                logger.info("HF-4: verify ticket=%d ALREADY FILLED (vol=%.2f) - skip retry", ticket, pos.volume)
                return PreRetryCheck(ticket=ticket, symbol=symbol, already_filled=True,
                    mt5_volume=pos.volume, mt5_profit=pos.profit,
                    direction="BUY" if pos.type == 0 else "SELL")
            logger.debug("HF-4: ticket %d not in MT5 - retry allowed", ticket)
            return PreRetryCheck(ticket=ticket, symbol=symbol, already_filled=False)
        except Exception as exc:
            logger.error("HF-4: verify_position_exists error: %s", exc)
            return PreRetryCheck(ticket=ticket, symbol=symbol, already_filled=False, error=str(exc))

    async def check_symbol_already_open(self, symbol: str, direction: str) -> DuplicateCheck:
        if self._mt5 is None:
            return DuplicateCheck(symbol=symbol, direction=direction, has_duplicate=False)
        sym = symbol.upper().strip()
        dir_type = 0 if direction.upper() == "BUY" else 1
        try:
            positions = await asyncio.to_thread(self._mt5.positions_get, symbol=sym)
            if positions is None: positions = []
            matching = [p for p in positions if p.type == dir_type]
            if matching:
                tickets = [p.ticket for p in matching]
                volume = sum(p.volume for p in matching)
                logger.warning("HF-4: duplicate %s %s already open (tickets=%s vol=%.2f)", sym, direction, tickets, volume)
                return DuplicateCheck(symbol=sym, direction=direction, has_duplicate=True,
                    existing_tickets=tickets, existing_volume=volume)
            return DuplicateCheck(symbol=sym, direction=direction, has_duplicate=False)
        except Exception as exc:
            logger.error("HF-4: check_symbol_already_open error: %s", exc)
            return DuplicateCheck(symbol=sym, direction=direction, has_duplicate=False)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("PositionReconciliation started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    def set_interval(self, seconds: int) -> None:
        self._interval = _clamp(seconds)
        logger.info("HF-4: interval updated to %ds", self._interval)

    async def run_once(self) -> ReconciliationResult:
        """BUG-PR-1 FIX: Public wrapper. execution_service called run_once() but only _run_once() existed."""
        return await self._run_once()

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self._run_once()
            except asyncio.CancelledError: break
            except Exception as exc: logger.error("Reconciliation loop error: %s", exc, exc_info=True)

    async def _run_once(self) -> ReconciliationResult:
        async with self._lock: return await self._reconcile()

    async def _reconcile(self) -> ReconciliationResult:
        now = datetime.now(timezone.utc)
        mt5_positions: List[Any] = []
        if self._mt5:
            try: mt5_positions = await asyncio.to_thread(self._mt5.positions_get) or []
            except Exception as exc: logger.error("MT5 positions_get error: %s", exc)
        mt5_tickets: Set[int] = {p.ticket for p in mt5_positions}
        db_tickets: Set[str] = set()
        db_failure = False
        try:
            from ..database import db
            rows = await asyncio.to_thread(
                lambda: db.client.table("execution_orders").select("mt5_ticket").eq("status", "filled").execute())
            db_tickets = {str(r["mt5_ticket"]) for r in (rows.data or []) if r.get("mt5_ticket")}
        except Exception as exc:
            db_failure = True
            logger.error("HF-4: DB read FAILED (%s) - NO positions will be closed.", exc)
        new_orphans: List[OrphanPosition] = []
        if not db_failure:
            for pos in mt5_positions:
                if str(pos.ticket) not in db_tickets and pos.ticket not in self._orphans:
                    orphan = OrphanPosition(ticket=pos.ticket, symbol=pos.symbol,
                        direction="BUY" if pos.type == 0 else "SELL",
                        volume=pos.volume, open_price=pos.price_open, profit=pos.profit)
                    self._orphans[pos.ticket] = orphan
                    new_orphans.append(orphan)
                    logger.warning("HF-4: ORPHAN ticket=%d %s ALERT ONLY - manual review required", pos.ticket, pos.symbol)
        alert_sent = False
        if new_orphans and self._alert:
            try: await self._alert(new_orphans, db_failure); alert_sent = True
            except Exception as exc: logger.error("Orphan alert error: %s", exc)
        orphan_db = [t for t in db_tickets if int(t) not in mt5_tickets] if not db_failure else []
        return ReconciliationResult(timestamp=now, mt5_count=len(mt5_positions), db_count=len(db_tickets),
            matched=len(mt5_tickets & {int(t) for t in db_tickets}) if not db_failure else 0,
            orphan_mt5=list(self._orphans.values()), orphan_db=orphan_db,
            db_failure=db_failure, alert_sent=alert_sent, interval_used=self._interval)

    def get_orphan_registry(self) -> List[OrphanPosition]: return list(self._orphans.values())
    def get_pending_orphans(self) -> List[OrphanPosition]:
        return [o for o in self._orphans.values() if o.status == OrphanStatus.PENDING_REVIEW]

    async def close_orphan_ticket(self, ticket: int, note: str = "") -> bool:
        orphan = self._orphans.get(ticket)
        if orphan is None:
            logger.warning("close_orphan_ticket: ticket %d not in orphan registry", ticket); return False
        if self._mt5 is None:
            logger.error("close_orphan_ticket: MT5 not configured"); return False
        try:
            result = await self._mt5.close_position(ticket)
            if result and result.success:
                orphan.status = OrphanStatus.MANUALLY_CLOSED
                orphan.closed_at = datetime.now(timezone.utc)
                orphan.review_note = note
                logger.info("HF-4: Orphan ticket=%d manually closed by admin", ticket)
                return True
            logger.error("HF-4: Failed to close orphan ticket=%d", ticket)
            return False
        except Exception as exc:
            logger.error("HF-4: close_orphan_ticket error: %s", exc)
            return False

    def mark_orphan_reviewed(self, ticket: int, status: OrphanStatus = OrphanStatus.REVIEWED, note: str = "") -> bool:
        orphan = self._orphans.get(ticket)
        if orphan is None: return False
        orphan.status = status; orphan.review_note = note
        logger.info("HF-4: orphan ticket=%d marked as %s", ticket, status.value)
        return True

    def pending_count(self) -> int: return len(self.get_pending_orphans())

    def health(self) -> Dict[str, Any]:
        return {"interval_s": self._interval, "total_orphans": len(self._orphans),
                "pending_review": self.pending_count(), "auto_close_enabled": False,
                "mt5_connected": self._mt5 is not None}


position_reconciliation = PositionReconciliation()
