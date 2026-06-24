from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('risk.correlation_filter')

try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
except ImportError:  # pragma: no cover
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = 'FAIL_CLOSED'
        FAIL_OPEN   = 'FAIL_OPEN'
    def _coerce_fm(v):
        return v if isinstance(v, FailMode) else FailMode(str(v).upper())

CORRELATION_MATRIX: Dict[str, Dict[str, float]] = {
    'EURUSD': {'GBPUSD': 0.85, 'AUDUSD': 0.72, 'NZDUSD': 0.70,
               'USDCHF': -0.92, 'USDJPY': -0.55, 'USDCAD': -0.60,
               'XAUUSD': 0.30, 'EURUSD': 1.0},
    'GBPUSD': {'EURUSD': 0.85, 'AUDUSD': 0.65, 'NZDUSD': 0.60,
               'USDCHF': -0.80, 'USDJPY': -0.45, 'USDCAD': -0.55,
               'XAUUSD': 0.25, 'GBPUSD': 1.0},
    'AUDUSD': {'EURUSD': 0.72, 'GBPUSD': 0.65, 'NZDUSD': 0.92,
               'USDCHF': -0.68, 'USDJPY': -0.40, 'USDCAD': -0.50,
               'XAUUSD': 0.45, 'AUDUSD': 1.0},
    'NZDUSD': {'EURUSD': 0.70, 'GBPUSD': 0.60, 'AUDUSD': 0.92,
               'USDCHF': -0.65, 'USDJPY': -0.38, 'USDCAD': -0.48,
               'XAUUSD': 0.40, 'NZDUSD': 1.0},
    'USDCHF': {'EURUSD': -0.92, 'GBPUSD': -0.80, 'AUDUSD': -0.68,
               'NZDUSD': -0.65, 'USDJPY': 0.50, 'USDCAD': 0.55,
               'XAUUSD': -0.28, 'USDCHF': 1.0},
    'USDJPY': {'EURUSD': -0.55, 'GBPUSD': -0.45, 'AUDUSD': -0.40,
               'NZDUSD': -0.38, 'USDCHF': 0.50, 'USDCAD': 0.40,
               'XAUUSD': -0.35, 'USDJPY': 1.0},
    'USDCAD': {'EURUSD': -0.60, 'GBPUSD': -0.55, 'AUDUSD': -0.50,
               'NZDUSD': -0.48, 'USDCHF': 0.55, 'USDJPY': 0.40,
               'XAUUSD': -0.20, 'USDCAD': 1.0},
    'XAUUSD': {'EURUSD': 0.30, 'GBPUSD': 0.25, 'AUDUSD': 0.45,
               'NZDUSD': 0.40, 'USDCHF': -0.28, 'USDJPY': -0.35,
               'USDCAD': -0.20, 'XAUUSD': 1.0},
    'XAGUSD': {'XAUUSD': 0.87, 'EURUSD': 0.28, 'AUDUSD': 0.42, 'XAGUSD': 1.0},
    'BTCUSD': {'XAUUSD': 0.15, 'ETHUSD': 0.92, 'BTCUSD': 1.0},
    'ETHUSD': {'BTCUSD': 0.92, 'ETHUSD': 1.0},
}


@dataclass
class CorrelationFilterConfig:
    max_correlated_exposure: float = 0.80
    correlation_penalty_threshold: float = 0.60
    max_same_direction_corr_pairs: int = 2
    risk_multiplier_high_corr: float = 0.5
    fail_mode: FailMode = FailMode.FAIL_CLOSED


@dataclass
class OpenPosition:
    symbol: str
    direction: str
    risk_percent: float


@dataclass
class CorrelationCheckResult:
    can_trade: bool
    reason: str
    correlation_score: float
    correlated_pairs: List[str]
    adjusted_risk_percent: float
    risk_multiplier: float


