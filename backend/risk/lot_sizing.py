"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dynamic Lot Sizing & ATR Position Sizing Engine
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import math


class LotSizingMethod(str, Enum):
    FIXED_PERCENT   = "FIXED_PERCENT"    # % of balance
    ATR_BASED       = "ATR_BASED"        # ATR-normalised risk
    FIXED_LOT       = "FIXED_LOT"        # static lot
    KELLY           = "KELLY"            # Kelly Criterion (capped)
    VOLATILITY_ADJ  = "VOLATILITY_ADJ"   # scaled by realised vol


@dataclass
class LotSizingConfig:
    method: LotSizingMethod = LotSizingMethod.ATR_BASED
    risk_percent: float = 1.0           # % of balance per trade
    fixed_lot: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 5.0
    lot_step: float = 0.01
    atr_multiplier: float = 1.5         # SL = ATR x multiplier
    kelly_fraction: float = 0.25        # fractional Kelly


# ---------------------------------------------------------------------------
# Pip value table  ($ per pip per standard lot)
# ---------------------------------------------------------------------------
_PIP_VALUE_TABLE = {
    # Forex majors / minors
    "EURUSD": 10.0,  "GBPUSD": 10.0,  "AUDUSD": 10.0,  "NZDUSD": 10.0,
    "USDCAD": 10.0,  "USDCHF": 10.0,  "USDJPY": 9.09,
    "EURGBP": 10.0,  "EURJPY": 9.09,  "GBPJPY": 9.09,
    "CADJPY": 9.09,  "AUDJPY": 9.09,  "CHFJPY": 9.09,
    # Metals
    "XAUUSD":  1.0,   # Gold   — pip=$0.01, 100 oz lot
    "XAGUSD": 50.0,   # Silver — pip=$0.001, 5000 oz lot  (FIX #4)
    "XPTUSD": 10.0,   # Platinum
    # Crypto
    "BTCUSD": 1.0,   "ETHUSD": 1.0,   "LTCUSD": 1.0,
    "BNBUSD": 1.0,   "XRPUSD": 1.0,
    # Indices
    "US30":   1.0,   "SPX500": 1.0,   "NAS100": 1.0,
    "GER40":  1.0,   "UK100":  1.0,   "JPN225": 1.0,
    "AUS200": 1.0,   "FRA40":  1.0,
    # Energy
    "USOIL":  10.0,  "UKOIL":  10.0,
}

# Aliases: broker names -> canonical symbol
_SYMBOL_ALIASES = {
    "GOLD":   "XAUUSD",  "SILVER":  "XAGUSD",
    "XAUUSD": "XAUUSD",  "XAGUSD":  "XAGUSD",
    "BTC":    "BTCUSD",  "BITCOIN": "BTCUSD",
    "ETH":    "ETHUSD",  "ETHEREUM":"ETHUSD",
    "DAX":    "GER40",   "DAX40":   "GER40",
    "NASDAQ": "NAS100",  "DOW":     "US30",
    "SP500":  "SPX500",  "FTSE":    "UK100",
    "NIKKEI": "JPN225",  "ASX200":  "AUS200",
}


def _resolve_pip_value(symbol: str) -> float:
    """Resolve pip value with alias and broker-suffix handling."""
    sym = symbol.upper().strip()
    # 1. alias
    canonical = _SYMBOL_ALIASES.get(sym, sym)
    if canonical in _PIP_VALUE_TABLE:
        return _PIP_VALUE_TABLE[canonical]
    # 2. suffix strip (broker variants: EURUSDm, XAUUSDpro, etc.)
    for n in range(1, 5):
        stripped = sym[:-n].upper()
        c2 = _SYMBOL_ALIASES.get(stripped, stripped)
        if c2 in _PIP_VALUE_TABLE:
            return _PIP_VALUE_TABLE[c2]
    # 3. fallback
    if sym.endswith("JPY") or canonical.endswith("JPY"):
        return 9.09
    if sym.endswith("USD") or canonical.endswith("USD"):
        return 10.0
    return 10.0


@dataclass
class LotSizeResult:
    lot_size:     float
    risk_percent: float
    risk_usd:     float
    method:       str
    details:      dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class UnknownSymbolError(ValueError):
    pass


class LotSizer:
    """
    Calculates position size based on configured method.
    FIX #4: get_pip_value() uses broker-aware resolution (alias + suffix strip).
    """

    def __init__(self, config: LotSizingConfig = None):
        self.config = config or LotSizingConfig()

    def get_pip_value(self, symbol: str) -> float:
        """Return pip value (USD per pip per standard lot) for symbol."""
        return _resolve_pip_value(symbol)

    async def calculate(
        self,
        symbol:         str,
        balance:        float,
        stop_loss_pips: float,
        win_rate:       Optional[float] = None,
        avg_win_loss:   Optional[float] = None,
        override_risk_pct: Optional[float] = None,   # FIX-5B
    ) -> LotSizeResult:
        """
        Calculate lot size.
        FIX-5B: override_risk_pct allows caller to specify exact risk percent.
        """
        cfg = self.config
        # FIX-5B: per-call override
        effective_risk_pct = (
            override_risk_pct
            if (override_risk_pct is not None and override_risk_pct > 0)
            else cfg.risk_percent
        )

        if cfg.method == LotSizingMethod.FIXED_LOT:
            lot = cfg.fixed_lot
            risk_usd = lot * stop_loss_pips * self.get_pip_value(symbol)
            return LotSizeResult(
                lot_size=lot,
                risk_percent=risk_usd / balance * 100 if balance else 0.0,
                risk_usd=risk_usd,
                method="FIXED_LOT",
            )

        if cfg.method == LotSizingMethod.KELLY and win_rate is not None and avg_win_loss is not None:
            kelly = win_rate - (1 - win_rate) / avg_win_loss
            kelly = max(0.0, kelly) * cfg.kelly_fraction
            effective_risk_pct = min(kelly * 100, effective_risk_pct)

        # Standard risk-based sizing
        risk_usd  = balance * (effective_risk_pct / 100)
        pip_value = self.get_pip_value(symbol)
        if stop_loss_pips <= 0 or pip_value <= 0:
            return LotSizeResult(
                lot_size=cfg.min_lot,
                risk_percent=effective_risk_pct,
                risk_usd=risk_usd,
                method=cfg.method.value,
                details={"warning": "zero_sl_or_pip_value"},
            )

        raw_lot = risk_usd / (stop_loss_pips * pip_value)
        # Snap to lot_step
        lot = math.floor(raw_lot / cfg.lot_step) * cfg.lot_step
        lot = max(cfg.min_lot, min(cfg.max_lot, lot))
        actual_risk_usd = lot * stop_loss_pips * pip_value

        return LotSizeResult(
            lot_size=round(lot, 4),
            risk_percent=actual_risk_usd / balance * 100 if balance else 0.0,
            risk_usd=actual_risk_usd,
            method=cfg.method.value,
        )


# Global singleton
_lot_sizer: Optional[LotSizer] = None


def get_lot_sizer(config: LotSizingConfig = None) -> LotSizer:
    global _lot_sizer
    if _lot_sizer is None:
        _lot_sizer = LotSizer(config=config)
    return _lot_sizer
