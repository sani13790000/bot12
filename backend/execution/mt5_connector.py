"""
backend/execution/mt5_connector.py
Galaxy Vast AI Trading Platform

فاز ۱ — رفع URL Mismatch بین MT5Connector و MT5 Gateway

تغییرات:
  PHASE1-C1: connect() → GET /ping    (بود: /health)
  PHASE1-C2: get_account_info() → GET /account   (بود: /account/info)
  PHASE1-C3: get_symbol_info() → GET /symbol      (بود: /symbol/info)
  PHASE1-C4: get_candles() → POST /candles        (بود: GET /candles)
  PHASE1-C5: place_order() → POST /order/open     (بود: /order/place)
  PHASE1-C6: close_position() → POST /order/close (بود: /position/close)
  PHASE1-C7: modify_position() → POST /order/modify (بود: /position/modify)
  PHASE1-C8: calculate_margin() → GET /margin/calc (endpoint جدید در gateway)
  PHASE1-C9: get_history() → GET /history         (endpoint جدید در gateway)
  PHASE1-C10: auth header → X-Gateway-Key         (بود: X-API-Key)

اصلاح‌های قبلی که حفظ شدند:
  BUG-R5-5: connect_with_backoff
  BUG-R5-6: get_positions()
  BUG-R6-8: _connected=False on network failure
  BUG-Y2:   _create_connector() critical log on fallback
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
    """خطای عمومی MT5 gateway."""

class MT5RequoteError(MT5Error):
    """بروکر requote داده — caller می‌تواند با قیمت جدید retry کند."""

class MT5NotConnectedError(MT5Error):
    """Connector هنوز connect نشده."""


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
    point: float = 0.00001


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
    """Async HTTP bridge به سرویس MT5 Gateway."""

    def __init__(
        self,
        base_url: str = "http://mt5-gateway:8080",
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
                "MT5Connector متصل نیست — ابتدا await connect() را فراخوانی کنید."
            )

    def _headers(self) -> Dict[str, str]:
        # PHASE1-C10: header صحیح X-Gateway-Key (بود: X-API-Key)
        if self._api_key:
            return {"X-Gateway-Key": self._api_key}
        return {}

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        import aiohttp
        url = f"{self._base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    if resp.status >= 400:
                        raise MT5Error(
                            f"MT5 gateway error {resp.status}: {await resp.text()}"
                        )
                    return await resp.json()
        except aiohttp.ClientError as exc:
            self._connected = False
            raise MT5Error(f"Network error: {exc}") from exc

    async def _post(self, path: str, payload: Optional[Dict] = None) -> Dict:
        import aiohttp
        url = f"{self._base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload or {},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    if resp.status >= 400:
                        raise MT5Error(
                            f"MT5 gateway error {resp.status}: {await resp.text()}"
                        )
                    return await resp.json()
        except aiohttp.ClientError as exc:
            self._connected = False
            raise MT5Error(f"Network error: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """بررسی اتصال به MT5 gateway."""
        try:
            # PHASE1-C1: endpoint صحیح /ping (بود: /health)
            await self._get("/ping")
            self._connected = True
            logger.info(
                "[MT5Connector] متصل شد به gateway در %s (demo=%s)",
                self._base_url, self.demo,
            )
            return True
        except MT5Error as exc:
            self._connected = False
            logger.error("[MT5Connector] اتصال ناموفق: %s", exc)
            return False

    async def connect_with_backoff(
        self, retries: int = 5, base_delay: float = 1.0
    ) -> bool:
        """اتصال با exponential backoff."""
        for attempt in range(1, retries + 1):
            if await self.connect():
                return True
            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning(
                    "[MT5Connector] تلاش %d/%d — retry در %.1f ثانیه",
                    attempt, retries, delay,
                )
                await asyncio.sleep(delay)
        logger.error(
            "[MT5Connector] تمام %d تلاش‌های اتصال ناموفق بودند", retries
        )
        return False

    async def get_account_info(self) -> Dict:
        self._require_connected()
        # PHASE1-C2: endpoint صحیح /account (بود: /account/info)
        return await self._get("/account")

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self._require_connected()
        # PHASE1-C3: endpoint صحیح /symbol (بود: /symbol/info)
        data = await self._get("/symbol", params={"symbol": symbol})
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
            point=data.get("point", 0.00001),
        )

    async def get_candles(
        self, symbol: str, timeframe: str, count: int = 500
    ) -> List[Dict]:
        self._require_connected()
        # PHASE1-C4: POST /candles با body (بود: GET /candles با params)
        data = await self._post(
            "/candles",
            {"symbol": symbol, "timeframe": timeframe, "count": count},
        )
        return data.get("candles", data) if isinstance(data, dict) else data

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
    ) -> OrderResult:
        self._require_connected()
        payload = {
            "symbol":    symbol,
            "direction": direction.upper(),
            "lot":       volume,
            "sl":        sl,
            "tp":        tp,
            "comment":   comment,
            "demo":      self.demo,
        }
        # PHASE1-C5: endpoint صحیح /order/open (بود: /order/place)
        data = await self._post("/order/open", payload)
        return OrderResult(
            ticket=data.get("ticket", 0),
            symbol=symbol,
            direction=direction.upper(),
            volume=volume,
            price=data.get("price", 0.0),
            sl=sl,
            tp=tp,
            comment=comment,
            retcode=data.get("retcode", 0),
        )

    async def close_position(self, ticket: int) -> Dict:
        self._require_connected()
        # PHASE1-C6: endpoint صحیح /order/close (بود: /position/close)
        return await self._post("/order/close", {"ticket": ticket})

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict:
        self._require_connected()
        # PHASE1-C7: endpoint صحیح /order/modify (بود: /position/modify)
        return await self._post("/order/modify", {
            "ticket": ticket,
            "sl":     sl,
            "tp":     tp,
        })

    async def get_positions(self) -> List[Position]:
        self._require_connected()
        data = await self._get("/positions")
        positions = []
        for p in data.get("positions", []):
            positions.append(Position(
                ticket=p.get("ticket", 0),
                symbol=p.get("symbol", ""),
                direction="BUY" if p.get("type", "buy") in ("buy", "BUY", 0) else "SELL",
                volume=p.get("volume", 0.0),
                open_price=p.get("open_price", 0.0),
                sl=p.get("sl"),
                tp=p.get("tp"),
                profit=p.get("profit", 0.0),
                comment=p.get("comment", ""),
            ))
        return positions

    async def get_history(self, from_ts: int, to_ts: int) -> List[Dict]:
        self._require_connected()
        # PHASE1-C9: endpoint جدید /history در gateway اضافه شد
        data = await self._get("/history", params={"from": from_ts, "to": to_ts})
        return data.get("deals", data) if isinstance(data, dict) else data

    async def calculate_margin(
        self, symbol: str, lot_size: float, direction: str
    ) -> float:
        self._require_connected()
        # PHASE1-C8: endpoint جدید /margin/calc در gateway اضافه شد
        data = await self._get(
            "/margin/calc",
            params={
                "symbol": symbol,
                "volume": lot_size,
                "type":   direction.upper(),
            },
        )
        return float(data.get("margin", 0.0))

    async def ping(self) -> Dict:
        """بررسی سلامت gateway بدون نیاز به اتصال."""
        return await self._get("/ping")


# ── Module-level singleton ─────────────────────────────────────────────────────

def _create_connector() -> "MT5Connector":
    """
    BUG-Y2 FIX: در صورت خطای config، CRITICAL log می‌زند.
    PHASE1: پورت پیش‌فرض gateway 8080 است.
    """
    try:
        from backend.core.config import get_settings
        s = get_settings()
        return MT5Connector(
            base_url=getattr(s, "MT5_GATEWAY_URL", "http://mt5-gateway:8080"),
            api_key=getattr(s, "GATEWAY_API_KEY", ""),
            demo=getattr(s, "MT5_DEMO_MODE", True),
        )
    except Exception as exc:
        logger.critical(
            "[MT5Connector] CRITICAL: بارگذاری config ناموفق — fallback به DEMO mode. "
            "تمام معاملات به حساب DEMO ارسال می‌شوند! خطا: %s",
            exc,
        )
        return MT5Connector(demo=True)


mt5_connector: MT5Connector = _create_connector()
