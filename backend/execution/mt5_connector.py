"""
MT5 Connector — Phase A Fix
BUG-R5-5: connect_with_backoff implemented
BUG-R5-6: get_positions() added
BUG-R6-8: _connected=False on network failure in _get/_post
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Exceptions ────────────────────────────────────────────────────────────────

class MT5Error(Exception):
    """General MT5 gateway error."""

class MT5RequoteError(MT5Error):
    """Broker requote — caller may retry with new price."""

class MT5NotConnectedError(MT5Error):
    """Connector has not been connected yet."""


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    ticket: int
    symbol: str
    direction: str
    volume: float
    price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = ""
    retcode: int = 0


@dataclass
class SymbolInfo:
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    digits: int = 5
    trade_contract_size: float = 100_000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: str          # "BUY" | "SELL"
    volume: float
    open_price: float
    sl: Optional[float]
    tp: Optional[float]
    profit: float
    comment: str = ""


# ── MT5 Connector ─────────────────────────────────────────────────────────────

class MT5Connector:
    """Async HTTP bridge to the MQL5 MT5 gateway service."""

    def __init__(
        self,
        base_url: str = "http://mt5-gateway:5000",
        api_key: str = "",
        demo: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.demo = demo
        self._timeout = timeout
        self._session: Optional[Any] = None
        self._connected: bool = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self._connected:
            raise MT5NotConnectedError(
                "MT5Connector is not connected — call await connect() first."
            )

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        import aiohttp
        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        try:
            async with self._session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as exc:
            self._connected = False
            raise MT5Error(f"GET {path} failed: {exc}") from exc

    async def _post(self, path: str, payload: Dict) -> Dict:
        import aiohttp
        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        try:
            async with self._session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as exc:
            self._connected = False
            raise MT5Error(f"POST {path} failed: {exc}") from exc

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection to MT5 gateway."""
        if self._connected:
            return
        try:
            import aiohttp
            self._session = aiohttp.ClientSession()
            if not self.demo:
                await self._get("/ping")
            self._connected = True
            logger.info("[MT5Connector] Connected (demo=%s)", self.demo)
        except ImportError:
            logger.warning("[MT5Connector] aiohttp not installed — DEMO stub mode")
            self._connected = True
            self.demo = True
        except MT5Error as exc:
            logger.error("[MT5Connector] connect() failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        self._connected = False
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("[MT5Connector] Disconnected.")

    async def reconnect(self) -> None:
        """
        BUG-R5-5 FIX: Real exponential backoff reconnect.
        Previously called undefined connect_with_backoff() causing NameError.
        """
        self._connected = False
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                await self.connect()
                logger.info(
                    "[MT5Connector] Reconnected on attempt %d/%d",
                    attempt, max_attempts
                )
                return
            except MT5Error as exc:
                wait = min(2 ** attempt + random.uniform(0, 1), 60)
                logger.warning(
                    "[MT5Connector] Reconnect attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt, max_attempts, exc, wait
                )
                await asyncio.sleep(wait)

        logger.error("[MT5Connector] All %d reconnect attempts exhausted.", max_attempts)

    async def health_check(self) -> Dict[str, Any]:
        """Return connection health info."""
        if self.demo:
            return {"ok": True, "mode": "DEMO", "latency_ms": 0}
        if not self._connected:
            return {"ok": False, "mode": "LIVE", "error": "not connected"}
        try:
            loop = asyncio.get_running_loop()
            start = loop.time()
            await self._get("/ping")
            latency = (loop.time() - start) * 1000
            return {"ok": True, "mode": "LIVE", "latency_ms": round(latency, 2)}
        except MT5Error as exc:
            return {"ok": False, "mode": "LIVE", "error": str(exc)}

    # ── Trading operations ─────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "GalaxyVast",
        max_deviation: int = 20,
        max_requote_retries: int = 3,
    ) -> OrderResult:
        """
        Place a market order with requote retry and SL/TP validation.
        max_deviation: max slippage in points (broker-specific)
        max_requote_retries: how many times to retry on REQUOTE
        """
        self._require_connected()
        direction = direction.upper()

        # SL/TP sanity validation
        if sl is not None and tp is not None:
            if direction == "BUY" and sl >= tp:
                raise MT5Error(f"BUY order: SL ({sl}) must be below TP ({tp})")
            if direction == "SELL" and sl <= tp:
                raise MT5Error(f"SELL order: SL ({sl}) must be above TP ({tp})")

        # DEMO stub — always succeeds
        if self.demo:
            fake_ticket = abs(hash(f"{symbol}{direction}{volume}")) % 900_000 + 100_000
            fake_price = 1.1000 if "USD" in symbol else 2000.0
            return OrderResult(
                ticket=fake_ticket, symbol=symbol, direction=direction,
                volume=volume, price=fake_price, sl=sl, tp=tp, comment=comment
            )

        payload = {
            "symbol": symbol,
            "direction": direction,
            "volume": volume,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "max_deviation": max_deviation,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, max_requote_retries + 1):
            try:
                data = await self._post("/order/open", payload)

                # Requote handling
                if data.get("retcode") in (10004, 10018):
                    new_price = data.get("bid") or data.get("ask")
                    logger.warning(
                        "[MT5Connector] Requote attempt %d/%d new_price=%s",
                        attempt, max_requote_retries, new_price
                    )
                    if attempt < max_requote_retries:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise MT5RequoteError(
                        f"Requote after {max_requote_retries} attempts; last price: {new_price}"
                    )

                # Other broker errors
                if data.get("retcode") not in (None, 0, 10009):
                    raise MT5Error(
                        f"Order rejected: retcode={data.get('retcode')} "
                        f"comment={data.get('comment', '')}"
                    )

                if not data.get("ticket"):
                    raise MT5Error(f"No ticket in response: {data}")

                return OrderResult(
                    ticket=int(data["ticket"]),
                    symbol=symbol,
                    direction=direction,
                    volume=float(data.get("volume", volume)),
                    price=float(data.get("price", 0)),
                    sl=sl,
                    tp=tp,
                    comment=comment,
                    retcode=int(data.get("retcode", 0)),
                )

            except MT5RequoteError:
                raise
            except MT5Error as exc:
                last_error = exc
                if attempt < max_requote_retries:
                    await asyncio.sleep(0.3 * attempt)
                    continue
                raise MT5Error(
                    f"place_order failed after {max_requote_retries} attempts: {last_error}"
                ) from last_error

        raise MT5Error("place_order: unexpected loop exit")

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """Close an open position by ticket."""
        self._require_connected()
        if self.demo:
            return True
        payload: Dict[str, Any] = {"ticket": ticket}
        if volume is not None:
            payload["volume"] = volume
        try:
            data = await self._post("/position/close", payload)
            return bool(data.get("success", False))
        except MT5Error:
            return False

    async def get_positions(self) -> List[Position]:
        """
        BUG-R5-6 FIX: This method was missing — caused AttributeError
        in _position_reconciler() every 30 seconds.
        Returns list of currently open positions from MT5 gateway.
        """
        self._require_connected()

        if self.demo:
            return []   # No real positions in DEMO mode

        try:
            data = await self._get("/positions")
            positions: List[Position] = []
            for raw in data.get("positions", []):
                try:
                    positions.append(Position(
                        ticket=int(raw["ticket"]),
                        symbol=str(raw["symbol"]),
                        direction=str(raw.get("type", "BUY")).upper(),
                        volume=float(raw["volume"]),
                        open_price=float(raw["price_open"]),
                        sl=float(raw["sl"]) if raw.get("sl") else None,
                        tp=float(raw["tp"]) if raw.get("tp") else None,
                        profit=float(raw.get("profit", 0.0)),
                        comment=str(raw.get("comment", "")),
                    ))
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning(
                        "[MT5Connector] Skipping malformed position: %s — %s", raw, exc
                    )
            return positions
        except MT5Error:
            return []

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV candle data."""
        self._require_connected()
        if self.demo:
            import time as _time
            now = int(_time.time())
            step = 900
            base = 1.1000
            candles = []
            for i in range(count):
                ts = now - (count - i) * step
                o = round(base + (i % 10) * 0.0001, 5)
                h = round(o + 0.0005, 5)
                l = round(o - 0.0005, 5)
                c = round(o + 0.0002, 5)
                candles.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": 100 + i})
            return candles
        data = await self._get(
            "/candles",
            params={"symbol": symbol, "timeframe": timeframe, "count": count}
        )
        return data.get("candles", [])

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Fetch symbol metadata including contract size for margin calculation."""
        self._require_connected()
        if self.demo:
            contract_map = {
                "XAUUSD": 100.0,
                "XAGUSD": 5000.0,
                "BTCUSD": 1.0,
                "ETHUSD": 1.0,
            }
            cs = contract_map.get(symbol.upper(), 100_000.0)
            return SymbolInfo(symbol=symbol, trade_contract_size=cs)
        data = await self._get("/symbol/info", params={"symbol": symbol})
        return SymbolInfo(
            symbol=symbol,
            bid=float(data.get("bid", 0)),
            ask=float(data.get("ask", 0)),
            spread=float(data.get("spread", 0)),
            digits=int(data.get("digits", 5)),
            trade_contract_size=float(data.get("trade_contract_size", 100_000)),
            volume_min=float(data.get("volume_min", 0.01)),
            volume_max=float(data.get("volume_max", 100.0)),
            volume_step=float(data.get("volume_step", 0.01)),
        )

    async def order_calc_margin(
        self,
        symbol: str,
        lot_size: float,
        direction: str = "BUY",
    ) -> float:
        """Calculate required margin for a given position size."""
        self._require_connected()
        if self.demo:
            info = await self.get_symbol_info(symbol)
            return round(lot_size * info.trade_contract_size * 0.02, 2)
        data = await self._get(
            "/margin/calc",
            params={"symbol": symbol, "volume": lot_size, "type": direction.upper()}
        )
        return float(data.get("margin", 0.0))


# ── Module-level singleton ─────────────────────────────────────────────────────

def _create_connector() -> MT5Connector:
    try:
        from backend.core.config import get_settings
        s = get_settings()
        return MT5Connector(
            base_url=getattr(s, "MT5_GATEWAY_URL", "http://mt5-gateway:5000"),
            api_key=getattr(s, "GATEWAY_API_KEY", ""),
            demo=getattr(s, "MT5_DEMO_MODE", True),
        )
    except Exception:
        return MT5Connector(demo=True)


mt5_connector: MT5Connector = _create_connector()
