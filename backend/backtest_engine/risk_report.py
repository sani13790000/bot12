"""
Galaxy Vast AI Trading Platform
RiskReportGenerator — Institutional Risk Report

Sections:
  - VaR / CVaR analysis
  - Drawdown analysis (underwater chart data)
  - Tail risk metrics
  - Position sizing recommendations
  - Risk classification: CONSERVATIVE / MODERATE / AGGRESSIVE
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .multi_symbol_engine import MultiSymbolResult
from .monte_carlo_advanced import MonteCarloAdvancedResult


class RiskReportGenerator:
    """
    Generates branded Galaxy Vast risk reports.
    """

    BRAND   = "Galaxy Vast AI Trading Platform"
    VERSION = "v3.0.0"

    # Risk thresholds
    SHARPE_EXCELLENT  = 2.0
    SHARPE_GOOD       = 1.0
    MAX_DD_SAFE       = 10.0
    MAX_DD_WARNING    = 20.0
    PF_GOOD           = 1.5

    def classify_risk(self, result: MultiSymbolResult) -> str:
        """Classify overall strategy risk."""
        score = 0
        if result.max_drawdown_pct < self.MAX_DD_SAFE:       score += 2
        elif result.max_drawdown_pct < self.MAX_DD_WARNING:  score += 1
        if result.sharpe_ratio >= self.SHARPE_EXCELLENT:     score += 2
        elif result.sharpe_ratio >= self.SHARPE_GOOD:        score += 1
        if result.profit_factor >= self.PF_GOOD:             score += 1
        if result.max_consecutive_losses <= 3:               score += 1
        if result.win_rate >= 0.55:                          score += 1

        if score >= 6:   return "LOW RISK"
        if score >= 4:   return "MODERATE RISK"
        if score >= 2:   return "HIGH RISK"
        return "VERY HIGH RISK"

    def generate_json(
        self,
        backtest: MultiSymbolResult,
        monte_carlo: Optional[MonteCarloAdvancedResult] = None,
    ) -> dict:
        """Return structured JSON risk report."""
        risk_class = self.classify_risk(backtest)
        recommendations = self._build_recommendations(backtest, monte_carlo)

        report = {
            "brand":           self.BRAND,
            "version":         self.VERSION,
            "generated":       datetime.utcnow().isoformat(),
            "type":            "RISK_REPORT",
            "risk_classification": risk_class,
            "recommendations": recommendations,
            "metrics": {
                "max_drawdown_pct":       backtest.max_drawdown_pct,
                "avg_drawdown_pct":       backtest.avg_drawdown_pct,
                "sharpe_ratio":           backtest.sharpe_ratio,
                "sortino_ratio":          backtest.sortino_ratio,
                "calmar_ratio":           backtest.calmar_ratio,
                "recovery_factor":        backtest.recovery_factor,
                "max_consecutive_losses": backtest.max_consecutive_losses,
                "win_rate":               round(backtest.win_rate * 100, 1),
                "profit_factor":          backtest.profit_factor,
            },
        }
        if monte_carlo:
            mc = monte_carlo.to_dict()
            report["monte_carlo_risk"] = {
                "probability_ruin_pct":  mc["probability_ruin_pct"],
                "var_95pct":             mc["var"].get("95pct", 0),
                "cvar_95pct":            mc["cvar"].get("95pct", 0),
                "worst_max_drawdown":    mc["drawdown"]["worst_max_pct"],
                "optimal_risk_pct":      mc["optimal_risk_pct"],
                "kelly_fraction":        mc["kelly_fraction"],
            }
        return report

    def generate_html(
        self,
        backtest: MultiSymbolResult,
        monte_carlo: Optional[MonteCarloAdvancedResult] = None,
    ) -> str:
        """Return full standalone HTML risk report."""
        risk_class  = self.classify_risk(backtest)
        recs        = self._build_recommendations(backtest, monte_carlo)
        recs_html   = "".join(f'<li>{r}</li>' for r in recs)

        risk_color = {
            "LOW RISK": "#10b981", "MODERATE RISK": "#f59e0b",
            "HIGH RISK": "#f97316", "VERY HIGH RISK": "#ef4444",
        }.get(risk_class, "#6b7280")

        dd_data = json.dumps([round(e.drawdown * 100, 3) for e in backtest.drawdown_curve[:300]])
        labels  = json.dumps([e.time.strftime("%Y-%m-%d") for e in backtest.drawdown_curve[:300]])

        mc_section = ""
        if monte_carlo:
            mc = monte_carlo.to_dict()
            mc_section = f"""
            <div class="section">
                <h2>🎲 Probabilistic Risk (Monte Carlo)</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Ruin Probability</div>
                        <div class="metric-value" style="color:{'#ef4444' if mc['probability_ruin_pct']>5 else '#10b981'}">{mc['probability_ruin_pct']}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">VaR 95%</div>
                        <div class="metric-value negative">{mc['var'].get('95pct',0):.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">CVaR 95%</div>
                        <div class="metric-value negative">{mc['cvar'].get('95pct',0):.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Worst Drawdown (MC)</div>
                        <div class="metric-value negative">{mc['drawdown']['worst_max_pct']:.2f}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Optimal Risk %</div>
                        <div class="metric-value positive">{mc['optimal_risk_pct']}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Kelly Fraction</div>
                        <div class="metric-value">{mc['kelly_fraction']:.4f}</div>
                    </div>
                </div>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Galaxy Vast — Risk Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:'Segoe UI',system-ui,sans-serif; background:#0a0f1e; color:#e2e8f0; }}
        .header {{ background:linear-gradient(135deg,#1a1f3e,#0d1530);
                   border-bottom:2px solid #ef4444; padding:24px 40px;
                   display:flex; justify-content:space-between; align-items:center; }}
        .brand {{ font-size:22px; font-weight:700; color:#f87171; }}
        .brand span {{ color:#f8fafc; }}
        .risk-badge {{ background:#1f0a0a; color:{risk_color}; border:2px solid {risk_color};
                       border-radius:8px; padding:8px 20px; font-size:14px; font-weight:700; }}
        .content {{ max-width:1400px; margin:0 auto; padding:32px 40px; }}
        .section {{ margin-bottom:40px; }}
        h2 {{ font-size:18px; font-weight:600; color:#f1f5f9;
              border-left:3px solid #ef4444; padding-left:12px; margin-bottom:20px; }}
        .metrics-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:16px; }}
        .metric-card {{ background:#111827; border:1px solid #1f2937; border-radius:12px;
                        padding:20px; text-align:center; }}
        .metric-label {{ font-size:12px; color:#6b7280; margin-bottom:8px; text-transform:uppercase; }}
        .metric-value {{ font-size:24px; font-weight:700; }}
        .positive {{ color:#10b981; }} .negative {{ color:#ef4444; }} .neutral {{ color:#f59e0b; }}
        .chart-container {{ background:#111827; border:1px solid #1f2937;
                            border-radius:12px; padding:24px; margin-bottom:24px; }}
        canvas {{ max-height:280px; }}
        ul {{ list-style:none; padding:0; }}
        ul li {{ padding:10px 14px; background:#111827; border-left:3px solid #3b82f6;
                 margin-bottom:8px; border-radius:0 8px 8px 0; font-size:14px; }}
        .footer {{ text-align:center; padding:24px; color:#4b5563; font-size:12px;
                   border-top:1px solid #1f2937; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="brand">🌌 Galaxy <span>Vast</span></div>
            <div style="font-size:13px;color:#94a3b8;margin-top:4px;">
                Institutional AI Trading Platform — Risk Report</div>
        </div>
        <div class="risk-badge">⚠️ {risk_class}</div>
    </div>

    <div class="content">

        <div class="section">
            <h2>📊 Core Risk Metrics</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Max Drawdown</div>
                    <div class="metric-value {'positive' if backtest.max_drawdown_pct < 10 else 'negative'}">{backtest.max_drawdown_pct:.2f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Sharpe Ratio</div>
                    <div class="metric-value {'positive' if backtest.sharpe_ratio >= 1 else 'neutral'}">{backtest.sharpe_ratio:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Sortino Ratio</div>
                    <div class="metric-value {'positive' if backtest.sortino_ratio >= 1 else 'neutral'}">{backtest.sortino_ratio:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Calmar Ratio</div>
                    <div class="metric-value {'positive' if backtest.calmar_ratio >= 1 else 'neutral'}">{backtest.calmar_ratio:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Recovery Factor</div>
                    <div class="metric-value {'positive' if backtest.recovery_factor >= 2 else 'neutral'}">{backtest.recovery_factor:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Max Consec. Losses</div>
                    <div class="metric-value {'positive' if backtest.max_consecutive_losses <= 3 else 'negative'}">{backtest.max_consecutive_losses}</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📉 Drawdown Analysis</h2>
            <div class="chart-container">
                <canvas id="ddChart"></canvas>
            </div>
        </div>

        {mc_section}

        <div class="section">
            <h2>✅ Risk Recommendations</h2>
            <ul>{recs_html}</ul>
        </div>

    </div>

    <div class="footer">
        <strong>Galaxy Vast AI Trading Platform</strong> — Risk Classification: {risk_class} |
        Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
    </div>

    <script>
    new Chart(document.getElementById('ddChart'), {{
        type: 'line',
        data: {{
            labels: {labels},
            datasets: [{{
                label: 'Drawdown (%)',
                data: {dd_data}.map(v => -v),
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239,68,68,0.1)',
                borderWidth: 2, fill: true, tension: 0.2, pointRadius: 0,
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
</html>"""

    def _build_recommendations(

    def _build_recommendations(
        self,
        result: MultiSymbolResult,
        mc: Optional[MonteCarloAdvancedResult] = None,
    ) -> list:
        recs = []
        if result.max_drawdown_pct > 20:
            recs.append(f"⚠️ Max drawdown {result.max_drawdown_pct:.1f}% exceeds 20% — reduce position sizing immediately")
        elif result.max_drawdown_pct > 10:
            recs.append(f"🔔 Max drawdown {result.max_drawdown_pct:.1f}% above optimal threshold — consider tighter risk controls")
        else:
            recs.append(f"✅ Max drawdown {result.max_drawdown_pct:.1f}% within acceptable range")

        if result.sharpe_ratio < 0.5:
            recs.append("⚠️ Sharpe Ratio < 0.5 — risk-adjusted return is poor. Revisit entry/exit logic")
        elif result.sharpe_ratio >= 1.5:
            recs.append(f"✅ Excellent Sharpe Ratio {result.sharpe_ratio:.2f} — strategy has strong risk-adjusted returns")

        if result.max_consecutive_losses > 5:
            recs.append(f"⚠️ {result.max_consecutive_losses} consecutive losses detected — implement a circuit breaker after 3-4 losses")

        if result.profit_factor < 1.2:
            recs.append("⚠️ Profit Factor < 1.2 — strategy barely profitable after costs. Needs improvement")
        elif result.profit_factor >= 2.0:
            recs.append(f"✅ Strong Profit Factor {result.profit_factor:.2f} — strategy generates solid gross profit vs loss")

        if mc:
            if mc.probability_ruin > 0.05:
                recs.append(f"🚨 Monte Carlo ruin probability {mc.probability_ruin*100:.1f}% — CRITICAL: reduce risk per trade")
            recs.append(f"📊 Optimal position sizing: {mc.optimal_risk_pct:.1f}% per trade (Half-Kelly criterion)")

        if not recs:
            recs.append("✅ Risk profile is within acceptable institutional parameters")
        return recs
