"""
backend/execution/position_reconciliation.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Background task that reconciles the internal OrderStateMachine
with the live MT5 position list.

What it detects
---------------
GHOST positions:
    Tickets that the state machine believes are OPEN but MT5 no longer
    has — closed externally (manual close, stop-out, etc.).

ORPHAN positions:
    Tickets that MT5 has open but the state machine does not know about
    — opened outside the bot (manual trades).

Usage::

    from backend.execution.position_reconciliation import reconciler
    from backend.services.scheduler import scheduler

    scheduler.register("reconcile", reconciler.run, interval_s=30)
"""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


class PositionReconciler:
    """
    Compares internal state with live MT5 positions and resolves
    discrepancies.
    """

    def __init__(
        self,
        connector:     object = None,   # MT5Connector
        state_machine: object = None,   # OrderStateMachine
    ) -> None:
        self._connector     = connector
        self._state_machine = state_machine
        self._ghost_count   = 0
        self._orphan_count  = 0

    async def run(self) -> None:
        """
        Periodic reconciliation entry point.

        Called by the Scheduler every N seconds.
        """
        connector, osm = self._get_deps()
        if connector is None or osm is None:
            return

        try:
            live_positions = await connector.get_all_positions()
        except Exception as exc:
            logger.warning("[reconciler] cannot fetch MT5 positions: %s", exc)
            return

        live_tickets = {p.ticket for p in live_positions}
        active_tickets = set(osm.active_tickets())

        # ── GHOST: OSM thinks open, MT5 says closed ───────────────────── #
        ghosts = active_tickets - live_tickets
        for ticket in ghosts:
            logger.warning(
                "[reconciler] GHOST ticket=%d — closing in OSM", ticket
            )
            try:
                osm.transition(ticket, "CLOSED")
                self._ghost_count += 1
            except Exception as exc:
                logger.error(
                    "[reconciler] failed to close ghost ticket=%d: %s",
                    ticket, exc,
                )

        # ── ORPHAN: MT5 has open, OSM does not know ───────────────────── #
        orphans = live_tickets - active_tickets
        for ticket in orphans:
            logger.warning(
                "[reconciler] ORPHAN ticket=%d — registering in OSM", ticket
            )
            try:
                osm.register(ticket)
                osm.transition(ticket, "SUBMITTED")
                osm.transition(ticket, "OPEN")
                self._orphan_count += 1
            except Exception as exc:
                logger.error(
                    "[reconciler] failed to register orphan ticket=%d: %s",
                    ticket, exc,
                )

        if ghosts or orphans:
            logger.info(
                "[reconciler] cycle complete: %d ghost(s), %d orphan(s)",
                len(ghosts), len(orphans),
            )
        else:
            logger.debug("[reconciler] cycle complete: no discrepancies")

    def stats(self) -> dict:
        """Return lifetime reconciliation counters."""
        return {
            "total_ghosts_resolved":  self._ghost_count,
            "total_orphans_resolved": self._orphan_count,
        }

    # ── Internals ─────────────────────────────────────────────────────────── #

    def _get_deps(self):
        """Lazy-load dependencies to avoid circular imports at module level."""
        connector = self._connector
        osm       = self._state_machine

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

        return connector, osm


# ── Module-level singleton ────────────────────────────────────────────────── #
reconciler = PositionReconciler()
