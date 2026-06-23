"""backend/services/trade_service_patch.py -- Phase U
U-1: ZeroDivisionError in compute_statistics on empty trades + profit_factor
U-2: close_trade pnl_usd never passed to EquityProtection
U-3: get_open_trades symbol filter Python-side fix
U-4: get_trade_history date range Python-side fix
U-5: idempotency lookup missing user_id cross-user info leak fix
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
from backend.core.logger import get_logger
logger = get_logger("services.trade_service_patch")


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    """Never raises ZeroDivisionError."""
    return num / den if den else default


def compute_statistics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """U-1 FIX: profit_factor + no ZeroDivisionError on empty/loss-only."""
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "largest_win": 0.0, "largest_loss": 0.0,
        }
    closed = [t for t in trades if t.get("status") == "closed"]
    total = len(closed)
    pnls = [float(t.get("pnl_usd") or 0.0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    return {
        "total_trades":  total,
        "win_rate":      _safe_div(len(wins) * 100.0, total),
        "total_pnl":     sum(pnls),
        "gross_profit":  gp,
        "gross_loss":    gl,
        "profit_factor": _safe_div(gp, gl),
        "avg_win":       _safe_div(gp, len(wins)),
        "avg_loss":      _safe_div(gl, len(losses)),
        "largest_win":   max(wins, default=0.0),
        "largest_loss":  min(losses, default=0.0),
    }


async def notify_equity_protection(pnl_usd: float, new_equity: float, new_balance: float) -> None:
    """U-2 FIX: call after close_trade() to update EquityProtection."""
    try:
        from backend.risk.equity_protection import get_equity_protection
        ep = get_equity_protection()
        ep.record_trade_result(pnl_usd)
        ep.update_equity(new_equity, new_balance)
    except Exception as exc:
        logger.warning("equity_protection notify failed (non-fatal): %s", exc)


def build_open_trades_filters(user_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
    """U-3 FIX: push symbol filter to DB instead of Python-side."""
    f: Dict[str, Any] = {"user_id": user_id, "status": "open"}
    if symbol:
        f["symbol"] = symbol.upper().strip()
    return f


def build_history_filters(
    user_id: str,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """U-4 FIX: date range pushed to DB via gte/lte filters."""
    f: Dict[str, Any] = {"user_id": user_id}
    if symbol:    f["symbol"]          = symbol.upper().strip()
    if status:    f["status"]          = status
    if from_date: f["opened_at__gte"]  = from_date
    if to_date:   f["opened_at__lte"]  = to_date
    return f


async def check_signal_idempotency(db: Any, signal_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """U-5 FIX: always scope idempotency check to user_id to prevent info leak."""
    try:
        return await db.select_one("trades", {"signal_id": signal_id, "user_id": user_id})
    except Exception as exc:
        logger.warning("idempotency check failed signal=%s: %s", signal_id, exc)
        return None
