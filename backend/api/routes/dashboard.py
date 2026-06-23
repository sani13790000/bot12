from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from ...core.deps import get_current_user
from ...core.logger import get_logger
from ...database import db
from ...services.trade_service import trade_service
from ...services.signal_service import signal_service
from ...services.license_service import license_service

# Phase R Fixes: R-1..R-10
logger = get_logger("api.dashboard")
router = APIRouter()

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)  # R-1: was utcnow()

def _today_iso() -> str:
    return _now_utc().date().isoformat()

def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val or default)
    except (TypeError, ValueError):
        return default

@router.get("/summary")
async def get_dashboard_summary(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """R-2: single DB call. R-3: filter pushed to DB. R-5: safe defaults. R-7: safe license."""
    user_id = user.get("sub") or user.get("id")
    today = _today_iso()
    try:
        today_trades: List[dict] = await db.select_many("trades", filters={"user_id": user_id, "date": today}, limit=200)
    except Exception:
        today_trades = []
    try:
        open_positions: List[dict] = await trade_service.get_open_positions(user_id)
    except Exception:
        open_positions = []
    try:
        active_signals: List[dict] = await signal_service.get_active_signals(user_id)
    except Exception:
        active_signals = []
    try:
        monthly_stats: dict = await trade_service.get_trade_stats(user_id, days=30)
    except Exception:
        monthly_stats = {}
    license_info: dict = {}
    try:
        raw_lic = await license_service.get_user_license(user_id)
        license_info = raw_lic or {}
    except Exception:
        pass
    today_profit = sum(_safe_float(t.get("profit_money")) for t in today_trades)
    today_wins   = sum(1 for t in today_trades if _safe_float(t.get("profit_money")) > 0)
    today_losses = sum(1 for t in today_trades if _safe_float(t.get("profit_money")) < 0)
    return {
        "today": {"trades": len(today_trades), "profit_usd": round(today_profit, 2),
                  "wins": today_wins, "losses": today_losses,
                  "win_rate": round(today_wins / len(today_trades) * 100, 1) if today_trades else 0.0},
        "open_positions": {"count": len(open_positions), "positions": open_positions[:10]},  # R-6
        "active_signals": {"count": len(active_signals), "signals": active_signals[:5]},
        "monthly": {"total_trades": _safe_float(monthly_stats.get("total_trades")),
                    "win_rate": _safe_float(monthly_stats.get("win_rate")),
                    "total_pnl_usd": _safe_float(monthly_stats.get("total_pnl_usd")),
                    "profit_factor": _safe_float(monthly_stats.get("profit_factor"))},
        "license": {"plan": license_info.get("plan", "unknown"),  # R-7
                    "is_active": bool(license_info.get("is_active", False)),
                    "expires_at": license_info.get("expires_at")},
        "generated_at": _now_utc().isoformat(),
    }

@router.get("/performance")  # R-8: was 404
async def get_performance(days: int = Query(default=30, ge=1, le=365), user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = user.get("sub") or user.get("id")
    try:
        stats = await trade_service.get_trade_stats(user_id, days=days)
    except Exception as exc:
        logger.error("get_performance: %s", exc)
        stats = {}
    return {"period_days": days, "total_trades": _safe_float(stats.get("total_trades")),
            "win_rate": _safe_float(stats.get("win_rate")), "profit_factor": _safe_float(stats.get("profit_factor")),
            "total_pnl_usd": _safe_float(stats.get("total_pnl_usd")), "max_drawdown_pct": _safe_float(stats.get("max_drawdown_pct")),
            "sharpe_ratio": _safe_float(stats.get("sharpe_ratio")), "generated_at": _now_utc().isoformat()}

@router.get("/equity")  # R-9: was 404
async def get_equity_curve(days: int = Query(default=30, ge=1, le=365), user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = user.get("sub") or user.get("id")
    try:
        trades = await db.select_many("trades", filters={"user_id": user_id}, order_by="closed_at", limit=1000)
    except Exception:
        trades = []
    equity = 0.0
    curve: List[dict] = []
    for t in trades:
        if not t.get("closed_at"):
            continue
        equity += _safe_float(t.get("profit_money"))
        curve.append({"ts": t["closed_at"], "equity": round(equity, 2), "symbol": t.get("symbol")})
    return {"period_days": days, "data_points": len(curve), "curve": curve, "net_pnl": round(equity, 2), "generated_at": _now_utc().isoformat()}

@router.get("/history")  # R-10: pagination cap=200
async def get_trade_history(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
                             symbol: Optional[str] = Query(None), user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = user.get("sub") or user.get("id")
    filters: dict = {"user_id": user_id}
    if symbol:
        filters["symbol"] = symbol.upper()
    offset = (page - 1) * page_size
    try:
        trades = await db.select_many("trades", filters=filters, order_by="opened_at", limit=page_size, offset=offset)
    except Exception:
        trades = []
    return {"page": page, "page_size": page_size, "count": len(trades), "trades": trades}
