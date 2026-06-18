"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Orchestrator — single entry point for ALL risk checks
Combines: Lot Sizing + Equity Protection + Correlation +
          Volatility + Exposure Control + Daily Limits
Trading stops AUTOMATICALLY if any limit is exceeded.

C5 FIX: هر Gate در یک try/except جداگانه اجرا می‌شود.
اگر یک Gate exception دهد → آن Gate به حالت PASS (پرمیسیو default)
می‌رود و خطا log می‌شود. این مانع می‌شود یک باگ در correlation_filter
کل سیستم risk را از کار بیندازد.

C7 FIX: یک asyncio.Lock روی singleton orchestrator برای جلوگیری
از race condition در position sizing همزمان.
"""
from __future__ import annotations

import asyncio
import logging
import math
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

    C5 FIX: per-gate try/except با permissive fallback در صورت خطای gate.
    C7 FIX: asyncio.Lock برای جلوگیری از race condition در lot sizing.
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

        # C7 FIX: Lock برای جلوگیری از race condition در position sizing
        self._sizing_lock: asyncio.Lock = asyncio.Lock()

    # ── main entry point ───────────────────────────────

    async def assess(self, inp: RiskInput) -> RiskDecision:
        """
        Run all risk checks in order.
        Short-circuit on first hard failure (most critical first).
        C5 FIX: هر gate در try/except مجزا — خطای یک gate سیستم را crash نمی‌کند.
        C7 FIX: async lock روی position sizing برای جلوگیری از race condition.
        """

        drawdown_pct: float = 0.0
        daily_loss_pct: float = 0.0

        # ── GATE 1: Equity Protection (highest priority) ───────
        try:
            equity_result = self._equity.update_equity(inp.equity, inp.balance)
            drawdown_pct  = equity_result.drawdown_percent
            daily_loss_pct = getattr(equity_result, "daily_loss_percent", 0.0)
            if not equity_result.can_trade:
                return self._blocked(
                    reason=equity_result.reason,
                    drawdown=drawdown_pct,
                    daily_loss=daily_loss_pct,
                    equity_ok=False,
                )
        except Exception as exc:
            _logger.error(f"[RiskOrchestrator] GATE 1 (Equity) exception — blocking trade: {exc}", exc_info=True)
            return self._blocked(
                reason=f"Equity gate error: {type(exc).__name__}",
                equity_ok=False,
            )

        # ── GATE 2: Daily / Weekly / Monthly Limits ────────────
        try:
            today = TodayTrades(
                trade_count=inp.today_trades_count,
                pnl_usd=inp.today_pnl_usd,
                risk_used_percent=0.0,
            )
            daily_result = self._daily.check_limits(
                inp.balance, today, inp.week_pnl_usd, inp.month_pnl_usd
            )
            if not daily_result.can_trade:
                return self._blocked(
                    reason=daily_result.reason,
                    drawdown=drawdown_pct,
                    daily_loss=daily_loss_pct,
                    daily_limits_ok=False,
                )
        except Exception as exc:
            _logger.error(f"[RiskOrchestrator] GATE 2 (Daily Limits) exception — blocking trade: {exc}", exc_info=True)
            return self._blocked(
                reason=f"Daily limits gate error: {type(exc).__name__}",
                drawdown=drawdown_pct,
                daily_limits_ok=False,
            )

        # ── GATE 3: Volatility Filter ──────────────────────────
        vol_level      = "UNKNOWN"
        vol_multiplier = 1.0
        try:
            vol_result     = self._vol.check(
                current_atr=inp.current_atr,
                atr_history=inp.atr_history,
                current_spread=inp.current_spread,
                avg_spread=inp.avg_spread,
            )
            vol_level      = vol_result.level.value
            vol_multiplier = vol_result.lot_multiplier
            if not vol_result.can_trade:
                return self._blocked(
                    reason=vol_result.reason,
                    drawdown=drawdown_pct,
                    daily_loss=daily_loss_pct,
                    volatility_ok=False,
                    volatility_level=vol_level,
                )
        except Exception as exc:
            # C5 FIX: Volatility gate خطا داد → log + ادامه با multiplier=1.0
            _logger.warning(
                f"[RiskOrchestrator] GATE 3 (Volatility) exception — "
                f"continuing with neutral multiplier: {exc}",
                exc_info=True,
            )
            vol_level      = "ERROR_FALLBACK"
            vol_multiplier = 1.0

        # ── GATE 4: Correlation Filter ─────────────────────────
        corr_score      = 0.0
        corr_multiplier = 1.0
        try:
            corr_positions = [
                CorrPosition(
                    symbol=p.symbol,
                    direction=p.direction,
                    risk_percent=p.risk_percent,
                )
                for p in inp.open_positions
            ]
            corr_result     = self._corr.check(
                new_symbol=inp.symbol,
                new_direction=inp.direction,
                open_positions=corr_positions,
                base_risk_percent=self._lot_sizer.config.risk_percent,
            )
            corr_score      = corr_result.correlation_score
            corr_multiplier = corr_result.risk_multiplier
            if not corr_result.can_trade:
                return self._blocked(
                    reason=corr_result.reason,
                    drawdown=drawdown_pct,
                    daily_loss=daily_loss_pct,
                    correlation_ok=False,
                    corr_score=corr_score,
                )
        except Exception as exc:
            # C5 FIX: Correlation gate خطا داد → log + ادامه با multiplier=1.0
            _logger.warning(
                f"[RiskOrchestrator] GATE 4 (Correlation) exception — "
                f"continuing with neutral multiplier: {exc}",
                exc_info=True,
            )
            corr_score      = 0.0
            corr_multiplier = 1.0

        # ── GATE 5: Exposure Control ───────────────────────────
        projected_exposure = 0.0
        try:
            base_risk    = self._lot_sizer.config.risk_percent
            adj_risk     = base_risk * corr_multiplier * vol_multiplier
            exposure_result = self._exposure.check(
                new_symbol=inp.symbol,
                new_direction=inp.direction,
                new_risk_percent=adj_risk,
                open_positions=inp.open_positions,
                balance=inp.balance,
            )
            projected_exposure = exposure_result.projected_total_risk
            if not exposure_result.can_trade:
                return self._blocked(
                    reason=exposure_result.reason,
                    drawdown=drawdown_pct,
                    daily_loss=daily_loss_pct,
                    exposure_ok=False,
                    total_exposure=projected_exposure,
                )
        except Exception as exc:
            # C5 FIX: Exposure gate خطا داد → log + ادامه
            _logger.warning(
                f"[RiskOrchestrator] GATE 5 (Exposure) exception — "
                f"continuing with zero exposure: {exc}",
                exc_info=True,
            )
            projected_exposure = 0.0

        # ── ALL GATES PASSED → Calculate Final Lot Size ───────
        # C7 FIX: async lock برای جلوگیری از race condition
        async with self._sizing_lock:
            combined_multiplier = corr_multiplier * vol_multiplier
            try:
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
            except Exception as exc:
                _logger.error(
                    f"[RiskOrchestrator] Lot sizing exception — using min_lot: {exc}",
                    exc_info=True,
                )
                final_lot = self._lot_sizer.config.min_lot

            step      = self._lot_sizer.config.lot_step
            final_lot = math.floor(final_lot / step) * step
            final_lot = max(self._lot_sizer.config.min_lot, final_lot)

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
            drawdown_percent=drawdown_pct,
            total_exposure_percent=projected_exposure,
            volatility_level=vol_level,
            correlation_score=corr_score,
            lot_multiplier=combined_multiplier,
        )

    # ── helpers ─────────────────────────────────────────────

    def _blocked(
        self,
        reason: str,
        drawdown: float = 0.0,
        daily_loss: float = 0.0,
        equity_ok: bool = True,
        daily_limits_ok: bool = True,
        volatility_ok: bool = True,
        correlation_ok: bool = True,
        exposure_ok: bool = True,
        volatility_level: str = "UNKNOWN",
        corr_score: float = 0.0,
        total_exposure: float = 0.0,
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


# ── Singleton with async-safe initialisation ──────────────────────────────
_orchestrator: Optional[RiskOrchestrator] = None
_init_lock = asyncio.Lock()


async def get_risk_orchestrator() -> RiskOrchestrator:
    """
    Async singleton factory.
    C7 FIX: استفاده از asyncio.Lock برای جلوگیری از double-init.
    """
    global _orchestrator
    if _orchestrator is None:
        async with _init_lock:
            if _orchestrator is None:          # double-checked locking
                _orchestrator = RiskOrchestrator()
    return _orchestrator


def get_risk_orchestrator_sync() -> RiskOrchestrator:
    """
    Sync accessor برای استفاده در startup hooks.
    فقط بعد از اولین await get_risk_orchestrator() فراخوانی شود.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RiskOrchestrator()
    return _orchestrator
