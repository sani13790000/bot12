"""backend/services/trade_service.py v3 - Phase T + Phase1 Merge

PHASE1-MERGE U-1..U-5 from trade_service_patch.py:
  U-1: ZeroDivisionError in compute_statistics on empty trades + profit_factor
  U-2: close_trade pnl_usd passed to EquityProtection
  U-3: get_open_trades symbol filter
  U-4: get_trade_history date range filter
  U-5: idempotency lookup scoped to user_id to prevent cross-user info leak
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("services.trade_service")


# ── U-1 FIX: safe division ────────────────────────────────────────────────────
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
    total  = len(closed)
    if total == 0:
        return compute_statistics([])

    pnls        = [float(t.get("pnl_usd", 0.0)) for t in closed]
    winners     = [p for p in pnls if p > 0]
    losers      = [p for p in pnls if p < 0]
    gross_profit = sum(winners)
    gross_loss   = abs(sum(losers))

    return {
        "total_trades":  total,
        "win_rate":      _safe_div(len(winners), total),
        "total_pnl":     sum(pnls),
        "gross_profit":  gross_profit,
        "gross_loss":    gross_loss,
        "profit_factor": _safe_div(gross_profit, gross_loss),
        "avg_win":       _safe_div(sum(winners), len(winners)) if winners else 0.0,
        "avg_loss":      _safe_div(sum(losers),  len(losers))  if losers  else 0.0,
        "largest_win":   max(winners) if winners else 0.0,
        "largest_loss":  min(losers)  if losers  else 0.0,
    }


# ── U-2 FIX: notify equity protection on close ────────────────────────────────
async def notify_equity_protection(
    pnl_usd: float,
    new_equity: float,
    new_balance: float,
) -> None:
    """U-2 FIX: Pass pnl to EquityProtectionEngine after trade close."""
    try:
        from backend.risk.equity_protection import get_equity_protection_engine
        ep = await get_equity_protection_engine()
        await ep.update_equity(new_equity, new_balance)
    except Exception as exc:
        logger.debug("equity protection notify failed", exc_info=True)


# ── U-3 FIX: open trades filter ───────────────────────────────────────────────
def build_open_trades_filters(
    user_id: str,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """U-3 FIX: Build filters for open trades query."""
    f: Dict[str, Any] = {"user_id": user_id, "status": "open"}
    if symbol:
        f["symbol"] = symbol.upper().strip()
    return f


# ── U-4 FIX: history filter ───────────────────────────────────────────────────
def build_history_filters(
    user_id: str,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """U-4 FIX: Build trade history filters with date range and symbol."""
    f: Dict[str, Any] = {"user_id": user_id}
    if symbol:
        f["symbol"] = symbol.upper().strip()
    if from_date:
        f["from_date"] = from_date
    if to_date:
        f["to_date"] = to_date
    if status:
        f["status"] = status
    return f


# ── U-5 FIX: idempotency scoped to user_id ───────────────────────────────────
async def check_signal_idempotency(
    db: Any,
    signal_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """U-5 FIX: always scope idempotency check to user_id to prevent info leak."""
    try:
        return await db.select_one(
            "trades",
            {"signal_id": signal_id, "user_id": user_id},
        )
    except Exception:
        logger.debug("idempotency check failed", exc_info=True)
        return None


class TradeService:
    """Core trade service — create, close, list trades."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def create_trade(
        self,
        user_id: str,
        signal_id: str,
        symbol: str,
        direction: str,
        lot_size: float,
        entry_price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        # U-5: idempotency check
        existing = await check_signal_idempotency(self._db, signal_id, user_id)
        if existing:
            return existing

        trade: Dict[str, Any] = {
            "id":          str(uuid4()),
            "user_id":     user_id,
            "signal_id":   signal_id,
            "symbol":      symbol.upper().strip(),
            "direction":   direction,
            "lot_size":    lot_size,
            "entry_price": entry_price,
            "sl":          sl,
            "tp":          tp,
            "status":      "open",
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }
        await self._db.insert("trades", trade)
        return trade

    async def close_trade(
        self,
        trade_id: str,
        user_id: str,
        close_price: float,
        pnl_usd: float,
    ) -> Dict[str, Any]:
        update: Dict[str, Any] = {
            "status":     "closed",
            "close_price": close_price,
            "pnl_usd":     pnl_usd,
            "closed_at":   datetime.now(timezone.utc).isoformat(),
        }
        await self._db.update("trades", {"id": trade_id, "user_id": user_id}, update)
        # U-2: notify equity protection
        await notify_equity_protection(pnl_usd, 0.0, 0.0)
        return {"id": trade_id, **update}

    async def get_open_trades(
        self,
        user_id: str,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters = build_open_trades_filters(user_id, symbol)
        return await self._db.select_many("trades", filters)

    async def get_trade_history(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters = build_history_filters(user_id, symbol, from_date, to_date, status)
        return await self._db.select_many("trades", filters)

    async def get_statistics(self, user_id: str) -> Dict[str, Any]:
        trades = await self._db.select_many("trades", {"user_id": user_id})
        return compute_statistics(trades)


_trade_service_instance: Optional[TradeService] = None
_trade_service_lock = asyncio.Lock()


async def get_trade_service(db: Any) -> TradeService:
    global _trade_service_instance
    async with _trade_service_lock:
        if _trade_service_instance is None:
            _trade_service_instance = TradeService(db)
        return _trade_service_instance
