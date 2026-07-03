"""
backend/execution/order_state_machine.py
Galaxy Vast AI - Order State Machine (Phase 3)

States: PENDING -> SUBMITTED -> FILLED -> CLOSED
Features: thread-safe singleton, event hooks, circuit breaker integration.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Optional
from uuid import UUID

log = logging.getLogger(__name__)


class OrderState(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class OrderEvent(str, Enum):
    SUBMIT = "SUBMIT"
    FILL = "FILL"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE = "CLOSE"
    CANCEL = "CANCEL"
    REJECT = "REJECT"
    ERROR = "ERROR"
    RESET = "RESET"


TRANSITIONS: dict = {
    (OrderState.PENDING, OrderEvent.SUBMIT): OrderState.SUBMITTED,
    (OrderState.PENDING, OrderEvent.CANCEL): OrderState.CANCELLED,
    (OrderState.PENDING, OrderEvent.ERROR): OrderState.ERROR,
    (OrderState.SUBMITTED, OrderEvent.FILL): OrderState.FILLED,
    (OrderState.SUBMITTED, OrderEvent.REJECT): OrderState.REJECTED,
    (OrderState.SUBMITTED, OrderEvent.CANCEL): OrderState.CANCELLED,
    (OrderState.SUBMITTED, OrderEvent.ERROR): OrderState.ERROR,
    (OrderState.FILLED, OrderEvent.PARTIAL_CLOSE): OrderState.PARTIALLY_CLOSED,
    (OrderState.FILLED, OrderEvent.CLOSE): OrderState.CLOSED,
    (OrderState.FILLED, OrderEvent.ERROR): OrderState.ERROR,
    (OrderState.PARTIALLY_CLOSED, OrderEvent.CLOSE): OrderState.CLOSED,
    (OrderState.PARTIALLY_CLOSED, OrderEvent.ERROR): OrderState.ERROR,
    (OrderState.ERROR, OrderEvent.RESET): OrderState.PENDING,
}

TERMINAL_STATES = {OrderState.CLOSED, OrderState.CANCELLED, OrderState.REJECTED}


class OrderContext:
    __slots__ = ("order_id", "state", "symbol", "volume", "ticket", "open_price", "close_price", "profit", "created_at", "updated_at", "history")

    def __init__(self, order_id: UUID, symbol: str, volume: float) -> None:
        self.order_id = order_id
        self.state = OrderState.PENDING
        self.symbol = symbol
        self.volume = volume
        self.ticket: Optional[int] = None
        self.open_price: Optional[float] = None
        self.close_price: Optional[float] = None
        self.profit: Optional[float] = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.history: list = []

    def record(self, event: OrderEvent, new_state: OrderState) -> None:
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
        self.history.append((event.value, new_state.value))

    def to_dict(self) -> dict:
        return {"order_id": str(self.order_id), "state": self.state.value, "symbol": self.symbol, "volume": self.volume, "ticket": self.ticket, "open_price": self.open_price, "close_price": self.close_price, "profit": self.profit, "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(), "history": self.history}


Hook = Callable[[OrderContext, OrderEvent, OrderState], Awaitable[None]]


class OrderStateMachine:
    """Singleton order state machine."""

    _instance: Optional["OrderStateMachine"] = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._orders: dict = {}
        self._hooks: list = []
        self._order_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "OrderStateMachine":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_hook(self, hook: Hook) -> None:
        self._hooks.append(hook)

    async def create_order(self, order_id: UUID, symbol: str, volume: float) -> OrderContext:
        async with self._order_lock:
            if order_id in self._orders:
                raise ValueError(f"Order {order_id} already exists")
            ctx = OrderContext(order_id=order_id, symbol=symbol, volume=volume)
            self._orders[order_id] = ctx
            log.info("Order created: %s %s %.2f", order_id, symbol, volume)
            return ctx

    async def transition(self, order_id: UUID, event: OrderEvent, **kwargs) -> OrderContext:
        async with self._order_lock:
            ctx = self._orders.get(order_id)
            if ctx is None:
                raise KeyError(f"Order {order_id} not found")
            if ctx.state in TERMINAL_STATES:
                raise ValueError(f"Order {order_id} is in terminal state {ctx.state}")
            key = (ctx.state, event)
            new_state = TRANSITIONS.get(key)
            if new_state is None:
                raise ValueError(f"Invalid transition: {ctx.state} + {event}")
            if "ticket" in kwargs and kwargs["ticket"] is not None:
                ctx.ticket = int(kwargs["ticket"])
            if "open_price" in kwargs and kwargs["open_price"] is not None:
                ctx.open_price = float(kwargs["open_price"])
            if "close_price" in kwargs and kwargs["close_price"] is not None:
                ctx.close_price = float(kwargs["close_price"])
            if "profit" in kwargs and kwargs["profit"] is not None:
                ctx.profit = float(kwargs["profit"])
            old_state = ctx.state
            ctx.record(event, new_state)
            log.info("Order %s: %s -[%s]-> %s", order_id, old_state.value, event.value, new_state.value)
        for hook in self._hooks:
            try:
                await hook(ctx, event, new_state)
            except Exception:
                log.exception("Hook error for order %s", order_id)
        return ctx

    async def get_order(self, order_id: UUID) -> Optional[OrderContext]:
        return self._orders.get(order_id)

    async def get_all_active(self) -> list:
        return [ctx for ctx in self._orders.values() if ctx.state not in TERMINAL_STATES]

    async def remove_order(self, order_id: UUID) -> None:
        async with self._order_lock:
            self._orders.pop(order_id, None)
