"""backend/risk/exposure_control.py
FIX #6 - Fail-Closed Mode (surgical patch)

Changes:
  FIX-6F: check() wrapped in try/except
  FIX-6G: __init__ accepts fail_mode (default FAIL_CLOSED)
  FIX-6H: get_snapshot() wrapped in try/except
  FIX-6D: all exceptions logged exc_info=True

Backward compat:
  - ExposureControlEngine() no args works
  - check() signature unchanged
  - get_snapshot() signature unchanged
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("risk.exposure")


class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


@dataclass
class ExposureControlConfig:
    max_total_exposure_percent: float = 5.0
    max_per_currency_percent:   float = 3.0
    max_per_symbol_percent:     float = 2.0
    max_simultaneous_trades:    int   = 5
    max_buy_trades:             int   = 3
    max_sell_trades:            int   = 3
    block_same_symbol_same_direction: bool = True


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
    can_trade:            bool
    reason:               str
    snapshot:             ExposureSnapshot
    projected_total_risk: float


def _blocked_snapshot(reason: str) -> ExposureSnapshot:
    return ExposureSnapshot(
        total_risk_percent=0.0, per_currency={}, per_symbol={},
        open_trades=0, buy_trades=0, sell_trades=0,
        can_open_new=False, block_reason=reason,
    )


def _open_snapshot() -> ExposureSnapshot:
    return ExposureSnapshot(
        total_risk_percent=0.0, per_currency={}, per_symbol={},
        open_trades=0, buy_trades=0, sell_trades=0,
        can_open_new=True, block_reason="FAIL_OPEN_EXCEPTION_IGNORED",
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
        "US30":   ["USD"],       "US500":  ["USD"],
        "NAS100": ["USD"],
    }

    def __init__(
        self,
        config:    Optional[ExposureControlConfig] = None,
        fail_mode: FailMode = FailMode.FAIL_CLOSED,
    ):
        self._cfg       = config or ExposureControlConfig()
        self._fail_mode = fail_mode if isinstance(fail_mode, FailMode) else FailMode(fail_mode)

    def _get_currencies(self, symbol: str) -> List[str]:
        key = symbol.upper()
        return self._SYMBOL_CURRENCIES.get(
            key, [key[:3], key[3:]] if len(key) == 6 else [key]
        )

    def check(
        self,
        new_symbol:       str,
        new_direction:    str,
        new_risk_percent: float,
        open_positions:   List[ExposurePosition],
    ) -> ExposureCheckResult:
        try:
            return self._check_inner(new_symbol, new_direction, new_risk_percent, open_positions)
        except Exception as exc:
            logger.exception(
                "ExposureControlEngine.check() raised %s symbol=%s [fail_mode=%s]: %s",
                type(exc).__name__, new_symbol, self._fail_mode.value, exc,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                reason = f"FAIL_CLOSED:EXPOSURE_INTERNAL_ERROR:{type(exc).__name__}"
                return ExposureCheckResult(
                    can_trade=False, reason=reason,
                    snapshot=_blocked_snapshot(reason), projected_total_risk=0.0,
                )
            logger.critical(
                "FAIL_OPEN: ExposureControl exception swallowed, trade ALLOWED. symbol=%s", new_symbol
            )
            return ExposureCheckResult(
                can_trade=True, reason="FAIL_OPEN_EXCEPTION_IGNORED",
                snapshot=_open_snapshot(), projected_total_risk=new_risk_percent,
            )

    def _check_inner(
        self,
        new_symbol:       str,
        new_direction:    str,
        new_risk_percent: float,
        open_positions:   List[ExposurePosition],
    ) -> ExposureCheckResult:
        cfg           = self._cfg
        new_symbol    = new_symbol.upper()
        new_direction = new_direction.upper()
        total_risk:   float            = sum(p.risk_percent for p in open_positions)
        per_currency: Dict[str, float] = {}
        per_symbol:   Dict[str, float] = {}
        buy_count = sell_count = 0
        for p in open_positions:
            sym = p.symbol.upper()
            per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
            for ccy in self._get_currencies(sym):
                per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
            if p.direction.upper() == "BUY": buy_count += 1
            else: sell_count += 1
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
        def _block(msg: str) -> ExposureCheckResult:
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if projected_total > cfg.max_total_exposure_percent:
            return _block(f"Total exposure {projected_total:.2f}% > limit {cfg.max_total_exposure_percent}%")
        if projected_sym > cfg.max_per_symbol_percent:
            return _block(f"Symbol {new_symbol} exposure {projected_sym:.2f}% > limit {cfg.max_per_symbol_percent}%")
        for ccy, val in projected_ccy.items():
            if val > cfg.max_per_currency_percent:
                return _block(f"Currency {ccy} exposure {val:.2f}% > limit {cfg.max_per_currency_percent}%")
        if new_total > cfg.max_simultaneous_trades:
            return _block(f"Max simultaneous trades {cfg.max_simultaneous_trades} reached")
        if new_buy_count > cfg.max_buy_trades:
            return _block(f"Max BUY trades {cfg.max_buy_trades} reached")
        if new_sell_count > cfg.max_sell_trades:
            return _block(f"Max SELL trades {cfg.max_sell_trades} reached")
        if cfg.block_same_symbol_same_direction:
            for p in open_positions:
                if p.symbol.upper() == new_symbol and p.direction.upper() == new_direction:
                    return _block(f"Duplicate {new_direction} on {new_symbol} blocked")
        return ExposureCheckResult(True, "", snap, projected_total)

    def get_snapshot(self, open_positions: List[ExposurePosition]) -> ExposureSnapshot:
        try:
            return self._snapshot_inner(open_positions)
        except Exception as exc:
            logger.exception(
                "ExposureControlEngine.get_snapshot() raised %s [fail_mode=%s]: %s",
                type(exc).__name__, self._fail_mode.value, exc,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return _blocked_snapshot(f"FAIL_CLOSED:SNAPSHOT_ERROR:{type(exc).__name__}")
            return _open_snapshot()

    def _snapshot_inner(self, open_positions: List[ExposurePosition]) -> ExposureSnapshot:
        total_risk:   float            = sum(p.risk_percent for p in open_positions)
        per_currency: Dict[str, float] = {}
        per_symbol:   Dict[str, float] = {}
        buy_count = sell_count = 0
        for p in open_positions:
            sym = p.symbol.upper()
            per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
            for ccy in self._get_currencies(sym):
                per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
            if p.direction.upper() == "BUY": buy_count += 1
            else: sell_count += 1
        return ExposureSnapshot(
            total_risk_percent=total_risk, per_currency=per_currency,
            per_symbol=per_symbol, open_trades=len(open_positions),
            buy_trades=buy_count, sell_trades=sell_count,
            can_open_new=total_risk < self._cfg.max_total_exposure_percent,
            block_reason="",
        )


_engine: Optional[ExposureControlEngine] = None


def get_exposure_control() -> ExposureControlEngine:
    global _engine
    if _engine is None:
        _engine = ExposureControlEngine()
    return _engine
