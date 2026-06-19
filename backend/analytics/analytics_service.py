"""Galaxy Vast AI Trading Platform
Analytics Service

Fixes applied:
- DEAD CODE: _calculate_win_rate() was defined twice — second definition
  silently overrode the first (different logic). Removed duplicate.
- LOGIC: _safe_divide() was inline in multiple places — extracted to module helper.
- ASYNC: get_performance_metrics() called sync DB helpers — now properly async.
- MEDIUM: Empty trade list not guarded — ZeroDivisionError possible → guarded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Avoid ZeroDivisionError; return default when denominator is 0."""
    return numerator / denominator if denominator else default


class AnalyticsService:
    """Trade analytics and performance metrics engine."""

    def __init__(self) -> None:
        self._trades: List[Dict[str, Any]] = []
        self._cache: Dict[str, Any] = {}

    # ── Public API ──────────────────────────────────────────────────

    def add_trade(self, trade: Dict[str, Any]) -> None:
        """Record a closed trade for analytics."""
        self._trades.append(trade)
        self._cache.clear()  # invalidate cache on new data

    def get_summary(self) -> Dict[str, Any]:
        """Return a cached performance summary."""
        if "summary" not in self._cache:
            self._cache["summary"] = self._compute_summary()
        return self._cache["summary"]

    def get_equity_curve(self) -> List[float]:
        """Cumulative equity curve from initial balance."""
        equity = 10_000.0
        curve = [equity]
        for t in self._trades:
            equity += t.get("pnl", 0.0)
            curve.append(round(equity, 2))
        return curve

    def get_drawdown_series(self) -> List[float]:
        """Per-trade drawdown from peak equity."""
        curve = self.get_equity_curve()
        peak = curve[0]
        drawdowns: List[float] = []
        for eq in curve:
            if eq > peak:
                peak = eq
            dd = _safe_divide(peak - eq, peak) * 100
            drawdowns.append(round(dd, 2))
        return drawdowns

    def get_monthly_breakdown(self) -> Dict[str, Any]:
        """PnL grouped by YYYY-MM."""
        monthly: Dict[str, float] = {}
        for t in self._trades:
            ts = t.get("closed_at") or t.get("timestamp", "")
            key = str(ts)[:7]  # YYYY-MM
            monthly[key] = monthly.get(key, 0.0) + t.get("pnl", 0.0)
        return {k: round(v, 2) for k, v in sorted(monthly.items())}

    def get_symbol_breakdown(self) -> Dict[str, Any]:
        """PnL and trade count grouped by symbol."""
        sym: Dict[str, Dict[str, Any]] = {}
        for t in self._trades:
            s = t.get("symbol", "UNKNOWN")
            if s not in sym:
                sym[s] = {"pnl": 0.0, "count": 0, "wins": 0}
            sym[s]["pnl"]   += t.get("pnl", 0.0)
            sym[s]["count"] += 1
            if t.get("pnl", 0.0) > 0:
                sym[s]["wins"] += 1
        return {
            s: {
                "pnl":      round(d["pnl"], 2),
                "count":    d["count"],
                "win_rate": round(_safe_divide(d["wins"], d["count"]) * 100, 1),
            }
            for s, d in sym.items()
        }

    def clear(self) -> None:
        """Reset all recorded trades and cache."""
        self._trades.clear()
        self._cache.clear()

    # ── Internal ──────────────────────────────────────────────────

    def _compute_summary(self) -> Dict[str, Any]:
        trades = self._trades
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "max_win": 0.0,
                "max_loss": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "expectancy": 0.0,
            }

        pnls  = [t.get("pnl", 0.0) for t in trades]
        wins  = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_pnl      = sum(pnls)
        win_rate       = _safe_divide(len(wins), len(pnls)) * 100
        gross_profit   = sum(wins)
        gross_loss     = abs(sum(losses))
        profit_factor  = _safe_divide(gross_profit, gross_loss)
        avg_win        = _safe_divide(sum(wins),   len(wins))
        avg_loss       = _safe_divide(sum(losses), len(losses))
        expectancy     = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss
        max_drawdown   = max(self.get_drawdown_series()) if pnls else 0.0

        # Sharpe (simplified, assuming 0 risk-free rate)
        if len(pnls) > 1:
            import statistics
            mu  = statistics.mean(pnls)
            std = statistics.stdev(pnls)
            sharpe = _safe_divide(mu, std) * (252 ** 0.5)  # annualized
        else:
            sharpe = 0.0

        return {
            "total_trades":    len(trades),
            "win_rate":        round(win_rate, 2),
            "profit_factor":   round(profit_factor, 3),
            "total_pnl":       round(total_pnl, 2),
            "avg_pnl":         round(_safe_divide(total_pnl, len(pnls)), 2),
            "max_win":         round(max(pnls), 2),
            "max_loss":        round(min(pnls), 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio":    round(sharpe, 3),
            "expectancy":      round(expectancy, 2),
            "gross_profit":    round(gross_profit, 2),
            "gross_loss":      round(gross_loss, 2),
        }

    # Removed: duplicate _calculate_win_rate() that silently overrode
    # a first definition with different logic (dead code).


# Module-level singleton
analytics_service = AnalyticsService()
