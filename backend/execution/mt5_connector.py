"""
backend/execution/mt5_connector.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Async HTTP bridge to the MetaTrader 5 REST gateway.

فاز G — تغییرات:
- demo پیش‌فرض از env var خوانده می‌شود (MT5_DEMO_MODE)
- get_candles() اضافه شد
- get_symbol_info() اضافه شد
- singleton با تنظیمات env ساخته می‌شود
- health_check() اضافه شد

فاز P — تغییرات:
- P-FIX-2: MT5TIMEOUT_S ⇒ MT5_GATEWAY_TIMEOUT (consistent with config_v11.py)

Usage::

    connector = MT5Connector(base_url="http://localhost:8080", demo=False)
    await connector.connect()
    ticket = await connector.place_order(
        symbol="EURUSD", direction="BUY",
        volume=0.01, sl=1.0800, tp=1.1050
    )
    candles = await connector.get_candles("EURUSD", "H1", 100)
    await connector.close_position(ticket)
    await connector.disconnect()

Design notes:
- All I/O is async (aiohttp).
- demo=False ⇒ real MT5 REST gateway calls.
- demo=True  ⇒ logged stubs (safe for CI/testing).
- Retries use exponential back-off (max 3 attempts).
- Every public method raises MT5Error on unrecoverable failure.
- MT5_DEMO_MODE env var controls default: "false" = LIVE, "true" = DEMO
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MT5Error(RuntimeError):
    """Raised when the MT5 gateway returns an error or is unreachable."""


@dataclass
class OrderResult:
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionInfo:
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    current_price: float
    profit: float
    sl: Optional[float] = None
    tp: Optional[float] = None


@dataclass
class CandleData:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    spread: int = 0


@dataclass
class SymbolInfo:
    name: str
    digits: int
    point: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    spread: int
    bid: float
    ask: float


class MT5Connector:
    def __init__(self, base_url="", timeout_s=10.0, max_retries=3, demo=None):
        if demo is None:
            env_demo = os.environ.get("MT5_DEMO_MODE", "true").lower()
            demo = env_demo not in ("false", "0", "no", "off")
        self.base_url = (base_url or os.environ.get("MT5_GATEWAY_URL", "http://localhost:8080")).rstrip("/")
        # P-FIX-2: was MT5TIMEOUT_S (missing underscore) — now consistent with config_v11.py
        self.timeout_s = float(os.environ.get("MT5_GATEWAY_TIMEOUT", str(timeout_s)))
        self.max_retries = int(os.environ.get("MT5_MAX_RETRIES", str(max_retries)))
        self.demo = demo
        self._session = None
        self._connected = False

    async def connect(self):
        if self._connected:
            return
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s))
            if not self.demo:
                await self._get("/ping")
            self._connected = True
            logger.info("[MT5Connector] connected (%s)", "DEMO" if self.demo else "LIVE")
        except ImportError:
            logger.warning("[MT5Connector] aiohttp missing - STUB mode")
            self._connected = True
            self.demo = True
        except MT5Error as exc:
            raise MT5Error(f"Cannot connect to MT5 gateway: {exc}") from exc

    async def disconnect(self):
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    async def health_check(self):
        if self.demo:
            return {"ok": True, "mode": "DEMO", "ping_ms": 0.0, "account": "demo"}
        try:
            import time
            t0 = time.monotonic()
            data = await self._get("/ping")
            ping_ms = (time.monotonic() - t0) * 1000
            return {"ok": True, "mode": "LIVE", "ping_ms": round(ping_ms, 1), **data}
        except MT5Error as exc:
            return {"ok": False, "mode": "LIVE", "error": str(exc)}

    async def get_candles(self, symbol, timeframe, count=100, from_date=None):
        self._require_connected()
        if self.demo:
            import random
            rng = random.Random(42)
            candles = []
            price = 1.1000
            now = datetime.now(timezone.utc)
            tf_seconds = self._timeframe_to_seconds(timeframe)
            for i in range(count):
                ts = datetime.fromtimestamp(now.timestamp() - (count - i) * tf_seconds, tz=timezone.utc)
                o = price
                h = o + rng.uniform(0.0001, 0.0020)
                l = o - rng.uniform(0.0001, 0.0020)
                c = rng.uniform(l, h)
                price = c
                candles.append(CandleData(time=ts, open=round(o, 5), high=round(h, 5), low=round(l, 5), close=round(c, 5), volume=rng.randint(100, 5000), spread=rng.randint(1, 3)))
            return candles
        params = {"symbol": symbol, "timeframe": timeframe, "count": min(count, 5000)}
        if from_date:
            params["from"] = from_date.isoformat()
        data = await self._get("/candles", params=params)
        return [CandleData(time=datetime.fromisoformat(b["time"]), open=float(b["open"]), high=float(b["high"]), low=float(b["low"]), close=float(b["close"]), volume=int(b["volume"]), spread=int(b.get("spread", 0))) for b in data.get("candles", [])]

    async def get_symbol_info(self, symbol):
        self._require_connected()
        if self.demo:
            return SymbolInfo(name=symbol, digits=5, point=0.00001, trade_contract_size=100000.0, volume_min=0.01, volume_max=500.0, volume_step=0.01, spread=1, bid=1.09999, ask=1.10001)
        data = await self._get(f"/symbol/{symbol}")
        return SymbolInfo(name=data["name"], digits=int(data["digits"]), point=float(data["point"]), trade_contract_size=float(data["trade_contract_size"]), volume_min=float(data["volume_min"]), volume_max=float(data["volume_max"]), volume_step=float(data["volume_step"]), spread=int(data.get("spread", 0)), bid=float(data.get("bid", 0.0)), ask=float(data.get("ask", 0.0)))

    async def get_tick(self, symbol):
        self._require_connected()
        if self.demo:
            return {"bid": 1.09999, "ask": 1.10001, "time": datetime.now(timezone.utc).timestamp()}
        return await self._get(f"/tick/{symbol}")

    async def place_order(self, symbol, direction, volume, sl=None, tp=None, comment="GalaxyVast"):
        self._require_connected()
        payload = {"symbol": symbol, "direction": direction.upper(), "volume": volume, "sl": sl, "tp": tp, "comment": comment}
        if self.demo:
            ticket = abs(hash(f"{symbol}{direction}{volume}")) % 1_000_000 + 100_000
            logger.info("[MT5Connector][DEMO] place_order %s %s %.2f -> ticket=%d", direction, symbol, volume, ticket)
            return OrderResult(ticket=ticket, symbol=symbol, direction=direction, volume=volume, open_price=0.0, sl=sl, tp=tp)
        data = await self._post("/order/open", payload)
        if not data.get("ticket"):
            raise MT5Error(f"No ticket in response: {data}")
        return OrderResult(ticket=int(data["ticket"]), symbol=symbol, direction=direction, volume=volume, open_price=float(data.get("open_price", 0.0)), sl=sl, tp=tp, raw=data)

    async def close_position(self, ticket: int) -> bool:
        self._require_connected()
        if self.demo:
            logger.info("[MT5Connector][DEMO] close_position ticket=%d", ticket)
            return True
        data = await self._post("/order/close", {"ticket": ticket})
        return bool(data.get("closed"))

    async def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        self._require_connected()
        if self.demo:
            return True
        payload = {"ticket": ticket}
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        data = await self._post("/order/modify", payload)
        return bool(data.get("modified"))

    async def get_open_positions(self) -> List[PositionInfo]:
        self._require_connected()
        if self.demo:
            return []
        data = await self._get("/positions")
        return [PositionInfo(ticket=int(p["ticket"]), symbol=p["symbol"], direction=p["direction"], volume=float(p["volume"]), open_price=float(p["open_price"]), current_price=float(p["current_price"]), profit=float(p["profit"]), sl=p.get("sl"), tp=p.get("tp")) for p in data.get("positions", [])]

    async def get_account_info(self) -> Dict[str, Any]:
        self._require_connected()
        if self.demo:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0, "profit": 0.0, "leverage": 100, "currency": "USD"}
        return await self._get("/account")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _require_connected(self):
        if not self._connected:
            raise MT5Error("Not connected — call connect() first")

    def _timeframe_to_seconds(self, tf: str) -> int:
        mapping = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800, "MN1": 2592000}
        return mapping.get(tf.upper(), 3600)

    async def _get(self, path: str, params=None):
        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.get(self.base_url + path, params=params) as r:
                    if r.status >= 400:
                        text = await r.text()
                        raise MT5Error(f"GET {path} ⇒ {r.status}: {text}")
                    return await r.json()
            except MT5Error:
                raise
            except Exception as exc:
                if attempt == self.max_retries:
                    raise MT5Error(f"Request GET {path} failed: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
        raise MT5Error("unreachable")

    async def _post(self, path: str, payload):
        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.post(self.base_url + path, json=payload) as r:
                    if r.status >= 400:
                        text = await r.text()
                        raise MT5Error(f"POST {path} ⇒ {r.status}: {text}")
                    return await r.json()
            except MT5Error:
                raise
            except Exception as exc:
                if attempt == self.max_retries:
                    raise MT5Error(f"Request POST {path} failed: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
        raise MT5Error("unreachable")


mt5_connector = MT5Connector()
