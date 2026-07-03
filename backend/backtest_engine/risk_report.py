"""
Galaxy Vast AI Trading Platform
RiskReportGenerator -- Institutional Risk Report Generator
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class RiskMetrics:
    max_drawdown_pct:  float = 0.0
    var_95:            float = 0.0
    cvar_95:           float = 0.0
    sharpe_ratio:      float = 0.0
    sortino_ratio:     float = 0.0
    calmar_ratio:      float = 0.0
    beta:              float = 0.0
    correlation:       float = 0.0
    exposure_pct:      float = 0.0
    margin_usage_pct:  float = 0.0


class RiskReportGenerator:
    """Generate institutional-grade risk analysis reports."""

    def __init__(self) -> None:
        self._generated_at = datetime.now(timezone.utc).isoformat()

    def generate_html(self, metrics: RiskMetrics, symbol: str = "ALL") -> str:
        """Generate an HTML risk report."""
        recs = self._build_recommendations(metrics)
        rec_html = "\n".join(f"<li>{r}</li>" for r in recs)
        return f"""<!DOCTYPE html>
<html><head><title>Risk Report</title></head>
<body>
<h1>Risk Report - {symbol}</h1>
<p>Generated: {self._generated_at}</p>
<table border='1'>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Max Drawdown</td><td>{metrics.max_drawdown_pct:.1f}%</td></tr>
  <tr><td>VaR 95%</td><td>{metrics.var_95:.2f}</td></tr>
  <tr><td>CVaR 95%</td><td>{metrics.cvar_95:.2f}</td></tr>
  <tr><td>Sharpe Ratio</td><td>{metrics.sharpe_ratio:.2f}</td></tr>
  <tr><td>Sortino Ratio</td><td>{metrics.sortino_ratio:.2f}</td></tr>
  <tr><td>Exposure %</td><td>{metrics.exposure_pct:.1f}%</td></tr>
</table>
<h2>Recommendations</h2>
<ul>{rec_html}</ul>
</body></html>"""

    def _build_recommendations(
        self,
        result: RiskMetrics,
        mc: Optional[Any] = None,
    ) -> list:
        recs = []
        if result.max_drawdown_pct > 20:
            recs.append(
                f"Max drawdown {result.max_drawdown_pct:.1f}% exceeds 20% "
                "-- reduce position sizing immediately"
            )
        elif result.max_drawdown_pct > 10:
            recs.append(
                f"Max drawdown {result.max_drawdown_pct:.1f}% exceeds 10% "
                "-- consider reducing exposure"
            )
        if result.sharpe_ratio < 1.0:
            recs.append("Sharpe ratio below 1.0 -- review strategy parameters")
        if not recs:
            recs.append("Risk profile is within acceptable institutional parameters")
        return recs

    def to_dict(self, metrics: RiskMetrics) -> dict:
        return {
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "var_95":          round(metrics.var_95, 4),
            "cvar_95":         round(metrics.cvar_95, 4),
            "sharpe_ratio":    round(metrics.sharpe_ratio, 4),
            "sortino_ratio":   round(metrics.sortino_ratio, 4),
            "generated_at":    self._generated_at,
        }
