from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
except ImportError:  # pragma: no cover
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = 'FAIL_CLOSED'
        FAIL_OPEN   = 'FAIL_OPEN'

    def _coerce_fm(v):  # type: ignore[misc]
        if isinstance(v, FailMode): return v
        return FailMode(str(v).upper())

try:
    from backend.risk.correlation_engine import RollingCorrelationEngine
except ImportError:  # pragma: no cover
    RollingCorrelationEngine = None  # type: ignore

logger = logging.getLogger('risk.correlation_filter')


@dataclass
class CorrelationFilterConfig:
    max_corr:          float     = 0.85
    lookback_bars:     int       = 50
    min_bars:          int       = 20
    fail_mode:         FailMode  = FailMode.FAIL_CLOSED


@dataclass
class CorrelationCheckResult:
    can_trade:       bool
    reason:          str  = ''
    correlation:     float = 0.0
    pair_checked:    str  = ''


class CorrelationFilter:
    """
    Checks correlation between proposed trade and open positions.
    FIX-6: configurable fail_mode — FAIL_CLOSED blocks on exception,
            FAIL_OPEN allows with CRITICAL log.
    """

    def __init__(self, config: CorrelationFilterConfig = None,
                 correlation_engine=None,
                 fail_mode=None):
        self._cfg    = config or CorrelationFilterConfig()
        self._engine = correlation_engine
        # fail_mode kwarg overrides config
        _fm_src = fail_mode if fail_mode is not None else self._cfg.fail_mode
        self._fail_mode: FailMode = _coerce_fm(_fm_src)

    # ------------------------------------------------------------------
    # Public API — signature unchanged
    # ------------------------------------------------------------------
    async def check(
        self,
        symbol:         str,
        direction:      str,
        open_positions: List[Dict] | None = None,
    ) -> CorrelationCheckResult:
        try:
            return await self._check_inner(symbol, direction, open_positions)
        except Exception as exc:
            logger.critical(
                "CorrelationFilter exception symbol=%s fail_mode=%s: %s",
                symbol, self._fail_mode, exc, exc_info=True,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return CorrelationCheckResult(
                    can_trade=False,
                    reason=f'FAIL_CLOSED:CORR_EXCEPTION:{type(exc).__name__}',
                )
            logger.critical(
                "FAIL_OPEN: CorrelationFilter exception swallowed symbol=%s", symbol
            )
            return CorrelationCheckResult(
                can_trade=True,
                reason='FAIL_OPEN:CORR_EXCEPTION_IGNORED',
            )

    # ------------------------------------------------------------------
    # Inner logic
    # ------------------------------------------------------------------
    async def _check_inner(
        self,
        symbol:         str,
        direction:      str,
        open_positions: List[Dict] | None = None,
    ) -> CorrelationCheckResult:
        if not open_positions or self._engine is None:
            return CorrelationCheckResult(can_trade=True, reason='NO_POSITIONS_OR_ENGINE')

        max_corr = self._cfg.max_corr
        for pos in open_positions:
            pos_sym = pos.get('symbol', '') if isinstance(pos, dict) else getattr(pos, 'symbol', '')
            if not pos_sym or pos_sym == symbol:
                continue
            try:
                corr = await self._engine.get_correlation(symbol, pos_sym)
            except Exception:
                corr = 0.0
            if abs(corr) >= max_corr:
                return CorrelationCheckResult(
                    can_trade=False,
                    reason=f'CORR_TOO_HIGH:{pos_sym}',
                    correlation=corr,
                    pair_checked=pos_sym,
                )
        return CorrelationCheckResult(can_trade=True, reason='CORR_OK')


_corr_filter_instance = None


def get_correlation_filter(
    config: CorrelationFilterConfig = None,
    correlation_engine=None,
) -> CorrelationFilter:
    global _corr_filter_instance
    if _corr_filter_instance is None:
        _corr_filter_instance = CorrelationFilter(
            config=config,
            correlation_engine=correlation_engine,
        )
    return _corr_filter_instance
