"""
Galaxy Vast AI Trading Platform
ReportGenerator — HTML + JSON performance reports
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .metrics_engine import AnalyticsResult


class ReportGenerator:
    """
    Generates professional analytics reports.
    Output formats: JSON dict, HTML string.
    """

    BRAND_NAME = "Galaxy Vast AI Trading Platform"

    def to_json(self, result: AnalyticsResult, pretty: bool = True) -> str:
        d = result.to_dict()
        d["generated_at"] = datetime.utcnow().isoformat()
        d["brand"] = self.BRAND_NAME
        return json.dumps(d, indent=2 if pretty else None, default=str)

    def to_html(self, result: AnalyticsResult, symbol: str = "ALL") -> str:
        d = result.to_dict()

        def badge(value: float, good_above: float, bad_below: float) -> str:
            if value >= good_above:
                color = "#00e676"   # green
            elif value < bad_below:
                color = "#ef5350"   # red
            else:
                color = "#ffca28"   # amber
            return f'<span style="color:{color};font-weight:700">{value}</span>'

        sharpe_badge  = badge(d["sharpe_ratio"],  1.5,  0.5)
        sortino_badge = badge(d["sortino_ratio"], 2.0,  0.8)
        calmar_badge  = badge(d["calmar_ratio"],  2.0,  0.5)
        pf_badge      = badge(d["profit_factor"], 1.5,  1.0)
        wr_badge      = badge(round(d["win_rate"] * 100, 1), 55, 45)
        dd_badge      = badge(
            round(d["max_drawdown_pct"] * 100, 2),
            0, 10   # drawdown: lower is better — invert logic
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{self.BRAND_NAME} — Analytics Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0a0e1a; color: #e0e6f0; font-family: 'Segoe UI', sans-serif; padding: 32px; }}
    h1   {{ font-size: 1.8rem; color: #7c8cf8; margin-bottom: 4px; }}
    h2   {{ font-size: 1.1rem; color: #a0aec0; margin: 24px 0 12px; }}
    .sub {{ font-size: 0.85rem; color: #718096; margin-bottom: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
    .card {{
        background: #131929; border: 1px solid #1e2d45;
        border-radius: 10px; padding: 16px;
    }}
    .card .label {{ font-size: 0.75rem; color: #718096; text-transform: uppercase; letter-spacing: .05em; }}
    .card .value {{ font-size: 1.4rem; font-weight: 700; margin-top: 6px; }}
    .section {{ margin-top: 32px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ background: #1a2540; color: #a0aec0; padding: 8px 12px; text-align: left; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #1e2d45; }}
    tr:hover td {{ background: #131929; }}
    .green {{ color: #00e676; }} .red {{ color: #ef5350; }} .amber {{ color: #ffca28; }}
    footer {{ margin-top: 40px; font-size: 0.75rem; color: #4a5568; }}
  </style>
</head>
<body>
  <h1>🌌 {self.BRAND_NAME}</h1>
  <div class="sub">Symbol: <strong>{symbol}</strong> &nbsp;|&nbsp;
       Period: {d.get("period_start","—")} → {d.get("period_end","—")} &nbsp;|&nbsp;
       Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
  </div>

  <h2>📊 Core Metrics</h2>
  <div class="grid">
    <div class="card"><div class="label">Sharpe Ratio</div>
      <div class="value">{sharpe_badge}</div></div>
    <div class="card"><div class="label">Sortino Ratio</div>
      <div class="value">{sortino_badge}</div></div>
    <div class="card"><div class="label">Calmar Ratio</div>
      <div class="value">{calmar_badge}</div></div>
    <div class="card"><div class="label">Profit Factor</div>
      <div class="value">{pf_badge}</div></div>
    <div class="card"><div class="label">Win Rate</div>
      <div class="value">{wr_badge}%</div></div>
    <div class="card"><div class="label">Recovery Factor</div>
      <div class="value">{round(d["recovery_factor"],2) if d["recovery_factor"] != float("inf") else "∞"}</div></div>
    <div class="card"><div class="label">Max Drawdown</div>
      <div class="value red">{round(d["max_drawdown_pct"]*100, 2)}%</div></div>
    <div class="card"><div class="label">Expectancy (R)</div>
      <div class="value">{d["expectancy_r"]}R</div></div>
    <div class="card"><div class="label">CAGR</div>
      <div class="value">{round(d["cagr"]*100, 2)}%</div></div>
    <div class="card"><div class="label">Net Profit</div>
      <div class="value {'green' if d['net_profit']>=0 else 'red'}">${d["net_profit"]}</div></div>
    <div class="card"><div class="label">Total Trades</div>
      <div class="value">{d["total_trades"]}</div></div>
    <div class="card"><div class="label">Avg Hold (min)</div>
      <div class="value">{d["avg_hold_minutes"]}</div></div>
  </div>

  <div class="section">
    <h2>💰 P&amp;L Summary</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Gross Profit</td><td class="green">${d["gross_profit"]}</td></tr>
      <tr><td>Gross Loss</td><td class="red">-${d["gross_loss"]}</td></tr>
      <tr><td>Net Profit</td>
          <td class="{'green' if d['net_profit']>=0 else 'red'}">${d["net_profit"]}</td></tr>
      <tr><td>Average Win</td><td class="green">${d["average_win"]}</td></tr>
      <tr><td>Average Loss</td><td class="red">${d["average_loss"]}</td></tr>
      <tr><td>Average RR</td><td>1:{d["average_rr"]}</td></tr>
      <tr><td>Expectancy</td><td>${d["expectancy"]}</td></tr>
    </table>
  </div>

  <div class="section">
    <h2>📈 Trade Statistics</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Winning Trades</td><td class="green">{d["winning_trades"]}</td></tr>
      <tr><td>Losing Trades</td><td class="red">{d["losing_trades"]}</td></tr>
      <tr><td>Break Even</td><td>{d["break_even_trades"]}</td></tr>
      <tr><td>Max Consecutive Wins</td><td class="green">{d["max_consecutive_wins"]}</td></tr>
      <tr><td>Max Consecutive Losses</td><td class="red">{d["max_consecutive_losses"]}</td></tr>
      <tr><td>Trading Days</td><td>{d["trading_days"]}</td></tr>
    </table>
  </div>

  <footer>Galaxy Vast AI Trading Platform — Institutional Analytics Engine</footer>
</body>
</html>"""
        return html

    def to_summary_dict(self, result: AnalyticsResult) -> dict:
        """Compact summary for dashboard cards."""
        return {
            "sharpe_ratio":          round(result.sharpe_ratio, 3),
            "sortino_ratio":         round(result.sortino_ratio, 3),
            "calmar_ratio":          round(result.calmar_ratio, 3),
            "profit_factor":         round(result.profit_factor, 3),
            "recovery_factor":       round(result.recovery_factor, 3),
            "win_rate_pct":          round(result.win_rate * 100, 2),
            "max_drawdown_pct":      round(result.max_drawdown_pct * 100, 2),
            "net_profit":            round(result.net_profit, 2),
            "expectancy_r":          round(result.expectancy_r, 3),
            "total_trades":          result.total_trades,
            "cagr_pct":              round(result.cagr * 100, 2),
            "avg_rr":                round(result.average_rr, 2),
        }
