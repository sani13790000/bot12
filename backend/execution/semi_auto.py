"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Automatic Trading

Semi-auto mode: AI generates signals, human confirms before execution.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class PendingTrade:
    id: str
    symbol: str
    direction: str
    lots: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    approved: Optional[bool] = None


class SemiAutoTrader:
    """Semi-automatic trade approval system."""

    def __init__(self, approval_timeout: float = 300.0) -> None:
        self._pending: Dict[str, PendingTrade] = {}
        self._timeout = approval_timeout
        self._callbacks: List[Callable] = []

    async def propose_trade(self, trade_data: Dict[str, Any]) -> str:
        import uuid
        trade_id = str(uuid.uuid4())[:8]
        trade = PendingTrade(
            id=trade_id,
            symbol=trade_data['symbol'],
            direction=trade_data['direction'],
            lots=trade_data.get('lots', 0.01),
            stop_loss=trade_data.get('stop_loss'),
            take_profit=trade_data.get('take_profit'),
            expires_at=time.time() + self._timeout,
        )
        self._pending[trade_id] = trade
        _LOG.info('Trade proposed: %s %s %s (id=%s)', trade.symbol, trade.direction, trade.lots, trade_id)
        for cb in self._callbacks:
            try:
                await cb(trade)
            except Exception as e:
                _LOG.debug('Callback error: %s', e)
        return trade_id

    async def approve(self, trade_id: str) -> bool:
        trade = self._pending.get(trade_id)
        if not trade:
            return False
        if trade.expires_at and time.time() > trade.expires_at:
            del self._pending[trade_id]
            _LOG.warning('Trade %s expired', trade_id)
            return False
        trade.approved = True
        _LOG.info('Trade %s approved', trade_id)
        return True

    async def reject(self, trade_id: str) -> bool:
        trade = self._pending.get(trade_id)
        if not trade:
            return False
        trade.approved = False
        del self._pending[trade_id]
        _LOG.info('Trade %s rejected', trade_id)
        return True

    def get_pending(self) -> List[PendingTrade]:
        now = time.time()
        expired = [tid for tid, t in self._pending.items() if t.expires_at and now > t.expires_at]
        for tid in expired:
            del self._pending[tid]
        return list(self._pending.values())

    def on_proposal(self, callback: Callable) -> None:
        self._callbacks.append(callback)


_trader: Optional[SemiAutoTrader] = None


def get_semi_auto_trader() -> SemiAutoTrader:
    global _trader
    if _trader is None:
        _trader = SemiAutoTrader()
    return _trader
