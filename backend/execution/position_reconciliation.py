"""
backend/execution/position_reconciliation.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Background task: تطبیق OSM با MT5

GHOST positions:
  - OSM darad -- MT5 nadarad
  - action: talash braye bastan / taref kardan dar OSM

ORPHAN positions:
  - MT5 darad -- OSM nami danad
  - action: sabht dar OSM ya alarm be
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class MismatchType(StrEnum):
    GHOST  = "GHOST"    # OSM open — MT5 uadarad
    ORPHAN = "ORPHAN"   # MT5 open — OSM nami danad


@dataclass
class Mismatch:
    ticket: int
    mismatch_type: MismatchType
    detail: str = ""


@dataclass
class ReconciliationResult:
    mismatches: list[Mismatch] = field(default_factory=list)
    ghosts: int = 0
    orphans: int = 0
    actions_taken: int = 0


class PositionReconciler:
    """
    Reconciler beyn OSM o MT5.

    mesal:
        reconciler = PositionReconciler(connector=mt5, osm=osm)
        result = await reconciler.run()
        logger.info("[reconciler] example: GHOST=%d, ORPHAN=%d", result.ghosts, result.orphans)
    """

    def __init__(
        self,
        connector:    Any = None,
        osm:          Any = None,
        auto_close_ghosts: bool = True,
        auto_register_orphans: bool = True,
    ) -> None:
        self.connector = connector
        self.osm = osm
        self.auto_close_ghosts = auto_close_ghosts
        self.auto_register_orphans = auto_register_orphans

    async def run(self) -> ReconciliationResult:
        """Hamahang-sazi beyn OSM v MT5."""
        result = ReconciliationResult()
        try:
            mt5_tickets = await self._get_mt5_open_tickets()
            osm_tickets = await self._get_osm_open_tickets()

            ghosts  = osm_tickets - mt5_tickets
            orphans = mt5_tickets - osm_tickets

            result.ghosts  = len(ghosts)
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
                    detail="MT5 why darad -- OSM uadarad",
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
        """Tickethaye az MT5 Gateway."""
        if self.connector is None:
            return set()
        try:
            positions = await self.connector.get_positions()
            return {p["ticket"] for p in positions if "ticket" in p}
        except Exception as exc:
            logger.warning("[reconciler] MT5 get_positions failed: %s", exc)
        return set()

    async def _get_osm_open_tickets(self) -> set[int]:
        """Tickethaye azi OSM."""
        if self.osm is None:
            return set()
        try:
            tickets = await self.osm.get_open_tickets()
            return set(tickets)
        except Exception as exc:
            logger.warning("[reconciler] OSM get_open_tickets failed: %s", exc)
        return set()


async def reconciler_loop(
    connector: Any,
    osm: Any,
    interval_s: float = 30.0,
    auto_close_ghosts: bool = True,
    auto_register_orphans: bool = True,
) -> None:
    """Loop daime-dar braye hamahang-sazy dar pas-zamine."""
    reconciler = PositionReconciler(
        connector=connector,
        osm=osm,
        auto_close_ghosts=auto_close_ghosts,
        auto_register_orphans=auto_register_orphans,
    )
    logger.info("[reconciler] loop started interval=%.0fs", interval_s)
    while True:
        try:
            result = await reconciler.run()
            if result.mismatches:
                logger.warning(
                    "[reconciler] mismatches=%d ghosts=%d orphans=%d actions=%d",
                    len(result.mismatches),
                    result.ghosts,
                    result.orphans,
                    result.actions_taken,
                )
        except Exception as exc:
            logger.error("[reconciler] loop error: %s", exc)
        await asyncio.sleep(interval_s)
