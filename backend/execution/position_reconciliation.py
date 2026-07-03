"""
backend/execution/position_reconciliation.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Background task: تطبیق OSM با MT5

GHOST positions:
  OSM معتقد است position باز است اما MT5 آن را نمی‌شناسد.
  → OSM را به CLOSED منتقل می‌کنیم.

ORPHAN positions:
  MT5 یک position باز دارد که OSM از آن خبر ندارد.
  → در OSM register و OPEN می‌کنیم.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MismatchType(str, Enum):
    """نوع ناهماهنگی بین OSM و MT5."""
    GHOST  = "GHOST"   # OSM open — MT5 ندارد
    ORPHAN = "ORPHAN"  # MT5 open — OSM نمی‌داند


@dataclass
class Mismatch:
    """یک ناهماهنگی بین OSM و MT5."""
    ticket:        int
    mismatch_type: MismatchType
    symbol:        Optional[str] = None
    volume:        Optional[float] = None
    detail:        str = ""


@dataclass
class ReconcileResult:
    """نتیجه یک دور reconciliation."""
    ghosts:     int = 0
    orphans:    int = 0
    mismatches: List[Mismatch] = field(default_factory=list)
    duration_ms: float = 0.0
    error:      Optional[str] = None


class PositionReconciler:
    """
    Reconciler بین OSM و MT5.

    مثال:
        reconciler = PositionReconciler(connector=mt5, osm=osm)
        result = await reconciler.run()
        print(f"GHOST: {result.ghosts}, ORPHAN: {result.orphans}")
    """

    def __init__(
        self,
        connector:    Any = None,
        osm:          Any = None,
        auto_close:   bool = True,
        auto_register: bool = True,
    ) -> None:
        self._connector    = connector
        self._osm          = osm
        self._auto_close   = auto_close
        self._auto_register = auto_register
        self._total_runs   = 0
        self._total_ghosts = 0
        self._total_orphans = 0
        self._last_run_at: Optional[float] = None

    async def run(self) -> ReconcileResult:
        """یک دور کامل reconciliation."""
        t0 = time.monotonic()
        result = ReconcileResult()

        connector = self._connector
        osm = self._osm

        if connector is None:
            try:
                from backend.execution.mt5_connector import mt5_connector
                connector = mt5_connector
            except Exception:
                pass

        if osm is None:
            try:
                from backend.execution.order_state_machine import order_state_machine
                osm = order_state_machine
            except Exception:
                pass

        if connector is None or osm is None:
            result.error = "connector یا osm موجود نیست"
            return result

        try:
            mt5_positions: List[Dict[str, Any]] = (
                await connector.get_open_positions()
            )
            mt5_tickets: Set[int] = {int(p["ticket"]) for p in mt5_positions}
            mt5_by_ticket: Dict[int, Dict] = {
                int(p["ticket"]): p for p in mt5_positions
            }

            osm_tickets: Set[int] = set(osm.active_tickets)

            # ── GHOST ─────────────────────────────────────────────────── #
            for ticket in osm_tickets - mt5_tickets:
                if osm.is_terminal(ticket):
                    continue
                m = Mismatch(
                    ticket=ticket,
                    mismatch_type=MismatchType.GHOST,
                    detail=f"ticket={ticket} در OSM open است اما MT5 ندارد",
                )
                result.mismatches.append(m)
                result.ghosts += 1
                logger.warning("[reconciler] GHOST ticket=%d", ticket)
                if self._auto_close:
                    try:
                        osm.transition(ticket, "CLOSED")
                    except Exception as exc:
                        logger.error("[reconciler] GHOST close error ticket=%d: %s", ticket, exc)

            # ── ORPHAN ────────────────────────────────────────────────── #
            for ticket in mt5_tickets - osm_tickets:
                pos = mt5_by_ticket[ticket]
                m = Mismatch(
                    ticket=ticket,
                    mismatch_type=MismatchType.ORPHAN,
                    symbol=pos.get("symbol"),
                    volume=pos.get("volume"),
                    detail=f"ticket={ticket} در MT5 open است اما OSM نمی‌داند",
                )
                result.mismatches.append(m)
                result.orphans += 1
                logger.warning("[reconciler] ORPHAN ticket=%d", ticket)
                if self._auto_register:
                    try:
                        osm.register(ticket)
                        osm.transition(ticket, "OPEN")
                    except Exception as exc:
                        logger.error("[reconciler] ORPHAN register error ticket=%d: %s", ticket, exc)

        except Exception as exc:
            logger.error("[reconciler] run() failed: %s", exc)
            result.error = str(exc)

        result.duration_ms = (time.monotonic() - t0) * 1000
        self._total_runs   += 1
        self._total_ghosts  += result.ghosts
        self._total_orphans += result.orphans
        self._last_run_at   = time.time()
        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "total_runs":    self._total_runs,
            "total_ghosts":  self._total_ghosts,
            "total_orphans": self._total_orphans,
            "last_run_at":   self._last_run_at,
        }

    async def loop(self, interval_s: float = 60.0) -> None:
        logger.info("[reconciler] loop started interval=%.0fs", interval_s)
        while True:
            await self.run()
            await asyncio.sleep(interval_s)


# ── backward-compat aliases ───────────────────────────────────────────────── #
PositionReconciliation = PositionReconciler
reconciler = PositionReconciler()
