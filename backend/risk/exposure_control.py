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

logger = logging.getLogger('risk.exposure_control')


@dataclass
class ExposurePosition:
    symbol:       str
    direction:    str
    risk_percent: float
    risk_usd:     float  = 0.0


@dataclass
class ExposureConfig:
    max_total_risk_percent:    float    = 5.0
    max_risk_per_symbol:       float    = 2.0
    max_open_trades:           int      = 5
    max_correlated_risk:       float    = 3.0
    fail_mode:                 FailMode = FailMode.FAIL_CLOSED


@dataclass
class ExposureSnapshot:
    total_risk_percent:   float
    risk_by_symbol:       Dict[str, float]
    risk_by_direction:    Dict[str, float]
    open_trade_count:     int
    max_symbol_risk:      float
    max_direction_risk:   float
    limit_breached:       bool
    breach_reason:        str


@dataclass
class ExposureCheckResult:
    can_trade:              bool
    reason:                 str   = ''
    current_total_risk:     float = 0.0
    projected_total_risk:   float = 0.0
    available_risk:         float = 0.0
    snapshot:               ExposureSnapshot = None


def _empty_snapshot() -> ExposureSnapshot:
    return ExposureSnapshot(
        total_risk_percent=0.0,
        risk_by_symbol={},
        risk_by_direction={},
        open_trade_count=0,
        max_symbol_risk=0.0,
        max_direction_risk=0.0,
        limit_breached=False,
        breach_reason='',
    )


class ExposureControlEngine:
    """
    Portfolio exposure gatekeeper.
    FIX-6: configurable fail_mode — exception in check()/get_snapshot()
            => FAIL_CLOSED blocks, FAIL_OPEN allows with CRITICAL log.
    """

    def __init__(self, config: ExposureConfig = None, fail_mode=None):
        self._cfg = config or ExposureConfig()
        _fm_src = fail_mode if fail_mode is not None else self._cfg.fail_mode
        self._fail_mode: FailMode = _coerce_fm(_fm_src)

    # ------------------------------------------------------------------
    # Public API — signatures unchanged
    # ------------------------------------------------------------------
    def check(
        self,
        new_symbol:       str,
        new_direction:    str,
        new_risk_percent: float,
        open_positions:   List[ExposurePosition] | None = None,
        account_balance:  float = 10_000.0,
    ) -> ExposureCheckResult:
        try:
            return self._check_inner(
                new_symbol, new_direction, new_risk_percent,
                open_positions, account_balance,
            )
        except Exception as exc:
            logger.exception(
                "ExposureControlEngine.check exception symbol=%s fail_mode=%s",
                new_symbol, self._fail_mode, exc_info=True,
            )
            snap = _empty_snapshot()
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return ExposureCheckResult(
                    can_trade=False,
                    reason=f'FAIL_CLOSED:EXPOSURE_EXCEPTION:{type(exc).__name__}',
                    snapshot=snap,
                )
            logger.critical(
                "FAIL_OPEN: ExposureControl exception swallowed symbol=%s fail_mode=%s: %s",
                new_symbol, self._fail_mode, exc,
            )
            return ExposureCheckResult(
                can_trade=True,
                reason='FAIL_OPEN_EXCEPTION_IGNORED',
                projected_total_risk=new_risk_percent,
                snapshot=snap,
            )

    def get_snapshot(
        self,
        open_positions: List[ExposurePosition] | None = None,
    ) -> ExposureSnapshot:
        try:
            return self._snapshot_inner(open_positions)
        except Exception as exc:
            logger.exception(
                "ExposureControlEngine.get_snapshot exception fail_mode=%s",
                self._fail_mode, exc_info=True,
            )
            if self._fail_mode is FailMode.FAIL_CLOSED:
                raise
            logger.critical(
                "FAIL_OPEN: get_snapshot exception swallowed fail_mode=%s: %s",
                self._fail_mode, exc,
            )
            return _empty_snapshot()

    # ------------------------------------------------------------------
    # Inner logic
    # ------------------------------------------------------------------
    def _check_inner(
        self,
        new_symbol:       str,
        new_direction:    str,
        new_risk_percent: float,
        open_positions:   List[ExposurePosition] | None,
        account_balance:  float,
    ) -> ExposureCheckResult:
        cfg  = self._cfg
        ops  = open_positions or []
        total = sum(p.risk_percent for p in ops)
        projected = total + new_risk_percent
        avail = cfg.max_total_risk_percent - total
        snap = self._snapshot_inner(ops)

        # total portfolio risk
        if projected > cfg.max_total_risk_percent:
            return ExposureCheckResult(
                can_trade=False,
                reason=f'MAX_TOTAL_RISK:{projected:.2f}>{cfg.max_total_risk_percent}',
                current_total_risk=total,
                projected_total_risk=projected,
                available_risk=avail,
                snapshot=snap,
            )
        # per-symbol risk
        sym_risk = sum(p.risk_percent for p in ops if p.symbol == new_symbol)
        sym_risk += new_risk_percent
        if sym_risk > cfg.max_risk_per_symbol:
            return ExposureCheckResult(
                can_trade=False,
                reason=f'MAX_SYMBOL_RISK:{new_symbol}:{sym_risk:.2f}>{cfg.max_risk_per_symbol}',
                current_total_risk=total,
                projected_total_risk=projected,
                available_risk=avail,
                snapshot=snap,
            )
        # max open trades
        if len(ops) >= cfg.max_open_trades:
            return ExposureCheckResult(
                can_trade=False,
                reason=f'MAX_OPEN_TRADES:{len(ops)}>={cfg.max_open_trades}',
                current_total_risk=total,
                projected_total_risk=projected,
                available_risk=avail,
                snapshot=snap,
            )
        return ExposureCheckResult(
            can_trade=True,
            reason='EXPOSURE_OK',
            current_total_risk=total,
            projected_total_risk=projected,
            available_risk=avail,
            snapshot=snap,
        )

    def _snapshot_inner(
        self,
        open_positions: List[ExposurePosition] | None,
    ) -> ExposureSnapshot:
        ops = open_positions or []
        total = sum(p.risk_percent for p in ops)
        by_sym: Dict[str, float] = {}
        by_dir: Dict[str, float] = {}
        for p in ops:
            by_sym[p.symbol]    = by_sym.get(p.symbol, 0.0)    + p.risk_percent
            by_dir[p.direction] = by_dir.get(p.direction, 0.0) + p.risk_percent
        max_sym = max(by_sym.values(), default=0.0)
        max_dir = max(by_dir.values(), default=0.0)
        breached = total > self._cfg.max_total_risk_percent
        return ExposureSnapshot(
            total_risk_percent=total,
            risk_by_symbol=by_sym,
            risk_by_direction=by_dir,
            open_trade_count=len(ops),
            max_symbol_risk=max_sym,
            max_direction_risk=max_dir,
            limit_breached=breached,
            breach_reason='MAX_TOTAL_RISK' if breached else '',
        )


_exposure_instance = None


def get_exposure_control(config: ExposureConfig = None) -> ExposureControlEngine:
    global _exposure_instance
    if _exposure_instance is None:
        _exposure_instance = ExposureControlEngine(config=config)
    return _exposure_instance
