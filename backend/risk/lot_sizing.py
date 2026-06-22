"""
Galaxy Vast AI Trading Platform
Lot Sizing - FIX-3

FIX-3: Unknown Symbol Pip Value Risk
  BEFORE: _DEFAULT_PIP_VALUE = 1.0  (silently wrong)
  AFTER:
    - Dynamic pip/tick value from MT5 terminal (primary)
    - Static table with 25 symbols (fallback)
    - UnknownSymbolError raised if unknown - NEVER silent
    - XAUUSD corrected: 10.0 -> 1.0
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..core.logger import get_logger

logger = get_logger("risk.lot_sizing")


# FIX-3: explicit pip/tick table (USD per pip per 1 standard lot)
_PIP_VALUE_TABLE: Dict[str, float] = {
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCAD":  7.7,
    "USDCHF": 10.7,
    "USDJPY":  6.7,
    "EURGBP": 12.9,
    "EURJPY":  6.7,
    "GBPJPY":  6.7,
    "AUDJPY":  6.7,
    "EURAUD": 10.0,
    "EURCHF": 10.7,
    "GBPAUD": 10.0,
    "GBPCHF": 10.7,
    "AUDCAD":  7.7,
    # Metals - FIX-3: XAUUSD was 10.0, corrected to 1.0
    "XAUUSD":  1.0,
    "XAGUSD":  5.0,
    "XPTUSD":  1.0,
    "XPDUSD":  1.0,
    # Indices
    "US30":    1.0,
    "US500":   1.0,
    "NAS100":  1.0,
    "GER40":   1.0,
    # Crypto
    "BTCUSD":  1.0,
    "ETHUSD":  1.0,
}


class UnknownSymbolError(ValueError):
    """Raised when pip value cannot be determined. Never silently continue."""
    pass


@dataclass
class LotSizingConfig:
    risk_percent:   float = 1.0
    min_lot:        float = 0.01
    max_lot:        float = 10.0
    lot_step:       float = 0.01
    kelly_fraction: float = 0.5


@dataclass
class LotSizeResult:
    lot_size:       float
    pip_value_used: float
    risk_usd:       float
    risk_percent:   float
    kelly_lot:      float
    source:         str   # "mt5_dynamic" | "static_table" | "provided"
    symbol:         str


class LotSizer:
    """
    FIX-3: pip value lookup order:
      1. MT5 terminal (dynamic, real-time)
      2. _PIP_VALUE_TABLE (static, curated)
      3. UnknownSymbolError (NEVER silent)
    """

    def __init__(self, config: Optional[LotSizingConfig] = None, mt5_connector=None):
        self.config = config or LotSizingConfig()
        self._mt5   = mt5_connector
        self._pip_cache: Dict[str, float] = {}
        self._pip_cache_lock = asyncio.Lock()

    async def get_pip_value(self, symbol: str) -> Tuple[float, str]:
        """Returns (pip_value_usd, source). Raises UnknownSymbolError if unknown."""
        sym = symbol.upper().replace(" ", "")

        # 1. MT5 terminal
        if self._mt5 is not None:
            try:
                async with self._pip_cache_lock:
                    if sym in self._pip_cache:
                        return self._pip_cache[sym], "mt5_cache"
                tick_value = await self._fetch_mt5_pip_value(sym)
                if tick_value is not None and tick_value > 0:
                    async with self._pip_cache_lock:
                        self._pip_cache[sym] = tick_value
                    logger.debug("Pip value %s from MT5: %.4f", sym, tick_value)
                    return tick_value, "mt5_dynamic"
            except Exception as exc:
                logger.warning("MT5 pip value fetch failed for %s: %s", sym, exc)

        # 2. Static table
        if sym in _PIP_VALUE_TABLE:
            return _PIP_VALUE_TABLE[sym], "static_table"

        # 3. FIX-3: NEVER silently continue
        raise UnknownSymbolError(
            f"Cannot determine pip value for '{sym}'. "
            f"Add to _PIP_VALUE_TABLE or connect MT5. "
            f"Known: {sorted(_PIP_VALUE_TABLE.keys())}"
        )

    async def _fetch_mt5_pip_value(self, symbol: str) -> Optional[float]:
        try:
            info = await self._mt5.get_symbol_info(symbol)
            if info is None:
                return None
            tick_value = getattr(info, "trade_tick_value", None)
            tick_size  = getattr(info, "trade_tick_size", None)
            digits     = getattr(info, "digits", 5)
            if tick_value is None or tick_size is None or tick_size == 0:
                return None
            pip_size  = 10 ** -(digits - 1) if digits >= 2 else tick_size
            pip_value = tick_value * (pip_size / tick_size)
            return round(pip_value, 6)
        except Exception as exc:
            logger.warning("_fetch_mt5_pip_value error for %s: %s", symbol, exc)
            return None

    async def calculate(self, balance: float, stop_loss_pips: float, symbol: str, atr_pips: float = 0.0, win_rate: float = 0.55, avg_rr: float = 1.5, volatility_ratio: float = 1.0) -> LotSizeResult:
        """FIX-3: symbol is REQUIRED. Raises UnknownSymbolError if not resolvable."""
        if not symbol:
            raise UnknownSymbolError("symbol parameter is required for lot sizing")
        pip_value, source = await self.get_pip_value(symbol)
        sl_pips = max(stop_loss_pips, 0.1)
        risk_amount = balance * (self.config.risk_percent / 100.0)
        base_lot    = risk_amount / (sl_pips * pip_value)
        kelly_lot = base_lot
        if self.config.kelly_fraction > 0 and win_rate > 0 and avg_rr > 0:
            kelly_f   = win_rate - (1 - win_rate) / avg_rr
            kelly_lot = base_lot * max(0.0, kelly_f) * self.config.kelly_fraction
        raw_lot = kelly_lot * volatility_ratio
        clamped = max(self.config.min_lot, min(raw_lot, self.config.max_lot))
        step    = self.config.lot_step
        final   = math.floor(clamped / step) * step
        final   = max(self.config.min_lot, round(final, 2))
        risk_usd = final * sl_pips * pip_value
        risk_pct = (risk_usd / balance * 100) if balance > 0 else 0.0
        logger.info("LotSizing %s: pip=%.4f(%s) sl=%.1f lot=%.2f risk_usd=%.2f(%.2f%%)", symbol, pip_value, source, sl_pips, final, risk_usd, risk_pct)
        return LotSizeResult(lot_size=final, pip_value_used=pip_value, risk_usd=round(risk_usd, 2), risk_percent=round(risk_pct, 4), kelly_lot=round(kelly_lot, 4), source=source, symbol=symbol)

    def calculate_sync(self, balance: float, stop_loss_pips: float, pip_value_usd: float, win_rate: float = 0.55, avg_rr: float = 1.5, volatility_ratio: float = 1.0, symbol: str = "") -> LotSizeResult:
        if pip_value_usd <= 0:
            raise ValueError(f"pip_value_usd must be > 0, got {pip_value_usd}")
        sl_pips     = max(stop_loss_pips, 0.1)
        risk_amount = balance * (self.config.risk_percent / 100.0)
        base_lot    = risk_amount / (sl_pips * pip_value_usd)
        kelly_lot = base_lot
        if self.config.kelly_fraction > 0 and win_rate > 0 and avg_rr > 0:
            kelly_f   = win_rate - (1 - win_rate) / avg_rr
            kelly_lot = base_lot * max(0.0, kelly_f) * self.config.kelly_fraction
        raw_lot = kelly_lot * volatility_ratio
        clamped = max(self.config.min_lot, min(raw_lot, self.config.max_lot))
        step    = self.config.lot_step
        final   = math.floor(clamped / step) * step
        final   = max(self.config.min_lot, round(final, 2))
        risk_usd = final * sl_pips * pip_value_usd
        risk_pct = (risk_usd / balance * 100) if balance > 0 else 0.0
        return LotSizeResult(lot_size=final, pip_value_used=pip_value_usd, risk_usd=round(risk_usd, 2), risk_percent=round(risk_pct, 4), kelly_lot=round(kelly_lot, 4), source="provided", symbol=symbol)
