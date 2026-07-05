"""backend/analytics/metrics_engine.py — Phase O fix

BUG-O3: get_sharpe_ratio() returns 0.0 when < 30 trades — always on first deploy
  - METRICS_MIN_TRADES_FOR_SHARPE now from settings (configurable via env var)
  - Response includes 'min_required' so dashboard can show informative message
  - calculate_from_db() also uses configurable threshold
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _get_min_trades() -> int:
    """Read configurable threshold from settings (BUG-O3 fix)."""
    try:
        from backend.core.config import settings
        return settings.METRICS_MIN_TRADES_FOR_SHARPE
    except Exception:
        return 30


@dataclass
class TradeRecord:
    pnl:          float
    entry_price:  float
    exit_price:   float
    stop_loss:    float
    take_profit:  float
    direction:    str
    opened_at:    datetime
    closed_at:    datetime
    symbol:       str = ""
    commission:   float = 0.0


@dataclass
class PerformanceMetrics:
    total_trades:      int   = 0
    winning_trades:    int   = 0
    losing_trades:     int   = 0
    win_rate:          float = 0.0
    avg_win:           float = 0.0
    avg_loss:          float = 0.0
    profit_factor:     float = 0.0
    total_pnl:         float = 0.0
    max_drawdown:      float = 0.0
    max_drawdown_pct:  float = 0.0
    sharpe_ratio:      float = 0.0
    sortino_ratio:     float = 0.0
    avg_rr:            float = 0.0
    expectancy:        float = 0.0
    best_trade:        float = 0.0
    worst_trade:       float = 0.0
    avg_hold_hours:    float = 0.0
    consecutive_wins:  int   = 0
    consecutive_losses:int   = 0


class MetricsEngine:
    """Trade performance metrics calculator."""

    def calculate(self, trades: List[TradeRecord]) -> PerformanceMetrics:
        """Calculate performance metrics from a list of TradeRecord."""
        m = PerformanceMetrics()
        if not trades:
            return m

        m.total_trades = len(trades)
        pnls = [t.pnl for t in trades]
        m.total_pnl = round(sum(pnls), 4)

        wins  = [p for p in pnls if p > 0]
        loses = [p for p in pnls if p < 0]
        m.winning_trades = len(wins)
        m.losing_trades  = len(loses)
        m.win_rate       = round(m.winning_trades / m.total_trades, 4)

        m.avg_win  = round(sum(wins)  / len(wins),  4) if wins  else 0.0
        m.avg_loss = round(sum(loses) / len(loses), 4) if loses else 0.0

        gross_profit = sum(wins)
        gross_loss   = abs(sum(loses))
        m.profit_factor = round(gross_profit / gross_loss, 4) if gross_loss else float("inf")

        m.best_trade  = round(max(pnls), 4)
        m.worst_trade = round(min(pnls), 4)

        # Drawdown
        equity = 0.0; peak = 0.0; max_dd = 0.0
        for p in pnls:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = round(max_dd, 4)
        m.max_drawdown_pct = round((max_dd / peak * 100) if peak > 0 else 0.0, 4)

        # Sharpe / Sortino (annualised, daily returns proxy)
        min_trades = _get_min_trades()  # BUG-O3 fix
        if len(pnls) >= min_trades:
            mean_r = sum(pnls) / len(pnls)
            var    = sum((p - mean_r) ** 2 for p in pnls) / len(pnls)
            std_r  = math.sqrt(var)
            m.sharpe_ratio = round((mean_r / std_r) * math.sqrt(252) if std_r else 0.0, 4)
            neg_dev = [p - mean_r for p in pnls if p < mean_r]
            down_var = sum(d ** 2 for d in neg_dev) / len(pnls) if neg_dev else 0.0
            down_std = math.sqrt(down_var)
            m.sortino_ratio = round((mean_r / down_std) * math.sqrt(252) if down_std else 0.0, 4)
        else:
            log.debug(
                "MetricsEngine: %d trades < min_required=%d — Sharpe/Sortino set to 0.0",
                len(pnls), min_trades
            )

        # Expectancy
        m.expectancy = round(
            (m.win_rate * m.avg_win) + ((1 - m.win_rate) * m.avg_loss), 4
        )

        # Avg hold time
        hold_hours = [
            (t.closed_at - t.opened_at).total_seconds() / 3600
            for t in trades
            if t.closed_at > t.opened_at
        ]
        m.avg_hold_hours = round(sum(hold_hours) / len(hold_hours), 2) if hold_hours else 0.0

        # Avg R:R
        rr_list = []
        for t in trades:
            risk   = abs(t.entry_price - t.stop_loss)
            reward = abs(t.take_profit - t.entry_price)
            if risk > 0:
                rr_list.append(reward / risk)
        m.avg_rr = round(sum(rr_list) / len(rr_list), 4) if rr_list else 0.0

        # Consecutive wins/losses
        max_cw = cw = 0; max_cl = cl = 0
        for p in pnls:
            if p > 0:
                cw += 1; cl = 0
                if cw > max_cw: max_cw = cw
            elif p < 0:
                cl += 1; cw = 0
                if cl > max_cl: max_cl = cl
        m.consecutive_wins   = max_cw
        m.consecutive_losses = max_cl

        return m

    async def get_sharpe_ratio(self) -> Dict[str, Any]:
        """BUG-O3 fix: min_required from settings, informative response."""
        min_required = _get_min_trades()
        try:
            db_metrics = await self.calculate_from_db(days=30)
            trade_count = db_metrics.get("total_trades", 0)
            if trade_count < min_required:
                return {
                    "sharpe":       0.0,
                    "note":         "insufficient_data",
                    "min_required": min_required,
                    "current":      trade_count,
                }
            return {
                "sharpe":       db_metrics.get("sharpe_ratio", 0.0),
                "note":         "ok",
                "min_required": min_required,
                "current":      trade_count,
            }
        except Exception as e:
            log.debug("get_sharpe_ratio: %s", e)
            return {"sharpe": 0.0, "note": "error", "min_required": min_required, "current": 0}

    async def calculate_from_db(self, days: int = 30) -> Dict[str, Any]:
        """Fetch recent closed trades from DB and calculate metrics."""
        min_required = _get_min_trades()  # BUG-O3 fix
        try:
            from backend.database.connection import get_db_client
            db = await get_db_client()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            import asyncio
            r = await asyncio.wait_for(
                asyncio.to_thread(lambda: db.table("trades")
                    .select("pnl,entry_price,exit_price,stop_loss,take_profit,direction,opened_at,closed_at,symbol,commission")
                    .eq("status", "closed")
                    .gte("closed_at", since)
                    .execute()),
                timeout=10.0)
            rows = r.data or []
            trades: List[TradeRecord] = []
            for row in rows:
                try:
                    trades.append(TradeRecord(
                        pnl=float(row.get("pnl", 0)),
                        entry_price=float(row.get("entry_price", 0)),
                        exit_price=float(row.get("exit_price", 0)),
                        stop_loss=float(row.get("stop_loss", 0)),
                        take_profit=float(row.get("take_profit", 0)),
                        direction=row.get("direction", "BUY"),
                        opened_at=datetime.fromisoformat(row["opened_at"]) if row.get("opened_at") else datetime.now(timezone.utc),
                        closed_at=datetime.fromisoformat(row["closed_at"]) if row.get("closed_at") else datetime.now(timezone.utc),
                        symbol=row.get("symbol", ""),
                        commission=float(row.get("commission", 0)),
                    ))
                except Exception:
                    continue
            perf = self.calculate(trades)
            result = perf.__dict__.copy()
            result["total_trades"] = len(trades)
            result["min_trades_for_sharpe"] = min_required  # BUG-O3: expose to dashboard
            result["sharpe_available"] = len(trades) >= min_required
            return result
        except Exception as e:
            log.debug("calculate_from_db: %s", e)
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "min_trades_for_sharpe": min_required,
                "sharpe_available": False,
            }

    async def get_agent_performance(self) -> Dict[str, Any]:
        """Get agent voting performance from AgentPerformanceTracker."""
        try:
            from backend.analytics.agent_performance_tracker import agent_tracker
            return await agent_tracker.get_summary()
        except Exception as e:
            log.debug("get_agent_performance: %s", e)
            return {"agents": [], "total_votes": 0, "consensus_rate": 0.0}


# Module-level singleton
metrics_engine = MetricsEngine()