class CorrelationFilter:
    """FIX #6: FAIL_CLOSED (default) or FAIL_OPEN on exception. Every exception logged."""

    def __init__(self, config=None, fail_mode=None):
        self._cfg = config or CorrelationFilterConfig()
        _fm = fail_mode if fail_mode is not None else self._cfg.fail_mode
        self._fail_mode: FailMode = _coerce_fm(_fm)

    def check(self, new_symbol, new_direction, open_positions, base_risk_percent):
        """FIX #6: wraps _check_inner() -- exceptions handled per fail_mode."""
        try:
            return self._check_inner(new_symbol, new_direction, open_positions, base_risk_percent)
        except Exception as exc:
            logger.critical(
                'CorrelationFilter.check exception symbol=%s fail_mode=%s: %s',
                new_symbol, self._fail_mode, exc, exc_info=True,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return CorrelationCheckResult(
                    can_trade=False,
                    reason='FAIL_CLOSED:CORRELATION_GATE_ERROR:' + type(exc).__name__,
                    correlation_score=0.0, correlated_pairs=[],
                    adjusted_risk_percent=0.0, risk_multiplier=0.0,
                )
            logger.critical(
                'FAIL_OPEN: CorrelationFilter exception swallowed, trade ALLOWED. symbol=%s fail_mode=%s',
                new_symbol, self._fail_mode,
            )
            return CorrelationCheckResult(
                can_trade=True,
                reason='FAIL_OPEN:CORRELATION_GATE_ERROR:' + type(exc).__name__,
                correlation_score=0.0, correlated_pairs=[],
                adjusted_risk_percent=base_risk_percent, risk_multiplier=1.0,
            )

    def get_correlation(self, sym_a, sym_b):
        return self._get_correlation(sym_a, sym_b)

    def _check_inner(self, new_symbol, new_direction, open_positions, base_risk_percent):
        if not open_positions:
            return CorrelationCheckResult(
                can_trade=True, reason='NO_OPEN_POSITIONS',
                correlation_score=0.0, correlated_pairs=[],
                adjusted_risk_percent=base_risk_percent, risk_multiplier=1.0,
            )
        max_corr = 0.0
        corr_pairs = []
        same_dir_count = 0
        for pos in open_positions:
            corr = self._get_correlation(new_symbol, pos.symbol)
            if corr is None:
                continue
            abs_corr = abs(corr)
            if abs_corr > max_corr:
                max_corr = abs_corr
            effective_corr = corr if pos.direction == new_direction else -corr
            if abs(effective_corr) >= self._cfg.correlation_penalty_threshold:
                corr_pairs.append(pos.symbol + '(' + format(corr, '+.2f') + ')')
                if effective_corr > 0:
                    same_dir_count += 1
        if max_corr >= self._cfg.max_correlated_exposure:
            return CorrelationCheckResult(
                can_trade=False,
                reason='HIGH_CORRELATION ' + format(max_corr, '.2f') + ' >= ' + str(self._cfg.max_correlated_exposure),
                correlation_score=max_corr, correlated_pairs=corr_pairs,
                adjusted_risk_percent=0.0, risk_multiplier=0.0,
            )
        if same_dir_count >= self._cfg.max_same_direction_corr_pairs:
            return CorrelationCheckResult(
                can_trade=False,
                reason='TOO_MANY_CORRELATED_PAIRS ' + str(same_dir_count) + ' same-direction',
                correlation_score=max_corr, correlated_pairs=corr_pairs,
                adjusted_risk_percent=0.0, risk_multiplier=0.0,
            )
        multiplier = self._cfg.risk_multiplier_high_corr if corr_pairs else 1.0
        adj_risk = base_risk_percent * multiplier
        return CorrelationCheckResult(
            can_trade=True,
            reason='PASSED' if not corr_pairs else 'CORR_PENALTY x' + str(multiplier),
            correlation_score=max_corr, correlated_pairs=corr_pairs,
            adjusted_risk_percent=round(adj_risk, 3), risk_multiplier=multiplier,
        )

    def _get_correlation(self, a, b):
        a, b = a.upper(), b.upper()
        if a == b:
            return 1.0
        row = CORRELATION_MATRIX.get(a, {})
        if b in row:
            return row[b]
        row_b = CORRELATION_MATRIX.get(b, {})
        if a in row_b:
            return row_b[a]
        return None


_corr_filter = None

def get_correlation_filter():
    global _corr_filter
    if _corr_filter is None:
        _corr_filter = CorrelationFilter()
    return _corr_filter
