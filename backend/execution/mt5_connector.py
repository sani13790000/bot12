"""
Galaxy Vast AI Trading Platform
MT5 Async Connector - Production Reliability v2

FIXES:
  R-1:      Health revalidation after initialize()
  R-2:      Login failure propagation
  R-3:      Dynamic slippage deviation via ATR/spread/volatility
  T-6:      close_position validates position exists
  T-7:      DEADLOCK removed - _is_connected() lock-free
  T-14:     type_filling from MT5_ORDER_FILLING env var
  BUG-MT5-1: Race condition - concurrent send_order() on MT5 C++ lib.
             FIX: acquire self._lock for entire _send_order_sync_unlocked.
  BUG-MT5-2: Race condition - close_position() vs shutdown() use-after-free.
             FIX: acquire self._lock in close_position before to_thread.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.mt5_connector")
_DEFAULT_TYPE_FILLING = os.environ.get("MT5_ORDER_FILLING", "ORDER_FILLING_IOC")

_REVALIDATE_TIMEOUT_S: float = float(os.environ.get("MT5_REVALIDATE_TIMEOUT", "5"))
_REVALIDATE_RETRIES:   int   = int(os.environ.get("MT5_REVALIDATE_RETRIES",  "3"))

_SLIPPAGE_BASE:         int   = int(os.environ.get("MT5_SLIPPAGE_BASE",    "10"))
_SLIPPAGE_MAX:          int   = int(os.environ.get("MT5_SLIPPAGE_MAX",     "50"))
_SLIPPAGE_SPREAD_MULT:  float = float(os.environ.get("MT5_SLIPPAGE_SPREAD_MULT", "1.5"))
_SLIPPAGE_ATR_MULT:     float = float(os.environ.get("MT5_SLIPPAGE_ATR_MULT",   "2.0"))
_SLIPPAGE_VOL_HIGH_ADD: int   = int(os.environ.get("MT5_SLIPPAGE_VOL_HIGH_ADD", "10"))


class MT5ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING   = "connecting"
    CONNECTED    = "connected"
    ERROR        = "error"


@dataclass
class MT5OrderRequest:
    symbol:          str
    action:          str
    volume:          float
    price:           Optional[float] = None
    sl:              Optional[float] = None
    tp:              Optional[float] = None
    deviation:       int             = _SLIPPAGE_BASE
    magic:           int             = 0
    comment:         str             = ""
    type_filling:    str             = _DEFAULT_TYPE_FILLING
    current_atr:     Optional[float] = None
    avg_atr:         Optional[float] = None
    current_spread:  Optional[float] = None
    avg_spread:      Optional[float] = None
    volatility_high: bool            = False


@dataclass
class MT5OrderResult:
    success:   bool
    retcode:   int                   = 0
    deal:      int                   = 0
    order:     int                   = 0
    volume:    float                 = 0.0
    price:     float                 = 0.0
    deviation: int                   = 0
    comment:   str                   = ""
    request:   Optional[Dict[str, Any]] = None
    error:     Optional[str]         = None
    timestamp: datetime              = field(default_factory=lambda: datetime.now(timezone.utc))


def compute_dynamic_deviation(request: MT5OrderRequest) -> int:
    deviation = float(_SLIPPAGE_BASE)
    try:
        if request.current_atr and request.avg_atr and request.avg_atr > 0:
            atr_ratio  = request.current_atr / request.avg_atr
            atr_add    = (atr_ratio - 1.0) * _SLIPPAGE_ATR_MULT * _SLIPPAGE_BASE
            deviation += max(0.0, atr_add)
        if request.current_spread and request.avg_spread and request.avg_spread > 0:
            spread_ratio = request.current_spread / request.avg_spread
            spread_add   = (spread_ratio - 1.0) * _SLIPPAGE_SPREAD_MULT * _SLIPPAGE_BASE
            deviation   += max(0.0, spread_add)
        if request.volatility_high:
            deviation += _SLIPPAGE_VOL_HIGH_ADD
    except Exception as exc:
        logger.warning("compute_dynamic_deviation error: %s", exc)
        return _SLIPPAGE_BASE
    result = max(_SLIPPAGE_BASE, min(int(round(deviation)), _SLIPPAGE_MAX))
    logger.info("DynamicSlippage: %d pts", result)
    return result


class MT5Connector:
    def __init__(self, exe_path=None, timeout_seconds=30, max_retries=3, retry_delay=1.0):
        self.exe_path    = exe_path or os.environ.get("MT5_EXE_PATH", "")
        self.timeout     = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._status     = MT5ConnectionStatus.DISCONNECTED
        self._lock       = asyncio.Lock()
        self._last_error: Optional[str] = None
        self._mt5:        Optional[Any] = None
        self._connection_attempts       = 0

    @property
    def status(self) -> MT5ConnectionStatus: return self._status

    def _is_connected(self) -> bool:
        return self._status == MT5ConnectionStatus.CONNECTED and self._mt5 is not None

    async def initialize(self) -> bool:
        async with self._lock:
            if self._is_connected(): return True
            self._status = MT5ConnectionStatus.CONNECTING
            self._connection_attempts += 1
            try:
                self._mt5 = await asyncio.to_thread(self._import_mt5)
                if self._mt5 is None:
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = "MT5 package not installed"
                    logger.error(self._last_error); return False
                kwargs: Dict[str, Any] = {}
                if self.exe_path: kwargs["path"] = self.exe_path
                ok = await asyncio.to_thread(self._mt5.initialize, **kwargs)
                if not ok:
                    err = self._mt5.last_error()
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = f"MT5 initialize() failed: {err}"
                    logger.error(self._last_error); return False
                login_ok = await self._login_from_env()
                if not login_ok:
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = "MT5 login failed - trading blocked"
                    logger.error("R-2: %s", self._last_error)
                    try: await asyncio.to_thread(self._mt5.shutdown)
                    except Exception: pass
                    return False
                revalidated = await self._revalidate()
                if not revalidated:
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = "MT5 revalidation failed after initialize()"
                    logger.error("R-1: %s", self._last_error); return False
                self._status = MT5ConnectionStatus.CONNECTED
                self._last_error = None
                self._connection_attempts = 0
                logger.info("MT5 connector initialized and revalidated")
                return True
            except Exception as exc:
                self._status = MT5ConnectionStatus.ERROR
                self._last_error = str(exc)
                logger.exception("MT5 initialize exception")
                return False

    async def _revalidate(self) -> bool:
        for attempt in range(1, _REVALIDATE_RETRIES + 1):
            try:
                info = await asyncio.wait_for(
                    asyncio.to_thread(self._mt5.terminal_info),
                    timeout=_REVALIDATE_TIMEOUT_S)
                if info and info.connected:
                    logger.info("R-1: Revalidation OK (attempt %d)", attempt); return True
                logger.warning("R-1: Revalidation attempt %d: not connected", attempt)
            except asyncio.TimeoutError:
                logger.warning("R-1: Revalidation attempt %d timed out", attempt)
            except Exception as exc:
                logger.warning("R-1: Revalidation attempt %d error: %s", attempt, exc)
            if attempt < _REVALIDATE_RETRIES: await asyncio.sleep(1.0)
        return False

    def _import_mt5(self) -> Optional[Any]:
        try:
            import MetaTrader5 as mt5
            return mt5
        except Exception:
            logger.warning("MetaTrader5 package not available")
            return None

    async def _login_from_env(self) -> bool:
        login    = os.environ.get("MT5_LOGIN")
        password = os.environ.get("MT5_PASSWORD")
        server   = os.environ.get("MT5_SERVER")
        if not (login and password and server):
            logger.warning("R-2: MT5 credentials not set - login failed"); return False
        try:
            ok = bool(await asyncio.to_thread(self._mt5.login, int(login), password, server))
            if ok: logger.info("MT5 login OK (account %s @ %s)", login, server)
            else: logger.error("MT5 login FAILED: %s", self._mt5.last_error())
            return ok
        except Exception as exc:
            logger.error("MT5 login exception: %s", exc); return False

    async def shutdown(self) -> None:
        async with self._lock:
            if self._mt5:
                try: await asyncio.to_thread(self._mt5.shutdown)
                except Exception as exc: logger.warning("MT5 shutdown error: %s", exc)
                finally: self._mt5 = None
            self._status = MT5ConnectionStatus.DISCONNECTED

    async def health_check(self) -> bool:
        if not self._is_connected(): return False
        async with self._lock:
            if not self._is_connected(): return False
            try:
                info = await asyncio.to_thread(self._mt5.terminal_info)
                ok   = bool(info and info.connected)
                if not ok: self._status = MT5ConnectionStatus.ERROR
                return ok
            except Exception as exc:
                logger.warning("MT5 health_check failed: %s", exc)
                self._status = MT5ConnectionStatus.ERROR
                return False

    async def get_account_info(self) -> Optional[Any]:
        if not await self.health_check(): return None
        async with self._lock:
            if not self._is_connected(): return None
            return await asyncio.to_thread(self._mt5.account_info)

    async def get_positions(self) -> List[Any]:
        if not await self.health_check(): return []
        async with self._lock:
            if not self._is_connected(): return []
            return await asyncio.to_thread(self._mt5.positions_get) or []

    async def get_orders(self) -> List[Any]:
        if not await self.health_check(): return []
        async with self._lock:
            if not self._is_connected(): return []
            return await asyncio.to_thread(self._mt5.orders_get) or []

    async def send_order(self, request: MT5OrderRequest, retry_policy=None) -> MT5OrderResult:
        request.deviation = compute_dynamic_deviation(request)
        if not await self.health_check():
            await self.initialize()
        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # BUG-MT5-1 FIX: hold self._lock for entire MT5 C++ send.
                # MT5 is NOT thread-safe for concurrent order_send() calls.
                async with self._lock:
                    if not self._is_connected():
                        last_error = "MT5 disconnected before send"; break
                    result = await asyncio.wait_for(
                        self._send_order_sync_unlocked(request),
                        timeout=self.timeout)
                if result.success: return result
                last_error = result.error
                if retry_policy and not retry_policy(result): break
            except asyncio.TimeoutError:
                last_error = f"MT5 order timeout attempt {attempt}"
                logger.warning(last_error)
            except Exception as exc:
                last_error = str(exc)
                logger.exception("MT5 send_order error attempt %s", attempt)
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)
        return MT5OrderResult(success=False, error=last_error or "unknown", deviation=request.deviation)

    async def _send_order_sync_unlocked(self, request: MT5OrderRequest) -> MT5OrderResult:
        """Must be called while holding self._lock (BUG-MT5-1)."""
        def _send() -> MT5OrderResult:
            if not self._mt5: return MT5OrderResult(success=False, error="MT5 not initialized")
            order_type   = (self._mt5.ORDER_TYPE_BUY if request.action.upper() == "BUY" else self._mt5.ORDER_TYPE_SELL)
            filling_attr = getattr(self._mt5, request.type_filling, None) or getattr(self._mt5, "ORDER_FILLING_IOC", 1)
            req: Dict[str, Any] = {
                "action": self._mt5.TRADE_ACTION_DEAL, "symbol": request.symbol,
                "volume": float(request.volume), "type": order_type,
                "deviation": request.deviation, "magic": request.magic,
                "comment": request.comment, "type_filling": filling_attr,
            }
            if request.price is not None: req["price"] = float(request.price)
            if request.sl   is not None: req["sl"]    = float(request.sl)
            if request.tp   is not None: req["tp"]    = float(request.tp)
            result = self._mt5.order_send(req)
            if result is None:
                return MT5OrderResult(success=False, retcode=-1,
                    error=f"MT5 None: {self._mt5.last_error()}", deviation=request.deviation)
            success = result.retcode == self._mt5.TRADE_RETCODE_DONE
            return MT5OrderResult(
                success=success, retcode=result.retcode,
                deal=getattr(result, "deal", 0), order=getattr(result, "order", 0),
                volume=getattr(result, "volume", 0.0), price=getattr(result, "price", 0.0),
                comment=getattr(result, "comment", ""), request=req,
                deviation=request.deviation,
                error=None if success else f"retcode={result.retcode}",
            )
        return await asyncio.to_thread(_send)

    async def close_position(self, ticket: int, deviation: int = 10) -> MT5OrderResult:
        if not await self.health_check():
            return MT5OrderResult(success=False, error="MT5 not connected")
        # BUG-MT5-2 FIX: hold lock so shutdown() cannot set self._mt5=None
        # concurrently with the close thread.
        async with self._lock:
            if not self._is_connected():
                return MT5OrderResult(success=False, error="MT5 disconnected before close")
            def _close() -> MT5OrderResult:
                if not self._mt5: return MT5OrderResult(success=False, error="MT5 not initialized")
                position_list = self._mt5.positions_get(ticket=ticket)
                if not position_list:
                    return MT5OrderResult(success=False, error=f"Position {ticket} not found or already closed")
                pos = position_list[0]
                order_type = (self._mt5.ORDER_TYPE_SELL if pos.type == self._mt5.ORDER_TYPE_BUY else self._mt5.ORDER_TYPE_BUY)
                tick = self._mt5.symbol_info_tick(pos.symbol)
                if tick is None:
                    return MT5OrderResult(success=False, error=f"Cannot get tick for {pos.symbol}")
                price = tick.bid if order_type == self._mt5.ORDER_TYPE_SELL else tick.ask
                req = {"action": self._mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": pos.symbol,
                       "volume": pos.volume, "type": order_type, "price": price,
                       "deviation": deviation, "comment": "bot_close"}
                result  = self._mt5.order_send(req)
                success = getattr(result, "retcode", -1) == self._mt5.TRADE_RETCODE_DONE
                return MT5OrderResult(success=success, retcode=getattr(result, "retcode", -1),
                    deal=getattr(result, "deal", 0), comment=getattr(result, "comment", ""),
                    error=None if success else f"retcode={getattr(result, 'retcode', -1)}")
            return await asyncio.to_thread(_close)


mt5_connector = MT5Connector()
