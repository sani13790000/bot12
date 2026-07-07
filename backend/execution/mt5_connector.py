"""
MT5 Connector — Phase A Fix
BUG-R5-5: connect_with_backoff implemented
BUG-R5-6: get_positions() added
BUG-R6-8: _connected=False on network failure in _get/_post
BUG-Y2:   _create_connector() silent fallback → logger.critical added
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
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
    direction: str  # "BUY" | "SELL"
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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        payload: Optional[Dict] = None,
    ) -> Dict:
        import aiohttp

        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        kwargs: Dict[str, Any] = {
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=self._timeout),
        }
        if method == "GET":
            kwargs["params"] = params
        else:
            kwargs["json"] = payload or {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, **kwargs) as resp:
                    if resp.status >= 400:
                        raise MT5Error(f"MT5 gateway error {resp.status}: {await resp.text()}")
                    return await resp.json()
        except aiohttp.ClientError as exc:
            self._connected = False
            raise MT5Error(f"Network error: {exc}") from exc

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, payload: Optional[Dict] = None) -> Dict:
        return await self._request("POST", path, payload=payload)

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Test connectivity to the MT5 gateway."""
        try:
            await self._get("/health")
            self._connected = True
            logger.info(
                "[MT5Connector] Connected to gateway at %s (demo=%s)", self._base_url, self.demo
            )
            return True
        except MT5Error as exc:
            self._connected = False
            logger.error("[MT5Connector] Connection failed: %s", exc)
            return False

    async def connect_with_backoff(self, retries: int = 5, base_delay: float = 1.0) -> bool:
        """Connect with exponential backoff."""
        for attempt in range(1, retries + 1):
            if await self.connect():
                return True
            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning("[MT5Connector] Retry %d/%d in %.1fs", attempt, retries, delay)
                await asyncio.sleep(delay)
        logger.error("[MT5Connector] All %d connection attempts failed", retries)
        return False

    async def get_account_info(self) -> Dict:
        self._require_connected()
        return await self._get("/account/info")

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self._require_connected()
        data = await self._get("/symbol/info", params={"symbol": symbol})
        return SymbolInfo(
            symbol=symbol,
            bid=data.get("bid", 0.0),
            ask=data.get("ask", 0.0),
            spread=data.get("spread", 0.0),
            digits=data.get("digits", 5),
            trade_contract_size=data.get("trade_contract_size", 100_000.0),
            volume_min=data.get("volume_min", 0.01),
            volume_max=data.get("volume_max", 100.0),
            volume_step=data.get("volume_step", 0.01),
        )

    async def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> List[Dict]:
        self._require_connected()
        return await self._get(
            "/candles", params={"symbol": symbol, "timeframe": timeframe, "count": count}
        )

    async def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
    ) -> OrderResult:
        self._require_connected()
        payload = {
            "symbol": symbol,
            "direction": direction.upper(),
            "lot_size": lot_size,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "demo": self.demo,
        }
        data = await self._post("/order/place", payload)
        return OrderResult(
            ticket=data.get("ticket", 0),
            symbol=symbol,
            direction=direction.upper(),
            volume=lot_size,
            price=data.get("price", 0.0),
            sl=sl,
            tp=tp,
            comment=comment,
            retcode=data.get("retcode", 0),
        )

    async def close_position(self, ticket: int) -> Dict:
        self._require_connected()
        return await self._post("/position/close", {"ticket": ticket, "demo": self.demo})

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict:
        self._require_connected()
        return await self._post(
            "/position/modify",
            {
                "ticket": ticket,
                "sl": sl,
                "tp": tp,
                "demo": self.demo,
            },
        )

    async def get_positions(self) -> List[Position]:
        self._require_connected()
        data = await self._get("/positions")
        positions = []
        for p in data.get("positions", []):
            positions.append(
                Position(
                    ticket=p.get("ticket", 0),
                    symbol=p.get("symbol", ""),
                    direction=p.get("direction", "BUY"),
                    volume=p.get("volume", 0.0),
                    open_price=p.get("open_price", 0.0),
                    sl=p.get("sl"),
                    tp=p.get("tp"),
                    profit=p.get("profit", 0.0),
                    comment=p.get("comment", ""),
                )
            )
        return positions

    async def get_history(self, from_ts: int, to_ts: int) -> List[Dict]:
        self._require_connected()
        return await self._get("/history", params={"from": from_ts, "to": to_ts})

    async def calculate_margin(self, symbol: str, lot_size: float, direction: str) -> float:
        self._require_connected()
        data = await self._get(
            "/margin/calc", params={"symbol": symbol, "volume": lot_size, "type": direction.upper()}
        )
        return float(data.get("margin", 0.0))


# ── Module-level singleton ─────────────────────────────────────────────────────


def _create_connector() -> MT5Connector:
    """
    BUG-Y2 FIX: Silent fallback to demo=True without any log was a production risk.
    Now logs CRITICAL so operators are immediately alerted when config fails.
    """
    try:
        from backend.core.config import get_settings

        s = get_settings()
        return MT5Connector(
            base_url=getattr(s, "MT5_GATEWAY_URL", "http://mt5-gateway:5000"),
            api_key=getattr(s, "GATEWAY_API_KEY", ""),
            demo=getattr(s, "MT5_DEMO_MODE", True),
        )
    except Exception as exc:
        logger.critical(
            "[MT5Connector] CRITICAL: Config load failed — falling back to DEMO mode. "
            "All trades will be sent to DEMO account! Error: %s",
            exc,
        )
        return MT5Connector(demo=True)


mt5_connector: MT5Connector = _create_connector()
