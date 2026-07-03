from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from ..core.logger import get_logger
from .mt5_connector import MT5Connector
from .order_state_machine import OrderState, get_order_state_machine

logger = get_logger('execution.position_reconciliation')
_RECONCILE_INTERVAL_S = 30


class ReconciliationResult:
    def __init__(self):
        self.matched: List[str] = []
        self.diverged: List[str] = []
        self.recovered: List[str] = []
        self.errors: List[str] = []
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self):
        return {'matched': len(self.matched), 'diverged': len(self.diverged), 'recovered': len(self.recovered), 'errors': len(self.errors), 'timestamp': self.timestamp.isoformat()}


class PositionReconciler:
    def __init__(self, connector: MT5Connector):
        self._connector = connector
        self._log = logger
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reconcile_loop(), name='reconciler')
        self._log.info('PositionReconciler started')

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _reconcile_loop(self):
        while self._running:
            try:
                await self.reconcile_once()
            except Exception as exc:
                self._log.error('Reconciliation error: %s', exc)
            await asyncio.sleep(_RECONCILE_INTERVAL_S)

    async def reconcile_once(self) -> ReconciliationResult:
        result = ReconciliationResult()
        osm = await get_order_state_machine()
        try:
            mt5_positions = await self._connector.get_open_positions()
        except Exception as exc:
            result.errors.append(f'MT5 fetch failed: {exc}')
            return result
        mt5_tickets: Set[int] = {p.get('ticket') for p in mt5_positions if p.get('ticket')}
        local_open = await osm.get_open_orders()
        for rec in local_open:
            ticket = rec.mt5_ticket
            if ticket is None:
                continue
            if ticket in mt5_tickets:
                result.matched.append(rec.order_id)
            else:
                self._log.warning('Divergence: %s (ticket=%d) not in MT5', rec.order_id, ticket)
                result.diverged.append(rec.order_id)
                try:
                    await osm.transition(rec.order_id, OrderState.HUNG)
                    result.recovered.append(rec.order_id)
                except Exception as exc:
                    result.errors.append(f'{rec.order_id}: {exc}')
        return result
