"""
Galaxy Vast AI Trading Platform
Position Reconciliation — Phase 7

Compares positions in MT5 terminal vs. local DB every N seconds.
If a position exists in MT5 but not in DB (or vice-versa), it:
  1. Logs the discrepancy
  2. Sends a Telegram alert
  3. Optionally closes orphan MT5 positions

Runs as a background asyncio task.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger
from .mt5_connector import MT5Connector, mt5_connector as _default_mt5

logger = get_logger("execution.reconciliation")


class ReconciliationResult:
    __slots__ = (
        "timestamp", "mt5_count", "db_count",
        "orphan_in_mt5", "orphan_in_db", "matched",
    )

    def __init__(self) -> None:
        self.timestamp = datetime.now(timezone.utc)
        self.mt5_count = 0
        self.db_count = 0
        self.orphan_in_mt5: List[int] = []
        self.orphan_in_db: List[str] = []
        self.matched: int = 0

    @property
    def has_discrepancy(self) -> bool:
        return bool(self.orphan_in_mt5 or self.orphan_in_db)


class PositionReconciliation:
    """Compares MT5 open positions with DB records periodically."""

    def __init__(
        self,
        mt5: Optional[MT5Connector] = None,
        interval_seconds: int = 60,
        auto_close_orphans: bool = False,
    ) -> None:
        self._mt5 = mt5 or _default_mt5
        self._interval = interval_seconds
        self._auto_close = auto_close_orphans
        self._task: Optional[asyncio.Task] = None
        self._last_result: Optional[ReconciliationResult] = None
        self._alert_callback: Optional[Any] = None

    def set_alert_callback(self, cb: Any) -> None:
        self._alert_callback = cb

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("PositionReconciliation started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run_once(self, db_tickets: Optional[List[int]] = None) -> ReconciliationResult:
        result = ReconciliationResult()

        # Get MT5 positions
        try:
            mt5_positions = await self._mt5.get_positions()
        except Exception as exc:
            logger.error("Failed to get MT5 positions: %s", exc)
            return result

        mt5_tickets = {getattr(p, "ticket", 0) for p in mt5_positions}
        result.mt5_count = len(mt5_tickets)

        # Get DB positions
        if db_tickets is None:
            db_tickets = await self._get_db_open_tickets()
        db_ticket_set = set(db_tickets)
        result.db_count = len(db_ticket_set)

        result.orphan_in_mt5 = sorted(mt5_tickets - db_ticket_set)
        result.orphan_in_db = [str(t) for t in sorted(db_ticket_set - mt5_tickets)]
        result.matched = len(mt5_tickets & db_ticket_set)

        self._last_result = result

        if result.has_discrepancy:
            logger.warning(
                "Reconciliation discrepancy: orphan_mt5=%s orphan_db=%s",
                result.orphan_in_mt5, result.orphan_in_db,
            )
            if self._alert_callback:
                try:
                    await self._alert_callback(result)
                except Exception as exc:
                    logger.error("Alert callback error: %s", exc)

            if self._auto_close and result.orphan_in_mt5:
                for ticket in result.orphan_in_mt5:
                    logger.warning("Auto-closing orphan MT5 position: %s", ticket)
                    await self._mt5.close_position(ticket)

        return result

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("Reconciliation loop error: %s", exc)
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    async def _get_db_open_tickets(self) -> List[int]:
        """Fetch open MT5 tickets from Supabase."""
        try:
            from ..database import db
            result = await asyncio.to_thread(
                lambda: db.client.table("trades")
                .select("mt5_ticket")
                .eq("status", "open")
                .not_.is_("mt5_ticket", "null")
                .execute()
            )
            rows = getattr(result, "data", []) or []
            return [r["mt5_ticket"] for r in rows if r.get("mt5_ticket")]
        except Exception as exc:
            logger.error("DB position fetch error: %s", exc)
            return []

    @property
    def last_result(self) -> Optional[ReconciliationResult]:
        return self._last_result


# Singleton
position_reconciliation = PositionReconciliation()
