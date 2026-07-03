"""
backend/execution/mt5_connector.py
MT5 Connector — async bridge to MetaTrader 5 terminal via HTTP bridge.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional
from ..core.logger import get_logger

logger = get_logger("execution.mt5_connector")


class MT5ConnectionError(RuntimeError):
    pass


class MT5Order:
    def __init__(self, ticket: int, symbol: str, side: str, volume: float, price: float, sl: float = 0.0, tp: float = 0.0, comment: str = "") -> None:
        self.ticket = ticket
        self.symbol = symbol
        self.side = side
        self.volume = volume
        self.price = price
        self.sl = sl
        self.tp = tp
        self.comment = comment

    def to_dict(self) -> Dict[str, Any]:
        return vars(self)


class MT5Connector:
    """Async connector to MetaTrader 5. Supports demo mode for testing."""

    def __init__(self, host: str = "localhost", port: int = 5555, timeout: float = 10.0, demo: bool = False) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._demo = demo
        self._session: Optional[Any] = None
        self._log = logger

    async def connect(self) -> None:
        if self._demo:
            self._log.info("MT5Connector: demo mode")
            return
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                base_url=f"http://{self._host}:{self._port}",
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            )
            await self._health_check()
            self._log.info("MT5Connector: connected to %s:%d", self._host, self._port)
        except Exception as exc:
            raise MT5ConnectionError(f"Cannot connect to MT5: {exc}") from exc

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _health_check(self) -> None:
        if not self._session:
            return
        async with self._session.get("/health") as resp:
            if resp.status != 200:
                raise MT5ConnectionError(f"MT5 health check failed: {resp.status}")

    async def get_account_info(self) -> Dict[str, Any]:
        if self._demo:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        return await self._get("/account")

    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        if self._demo:
            return {"symbol": symbol, "bid": 1.1000, "ask": 1.1002, "point": 0.0001, "digits": 5}
        return await self._get("/symbol", params={"symbol": symbol})

    async def get_tick(self, symbol: str) -> Dict[str, float]:
        if self._demo:
            return {"bid": 1.1000, "ask": 1.1002, "last": 1.1001, "time": 0}
        return await self._get("/tick", params={"symbol": symbol})

    async def place_order(self, symbol: str, side: str, volume: float, price: float = 0.0, sl: float = 0.0, tp: float = 0.0, comment: str = "") -> MT5Order:
        if self._demo:
            import random
            ticket = random.randint(100000, 999999)
            self._log.info("DEMO order: %s %s %.2f @ %.5f [ticket=%d]", side, symbol, volume, price, ticket)
            return MT5Order(ticket, symbol, side, volume, price, sl, tp, comment)
        payload = {"symbol": symbol, "side": side, "volume": volume, "price": price, "sl": sl, "tp": tp, "comment": comment}
        data = await self._post("/order/place", payload)
        return MT5Order(ticket=data["ticket"], symbol=symbol, side=side, volume=float(data.get("volume", volume)), price=float(data.get("price", price)), sl=sl, tp=tp, comment=comment)

    async def close_order(self, ticket: int, volume: Optional[float] = None) -> Dict[str, Any]:
        if self._demo:
            return {"ticket": ticket, "status": "closed"}
        return await self._post("/order/close", {"ticket": ticket, "volume": volume})

    async def modify_order(self, ticket: int, sl: float = 0.0, tp: float = 0.0) -> Dict[str, Any]:
        if self._demo:
            return {"ticket": ticket, "sl": sl, "tp": tp}
        return await self._post("/order/modify", {"ticket": ticket, "sl": sl, "tp": tp})

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        if self._demo:
            return []
        return await self._get("/positions")

    async def get_history(self, from_ts: float, to_ts: float) -> List[Dict[str, Any]]:
        if self._demo:
            return []
        return await self._get("/history", params={"from": from_ts, "to": to_ts})

    async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        if not self._session:
            raise MT5ConnectionError("Not connected")
        async with self._session.get(path, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, body: Dict) -> Any:
        if not self._session:
            raise MT5ConnectionError("Not connected")
        async with self._session.post(path, json=body) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def __aenter__(self) -> "MT5Connector":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()
