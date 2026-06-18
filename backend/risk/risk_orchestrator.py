"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Orchestrator — single entry point for ALL risk checks
Combines: Lot Sizing + Equity Protection + Correlation +
          Volatility + Exposure Control + Daily Limits
Trading stops AUTOMATICALLY if any limit is exceeded.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone

from .lot_sizing        import DynamicLotSizer, LotSizingConfig, get_lot_sizer
from .equity_protection import EquityProtectionEngine, get_equity_protection
from .correlation_filter import CorrelationFilter, OpenPosition as CorrPosition, get_correlation_filter
from .volatility_filter  import VolatilityFilter, get_volatility_filter
from .exposure_control   import ExposureControlEngine, ExposurePosition, get_exposure_control
from .daily_limits       import DailyLimitsEngine


@dataclass
class RiskInput:
    """All inputs needed for a complete risk assessment."""
    symbol: str
    direction: str              # "BUY" | "SELL"
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
    """Final risk decision with complete audit trail."""
    approved: bool
    block_reason: str           # empty if approved
    lot_size: float
    risk_percent: float
    risk_usd: float

    # Individual gate results
    equity_ok: bool
    daily_limits_ok: bool
    volatility_ok: bool
    correlation_ok: bool
    exposure_ok: bool

    # Metrics
    drawdown_percent: float
    total_exposure_percent: float
    volatility_level: str
    correlation_score: float
    lot_multiplier: float       # combined from vol + corr adjustments

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "block_reason": self.block_reason,
            "lot_size": self.lot_size,
            "risk_percent": self.risk_percent,
            "risk_usd": round(self.risk_usd, 2),
            "gates": {
                "equity": self.equity_ok,
                "daily_limits": self.daily_limits_ok,
                "volatility": self.volatility_ok,
                "correlation": self.correlation_ok,
                "exposure": self.exposure_ok,
            },
            "metrics": {
                "drawdown_percent": round(self.drawdown_percent, 2),
                "total_exposure_percent": round(self.total_exposure_percent, 2),
                "volatility_level": self.volatility_level,
                "correlation_score": round(self.correlation_score, 3),
                "lot_multiplier": round(self.lot_multiplier, 3),
            },
            "timestamp": self.timestamp.isoformat(),
        }


