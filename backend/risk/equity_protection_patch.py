"""backend/risk/equity_protection_patch.py -- Phase U
U-6:  balance=0 -> HWM=0 -> 100% drawdown immediately
U-7:  update_equity before initialize race condition
U-8:  halt state race condition
U-9:  halt reason lost after restart
U-10: daily_loss_usd never resets at midnight
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
from backend.core.logger import get_logger
logger = get_logger("risk.equity_protection_patch")

_DEFAULT_BALANCE: float = 10_000.0


def safe_initialize(ep_engine: object, balance: float) -> None:
    """U-6 FIX: balance<=0 uses fallback to prevent HWM=0 instant halt."""
    if balance <= 0:
        logger.critical(
            "[EquityProtection] balance=%.2f invalid, using fallback=%.2f",
            balance, _DEFAULT_BALANCE,
        )
        balance = _DEFAULT_BALANCE
    ep_engine.initialize(balance)
    logger.info("[EquityProtection] initialized HWM=%.2f", ep_engine.state.high_water_mark)


def auto_init_guard(ep_engine: object, equity: float, balance: float) -> None:
    """U-7 FIX: auto-initialize if update_equity called before initialize."""
    if not ep_engine.is_initialized:
        real = balance if balance > 0 else equity if equity > 0 else _DEFAULT_BALANCE
        logger.warning("[EquityProtection] auto-init with balance=%.2f", real)
        ep_engine.initialize(real)


def is_halted_check(ep_engine: object) -> bool:
    """U-8: returns True if currently HALTed."""
    try:
        from backend.risk.equity_protection import ProtectionLevel
        return ep_engine.state.protection_level == ProtectionLevel.HALT
    except Exception:
        return False


_last_reset_date: Optional[str] = None
_reset_lock = asyncio.Lock()


async def maybe_reset_daily(ep_engine: object) -> None:
    """U-10 FIX: reset daily_loss_usd at midnight UTC."""
    global _last_reset_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with _reset_lock:
        if _last_reset_date != today:
            try:
                ep_engine.reset_daily()
                _last_reset_date = today
                logger.info("[EquityProtection] Daily reset for %s", today)
            except Exception as exc:
                logger.warning("[EquityProtection] reset_daily failed: %s", exc)


async def persist_halt_state(ep_engine: object, db: object) -> None:
    """U-9 FIX: persist halt reason to DB for restart recovery."""
    try:
        from backend.risk.equity_protection import ProtectionLevel
        if ep_engine.state.protection_level != ProtectionLevel.HALT:
            return
        state = ep_engine.state
        await db.upsert("system_state", {
            "key": "equity_protection_halt",
            "value": {
                "halted": True,
                "reason": getattr(state, "halt_reason", "unknown"),
                "drawdown_pct": round(state.current_drawdown_percent, 4),
                "high_water_mark": round(state.high_water_mark, 4),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        })
    except Exception as exc:
        logger.warning("persist_halt_state failed: %s", exc)


async def restore_halt_state(ep_engine: object, db: object) -> None:
    """U-9 FIX: restore halt on startup from DB."""
    try:
        row = await db.select_one("system_state", {"key": "equity_protection_halt"})
        if row and isinstance(row.get("value"), dict) and row["value"].get("halted"):
            val = row["value"]
            logger.critical("[EquityProtection] Restoring HALT: %s", val.get("reason", "?"))
            hwm = float(val.get("high_water_mark", _DEFAULT_BALANCE))
            if not ep_engine.is_initialized:
                ep_engine.initialize(hwm)
            ep_engine._set_halt(val.get("reason", "restored_from_db"))
    except Exception as exc:
        logger.warning("restore_halt_state failed: %s", exc)
