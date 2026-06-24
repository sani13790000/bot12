from __future__ import annotations
"""
backend/risk/volatility_filter.py
=============================================
Volatility & Spread Filter for Trade Entry

FIX #6 changes:
  - FailMode imported from canonical fail_mode.py (single source of truth)
  - _fail_mode cached in __init__ (not re-computed on every check)
  - check() wraps _check_inner() in try/except with full logging
  - FAIL_CLOSED: exception => block trade
  - FAIL_OPEN:   exception => allow + CRITICAL log

FIX #7 changes:
  - Removed dead 'field' import from dataclasses (0 field() calls)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
except ImportError:
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce_fm(v):  # type: ignore[misc]
        if isinstance(v, FailMode): return v
        return FailMode(str(v).upper().strip())

logger = logging.getLogger("risk.volatility_filter")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class VolatilityCheckResult:
    can_trade:   bool
    reason:      str   = ""
    atr_ratio:   float = 0.0
    spread_ratio: float = 0.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class VolatilityConfig:
    # ATR thresholds
    atr_min_ratio:      float    = 0.5    # current ATR / avg ATR must be >= this
    atr_max_ratio:      float    = 3.0    # and <= this
    # Spread threshold
    max_spread_ratio:   float    = 2.0    # spread / avg_spread must be <= this
    # Minimum history
    min_atr_bars:       int      = 5
    # Fail mode
    fail_mode:          FailMode = FailMode.FAIL_CLOSED


# ---------------------------------------------------------------------------
# Per-symbol cache entry
# ---------------------------------------------------------------------------
@dataclass
class _SymbolCache:
    last_check:  datetime
    result:      VolatilityCheckResult


# ---------------------------------------------------------------------------
# Per-symbol ATR history tracker
# ---------------------------------------------------------------------------
class ATRHistory:
    """Maintains a rolling window of ATR values for a single symbol."""

    def __init__(self, max_bars: int = 200):
        self._bars: List[float] = []
        self._max  = max_bars

    def push(self, atr: float) -> None:
        self._bars.append(atr)
        if len(self._bars) > self._max:
            self._bars.pop(0)

    def average(self, window: Optional[int] = None) -> float:
        data = self._bars if window is None else self._bars[-window:]
        return sum(data) / len(data) if data else 0.0

    def count(self) -> int:
        return len(self._bars)


# ---------------------------------------------------------------------------
# VolatilityFilter
# ---------------------------------------------------------------------------
class VolatilityFilter:
    """
    Evaluates whether market volatility and spread are acceptable for a new trade.

    check() signature (unchanged from pre-FIX-6):
        check(current_atr, atr_history, current_spread, avg_spread, symbol) -> VolatilityCheckResult

    FIX-6: all exceptions caught; behaviour controlled by fail_mode.
    """

    def __init__(self, config: VolatilityConfig = None):
        self._cfg = config or VolatilityConfig()
        # FIX-6 / FIX-7: cache fail_mode once at construction
        self._fail_mode: FailMode = _coerce_fm(
            getattr(self._cfg, "fail_mode", FailMode.FAIL_CLOSED)
        )
        self._cache: Dict[str, _SymbolCache] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def check(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str = "",
    ) -> VolatilityCheckResult:
        try:
            result = self._check_inner(
                current_atr, atr_history, current_spread, avg_spread, symbol
            )
            # update cache
            self._cache[symbol] = _SymbolCache(
                last_check=datetime.now(timezone.utc),
                result=result,
            )
            return result
        except Exception as exc:
            logger.error(
                "VolatilityFilter.check exception symbol=%s fail_mode=%s: %s",
                symbol, self._fail_mode, exc, exc_info=True,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return VolatilityCheckResult(
                    can_trade=False,
                    reason=f"FAIL_CLOSED:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
                )
            logger.critical(
                "FAIL_OPEN: VolatilityFilter exception swallowed symbol=%s fail_mode=%s",
                symbol, self._fail_mode,
            )
            return VolatilityCheckResult(
                can_trade=True,
                reason=f"FAIL_OPEN:VOLATILITY_GATE_ERROR:{type(exc).__name__}",
            )

    def get_cached(
        self, symbol: str
    ) -> Optional[Tuple[VolatilityCheckResult, datetime]]:
        """Return last check result + timestamp for a symbol, or None."""
        entry = self._cache.get(symbol)
        if entry is None:
            return None
        return entry.result, entry.last_check

    # ------------------------------------------------------------------
    # Inner logic
    # ------------------------------------------------------------------
    def _check_inner(
        self,
        current_atr:    float,
        atr_history:    List[float],
        current_spread: float,
        avg_spread:     float,
        symbol:         str,
    ) -> VolatilityCheckResult:
        cfg = self._cfg

        # Need minimum ATR history
        if len(atr_history) < cfg.min_atr_bars:
            return VolatilityCheckResult(
                can_trade=True,
                reason="INSUFFICIENT_ATR_HISTORY",
                atr_ratio=0.0,
                spread_ratio=0.0,
            )

        avg_atr = sum(atr_history) / len(atr_history) if atr_history else 0.0
        if avg_atr <= 0:
            return VolatilityCheckResult(
                can_trade=True,
                reason="ZERO_AVG_ATR",
            )

        atr_ratio = current_atr / avg_atr

        # ATR too low — market too quiet / illiquid
        if atr_ratio < cfg.atr_min_ratio:
            return VolatilityCheckResult(
                can_trade=False,
                reason=f"ATR_TOO_LOW:{atr_ratio:.3f}<{cfg.atr_min_ratio}",
                atr_ratio=atr_ratio,
            )

        # ATR too high — market too volatile
        if atr_ratio > cfg.atr_max_ratio:
            return VolatilityCheckResult(
                can_trade=False,
                reason=f"ATR_TOO_HIGH:{atr_ratio:.3f}>{cfg.atr_max_ratio}",
                atr_ratio=atr_ratio,
            )

        # Spread check
        spread_ratio = 0.0
        if avg_spread > 0:
            spread_ratio = current_spread / avg_spread
            if spread_ratio > cfg.max_spread_ratio:
                return VolatilityCheckResult(
                    can_trade=False,
                    reason=f"SPREAD_TOO_WIDE:{spread_ratio:.3f}>{cfg.max_spread_ratio}",
                    atr_ratio=atr_ratio,
                    spread_ratio=spread_ratio,
                )

        return VolatilityCheckResult(
            can_trade=True,
            reason="VOLATILITY_OK",
            atr_ratio=atr_ratio,
            spread_ratio=spread_ratio,
        )


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------
_vf_instance: Optional[VolatilityFilter] = None


def get_volatility_filter(config: VolatilityConfig = None) -> VolatilityFilter:
    global _vf_instance
    if _vf_instance is None:
        _vf_instance = VolatilityFilter(config=config)
    return _vf_instance
