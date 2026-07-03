"""
backend/execution/mt5_connector.py
Galaxy Vast AI — MT5 Connector (async)

اتصال به MetaTrader 5 از طریق Python package یا demo simulation.
همه متدها async هستند تا event loop بلاک نشود.

demo_mode=True  → شبیه‌سازی کامل، بدون نیاز به MT5 نصب‌شده.
demo_mode=False → استفاده از MetaTrader5 Python package.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderType(Enum):
    BUY        = "buy"
    SELL       = "sell"
    BUY_LIMIT  = "buy_limit"
    SELL_LIMIT = "sell_limit"
    BUY_STOP   = "buy_stop"
    SELL_STOP  = "sell_stop"


class OrderStatus(Enum):
    PENDING   = auto()
    FILLED    = auto()
    PARTIAL   = auto()
    CANCELLED = auto()
    REJECTED  = auto()
    CLOSED    = auto()


@dataclass
class MT5Order:
    ticket:     int
    symbol:     str
    order_type: OrderType
    volume:     float
    price:      float
    sl:         float        = 0.0
    tp:         float        = 0.0
    status:     OrderStatus  = OrderStatus.PENDING
    open_time:  datetime     = field(default_factory=lambda: datetime.now(timezone.utc))
    close_time: Optional[datetime] = None
    profit:     float        = 0.0
    comment:    str          = ""


@dataclass
class Tick:
    symbol: str
    bid:    float
    ask:    float
    time:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 5)

    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2, 5)


class MT5Connector:
    """
    Async connector به MetaTrader 5.
    demo_mode=True  → شبیه‌سازی کامل
    demo_mode=False → MetaTrader5 Python package
    """

    def __init__(self, host: str = "localhost", port: int = 8080,
                 demo_mode: bool = True, timeout_s: float = 10.0) -> None:
        self._host      = host
        self._port      = port
        self._demo      = demo_mode
        self._timeout   = timeout_s
        self._connected = False
        self._orders:   Dict[int, MT5Order] = {}
        logger.info("[MT5] init host=%s:%d demo=%s", host, port, demo_mode)

    async def connect(self) -> bool:
        if self._connected:
            return True
        if self._demo:
            self._connected = True
            logger.info("[MT5] Demo mode active")
            return True
        try:
            import MetaTrader5 as mt5  # type: ignore
            ok = await asyncio.get_event_loop().run_in_executor(None, mt5.initialize)
            self._connected = bool(ok)
            if not ok:
                logger.error("[MT5] init failed: %s", mt5.last_error())
        except ImportError:
            logger.warning("[MT5] MT5 package missing — switching to demo")
            self._demo = self._connected = True
        except Exception as exc:
            logger.error("[MT5] connect: %s", exc)
        return self._connected

    async def disconnect(self) -> None:
        if not self._connected:
            return
        if not self._demo:
            try:
                import MetaTrader5 as mt5  # type: ignore
                await asyncio.get_event_loop().run_in_executor(None, mt5.shutdown)
            except Exception as exc:
                logger.warning("[MT5] disconnect: %s", exc)
        self._connected = False
        logger.info("[MT5] disconnected")

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self._connected:
            return None
        if self._demo:
            import random
            base = {"EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 148.50}.get(symbol, 1.0)
            bid  = round(base + random.uniform(-0.0005, 0.0005), 5)
            return Tick(symbol=symbol, bid=bid, ask=round(bid + 0.0001, 5))
        try:
            import MetaTrader5 as mt5  # type: ignore
            t = await asyncio.get_event_loop().run_in_executor(None, mt5.symbol_info_tick, symbol)
            return Tick(symbol=symbol, bid=t.bid, ask=t.ask) if t else None
        except Exception as exc:
            logger.error("[MT5] get_tick %s: %s", symbol, exc)
            return None

    async def get_ohlcv(self, symbol: str, timeframe: str = "H1",
                        count: int = 100) -> List[Dict[str, Any]]:
        if not self._connected or self._demo:
            import random
            price, bars = 1.0850, []
            for _ in range(count):
                o = price
                h = o + random.uniform(0, 0.002)
                lo = o - random.uniform(0, 0.002)
                c = random.uniform(lo, h)
                bars.append({"open": o, "high": h, "low": lo, "close": c,
                              "volume": random.randint(100, 1000)})
                price = c
            return bars
        return []

    async def place_order(self, symbol: str, order_type: OrderType, volume: float,
                          price: float = 0.0, sl: float = 0.0, tp: float = 0.0,
                          comment: str = "") -> Optional[MT5Order]:
        if not self._connected:
            logger.error("[MT5] not connected")
            return None
        if price == 0.0:
            tick = await self.get_tick(symbol)
            if tick is None:
                return None
            price = tick.ask if "buy" in order_type.value else tick.bid
        ticket = int(time.time() * 1000) % 1_000_000
        order  = MT5Order(ticket=ticket, symbol=symbol, order_type=order_type,
                          volume=volume, price=price, sl=sl, tp=tp,
                          status=OrderStatus.FILLED, comment=comment)
        if not self._demo:
            try:
                import MetaTrader5 as mt5  # type: ignore
                req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
                       "volume": volume, "price": price, "sl": sl, "tp": tp,
                       "comment": comment, "type_filling": mt5.ORDER_FILLING_IOC,
                       "type": mt5.ORDER_TYPE_BUY if order_type == OrderType.BUY else mt5.ORDER_TYPE_SELL}
                res = await asyncio.get_event_loop().run_in_executor(None, mt5.order_send, req)
                if res.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error("[MT5] order_send retcode=%d", res.retcode)
                    return None
                order.ticket = res.order
            except Exception as exc:
                logger.error("[MT5] place_order: %s", exc)
                return None
        self._orders[order.ticket] = order
        logger.info("[MT5] placed ticket=%d %s %s %.2f@%.5f",
                    order.ticket, symbol, order_type.value, volume, price)
        return order

    async def close_order(self, ticket: int) -> bool:
        order = self._orders.get(ticket)
        if not order:
            logger.warning("[MT5] close ticket %d not found", ticket)
            return False
        if self._demo:
            order.status = OrderStatus.CLOSED
            order.close_time = datetime.now(timezone.utc)
            return True
        try:
            import MetaTrader5 as mt5  # type: ignore
            tick = await self.get_tick(order.symbol)
            if not tick:
                return False
            cp  = tick.bid if order.order_type == OrderType.BUY else tick.ask
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": order.symbol,
                   "volume": order.volume, "position": ticket, "price": cp,
                   "type": mt5.ORDER_TYPE_SELL if order.order_type == OrderType.BUY else mt5.ORDER_TYPE_BUY}
            res = await asyncio.get_event_loop().run_in_executor(None, mt5.order_send, req)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                order.status = OrderStatus.CLOSED
                order.close_time = datetime.now(timezone.utc)
                return True
            return False
        except Exception as exc:
            logger.error("[MT5] close_order: %s", exc)
            return False

    async def modify_order(self, ticket: int, sl: float = 0.0, tp: float = 0.0) -> bool:
        order = self._orders.get(ticket)
        if not order:
            return False
        order.sl, order.tp = sl, tp
        return True

    def get_open_orders(self) -> List[MT5Order]:
        return [o for o in self._orders.values() if o.status == OrderStatus.FILLED]

    @property
    def is_connected(self) -> bool:
        return self._connected
