"""
backend/execution/execution_service.py
Galaxy Vast AI — Execution Service

وظیفه: دریافت سیگنال از VotingEngine، محاسبه حجم،
       ارسال سفارش به MT5، و مدیریت چرخه عمر order.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .mt5_connector import MT5Connector, MT5Order, OrderType
from .order_state_machine import OrderStateMachine, OrderState

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    max_open_orders:  int   = 5
    default_volume:   float = 0.01
    max_volume:       float = 1.0
    default_sl_pips:  float = 30.0
    default_tp_pips:  float = 60.0
    pip_value:        float = 0.0001
    retry_attempts:   int   = 3
    retry_delay_s:    float = 1.0


class ExecutionService:
    """
    سرویس اجرای معاملات.

    استفاده:
        svc = ExecutionService(connector, config)
        order = await svc.execute_signal({"signal": "BUY", "symbol": "EURUSD", ...})
        await svc.close_all()
    """

    def __init__(self, connector: MT5Connector,
                 config: Optional[ExecutionConfig] = None) -> None:
        self._connector = connector
        self._config    = config or ExecutionConfig()
        self._osm       = OrderStateMachine()
        self._active:   Dict[int, MT5Order] = {}

    async def execute_signal(self, signal: Dict[str, Any]) -> Optional[MT5Order]:
        """
        یک سیگنال معاملاتی را اجرا کن.

        signal باید شامل باشد:
          signal: "BUY" | "SELL"
          symbol: str
          confidence: float (0–100)
          volume, sl_pips, tp_pips: float (اختیاری)
        """
        direction = signal.get("signal", "").upper()
        if direction not in ("BUY", "SELL"):
            logger.warning("[Exec] invalid signal direction: %s", direction)
            return None
        if len(self._active) >= self._config.max_open_orders:
            logger.warning("[Exec] max open orders reached (%d)", self._config.max_open_orders)
            return None

        symbol     = signal.get("symbol", "EURUSD")
        volume     = min(signal.get("volume", self._config.default_volume), self._config.max_volume)
        sl_pips    = signal.get("sl_pips", self._config.default_sl_pips)
        tp_pips    = signal.get("tp_pips", self._config.default_tp_pips)
        order_type = OrderType.BUY if direction == "BUY" else OrderType.SELL

        tick = await self._connector.get_tick(symbol)
        if tick is None:
            logger.error("[Exec] cannot get tick for %s", symbol)
            return None

        pip   = self._config.pip_value
        price = tick.ask if direction == "BUY" else tick.bid
        sl    = price - sl_pips * pip if direction == "BUY" else price + sl_pips * pip
        tp    = price + tp_pips * pip if direction == "BUY" else price - tp_pips * pip

        order = await self._place_with_retry(symbol, order_type, volume, price, sl, tp)
        if order:
            self._active[order.ticket] = order
            self._osm.transition(order.ticket, OrderState.FILLED)
            logger.info("[Exec] %s %s %.2f @ %.5f SL=%.5f TP=%.5f",
                        direction, symbol, volume, price, sl, tp)
        return order

    async def close_all(self) -> int:
        """همه position‌های باز را ببند."""
        closed = 0
        for ticket in list(self._active.keys()):
            if await self._connector.close_order(ticket):
                del self._active[ticket]
                self._osm.transition(ticket, OrderState.CLOSED)
                closed += 1
        return closed

    async def close_order(self, ticket: int) -> bool:
        """یک position خاص را ببند."""
        ok = await self._connector.close_order(ticket)
        if ok:
            self._active.pop(ticket, None)
            self._osm.transition(ticket, OrderState.CLOSED)
        return ok

    def get_active_orders(self) -> List[MT5Order]:
        return list(self._active.values())

    async def _place_with_retry(self, symbol: str, order_type: OrderType,
                                 volume: float, price: float,
                                 sl: float, tp: float) -> Optional[MT5Order]:
        """ارسال سفارش با retry."""
        for attempt in range(1, self._config.retry_attempts + 1):
            order = await self._connector.place_order(
                symbol=symbol, order_type=order_type,
                volume=volume, price=price, sl=sl, tp=tp,
            )
            if order:
                return order
            logger.warning("[Exec] place_order attempt %d/%d failed",
                           attempt, self._config.retry_attempts)
            if attempt < self._config.retry_attempts:
                await asyncio.sleep(self._config.retry_delay_s)
        return None
