from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger('risk.exposure_control')

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
except ImportError:  # pragma: no cover
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = 'FAIL_CLOSED'
        FAIL_OPEN   = 'FAIL_OPEN'
    def _coerce_fm(v):
        return v if isinstance(v, FailMode) else FailMode(str(v).upper())


@dataclass
class ExposureControlConfig:
    max_total_exposure_percent: float = 5.0
    max_per_currency_percent: float = 3.0
    max_per_symbol_percent: float = 2.0
    max_simultaneous_trades: int = 5
    max_buy_trades: int = 3
    max_sell_trades: int = 3
    block_same_symbol_same_direction: bool = True
    fail_mode: FailMode = FailMode.FAIL_CLOSED


@dataclass
class ExposurePosition:
    symbol: str
    direction: str
    risk_percent: float
    risk_usd: float


@dataclass
class ExposureSnapshot:
    total_risk_percent: float
    per_currency: Dict[str, float]
    per_symbol: Dict[str, float]
    open_trades: int
    buy_trades: int
    sell_trades: int
    can_open_new: bool
    block_reason: str


@dataclass
class ExposureCheckResult:
    can_trade: bool
    reason: str
    snapshot: ExposureSnapshot
    projected_total_risk: float


def _empty_snapshot():
    return ExposureSnapshot(
        total_risk_percent=0.0, per_currency={}, per_symbol={},
        open_trades=0, buy_trades=0, sell_trades=0,
        can_open_new=False, block_reason='',
    )


