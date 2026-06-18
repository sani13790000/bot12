"""
Galaxy Vast AI Trading Platform
Execution Service — Phase 7

Orchestrates the full order lifecycle:
  1. Receive signal
  2. Risk guard check
  3. Send to MT5 via async connector
  4. Update order state machine
  5. Handle failures via recovery engine
  6. Reconcile positions
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..core.logger import get_logger
from .mt5_connector import MT5Connector, MT5OrderRequest, mt5_connector as _mt5
from .order_state_machine import (
    ManagedOrder,
    OrderState,
    OrderStateMachine,
    order_state_machine as _osm,
)
from .failure_recovery import FailureRecoveryEngine, failure_recovery as _fr
from .position_reconciliation import PositionReconciliation, position_reconciliation as _pr
from .semi_auto import SemiAutoManager

logger = get_logger("execution.execution_service")


class ExecutionService:
    """
    Orchestrates the full execution pipeline:
    Signal -> Risk Check -> MT5 -> State Machine -> Recovery
    """

    def __init__(
        self,
        mt5: Optional[MT5Connector] = None,
        osm: Optional[OrderStateMachine] = None,
        recovery: Optional[FailureRecoveryEngine] = None,
        reconciliation: Optional[PositionReconciliation] = None,
        semi_auto: bool = True,
    ) -> None:
        self._mt5 = mt5 or _mt5
        self._osm = osm or _osm
        self._fr = recovery or _fr
        self._pr = reconciliation or _pr
        self._semi_auto_enabled = semi_auto
        self._semi_auto = SemiAutoManager()
        self._running = False

    async def start(self) -> None:
        """Start all sub-services."""
        await self._mt5.initialize()
        await self._osm.start()
        await self._fr.start()
        await self._pr.start()
        if self._semi_auto_enabled:
            await self._semi_auto.start()
        self._running = True
        logger.info("ExecutionService started")

    async def stop(self) -> None:
        """Stop all sub-services gracefully."""
        self._running = False
        await self._pr.stop()
        await self._fr.stop()
        await self._osm.stop()
        if self._semi_auto_enabled:
            await self._semi_auto.stop()
        await self._mt5.shutdown()
        logger.info("ExecutionService stopped")

    async def execute_signal(
        self, signal: Dict[str, Any], user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: take a signal dict and execute it.
        Returns execution result dict.
        """
        order_id = str(uuid.uuid4())
        signal_id = signal.get("signal_id", order_id)
        symbol = signal.get("symbol", "XAUUSD")
        action = signal.get("action", "")
        volume = float(signal.get("lot_size", 0.01))
        entry = float(signal.get("entry_price", 0.0))
        sl = float(signal.get("stop_loss", 0.0))
        tp = float(signal.get("take_profit_1", 0.0))

        # Create order in state machine
        order = ManagedOrder(
            order_id=order_id,
            signal_id=signal_id,
            symbol=symbol,
            action=action,
            requested_volume=volume,
            requested_price=entry,
            stop_loss=sl,
            take_profit=tp,
        )
        await self._osm.create_order(order)

        # Semi-auto check
        if self._semi_auto_enabled:
            from .semi_auto import PendingSignal
            pending = PendingSignal(
                signal_id=signal_id,
                symbol=symbol,
                action=action,
                entry_price=entry,
                stop_loss=sl,
                take_profit_1=tp,
                lot_size=volume,
            )
            await self._semi_auto.submit_for_approval(pending)
            return {
                "status": "pending_approval",
                "order_id": order_id,
                "signal_id": signal_id,
                "message": "Signal submitted for manual approval",
            }

        return await self._submit_order(order)

    async def execute_approved(
        self, signal_id: str, user_id: int
    ) -> Dict[str, Any]:
        """Execute an approved semi-auto signal immediately."""
        pending = await self._semi_auto.approve_signal(signal_id, user_id)
        if not pending:
            return {"status": "error", "message": "Signal not found or already processed"}

        orders = await self._osm.get_all_orders()
        order = next((o for o in orders if o.signal_id == signal_id), None)
        if not order:
            return {"status": "error", "message": "Order not found in state machine"}

        return await self._submit_order(order)

    async def _submit_order(self, order: ManagedOrder) -> Dict[str, Any]:
        """Submit order to MT5 and handle result."""
        await self._osm.transition(order.order_id, OrderState.SUBMITTED, reason="submitting to MT5")

        mt5_req = MT5OrderRequest(
            symbol=order.symbol,
            action=order.action,
            volume=order.requested_volume,
            price=order.requested_price or None,
            sl=order.stop_loss or None,
            tp=order.take_profit or None,
        )

        result = await self._mt5.send_order(mt5_req)

        if result.success:
            order.mt5_ticket = result.order
            order.mt5_deal = result.deal
            order.filled_volume = result.volume
            order.filled_price = result.price
            await self._osm.transition(
                order.order_id, OrderState.FILLED,
                reason=f"MT5 filled at {result.price}",
                metadata={"ticket": result.order, "deal": result.deal},
            )
            logger.info(
                "Order %s filled: ticket=%s price=%s volume=%s",
                order.order_id[:8], result.order, result.price, result.volume,
            )
            return {
                "status": "filled",
                "order_id": order.order_id,
                "ticket": result.order,
                "price": result.price,
                "volume": result.volume,
            }
        else:
            await self._osm.transition(
                order.order_id, OrderState.REJECTED,
                reason=result.error or "MT5 rejected",
            )
            strategy = await self._fr.handle_failure(
                order_id=order.order_id,
                signal_id=order.signal_id,
                error=result.error or "unknown",
                retcode=result.retcode,
            )
            return {
                "status": "rejected",
                "order_id": order.order_id,
                "error": result.error,
                "retcode": result.retcode,
                "recovery": strategy,
            }

    async def health_check(self) -> Dict[str, Any]:
        mt5_ok = await self._mt5.health_check()
        active_orders = await self._osm.get_active_orders()
        return {
            "mt5_connected": mt5_ok,
            "mt5_status": self._mt5.status,
            "active_orders": len(active_orders),
            "recovery_stats": self._fr.health_stats(),
            "last_reconciliation": (
                self._pr.last_result.timestamp.isoformat()
                if self._pr.last_result else None
            ),
        }


# Singleton
execution_service = ExecutionService()
