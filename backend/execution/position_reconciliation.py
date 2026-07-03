"""
backend/execution/position_reconciliation.py
Galaxy Vast AI - Position Reconciliation Service

Compares MT5 positions with OrderStateMachine every 30 seconds.
Detects: GHOST (in MT5 but not SM), ORPHAN (in SM but not MT5).
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from backend.execution.mt5_connector import MT5Connector, Position
from backend.execution.order_state_machine import OrderContext, OrderState, OrderStateMachine

log = logging.getLogger(__name__)
RECONCILE_INTERVAL = 30


class DiscrepancyType(str, Enum):
    GHOST = "GHOST"
    ORPHAN = "ORPHAN"
    DRIFT = "DRIFT"


@dataclass
class Discrepancy:
    kind: DiscrepancyType
    ticket: Optional[int]
    order_id: Optional[str]
    detail: str


class PositionReconciler:
    """Periodic MT5 vs OrderStateMachine comparison."""

    def __init__(self, connector: MT5Connector) -> None:
        self._connector = connector
        self._running = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="reconciler")
        log.info("PositionReconciler started (interval=%ds)", RECONCILE_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("PositionReconciler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                discrepancies = await self.reconcile_once()
                if discrepancies:
                    log.warning("Reconciliation found %d discrepancies", len(discrepancies))
                    for d in discrepancies:
                        log.warning("  [%s] ticket=%s order=%s - %s", d.kind.value, d.ticket, d.order_id, d.detail)
            except Exception:
                log.exception("Reconciliation error")
            await asyncio.sleep(RECONCILE_INTERVAL)

    async def reconcile_once(self) -> list:
        mt5_positions = await self._connector.get_positions()
        sm = await OrderStateMachine.get_instance()
        active_orders = await sm.get_all_active()
        mt5_tickets = {p.ticket for p in mt5_positions}
        sm_tickets = {ctx.ticket for ctx in active_orders if ctx.ticket is not None and ctx.state == OrderState.FILLED}
        discrepancies = []
        for ticket in mt5_tickets - sm_tickets:
            discrepancies.append(Discrepancy(kind=DiscrepancyType.GHOST, ticket=ticket, order_id=None, detail=f"ticket {ticket} in MT5 but not in state machine"))
        for ticket in sm_tickets - mt5_tickets:
            ctx = next((c for c in active_orders if c.ticket == ticket), None)
            discrepancies.append(Discrepancy(kind=DiscrepancyType.ORPHAN, ticket=ticket, order_id=str(ctx.order_id) if ctx else None, detail=f"ticket {ticket} in state machine but not in MT5"))
        return discrepancies
