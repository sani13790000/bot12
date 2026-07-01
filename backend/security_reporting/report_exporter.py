"""
backend/security_reporting/report_exporter.py
Phase-6 — Report Exporter: JSON + HTML + optional PDF
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from backend.security_reporting.security_report_service import SecurityReport

log = logging.getLogger(__name__)
_REPORTS_DIR = Path(os.getenv("SECURITY_REPORTS_DIR", "/reports/security"))


def _ensure_dir() -> Path:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR


def export_json(report: SecurityReport) -> Path:
    out = _ensure_dir() / f"{report.report_id}.json"
    with open(out, "w") as fh:
        json.dump(asdict(report), fh, indent=2, default=str)
    log.info("Security report exported to %s", out)
    return out


def export_html(report: SecurityReport) -> Path:
    out = _ensure_dir() / f"{report.report_id}.html"
    rows = ""
    for finding in report.findings:
        severity_class = finding.severity.lower()
        rows += (
            f"<tr class='{severity_class}'>"
            f"<td>{finding.severity}</td>"
            f"<td>{finding.category}</td>"
            f"<td>{finding.description}</td>"
            f"<td>{finding.recommendation}</td>"
            f"</tr>\n"
        )
    html = f"""<!DOCTYPE html><html><head><title>Security Report</title>
    <style>table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
    .critical{{background:#ff6b6b}} .high{{background:#ffa502}}
    .medium{{background:#ffd700}} .low{{background:#2ed573}}
    </style></head><body>
    <h1>Security Report: {report.report_id}</h1>
    <p>Score: {report.overall_score:.1f}/100 | Generated: {report.generated_at}</p>
    <table><tr><th>Severity</th><th>Category</th><th>Description</th><th>Recommendation</th></tr>
    {rows}</table></body></html>"""
    out.write_text(html, encoding="utf-8")
    log.info("HTML report exported to %s", out)
    return out


def export_report(report: SecurityReport, fmt: str = "json") -> Optional[Path]:
    if fmt == "json":
        return export_json(report)
    if fmt == "html":
        return export_html(report)
    log.warning("Unknown report format: %s", fmt)
    return None
