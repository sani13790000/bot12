"""
backend/execution/mt5_connector.py
Enterprise MT5 Connector — Async HTTP bridge to MetaTrader 5

Environment:
  MT5_HOST      = "127.0.0.1"
  MT5_PORT      = "8765"
  MT5_TIMEOUT   = "10"
  MT5_DEMO_MODE = "true"  (set to "false" for live trading)
"""
from __future__ import annotations

import asyncio, logging, os, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MT5_HOST    = os.environ.get("MT5_HOST",    "127.0.0.1")
MT5_PORT    = int(os.environ.get("MT5_PORT", "8765"))
MT5_TIMEOUT = float(os.environ.get("MT5_TIMEOUT", "10"))
DEMO_MODE   = os.environ.get("MT5_DEMO_MODE", "true").lower() == "true"


class OrderType(str, Enum):
    BUY        = "BUY"
    SELL       = "SELL"
    BUY_LIMIT  = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP   = "BUY_STOP"
    SELL_STOP  = "SELL_STOP"


class MT5Error(Exception):
    """Raised on protocol or trade errors."""


@dataclass
class TradeRequest:
    symbol:     str
    order_type: OrderType
    volume:     float
    price:      Optional[float] = None
    sl:         Optional[float] = None
    tp:         Optional[float] = None
    comment:    str             = ""
    magic:      int             = 20240101
    deviation:  int             = 10


@dataclass
class TradeResult:
    order_id:   int
    symbol:     str
    order_type: OrderType
    volume:     float
    open_price: float
    sl:         Optional[float]
    tp:         Optional[float]
    ts:         float = field(default_factory=time.time)
    demo:       bool  = True


@dataclass
class PositionInfo:
    ticket:        int
    symbol:        str
    order_type:    OrderType
    volume:        float
    open_price:    float
    current_price: float
    profit:        float
    sl:            Optional[float]
    tp:            Optional[float]
    comment:       str
    magic:         int


class MT5Connector:
    """Async connector to the MetaTrader 5 EA HTTP bridge."""

    _RETRY_DELAYS = (1, 2, 4, 8)

    def __init__(self) -> None:
        self._session:   Optional[Any] = None
        self._connected: bool          = False

    async def connect(self) -> None:
        try:
            import aiohttp
        except ImportError:
            raise MT5Error("aiohttp not installed — run: pip install aiohttp")
        if self._session and not self._session.closed:
            return
        self._session   = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=MT5_TIMEOUT)
        )
        self._connected = True
        log.info("MT5Connector: connected (host=%s port=%d demo=%s)", MT5_HOST, MT5_PORT, DEMO_MODE)

    async def disconnect(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False

    async def __aenter__(self) -> "MT5Connector":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    async def _rpc(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if DEMO_MODE:
            return self._demo_response(endpoint, payload)
        if not self._connected:
            await self.connect()
        url, last_err = f"http://{MT5_HOST}:{MT5_PORT}/{endpoint}", None
        for delay in (*self._RETRY_DELAYS, None):
            try:
                async with self._session.post(url, json=payload) as r:
                    r.raise_for_status()
                    return await r.json()
            except Exception as exc:
                last_err = exc
                log.warning("MT5 %s failed: %s", endpoint, exc)
                if delay is not None:
                    await asyncio.sleep(delay)
        raise MT5Error(f"MT5 {endpoint} failed after retries: {last_err}")

    def _demo_response(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        import random
        price = payload.get("price") or round(1.08500 + random.uniform(-0.001, 0.001), 5)
        return {"success": True, "order_id": random.randint(100_000, 999_999),
                "open_price": price, "volume": payload.get("volume", 0.01), "demo": True}

    async def place_order(self, req: TradeRequest) -> TradeResult:
        resp = await self._rpc("trade/open", {
            "symbol": req.symbol, "type": req.order_type.value,
            "volume": req.volume, "price": req.price,
            "sl": req.sl, "tp": req.tp, "comment": req.comment,
            "magic": req.magic, "deviation": req.deviation,
        })
        if not resp.get("success"):
            raise MT5Error(f"place_order failed: {resp.get('error', 'unknown')}")
        return TradeResult(
            order_id=resp["order_id"], symbol=req.symbol,
            order_type=req.order_type, volume=resp.get("volume", req.volume),
            open_price=resp["open_price"], sl=req.sl, tp=req.tp,
            demo=resp.get("demo", DEMO_MODE),
        )

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        payload: Dict[str, Any] = {"ticket": ticket}
        if volume is not None:
            payload["volume"] = volume
        return (await self._rpc("trade/close", payload)).get("success", False)

    async def modify_position(self, ticket: int,
                              sl: Optional[float] = None,
                              tp: Optional[float] = None) -> bool:
        return (await self._rpc("trade/modify", {"ticket": ticket, "sl": sl, "tp": tp})).get("success", False)

    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        resp = await self._rpc("positions/list", {"symbol": symbol} if symbol else {})
        out  = []
        for p in resp.get("positions", []):
            try:
                out.append(PositionInfo(
                    ticket=p["ticket"], symbol=p["symbol"],
                    order_type=OrderType(p["type"]), volume=p["volume"],
                    open_price=p["open_price"],
                    current_price=p.get("current_price", p["open_price"]),
                    profit=p.get("profit", 0.0), sl=p.get("sl"), tp=p.get("tp"),
                    comment=p.get("comment", ""), magic=p.get("magic", 0),
                ))
            except (KeyError, ValueError) as exc:
                log.warning("Skipping malformed position: %s — %s", p, exc)
        return out

    async def get_account_info(self) -> Dict[str, Any]:
        return (await self._rpc("account/info", {})).get("account", {})

    async def ping(self) -> bool:
        try:
            return (await self._rpc("ping", {})).get("pong", False)
        except MT5Error:
            return False


_connector: Optional[MT5Connector] = None


def get_connector() -> MT5Connector:
    global _connector
    if _connector is None:
        _connector = MT5Connector()
    return _connector
