"""lot_sizing.py - Hedge-Fund Grade Dynamic Pip/Tick Value v2 (HF-3)

HF-3: Broker-based pip/tick calculation
  Lookup order:
    1. MT5 terminal: symbol_info().trade_tick_value (broker-specific)
    2. Static curated table (38 symbols)
    3. UnknownSymbolError - NEVER silently continue
  Features:
    - Async-safe TTL cache (5 min)
    - Kelly fraction + fixed-risk dual sizing
    - XAUUSD pip_value=1.0 (critical fix from 10.0)
"""
from __future__ import annotations
import asyncio, math, time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import logging
logger = logging.getLogger("risk.lot_sizing")

_PIP_VALUE_TABLE: Dict[str, float] = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCAD": 7.7, "USDCHF": 10.7, "USDJPY": 6.7,
    "EURGBP": 12.9, "EURJPY": 6.7, "EURAUD": 10.0,
    "EURCHF": 10.7, "EURNZD": 10.0, "EURCAD": 7.7,
    "GBPJPY": 6.7, "GBPAUD": 10.0, "GBPCHF": 10.7,
    "GBPNZD": 10.0, "GBPCAD": 7.7,
    "AUDJPY": 6.7, "AUDCAD": 7.7, "AUDCHF": 10.7, "AUDNZD": 10.0,
    "CADCHF": 10.7, "CADJPY": 6.7, "CHFJPY": 6.7,
    "NZDCAD": 7.7, "NZDCHF": 10.7, "NZDJPY": 6.7,
    "XAUUSD": 1.0,  # HF-3 FIX: was incorrectly 10.0
    "XAGUSD": 5.0, "XPTUSD": 1.0, "XPDUSD": 1.0,
    "USOIL": 1.0, "UKOIL": 1.0, "NATGAS": 1.0,
    "US30": 1.0, "US500": 1.0, "NAS100": 1.0,
    "GER40": 1.0, "UK100": 1.0, "JPN225": 0.1,
    "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0, "XRPUSD": 1.0,
}
_PIP_CACHE_TTL = 300.0
_MIN_LOT_GLOBAL = 0.01
_MAX_LOT_GLOBAL = 100.0


class UnknownSymbolError(ValueError):
    """Raised when pip value cannot be determined. NEVER silently continue."""


@dataclass
class LotSizingConfig:
    risk_percent: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 10.0
    lot_step: float = 0.01
    kelly_fraction: float = 0.5


@dataclass
class LotSizeResult:
    lot_size: float; pip_value_used: float; risk_usd: float
    risk_percent: float; kelly_lot: float; source: str
    symbol: str; method: str


