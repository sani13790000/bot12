"""backend/risk/equity_protection.py
Equity Protection Engine — guards account from drawdown.

Fixes:
  - Phase Q Fix Q-12: cooldown_remaining_minutes always >= 0.0
  - Phase Q BUG: engine must stay HALTED during cooldown even if drawdown improves
  - STRESS-3: cooldown enforcement fixed
  - PHASE1-MERGE U-6..U-10 from equity_protection_patch.py:
    U-6:  balance=0 -> HWM=0 -> 100% drawdown immediately (safe_initialize)
    U-7:  update_equity before initialize race condition (auto_init_guard)
    U-8:  halt state race condition (is_halted_check)
    U-9:  halt reason lost after restart (persist_halt_state/restore_halt_state)
    U-10: daily_loss_usd resets at midnight (maybe_reset_daily)
  - P4-FIX-V2-1: drawdown_pct = max(0.0,...) — no negative drawdown when equity>HWM
  - P4-FIX-V2-EP: check() method added — orchestrator calls check(), not can_trade()
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from ..core.logger import get_logger

logger = get_logger("risk.equity_protection")

_DEFAULT_BALANCE: float = 10_000.0


class ProtectionStatus(str, Enum):
    SAFE    = "SAFE"
    WARNING = "WARNING"
    HALTED  = "HALTED"


@dataclass
class EquityCheckResult:
    """P4-FIX-V2-EP: Result of EquityProtectionEngine.check()."""
    can_trade: bool
    level: ProtectionStatus
    reason: str


@dataclass
class EquityProtectionConfig:
    daily_loss_limit_pct:   float = 5.0
    total_drawdown_limit_pct: float = 10.0
    warning_drawdown_pct:   float = 7.0
    cooldown_minutes:           int   = 60
    trailing_hwm:               bool  = True


@dataclass
class EquityProtectionState:
    status:               ProtectionStatus = ProtectionStatus.SAFE
    high_water_mark:      float = 0.0
    current_equity:       float = 0.0
    daily_loss_usd:       float = 0.0
    daily_reset_date:     Optional[str] = None
    halt_reason:          Optional[str] = None
    halted_at:            Optional[datetime] = None
    initialized:          bool = False

    def cooldown_remaining_minutes(self) -> float:
        if self.halted_at is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self.halted_at).total_seconds() / 60
        return max(0.0, 60.0 - elapsed)


class EquityProtectionEngine:
    """Guards trading account against drawdown limits."""

    def __init__(self, config: Optional[EquityProtectionConfig] = None) -> None:
        self.config = config or EquityProtectionConfig()
        self.state  = EquityProtectionState()
        self._lock  = asyncio.Lock()

    def initialize(self, balance: float) -> None:
        """U-6: balance <= 0 uses fallback to prevent HWM=0 instant halt."""
        if balance <= 0:
            logger.debug("balance invalid, using fallback", balance=balance, fallback=_DEFAULT_BALANCE)
            balance = _DEFAULT_BALANCE
        self.state.high_water_mark  = balance
        self.state.current_equity   = balance
        self.state.daily_loss_usd   = 0.0
        self.state.daily_reset_date = datetime.now(timezone.utc).date().isoformat()
        self.state.initialized      = True
        logger.debug("initialized", hwm=balance)

    async def update_equity(self, equity: float, balance: float) -> None:
        """U-7: auto-initialize if not yet done."""
        async with self._lock:
            if not self.state.initialized:
                self.initialize(balance if balance > 0 else equity)

            # U-10: reset daily loss at midnight
            today = datetime.now(timezone.utc).date().isoformat()
            if self.state.daily_reset_date != today:
                self.state.daily_loss_usd   = 0.0
                self.state.daily_reset_date = today
                logger.debug("daily loss reset", date=today)

            prev = self.state.current_equity
            self.state.current_equity = equity
            if equity < prev:
                self.state.daily_loss_usd += prev - equity

            # Update HWM
            if self.config.trailing_hwm and equity > self.state.high_water_mark:
                self.state.high_water_mark = equity

            self._evaluate()

    def _evaluate(self) -> None:
        """Evaluate drawdown and update status. Must hold lock."""
        hwm    = self.state.high_water_mark
        equity = self.state.current_equity
        config = self.config

        if hwm <= 0:
            return

        # U-8: stay HALTED during cooldown
        if self.state.status == ProtectionStatus.HALTED:
            if self.state.cooldown_remaining_minutes() > 0:
                return  # stay halted
            else:
                # cooldown expired
                self.state.status     = ProtectionStatus.SAFE
                self.state.halt_reason = None
                self.state.halted_at   = None
                logger.debug("halt cooldown expired, resuming")
                return

        # P4-FIX-V2-1: max(0.0,...) prevents negative drawdown when equity > HWM
        drawdown_pct = max(0.0, (hwm - equity) / hwm * 100)
        daily_pct    = self.state.daily_loss_usd / hwm * 100

        if drawdown_pct >= config.total_drawdown_limit_pct or daily_pct >= config.daily_loss_limit_pct:
            reason = (
                f"drawdown={drawdown_pct:.1f}%" if drawdown_pct >= config.total_drawdown_limit_pct
                else f"daily_loss={daily_pct:.1f}%"
            )
            self.state.status     = ProtectionStatus.HALTED
            self.state.halt_reason = reason
            self.state.halted_at   = datetime.now(timezone.utc)
            logger.debug("HALTED", reason=reason)
        elif drawdown_pct >= config.warning_drawdown_pct:
            self.state.status = ProtectionStatus.WARNING
        else:
            self.state.status = ProtectionStatus.SAFE

    def can_trade(self) -> bool:
        return self.state.status != ProtectionStatus.HALTED

    def check(self) -> "EquityCheckResult":
        """P4-FIX-V2-EP: check() method — used by RiskOrchestrator GATE 1."""
        status = self.state.status
        can_trade = status != ProtectionStatus.HALTED
        reason = self.state.halt_reason or ""
        return EquityCheckResult(can_trade=can_trade, level=status, reason=reason)

    def get_status(self) -> dict:
        s = self.state
        return {
            "status":           s.status.value,
            "can_trade":        self.can_trade(),
            "high_water_mark":  s.high_water_mark,
            "current_equity":   s.current_equity,
            "daily_loss_usd":   s.daily_loss_usd,
            "halt_reason":      s.halt_reason,
            "cooldown_remaining_minutes": s.cooldown_remaining_minutes(),
        }


# ── U-6..U-10 helper functions (PHASE1-MERGE) ─────────────────────────────────

def safe_initialize(ep_engine: EquityProtectionEngine, balance: float) -> None:
    ep_engine.initialize(balance)


def auto_init_guard(ep_engine: EquityProtectionEngine, equity: float, balance: float) -> None:
    if not ep_engine.state.initialized:
        safe_initialize(ep_engine, balance if balance > 0 else equity)


def is_halted_check(ep_engine: EquityProtectionEngine) -> bool:
    return ep_engine.state.status == ProtectionStatus.HALTED


async def maybe_reset_daily(ep_engine: EquityProtectionEngine) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if ep_engine.state.daily_reset_date != today:
        async with ep_engine._lock:
            ep_engine.state.daily_loss_usd   = 0.0
            ep_engine.state.daily_reset_date = today
            logger.debug("daily loss reset", date=today)


async def persist_halt_state(ep_engine: EquityProtectionEngine, db: Any) -> None:
    try:
        await db.upsert("equity_protection_state", {
            "status":      ep_engine.state.status.value,
            "halt_reason": ep_engine.state.halt_reason,
            "halted_at":   ep_engine.state.halted_at.isoformat() if ep_engine.state.halted_at else None,
        })
    except Exception as exc:
        logger.debug("persist_halt_state failed", error=str(exc))


async def restore_halt_state(ep_engine: EquityProtectionEngine, db: Any) -> None:
    try:
        row = await db.select_one("equity_protection_state", {})
        if row and row.get("status") == ProtectionStatus.HALTED.value:
            ep_engine.state.status     = ProtectionStatus.HALTED
            ep_engine.state.halt_reason = row.get("halt_reason")
            halted_at = row.get("halted_at")
            if halted_at:
                ep_engine.state.halted_at = datetime.fromisoformat(halted_at)
            logger.debug("halt state restored from DB", reason=ep_engine.state.halt_reason)
    except Exception as exc:
        logger.debug("restore_halt_state failed", error=str(exc))


# Singleton
_ep_instance: Optional[EquityProtectionEngine] = None
_ep_lock = asyncio.Lock()


async def get_equity_protection_engine() -> EquityProtectionEngine:
    global _ep_instance
    async with _ep_lock:
        if _ep_instance is None:
            _ep_instance = EquityProtectionEngine()
        return _ep_instance
