"""
backend/security_reporting/report_exporter.py
Phase-6 -- Security Report Exporter
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any


class ReportExporter:
    """Export security reports to JSON, CSV, and HTML formats."""

    @staticmethod
    def to_json(report: dict) -> str:
        """Serialize report to JSON string."""
        return json.dumps(report, indent=2, ensure_ascii=False, default=str)

    @staticmethod
    def to_csv(report: dict) -> str:
        """Serialize report findings to CSV."""
        findings = report.get("findings", [])
        if not findings:
            return "severity,title,description\n"
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["severity", "title", "description"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(findings)
        return output.getvalue()

    @staticmethod
    def to_html(report: dict) -> str:
        """Serialize report to a minimal HTML page."""
        timestamp = report.get("timestamp", datetime.now(timezone.utc).isoformat())
        findings  = report.get("findings", [])
        rows = "".join(
            f"<tr><td>{f.get('severity','')}</td>"
            f"<td>{f.get('title','')}</td>"
            f"<td>{f.get('description','')}</td></tr>"
            for f in findings
        )
        return (
            "<!DOCTYPE html><html><head><title>Security Report</title></head><body>"
            f"<h1>Security Report</h1><p>Generated: {timestamp}</p>"
            "<table border='1'><tr><th>Severity</th><th>Title</th><th>Description</th></tr>"
            f"{rows}</table></body></html>"
        )


report_exporter = ReportExporter()
