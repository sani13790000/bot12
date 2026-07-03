"""
backend/execution/execution_service.py
Galaxy Vast AI - Execution Service

Receives signal from Decision Engine, executes in MT5,
updates OrderStateMachine, and persists result.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4
from backend.execution.mt5_connector import MT5Connector, OrderRequest, OrderResult
from backend.execution.order_state_machine import OrderEvent, OrderStateMachine, OrderState

log = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    symbol: str
    direction: str
    volume: float
    sl_pips: float
    tp_pips: float
    comment: str = ""
    signal_id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.signal_id is None:
            self.signal_id = uuid4()


class ExecutionService:
    """Trade execution service."""

    def __init__(self, connector: MT5Connector) -> None:
        self._connector = connector

    async def execute(self, signal: TradeSignal) -> Optional[UUID]:
        if signal.volume <= 0:
            log.warning("Rejected signal %s: volume=%.2f", signal.signal_id, signal.volume)
            return None
        if signal.direction not in ("BUY", "SELL"):
            log.warning("Rejected signal %s: direction=%s", signal.signal_id, signal.direction)
            return None
        sm = await OrderStateMachine.get_instance()
        order_id = uuid4()
        await sm.create_order(order_id=order_id, symbol=signal.symbol, volume=signal.volume)
        await sm.transition(order_id, OrderEvent.SUBMIT)
        req = OrderRequest(symbol=signal.symbol, direction=signal.direction, volume=signal.volume, sl_pips=signal.sl_pips, tp_pips=signal.tp_pips, comment=signal.comment or f"sig:{signal.signal_id}")
        result: OrderResult = await self._connector.place_order(req)
        if result.success:
            await sm.transition(order_id, OrderEvent.FILL, ticket=result.ticket, open_price=result.open_price)
            log.info("Order %s filled: ticket=%s price=%.5f latency=%.1fms", order_id, result.ticket, result.open_price or 0, result.latency_ms)
            return order_id
        else:
            await sm.transition(order_id, OrderEvent.REJECT)
            log.error("Order %s rejected: code=%s msg=%s", order_id, result.error_code, result.error_msg)
            return None

    async def close(self, order_id: UUID, ticket: int, volume: float) -> bool:
        sm = await OrderStateMachine.get_instance()
        result = await self._connector.close_order(ticket=ticket, volume=volume)
        if result.success:
            await sm.transition(order_id, OrderEvent.CLOSE, close_price=result.open_price)
            log.info("Order %s closed: ticket=%s", order_id, ticket)
            return True
        else:
            await sm.transition(order_id, OrderEvent.ERROR)
            log.error("Failed to close order %s: %s", order_id, result.error_msg)
            return False
