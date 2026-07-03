"""
backend/execution/mt5_connector.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Async HTTP bridge to the MetaTrader 5 REST gateway.

Usage::

    connector = MT5Connector(base_url="http://localhost:8080", demo=True)
    await connector.connect()
    ticket = await connector.place_order(
        symbol="EURUSD", direction="BUY",
        volume=0.01, sl=1.0800, tp=1.1050
    )
    await connector.close_position(ticket)
    await connector.disconnect()

Design notes:
- All I/O is async (aiohttp).
- demo=True replaces real calls with logged stubs (safe for CI).
- Retries use exponential back-off (max 3 attempts).
- Every public method raises MT5Error on unrecoverable failure.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Sentinel so callers can catch a single exception type ────────────────── #


class MT5Error(RuntimeError):
    """Raised when the MT5 gateway returns an error or is unreachable."""


# ── Value objects ─────────────────────────────────────────────────────────── #


@dataclass
class OrderResult:
    """Result returned by place_order()."""
    ticket:      int
    symbol:      str
    direction:   str          # "BUY" | "SELL"
    volume:      float
    open_price:  float
    sl:          Optional[float] = None
    tp:          Optional[float] = None
    raw:         Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionInfo:
    """Live position snapshot returned by get_position()."""
    ticket:      int
    symbol:      str
    direction:   str
    volume:      float
    open_price:  float
    current_price: float
    profit:      float
    sl:          Optional[float] = None
    tp:          Optional[float] = None


# ── Connector ─────────────────────────────────────────────────────────────── #


class MT5Connector:
    """
    Async HTTP client for the MT5 REST gateway.

    Parameters
    ----------
    base_url:
        Root URL of the MT5 gateway, e.g. ``http://localhost:8080``.
    timeout_s:
        Per-request timeout in seconds.
    max_retries:
        How many times to retry a failed request before raising MT5Error.
    demo:
        When True every write operation is a no-op (returns realistic stubs).
    """

    def __init__(
        self,
        base_url:    str   = "http://localhost:8080",
        timeout_s:   float = 10.0,
        max_retries: int   = 3,
        demo:        bool  = True,
    ) -> None:
        self.base_url    = base_url.rstrip("/")
        self.timeout_s   = timeout_s
        self.max_retries = max_retries
        self.demo        = demo
        self._session: Any = None   # aiohttp.ClientSession
        self._connected  = False

    # ── Lifecycle ────────────────────────────────────────────────────────── #

    async def connect(self) -> None:
        """Open the HTTP session and verify the gateway is reachable."""
        if self._connected:
            return
        try:
            import aiohttp  # type: ignore
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_s)
            )
            if not self.demo:
                await self._get("/ping")
            self._connected = True
            mode = "DEMO" if self.demo else "LIVE"
            logger.info("[MT5Connector] connected (%s) → %s", mode, self.base_url)
        except ImportError:
            # aiohttp not installed: run in stub mode automatically
            logger.warning("[MT5Connector] aiohttp missing — running in STUB mode")
            self._connected = True
            self.demo = True

    async def disconnect(self) -> None:
        """Close the underlying HTTP session gracefully."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("[MT5Connector] disconnected")

    # ── Trading operations ───────────────────────────────────────────────── #

    async def place_order(
        self,
        symbol:    str,
        direction: str,
        volume:    float,
        sl:        Optional[float] = None,
        tp:        Optional[float] = None,
        comment:   str = "GalaxyVast",
    ) -> OrderResult:
        """
        Open a market order.

        Parameters
        ----------
        symbol:    Instrument, e.g. ``"EURUSD"``.
        direction: ``"BUY"`` or ``"SELL"``.
        volume:    Lot size, e.g. ``0.01``.
        sl:        Stop-loss price (optional).
        tp:        Take-profit price (optional).
        comment:   Order comment shown in MT5 terminal.

        Returns
        -------
        OrderResult with the assigned ticket number.
        """
        self._require_connected()
        payload = {
            "symbol":    symbol,
            "direction": direction.upper(),
            "volume":    volume,
            "sl":        sl,
            "tp":        tp,
            "comment":   comment,
        }
        if self.demo:
            ticket = hash(f"{symbol}{direction}{volume}") % 1_000_000 + 100_000
            logger.info("[MT5Connector][DEMO] place_order %s %s %.2f → ticket=%d",
                        direction, symbol, volume, ticket)
            return OrderResult(
                ticket=ticket, symbol=symbol, direction=direction,
                volume=volume, open_price=0.0, sl=sl, tp=tp,
            )
        data = await self._post("/order/open", payload)
        return OrderResult(
            ticket=int(data["ticket"]),
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=float(data.get("price", 0.0)),
            sl=sl,
            tp=tp,
            raw=data,
        )

    async def close_position(self, ticket: int) -> bool:
        """
        Close an open position by ticket number.

        Returns True on success, False if the position no longer exists.
        """
        self._require_connected()
        if self.demo:
            logger.info("[MT5Connector][DEMO] close_position ticket=%d", ticket)
            return True
        try:
            await self._post("/order/close", {"ticket": ticket})
            return True
        except MT5Error as exc:
            if "not found" in str(exc).lower():
                return False
            raise

    async def modify_order(
        self,
        ticket: int,
        sl:     Optional[float] = None,
        tp:     Optional[float] = None,
    ) -> bool:
        """Modify stop-loss / take-profit of an open position."""
        self._require_connected()
        if self.demo:
            logger.info("[MT5Connector][DEMO] modify_order ticket=%d sl=%s tp=%s",
                        ticket, sl, tp)
            return True
        payload = {"ticket": ticket, "sl": sl, "tp": tp}
        await self._post("/order/modify", payload)
        return True

    async def get_position(self, ticket: int) -> Optional[PositionInfo]:
        """Fetch live details for a single open position."""
        self._require_connected()
        if self.demo:
            return PositionInfo(
                ticket=ticket, symbol="EURUSD", direction="BUY",
                volume=0.01, open_price=1.1000, current_price=1.1010,
                profit=10.0,
            )
        try:
            data = await self._get(f"/position/{ticket}")
            return PositionInfo(
                ticket=int(data["ticket"]),
                symbol=data["symbol"],
                direction=data["type"],
                volume=float(data["volume"]),
                open_price=float(data["price_open"]),
                current_price=float(data["price_current"]),
                profit=float(data["profit"]),
                sl=data.get("sl"),
                tp=data.get("tp"),
            )
        except MT5Error:
            return None

    async def get_all_positions(self) -> list[PositionInfo]:
        """Return all currently open positions."""
        self._require_connected()
        if self.demo:
            return []
        data = await self._get("/positions")
        results = []
        for item in data.get("positions", []):
            results.append(PositionInfo(
                ticket=int(item["ticket"]),
                symbol=item["symbol"],
                direction=item["type"],
                volume=float(item["volume"]),
                open_price=float(item["price_open"]),
                current_price=float(item["price_current"]),
                profit=float(item["profit"]),
                sl=item.get("sl"),
                tp=item.get("tp"),
            ))
        return results

    async def get_account_info(self) -> Dict[str, Any]:
        """Return account balance, equity, margin, etc."""
        self._require_connected()
        if self.demo:
            return {"balance": 10_000.0, "equity": 10_000.0,
                    "margin": 0.0, "free_margin": 10_000.0, "leverage": 100}
        return await self._get("/account")

    # ── Internal HTTP helpers ────────────────────────────────────────────── #

    def _require_connected(self) -> None:
        if not self._connected:
            raise MT5Error("MT5Connector.connect() must be called first")

    async def _get(self, path: str) -> Dict[str, Any]:
        return await self._request("GET", path)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def _request(
        self,
        method: str,
        path:   str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        url = self.base_url + path
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._session.request(method, url, **kwargs) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise MT5Error(f"HTTP {resp.status} from {url}: {body}")
                    return await resp.json()
            except MT5Error:
                raise
            except Exception as exc:
                if attempt == self.max_retries:
                    raise MT5Error(f"Request {method} {url} failed: {exc}") from exc
                wait = 2 ** attempt
                logger.warning("[MT5Connector] attempt %d/%d failed, retry in %ds: %s",
                               attempt, self.max_retries, wait, exc)
                await asyncio.sleep(wait)
        raise MT5Error("unreachable")  # pragma: no cover


# ── Module-level singleton (lazy-connected) ───────────────────────────────── #
mt5_connector = MT5Connector()
