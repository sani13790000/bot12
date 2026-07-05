"""
backend/execution/mt5_connector.py
Galaxy Vast AI Trading Platform

FIXES APPLIED:
  BUG-R4-4: No reconnect logic -> _connected reset on network error + reconnect()
  BUG-R4-5: place_order missing max_deviation, requote retry, SL/TP validation
  BUG-R4-6: Silent DEMO fallback on aiohttp ImportError -> now raises MT5Error
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEVIATION = int(os.environ.get("MT5_MAX_DEVIATION_POINTS", "20"))
_REQUOTE_RETRIES = int(os.environ.get("MT5_REQUOTE_RETRIES", "3"))
_REQUOTE_DELAY_S = float(os.environ.get("MT5_REQUOTE_DELAY_S", "0.5"))


class MT5Error(RuntimeError):
    """Raised when the MT5 gateway returns an error or is unreachable."""


class MT5RequoteError(MT5Error):
    """Raised when broker sends a requote with a new price."""
    def __init__(self, message: str, new_price: Optional[float] = None):
        super().__init__(message)
        self.new_price = new_price


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
        self.timeout_s = float(os.environ.get("MT5_GATEWAY_TIMEOUT", str(timeout_s)))
        self.max_retries = int(os.environ.get("MT5_MAX_RETRIES", str(max_retries)))
        self.demo = demo
        self._session = None
        self._connected = False
        self._reconnect_lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._reconnect_lock is None:
            self._reconnect_lock = asyncio.Lock()
        return self._reconnect_lock

    async def connect(self) -> None:
        if self._connected:
            return
        async with self._get_lock():
            if self._connected:
                return
            try:
                import aiohttp
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout_s)
                )
                if not self.demo:
                    await self._get("/ping")
                self._connected = True
                logger.info("[MT5Connector] connected (%s)", "DEMO" if self.demo else "LIVE")
            except ImportError:
                raise MT5Error(
                    "aiohttp package not installed. "
                    "Add 'aiohttp>=3.9.0,<4.0' to requirements.txt"
                )
            except MT5Error as exc:
                raise MT5Error(f"Cannot connect to MT5 gateway: {exc}") from exc

    async def reconnect(self) -> None:
        """BUG-R4-4 FIX: Force reconnect after network failure."""
        self._connected = False
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        await connect_with_backoff(self, max_attempts=5)

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    def _require_connected(self) -> None:
        if not self._connected:
            raise MT5Error("Not connected -- call connect() first")

    async def health_check(self) -> Dict[str, Any]:
        if self.demo:
            return {"ok": True, "mode": "demo", "ping_ms": 0}
        try:
            result = await asyncio.wait_for(self._get("/ping"), timeout=3.0)
            return {"ok": True, "mode": "live", "ping_ms": result.get("ms", 0)}
        except Exception as exc:
            return {"ok": False, "mode": "live", "error": str(exc)}

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "GalaxyVast",
        max_deviation: int = _DEFAULT_MAX_DEVIATION,
    ) -> OrderResult:
        """
        BUG-R4-5 FIX: max_deviation added + requote retry loop.
        BUG-R4-6 FIX: SL/TP geometry validated before sending to broker.
        """
        self._require_connected()

        direction_upper = direction.upper()
        if sl is not None and tp is not None:
            if direction_upper == "BUY" and sl >= tp:
                raise MT5Error(f"Invalid SL/TP for BUY: SL ({sl}) must be < TP ({tp})")
            if direction_upper == "SELL" and sl <= tp:
                raise MT5Error(f"Invalid SL/TP for SELL: SL ({sl}) must be > TP ({tp})")

        if self.demo:
            ticket = abs(hash(f"{symbol}{direction}{volume}")) % 1_000_000 + 100_000
            logger.info("[MT5Connector][DEMO] place_order %s %s %.2f -> ticket=%d",
                        direction_upper, symbol, volume, ticket)
            return OrderResult(ticket=ticket, symbol=symbol, direction=direction_upper,
                               volume=volume, open_price=0.0, sl=sl, tp=tp)

        payload = {
            "symbol": symbol, "direction": direction_upper,
            "volume": volume, "sl": sl, "tp": tp,
            "comment": comment,
            "max_deviation": max_deviation,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(_REQUOTE_RETRIES + 1):
            try:
                data = await self._post("/order/open", payload)
                if data.get("error"):
                    err_code = data.get("error_code", "")
                    err_msg = data.get("error", "")
                    if "REQUOTE" in str(err_code).upper() or "REQUOTE" in str(err_msg).upper():
                        new_price = data.get("new_price")
                        if attempt < _REQUOTE_RETRIES:
                            logger.warning("[MT5Connector] Requote %d/%d %s new_price=%s",
                                           attempt + 1, _REQUOTE_RETRIES, symbol, new_price)
                            await asyncio.sleep(_REQUOTE_DELAY_S * (attempt + 1))
                            last_exc = MT5RequoteError(f"Requote {symbol}", new_price=new_price)
                            continue
                        raise MT5RequoteError(f"Requote max retries for {symbol}", new_price=new_price)
                    raise MT5Error(f"Order rejected: {err_code} -- {err_msg}")

                if not data.get("ticket"):
                    raise MT5Error(f"No ticket in response: {data}")

                return OrderResult(
                    ticket=int(data["ticket"]), symbol=symbol,
                    direction=direction_upper, volume=volume,
                    open_price=float(data.get("open_price", 0.0)),
                    sl=sl, tp=tp, raw=data,
                )
            except (MT5RequoteError, MT5Error):
                raise
            except Exception as exc:
                last_exc = exc
                break

        raise MT5Error(f"place_order failed: {last_exc}")

    async def close_position(self, ticket: int) -> bool:
        self._require_connected()
        if self.demo:
            return True
        data = await self._post("/order/close", {"ticket": ticket})
        return bool(data.get("closed"))

    async def modify_position(self, ticket: int, sl: Optional[float] = None,
                              tp: Optional[float] = None) -> bool:
        self._require_connected()
        if self.demo:
            return True
        payload: Dict[str, Any] = {"ticket": ticket}
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        data = await self._post("/order/modify", payload)
        return bool(data.get("modified"))

    async def get_positions(self) -> List[PositionInfo]:
        self._require_connected()
        if self.demo:
            return []
        data = await self._get("/positions")
        return [
            PositionInfo(
                ticket=int(p["ticket"]), symbol=p["symbol"],
                direction=p["direction"], volume=float(p["volume"]),
                open_price=float(p["open_price"]),
                current_price=float(p.get("current_price", 0.0)),
                profit=float(p.get("profit", 0.0)),
                sl=p.get("sl"), tp=p.get("tp"),
            )
            for p in data.get("positions", [])
        ]

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> List[CandleData]:
        self._require_connected()
        if self.demo:
            now = datetime.now(timezone.utc)
            tf_s = self._timeframe_to_seconds(timeframe)
            return [
                CandleData(
                    time=datetime.fromtimestamp(now.timestamp() - tf_s * i, timezone.utc),
                    open=1.10000, high=1.10050, low=1.09950, close=1.10020,
                    volume=1000, spread=1,
                )
                for i in range(count)
            ]
        data = await self._get(f"/candles/{symbol}/{timeframe}", params={"count": count})
        return [
            CandleData(
                time=datetime.fromtimestamp(float(c["time"]), timezone.utc),
                open=float(c["open"]), high=float(c["high"]),
                low=float(c["low"]), close=float(c["close"]),
                volume=int(c.get("volume", 0)), spread=int(c.get("spread", 0)),
            )
            for c in data.get("candles", [])
        ]

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self._require_connected()
        if self.demo:
            return SymbolInfo(name=symbol, digits=5, point=0.00001,
                              trade_contract_size=100000.0, volume_min=0.01,
                              volume_max=500.0, volume_step=0.01,
                              spread=1, bid=1.09999, ask=1.10001)
        data = await self._get(f"/symbol/{symbol}")
        return SymbolInfo(
            name=data["name"], digits=int(data["digits"]),
            point=float(data["point"]),
            trade_contract_size=float(data["trade_contract_size"]),
            volume_min=float(data["volume_min"]), volume_max=float(data["volume_max"]),
            volume_step=float(data["volume_step"]),
            spread=int(data.get("spread", 0)),
            bid=float(data.get("bid", 0.0)), ask=float(data.get("ask", 0.0)),
        )

    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        self._require_connected()
        if self.demo:
            return {"bid": 1.09999, "ask": 1.10001,
                    "time": datetime.now(timezone.utc).timestamp()}
        return await self._get(f"/tick/{symbol}")

    async def get_account_info(self) -> Dict[str, Any]:
        self._require_connected()
        if self.demo:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0,
                    "free_margin": 10000.0, "margin_level": 0.0, "currency": "USD"}
        return await self._get("/account")

    async def order_calc_margin(self, symbol: str, lot_size: float, direction: str) -> float:
        self._require_connected()
        if self.demo:
            return lot_size * 1000.0
        data = await self._post("/order/calc_margin", {
            "symbol": symbol, "volume": lot_size, "direction": direction.upper(),
        })
        return float(data.get("margin", 0.0))

    def _timeframe_to_seconds(self, tf: str) -> int:
        return {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600,
                "H4": 14400, "D1": 86400, "W1": 604800, "MN1": 2592000}.get(tf.upper(), 3600)

    async def _get(self, path: str, params=None) -> Dict[str, Any]:
        """BUG-R4-4 FIX: _connected=False on network error."""
        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.get(self.base_url + path, params=params) as r:
                    if r.status >= 400:
                        text = await r.text()
                        raise MT5Error(f"GET {path} => {r.status}: {text}")
                    return await r.json()
            except MT5Error:
                raise
            except Exception as exc:
                if attempt == self.max_retries:
                    self._connected = False
                    logger.error("[MT5Connector] connection lost GET %s: %s", path, exc)
                    raise MT5Error(f"Request GET {path} failed: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
        raise MT5Error("unreachable")

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """BUG-R4-4 FIX: _connected=False on network error."""
        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.post(self.base_url + path, json=payload) as r:
                    if r.status >= 400:
                        text = await r.text()
                        raise MT5Error(f"POST {path} => {r.status}: {text}")
                    return await r.json()
            except MT5Error:
                raise
            except Exception as exc:
                if attempt == self.max_retries:
                    self._connected = False
                    logger.error("[MT5Connector] connection lost POST %s: %s", path, exc)
                    raise MT5Error(f"Request POST {path} failed: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
        raise MT5Error("unreachable")


async def connect_with_backoff(connector: MT5Connector, max_attempts: int = 5) -> None:
    """Reconnect helper with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            await connector.connect()
            logger.info("[MT5Connector] reconnected after %d attempt(s)", attempt + 1)
            return
        except MT5Error as exc:
            delay = 2 ** attempt
            logger.warning("[MT5Connector] reconnect attempt %d/%d failed: %s. Retry in %ds",
                           attempt + 1, max_attempts, exc, delay)
            await asyncio.sleep(delay)
    raise MT5Error(f"Could not reconnect after {max_attempts} attempts")


mt5_connector = MT5Connector()
