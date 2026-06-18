"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Equity Protection Engine
- Drawdown guard
- Consecutive loss stop
- Equity high-water mark
- Auto-halt + cooldown
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ProtectionLevel(str, Enum):
    SAFE        = "SAFE"
    WARNING     = "WARNING"
    RESTRICTED  = "RESTRICTED"
    HALTED      = "HALTED"


@dataclass
class EquityProtectionConfig:
    max_drawdown_percent: float = 10.0       # hard halt
    warning_drawdown_percent: float = 5.0   # warning zone
    max_consecutive_losses: int = 5
    consecutive_loss_halt_count: int = 3     # halt after N consecutive
    equity_recovery_required: float = 2.0   # % recovery to resume
    cooldown_minutes: int = 60               # after halt
    daily_loss_halt_percent: float = 3.0
    weekly_loss_halt_percent: float = 7.0
    monthly_drawdown_halt_percent: float = 15.0


@dataclass
class EquityState:
    balance: float = 0.0
    equity: float = 0.0
    high_water_mark: float = 0.0
    current_drawdown_percent: float = 0.0
    consecutive_losses: int = 0
    total_trades: int = 0
    daily_loss_usd: float = 0.0
    daily_loss_percent: float = 0.0
    weekly_loss_usd: float = 0.0
    monthly_loss_usd: float = 0.0
    protection_level: ProtectionLevel = ProtectionLevel.SAFE
    halt_reason: str = ""
    halt_time: Optional[datetime] = None
    last_reset_date: Optional[datetime] = None


@dataclass
class ProtectionCheckResult:
    can_trade: bool
    level: ProtectionLevel
    reason: str
    drawdown_percent: float
    consecutive_losses: int
    daily_loss_percent: float
    should_close_all: bool = False
    cooldown_remaining_minutes: float = 0.0


