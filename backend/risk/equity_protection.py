"""backend/risk/equity_protection.py
Phase Q Fix Q-12: cooldown_remaining_minutes always >= 0.0
PHASE Q Fix BUG: engine must stay HALTED during cooldown even if drawdown improves
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ProtectionLevel(str, Enum):
    SAFE     = "SAFE"
    WARNING  = "WARNING"
    HALTED   = "HALTED"
    CRITICAL = "CRITICAL"


@dataclass
class EquityProtectionConfig:
    max_drawdown_percent:          float = 20.0  # % below HWM
    warning_drawdown_percent:      float = 10.0  # % warning level
    max_consecutive_losses:        int   = 5     # deprecated alias
    consecutive_loss_halt_count:   int   = 5
    equity_recovery_required:      float = 5.0   # % recovery needed to resume
    cooldown_minutes:               int   = 60
    daily_loss_halt_percent:       float = 5.0   # % of balance
    weekly_loss_halt_percent:       float = 10.0  # % of balance
    monthly_drawdown_halt_percent:  float = 20.0  # % of balance


@dataclass
class EquityState:
    balance:                  float = 0.0
    equity:                   float = 0.0
    high_water_mark:          float = 0.0
    current_drawdown_percent: float = 0.0
    consecutive_losses:       int   = 0
    daily_loss_usd:           float = 0.0
    weekly_loss_usd:          float = 0.0
    monthly_loss_usd:         float = 0.0
    daily_loss_percent:       float = 0.0
    total_trades:             int   = 0
    protection_level:         ProtectionLevel = ProtectionLevel.SAFE
    halt_reason:              str = ""
    halt_time:                Optional[datetime] = None
    _initialized:             bool = False


@dataclass
class ProtectionCheckResult:
    can_trade:                 bool
    level:                     ProtectionLevel
    reason:                    str
    drawdown_percent:          float
    consecutive_losses:        int
    daily_loss_percent:        float
    should_close_all:          bool = False
    cooldown_remaining_minutes: float = 0.0  # Q-12: always >= 0.0


class EquityProtectionEngine:
    def __init__(self, config: Optional[EquityProtectionConfig] = None) -> None:
        self._cfg = config or EquityProtectionConfig()
        self._state = EquityState()

    def initialize(self, initial_balance: float) -> None:
        if initial_balance <= 0:
            raise ValueError(f"initial_balance must be > 0, got {initial_balance}")
        self._state.balance = initial_balance
        self._state.equity = initial_balance
        self._state.high_water_mark = initial_balance
        self._state._initialized = True

    def update_equity(self, equity: float, balance: float) -> None:
        if not self._state._initialized:
            self.initialize(max(balance, equity))
        self._state.equity = equity; self._state.balance = balance
        if equity > self._state.high_water_mark:
            self._state.high_water_mark = equity
        if self._state.high_water_mark > 0:
            dd = (self._state.high_water_mark - equity) / self._state.high_water_mark * 100.0
            self._state.current_drawdown_percent = max(0.0, dd)
        else:
            self._state.current_drawdown_percent = 0.0

    def record_trade_result(self, pnl_usd: float) -> None:
        if pnl_usd < 0:
            self._state.consecutive_losses += 1
            self._state.daily_loss_usd += abs(pnl_usd)
            self._state.weekly_loss_usd += abs(pnl_usd)
            self._state.monthly_loss_usd += abs(pnl_usd)
        else:
            self._state.consecutive_losses = 0
        self._state.total_trades += 1
        if self._state.balance > 0:
            self._state.daily_loss_percent = self._state.daily_loss_usd / self._state.balance * 100.0

    def _cooldown_remaining(self) -> float:
        """Q-12: always returns >= 0.0"""
        if self._state.halt_time is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self._state.halt_time).total_seconds() / 60.0
        return max(0.0, self._cfg.cooldown_minutes - elapsed)  # Q-12 FIX

    def check(self) -> ProtectionCheckResult:
        state = self._state; cfg = self._cfg
        if not state._initialized:
            return ProtectionCheckResult(can_trade=False, level=ProtectionLevel.HALTED, reason="Not initialized", drawdown_percent=0.0, consecutive_losses=0, daily_loss_percent=0.0, cooldown_remaining_minutes=0.0)
        cooldown_left = self._cooldown_remaining()
        # FIX: If HALTED and cooldown still active, stay blocked regardless of current drawdown
        if state.protection_level == ProtectionLevel.HALTED:
            if cooldown_left > 0.0:
                return self._halted_result(cooldown_left)
            else:
                # Cooldown expired - reset to SAFE and re-evaluate
                state.protection_level = ProtectionLevel.SAFE; state.halt_reason = ""; state.halt_time = None
        if state.current_drawdown_percent >= cfg.max_drawdown_percent:
            self._set_halt(f"Max drawdown {state.current_drawdown_percent:.1f}%"); return self._halted_result(self._cooldown_remaining())
        if state.daily_loss_percent >= cfg.daily_loss_halt_percent:
            self._set_halt(f"Daily loss {state.daily_loss_percent:.1f}%"); return self._halted_result(self._cooldown_remaining())
        if state.consecutive_losses >= cfg.consecutive_loss_halt_count:
            self._set_halt(f"Consecutive losses {state.consecutive_losses}"); return self._halted_result(self._cooldown_remaining())
        if state.balance > 0:
            weekly_pct = state.weekly_loss_usd / state.balance * 100.0
            if weekly_pct >= cfg.weekly_loss_halt_percent:
                self._set_halt(f"Weekly loss {weekly_pct:.1f}%"); return self._halted_result(self._cooldown_remaining())
        if state.protection_level == ProtectionLevel.HALTED:
            return self._halted_result(cooldown_left)
        if state.current_drawdown_percent >= cfg.warning_drawdown_percent:
            state.protection_level = ProtectionLevel.WARNING
            return ProtectionCheckResult(can_trade=True, level=ProtectionLevel.WARNING, reason=f"Drawdown warning {state.current_drawdown_percent:.1f}%", drawdown_percent=state.current_drawdown_percent, consecutive_losses=state.consecutive_losses, daily_loss_percent=state.daily_loss_percent, cooldown_remaining_minutes=0.0)
        state.protection_level = ProtectionLevel.SAFE
        return ProtectionCheckResult(can_trade=True, level=ProtectionLevel.SAFE, reason="", drawdown_percent=state.current_drawdown_percent, consecutive_losses=state.consecutive_losses, daily_loss_percent=state.daily_loss_percent, cooldown_remaining_minutes=0.0)

    def _set_halt(self, reason: str) -> None:
        if self._state.protection_level != ProtectionLevel.HALTED:
            self._state.protection_level = ProtectionLevel.HALTED
            self._state.halt_reason = reason
            self._state.halt_time = datetime.now(timezone.utc)

    def _halted_result(self, cooldown_left: float) -> ProtectionCheckResult:
        return ProtectionCheckResult(can_trade=False, level=ProtectionLevel.HALTED, reason=self._state.halt_reason, drawdown_percent=self._state.current_drawdown_percent, consecutive_losses=self._state.consecutive_losses, daily_loss_percent=self._state.daily_loss_percent, should_close_all=True, cooldown_remaining_minutes=cooldown_left)

    def status(self) -> dict:
        s = self._state
        return {"balance": s.balance, "equity": s.equity, "high_water_mark": s.high_water_mark, "drawdown_percent": round(s.current_drawdown_percent, 2), "consecutive_losses": s.consecutive_losses, "daily_loss_percent": round(s.daily_loss_percent, 2), "protection_level": s.protection_level.value, "halt_reason": s.halt_reason, "cooldown_remaining": round(self._cooldown_remaining(), 1)}