class RiskOrchestrator:
    """
    Master Risk Engine — ALL trades must pass through here.
    One method: assess() → RiskDecision
    If not approved → trading is blocked automatically.
    """

    def __init__(
        self,
        lot_sizer:          Optional[DynamicLotSizer]        = None,
        equity_protection:  Optional[EquityProtectionEngine] = None,
        correlation_filter: Optional[CorrelationFilter]      = None,
        volatility_filter:  Optional[VolatilityFilter]       = None,
        exposure_control:   Optional[ExposureControlEngine]  = None,
        daily_limits:       Optional[DailyLimitsEngine]      = None,
    ):
        self._lot_sizer  = lot_sizer          or get_lot_sizer()
        self._equity     = equity_protection  or get_equity_protection()
        self._corr       = correlation_filter or get_correlation_filter()
        self._vol        = volatility_filter  or get_volatility_filter()
        self._exposure   = exposure_control   or get_exposure_control()
        self._daily      = daily_limits       or DailyLimitsEngine()

    # ── main entry point ────────────────────────────────────────

    def assess(self, inp: RiskInput) -> RiskDecision:
        """
        Run all risk checks in order.
        Short-circuit on first failure (most critical first).
        """

        # ── GATE 1: Equity Protection (highest priority) ───────
        equity_result = self._equity.update_equity(inp.equity, inp.balance)
        if not equity_result.can_trade:
            return self._blocked(
                reason=equity_result.reason,
                drawdown=equity_result.drawdown_percent,
                daily_loss=equity_result.daily_loss_percent,
                equity_ok=False,
            )

        # ── GATE 2: Daily / Weekly / Monthly Limits ────────────
        from .daily_limits import TodayTrades
        today = TodayTrades(
            trade_count=inp.today_trades_count,
            pnl_usd=inp.today_pnl_usd,
            risk_used_percent=0.0,  # calculated below
        )
        daily_result = self._daily.check_limits(inp.balance, today,
                                                 inp.week_pnl_usd,
                                                 inp.month_pnl_usd)
        if not daily_result.can_trade:
            return self._blocked(
                reason=daily_result.reason,
                drawdown=equity_result.drawdown_percent,
                daily_loss=equity_result.daily_loss_percent,
                daily_limits_ok=False,
            )

        # ── GATE 3: Volatility Filter ──────────────────────────
        vol_result = self._vol.check(
            current_atr=inp.current_atr,
            atr_history=inp.atr_history,
            current_spread=inp.current_spread,
            avg_spread=inp.avg_spread,
        )
        if not vol_result.can_trade:
            return self._blocked(
                reason=vol_result.reason,
                drawdown=equity_result.drawdown_percent,
                daily_loss=equity_result.daily_loss_percent,
                volatility_ok=False,
                volatility_level=vol_result.level.value,
            )

        # ── GATE 4: Correlation Filter ─────────────────────────
        corr_positions = [
            CorrPosition(symbol=p.symbol, direction=p.direction,
                         risk_percent=p.risk_percent)
            for p in inp.open_positions
        ]
        corr_result = self._corr.check(
            new_symbol=inp.symbol,
            new_direction=inp.direction,
            open_positions=corr_positions,
            base_risk_percent=self._lot_sizer.config.risk_percent,
        )
        if not corr_result.can_trade:
            return self._blocked(
                reason=corr_result.reason,
                drawdown=equity_result.drawdown_percent,
                daily_loss=equity_result.daily_loss_percent,
                correlation_ok=False,
                corr_score=corr_result.correlation_score,
            )

        # ── GATE 5: Exposure Control ───────────────────────────
        base_risk = self._lot_sizer.config.risk_percent
        adj_risk  = base_risk * corr_result.risk_multiplier * vol_result.lot_multiplier
        exposure_result = self._exposure.check(
            new_symbol=inp.symbol,
            new_direction=inp.direction,
            new_risk_percent=adj_risk,
            open_positions=inp.open_positions,
            balance=inp.balance,
        )
        if not exposure_result.can_trade:
            return self._blocked(
                reason=exposure_result.reason,
                drawdown=equity_result.drawdown_percent,
                daily_loss=equity_result.daily_loss_percent,
                exposure_ok=False,
                total_exposure=exposure_result.projected_total_risk,
            )

        # ── ALL GATES PASSED → Calculate Final Lot Size ───────
        combined_multiplier = corr_result.risk_multiplier * vol_result.lot_multiplier
        lot_result = self._lot_sizer.calculate(
            balance=inp.balance,
            stop_loss_pips=inp.stop_loss_pips,
            atr_pips=inp.current_atr,
            win_rate=inp.win_rate,
            avg_rr=inp.avg_rr,
            volatility_ratio=1.0 / max(combined_multiplier, 0.1),
        )
        final_lot = max(
            self._lot_sizer.config.min_lot,
            lot_result.lot_size * combined_multiplier,
        )
        import math
        step = self._lot_sizer.config.lot_step
        final_lot = math.floor(final_lot / step) * step

        risk_usd = final_lot * inp.stop_loss_pips * self._lot_sizer.config.pip_value_usd
        risk_pct = (risk_usd / inp.balance * 100) if inp.balance > 0 else 0.0

        return RiskDecision(
            approved=True,
            block_reason="",
            lot_size=final_lot,
            risk_percent=round(risk_pct, 3),
            risk_usd=round(risk_usd, 2),
            equity_ok=True,
            daily_limits_ok=True,
            volatility_ok=True,
            correlation_ok=True,
            exposure_ok=True,
            drawdown_percent=equity_result.drawdown_percent,
            total_exposure_percent=exposure_result.projected_total_risk,
            volatility_level=vol_result.level.value,
            correlation_score=corr_result.correlation_score,
            lot_multiplier=combined_multiplier,
        )

    # ── helpers ─────────────────────────────────────────────────

    def _blocked(self, reason: str, drawdown: float = 0.0,
                 daily_loss: float = 0.0,
                 equity_ok: bool = True, daily_limits_ok: bool = True,
                 volatility_ok: bool = True, correlation_ok: bool = True,
                 exposure_ok: bool = True, volatility_level: str = "UNKNOWN",
                 corr_score: float = 0.0, total_exposure: float = 0.0,
                 ) -> RiskDecision:
        return RiskDecision(
            approved=False,
            block_reason=reason,
            lot_size=0.0,
            risk_percent=0.0,
            risk_usd=0.0,
            equity_ok=equity_ok,
            daily_limits_ok=daily_limits_ok,
            volatility_ok=volatility_ok,
            correlation_ok=correlation_ok,
            exposure_ok=exposure_ok,
            drawdown_percent=drawdown,
            total_exposure_percent=total_exposure,
            volatility_level=volatility_level,
            correlation_score=corr_score,
            lot_multiplier=0.0,
        )

    def record_trade_result(self, pnl_usd: float, balance: float) -> None:
        """Call after every trade close."""
        self._equity.record_trade_result(pnl_usd, balance)

    def reset_daily(self) -> None:
        self._equity.reset_daily()
        self._daily.reset_daily()

    def reset_weekly(self) -> None:
        self._equity.reset_weekly()

    def reset_monthly(self) -> None:
        self._equity.reset_monthly()


# Singleton
_orchestrator: Optional[RiskOrchestrator] = None

def get_risk_orchestrator() -> RiskOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RiskOrchestrator()
    return _orchestrator
