"""lot_sizing.py — Hedge-Fund Grade Dynamic Pip/Tick Value

HF-3: Broker-based pip/tick calculation
  - MT5 terminal lookup: symbol_info().trade_tick_value (primary)
  - MT5 symbol_info() contract-based calculation (secondary)
  - Static curated table with 38 symbols (tertiary)
  - UnknownSymbolError — NEVER silently continue
  - Async-safe TTL cache (5 min)
  - Kelly fraction + fixed-risk position sizing
"""
from __future__ import annotations
import asyncio
import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import logging
logger = logging.getLogger("risk.lot_sizing")

_PIP_VALUE_TABLE: Dict[str, float] = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCAD":  7.7, "USDCHF": 10.7, "USDJPY":  6.7,
    "EURGBP": 12.9, "EURJPY":  6.7, "GBPJPY":  6.7, "AUDJPY":  6.7,
    "EURAUD": 10.0, "EURCHF": 10.7, "GBPAUD": 10.0, "GBPCHF": 10.7,
    "AUDCAD":  7.7, "AUDCHF": 10.7, "CADCHF": 10.7, "CADJPY":  6.7,
    "CHFJPY":  6.7, "EURNZD": 10.0, "GBPNZD": 10.0, "NZDCAD":  7.7,
    "NZDCHF": 10.7, "NZDJPY":  6.7,
    "XAUUSD":  1.0, "XAGUSD":  5.0, "XPTUSD":  1.0, "XPDUSD":  1.0,
    "USOIL":   1.0, "UKOIL":   1.0, "NATGAS":  1.0,
    "US30":    1.0, "US500":   1.0, "NAS100":  1.0,
    "GER40":   1.0, "UK100":   1.0, "JPN225":  0.1,
    "BTCUSD":  1.0, "ETHUSD":  1.0, "LTCUSD":  1.0, "XRPUSD":  1.0,
}
_PIP_CACHE_TTL = 300.0


class UnknownSymbolError(ValueError):
    """Raised when pip value cannot be determined. NEVER silently continue."""


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
    source:         str
    symbol:         str
    method:         str


class LotSizer:
    """
    HF-3: Pip value lookup order:
      1. MT5 terminal (dynamic, broker-specific)
      2. Static table (38 symbols curated)
      3. UnknownSymbolError -- NEVER silent
    """

    def __init__(self, config: Optional[LotSizingConfig] = None, mt5_connector=None) -> None:
        self.config = config or LotSizingConfig()
        self._mt5   = mt5_connector
        self._cache: Dict[str, Tuple[float, float, str]] = {}
        self._lock   = asyncio.Lock()

    async def get_pip_value(self, symbol: str) -> Tuple[float, str]:
        sym = symbol.upper().strip()
        async with self._lock:
            cached = self._cache.get(sym)
            if cached and (time.monotonic() - cached[1]) < _PIP_CACHE_TTL:
                return cached[0], cached[2]
        if self._mt5 is not None:
            try:
                val = await self._mt5_tick_value(sym)
                if val is not None and val > 0:
                    async with self._lock:
                        self._cache[sym] = (val, time.monotonic(), "mt5_tick_value")
                    logger.info("pip[%s]=%.4f (mt5_tick_value)", sym, val)
                    return val, "mt5_tick_value"
            except Exception as e:
                logger.warning("MT5 tick_value[%s]: %s", sym, e)
            try:
                val = await self._mt5_symbol_info_value(sym)
                if val is not None and val > 0:
                    async with self._lock:
                        self._cache[sym] = (val, time.monotonic(), "mt5_symbol_info")
                    logger.info("pip[%s]=%.4f (mt5_symbol_info)", sym, val)
                    return val, "mt5_symbol_info"
            except Exception as e:
                logger.warning("MT5 symbol_info[%s]: %s", sym, e)
        static = _PIP_VALUE_TABLE.get(sym)
        if static is not None:
            async with self._lock:
                self._cache[sym] = (static, time.monotonic(), "static_table")
            logger.info("pip[%s]=%.4f (static_table)", sym, static)
            return static, "static_table"
        raise UnknownSymbolError(
            f"Cannot determine pip value for '{sym}'. "
            f"Add to _PIP_VALUE_TABLE or verify MT5 symbol name."
        )

    async def _mt5_tick_value(self, symbol: str) -> Optional[float]:
        loop = asyncio.get_event_loop()
        def _get():
            try:
                import MetaTrader5 as mt5
                info = mt5.symbol_info(symbol)
                if info is None: return None
                tick_val  = info.trade_tick_value
                tick_size = info.trade_tick_size
                if tick_size <= 0 or tick_val <= 0: return None
                digits   = info.digits
                pip_size = 10 * tick_size if digits in (4, 5) else tick_size
                return tick_val * (pip_size / tick_size)
            except Exception: return None
        return await loop.run_in_executor(None, _get)

    async def _mt5_symbol_info_value(self, symbol: str) -> Optional[float]:
        loop = asyncio.get_event_loop()
        def _get():
            try:
                import MetaTrader5 as mt5
                info = mt5.symbol_info(symbol)
                tick = mt5.symbol_info_tick(symbol)
                if info is None or tick is None: return None
                digits    = info.digits
                pip_size  = 10 ** -(digits - 1) if digits in (4, 5) else 10 ** -digits
                contract  = info.trade_contract_size or 100_000
                if symbol.endswith("USD"): return pip_size * contract
                if "USD" in symbol: return pip_size * contract / tick.ask if tick.ask > 0 else None
                return info.trade_tick_value
            except Exception: return None
        return await loop.run_in_executor(None, _get)

    async def calculate(
        self,
        balance: float,
        stop_loss_pips: float,
        symbol: str,
        win_rate: Optional[float] = None,
        avg_win_pips: Optional[float] = None,
        avg_loss_pips: Optional[float] = None,
        risk_percent_override: Optional[float] = None,
    ) -> LotSizeResult:
        pip_value, source = await self.get_pip_value(symbol)
        risk_pct = risk_percent_override or self.config.risk_percent
        risk_usd = balance * risk_pct / 100.0
        if stop_loss_pips <= 0:
            stop_loss_pips = 10.0
            logger.warning("stop_loss_pips<=0, defaulting to 10")
        fixed_lot = self._round_lot(risk_usd / (stop_loss_pips * pip_value))
        kelly_lot = fixed_lot
        method    = "fixed_risk"
        if win_rate and avg_win_pips and avg_loss_pips and avg_loss_pips > 0:
            edge = (win_rate * avg_win_pips - (1 - win_rate) * avg_loss_pips) / avg_loss_pips
            if edge > 0:
                kelly_raw = (edge * self.config.kelly_fraction) * balance / (stop_loss_pips * pip_value)
                kelly_lot = self._round_lot(kelly_raw)
                if kelly_lot < fixed_lot:
                    fixed_lot = kelly_lot
                    method = "kelly"
        lot = max(self.config.min_lot, min(fixed_lot, self.config.max_lot))
        logger.info("lot[%s]=%.2f pv=%.4f src=%s risk=%.2f%% sl=%.1fpips", symbol, lot, pip_value, source, risk_pct, stop_loss_pips)
        return LotSizeResult(lot_size=lot, pip_value_used=pip_value, risk_usd=risk_usd,
            risk_percent=risk_pct, kelly_lot=kelly_lot, source=source, symbol=symbol, method=method)

    def _round_lot(self, lot: float) -> float:
        step = self.config.lot_step
        if step <= 0: return lot
        return round(math.floor(lot / step) * step, 10)
