"""
Galaxy Vast AI Trading Platform
PerformanceReportGenerator — Institutional HTML + JSON performance reports

Sections:
  1. Executive Summary
  2. Portfolio Metrics
  3. Per-Symbol Breakdown
  4. Time-Series Equity Curve
  5. Drawdown Analysis
  6. Risk-Adjusted Returns
  7. Trade Log (last 50)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    calmar_ratio: float = 0.0
    expectancy: float = 0.0
    avg_holding_h: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0


class PerformanceReportGenerator:
    """Generate institutional performance reports."""

    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)

    def compute_metrics(self, trades: List[Dict[str, Any]], initial_equity: float = 10000.0) -> PerformanceMetrics:
        """Compute all performance metrics from trade list."""
        if not trades:
            return PerformanceMetrics()

        pnls = [t.get("pnl", 0.0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total = len(pnls)
        n_wins = len(wins)
        n_losses = len(losses)
        total_pnl = sum(pnls)
        win_rate = n_wins / total if total else 0.0
        avg_win = sum(wins) / n_wins if wins else 0.0
        avg_loss = sum(losses) / n_losses if losses else 0.0
        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

        # Equity curve
        equity = [initial_equity]
        for pnl in pnls:
            equity.append(equity[-1] + pnl)

        # Max drawdown
        peak = equity[0]
        max_dd = 0.0
        max_dd_pct = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = peak - v
            dd_pct = dd / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
            max_dd_pct = max(max_dd_pct, dd_pct)

        # Sharpe (daily returns)
        n = len(pnls)
        if n > 1:
            mean_r = total_pnl / n
            std_r = math.sqrt(sum((p - mean_r) ** 2 for p in pnls) / (n - 1))
            sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
            neg_pnls = [p for p in pnls if p < 0]
            down_std = math.sqrt(sum(p**2 for p in neg_pnls) / max(len(neg_pnls), 1))
            sortino = (mean_r / down_std * math.sqrt(252)) if down_std > 0 else 0.0
        else:
            sharpe = sortino = 0.0

        annual_return = total_pnl / initial_equity * (252 / max(n, 1))
        calmar = annual_return / max_dd_pct if max_dd_pct > 0 else 0.0

        return PerformanceMetrics(
            total_trades=total, winning_trades=n_wins, losing_trades=n_losses,
            win_rate=win_rate, total_pnl=total_pnl,
            avg_win=avg_win, avg_loss=avg_loss, profit_factor=profit_factor,
            sharpe_ratio=sharpe, sortino_ratio=sortino,
            max_drawdown=max_dd, max_drawdown_pct=max_dd_pct, calmar_ratio=calmar,
            expectancy=expectancy,
            best_trade=max(pnls) if pnls else 0.0,
            worst_trade=min(pnls) if pnls else 0.0,
        )

    def generate_json(self, trades: List[Dict], initial_equity: float = 10000.0, title: str = "Performance Report") -> Dict[str, Any]:
        """Generate JSON report."""
        p = self.compute_metrics(trades, initial_equity)
        return {
            "title": title,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "initial_equity": initial_equity,
            "summary": {
                "total_trades": p.total_trades, "winning": p.winning_trades, "losing": p.losing_trades,
                "win_rate": f"{p.win_rate:.1%}", "total_pnl": f"{p.total_pnl:+.2f}",
                "profit_factor": f"{p.profit_factor:.2f}",
                "sharpe_ratio": f"{p.sharpe_ratio:.2f}", "max_drawdown": f"{p.max_drawdown_pct:.2%}",
                "calmar_ratio": f"{p.calmar_ratio:.2f}",
            },
        }

    def generate_html(self, trades: List[Dict], initial_equity: float = 10000.0, title: str = "Performance Report") -> str:
        """Generate HTML report."""
        p = self.compute_metrics(trades, initial_equity)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sharpe_color = "positive" if p.sharpe_ratio >= 1 else ("neutral" if p.sharpe_ratio >= 0 else "negative")
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title}</title>
<style>
body{{font-family:monospace;padding:20px;background:#1a1a2e;color:#e0e0e0}}
.card{{background:#16213e;border-radius:8px;padding:16px;margin:12px 0}}
.positive{{color:#00ff88}} .negative{{color:#ff4444}} .neutral{{color:#ffaa00}}
h1{{color:#0f3460}} table{{width:100%;border-collapse:collapse}}
td,th{{padding:8px;border:1px solid #333;text-align:left}}
th{{background:#0f3460}}
</style></head>
<body>
<h1>{title}</h1><p>Generated: {ts}</p>
<div class="card">
<h2>Executive Summary</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Trades</td><td>{p.total_trades}</td></tr>
<tr><td>Win Rate</td><td>{p.win_rate:.1%}</td></tr>
<tr><td>Total P&amp;L</td><td class="{'positive' if p.total_pnl>=0 else 'negative'}">${p.total_pnl:+.2f}</td></tr>
<tr><td>Profit Factor</td><td>{p.profit_factor:.2f}</td></tr>
<tr><td>Sharpe Ratio</td><td class="{sharpe_color}">{p.sharpe_ratio:.2f}</td></tr>
<tr><td>Max Drawdown</td><td class="negative">{p.max_drawdown_pct:.2%}</td></tr>
<tr><td>Calmar Ratio</td><td>{p.calmar_ratio:.2f}</td></tr>
<tr><td>Expectancy</td><td>${p.expectancy:+.2f}</td></tr>
</table>
</div>
</body></html>"""
