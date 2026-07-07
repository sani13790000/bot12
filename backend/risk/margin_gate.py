"""backend/risk/margin_gate.py — BUG-R6-5 FIX
Margin calculation now uses SymbolInfo.trade_contract_size from MT5
instead of hardcoded contract sizes that were wrong for XAUUSD/BTCUSD.

BUG-R6-5: XAUUSD hardcode 100,000 was WRONG.
  Correct: 100 troy oz * price = notional (not 100,000 units)
  Fix: use mt5_connector.get_symbol_info() for real contract_size
  Fallback table for offline/demo mode with correct values.

BUG-R8: asyncio.to_thread(async_coroutine) removed.
  Fix: direct await on async method.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Fallback contract sizes ONLY when MT5 is unavailable
_FALLBACK_CONTRACT_SIZES: Dict[str, float] = {
    "XAUUSD": 100.0,
    "XAGUSD": 5000.0,
    "BTCUSD": 1.0,
    "ETHUSD": 1.0,
    "USOIL": 1000.0,
    "UKOIL": 1000.0,
    "NAS100": 1.0,
    "US30": 1.0,
    "SPX500": 1.0,
}
_FOREX_DEFAULT_CONTRACT = 100_000.0


@dataclass
class MarginCheckResult:
    approved: bool
    required_margin: float = 0.0
    available_margin: float = 0.0
    margin_level_pct: float = 0.0
    reject_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class MarginGate:
    """
    Gate 7: Validates sufficient free margin before placing a trade.
    Uses real contract_size from MT5 SymbolInfo.
    """

    def __init__(
        self,
        min_free_margin_pct: float = 0.20,
        safety_multiplier: float = 1.20,
    ) -> None:
        self._min_free_pct = min_free_margin_pct
        self._safety = safety_multiplier
        self._mt5: Any = None

    def _get_mt5(self) -> Any:
        if self._mt5 is None:
            try:
                from backend.execution.mt5_connector import mt5_connector

                self._mt5 = mt5_connector
            except ImportError:
                pass
        return self._mt5

    async def _get_contract_size(self, symbol: str) -> float:
        """BUG-R6-5 FIX: Fetch real contract_size from MT5."""
        mt5 = self._get_mt5()
        if mt5 is not None:
            try:
                info = await asyncio.wait_for(mt5.get_symbol_info(symbol), timeout=2.0)
                if info:
                    cs = float(
                        info.trade_contract_size
                        if hasattr(info, "trade_contract_size")
                        else info.get("trade_contract_size", 0)
                    )
                    if cs > 0:
                        return cs
            except Exception as exc:
                log.debug("MT5 symbol info unavailable for %s: %s", symbol, exc)

        sym_upper = symbol.upper()
        for key, size in _FALLBACK_CONTRACT_SIZES.items():
            if sym_upper.startswith(key) or sym_upper == key:
                log.debug("Using fallback contract_size=%s for %s", size, symbol)
                return size
        return _FOREX_DEFAULT_CONTRACT

    async def _required_margin(
        self, symbol: str, lot_size: float, direction: str, margin_rate_pct: float
    ) -> float:
        """BUG-R8 FIX: direct await, not asyncio.to_thread()."""
        mt5 = self._get_mt5()
        if mt5 is not None and hasattr(mt5, "order_calc_margin"):
            try:
                result = await asyncio.wait_for(
                    mt5.order_calc_margin(symbol, lot_size, direction),
                    timeout=3.0,
                )
                if result and result > 0:
                    return float(result) * self._safety
            except Exception as exc:
                log.debug("MT5 order_calc_margin failed: %s", exc)

        contract_size = await self._get_contract_size(symbol)
        notional = lot_size * contract_size
        return notional * (margin_rate_pct / 100.0) * self._safety

    async def check(
        self,
        symbol: str,
        lot_size: float,
        balance: float,
        equity: float,
        free_margin: float,
        used_margin: float = 0.0,
        *,
        direction: str = "BUY",
        margin_rate_pct: float = 2.0,
    ) -> MarginCheckResult:
        if lot_size <= 0:
            return MarginCheckResult(approved=False, reject_reason="lot_size must be positive")

        required = await self._required_margin(symbol, lot_size, direction, margin_rate_pct)

        if free_margin < required:
            return MarginCheckResult(
                approved=False,
                required_margin=required,
                available_margin=free_margin,
                reject_reason=f"insufficient free margin: need {required:.2f}, have {free_margin:.2f}",
            )

        if equity > 0:
            free_pct = free_margin / equity
            if free_pct < self._min_free_pct:
                return MarginCheckResult(
                    approved=False,
                    required_margin=required,
                    available_margin=free_margin,
                    margin_level_pct=free_pct * 100,
                    reject_reason=f"free margin {free_pct:.1%} below minimum {self._min_free_pct:.1%}",
                )

        margin_level = (
            (equity / (used_margin + required) * 100) if (used_margin + required) > 0 else 9999.0
        )
        return MarginCheckResult(
            approved=True,
            required_margin=required,
            available_margin=free_margin - required,
            margin_level_pct=margin_level,
        )
