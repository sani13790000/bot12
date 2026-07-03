from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ..core.logger import get_logger
from .mt5_connector import MT5Connector, MT5Order
from .order_state_machine import OrderState, OrderStateMachine, get_order_state_machine

logger = get_logger('execution.execution_service')


class ExecutionError(RuntimeError):
    pass


class TradeRequest:
    def __init__(self, symbol, direction, volume, price=0.0, sl=0.0, tp=0.0, comment='', user_id='', strategy=''):
        self.request_id = str(uuid.uuid4())
        self.symbol = symbol
        self.direction = direction
        self.volume = volume
        self.price = price
        self.sl = sl
        self.tp = tp
        self.comment = comment
        self.user_id = user_id
        self.strategy = strategy
        self.created_at = datetime.now(timezone.utc)


class TradeResult:
    def __init__(self, request_id, ticket, success, fill_price=0.0, error=None):
        self.request_id = request_id
        self.ticket = ticket
        self.success = success
        self.fill_price = fill_price
        self.error = error
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self):
        return {'request_id': self.request_id, 'ticket': self.ticket, 'success': self.success, 'fill_price': self.fill_price, 'error': self.error, 'timestamp': self.timestamp.isoformat()}


class ExecutionService:
    def __init__(self, connector=None, demo=False):
        self._connector = connector or MT5Connector(demo=demo)
        self._demo = demo
        self._log = logger
        self._osm = None

    async def _get_osm(self):
        if self._osm is None:
            self._osm = await get_order_state_machine()
        return self._osm

    async def execute(self, req):
        osm = await self._get_osm()
        side = 'buy' if str(getattr(req.direction, 'value', req.direction)) == 'BUY' else 'sell'
        await osm.register(order_id=req.request_id, symbol=req.symbol, side=side, volume=req.volume, price=req.price, meta={'user_id': req.user_id, 'strategy': req.strategy})
        try:
            await osm.transition(req.request_id, OrderState.SUBMITTED)
            if not self._connector._session and not self._demo:
                await self._connector.connect()
            order = await self._connector.place_order(symbol=req.symbol, side=side, volume=req.volume, price=req.price, sl=req.sl, tp=req.tp, comment=req.comment)
            await osm.transition(req.request_id, OrderState.FILLED, mt5_ticket=order.ticket, fill_price=order.price, fill_volume=order.volume)
            self._log.info('EXEC OK | %s %s %.2f @ %.5f ticket=%d', side.upper(), req.symbol, req.volume, order.price, order.ticket)
            return TradeResult(request_id=req.request_id, ticket=order.ticket, success=True, fill_price=order.price)
        except Exception as exc:
            self._log.error('EXEC FAIL | req=%s | %s', req.request_id, exc)
            try:
                await osm.transition(req.request_id, OrderState.FAILED, error_msg=str(exc))
            except Exception:
                pass
            return TradeResult(request_id=req.request_id, ticket=None, success=False, error=str(exc))

    async def close_position(self, ticket, volume=None):
        if not self._connector._session and not self._demo:
            await self._connector.connect()
        return await self._connector.close_order(ticket, volume)

    async def get_account_info(self):
        if not self._connector._session and not self._demo:
            await self._connector.connect()
        return await self._connector.get_account_info()
