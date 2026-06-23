"""backend/risk/risk_orchestrator.py
Phase Q Fixes:
  Q-9:  lot_size=0 blocked (never silent pass)
  Q-10: gates run in strict priority order
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from .lot_sizing         import DynamicLotSizer, LotSizingConfig, get_lot_sizer
from .equity_protection  import EquityProtectionEngine, get_equity_protection
from .correlation_filter import CorrelationFilter, OpenPosition as CorrPosition, get_correlation_filter
from .volatility_filter  import VolatilityFilter, get_volatility_filter
from .exposure_control   import ExposureControlEngine, ExposurePosition, get_exposure_control
from .daily_limits       import DailyLimitsEngine, TodayTrades

_logger = logging.getLogger(__name__)


@dataclass
class RiskInput:
    symbol: str
    direction: str
    balance: float
    equity: float
    stop_loss_pips: float
    current_atr: float
    atr_history: List[float]
    current_spread: float
    avg_spread: float
    open_positions: List[ExposurePosition]
    today_trades_count: int
    today_pnl_usd: float
    week_pnl_usd: float
    month_pnl_usd: float
    win_rate: float = 0.55
    avg_rr: float = 1.5
    volatility_ratio: float = 1.0


@dataclass
class RiskDecision:
    approved: bool
    block_reason: str
    lot_size: float
    risk_percent: float
    risk_usd: float
    equity_ok: bool
    daily_limits_ok: bool
    volatility_ok: bool
    correlation_ok: bool
    exposure_ok: bool
    drawdown_percent: float
    total_exposure_percent: float
    volatility_level: str
    correlation_score: float
    lot_multiplier: float
    pip_value_used: float = 10.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "approved": self.approved, "block_reason": self.block_reason,
            "lot_size": self.lot_size, "risk_percent": self.risk_percent,
            "risk_usd": self.risk_usd, "equity_ok": self.equity_ok,
            "daily_limits_ok": self.daily_limits_ok, "volatility_ok": self.volatility_ok,
            "correlation_ok": self.correlation_ok, "exposure_ok": self.exposure_ok,
            "drawdown_percent": self.drawdown_percent,
            "total_exposure_percent": self.total_exposure_percent,
            "volatility_level": self.volatility_level,
            "correlation_score": self.correlation_score,
            "lot_multiplier": self.lot_multiplier,
            "pip_value_used": self.pip_value_used,
            "timestamp": self.timestamp.isoformat(),
        }


def _blocked(reason: str, inp: RiskInput) -> RiskDecision:
    return RiskDecision(
        approved=False, block_reason=reason,
        lot_size=0.0, risk_percent=0.0, risk_usd=0.0,
        equity_ok=False, daily_limits_ok=False,
        volatility_ok=False, correlation_ok=False, exposure_ok=False,
        drawdown_percent=0.0, total_exposure_percent=0.0,
        volatility_level="UNKNOWN", correlation_score=0.0, lot_multiplier=0.0,
    )


class RiskOrchestrator:
    """
    Q-10: Gates run in STRICT PRIORITY ORDER:
      Gate 1: Equity Protection
      Gate 2: Daily Limits
      Gate 3: Volatility Filter
      Gate 4: Correlation Filter
      Gate 5: Exposure Control
      Gate 6: Lot Calculation
    Each gate can BLOCK all subsequent gates.
    """

    _instance: Optional["RiskOrchestrator"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "RiskOrchestrator":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._lot_sizer       = get_lot_sizer()
        self._equity_engine   = get_equity_protection()
        self._corr_filter     = get_correlation_filter()
        self._vol_filter      = get_volatility_filter()
        self._exposure_engine = get_exposure_control()
        self._daily_engine    = DailyLimitsEngine()
        self._initialized     = True
        _logger.info("RiskOrchestrator ready (Q-10: ordered gates)")

    async def evaluate(self, inp: RiskInput) -> RiskDecision:
        _logger.debug("Risk eval symbol=%s dir=%s balance=%.2f", inp.symbol, inp.direction, inp.balance)

        # Gate 1: Equity Protection
        try:
            ep = self._equity_engine
            ep.update_equity(inp.equity, inp.balance)
            res = ep.check()
            if not res.can_trade:
                reason = f"EquityProtection: {res.reason}"
                _logger.warning("Gate1 BLOCKED %s", reason)
                return _blocked(reason, inp)
            drawdown_pct = res.drawdown_percent
        except Exception as exc:
            _logger.error("Gate1 exception: %s", exc, exc_info=True)
            return _blocked(f"equity_protection_error: {exc}", inp)

        # Gate 2: Daily Limits
        try:
            today = TodayTrades(trade_count=inp.today_trades_count, pnl_usd=inp.today_pnl_usd, risk_used_percent=0.0)
            dr = self._daily_engine.check_limits(inp.balance, today, week_pnl_usd=inp.week_pnl_usd, month_pnl_usd=inp.month_pnl_usd)
            if not dr.can_trade:
                reason = f"DailyLimits: {dr.reason}"
                _logger.warning("Gate2 BLOCKED %s", reason)
                return _blocked(reason, inp)
        except Exception as exc:
            _logger.error("Gate2 exception: %s", exc, exc_info=True)
            return _blocked(f"daily_limits_error: {exc}", inp)

        # Gate 3: Volatility Filter
        vol_ok = False; vol_level = "UNKNOWN"; lot_mult = 1.0
        try:
            vr = self._vol_filter.check(atr_values=inp.atr_history, current_atr=inp.current_atr, spread=inp.current_spread, avg_spread=inp.avg_spread)
            vol_ok = vr.can_trade; vol_level = vr.volatility_level; lot_mult = getattr(vr, "lot_multiplier", 1.0)
            if not vol_ok:
                reason = f"VolatilityFilter: {vr.reason}"
                _logger.warning("Gate3 BLOCKED %s", reason)
                return _blocked(reason, inp)
        except Exception as exc:
            _logger.error("Gate3 exception: %s", exc, exc_info=True)
            vol_ok = True; vol_level = "UNKNOWN"; lot_mult = 0.8

        # Gate 4: Correlation Filter
        corr_ok = False; corr_score = 0.0
        try:
            cr_positions = [CorrPosition(symbol=p.symbol, direction=p.direction, risk_percent=p.risk_percent) for p in inp.open_positions]
            corr_res = self._corr_filter.check(inp.symbol, inp.direction, cr_positions)
            corr_ok = corr_res.can_trade; corr_score = getattr(corr_res, "correlation_score", 0.0)
            if not corr_ok:
                reason = f"CorrelationFilter: {corr_res.reason}"
                _logger.warning("Gate4 BLOCKED %s", reason)
                return _blocked(reason, inp)
        except Exception as exc:
            _logger.error("Gate4 exception: %s", exc, exc_info=True)
            corr_ok = True; corr_score = 0.0

        # Gate 5: Exposure Control
        exposure_ok = False; total_exposure = 0.0
        try:
            exp_res = self._exposure_engine.check(new_symbol=inp.symbol, new_direction=inp.direction, new_risk_percent=1.0, open_positions=inp.open_positions)
            exposure_ok = exp_res.can_trade; total_exposure = getattr(exp_res.snapshot, "total_risk_percent", 0.0)
            if not exposure_ok:
                reason = f"ExposureControl: {exp_res.reason}"
                _logger.warning("Gate5 BLOCKED %s", reason)
                return _blocked(reason, inp)
        except Exception as exc:
            _logger.error("Gate5 exception: %s", exc, exc_info=True)
            exposure_ok = True; total_exposure = 0.0

        # Gate 6: Lot Sizing — Q-9: zero lot BLOCKED
        try:
            cfg = LotSizingConfig(win_rate=inp.win_rate, avg_rr=inp.avg_rr)
            lot_result = await self._lot_sizer.calculate(symbol=inp.symbol, balance=inp.balance, stop_loss_pips=inp.stop_loss_pips, config=cfg)
            lot_size = round(max(0.0, lot_result.lot_size * lot_mult), 2)
            risk_pct = lot_result.risk_percent
            risk_usd = round(inp.balance * risk_pct / 100.0, 2)
            pip_value = getattr(lot_result, "pip_value", 10.0)
            # Q-9: zero lot is NEVER a silent pass
            if lot_size <= 0.0:
                reason = f"LotSizer returned zero lot (balance={inp.balance}, sl_pips={inp.stop_loss_pips}, symbol={inp.symbol})"
                _logger.error("Gate6 BLOCKED zero lot: %s", reason)
                return _blocked(reason, inp)
        except Exception as exc:
            _logger.error("Gate6 exception: %s", exc, exc_info=True)
            return _blocked(f"lot_sizing_error: {exc}", inp)

        _logger.info("Risk APPROVED symbol=%s lot=%.2f risk=%.2f%%", inp.symbol, lot_size, risk_pct)
        return RiskDecision(
            approved=True, block_reason="",
            lot_size=lot_size, risk_percent=risk_pct, risk_usd=risk_usd,
            equity_ok=True, daily_limits_ok=True, volatility_ok=vol_ok,
            correlation_ok=corr_ok, exposure_ok=exposure_ok,
            drawdown_percent=drawdown_pct, total_exposure_percent=total_exposure,
            volatility_level=vol_level, correlation_score=corr_score,
            lot_multiplier=lot_mult, pip_value_used=pip_value,
        )


def get_risk_orchestrator() -> RiskOrchestrator:
    return RiskOrchestrator()
