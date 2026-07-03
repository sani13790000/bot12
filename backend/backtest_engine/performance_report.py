"""
Galaxy Vast AI Trading Platform
PerformanceReportGenerator -- Institutional HTML backtest report
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class PerformanceMetrics:
    total_trades:    int   = 0
    winning_trades:  int   = 0
    losing_trades:   int   = 0
    win_rate:        float = 0.0
    profit_factor:   float = 0.0
    total_pnl:       float = 0.0
    max_drawdown:    float = 0.0
    sharpe_ratio:    float = 0.0
    avg_trade:       float = 0.0
    best_trade:      float = 0.0
    worst_trade:     float = 0.0
    avg_hold_time:   float = 0.0


class PerformanceReportGenerator:
    """Generate institutional-grade HTML performance reports."""

    def __init__(self) -> None:
        self._generated_at = datetime.now(timezone.utc).isoformat()

    def generate(
        self,
        metrics: PerformanceMetrics,
        symbol: str = "ALL",
        period: str = "ALL",
        equity_curve: Optional[list[float]] = None,
    ) -> str:
        """Generate a full HTML performance report."""
        equity_data = equity_curve or []
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Performance Report - {symbol}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .metric {{ font-size: 1.2em; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Performance Report</h1>
    <p>Symbol: {symbol} | Period: {period} | Generated: {self._generated_at}</p>
    <h2>Key Metrics</h2>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Total Trades</td><td class="metric">{metrics.total_trades}</td></tr>
        <tr><td>Win Rate</td><td class="metric">{metrics.win_rate:.1%}</td></tr>
        <tr><td>Profit Factor</td><td class="metric">{metrics.profit_factor:.2f}</td></tr>
        <tr><td>Total PnL</td><td class="metric">${metrics.total_pnl:.2f}</td></tr>
        <tr><td>Max Drawdown</td><td class="metric">{metrics.max_drawdown:.1%}</td></tr>
        <tr><td>Sharpe Ratio</td><td class="metric">{metrics.sharpe_ratio:.2f}</td></tr>
        <tr><td>Avg Trade</td><td class="metric">${metrics.avg_trade:.2f}</td></tr>
        <tr><td>Best Trade</td><td class="metric">${metrics.best_trade:.2f}</td></tr>
        <tr><td>Worst Trade</td><td class="metric">${metrics.worst_trade:.2f}</td></tr>
    </table>
</body>
</html>"""

    def to_dict(self, metrics: PerformanceMetrics) -> dict:
        return {
            "total_trades":   metrics.total_trades,
            "win_rate":       round(metrics.win_rate, 4),
            "profit_factor":  round(metrics.profit_factor, 4),
            "total_pnl":      round(metrics.total_pnl, 2),
            "max_drawdown":   round(metrics.max_drawdown, 4),
            "sharpe_ratio":   round(metrics.sharpe_ratio, 4),
            "generated_at":   self._generated_at,
        }
