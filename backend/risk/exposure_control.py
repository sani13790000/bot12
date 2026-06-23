"""backend/risk/exposure_control.py
Phase Q Fix Q-11: _SYMBOL_CURRENCIES expanded from 14 to 38 symbols.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExposureControlConfig:
    max_total_exposure_percent: float = 5.0
    max_per_currency_percent: float = 3.0
    max_per_symbol_percent: float = 2.0
    max_simultaneous_trades: int = 5
    max_buy_trades: int = 3
    max_sell_trades: int = 3
    block_same_symbol_same_direction: bool = True


@dataclass
class ExposurePosition:
    symbol: str
    direction: str
    risk_percent: float
    risk_usd: float = 0.0


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


class ExposureControlEngine:
    # Q-11 FIX: 38 symbols (was 14)
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

    def __init__(self, config: Optional[ExposureControlConfig] = None):
        self._cfg = config or ExposureControlConfig()

    def _get_currencies(self, symbol: str) -> List[str]:
        key = symbol.upper()
        return self._SYMBOL_CURRENCIES.get(key, [key[:3], key[3:]] if len(key) == 6 else [key])

    def check(self, new_symbol: str, new_direction: str, new_risk_percent: float, open_positions: List[ExposurePosition]) -> ExposureCheckResult:
        cfg = self._cfg
        new_symbol = new_symbol.upper(); new_direction = new_direction.upper()
        total_risk = sum(p.risk_percent for p in open_positions)
        per_currency: Dict[str, float] = {}
        per_symbol: Dict[str, float] = {}
        buy_count = sell_count = 0
        for p in open_positions:
            sym = p.symbol.upper()
            per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
            for ccy in self._get_currencies(sym):
                per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
            if p.direction.upper() == "BUY": buy_count += 1
            else: sell_count += 1
        projected_total = total_risk + new_risk_percent
        projected_sym = per_symbol.get(new_symbol, 0.0) + new_risk_percent
        projected_ccy = {ccy: per_currency.get(ccy, 0.0) + new_risk_percent for ccy in self._get_currencies(new_symbol)}
        new_buy_count = buy_count + (1 if new_direction == "BUY" else 0)
        new_sell_count = sell_count + (1 if new_direction == "SELL" else 0)
        new_total = len(open_positions) + 1
        snap = ExposureSnapshot(total_risk_percent=total_risk, per_currency=per_currency, per_symbol=per_symbol, open_trades=len(open_positions), buy_trades=buy_count, sell_trades=sell_count, can_open_new=True, block_reason="")
        if projected_total > cfg.max_total_exposure_percent:
            msg = f"Total exposure {projected_total:.2f}% > limit {cfg.max_total_exposure_percent}%"
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        if projected_sym > cfg.max_per_symbol_percent:
            msg = f"Symbol {new_symbol} exposure {projected_sym:.2f}% > limit {cfg.max_per_symbol_percent}%"
            snap.can_open_new = False; snap.block_reason = msg
            return ExposureCheckResult(False, msg, snap, projected_total)
        for ccy, val in projected_ccy.items():
            if val > cfg.max_per_currency_percent:
                msg = f"Currency {ccy} exposure {val:.2f}% > limit {cfg.max_per_currency_percent}%"
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
        total_risk = sum(p.risk_percent for p in open_positions)
        per_currency: Dict[str, float] = {}
        per_symbol: Dict[str, float] = {}
        buy_count = sell_count = 0
        for p in open_positions:
            sym = p.symbol.upper()
            per_symbol[sym] = per_symbol.get(sym, 0.0) + p.risk_percent
            for ccy in self._get_currencies(sym):
                per_currency[ccy] = per_currency.get(ccy, 0.0) + p.risk_percent
            if p.direction.upper() == "BUY": buy_count += 1
            else: sell_count += 1
        return ExposureSnapshot(total_risk_percent=total_risk, per_currency=per_currency, per_symbol=per_symbol, open_trades=len(open_positions), buy_trades=buy_count, sell_trades=sell_count, can_open_new=total_risk < self._cfg.max_total_exposure_percent, block_reason="")


_engine: Optional[ExposureControlEngine] = None

def get_exposure_control() -> ExposureControlEngine:
    global _engine
    if _engine is None:
        _engine = ExposureControlEngine()
    return _engine
