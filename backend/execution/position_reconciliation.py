"""
backend/execution/position_reconciliation.py
Position reconciliation between OSM and MT5.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MismatchType(StrEnum):
    GHOST = "GHOST"
    ORPHAN = "ORPHAN"


@dataclass
class Mismatch:
    """Position mismatch."""
    ticket: int
    mismatch_type: MismatchType
    detail: str = ""


@dataclass
class ReconciliationResult:
    """Reconciliation result."""
    mismatches: list[Mismatch] = field(default_factory=list)
    ghosts: int = 0
    orphans: int = 0
    actions_taken: int = 0


class PositionReconciler:
    """Reconcile positions between OSM and MT5."""

    def __init__(
        self,
        connector: Any = None,
        osm: Any = None,
        auto_close_ghosts: bool = True,
        auto_register_orphans: bool = True,
    ):
        self.connector = connector
        self.osm = osm
        self.auto_close_ghosts = auto_close_ghosts
        self.auto_register_orphans = auto_register_orphans

    async def run(self) -> ReconciliationResult:
        """Run reconciliation."""
        result = ReconciliationResult()
        try:
            mt5_tickets = await self._get_mt5_open_tickets()
            osm_tickets = await self._get_osm_open_tickets()

            ghosts = osm_tickets - mt5_tickets
            orphans = mt5_tickets - osm_tickets

            result.ghosts = len(ghosts)
            result.orphans = len(orphans)

            for ticket in ghosts:
                mismatch = Mismatch(
                    ticket=ticket,
                    mismatch_type=MismatchType.GHOST,
                    detail="OSM darad -- MT5 uadarad",
                )
                result.mismatches.append(mismatch)
                logger.warning("[reconciler] GHOST ticket=%d", ticket)
                if self.auto_close_ghosts:
                    try:
                        await self.osm.reject(ticket, reason="GHOST reconciled")
                        result.actions_taken += 1
                    except Exception as exc:
                        logger.error("[reconciler] GHOST close error ticket=%d: %s", ticket, exc)

            for ticket in orphans:
                mismatch = Mismatch(
                    ticket=ticket,
                    mismatch_type=MismatchType.ORPHAN,
                    detail="MT5 darad -- OSM nami danad",
                )
                result.mismatches.append(mismatch)
                logger.warning("[reconciler] ORPHAN ticket=%d", ticket)
                if self.auto_register_orphans:
                    try:
                        await self.osm.register_orphan(ticket)
                        result.actions_taken += 1
                    except Exception as exc:
                        logger.error("[reconciler] ORPHAN register error ticket=%d: %s", ticket, exc)

        except Exception as exc:
            logger.error("[reconciler] run() failed: %s", exc)

        return result

    async def _get_mt5_open_tickets(self) -> set[int]:
        """Get MT5 tickets."""
        if self.connector is None:
            return set()
        try:
            positions = await self.connector.get_positions()
            return {p["ticket"] for p in positions if "ticket" in p}
        except Exception as exc:
            logger.error("[reconciler] _get_mt5_open_tickets failed: %s", exc)
        return set()

    async def _get_osm_open_tickets(self) -> set[int]:
        """Get OSM tickets."""
        if self.osm is None:
            return set()
        try:
            tickets = await self.osm.get_open_tickets()
            return set(tickets)
        except Exception as exc:
            logger.error("[reconciler] _get_osm_open_tickets failed: %s", exc)
        return set()
