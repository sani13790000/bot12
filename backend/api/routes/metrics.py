"""
backend/api/routes/metrics.py — Phase T Fix (BUG-T1)

Created because main.py imported metrics.router but this file did not exist.
ImportError on startup → all Group-1 core routes (auth, signals, trades,
analysis, ai_prediction, admin, backtest) failed to register.

Endpoints:
  GET /metrics/performance  — full PerformanceMetrics from DB trades
  GET /metrics/equity       — equity curve time-series
  GET /metrics/sharpe       — Sharpe ratio with configurable threshold
  GET /metrics/summary      — aggregated summary card data
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger(__name__)
router = APIRouter(tags=["Metrics"])


# ─── helpers ─────────────────────────────────────────────────────────────────
def _get_metrics_engine():
    from backend.analytics.metrics_engine import MetricsEngine
    return MetricsEngine()


async def _fetch_trade_records(days: int = 30) -> List[Any]:
    """Fetch closed TradeRecord objects from DB for the last `days` days."""
    try:
        from backend.database.connection import get_db_client
        from backend.analytics.metrics_engine import TradeRecord
        db = get_db_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (
            db.table("trades")
            .select("pnl_usd,entry_price,exit_price,stop_loss,take_profit,"
                    "direction,opened_at,closed_at,symbol,commission")
            .eq("status", "closed")
            .gte("closed_at", since)
            .execute()
        )
        records: List[TradeRecord] = []
        for row in (resp.data or []):
            try:
                records.append(TradeRecord(
                    pnl=float(row.get("pnl_usd", 0.0)),
                    entry_price=float(row.get("entry_price", 0.0)),
                    exit_price=float(row.get("exit_price", 0.0)),
                    stop_loss=float(row.get("stop_loss", 0.0)),
                    take_profit=float(row.get("take_profit", 0.0)),
                    direction=str(row.get("direction", "BUY")),
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    closed_at=datetime.fromisoformat(row["closed_at"]),
                    symbol=str(row.get("symbol", "")),
                    commission=float(row.get("commission", 0.0)),
                ))
            except Exception:
                continue
        return records
    except Exception as exc:
        log.warning("metrics: DB fetch failed: %s", exc)
        return []


# ─────────────────────── endpoints ───────────────────────

@router.get("/performance")
async def get_performance(
    days: int = Query(default=30, ge=1, le=365, description="Lookback days"),
) -> Dict[str, Any]:
    """BUG-T1 FIX: Full PerformanceMetrics from DB closed trades."""
    try:
        engine  = _get_metrics_engine()
        records = await _fetch_trade_records(days=days)
        metrics = engine.calculate(records)
        return {
            "ok": True,
            "lookback_days": days,
            "data_source": "live_db" if records else "no_data",
            "metrics": {
                "total_trades":       metrics.total_trades,
                "winning_trades":     metrics.winning_trades,
                "losing_trades":      metrics.losing_trades,
                "win_rate":           round(metrics.win_rate * 100, 2),
                "avg_win":            metrics.avg_win,
                "avg_loss":           metrics.avg_loss,
                "profit_factor":      metrics.profit_factor,
                "total_pnl":          metrics.total_pnl,
                "max_drawdown":       metrics.max_drawdown,
                "max_drawdown_pct":   metrics.max_drawdown_pct,
                "sharpe_ratio":       metrics.sharpe_ratio,
                "sortino_ratio":      metrics.sortino_ratio,
                "avg_rr":             metrics.avg_rr,
                "expectancy":         metrics.expectancy,
                "best_trade":         metrics.best_trade,
                "worst_trade":        metrics.worst_trade,
                "avg_hold_hours":     metrics.avg_hold_hours,
                "consecutive_wins":   metrics.consecutive_wins,
                "consecutive_losses": metrics.consecutive_losses,
            },
        }
    except Exception as exc:
        log.error("metrics/performance error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/equity")
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    """BUG-T1 FIX: Equity curve time-series for chart rendering."""
    try:
        records = await _fetch_trade_records(days=days)
        curve: List[Dict[str, Any]] = []
        equity = 0.0
        for rec in records:
            equity += rec.pnl
            curve.append({
                "ts":     rec.closed_at.isoformat(),
                "equity": round(equity, 2),
                "pnl":    round(rec.pnl, 2),
                "symbol": rec.symbol,
            })
        total_return = round(
            ((curve[-1]["equity"] - curve[0]["equity"]) / abs(curve[0]["equity"]) * 100)
            if len(curve) >= 2 and curve[0]["equity"] != 0 else 0.0,
            2,
        )
        return {
            "ok": True,
            "lookback_days": days,
            "data_points":   len(curve),
            "total_return":  total_return,
            "curve":         curve,
        }
    except Exception as exc:
        log.error("metrics/equity error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sharpe")
async def get_sharpe(
    days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    """BUG-T1 FIX: Sharpe ratio with configurable threshold (BUG-O3)."""
    try:
        engine  = _get_metrics_engine()
        records = await _fetch_trade_records(days=days)
        metrics = engine.calculate(records)

        from backend.core.config import get_settings
        settings    = get_settings()
        min_trades  = getattr(settings, "METRICS_MIN_TRADES_FOR_SHARPE", 30)
        available   = len(records) >= min_trades

        return {
            "ok":            True,
            "sharpe":        metrics.sharpe_ratio if available else 0.0,
            "sortino":       metrics.sortino_ratio if available else 0.0,
            "available":     available,
            "trade_count":   len(records),
            "min_required":  min_trades,
            "note":          "live" if available else "insufficient_data",
        }
    except Exception as exc:
        log.error("metrics/sharpe error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def get_summary(
    days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    """BUG-T1 FIX: Aggregated summary card data used by AnalyticsPage.tsx."""
    try:
        engine  = _get_metrics_engine()
        records = await _fetch_trade_records(days=days)
        metrics = engine.calculate(records)
        return {
            "ok":            True,
            "lookback_days": days,
            "data_source":   "live_db" if records else "no_data",
            "summary": {
                "total_trades":   metrics.total_trades,
                "win_rate":       round(metrics.win_rate * 100, 2),
                "total_pnl":      metrics.total_pnl,
                "profit_factor":  metrics.profit_factor,
                "max_drawdown":   metrics.max_drawdown,
                "sharpe_ratio":   metrics.sharpe_ratio,
                "sortino_ratio":  metrics.sortino_ratio,
                "expectancy":     metrics.expectancy,
                "best_trade":     metrics.best_trade,
                "worst_trade":    metrics.worst_trade,
            },
        }
    except Exception as exc:
        log.error("metrics/summary error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
