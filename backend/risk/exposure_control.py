"""backend/risk/exposure_control.py
FIX #6 - Fail-Closed Mode (surgical patch)

Changes:
  FIX-6A: ExposureControlConfig gets fail_mode field (default FAIL_CLOSED)
  FIX-6B: ExposureControlEngine.check() wraps _check_inner() with try/except
  FIX-6C: FAIL_CLOSED blocks, FAIL_OPEN allows + CRITICAL log
  FIX-6D: every exception logged with exc_info=True

Phase Q Fix Q-11: _SYMBOL_CURRENCIES expanded from 14 to 38 symbols.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fail_mode
except ImportError:
    from enum import Enum

    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce_fail_mode(v) -> FailMode:
        if isinstance(v, FailMode):
            return v
        return FailMode(str(v).upper())

logger = logging.getLogger("risk.exposure_control")


@dataclass
class ExposureControlConfig:
    max_total_exposure_percent:       float = 5.0
    max_per_currency_percent:         float = 3.0
    max_per_symbol_percent:           float = 2.0
    max_simultaneous_trades:          int   = 5
    max_buy_trades:                   int   = 3
    max_sell_trades:                  int   = 3
    block_same_symbol_same_direction: bool  = True
    fail_mode: FailMode = FailMode.FAIL_CLOSED


@dataclass
class ExposurePosition:
    symbol:       str
    direction:    str
    risk_percent: float
    risk_usd:     float = 0.0


@dataclass
class ExposureSnapshot:
    total_risk_percent: float
    per_currency:       Dict[str, float]
    per_symbol:         Dict[str, float]
    open_trades:        int
    buy_trades:         int
    sell_trades:        int
    can_open_new:       bool
    block_reason:       str


@dataclass
class ExposureCheckResult:
    can_trade:        bool
    reason:           str
    snapshot:         ExposureSnapshot
    projected_total_risk: float


_FAIL_CLOSED_SNAP = ExposureSnapshot(
    total_risk_percent=0.0, per_currency={}, per_symbol={},
    open_trades=0, buy_trades=0, sell_trades=0,
    can_open_new=False, block_reason="FAIL_CLOSED:EXCEPTION",
)


class ExposureControlEngine:
    _SYMBOL_CURRENCIES: Dict[str, List[str]] = {
        "EURUSD": ["EUR","USD"], "GBPUSD": ["GBP","USD"],
        "AUDUSD": ["AUD","USD"], "NZDUSD": ["NZD","USD"],
        "USDCHF": ["USD","CHF"], "USDJPY": ["USD","JPY"],
        "USDCAD": ["USD","CAD"],
        "EURGBP": ["EUR","GBP"], "EURJPY": ["EUR","JPY"],
        "EURCHF": ["EUR","CHF"], "EURCAD": ["EUR","CAD"],
        "EURAUD": ["EUR","AUD"], "EURNZD": ["EUR","NZD"],
        "GBPJPY": ["GBP","JPY"], "GBPCHF": ["GBP","CHF"],
        "GBPCAD": ["GBP","CAD"], "GBPAUD": ["GBP","AUD"],
        "GBPNZD": ["GBP","NZD"],
        "AUDJPY": ["AUD","JPY"], "AUDCAD": ["AUD","CAD"],
        "AUDCHF": ["AUD","CHF"], "AUDNZD": ["AUD","NZD"],
        "NZDJPY": ["NZD","JPY"], "NZDCAD": ["NZD","CAD"],
        "CADJPY": ["CAD","JPY"], "CADCHF": ["CAD","CHF"],
        "CHFJPY": ["CHF","JPY"],
        "XAUUSD": ["XAU","USD"], "XAGUSD": ["XAG","USD"],
        "XPTUSD": ["XPT","USD"], "XPDUSD": ["XPD","USD"],
        "BTCUSD": ["BTC","USD"], "ETHUSD": ["ETH","USD"],
        "LTCUSD": ["LTC","USD"], "XRPUSD": ["XRP","USD"],
        "US30":   ["USD"],        "US500":  ["USD"],
        "NAS100": ["USD"],
    }

    def __init__(
        self,
        config: Optional[ExposureControlConfig] = None,
        fail_mode: Optional[FailMode] = None,
    ) -> None:
        self._cfg = config or ExposureControlConfig()
        self._fail_mode = (
            _coerce_fail_mode(fail_mode)
            if fail_mode is not None
            else _coerce_fail_mode(self._cfg.fail_mode)
        )

    def _get_currencies(self, symbol: str) -> List[str]:
        key = symbol.upper()
        return self._SYMBOL_CURRENCIES.get(
            key, [key[:3], key[3:]] if len(key) == 6 else [key]
        )

    def check(
        self,
        new_symbol:      str,
        new_direction:   str,
        new_risk_percent: float,
        open_positions:  List[ExposurePosition],
    ) -> ExposureCheckResult:
        try:
            return self._check_inner(new_symbol, new_direction, new_risk_percent, open_positions)
        except Exception as exc:
            logger.critical(
                "ExposureControlEngine.check() EXCEPTION symbol=%s direction=%s "
                "fail_mode=%s error=%s",
                new_symbol, new_direction, self._fail_mode, exc,
                exc_info=True,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return ExposureCheckResult(
                    can_trade=False,
                    reason=f"FAIL_CLOSED:EXPOSURE_GATE_ERROR:{type(exc).__name__}",
                    snapshot=_FAIL_CLOSED_SNAP,
                    projected_total_risk=0.0,
                )
            return ExposureCheckResult(
                can_trade=True,
                reason=f"FAIL_OPEN:EXPOSURE_GATE_ERROR:{type(exc).__name__}",
                snapshot=ExposureSnapshot(
                    total_risk_percent=0.0, per_currency={}, per_symbol={},
                    open_trades=0, buy_trades=0, sell_trades=0,
                    can_open_new=True, block_reason="FAIL_OPEN_EXCEPTION_IGNORED",
                ),
                projected_total_risk=0.0,
            )

    def _check_inner(
        self,
        new_symbol:      str,
        new_direction:   str,
        new_risk_percent: float,
        open_positions:  List[ExposurePosition],
    ) -> ExposureCheckResult:
        cfg = self._cfg
        new_symbol    = new_symbol.upper()
        new_direction = new_direction.upper()
        total_risk  = sum(p.risk_percent for p in open_positions)
        per_currency: Dict[str, float] = {}
        per_symbol:   Dict[str, float] = {}
        buy_count = sell_count = 0
        for p in open_positions:
            sym = p.symbol.upper()
            per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
            for ccy in self._get_currencies(sym):
                per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
            if p.direction.upper() == "BUY":
                buy_count += 1
            else:
                sell_count += 1
        projected_total = total_risk + new_risk_percent
        projected_sym   = per_symbol.get(new_symbol, 0.0) + new_risk_percent
        projected_ccy   = {
            ccy: per_currency.get(ccy, 0.0) + new_risk_percent
            for ccy in self._get_currencies(new_symbol)
        }
        new_buy_count  = buy_count  + (1 if new_direction == "BUY"  else 0)
        new_sell_count = sell_count + (1 if new_direction == "SELL" else 0)
        new_total      = len(open_positions) + 1
        snap = ExposureSnapshot(
            total_risk_percent=total_risk, per_currency=per_currency,
            per_symbol=per_symbol, open_trades=len(open_positions),
            buy_trades=buy_count, sell_trades=sell_count,
            can_open_new=True, block_reason="",
        )
        if projected_total > cfg.max_total_exposure_percent:
            msg = (f"Total exposure {projected_total:.2f}% > "
                   f"limit {cfg.max_total_exposure_percent}%")
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if projected_sym > cfg.max_per_symbol_percent:
            msg = (f"Symbol {new_symbol} exposure {projected_sym:.2f}% > "
                   f"limit {cfg.max_per_symbol_percent}%")
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        for ccy, val in projected_ccy.items():
            if val > cfg.max_per_currency_percent:
                msg = (f"Currency {ccy} exposure {val:.2f}% > "
                       f"limit {cfg.max_per_currency_percent}%")
                snap.can_open_new = False; snap.block_reason = msg
                return ExposureCheckResult(False, msg, snap, projected_total)
        if new_total > cfg.max_simultaneous_trades:
            msg = f"Max simultaneous trades {cfg.max_simultaneous_trades} reached"
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if new_buy_count > cfg.max_buy_trades:
            msg = f"Max BUY trades {cfg.max_buy_trades} reached"
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if new_sell_count > cfg.max_sell_trades:
            msg = f"Max SELL trades {cfg.max_sell_trades} reached"
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if cfg.block_same_symbol_same_direction:
            for p in open_positions:
                if p.symbol.upper() == new_symbol and p.direction.upper() == new_direction:
                    msg = f"Duplicate {new_direction} on {new_symbol} blocked"
                    snap.can_open_new = False; snap.block_reason = msg
                    return ExposureCheckResult(False, msg, snap, projected_total)
        return ExposureCheckResult(True, "", snap, projected_total)

    def get_snapshot(self, open_positions: List[ExposurePosition]) -> ExposureSnapshot:
        try:
            total_risk  = sum(p.risk_percent for p in open_positions)
            per_currency: Dict[str, float] = {}
            per_symbol:   Dict[str, float] = {}
            buy_count = sell_count = 0
            for p in open_positions:
                sym = p.symbol.upper()
                per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
                for ccy in self._get_currencies(sym):
                    per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
                if p.direction.upper() == "BUY":
                    buy_count += 1
                else:
                    sell_count += 1
            return ExposureSnapshot(
                total_risk_percent=total_risk, per_currency=per_currency,
                per_symbol=per_symbol, open_trades=len(open_positions),
                buy_trades=buy_count, sell_trades=sell_count,
                can_open_new=total_risk < self._cfg.max_total_exposure_percent,
                block_reason="",
            )
        except Exception as exc:
            logger.critical("ExposureControlEngine.get_snapshot() EXCEPTION fail_mode=%s error=%s",
                            self._fail_mode, exc, exc_info=True)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return _FAIL_CLOSED_SNAP
            return ExposureSnapshot(
                total_risk_percent=0.0, per_currency={}, per_symbol={},
                open_trades=0, buy_trades=0, sell_trades=0,
                can_open_new=True, block_reason="FAIL_OPEN_SNAPSHOT_ERROR",
            )


_engine: Optional[ExposureControlEngine] = None

def get_exposure_control() -> ExposureControlEngine:
    global _engine
    if _engine is None:
        _engine = ExposureControlEngine()
    return _engine