class LotSizer:
    """
    HF-3: Pip value lookup: MT5 terminal -> static table -> UnknownSymbolError
    NEVER silently continues with a wrong pip value.
    """

    def __init__(self, config: Optional[LotSizingConfig] = None, mt5_connector=None) -> None:
        self.config = config or LotSizingConfig()
        self._mt5 = mt5_connector
        self._cache: Dict[str, Tuple[float, float, str]] = {}
        self._lock = asyncio.Lock()

    async def get_pip_value(self, symbol: str) -> Tuple[float, str]:
        sym = symbol.upper().strip()
        async with self._lock:
            return await self._resolve_pip_value(sym)

    async def calculate(self, balance: float, stop_loss_pips: float, symbol: str,
                        atr_pips: float = 0.0, win_rate: float = 0.55,
                        avg_rr: float = 1.5, volatility_ratio: float = 1.0) -> LotSizeResult:
        sym = symbol.upper().strip()
        if stop_loss_pips <= 0:
            raise ValueError(f"stop_loss_pips must be > 0, got {stop_loss_pips}")
        if balance <= 0:
            raise ValueError(f"balance must be > 0, got {balance}")
        pip_val, source = await self.get_pip_value(sym)
        risk_usd = balance * (self.config.risk_percent / 100.0) * volatility_ratio
        fixed_lot = risk_usd / (stop_loss_pips * pip_val)
        kelly_pct = max(0.0, min(0.25, (win_rate - (1 - win_rate) / avg_rr) if avg_rr > 0 else 0.0))
        kelly_lot = (balance * kelly_pct * self.config.kelly_fraction) / (stop_loss_pips * pip_val)
        blended = 0.70 * fixed_lot + 0.30 * kelly_lot
        final_lot = max(self.config.min_lot, min(self.config.max_lot,
                        max(_MIN_LOT_GLOBAL, min(_MAX_LOT_GLOBAL, blended))))
        step = self.config.lot_step
        final_lot = math.floor(final_lot / step) * step
        final_lot = max(self.config.min_lot, round(final_lot, 2))
        actual_risk_usd = final_lot * stop_loss_pips * pip_val
        actual_risk_pct = (actual_risk_usd / balance * 100) if balance > 0 else 0.0
        method = "min_fallback" if final_lot <= self.config.min_lot else ("kelly_blend" if kelly_pct > 0 else "fixed_risk")
        logger.debug("LotSizer %s: pip=%.4f(%s) sl=%.1f final=%.2f", sym, pip_val, source, stop_loss_pips, final_lot)
        return LotSizeResult(lot_size=final_lot, pip_value_used=pip_val,
            risk_usd=round(actual_risk_usd, 2), risk_percent=round(actual_risk_pct, 3),
            kelly_lot=round(kelly_lot, 4), source=source, symbol=sym, method=method)

    async def _resolve_pip_value(self, sym: str) -> Tuple[float, str]:
        now = time.monotonic()
        cached = self._cache.get(sym)
        if cached and (now - cached[1]) < _PIP_CACHE_TTL:
            return cached[0], cached[2]
        if self._mt5 is not None:
            try:
                pip_val, source = await self._from_mt5(sym)
                self._cache[sym] = (pip_val, now, source)
                return pip_val, source
            except Exception as exc:
                logger.warning("MT5 pip lookup failed for %s: %s", sym, exc)
        static = _PIP_VALUE_TABLE.get(sym)
        if static is not None:
            self._cache[sym] = (static, now, "static_table")
            return static, "static_table"
        raise UnknownSymbolError(
            f"Cannot determine pip value for '{sym}'. "
            f"Not in MT5 terminal and not in static table ({len(_PIP_VALUE_TABLE)} symbols). "
            f"Add '{sym}' to _PIP_VALUE_TABLE or verify broker symbol name."
        )

    async def _from_mt5(self, sym: str) -> Tuple[float, str]:
        info = await asyncio.to_thread(self._mt5.get_symbol_info, sym)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info({sym}) returned None")
        tick_val = getattr(info, "trade_tick_value", None)
        tick_sz = getattr(info, "trade_tick_size", None)
        if tick_val and tick_val > 0 and tick_sz and tick_sz > 0:
            point = getattr(info, "point", tick_sz)
            pip_sz = point * 10 if point <= 0.001 else point
            ratio = pip_sz / tick_sz if tick_sz > 0 else 1.0
            pip_val = tick_val * ratio
            return pip_val, "mt5_tick_value"
        contract = getattr(info, "trade_contract_size", None)
        if contract and contract > 0 and tick_sz and tick_sz > 0:
            pip_val = tick_sz * contract
            return pip_val, "mt5_contract"
        raise RuntimeError(f"MT5 could not compute pip value for {sym}")


_lot_sizer: Optional[LotSizer] = None


def get_lot_sizer(config: Optional[LotSizingConfig] = None, mt5_connector=None) -> LotSizer:
    global _lot_sizer
    if _lot_sizer is None:
        _lot_sizer = LotSizer(config=config, mt5_connector=mt5_connector)
    return _lot_sizer


DynamicLotSizer = LotSizer
