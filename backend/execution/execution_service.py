"""
backend/execution/execution_service.py
Enterprise Execution Service — Order lifecycle management

Flow: validate → MT5 place → state machine → journal
"""
from __future__ import annotations

import logging, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ExecutionRequest:
    symbol:    str
    direction: str
    volume:    float
    price:     Optional[float] = None
    sl:        Optional[float] = None
    tp:        Optional[float] = None
    comment:   str             = ""
    strategy:  str             = "MANUAL"
    user_id:   Optional[str]   = None


@dataclass
class ExecutionResponse:
    success:    bool
    order_id:   Optional[int]
    open_price: Optional[float]
    message:    str
    demo:       bool  = True
    ts:         float = field(default_factory=time.time)


class ExecutionService:
    """High-level execution service wrapping MT5Connector."""

    def __init__(self, connector=None, state_machine=None) -> None:
        self._mt5              = connector
        self._osm              = state_machine
        self._lazy_init_done   = False

    def _lazy_init(self) -> None:
        if self._lazy_init_done:
            return
        if self._mt5 is None:
            from backend.execution.mt5_connector import get_connector
            self._mt5 = get_connector()
        if self._osm is None:
            try:
                from backend.execution.order_state_machine import OrderStateMachineCompat
                self._osm = OrderStateMachineCompat.get_instance()
            except ImportError:
                self._osm = None
        self._lazy_init_done = True

    async def execute(self, req: ExecutionRequest) -> ExecutionResponse:
        self._lazy_init()
        try:
            self._validate(req)
        except ValueError as exc:
            return ExecutionResponse(success=False, order_id=None,
                                     open_price=None, message=str(exc))
        try:
            from backend.execution.mt5_connector import TradeRequest, OrderType
            trade_req = TradeRequest(
                symbol=req.symbol, order_type=OrderType(req.direction),
                volume=req.volume, price=req.price, sl=req.sl, tp=req.tp,
                comment=req.comment[:31],
            )
            async with self._mt5 as mt5:
                result = await mt5.place_order(trade_req)
        except Exception as exc:
            log.error("MT5 place_order failed: %s", exc)
            return ExecutionResponse(success=False, order_id=None,
                                     open_price=None, message=f"MT5 error: {exc}")
        if self._osm:
            try:
                self._osm.create_order(
                    order_id=str(result.order_id), symbol=req.symbol,
                    direction=req.direction, volume=req.volume,
                    price=result.open_price, sl=req.sl, tp=req.tp,
                    strategy=req.strategy, user_id=req.user_id,
                )
            except Exception as exc:
                log.warning("OSM registration failed: %s", exc)
        return ExecutionResponse(success=True, order_id=result.order_id,
                                 open_price=result.open_price, message="OK",
                                 demo=result.demo)

    async def close(self, order_id: int, volume: Optional[float] = None) -> bool:
        self._lazy_init()
        async with self._mt5 as mt5:
            ok = await mt5.close_position(order_id, volume)
        if ok and self._osm:
            try:
                self._osm.close_order(str(order_id))
            except Exception:
                pass
        return ok

    async def modify(self, order_id: int,
                     sl: Optional[float] = None,
                     tp: Optional[float] = None) -> bool:
        self._lazy_init()
        async with self._mt5 as mt5:
            return await mt5.modify_position(order_id, sl=sl, tp=tp)

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        self._lazy_init()
        async with self._mt5 as mt5:
            positions = await mt5.get_positions(symbol)
        return [{"ticket": p.ticket, "symbol": p.symbol, "type": p.order_type.value,
                 "volume": p.volume, "open_price": p.open_price,
                 "current_price": p.current_price, "profit": p.profit,
                 "sl": p.sl, "tp": p.tp} for p in positions]

    @staticmethod
    def _validate(req: ExecutionRequest) -> None:
        if not req.symbol:
            raise ValueError("symbol is required")
        if req.direction not in ("BUY", "SELL"):
            raise ValueError(f"invalid direction: {req.direction!r}")
        if req.volume <= 0:
            raise ValueError(f"volume must be positive, got {req.volume}")
        if req.volume > 100:
            raise ValueError(f"volume {req.volume} exceeds max 100 lots")


_service: Optional[ExecutionService] = None


def get_service() -> ExecutionService:
    global _service
    if _service is None:
        _service = ExecutionService()
    return _service
