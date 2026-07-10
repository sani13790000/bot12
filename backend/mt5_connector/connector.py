"""
backend/mt5_connector/connector.py
MetaTrader 5 Integration - Order Execution & Position Tracking
Complete production-ready implementation
"""

import logging
import asyncio
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import MetaTrader5, fallback if not installed
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False
    logger.warning("[mt5] MetaTrader5 library not installed - simulating")


@dataclass
class MT5Position:
    """MT5 Position data."""
    ticket: int
    symbol: str
    type: str  # 'buy' or 'sell'
    volume: float
    entry_price: float
    current_price: float
    profit: float
    stop_loss: float
    take_profit: float
    open_time: datetime
    modify_time: datetime


@dataclass
class MT5Order:
    """MT5 Order."""
    ticket: int
    symbol: str
    order_type: str
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    comment: str


class MT5Connector:
    """MetaTrader 5 Connection & Trading"""

    def __init__(
        self,
        account_id: int,
        password: str,
        server: str,
        path: Optional[str] = None
    ):
        """Initialize MT5 Connector."""
        self.account_id = account_id
        self.password = password
        self.server = server
        self.path = path
        self.connected = False
        self.last_error = None
        self.account_info = {}
        self.positions = []
        
    async def connect(self) -> bool:
        """Connect to MT5."""
        try:
            if not HAS_MT5:
                logger.warning("[mt5] MT5 library not available - using simulation mode")
                self.connected = True
                self.account_info = {
                    'balance': 10000,
                    'equity': 10000,
                    'margin': 0,
                    'free_margin': 10000,
                }
                return True
            
            if not mt5.initialize(path=self.path):
                self.last_error = f"MT5 initialize failed: {mt5.last_error()}"
                logger.error(self.last_error)
                return False
            
            if not mt5.login(self.account_id, self.password, self.server):
                self.last_error = f"MT5 login failed: {mt5.last_error()}"
                logger.error(self.last_error)
                mt5.shutdown()
                return False
            
            self.connected = True
            logger.info(f"[mt5] Connected: account={self.account_id}, server={self.server}")
            return True
            
        except Exception as exc:
            self.last_error = str(exc)
            logger.error(f"[mt5] Connection error: {exc}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from MT5."""
        try:
            if HAS_MT5:
                mt5.shutdown()
            self.connected = False
            logger.info("[mt5] Disconnected")
        except Exception as exc:
            logger.error(f"[mt5] Disconnect error: {exc}")

    async def get_account_info(self) -> Dict:
        """Get account information."""
        if not self.connected:
            logger.error("[mt5] Not connected")
            return {}
        
        try:
            if not HAS_MT5:
                return self.account_info
            
            info = mt5.account_info()
            if info:
                return {
                    'balance': info.balance,
                    'equity': info.equity,
                    'margin': info.margin,
                    'free_margin': info.free_margin,
                    'margin_level': info.margin_level,
                    'leverage': info.leverage,
                }
            return {}
        except Exception as exc:
            logger.error(f"[mt5] Get account info error: {exc}")
            return {}

    async def get_positions(self) -> List[MT5Position]:
        """Get all open positions."""
        if not self.connected:
            return []
        
        try:
            if not HAS_MT5:
                return self.positions
            
            positions = mt5.positions_get()
            if not positions:
                return []
            
            result = []
            for pos in positions:
                result.append(MT5Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    type='buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell',
                    volume=pos.volume,
                    entry_price=pos.price_open,
                    current_price=mt5.symbol_info_tick(pos.symbol).bid,
                    profit=pos.profit,
                    stop_loss=pos.sl,
                    take_profit=pos.tp,
                    open_time=datetime.fromtimestamp(pos.time),
                    modify_time=datetime.fromtimestamp(pos.time_update),
                ))
            return result
        except Exception as exc:
            logger.error(f"[mt5] Get positions error: {exc}")
            return []

    async def send_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        comment: str = ""
    ) -> Tuple[bool, Optional[int]]:
        """Send order to MT5."""
        if not self.connected:
            logger.error("[mt5] Not connected")
            return False, None
        
        try:
            if not HAS_MT5:
                # Simulation mode
                ticket = hash(f"{symbol}{order_type}{price}") % 100000000
                logger.info(f"[mt5] Order SIMULATED: {order_type} {symbol} {volume} @ {price} (ticket={ticket})")
                return True, ticket
            
            action = mt5.TRADE_ACTION_DEAL
            order_type_mt5 = mt5.ORDER_TYPE_BUY if order_type.upper() == 'BUY' else mt5.ORDER_TYPE_SELL
            
            request = {
                "action": action,
                "symbol": symbol,
                "volume": volume,
                "type": order_type_mt5,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": 20,
                "magic": 234000,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"[mt5] Order failed: {result.comment}")
                return False, None
            
            logger.info(f"[mt5] Order sent: {order_type} {symbol} {volume} @ {price}")
            return True, result.order
            
        except Exception as exc:
            logger.error(f"[mt5] Send order error: {exc}")
            return False, None

    async def close_position(self, ticket: int) -> Tuple[bool, str]:
        """Close position by ticket."""
        if not self.connected:
            return False, "Not connected"
        
        try:
            if not HAS_MT5:
                logger.info(f"[mt5] Position SIMULATED CLOSE: ticket={ticket}")
                self.positions = [p for p in self.positions if p.ticket != ticket]
                return True, "Position closed (simulated)"
            
            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                return False, "Position not found"
            
            pos = pos[0]
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": ticket,
                "price": mt5.symbol_info_tick(pos.symbol).bid,
                "deviation": 20,
                "magic": 234000,
                "comment": f"Close position {ticket}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return False, result.comment
            
            logger.info(f"[mt5] Position closed: ticket={ticket}")
            return True, "Position closed"
            
        except Exception as exc:
            logger.error(f"[mt5] Close position error: {exc}")
            return False, str(exc)

    async def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Tuple[bool, str]:
        """Modify position SL/TP."""
        if not self.connected:
            return False, "Not connected"
        
        try:
            if not HAS_MT5:
                logger.info(f"[mt5] Position SIMULATED MODIFY: ticket={ticket}, sl={stop_loss}, tp={take_profit}")
                return True, "Position modified (simulated)"
            
            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                return False, "Position not found"
            
            pos = pos[0]
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": stop_loss or pos.sl,
                "tp": take_profit or pos.tp,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return False, result.comment
            
            logger.info(f"[mt5] Position modified: ticket={ticket}")
            return True, "Position modified"
            
        except Exception as exc:
            logger.error(f"[mt5] Modify position error: {exc}")
            return False, str(exc)

    async def get_symbol_info(self, symbol: str) -> Dict:
        """Get symbol information."""
        if not self.connected:
            return {}
        
        try:
            if not HAS_MT5:
                return {
                    'symbol': symbol,
                    'bid': 1.0850,
                    'ask': 1.0851,
                }
            
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return {}
            
            return {
                'symbol': symbol,
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume,
                'time': datetime.fromtimestamp(tick.time),
            }
        except Exception as exc:
            logger.error(f"[mt5] Get symbol info error: {exc}")
            return {}