class EquityProtectionEngine:
    """
    Production-grade Equity Protection:
    - Real-time drawdown monitoring
    - Consecutive loss tracking
    - Daily/Weekly/Monthly loss limits
    - Auto-halt with cooldown
    - High-water mark maintenance
    """

    def __init__(self, config: Optional[EquityProtectionConfig] = None):
        self._cfg   = config or EquityProtectionConfig()
        self._state = EquityState()

    # ── public API ──────────────────────────────────────────────

    def initialize(self, balance: float) -> None:
        """Call once at startup with current account balance."""
        self._state.balance        = balance
        self._state.equity         = balance
        self._state.high_water_mark = balance
        self._state.last_reset_date = datetime.now(timezone.utc)

    def update_equity(self, current_equity: float, current_balance: float) -> ProtectionCheckResult:
        """Update equity state and return protection status."""
        self._state.equity  = current_equity
        self._state.balance = current_balance

        # Update high-water mark
        if current_equity > self._state.high_water_mark:
            self._state.high_water_mark = current_equity

        # Calculate drawdown from HWM
        hwm = self._state.high_water_mark
        if hwm > 0:
            self._state.current_drawdown_percent = ((hwm - current_equity) / hwm) * 100
        else:
            self._state.current_drawdown_percent = 0.0

        return self._evaluate()

    def record_trade_result(self, pnl_usd: float, balance: float) -> ProtectionCheckResult:
        """Record trade P&L and update protection state."""
        self._state.total_trades += 1

        if pnl_usd < 0:
            self._state.consecutive_losses += 1
            abs_loss = abs(pnl_usd)
            self._state.daily_loss_usd   += abs_loss
            self._state.weekly_loss_usd  += abs_loss
            self._state.monthly_loss_usd += abs_loss
        else:
            self._state.consecutive_losses = 0  # reset on win

        if balance > 0:
            self._state.daily_loss_percent = (self._state.daily_loss_usd / balance) * 100

        return self._evaluate()

    def check_can_trade(self) -> ProtectionCheckResult:
        """Check if new trade is allowed right now."""
        return self._evaluate()

    def reset_daily(self) -> None:
        """Call at midnight UTC."""
        self._state.daily_loss_usd     = 0.0
        self._state.daily_loss_percent = 0.0
        self._state.last_reset_date    = datetime.now(timezone.utc)

    def reset_weekly(self) -> None:
        self._state.weekly_loss_usd = 0.0

    def reset_monthly(self) -> None:
        self._state.monthly_loss_usd = 0.0

    def manual_resume(self) -> None:
        """Admin override — clear halt state."""
        self._state.protection_level = ProtectionLevel.SAFE
        self._state.halt_reason      = ""
        self._state.halt_time        = None

    @property
    def state(self) -> EquityState:
        return self._state

    # ── internal ────────────────────────────────────────────────

    def _evaluate(self) -> ProtectionCheckResult:
        cfg   = self._cfg
        state = self._state
        now   = datetime.now(timezone.utc)

        # ① check if already halted and cooldown active
        if state.halt_time:
            elapsed = (now - state.halt_time).total_seconds() / 60
            remaining = max(0.0, cfg.cooldown_minutes - elapsed)
            if remaining > 0:
                return ProtectionCheckResult(
                    can_trade=False,
                    level=ProtectionLevel.HALTED,
                    reason=f"HALTED: {state.halt_reason} | cooldown {remaining:.0f}m remaining",
                    drawdown_percent=state.current_drawdown_percent,
                    consecutive_losses=state.consecutive_losses,
                    daily_loss_percent=state.daily_loss_percent,
                    cooldown_remaining_minutes=remaining,
                )
            else:
                # Cooldown expired — check equity recovery
                recovery_ok = self._check_recovery()
                if recovery_ok:
                    state.halt_time   = None
                    state.halt_reason = ""
                    state.protection_level = ProtectionLevel.SAFE

        # ② max drawdown — HALT
        if state.current_drawdown_percent >= cfg.max_drawdown_percent:
            return self._halt(
                f"MAX DRAWDOWN {state.current_drawdown_percent:.1f}% >= {cfg.max_drawdown_percent}%",
                close_all=True,
            )

        # ③ consecutive losses — HALT
        if state.consecutive_losses >= cfg.consecutive_loss_halt_count:
            return self._halt(
                f"CONSECUTIVE LOSSES {state.consecutive_losses} >= {cfg.consecutive_loss_halt_count}",
            )

        # ④ daily loss limit
        if state.daily_loss_percent >= cfg.daily_loss_halt_percent:
            return self._halt(
                f"DAILY LOSS {state.daily_loss_percent:.1f}% >= {cfg.daily_loss_halt_percent}%",
            )

        # ⑤ weekly loss
        weekly_pct = (state.weekly_loss_usd / max(state.balance, 1)) * 100
        if weekly_pct >= cfg.weekly_loss_halt_percent:
            return self._halt(
                f"WEEKLY LOSS {weekly_pct:.1f}% >= {cfg.weekly_loss_halt_percent}%",
            )

        # ⑥ monthly drawdown
        monthly_pct = (state.monthly_loss_usd / max(state.balance, 1)) * 100
        if monthly_pct >= cfg.monthly_drawdown_halt_percent:
            return self._halt(
                f"MONTHLY DRAWDOWN {monthly_pct:.1f}% >= {cfg.monthly_drawdown_halt_percent}%",
            )

        # ⑦ warning zone
        if state.current_drawdown_percent >= cfg.warning_drawdown_percent:
            state.protection_level = ProtectionLevel.WARNING
            return ProtectionCheckResult(
                can_trade=True,
                level=ProtectionLevel.WARNING,
                reason=f"WARNING: drawdown {state.current_drawdown_percent:.1f}%",
                drawdown_percent=state.current_drawdown_percent,
                consecutive_losses=state.consecutive_losses,
                daily_loss_percent=state.daily_loss_percent,
            )

        # ✅ all clear
        state.protection_level = ProtectionLevel.SAFE
        return ProtectionCheckResult(
            can_trade=True,
            level=ProtectionLevel.SAFE,
            reason="SAFE",
            drawdown_percent=state.current_drawdown_percent,
            consecutive_losses=state.consecutive_losses,
            daily_loss_percent=state.daily_loss_percent,
        )

    def _halt(self, reason: str, close_all: bool = False) -> ProtectionCheckResult:
        self._state.protection_level = ProtectionLevel.HALTED
        self._state.halt_reason      = reason
        self._state.halt_time        = datetime.now(timezone.utc)
        return ProtectionCheckResult(
            can_trade=False,
            level=ProtectionLevel.HALTED,
            reason=f"HALTED: {reason}",
            drawdown_percent=self._state.current_drawdown_percent,
            consecutive_losses=self._state.consecutive_losses,
            daily_loss_percent=self._state.daily_loss_percent,
            should_close_all=close_all,
        )

    def _check_recovery(self) -> bool:
        hwm = self._state.high_water_mark
        if hwm <= 0:
            return True
        recovery_pct = ((self._state.equity - (hwm * (1 - self._cfg.max_drawdown_percent / 100)))
                        / hwm) * 100
        return recovery_pct >= self._cfg.equity_recovery_required


# Singleton
_equity_engine: Optional[EquityProtectionEngine] = None

def get_equity_protection() -> EquityProtectionEngine:
    global _equity_engine
    if _equity_engine is None:
        _equity_engine = EquityProtectionEngine()
    return _equity_engine
