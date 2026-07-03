"""
backend/execution/position_reconciliation.py
Position Reconciliation Service

Compares local OrderStateMachine vs live MT5 positions every 30s.
Detects ghosts (local OPEN but MT5 closed) and orphans (MT5 open, not tracked).
"""
from __future__ import annotations

import asyncio, logging, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)

RECONCILE_INTERVAL    = 30.0
PRICE_DRIFT_THRESHOLD = 0.0005


@dataclass
class ReconciliationResult:
    ts:               float     = field(default_factory=time.time)
    ghosts:           List[str] = field(default_factory=list)
    orphans:          List[int] = field(default_factory=list)
    drift_alerts:     List[str] = field(default_factory=list)
    reconciled_count: int       = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts, "ghosts": self.ghosts, "orphans": self.orphans,
                "drift_alerts": self.drift_alerts, "reconciled_count": self.reconciled_count}


class PositionReconciler:
    """Background service keeping local state in sync with MT5."""

    def __init__(self, connector: Any, state_machine: Any,
                 interval: float = RECONCILE_INTERVAL) -> None:
        self._mt5      = connector
        self._osm      = state_machine
        self._interval = interval
        self._running  = False
        self._last:    Optional[ReconciliationResult] = None

    async def run(self) -> None:
        self._running = True
        log.info("PositionReconciler: started (interval=%.0fs)", self._interval)
        while self._running:
            try:
                self._last = await self._reconcile_once()
                if self._last.ghosts or self._last.orphans:
                    log.warning("Reconciliation: ghosts=%s orphans=%s",
                                self._last.ghosts, self._last.orphans)
                else:
                    log.debug("Reconciliation OK: %d positions synced",
                              self._last.reconciled_count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Reconciliation error: %s", exc, exc_info=True)
            await asyncio.sleep(self._interval)
        log.info("PositionReconciler: stopped")

    def stop(self) -> None:
        self._running = False

    @property
    def last_result(self) -> Optional[ReconciliationResult]:
        return self._last

    async def _reconcile_once(self) -> ReconciliationResult:
        result = ReconciliationResult()
        try:
            async with self._mt5 as mt5:
                mt5_positions = await mt5.get_positions()
        except Exception as exc:
            log.warning("Cannot fetch MT5 positions: %s", exc)
            return result

        mt5_tickets: Set[int] = {p.ticket for p in mt5_positions}

        try:
            local_orders = self._osm.get_open_orders()
        except Exception as exc:
            log.warning("Cannot get local orders: %s", exc)
            return result

        local_tickets: Set[int] = set()
        for order in local_orders:
            t = order.get("order_id") or order.get("ticket")
            if t:
                try:
                    local_tickets.add(int(t))
                except (ValueError, TypeError):
                    pass

        for ticket in local_tickets - mt5_tickets:
            result.ghosts.append(str(ticket))
            try:
                self._osm.close_order(str(ticket))
            except Exception:
                pass

        for ticket in mt5_tickets - local_tickets:
            result.orphans.append(ticket)

        mt5_by_ticket = {p.ticket: p for p in mt5_positions}
        for order in local_orders:
            t = order.get("order_id") or order.get("ticket")
            if not t:
                continue
            try:
                ti = int(t)
            except (ValueError, TypeError):
                continue
            pos = mt5_by_ticket.get(ti)
            if not pos:
                continue
            local_price = order.get("open_price", 0.0)
            if local_price and abs(local_price - pos.open_price) > PRICE_DRIFT_THRESHOLD:
                result.drift_alerts.append(
                    f"ticket={ti} symbol={pos.symbol} "
                    f"local={local_price:.5f} mt5={pos.open_price:.5f}"
                )

        result.reconciled_count = len(mt5_tickets & local_tickets)
        return result


_reconciler: Optional[PositionReconciler] = None


def get_reconciler(connector: Any = None, state_machine: Any = None) -> PositionReconciler:
    global _reconciler
    if _reconciler is None:
        if connector is None:
            from backend.execution.mt5_connector import get_connector
            connector = get_connector()
        if state_machine is None:
            from backend.execution.order_state_machine import OrderStateMachineCompat
            state_machine = OrderStateMachineCompat.get_instance()
        _reconciler = PositionReconciler(connector, state_machine)
    return _reconciler


async def start_reconciler(**kwargs: Any) -> asyncio.Task:
    rec = get_reconciler(**kwargs)
    return asyncio.create_task(rec.run(), name="position_reconciler")