class ExposureControlEngine:
    """FIX #6: FAIL_CLOSED (default) or FAIL_OPEN on exception. Every exception logged."""

    _SYMBOL_CURRENCIES: Dict[str, List[str]] = {
        'EURUSD': ['EUR', 'USD'], 'GBPUSD': ['GBP', 'USD'],
        'AUDUSD': ['AUD', 'USD'], 'NZDUSD': ['NZD', 'USD'],
        'USDCHF': ['USD', 'CHF'], 'USDJPY': ['USD', 'JPY'],
        'USDCAD': ['USD', 'CAD'], 'EURGBP': ['EUR', 'GBP'],
        'EURJPY': ['EUR', 'JPY'], 'GBPJPY': ['GBP', 'JPY'],
        'XAUUSD': ['XAU', 'USD'], 'XAGUSD': ['XAG', 'USD'],
        'BTCUSD': ['BTC', 'USD'], 'ETHUSD': ['ETH', 'USD'],
    }

    def __init__(self, config=None, fail_mode=None):
        self._cfg = config or ExposureControlConfig()
        _fm = fail_mode if fail_mode is not None else self._cfg.fail_mode
        self._fail_mode: FailMode = _coerce_fm(_fm)

    def check(self, new_symbol, new_direction, new_risk_percent, open_positions, balance):
        """FIX #6: wraps _check_inner() -- exceptions handled per fail_mode."""
        try:
            return self._check_inner(new_symbol, new_direction, new_risk_percent, open_positions, balance)
        except Exception as exc:
            logger.critical(
                'ExposureControlEngine.check exception symbol=%s fail_mode=%s: %s',
                new_symbol, self._fail_mode, exc, exc_info=True,
            )
            snap = _empty_snapshot()
            if self._fail_mode is FailMode.FAIL_CLOSED:
                snap.block_reason = 'EXPOSURE_CHECK_ERROR:' + type(exc).__name__
                return ExposureCheckResult(
                    can_trade=False,
                    reason='FAIL_CLOSED:EXPOSURE_CHECK_ERROR:' + type(exc).__name__,
                    snapshot=snap, projected_total_risk=0.0,
                )
            logger.critical(
                'FAIL_OPEN: ExposureControlEngine exception swallowed, trade ALLOWED. symbol=%s fail_mode=%s',
                new_symbol, self._fail_mode,
            )
            snap.can_open_new = True
            return ExposureCheckResult(
                can_trade=True,
                reason='FAIL_OPEN:EXPOSURE_CHECK_ERROR:' + type(exc).__name__,
                snapshot=snap, projected_total_risk=new_risk_percent,
            )

    def _check_inner(self, new_symbol, new_direction, new_risk_percent, open_positions, balance):
        snapshot = self._build_snapshot(open_positions, balance)
        if snapshot.open_trades >= self._cfg.max_simultaneous_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = 'MAX_TRADES ' + str(snapshot.open_trades) + '/' + str(self._cfg.max_simultaneous_trades)
            return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=0.0)
        if new_direction == 'BUY' and snapshot.buy_trades >= self._cfg.max_buy_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = 'MAX_BUY_TRADES ' + str(snapshot.buy_trades)
            return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=0.0)
        if new_direction == 'SELL' and snapshot.sell_trades >= self._cfg.max_sell_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = 'MAX_SELL_TRADES ' + str(snapshot.sell_trades)
            return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=0.0)
        if self._cfg.block_same_symbol_same_direction:
            for pos in open_positions:
                if pos.symbol == new_symbol and pos.direction == new_direction:
                    snapshot.can_open_new = False
                    snapshot.block_reason = 'DUPLICATE ' + new_symbol + ' ' + new_direction
                    return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=0.0)
        projected_total = snapshot.total_risk_percent + new_risk_percent
        if projected_total > self._cfg.max_total_exposure_percent:
            snapshot.can_open_new = False
            snapshot.block_reason = 'MAX_EXPOSURE ' + format(projected_total, '.1f') + '%>' + str(self._cfg.max_total_exposure_percent) + '%'
            return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=projected_total)
        sym_risk = snapshot.per_symbol.get(new_symbol, 0.0) + new_risk_percent
        if sym_risk > self._cfg.max_per_symbol_percent:
            snapshot.can_open_new = False
            snapshot.block_reason = 'MAX_SYMBOL_EXPOSURE ' + new_symbol + ' ' + format(sym_risk, '.1f') + '%'
            return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=projected_total)
        currencies = self._SYMBOL_CURRENCIES.get(new_symbol.upper(), [])
        for ccy in currencies:
            ccy_risk = snapshot.per_currency.get(ccy, 0.0) + new_risk_percent
            if ccy_risk > self._cfg.max_per_currency_percent:
                snapshot.can_open_new = False
                snapshot.block_reason = 'MAX_CURRENCY_EXPOSURE ' + ccy + ' ' + format(ccy_risk, '.1f') + '%'
                return ExposureCheckResult(can_trade=False, reason=snapshot.block_reason, snapshot=snapshot, projected_total_risk=projected_total)
        snapshot.can_open_new = True
        snapshot.block_reason = ''
        return ExposureCheckResult(
            can_trade=True,
            reason='EXPOSURE_OK total=' + format(projected_total, '.1f') + '%',
            snapshot=snapshot, projected_total_risk=projected_total,
        )

    def _build_snapshot(self, positions, balance):
        total_risk = sum(p.risk_percent for p in positions)
        per_ccy = {}
        per_sym = {}
        buys = sells = 0
        for p in positions:
            per_sym[p.symbol] = per_sym.get(p.symbol, 0.0) + p.risk_percent
            for ccy in self._SYMBOL_CURRENCIES.get(p.symbol.upper(), []):
                per_ccy[ccy] = per_ccy.get(ccy, 0.0) + p.risk_percent
            if p.direction == 'BUY':
                buys += 1
            else:
                sells += 1
        return ExposureSnapshot(
            total_risk_percent=round(total_risk, 3),
            per_currency={k: round(v, 3) for k, v in per_ccy.items()},
            per_symbol={k: round(v, 3) for k, v in per_sym.items()},
            open_trades=len(positions), buy_trades=buys, sell_trades=sells,
            can_open_new=True, block_reason='',
        )


_exposure_engine = None

def get_exposure_control():
    global _exposure_engine
    if _exposure_engine is None:
        _exposure_engine = ExposureControlEngine()
    return _exposure_engine
