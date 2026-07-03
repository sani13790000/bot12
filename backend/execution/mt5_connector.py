"""
backend/execution/mt5_connector.py
Galaxy Vast AI — MT5 Connector

Connects to MetaTrader 5 via MetaApi or direct MT5 Python library.
Handles connection lifecycle, order placement, and position management.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("execution.mt5_connector")


@dataclass
class MT5Order:
    """Order to submit to MT5."""
    symbol:    str
    direction: str    # "BUY" | "SELL"
    volume:    float
    price:     float
    sl:        Optional[float] = None
    tp:        Optional[float] = None
    comment:   str             = "GalaxyVast"
    magic:     int             = 20260101


@dataclass
class MT5Result:
    """Result from MT5 operation."""
    success: bool
    ticket:  Optional[int]   = None
    price:   Optional[float] = None
    volume:  Optional[float] = None
    error:   Optional[str]   = None
    raw:     Optional[Dict[str, Any]] = field(default=None, repr=False)


class MT5Connector:
    """
    Async MT5 connector.

    Supports:
    - MetaApi cloud connection (recommended for production)
    - Direct MetaTrader5 Python library (Windows only)
    - Dry-run mode for testing
    """

    def __init__(
        self,
        account_id:  Optional[str] = None,
        api_token:   Optional[str] = None,
        server:      Optional[str] = None,
        login:       Optional[int] = None,
        password:    Optional[str] = None,
        dry_run:     bool          = False,
    ):
        self._account_id = account_id  or os.getenv("MT5_ACCOUNT_ID")
        self._api_token  = api_token   or os.getenv("METAAPI_TOKEN")
        self._server     = server      or os.getenv("MT5_SERVER")
        self._login      = login       or int(os.getenv("MT5_LOGIN", "0") or 0)
        self._password   = password    or os.getenv("MT5_PASSWORD")
        self._dry_run    = dry_run
        self._connected  = False
        self._api        = None  # MetaApi client instance
        self._account    = None  # MetaApi account instance

    async def connect(self) -> bool:
        """Establish connection to MT5."""
        if self._dry_run:
            self._connected = True
            logger.info("MT5 dry-run mode active")
            return True

        # Try MetaApi first
        try:
            from metaapi_cloud_sdk import MetaApi  # type: ignore
            self._api     = MetaApi(self._api_token)
            self._account = await self._api.metatrader_account_api.get_account(self._account_id)
            await self._account.deploy()
            await self._account.wait_connected(timeout_in_seconds=60)
            self._connected = True
            logger.info(f"Connected to MT5 via MetaApi: account={self._account_id}")
            return True
        except ImportError:
            logger.warning("metaapi_cloud_sdk not installed, trying direct MT5")
        except Exception as e:
            logger.error(f"MetaApi connection failed: {e}")

        # Try direct MT5 library
        try:
            import MetaTrader5 as mt5  # type: ignore
            if mt5.initialize(
                server   = self._server,
                login    = self._login,
                password = self._password,
            ):
                self._connected = True
                logger.info(f"Connected to MT5 directly: login={self._login}")
                return True
            else:
                logger.error(f"MT5 direct connect failed: {mt5.last_error()}")
        except ImportError:
            logger.warning("MetaTrader5 not installed")
        except Exception as e:
            logger.error(f"MT5 direct connect error: {e}")

        return False

    async def disconnect(self) -> None:
        """Disconnect from MT5."""
        if self._account:
            try:
                await self._account.undeploy()
            except Exception:
                pass
        if self._api:
            try:
                self._api.close()
            except Exception:
                pass
        self._connected = False
        logger.info("MT5 disconnected")

    async def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected

    async def place_order(self, order: MT5Order) -> MT5Result:
        """Place a trade order."""
        if self._dry_run:
            logger.info(f"DRY RUN place_order: {order}")
            return MT5Result(success=True, price=order.price, volume=order.volume, ticket=99999)

        if not self._connected:
            return MT5Result(success=False, error="Not connected to MT5")

        try:
            if self._account:
                # MetaApi path
                conn    = self._account.get_rpc_connection()
                await conn.connect()
                result  = await conn.create_market_buy_order(
                    symbol          = order.symbol,
                    volume          = order.volume,
                    stop_loss       = order.sl,
                    take_profit     = order.tp,
                    comment         = order.comment,
                ) if order.direction == "BUY" else await conn.create_market_sell_order(
                    symbol          = order.symbol,
                    volume          = order.volume,
                    stop_loss       = order.sl,
                    take_profit     = order.tp,
                    comment         = order.comment,
                )
                return MT5Result(
                    success = True,
                    ticket  = result.get("orderId"),
                    price   = result.get("openPrice"),
                    volume  = order.volume,
                    raw     = result,
                )
            else:
                # Direct MT5 path
                import MetaTrader5 as mt5  # type: ignore
                request = {
                    "action":   mt5.TRADE_ACTION_DEAL,
                    "symbol":   order.symbol,
                    "volume":   order.volume,
                    "type":     mt5.ORDER_TYPE_BUY if order.direction == "BUY" else mt5.ORDER_TYPE_SELL,
                    "price":    order.price,
                    "sl":       order.sl or 0.0,
                    "tp":       order.tp or 0.0,
                    "magic":    order.magic,
                    "comment":  order.comment,
                    "type_time":  mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return MT5Result(
                        success = True,
                        ticket  = result.order,
                        price   = result.price,
                        volume  = result.volume,
                    )
                else:
                    error = str(result.comment) if result else "unknown error"
                    return MT5Result(success=False, error=error)
        except Exception as e:
            logger.error(f"place_order error: {e}")
            return MT5Result(success=False, error=str(e))

    async def close_position(self, ticket: int, symbol: str, volume: float) -> MT5Result:
        """Close an existing position."""
        if self._dry_run:
            logger.info(f"DRY RUN close_position: ticket={ticket}")
            return MT5Result(success=True, ticket=ticket)

        try:
            if self._account:
                conn   = self._account.get_rpc_connection()
                await  conn.connect()
                result = await conn.close_position(str(ticket))
                return MT5Result(success=True, ticket=ticket, raw=result)
            else:
                import MetaTrader5 as mt5  # type: ignore
                position = mt5.positions_get(ticket=ticket)
                if not position:
                    return MT5Result(success=False, error=f"Position {ticket} not found")
                pos = position[0]
                close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                request = {
                    "action":   mt5.TRADE_ACTION_DEAL,
                    "symbol":   symbol,
                    "volume":   volume,
                    "type":     close_type,
                    "position": ticket,
                    "comment":  "GalaxyVast close",
                    "type_time":     mt5.ORDER_TIME_GTC,
                    "type_filling":  mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return MT5Result(success=True, ticket=ticket)
                return MT5Result(success=False, error=str(result.comment) if result else "unknown")
        except Exception as e:
            logger.error(f"close_position error: {e}")
            return MT5Result(success=False, error=str(e))

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open positions."""
        if self._dry_run:
            return []
        try:
            if self._account:
                conn      = self._account.get_rpc_connection()
                await     conn.connect()
                positions = await conn.get_positions(symbol=symbol)
                return positions or []
            else:
                import MetaTrader5 as mt5  # type: ignore
                if symbol:
                    positions = mt5.positions_get(symbol=symbol)
                else:
                    positions = mt5.positions_get()
                if positions is None:
                    return []
                return [
                    {
                        "ticket":  p.ticket,
                        "symbol":  p.symbol,
                        "volume":  p.volume,
                        "type":    "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                        "price":   p.price_open,
                        "sl":      p.sl,
                        "tp":      p.tp,
                        "profit":  p.profit,
                    }
                    for p in positions
                ]
        except Exception as e:
            logger.error(f"get_positions error: {e}")
            return []

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account balance and equity."""
        if self._dry_run:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        try:
            if self._account:
                conn = self._account.get_rpc_connection()
                await conn.connect()
                info = await conn.get_account_information()
                return info or {}
            else:
                import MetaTrader5 as mt5  # type: ignore
                info = mt5.account_info()
                if info:
                    return {
                        "balance":     info.balance,
                        "equity":      info.equity,
                        "margin":      info.margin,
                        "free_margin": info.margin_free,
                        "currency":    info.currency,
                        "leverage":    info.leverage,
                    }
                return {}
        except Exception as e:
            logger.error(f"get_account_info error: {e}")
            return {}
