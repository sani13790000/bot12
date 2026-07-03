"""
backend/execution/execution_service.py
Galaxy Vast AI — Execution Service

Routes orders from decision engine to MT5 connector.
Handles retry, timeout, and failure recovery.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .mt5_connector import MT5Connector, MT5Order, MT5Result
from .order_state_machine import (
    OrderStateMachine,
    OrderStatus,
    get_order_state_machine,
)
from .order_journal import OrderJournal
from ..core.logger import get_logger
from ..risk.kill_switch import KillSwitch

logger = get_logger("execution.execution_service")


@dataclass
class ExecutionConfig:
    max_retries:     int   = 3
    retry_delay_s:   float = 1.0
    timeout_s:       float = 30.0
    enable_dry_run:  bool  = False


@dataclass
class ExecutionResult:
    success:   bool
    ticket:    Optional[int]   = None
    price:     Optional[float] = None
    volume:    Optional[float] = None
    error:     Optional[str]   = None
    retries:   int             = 0
    latency_ms: float          = 0.0


class ExecutionService:
    """Routes trading signals to MT5 and manages order lifecycle."""

    def __init__(
        self,
        config:     Optional[ExecutionConfig] = None,
        connector:  Optional[MT5Connector]    = None,
        kill_switch: Optional[KillSwitch]     = None,
    ):
        self._config     = config      or ExecutionConfig()
        self._connector  = connector   or MT5Connector()
        self._kill_switch = kill_switch or KillSwitch()
        self._journal    = OrderJournal()
        self._osm:       Optional[OrderStateMachine] = None

    async def _get_osm(self) -> OrderStateMachine:
        if self._osm is None:
            self._osm = await get_order_state_machine()
        return self._osm

    async def execute(
        self,
        symbol:    str,
        direction: str,
        volume:    float,
        price:     float,
        sl:        Optional[float] = None,
        tp:        Optional[float] = None,
        order_id:  Optional[str]   = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute a trade order."""
        # Kill switch check
        if self._kill_switch.is_triggered:
            return ExecutionResult(
                success=False,
                error="Kill switch active — all trading blocked"
            )

        if self._config.enable_dry_run:
            logger.info(f"DRY RUN: {direction} {volume} {symbol} @ {price}")
            return ExecutionResult(success=True, price=price, volume=volume)

        import uuid
        oid = order_id or str(uuid.uuid4())
        osm = await self._get_osm()

        # Create order in state machine
        order = await osm.create_order(
            order_id  = oid,
            symbol    = symbol,
            direction = direction,
            volume    = volume,
            price     = price,
        )

        t0 = time.perf_counter()
        last_error = ""

        for attempt in range(self._config.max_retries):
            try:
                await osm.transition(oid, OrderStatus.SUBMITTED)
                result = await asyncio.wait_for(
                    self._connector.place_order(MT5Order(
                        symbol    = symbol,
                        direction = direction,
                        volume    = volume,
                        price     = price,
                        sl        = sl,
                        tp        = tp,
                    )),
                    timeout=self._config.timeout_s
                )

                if result.success:
                    await osm.transition(
                        oid, OrderStatus.FILLED,
                        filled_price  = result.price,
                        filled_volume = result.volume,
                        ticket        = result.ticket,
                    )
                    await self._journal.log_fill(order, result)
                    return ExecutionResult(
                        success    = True,
                        ticket     = result.ticket,
                        price      = result.price,
                        volume     = result.volume,
                        retries    = attempt,
                        latency_ms = (time.perf_counter() - t0) * 1000,
                    )
                else:
                    last_error = result.error or "unknown"
                    await asyncio.sleep(self._config.retry_delay_s)

            except asyncio.TimeoutError:
                last_error = f"timeout after {self._config.timeout_s}s"
                logger.warning(f"Execute timeout attempt {attempt+1}: {oid}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Execute error attempt {attempt+1}: {e}")

        await osm.transition(oid, OrderStatus.REJECTED, reason=last_error)
        return ExecutionResult(
            success = False,
            error   = last_error,
            retries = self._config.max_retries,
        )

    async def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float,
    ) -> ExecutionResult:
        """Close an existing position."""
        if self._kill_switch.is_triggered:
            return ExecutionResult(success=False, error="Kill switch active")

        try:
            result = await asyncio.wait_for(
                self._connector.close_position(ticket, symbol, volume),
                timeout=self._config.timeout_s
            )
            return ExecutionResult(
                success = result.success,
                ticket  = ticket,
                error   = result.error,
            )
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))

    async def health_check(self) -> Dict[str, Any]:
        """Check execution service health."""
        connected = await self._connector.is_connected()
        return {
            "status":      "ok" if connected else "degraded",
            "mt5_connected": connected,
            "dry_run":     self._config.enable_dry_run,
            "kill_switch": self._kill_switch.is_triggered,
        }


_service: Optional[ExecutionService] = None


def get_execution_service() -> ExecutionService:
    global _service
    if _service is None:
        _service = ExecutionService()
    return _service
