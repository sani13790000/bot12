"""
backend/execution/execution_service.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
High-level trade execution service.

Responsibilities
----------------
- Accept a TradeSignal from the decision layer.
- Run pre-flight risk checks (kill-switch, lot sizing).
- Delegate the actual order placement to MT5Connector.
- Advance the order through OrderStateMachine.
- Persist results to Supabase via the database client.

Usage::

    svc = ExecutionService()
    await svc.execute(signal)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────── #


@dataclass
class TradeSignal:
    """Minimal signal that ExecutionService needs to place a trade."""
    symbol:     str
    direction:  str           # "BUY" | "SELL"
    volume:     float
    entry:      Optional[float] = None
    sl:         Optional[float] = None
    tp:         Optional[float] = None
    strategy:   str = "unknown"
    confidence: float = 0.0
    meta:       Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Outcome of an execution attempt."""
    success:    bool
    ticket:     Optional[int]  = None
    open_price: Optional[float] = None
    error:      Optional[str]  = None
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Service ───────────────────────────────────────────────────────────────── #


class ExecutionService:
    """
    Orchestrates the full life-cycle of a trade order.

    The service is intentionally dependency-light so it can be unit-tested
    without a live MT5 connection.  Pass custom connector / state-machine
    instances for testing.
    """

    def __init__(
        self,
        connector:     Any = None,   # MT5Connector
        state_machine: Any = None,   # OrderStateMachine
        db_client:     Any = None,   # SupabaseClient
        kill_switch:   Any = None,   # KillSwitch
    ) -> None:
        # Lazy imports to avoid circular dependencies at module load time
        if connector is None:
            from backend.execution.mt5_connector import mt5_connector
            connector = mt5_connector
        if state_machine is None:
            from backend.execution.order_state_machine import order_state_machine
            state_machine = order_state_machine

        self._connector     = connector
        self._state_machine = state_machine
        self._db            = db_client
        self._kill_switch   = kill_switch

    # ── Public API ───────────────────────────────────────────────────────── #

    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        """
        Execute a trade signal end-to-end.

        Flow
        ----
        1. Kill-switch check.
        2. Volume validation.
        3. Place order via MT5Connector.
        4. Advance state machine to OPEN.
        5. Persist to database.

        Returns ExecutionResult with success=True and the ticket on success,
        or success=False with an error message on any failure.
        """
        logger.info(
            "[ExecutionService] execute %s %s vol=%.2f conf=%.2f",
            signal.direction, signal.symbol, signal.volume, signal.confidence,
        )

        # 1. Kill-switch guard
        if self._kill_switch is not None:
            if self._kill_switch.is_active():
                logger.warning("[ExecutionService] kill-switch ACTIVE — aborting")
                return ExecutionResult(success=False, error="kill_switch_active")

        # 2. Volume sanity check
        if signal.volume <= 0:
            return ExecutionResult(success=False, error="invalid_volume")

        # 3. Place order
        try:
            order = await self._connector.place_order(
                symbol=signal.symbol,
                direction=signal.direction,
                volume=signal.volume,
                sl=signal.sl,
                tp=signal.tp,
            )
        except Exception as exc:
            logger.error("[ExecutionService] place_order failed: %s", exc)
            return ExecutionResult(success=False, error=str(exc))

        # 4. Advance state machine
        try:
            self._state_machine.transition(order.ticket, "OPEN")
        except Exception as exc:
            logger.warning("[ExecutionService] state machine error: %s", exc)

        # 5. Persist (best-effort)
        await self._persist(signal, order)

        logger.info(
            "[ExecutionService] order OPEN ticket=%d price=%.5f",
            order.ticket, order.open_price,
        )
        return ExecutionResult(
            success=True,
            ticket=order.ticket,
            open_price=order.open_price,
        )

    async def close(self, ticket: int) -> ExecutionResult:
        """Close an open position and advance its state to CLOSED."""
        try:
            closed = await self._connector.close_position(ticket)
            if closed:
                self._state_machine.transition(ticket, "CLOSED")
                logger.info("[ExecutionService] ticket=%d CLOSED", ticket)
                return ExecutionResult(success=True, ticket=ticket)
            return ExecutionResult(success=False, error="position_not_found")
        except Exception as exc:
            logger.error("[ExecutionService] close ticket=%d failed: %s", ticket, exc)
            return ExecutionResult(success=False, error=str(exc))

    # ── Internals ─────────────────────────────────────────────────────────── #

    async def _persist(self, signal: TradeSignal, order: Any) -> None:
        """Write execution record to the database (failure is non-fatal)."""
        if self._db is None:
            return
        try:
            await self._db.insert("executions", {
                "ticket":    order.ticket,
                "symbol":    signal.symbol,
                "direction": signal.direction,
                "volume":    signal.volume,
                "strategy":  signal.strategy,
                "confidence": signal.confidence,
            })
        except Exception as exc:
            logger.warning("[ExecutionService] DB persist failed (non-fatal): %s", exc)


# ── Module-level singleton ────────────────────────────────────────────────── #
execution_service = ExecutionService()
