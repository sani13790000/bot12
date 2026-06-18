"""
Galaxy Vast AI Trading Platform
Backtest Report Generator

Generates branded HTML + JSON performance and risk reports.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from .multi_symbol_engine import MultiSymbolResult
from .parameter_optimizer import OptimizationResult


class BacktestReportGenerator:
    """
    Generates professional branded reports for backtest results.
    Supports HTML (with inline charts) and JSON formats.
    """

    BRAND = "Galaxy Vast AI Trading Platform"
    BRAND_COLOR = "#6366f1"

    def generate_html(
        self,
        result: MultiSymbolResult,
        opt_result: Optional[OptimizationResult] = None,
        mc_result: Optional[Dict[str, Any]] = None,
        wf_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate full branded HTML performance + risk report."""
        data = result.to_dict()
        p = data["portfolio"]

        equity_labels = json.dumps([e["time"][:10] for e in data["equity_curve"]])
        equity_values = json.dumps([e["equity"] for e in data["equity_curve"]])
        dd_values     = json.dumps([round(e["drawdown_pct"] * 100, 2) for e in data["equity_curve"]])

        symbol_rows = "".join(
            f"<tr><td>{sym}</td><td>{v['total_trades']}</td>"
            f"<td>{v['win_rate']*100:.1f}%</td>"
            f"<td>{v['profit_factor']:.2f}</td>"
            f"<td>${v['net_pnl']:,.2f}</td>"
            f"<td>{v['max_drawdown_pct']*100:.2f}%</td>"
            f"<td>{v['sharpe_ratio']:.2f}</td></tr>"
            for sym, v in data["per_symbol"].items()
        )

        opt_section = ""
        if opt_result:
            od = opt_result.to_dict()
            badge = "🟢 ROBUST" if od["is_robust"] else "🔴 CAUTION"
            opt_section = f"""
            <div class="section">
              <h2>⚙️ Parameter Optimization</h2>
              <div class="metric-grid">
                <div class="metric-card"><div class="label">Status</div><div class="value">{badge}</div></div>
                <div class="metric-card"><div class="label">Robustness</div><div class="value">{od["robustness_score"]:.1f}/100</div></div>
                <div class="metric-card"><div class="label">Best Test Metric</div><div class="value">{od["best_test_metric"]:.3f}</div></div>
                <div class="metric-card"><div class="label">Iterations</div><div class="value">{od["total_iterations"]}</div></div>
              </div>
              <p style="color:#6366f1;font-weight:600">{od["recommendation"]}</p>
              <h3>Best Parameters:</h3>
              <pre style="background:#1e1e2e;padding:1rem;border-radius:8px;color:#a6e3a1">{json.dumps(od["best_params"], indent=2)}</pre>
            </div>"""

        mc_section = ""
        if mc_result:
            mc_section = f"""
            <div class="section">
              <h2>🎲 Monte Carlo Simulation</h2>
              <div class="metric-grid">
                <div class="metric-card"><div class="label">Prob Profit</div><div class="value">{mc_result.get("probability_profit", 0)*100:.1f}%</div></div>
                <div class="metric-card"><div class="label">VaR 95%</div><div class="value">{mc_result.get("var_95", 0)*100:.2f}%</div></div>
                <div class="metric-card"><div class="label">Worst DD</div><div class="value">{mc_result.get("worst_max_drawdown", 0)*100:.2f}%</div></div>
                <div class="metric-card"><div class="label">Simulations</div><div class="value">{mc_result.get("simulations", 1000)}</div></div>
              </div>
            </div>"""

        wf_section = ""
        if wf_result:
            wf_section = f"""
            <div class="section">
              <h2>🔄 Walk-Forward Analysis</h2>
              <div class="metric-grid">
                <div class="metric-card"><div class="label">Result</div><div class="value">{wf_result.get("recommendation", "N/A")}</div></div>
                <div class="metric-card"><div class="label">Consistency</div><div class="value">{wf_result.get("consistency_score", 0):.1f}/100</div></div>
                <div class="metric-card"><div class="label">Pass Rate</div><div class="value">{wf_result.get("pass_rate", 0)*100:.0f}%</div></div>
              </div>
            </div>"""

        generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{self.BRAND} — Backtest Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{{--brand:{self.BRAND_COLOR};--bg:#0f0f1a;--surface:#1a1a2e;--text:#e2e8f0;--green:#22c55e;--red:#ef4444;--yellow:#f59e0b}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}
  .header{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:2.5rem 2rem;border-bottom:2px solid var(--brand)}}
  .header h1{{font-size:2rem;font-weight:800;color:#fff}}
  .header h1 span{{color:var(--brand)}}
  .header p{{color:#94a3b8;margin-top:.5rem}}
  .container{{max-width:1200px;margin:0 auto;padding:2rem}}
  .section{{background:var(--surface);border:1px solid #2d2d4a;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem}}
  .section h2{{font-size:1.25rem;font-weight:700;margin-bottom:1rem;color:#c4b5fd}}
  .section h3{{font-size:1rem;font-weight:600;margin:1rem 0 .5rem;color:#94a3b8}}
  .metric-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:1rem;margin-bottom:1rem}}
  .metric-card{{background:#0f0f1a;border:1px solid #2d2d4a;border-radius:8px;padding:1rem;text-align:center}}
  .metric-card .label{{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em}}
  .metric-card .value{{font-size:1.5rem;font-weight:700;color:#fff;margin-top:.25rem}}
  .metric-card .value.green{{color:var(--green)}}
  .metric-card .value.red{{color:var(--red)}}
  .metric-card .value.yellow{{color:var(--yellow)}}
  .chart-wrap{{position:relative;height:280px;margin-top:1rem}}
  table{{width:100%;border-collapse:collapse;font-size:.875rem}}
  th{{background:#0f0f1a;color:#94a3b8;padding:.75rem 1rem;text-align:left;font-weight:600;text-transform:uppercase;font-size:.75rem}}
  td{{padding:.75rem 1rem;border-bottom:1px solid #2d2d4a}}
  tr:hover td{{background:#0f0f1a}}
  .badge{{display:inline-block;padding:.25rem .75rem;border-radius:999px;font-size:.75rem;font-weight:700}}
  .badge-green{{background:#052e16;color:var(--green);border:1px solid var(--green)}}
  .badge-red{{background:#450a0a;color:var(--red);border:1px solid var(--red)}}
  .badge-yellow{{background:#422006;color:var(--yellow);border:1px solid var(--yellow)}}
  .footer{{text-align:center;color:#475569;font-size:.75rem;padding:2rem;border-top:1px solid #2d2d4a;margin-top:2rem}}
  pre{{overflow-x:auto;font-size:.8rem}}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <h1>🌌 <span>Galaxy Vast</span> — Institutional Backtest Report</h1>
    <p>Multi-Symbol · Multi-Timeframe · Walk-Forward · Monte Carlo · Parameter Optimization</p>
    <p style="font-size:.85rem;margin-top:.5rem">Generated: {generated_at} &nbsp;|&nbsp; Period: {data["config"]["start_date"][:10]} → {data["config"]["end_date"][:10]} &nbsp;|&nbsp; Symbols: {", ".join(data["config"]["symbols"])}</p>
  </div>
</div>
<div class="container">

  <!-- Portfolio Summary -->
  <div class="section">
    <h2>📊 Portfolio Performance</h2>
    <div class="metric-grid">
      <div class="metric-card"><div class="label">Total Trades</div><div class="value">{p["total_trades"]}</div></div>
      <div class="metric-card"><div class="label">Win Rate</div><div class="value {'green' if p['win_rate'] >= 0.5 else 'red'}">{p["win_rate"]*100:.1f}%</div></div>
      <div class="metric-card"><div class="label">Net P&L</div><div class="value {'green' if p['net_pnl'] >= 0 else 'red'}">${p["net_pnl"]:,.2f}</div></div>
      <div class="metric-card"><div class="label">Profit Factor</div><div class="value {'green' if p['profit_factor'] >= 1.5 else 'yellow' if p['profit_factor'] >= 1 else 'red'}">{p["profit_factor"]:.2f}</div></div>
      <div class="metric-card"><div class="label">Sharpe Ratio</div><div class="value {'green' if p['sharpe_ratio'] >= 1.5 else 'yellow'}">{p["sharpe_ratio"]:.2f}</div></div>
      <div class="metric-card"><div class="label">Sortino Ratio</div><div class="value {'green' if p['sortino_ratio'] >= 2 else 'yellow'}">{p["sortino_ratio"]:.2f}</div></div>
      <div class="metric-card"><div class="label">Calmar Ratio</div><div class="value {'green' if p['calmar_ratio'] >= 2 else 'yellow'}">{p["calmar_ratio"]:.2f}</div></div>
      <div class="metric-card"><div class="label">Max Drawdown</div><div class="value {'red' if p['max_drawdown_pct'] >= 0.15 else 'yellow'}">{p["max_drawdown_pct"]*100:.2f}%</div></div>
      <div class="metric-card"><div class="label">Recovery Factor</div><div class="value">{p["recovery_factor"]:.2f}</div></div>
      <div class="metric-card"><div class="label">Expectancy</div><div class="value {'green' if p['expectancy'] >= 0 else 'red'}">${p["expectancy"]:,.2f}</div></div>
      <div class="metric-card"><div class="label">CAGR</div><div class="value {'green' if p['cagr'] >= 0.10 else 'yellow'}">{p["cagr"]*100:.1f}%</div></div>
      <div class="metric-card"><div class="label">Avg Duration</div><div class="value">{p["avg_trade_duration_minutes"]}m</div></div>
    </div>
  </div>

  <!-- Equity Curve -->
  <div class="section">
    <h2>📈 Equity Curve</h2>
    <div class="chart-wrap"><canvas id="equityChart"></canvas></div>
  </div>

  <!-- Drawdown -->
  <div class="section">
    <h2>📉 Drawdown Curve</h2>
    <div class="chart-wrap"><canvas id="ddChart"></canvas></div>
  </div>

  <!-- Per Symbol -->
  <div class="section">
    <h2>📋 Per-Symbol Performance</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Trades</th><th>Win Rate</th><th>PF</th><th>Net P&L</th><th>Max DD</th><th>Sharpe</th></tr></thead>
      <tbody>{symbol_rows}</tbody>
    </table>
  </div>

  {opt_section}
  {mc_section}
  {wf_section}

</div>
<div class="footer">
  <p>© {datetime.utcnow().year} {self.BRAND} · Institutional Research Report · Confidential</p>
  <p style="margin-top:.25rem">Past performance does not guarantee future results. This report is for research purposes only.</p>
</div>

<script>
const labels = {equity_labels};
const equity = {equity_values};
const dd     = {dd_values};
const opts = {{ responsive:true, maintainAspectRatio:false, plugins:{{ legend:{{ display:false }} }}, scales:{{ x:{{ ticks:{{ color:'#64748b', maxTicksLimit:10 }}, grid:{{ color:'#1e1e2e' }} }}, y:{{ ticks:{{ color:'#64748b' }}, grid:{{ color:'#1e1e2e' }} }} }} }};
new Chart('equityChart', {{ type:'line', data:{{ labels, datasets:[{{ data:equity, borderColor:'{self.BRAND_COLOR}', backgroundColor:'{self.BRAND_COLOR}22', fill:true, tension:.4, pointRadius:0 }}] }}, options:opts }});
new Chart('ddChart', {{ type:'line', data:{{ labels, datasets:[{{ data:dd, borderColor:'#ef4444', backgroundColor:'#ef444422', fill:true, tension:.4, pointRadius:0 }}] }}, options:{{ ...opts, scales:{{ x:opts.scales.x, y:{{ ...opts.scales.y, reverse:false }} }} }} }});
</script>
</body>
</html>"""
        return html

    def generate_json(
        self,
        result: MultiSymbolResult,
        opt_result: Optional[OptimizationResult] = None,
        mc_result: Optional[Dict[str, Any]] = None,
        wf_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate structured JSON report."""
        report = {
            "brand": self.BRAND,
            "generated_at": datetime.utcnow().isoformat(),
            "backtest": result.to_dict(),
        }
        if opt_result:
            report["optimization"] = opt_result.to_dict()
        if mc_result:
            report["monte_carlo"] = mc_result
        if wf_result:
            report["walk_forward"] = wf_result
        return report
