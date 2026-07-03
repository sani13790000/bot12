"""
backend/execution/mt5_connector.py
Galaxy Vast AI - MT5 Connector (Async HTTP Bridge)

Connects to MT5 via HTTP bridge.
Demo mode: MT5_DEMO=true simulates all calls.
"""
from __future__ import annotations
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4
import aiohttp

log = logging.getLogger(__name__)

MT5_BRIDGE_URL = os.getenv("MT5_BRIDGE_URL", "http://localhost:8765")
MT5_BRIDGE_KEY = os.getenv("MT5_BRIDGE_KEY", "")
MT5_TIMEOUT_SEC = float(os.getenv("MT5_TIMEOUT_SEC", "10"))
MT5_DEMO_MODE = os.getenv("MT5_DEMO", "false").lower() == "true"


@dataclass
class OrderRequest:
    symbol: str
    direction: str
    volume: float
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    comment: str = ""
    magic: int = 12345
    client_id: UUID = field(default_factory=uuid4)


@dataclass
class OrderResult:
    success: bool
    ticket: Optional[int] = None
    open_price: Optional[float] = None
    error_code: Optional[int] = None
    error_msg: str = ""
    latency_ms: float = 0.0


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    current_sl: float
    current_tp: float
    profit: float
    open_time: str


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str


class _DemoSimulator:
    _ticket_counter = 100_000

    @classmethod
    def next_ticket(cls) -> int:
        cls._ticket_counter += 1
        return cls._ticket_counter

    @classmethod
    async def place_order(cls, req: OrderRequest) -> OrderResult:
        await asyncio.sleep(0.05)
        return OrderResult(success=True, ticket=cls.next_ticket(), open_price=1.08500, latency_ms=50.0)

    @classmethod
    async def close_order(cls, ticket: int, volume: float) -> OrderResult:
        await asyncio.sleep(0.05)
        return OrderResult(success=True, ticket=ticket, latency_ms=50.0)

    @classmethod
    async def get_positions(cls) -> list:
        return []

    @classmethod
    async def get_account(cls) -> AccountInfo:
        return AccountInfo(balance=10_000.0, equity=10_050.0, margin=200.0, free_margin=9_850.0, leverage=100, currency="USD")


class MT5Connector:
    """Async connector to MT5 HTTP bridge."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {"X-API-Key": MT5_BRIDGE_KEY, "Content-Type": "application/json"}

    async def __aenter__(self) -> "MT5Connector":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=MT5_TIMEOUT_SEC)
            self._session = aiohttp.ClientSession(base_url=MT5_BRIDGE_URL, headers=self._headers, timeout=timeout)
        log.info("MT5Connector connected (demo=%s)", MT5_DEMO_MODE)

    async def disconnect(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        log.info("MT5Connector disconnected")

    async def place_order(self, req: OrderRequest) -> OrderResult:
        if MT5_DEMO_MODE:
            return await _DemoSimulator.place_order(req)
        t0 = time.perf_counter()
        payload = {"symbol": req.symbol, "direction": req.direction, "volume": req.volume, "sl_pips": req.sl_pips, "tp_pips": req.tp_pips, "comment": req.comment, "magic": req.magic, "client_id": str(req.client_id)}
        try:
            assert self._session is not None
            async with self._session.post("/order/place", json=payload) as resp:
                data = await resp.json()
                latency = (time.perf_counter() - t0) * 1000
                if resp.status == 200 and data.get("success"):
                    return OrderResult(success=True, ticket=data["ticket"], open_price=data["open_price"], latency_ms=latency)
                return OrderResult(success=False, error_code=data.get("error_code"), error_msg=data.get("error_msg", "unknown"), latency_ms=latency)
        except Exception as exc:
            log.exception("place_order failed: %s", exc)
            return OrderResult(success=False, error_msg=str(exc))

    async def close_order(self, ticket: int, volume: float) -> OrderResult:
        if MT5_DEMO_MODE:
            return await _DemoSimulator.close_order(ticket, volume)
        try:
            assert self._session is not None
            async with self._session.post("/order/close", json={"ticket": ticket, "volume": volume}) as resp:
                data = await resp.json()
                return OrderResult(success=data.get("success", False), ticket=ticket, error_msg=data.get("error_msg", ""))
        except Exception as exc:
            log.exception("close_order failed: %s", exc)
            return OrderResult(success=False, error_msg=str(exc))

    async def get_positions(self) -> list:
        if MT5_DEMO_MODE:
            return await _DemoSimulator.get_positions()
        try:
            assert self._session is not None
            async with self._session.get("/positions") as resp:
                data = await resp.json()
                return [Position(ticket=p["ticket"], symbol=p["symbol"], direction=p["direction"], volume=p["volume"], open_price=p["open_price"], current_sl=p.get("sl", 0.0), current_tp=p.get("tp", 0.0), profit=p.get("profit", 0.0), open_time=p.get("open_time", "")) for p in data.get("positions", [])]
        except Exception as exc:
            log.exception("get_positions failed: %s", exc)
            return []

    async def get_account(self) -> Optional[AccountInfo]:
        if MT5_DEMO_MODE:
            return await _DemoSimulator.get_account()
        try:
            assert self._session is not None
            async with self._session.get("/account") as resp:
                d = await resp.json()
                return AccountInfo(balance=d["balance"], equity=d["equity"], margin=d["margin"], free_margin=d["free_margin"], leverage=d["leverage"], currency=d["currency"])
        except Exception as exc:
            log.exception("get_account failed: %s", exc)
            return None


_connector: Optional[MT5Connector] = None


async def get_connector() -> MT5Connector:
    global _connector
    if _connector is None:
        _connector = MT5Connector()
        await _connector.connect()
    return _connector
