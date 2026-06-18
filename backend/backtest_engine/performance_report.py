"""
Galaxy Vast AI Trading Platform
PerformanceReportGenerator — Institutional HTML + JSON performance reports

Sections:
  1. Executive Summary
  2. Portfolio Metrics
  3. Per-Symbol Breakdown
  4. Trade Distribution Analysis
  5. Equity + Drawdown Charts (Chart.js data)
  6. Monte Carlo Summary
  7. Risk Metrics
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .multi_symbol_engine import MultiSymbolResult
from .monte_carlo_advanced import MonteCarloAdvancedResult


class PerformanceReportGenerator:
    """
    Generates branded Galaxy Vast performance reports in HTML and JSON.
    """

    BRAND = "Galaxy Vast AI Trading Platform"
    VERSION = "v3.0.0"

    def generate_json(
        self,
        backtest: MultiSymbolResult,
        monte_carlo: Optional[MonteCarloAdvancedResult] = None,
    ) -> dict:
        """Return structured JSON report."""
        report = {
            "brand":      self.BRAND,
            "version":    self.VERSION,
            "generated":  datetime.utcnow().isoformat(),
            "type":       "PERFORMANCE_REPORT",
            "backtest":   backtest.to_dict(),
        }
        if monte_carlo:
            report["monte_carlo"] = monte_carlo.to_dict()
        return report

    def generate_html(
        self,
        backtest: MultiSymbolResult,
        monte_carlo: Optional[MonteCarloAdvancedResult] = None,
        title: str = "Performance Report",
    ) -> str:
        """Return full standalone HTML performance report."""
        mc_section = ""
        if monte_carlo:
            mc = monte_carlo.to_dict()
            mc_section = f"""
            <div class="section">
                <h2>🎲 Monte Carlo Analysis ({mc['simulations_run']:,} simulations)</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Win Probability</div>
                        <div class="metric-value positive">{mc['probability_profit_pct']}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Ruin Probability</div>
                        <div class="metric-value {'negative' if mc['probability_ruin_pct'] > 5 else 'positive'}">{mc['probability_ruin_pct']}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Median Final Balance</div>
                        <div class="metric-value">${mc['median_final_balance']:,.2f}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">VaR 95%</div>
                        <div class="metric-value negative">{mc['var'].get('95pct', 0):.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Expected Max DD</div>
                        <div class="metric-value">{mc['drawdown']['expected_max_pct']:.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Half-Kelly Risk</div>
                        <div class="metric-value">{mc['optimal_risk_pct']:.2f}%</div>
                    </div>
                </div>
            </div>"""

        p = backtest.to_dict()["portfolio"]
        by_sym = backtest.to_dict()["by_symbol"]

        symbol_rows = ""
        for sym, sr in by_sym.items():
            color = "positive" if sr["net_profit"] > 0 else "negative"
            symbol_rows += f"""
            <tr>
                <td><strong>{sym}</strong></td>
                <td>{sr['total_trades']}</td>
                <td>{sr['win_rate']}%</td>
                <td class="{color}">${sr['net_profit']:,.2f}</td>
                <td>{sr['profit_factor']}</td>
                <td>{sr['max_drawdown']}%</td>
            </tr>"""

        equity_data = json.dumps([e["equity"] for e in backtest.equity_curve[:200]])
        dd_data     = json.dumps([round(e["drawdown"], 3) for e in backtest.drawdown_curve[:200]])
        labels      = json.dumps([e["time"][:10] for e in backtest.equity_curve[:200]])

        profit_color = "positive" if p["net_profit"] > 0 else "negative"
        sharpe_color = "positive" if p["sharpe_ratio"] >= 1 else ("neutral" if p["sharpe_ratio"] >= 0.5 else "negative")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Galaxy Vast — {title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0f1e; color: #e2e8f0; }}
        .header {{ background: linear-gradient(135deg, #1a1f3e 0%, #0d1530 100%);
                   border-bottom: 2px solid #3b82f6; padding: 24px 40px;
                   display: flex; justify-content: space-between; align-items: center; }}
        .brand {{ font-size: 22px; font-weight: 700; color: #60a5fa; }}
        .brand span {{ color: #f8fafc; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
        .badge {{ background: #1e3a5f; color: #60a5fa; border: 1px solid #3b82f6;
                  border-radius: 20px; padding: 4px 14px; font-size: 12px; font-weight: 600; }}
        .content {{ max-width: 1400px; margin: 0 auto; padding: 32px 40px; }}
        .section {{ margin-bottom: 40px; }}
        h2 {{ font-size: 18px; font-weight: 600; color: #f1f5f9;
              border-left: 3px solid #3b82f6; padding-left: 12px; margin-bottom: 20px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
        .metric-card {{ background: #111827; border: 1px solid #1f2937;
                        border-radius: 12px; padding: 20px; text-align: center;
                        transition: border-color 0.2s; }}
        .metric-card:hover {{ border-color: #3b82f6; }}
        .metric-label {{ font-size: 12px; color: #6b7280; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .metric-value {{ font-size: 24px; font-weight: 700; }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}
        .neutral  {{ color: #f59e0b; }}
        .chart-container {{ background: #111827; border: 1px solid #1f2937;
                            border-radius: 12px; padding: 24px; margin-bottom: 24px; }}
        canvas {{ max-height: 300px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #1f2937; color: #9ca3af; font-size: 12px;
              text-transform: uppercase; padding: 12px 16px; text-align: left; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #1f2937; font-size: 14px; }}
        tr:hover td {{ background: #1a2233; }}
        .footer {{ text-align: center; padding: 24px; color: #4b5563; font-size: 12px;
                   border-top: 1px solid #1f2937; }}
        .tag {{ display: inline-block; background: #1e3a5f; color: #60a5fa;
                border-radius: 4px; padding: 2px 8px; font-size: 11px; margin: 2px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="brand">🌌 Galaxy <span>Vast</span></div>
            <div class="subtitle">Institutional AI Trading Platform — {self.VERSION}</div>
        </div>
        <div>
            <span class="badge">📊 {title}</span>
            <div style="font-size:11px; color:#6b7280; margin-top:6px;">
                Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
            </div>
        </div>
    </div>

    <div class="content">

        <!-- Executive Summary -->
        <div class="section">
            <h2>📈 Executive Summary</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Net Profit</div>
                    <div class="metric-value {profit_color}">${p['net_profit']:,.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Net Profit %</div>
                    <div class="metric-value {profit_color}">{p['net_profit_pct']:+.2f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value {'positive' if p['win_rate'] >= 50 else 'neutral'}">{p['win_rate']:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">{p['total_trades']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Profit Factor</div>
                    <div class="metric-value {'positive' if p['profit_factor'] >= 1.5 else 'neutral'}">{p['profit_factor']:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Max Drawdown</div>
                    <div class="metric-value {'positive' if p['max_drawdown_pct'] < 10 else 'negative'}">{p['max_drawdown_pct']:.2f}%</div>
                </div>
            </div>
        </div>

        <!-- Risk-Adjusted Ratios -->
        <div class="section">
            <h2>📐 Risk-Adjusted Ratios</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Sharpe Ratio</div>
                    <div class="metric-value {sharpe_color}">{p['sharpe_ratio']:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Sortino Ratio</div>
                    <div class="metric-value {'positive' if p['sortino_ratio'] >= 1 else 'neutral'}">{p['sortino_ratio']:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Calmar Ratio</div>
                    <div class="metric-value {'positive' if p['calmar_ratio'] >= 1 else 'neutral'}">{p['calmar_ratio']:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Recovery Factor</div>
                    <div class="metric-value {'positive' if p['recovery_factor'] >= 2 else 'neutral'}">{p['recovery_factor']:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Expectancy</div>
                    <div class="metric-value {'positive' if p['expectancy'] > 0 else 'negative'}">${p['expectancy']:,.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Duration</div>
                    <div class="metric-value neutral">{p['duration_days']}d</div>
                </div>
            </div>
        </div>

        <!-- Equity Curve -->
        <div class="section">
            <h2>📉 Equity & Drawdown Curves</h2>
            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="drawdownChart"></canvas>
            </div>
        </div>

        <!-- Per-Symbol Breakdown -->
        <div class="section">
            <h2>🎯 Per-Symbol Breakdown</h2>
            <div class="chart-container">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th><th>Trades</th><th>Win Rate</th>
                            <th>Net Profit</th><th>Profit Factor</th><th>Max DD</th>
                        </tr>
                    </thead>
                    <tbody>{symbol_rows}</tbody>
                </table>
            </div>
        </div>

        <!-- Streaks -->
        <div class="section">
            <h2>🔢 Trade Statistics</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Max Consec. Wins</div>
                    <div class="metric-value positive">{p['max_consecutive_wins']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Max Consec. Losses</div>
                    <div class="metric-value negative">{p['max_consecutive_losses']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Drawdown</div>
                    <div class="metric-value">{p['avg_drawdown_pct']:.2f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Final Balance</div>
                    <div class="metric-value">${p['final_balance']:,.2f}</div>
                </div>
            </div>
        </div>

        {mc_section}

    </div>

    <div class="footer">
        <strong>Galaxy Vast AI Trading Platform</strong> — {self.VERSION} |
        Institutional Intelligence System |
        Report generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
    </div>

    <script>
    const labels = {labels};
    const equityData = {equity_data};
    const ddData = {dd_data};

    new Chart(document.getElementById('equityChart'), {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [{{
                label: 'Portfolio Equity ($)',
                data: equityData,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59,130,246,0.08)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
            scales: {{
                x: {{ ticks: {{ color: '#6b7280', maxTicksLimit: 10 }}, grid: {{ color: '#1f2937' }} }},
                y: {{ ticks: {{ color: '#6b7280' }}, grid: {{ color: '#1f2937' }} }}
            }}
        }}
    }});

    new Chart(document.getElementById('drawdownChart'), {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [{{
                label: 'Drawdown (%)',
                data: ddData.map(v => -v),
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239,68,68,0.08)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
            scales: {{
                x: {{ ticks: {{ color: '#6b7280', maxTicksLimit: 10 }}, grid: {{ color: '#1f2937' }} }},
                y: {{ ticks: {{ color: '#6b7280' }}, grid: {{ color: '#1f2937' }} }}
            }}
        }}
    }});
    </script>
</body>
</html>