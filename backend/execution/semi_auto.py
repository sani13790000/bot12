"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Automatic Trade Execution Handler

Receives confirmed signals from the Telegram bot and executes them
through the MT5 connector with full risk checks.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SemiAutoSignal:
    """Signal approved by the trader for semi-auto execution."""
    signal_id:        str
    symbol:           str
    action:           str          # "buy" | "sell"
    entry_price:      float
    stop_loss:        float
    take_profit_1:    float
    take_profit_2:    float
    lot_size:         float
    risk_percent:     float
    rr_ratio:         float
    confidence_score: float
    market_context:   str          = ""
    remaining_seconds: int         = 60
    approved_by:      Optional[str] = None
    approved_at:      Optional[str] = None


class SemiAutoHandler:
    """
    Handles the lifecycle of semi-automatic trades:
    1. Receive approved signal from Telegram callback.
    2. Run risk pre-flight.
    3. Execute via MT5Connector.
    4. Track state via OrderStateMachine.
    """

    def __init__(
        self,
        connector:     Any = None,
        risk_manager:  Any = None,
        state_machine: Any = None,
    ) -> None:
        self._connector    = connector
        self._risk         = risk_manager
        self._sm           = state_machine

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    async def execute(self, signal: SemiAutoSignal) -> Dict[str, Any]:
        """
        Execute an approved semi-auto signal.
        Returns a result dict with keys: success, ticket, error.
        """
        logger.info(
            "[SemiAuto] executing signal %s %s %s lot=%.2f",
            signal.signal_id, signal.symbol, signal.action, signal.lot_size,
        )

        # 1. Risk pre-flight
        if self._risk:
            risk_result = await self._risk.check({
                "symbol":       signal.symbol,
                "direction":    signal.action,
                "lot_size":     signal.lot_size,
                "risk_percent": signal.risk_percent,
            }, {})
            if not risk_result.get("approved"):
                reason = risk_result.get("reason", "risk check failed")
                logger.warning("[SemiAuto] risk blocked %s: %s", signal.signal_id, reason)
                return {"success": False, "ticket": None, "error": reason}

        # 2. Execute
        if self._connector is None:
            return {"success": False, "ticket": None, "error": "no MT5 connector"}

        try:
            order_type = "ORDER_TYPE_BUY" if signal.action == "buy" else "ORDER_TYPE_SELL"
            result = await self._connector.place_order(
                symbol     = signal.symbol,
                order_type = order_type,
                volume     = signal.lot_size,
                price      = signal.entry_price,
                sl         = signal.stop_loss,
                tp         = signal.take_profit_1,
                comment    = f"semi_auto:{signal.signal_id[:8]}",
            )
            ticket = result.get("ticket")
            logger.info("[SemiAuto] placed ticket=%s for %s", ticket, signal.signal_id)

            # 3. State machine tracking
            if self._sm and ticket:
                await self._sm.transition(str(ticket), "submit")

            return {"success": True, "ticket": ticket, "error": None}

        except Exception as exc:
            logger.error("[SemiAuto] execution error for %s: %s", signal.signal_id, exc)
            return {"success": False, "ticket": None, "error": str(exc)}

    async def reject(self, signal_id: str, reason: str = "") -> None:
        """Mark a signal as rejected (no execution)."""
        logger.info("[SemiAuto] signal rejected: %s reason=%s", signal_id, reason)


# Module-level singleton
semi_auto_handler = SemiAutoHandler()
