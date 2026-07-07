"""
backend/execution/execution_service.py
Galaxy Vast AI Trading Platform

High-level trade execution service.

A3-FIX: Replaced eager module-level singleton `execution_service = ExecutionService()`
         with a lazy proxy. The old pattern triggered MT5 connection on every import.
         New pattern: connection is established only on first actual use.

FIX K-1: open_position() alias for routes/trades.py compatibility.
FIX K-2: retry with exponential backoff max 3 attempts.
FIX K-3: circuit breaker integration.
FIX K-4: Telegram alert on permanent order failure.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # exponential: 1, 2, 4


@dataclass
class TradeSignal:
    """Minimal signal that ExecutionService needs to place a trade."""

    symbol: str
    direction: str  # "BUY" | "SELL"
    volume: float
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    strategy: str = "unknown"
    confidence: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Outcome of an execution attempt."""

    success: bool
    ticket: Optional[int] = None
    open_price: Optional[float] = None
    error: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExecutionService:
    """
    Orchestrates the full life-cycle of a trade order.

    The service is dependency-light so it can be unit-tested
    without a live MT5 connection. Pass custom connector / state-machine
    instances for testing.
    """

    def __init__(
        self,
        connector: Any = None,
        state_machine: Any = None,
        db_client: Any = None,
        kill_switch: Any = None,
        notifier: Any = None,
    ) -> None:
        if connector is None:
            from backend.execution.mt5_connector import mt5_connector

            connector = mt5_connector
        if state_machine is None:
            from backend.execution.order_state_machine import order_state_machine

            state_machine = order_state_machine

        self._connector = connector
        self._state_machine = state_machine
        self._db = db_client
        self._kill_switch = kill_switch
        self._notifier = notifier

    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a trade signal end-to-end with retry and alerting."""
        logger.info(
            "[ExecutionService] execute %s %s vol=%.2f conf=%.2f",
            signal.direction,
            signal.symbol,
            signal.volume,
            signal.confidence,
        )

        if self._kill_switch is not None:
            if self._kill_switch.is_active():
                logger.warning("[ExecutionService] kill-switch ACTIVE")
                return ExecutionResult(success=False, error="kill_switch_active")

        if signal.volume <= 0:
            return ExecutionResult(success=False, error="invalid_volume")

        order = None
        last_error: Optional[str] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                order = await self._connector.place_order(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    volume=signal.volume,
                    sl=signal.sl,
                    tp=signal.tp,
                )
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "[ExecutionService] place_order attempt %d/%d failed: %s --retry in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "[ExecutionService] place_order FAILED after %d attempts: %s",
                        _MAX_RETRIES,
                        exc,
                    )
                    await self._send_failure_alert(signal, last_error)
                    return ExecutionResult(success=False, error=last_error)

        if order is None:
            return ExecutionResult(success=False, error=last_error or "unknown")

        try:
            self._state_machine.transition(order.ticket, "OPEN")
        except Exception as exc:
            logger.warning("[ExecutionService] state machine error: %s", exc)

        await self._persist(signal, order)

        logger.info(
            "[ExecutionService] order OPEN ticket=%d price=%.5f",
            order.ticket,
            order.open_price,
        )
        return ExecutionResult(
            success=True,
            ticket=order.ticket,
            open_price=order.open_price,
        )

    async def open_position(self, signal: TradeSignal) -> ExecutionResult:
        """FIX K-1: alias for execute() used by API routes."""
        return await self.execute(signal)

    async def close(self, ticket: int) -> ExecutionResult:
        """Close an open position and advance its state to CLOSED."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                closed = await self._connector.close_position(ticket)
                if closed:
                    self._state_machine.transition(ticket, "CLOSED")
                    logger.info("[ExecutionService] ticket=%d CLOSED", ticket)
                    return ExecutionResult(success=True, ticket=ticket)
                return ExecutionResult(success=False, error="position_not_found")
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "[ExecutionService] close attempt %d/%d failed: %s --retry in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("[ExecutionService] close ticket=%d FAILED: %s", ticket, exc)
                    return ExecutionResult(success=False, error=str(exc))
        return ExecutionResult(success=False, error="max_retries_exceeded")

    async def close_position(self, ticket: int) -> ExecutionResult:
        """Alias for close() — used by API routes."""
        return await self.close(ticket)

    async def _persist(self, signal: TradeSignal, order: Any) -> None:
        """Write execution record to the database; failure is non-fatal."""
        if self._db is None:
            return
        try:
            await self._db.insert(
                "executions",
                {
                    "ticket": order.ticket,
                    "symbol": signal.symbol,
                    "direction": signal.direction,
                    "volume": signal.volume,
                    "strategy": signal.strategy,
                    "confidence": signal.confidence,
                },
            )
        except Exception as exc:
            logger.warning("[ExecutionService] DB persist failed non-fatal: %s", exc)

    async def _send_failure_alert(self, signal: TradeSignal, error: str) -> None:
        """FIX K-4: send Telegram alert if order fails permanently."""
        if self._notifier is None:
            try:
                from backend.telegram.notifier import get_notifier

                self._notifier = get_notifier()
            except Exception:
                logger.warning("[ExecutionService] notifier unavailable")
                return
        try:
            msg = (
                f"\u2628\ufe0f *Order Failed*\n"
                f"Symbol: `{signal.symbol}`\n"
                f"Direction: `{signal.direction}`\n"
                f"Volume: `{signal.volume}`\n"
                f"Error: `{error}`\n"
                f"After {_MAX_RETRIES} retries."
            )
            await self._notifier.send(msg)
        except Exception as exc:
            logger.warning("[ExecutionService] Telegram alert failed: %s", exc)


# A3-FIX: lazy singleton — avoids MT5 connect on every import
_execution_service_instance: "ExecutionService | None" = None


class _LazyProxy:
    """Transparent proxy; initialises ExecutionService on first attribute access."""

    def __getattr__(self, name: str):  # type: ignore[override]
        global _execution_service_instance
        if _execution_service_instance is None:
            _execution_service_instance = ExecutionService()
        return getattr(_execution_service_instance, name)

    def __repr__(self) -> str:
        global _execution_service_instance
        if _execution_service_instance is None:
            return "<ExecutionService: not yet initialised>"
        return repr(_execution_service_instance)


execution_service = _LazyProxy()  # type: ignore[assignment]
