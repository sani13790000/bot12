"""backend/risk/margin_gate.py
PHASE-4: Real margin check before order submission.

Checks:
  1. free_margin >= required_margin
  2. margin_level >= MIN_MARGIN_LEVEL_PCT
  3. margin_call zone warning
  4. MT5 live or static table fallback

Fail-closed: blocks if MT5 unavailable (conservative mode).
"""
from __future__ import annotations
import asyncio, math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:
    from ..core.logger import get_logger
    logger = get_logger('risk.margin_gate')
except Exception:
    import logging
    logger = logging.getLogger('risk.margin_gate')

try:
    from .fail_mode import FailMode, coerce as coerce_fail_mode
except Exception:
    from enum import Enum
    class FailMode(str, Enum):
        FAIL_CLOSED = 'FAIL_CLOSED'
        FAIL_OPEN   = 'FAIL_OPEN'
    def coerce_fail_mode(v):
        return FailMode(str(v).upper().strip()) if not isinstance(v, FailMode) else v

_MIN_MARGIN_LEVEL_PCT: float  = 150.0
_MARGIN_CALL_LEVEL_PCT: float = 200.0
_DEFAULT_MARGIN_PCT: float    = 2.0

_STATIC_MARGIN_TABLE: Dict[str, float] = {
    'EURUSD':1.0,'GBPUSD':1.0,'AUDUSD':1.0,'NZDUSD':1.0,
    'USDCAD':1.0,'USDCHF':1.0,'USDJPY':1.0,
    'EURGBP':1.0,'EURJPY':1.0,'EURAUD':1.0,'GBPJPY':1.0,
    'XAUUSD':2.0,'XAGUSD':5.0,
    'US30':0.5,'US500':0.5,'NAS100':0.5,'GER40':1.0,'UK100':1.0,
    'BTCUSD':10.0,'ETHUSD':10.0,
    'USOIL':2.0,'UKOIL':2.0,
}

@dataclass
class MarginCheckResult:
    can_trade: bool
    reason: str = ''
    required_margin: float = 0.0
    free_margin: float = 0.0
    margin_level_pct: float = 0.0
    margin_call_warning: bool = False
    source: str = 'static'


class MarginGate:
    """
    Verifies sufficient free margin before an order.

    Args:
        mt5_connector:        Optional MT5Connector for live margin queries.
        min_margin_level_pct: Override default 150% level.
        fail_mode:            FAIL_CLOSED (block if MT5 unavailable) or FAIL_OPEN.
    """
    def __init__(self, mt5_connector: Any = None,
                 min_margin_level_pct: float = _MIN_MARGIN_LEVEL_PCT,
                 fail_mode: FailMode = FailMode.FAIL_CLOSED) -> None:
        self._mt5 = mt5_connector
        self._min_margin_level = min_margin_level_pct
        self._fail_mode = coerce_fail_mode(fail_mode)

    async def check(self, symbol: str, lot_size: float, balance: float,
                    equity: float, free_margin: float, used_margin: float = 0.0,
                    *, direction: str = 'BUY') -> MarginCheckResult:
        if not math.isfinite(equity) or equity <= 0:
            return MarginCheckResult(can_trade=False, reason='equity_invalid',
                                     free_margin=free_margin)
        if not math.isfinite(free_margin) or free_margin < 0:
            return MarginCheckResult(can_trade=False, reason='free_margin_invalid',
                                     free_margin=free_margin)

        required, source = await self._required_margin(symbol, lot_size, balance, direction)
        total_used = used_margin + required
        margin_level = (equity / total_used * 100.0) if total_used > 0 else 9999.0
        margin_call_warning = margin_level < _MARGIN_CALL_LEVEL_PCT

        if free_margin < required:
            logger.warning('Margin gate BLOCK: insufficient free margin',
                           symbol=symbol, required=required, free_margin=free_margin)
            return MarginCheckResult(
                can_trade=False,
                reason=f'insufficient_free_margin: need {required:.2f} have {free_margin:.2f}',
                required_margin=required, free_margin=free_margin,
                margin_level_pct=margin_level, margin_call_warning=margin_call_warning,
                source=source)

        if margin_level < self._min_margin_level:
            logger.warning('Margin gate BLOCK: margin level too low',
                           symbol=symbol, margin_level=margin_level,
                           threshold=self._min_margin_level)
            return MarginCheckResult(
                can_trade=False,
                reason=f'margin_level_too_low: {margin_level:.1f}% < {self._min_margin_level:.1f}%',
                required_margin=required, free_margin=free_margin,
                margin_level_pct=margin_level, margin_call_warning=True,
                source=source)

        if margin_call_warning:
            logger.warning('Margin call zone', symbol=symbol, margin_level=margin_level)

        return MarginCheckResult(
            can_trade=True, reason='ok', required_margin=required,
            free_margin=free_margin, margin_level_pct=margin_level,
            margin_call_warning=margin_call_warning, source=source)

    async def _required_margin(self, symbol: str, lot_size: float,
                                balance: float, direction: str) -> Tuple[float, str]:
        sym = symbol.upper().strip()
        if self._mt5 is not None:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._mt5.order_calc_margin,
                                      symbol, lot_size, direction), timeout=3.0)
                if result is not None and math.isfinite(result) and result > 0:
                    return result, 'mt5'
            except asyncio.TimeoutError:
                logger.debug('MT5 margin calc timeout', symbol=symbol)
            except Exception as exc:
                logger.debug('MT5 margin calc failed', symbol=symbol, error=str(exc))

        margin_pct = _STATIC_MARGIN_TABLE.get(sym, _DEFAULT_MARGIN_PCT)
        contract_size = 100_000.0 if sym.isalpha() and len(sym) == 6 else 10_000.0
        notional = lot_size * contract_size
        required = notional * (margin_pct / 100.0)
        if self._fail_mode == FailMode.FAIL_CLOSED:
            required *= 1.20
            source = 'static_conservative'
        else:
            source = 'static'
        return required, source


_gate: Optional[MarginGate] = None

def get_margin_gate(mt5_connector: Any = None,
                   min_margin_level_pct: float = _MIN_MARGIN_LEVEL_PCT,
                   fail_mode: FailMode = FailMode.FAIL_CLOSED) -> MarginGate:
    global _gate
    if _gate is None:
        _gate = MarginGate(mt5_connector=mt5_connector,
                           min_margin_level_pct=min_margin_level_pct,
                           fail_mode=fail_mode)
    return _gate
