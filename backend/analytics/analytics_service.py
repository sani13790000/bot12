"""
backend/analytics/analytics_service.py
Galaxy Vast AI Trading Platform
────────────────────────────────────────────────────────────────────────────────
Analytics service: aggregates trade history and computes
performance statistics for the dashboard and Telegram reports.

BUG-Q2 FIX: get_analytics_summary() was returning static zero dict.
Now queries real DB data with cache TTL=60s.

Usage::

    from backend.analytics.analytics_service import analytics_service

    stats = await analytics_service.get_performance_stats(days=30)
    print(stats["win_rate"], stats["net_pnl"])
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Computes aggregated performance metrics from the trade history.

    All heavy queries are cached for *cache_ttl_s* seconds to avoid
    hammering the database on every dashboard refresh.
    """

    def __init__(self, cache_ttl_s: float = 60.0) -> None:
        self._cache_ttl  = cache_ttl_s
        self._cache:     Dict[str, Any] = {}
        self._cache_ts:  Dict[str, float] = {}

    # ── Public API ──────────────────────────────────────────────────────────── #

    async def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Return aggregated performance stats for the last *days* days.

        Returns
        -------
        dict with keys:
            total_trades, winning_trades, losing_trades,
            win_rate, net_pnl, gross_pnl,
            max_drawdown, avg_rr, best_trade, worst_trade
        """
        cache_key = f"perf:{days}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]

        trades = await self._fetch_closed_trades(days)
        stats  = self._compute_stats(trades)
        self._set_cache(cache_key, stats)
        return stats

    async def get_symbol_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Return per-symbol performance breakdown.

        Returns a list of dicts: [{symbol, trades, win_rate, net_pnl}, ...]
        sorted by net_pnl descending.
        """
        trades = await self._fetch_closed_trades(days)
        by_symbol: Dict[str, List[Dict]] = {}
        for t in trades:
            sym = t.get("symbol", "UNKNOWN")
            by_symbol.setdefault(sym, []).append(t)

        result = []
        for sym, sym_trades in by_symbol.items():
            stats = self._compute_stats(sym_trades)
            result.append({"symbol": sym, **stats})

        result.sort(key=lambda x: x["net_pnl"], reverse=True)
        return result

    async def get_analytics_summary(self) -> Dict[str, Any]:
        """
        BUG-Q2 FIX: was returning static zeros.
        Now queries real DB data for dashboard analytics tab.

        Returns compact summary dict for dashboard cards.
        Cache TTL = 60 seconds.
        """
        cache_key = "analytics_summary"
        if self._is_cached(cache_key):
            return self._cache[cache_key]

        try:
            # Fetch last 30 days performance
            stats = await self.get_performance_stats(days=30)

            # Fetch active signals count from DB
            active_signals = await self._count_active_signals()

            summary = {
                "total_trades":   stats.get("total_trades", 0),
                "win_rate":       round(stats.get("win_rate", 0.0), 4),
                "total_pnl":      round(stats.get("net_pnl", 0.0), 2),
                "avg_rr":         round(stats.get("avg_rr", 0.0), 3),
                "active_signals": active_signals,
                "max_drawdown":   round(stats.get("max_drawdown", 0.0), 4),
                "best_trade":     round(stats.get("best_trade", 0.0), 2),
                "worst_trade":    round(stats.get("worst_trade", 0.0), 2),
                "data_source":    "live_db",
                "period_days":    30,
                "as_of":          datetime.now(timezone.utc).isoformat(),
            }
            self._set_cache(cache_key, summary)
            return summary

        except Exception as exc:
            logger.warning("get_analytics_summary DB error: %s — returning zeros", exc)
            # Graceful fallback — never crash dashboard
            return {
                "total_trades":   0,
                "win_rate":       0.0,
                "total_pnl":      0.0,
                "avg_rr":         0.0,
                "active_signals": 0,
                "max_drawdown":   0.0,
                "best_trade":     0.0,
                "worst_trade":    0.0,
                "data_source":    "fallback_db_error",
                "period_days":    30,
                "as_of":          datetime.now(timezone.utc).isoformat(),
            }

    # ── Computation ──────────────────────────────────────────────────────────── #

    @staticmethod
    def _compute_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Derive key metrics from a list of closed trade records."""
        if not trades:
            return {
                "total_trades":   0,
                "winning_trades": 0,
                "losing_trades":  0,
                "win_rate":       0.0,
                "net_pnl":        0.0,
                "gross_pnl":      0.0,
                "max_drawdown":   0.0,
                "avg_rr":         0.0,
                "best_trade":     0.0,
                "worst_trade":    0.0,
            }

        pnls     = [float(t.get("pnl", 0.0)) for t in trades]
        rrs      = [float(t.get("risk_reward", 0.0)) for t in trades if t.get("risk_reward")]
        winners  = [p for p in pnls if p > 0]
        losers   = [p for p in pnls if p < 0]
        gross    = sum(winners)
        net      = sum(pnls)

        # Max drawdown: largest peak-to-trough drop in cumulative P&L
        cumulative = 0.0
        peak       = 0.0
        max_dd     = 0.0
        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        return {
            "total_trades":   len(trades),
            "winning_trades": len(winners),
            "losing_trades":  len(losers),
            "win_rate":       len(winners) / len(trades) if trades else 0.0,
            "net_pnl":        round(net, 2),
            "gross_pnl":      round(gross, 2),
            "max_drawdown":   round(max_dd, 4),
            "avg_rr":         round(sum(rrs) / len(rrs), 3) if rrs else 0.0,
            "best_trade":     round(max(pnls), 2) if pnls else 0.0,
            "worst_trade":    round(min(pnls), 2) if pnls else 0.0,
        }

    # ── DB helpers ───────────────────────────────────────────────────────────── #

    async def _fetch_closed_trades(
        self, days: int
    ) -> List[Dict[str, Any]]:
        """Fetch closed trades from Supabase for the last *days* days."""
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            result = (
                db.table("trades")
                .select("id,symbol,pnl,risk_reward,closed_at,direction")
                .eq("status", "CLOSED")
                .gte("closed_at", since)
                .order("closed_at", desc=False)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning("_fetch_closed_trades error: %s", exc)
            return []

    async def _count_active_signals(self) -> int:
        """Count active (pending) signals from DB."""
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            result = (
                db.table("signals")
                .select("id", count="exact")
                .eq("status", "ACTIVE")
                .execute()
            )
            return result.count or 0
        except Exception as exc:
            logger.warning("_count_active_signals error: %s", exc)
            return 0

    # ── Cache helpers ─────────────────────────────────────────────────────────── #

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return (time.monotonic() - self._cache_ts.get(key, 0)) < self._cache_ttl

    def _set_cache(self, key: str, value: Any) -> None:
        self._cache[key]    = value
        self._cache_ts[key] = time.monotonic()

    def invalidate_cache(self) -> None:
        """Force invalidate all cached results (e.g. after new trades)."""
        self._cache.clear()
        self._cache_ts.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────
analytics_service = AnalyticsService()
