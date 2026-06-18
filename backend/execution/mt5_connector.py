"""
Galaxy Vast AI Trading Platform
MT5 Async Connector — Phase 7

Provides a non-blocking wrapper around MetaTrader5 with:
- connection health checks
- async order operations
- retry + circuit-breaker integration
- graceful degradation when MT5 is offline
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.mt5_connector")


class MT5ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MT5OrderRequest:
    symbol: str
    action: str  # BUY / SELL
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 10
    magic: int = 0
    comment: str = ""
    type_filling: str = "ORDER_FILLING_IOC"


@dataclass
class MT5OrderResult:
    success: bool
    retcode: int = 0
    deal: int = 0
    order: int = 0
    volume: float = 0.0
    price: float = 0.0
    comment: str = ""
    request: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MT5Connector:
    """Async wrapper for MetaTrader5 terminal."""

    def __init__(
        self,
        exe_path: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.exe_path = exe_path or os.environ.get("MT5_EXE_PATH", "")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._status = MT5ConnectionStatus.DISCONNECTED
        self._lock = asyncio.Lock()
        self._last_error: Optional[str] = None
        self._mt5: Optional[Any] = None
        self._connection_attempts = 0

    @property
    def status(self) -> MT5ConnectionStatus:
        return self._status

    async def initialize(self) -> bool:
        """Initialize MT5 terminal asynchronously."""
        async with self._lock:
            if self._status == MT5ConnectionStatus.CONNECTED and self._mt5:
                return True

            self._status = MT5ConnectionStatus.CONNECTING
            self._connection_attempts += 1

            try:
                self._mt5 = await asyncio.to_thread(self._import_mt5)
                if self._mt5 is None:
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = "MetaTrader5 package not installed"
                    return False

                kwargs: Dict[str, Any] = {}
                if self.exe_path:
                    kwargs["path"] = self.exe_path

                ok = await asyncio.to_thread(self._mt5.initialize, **kwargs)
                if not ok:
                    self._status = MT5ConnectionStatus.ERROR
                    self._last_error = f"MT5 init failed: {self._mt5.last_error()}"
                    logger.error(self._last_error)
                    return False

                login_ok = await self._login_from_env()
                if not login_ok:
                    logger.warning("MT5 login via env not configured or failed")

                self._status = MT5ConnectionStatus.CONNECTED
                self._last_error = None
                self._connection_attempts = 0
                logger.info("MT5 connector initialized successfully")
                return True

            except Exception as exc:
                self._status = MT5ConnectionStatus.ERROR
                self._last_error = str(exc)
                logger.exception("MT5 initialize failed")
                return False

    def _import_mt5(self) -> Optional[Any]:
        try:
            import MetaTrader5 as mt5
            return mt5
        except Exception:
            logger.warning("MetaTrader5 package not available")
            return None

    async def _login_from_env(self) -> bool:
        login = os.environ.get("MT5_LOGIN")
        password = os.environ.get("MT5_PASSWORD")
        server = os.environ.get("MT5_SERVER")
        if not (login and password and server):
            return False
        try:
            result = await asyncio.to_thread(
                self._mt5.login, int(login), password, server
            )
            return bool(result)
        except Exception as exc:
            logger.warning("MT5 login failed: %s", exc)
            return False

    async def shutdown(self) -> None:
        async with self._lock:
            if self._mt5:
                try:
                    await asyncio.to_thread(self._mt5.shutdown)
                except Exception as exc:
                    logger.warning("MT5 shutdown error: %s", exc)
                finally:
                    self._mt5 = None
            self._status = MT5ConnectionStatus.DISCONNECTED

    async def health_check(self) -> bool:
        """Return True if terminal is connected and responsive."""
        async with self._lock:
            if self._status != MT5ConnectionStatus.CONNECTED or not self._mt5:
                return False
            try:
                info = await asyncio.to_thread(self._mt5.terminal_info)
                return bool(info and info.connected)
            except Exception as exc:
                logger.warning("MT5 health check failed: %s", exc)
                self._status = MT5ConnectionStatus.ERROR
                return False

    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not await self.health_check():
            return None
        return await asyncio.to_thread(self._mt5.account_info)

    async def get_positions(self) -> List[Dict[str, Any]]:
        if not await self.health_check():
            return []
        return await asyncio.to_thread(self._mt5.positions_get) or []

    async def get_orders(self) -> List[Dict[str, Any]]:
        if not await self.health_check():
            return []
        return await asyncio.to_thread(self._mt5.orders_get) or []

    async def send_order(
        self,
        request: MT5OrderRequest,
        retry_policy: Optional[Callable[[MT5OrderResult], bool]] = None,
    ) -> MT5OrderResult:
        """Send an order with retry + timeout."""
        if not await self.health_check():
            await self.initialize()

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._send_order_sync(request),
                    timeout=self.timeout,
                )
                if result.success:
                    return result
                last_error = result.error
                if retry_policy and not retry_policy(result):
                    break
            except asyncio.TimeoutError:
                last_error = f"MT5 order timeout (attempt {attempt})"
                logger.warning(last_error)
            except Exception as exc:
                last_error = str(exc)
                logger.exception("MT5 send_order error attempt %s", attempt)

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)

        return MT5OrderResult(success=False, error=last_error or "unknown")

    async def _send_order_sync(self, request: MT5OrderRequest) -> MT5OrderResult:
        def _send() -> MT5OrderResult:
            if not self._mt5:
                return MT5OrderResult(success=False, error="MT5 not initialized")

            order_type = (
                self._mt5.ORDER_TYPE_BUY
                if request.action.upper() == "BUY"
                else self._mt5.ORDER_TYPE_SELL
            )
            action_type = self._mt5.TRADE_ACTION_DEAL

            req = {
                "action": action_type,
                "symbol": request.symbol,
                "volume": float(request.volume),
                "type": order_type,
                "deviation": request.deviation,
                "magic": request.magic,
                "comment": request.comment,
                "type_filling": getattr(
                    self._mt5, request.type_filling, "ORDER_FILLING_IOC"
                ),
            }
            if request.price:
                req["price"] = float(request.price)
            if request.sl is not None:
                req["sl"] = float(request.sl)
            if request.tp is not None:
                req["tp"] = float(request.tp)

            result = self._mt5.order_send(req)
            if result is None:
                return MT5OrderResult(
                    success=False,
                    retcode=-1,
                    error=f"MT5 returned None: {self._mt5.last_error()}",
                )

            return MT5OrderResult(
                success=result.retcode == self._mt5.TRADE_RETCODE_DONE,
                retcode=result.retcode,
                deal=getattr(result, "deal", 0),
                order=getattr(result, "order", 0),
                volume=getattr(result, "volume", 0.0),
                price=getattr(result, "price", 0.0),
                comment=getattr(result, "comment", ""),
                request=req,
            )

        return await asyncio.to_thread(_send)

    async def close_position(self, ticket: int, deviation: int = 10) -> MT5OrderResult:
        if not await self.health_check():
            return MT5OrderResult(success=False, error="MT5 not connected")

        def _close() -> MT5OrderResult:
            position = self._mt5.positions_get(ticket=ticket)
            if not position:
                return MT5OrderResult(success=False, error=f"Position {ticket} not found")
            pos = position[0]
            order_type = (
                self._mt5.ORDER_TYPE_SELL
                if pos.type == self._mt5.ORDER_TYPE_BUY
                else self._mt5.ORDER_TYPE_BUY
            )
            price = self._mt5.symbol_info_tick(pos.symbol).bid if order_type == self._mt5.ORDER_TYPE_SELL else self._mt5.symbol_info_tick(pos.symbol).ask
            req = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "price": price,
                "deviation": deviation,
            }
            result = self._mt5.order_send(req)
            return MT5OrderResult(
                success=getattr(result, "retcode", -1) == self._mt5.TRADE_RETCODE_DONE,
                retcode=getattr(result, "retcode", -1),
                deal=getattr(result, "deal", 0),
                comment=getattr(result, "comment", ""),
            )

        return await asyncio.to_thread(_close)


# Singleton
mt5_connector = MT5Connector()
