"""backend/execution/mt5_connector.py
Galaxy Vast AI Trading Platform — MT5 Connector (Enterprise)

Changes:
  - Silent 'except Exception: pass -> return False' replaced with debug logging
  - Lazy asyncio.Lock (CRIT-A fix preserved)
  - All other logic unchanged
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger
from ..core.retry import MT5_RETRY, async_retry

logger = get_logger("execution.mt5_connector")

# ── Lazy lock ─────────────────────────────────────────────────────────────────────────
_MT5_LOCK: Optional[asyncio.Lock] = None


def _get_mt5_lock() -> asyncio.Lock:
    global _MT5_LOCK
    if _MT5_LOCK is None:
        _MT5_LOCK = asyncio.Lock()
    return _MT5_LOCK


# ── Data classes ──────────────────────────────────────────────────────────────────

@dataclass
class MT5OrderRequest:
    symbol:     str
    direction:  str             # "BUY" | "SELL"
    lot_size:   float
    order_type: str = "MARKET"  # "MARKET" | "LIMIT" | "STOP"
    price:      float = 0.0
    sl:         float = 0.0
    tp:         float = 0.0
    comment:    str   = ""
    magic:      int   = 0
    deviation:  int   = 10


@dataclass
class MT5OrderResult:
    success:    bool
    ticket:     int    = 0
    order_id:   str    = ""
    price:      float  = 0.0
    volume:     float  = 0.0
    error_code: int    = 0
    error_msg:  str    = ""
    latency_ms: float  = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":    self.success,
            "ticket":     self.ticket,
            "order_id":   self.order_id,
            "price":      self.price,
            "volume":     self.volume,
            "error_code": self.error_code,
            "error_msg":  self.error_msg,
            "latency_ms": self.latency_ms,
        }


@dataclass
class MT5Position:
    ticket:     int
    symbol:     str
    direction:  str
    volume:     float
    open_price: float
    sl:         float  = 0.0
    tp:         float  = 0.0
    profit:     float  = 0.0
    comment:    str    = ""
    magic:      int    = 0
    open_time:  float  = field(default_factory=time.time)


# ── Connector ────────────────────────────────────────────────────────────────────

class MT5Connector:
    """
    Async wrapper around MetaTrader 5 C++ library.
    All blocking calls are offloaded to asyncio.to_thread().
    """

    def __init__(
        self,
        login:    Optional[int]   = None,
        password: Optional[str]   = None,
        server:   Optional[str]   = None,
        path:     Optional[str]   = None,
        timeout:  int             = 10_000,
    ) -> None:
        from ..core.config import get_settings
        _s = get_settings()
        self._login    = login    or getattr(_s, "MT5_LOGIN",    0)
        self._password = password or getattr(_s, "MT5_PASSWORD", "")
        self._server   = server   or getattr(_s, "MT5_SERVER",   "")
        self._path     = path     or getattr(_s, "MT5_PATH",     "")
        self._timeout  = timeout
        self._ready    = False
        self._mt5: Any = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """Connect to MT5 terminal. Returns True on success."""
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            logger.warning("MetaTrader5 package not installed — running in simulation mode")
            self._ready = False
            return False

        async with _get_mt5_lock():
            try:
                ok = await asyncio.to_thread(
                    self._mt5.initialize,
                    path=self._path or None,
                    login=self._login or None,
                    password=self._password or None,
                    server=self._server or None,
                    timeout=self._timeout,
                )
                if ok:
                    self._ready = True
                    info = await asyncio.to_thread(self._mt5.terminal_info)
                    logger.info("MT5 connected", build=getattr(info, "build", "?"),
                                server=self._server)
                else:
                    err = await asyncio.to_thread(self._mt5.last_error)
                    logger.error("MT5 init failed", error=err)
                return ok
            except Exception as exc:
                logger.error("MT5 initialize error", error=str(exc))
                return False

    async def shutdown(self) -> None:
        if self._mt5 is not None and self._ready:
            try:
                await asyncio.to_thread(self._mt5.shutdown)
                logger.info("MT5 disconnected")
            except Exception as exc:
                logger.debug("MT5 shutdown error", error=str(exc))
            finally:
                self._ready = False

    async def health_check(self) -> bool:
        if not self._ready or self._mt5 is None:
            return False
        try:
            info = await asyncio.to_thread(self._mt5.terminal_info)
            return info is not None and getattr(info, "connected", False)
        except Exception as exc:
            logger.debug("MT5 health_check error", error=str(exc))
            return False

    # ── Trading ──────────────────────────────────────────────────────────────────

    @async_retry(MT5_RETRY)
    async def send_order(self, request: MT5OrderRequest) -> MT5OrderResult:
        """Submit a market or pending order."""
        if not self._ready or self._mt5 is None:
            return MT5OrderResult(success=False, error_msg="MT5 not connected")

        t0 = time.monotonic()
        async with _get_mt5_lock():
            try:
                action = (
                    self._mt5.TRADE_ACTION_DEAL
                    if request.order_type == "MARKET"
                    else self._mt5.TRADE_ACTION_PENDING
                )
                order_type = (
                    self._mt5.ORDER_TYPE_BUY
                    if request.direction == "BUY"
                    else self._mt5.ORDER_TYPE_SELL
                )
                req = {
                    "action":    action,
                    "symbol":    request.symbol,
                    "volume":    request.lot_size,
                    "type":      order_type,
                    "price":     request.price or await self._get_current_price(request.symbol, request.direction),
                    "sl":        request.sl,
                    "tp":        request.tp,
                    "deviation": request.deviation,
                    "magic":     request.magic,
                    "comment":   request.comment,
                    "type_time": self._mt5.ORDER_TIME_GTC,
                    "type_filling": self._mt5.ORDER_FILLING_IOC,
                }
                result = await asyncio.to_thread(self._mt5.order_send, req)
                latency = (time.monotonic() - t0) * 1000

                if result is None:
                    err = await asyncio.to_thread(self._mt5.last_error)
                    logger.error("MT5 order_send returned None", error=err, symbol=request.symbol)
                    return MT5OrderResult(success=False, error_code=err[0] if err else -1,
                                         error_msg=str(err), latency_ms=latency)

                success = result.retcode == self._mt5.TRADE_RETCODE_DONE
                if not success:
                    logger.warning("MT5 order rejected", retcode=result.retcode,
                                   symbol=request.symbol, comment=getattr(result, "comment", ""))

                return MT5OrderResult(
                    success=success,
                    ticket=getattr(result, "order", 0),
                    order_id=str(getattr(result, "order", 0)),
                    price=getattr(result, "price", 0.0),
                    volume=getattr(result, "volume", 0.0),
                    error_code=result.retcode,
                    error_msg=getattr(result, "comment", ""),
                    latency_ms=latency,
                )
            except Exception as exc:
                logger.error("MT5 send_order exception", error=str(exc), symbol=request.symbol)
                return MT5OrderResult(success=False, error_msg=str(exc))

    async def close_position(self, ticket: int, volume: float) -> bool:
        """Close an open position by ticket."""
        if not self._ready or self._mt5 is None:
            logger.warning("MT5 not ready for close_position", ticket=ticket)
            return False
        async with _get_mt5_lock():
            try:
                positions = await asyncio.to_thread(self._mt5.positions_get, ticket=ticket)
                if not positions:
                    logger.warning("Position not found", ticket=ticket)
                    return False
                pos = positions[0]
                close_type = (
                    self._mt5.ORDER_TYPE_SELL
                    if pos.type == self._mt5.ORDER_TYPE_BUY
                    else self._mt5.ORDER_TYPE_BUY
                )
                price = await self._get_current_price(
                    pos.symbol,
                    "SELL" if close_type == self._mt5.ORDER_TYPE_SELL else "BUY",
                )
                req = {
                    "action":   self._mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol":   pos.symbol,
                    "volume":   volume,
                    "type":     close_type,
                    "price":    price,
                    "deviation":10,
                    "magic":    pos.magic,
                    "comment":  "close",
                    "type_time": self._mt5.ORDER_TIME_GTC,
                    "type_filling": self._mt5.ORDER_FILLING_IOC,
                }
                result = await asyncio.to_thread(self._mt5.order_send, req)
                success = result is not None and result.retcode == self._mt5.TRADE_RETCODE_DONE
                if not success:
                    logger.error("MT5 close_position failed", ticket=ticket,
                                 retcode=getattr(result, "retcode", -1))
                return success
            except Exception as exc:
                logger.error("MT5 close_position exception", ticket=ticket, error=str(exc))
                return False

    async def get_positions(self) -> List[MT5Position]:
        """Return all open positions."""
        if not self._ready or self._mt5 is None:
            return []
        try:
            raw = await asyncio.to_thread(self._mt5.positions_get)
            if raw is None:
                return []
            return [
                MT5Position(
                    ticket     = p.ticket,
                    symbol     = p.symbol,
                    direction  = "BUY" if p.type == self._mt5.ORDER_TYPE_BUY else "SELL",
                    volume     = p.volume,
                    open_price = p.price_open,
                    sl         = p.sl,
                    tp         = p.tp,
                    profit     = p.profit,
                    comment    = p.comment,
                    magic      = p.magic,
                )
                for p in raw
            ]
        except Exception as exc:
            logger.error("MT5 get_positions error", error=str(exc))
            return []

    async def get_account_info(self) -> Dict[str, Any]:
        """Return account balance, equity, margin."""
        if not self._ready or self._mt5 is None:
            return {}
        try:
            info = await asyncio.to_thread(self._mt5.account_info)
            if info is None:
                return {}
            return {
                "balance":  info.balance,
                "equity":   info.equity,
                "margin":   info.margin,
                "free_margin": info.margin_free,
                "leverage": info.leverage,
                "currency": info.currency,
            }
        except Exception as exc:
            logger.error("MT5 get_account_info error", error=str(exc))
            return {}

    async def _get_current_price(self, symbol: str, direction: str) -> float:
        """Get current bid/ask price for a symbol."""
        try:
            tick = await asyncio.to_thread(self._mt5.symbol_info_tick, symbol)
            if tick is None:
                return 0.0
            return tick.ask if direction == "BUY" else tick.bid
        except Exception as exc:
            logger.debug("_get_current_price error", symbol=symbol, error=str(exc))
            return 0.0


# ── Module singleton ───────────────────────────────────────────────────────────────────

mt5_connector = MT5Connector()


def get_mt5_breaker() -> Any:
    """Backward-compat helper: return the circuit breaker for MT5."""
    from ..circuit_breaker import get_breaker
    return get_breaker()
