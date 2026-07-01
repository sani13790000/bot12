"""
backend/security_reporting/report_exporter.py
Galaxy Vast AI — Security Report Exporter

Exports security audit reports in multiple formats:
  - JSON (machine-readable)
  - HTML (human-readable)
  - CSV (spreadsheet import)
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecurityReportExporter:
    """Multi-format security report exporter."""

    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)

    def to_json(self, report: Dict[str, Any], indent: int = 2) -> str:
        """Export report as JSON string."""
        return json.dumps(report, indent=indent, default=str, ensure_ascii=False)

    def to_csv(self, events: List[Dict[str, Any]]) -> str:
        """Export event list as CSV."""
        if not events:
            return ""
        buf = io.StringIO()
        fieldnames = list(events[0].keys()) if events else ["ts", "event", "severity", "detail"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for event in events:
            writer.writerow(event)
        return buf.getvalue()

    def to_html(self, report: Dict[str, Any], title: str = "Security Report") -> str:
        """Export report as HTML."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        events = report.get("events", [])
        rows = ""
        for e in events:
            severity = e.get("severity", "info").upper()
            color = {"CRITICAL": "#ff4444", "WARNING": "#ff8800", "INFO": "#4488ff"}.get(severity, "#888")
            rows += (
                f"<tr>"
                f"<td>{e.get('ts', '')}</td>"
                f"<td style='color:{color}'>{severity}</td>"
                f"<td>{e.get('event', '')}</td>"
                f"<td>{e.get('detail', '')}</td>"
                f"</tr>\n"
            )
        return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>body{{font-family:monospace;padding:20px}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:6px 12px;text-align:left}}
th{{background:#222;color:#fff}}
</style></head><body>
<h1>{title}</h1><p>Generated: {ts}</p>
<table><tr><th>Timestamp</th><th>Severity</th><th>Event</th><th>Detail</th></tr>
{rows}</table></body></html>"""

    def export(self, report: Dict[str, Any], fmt: str = "json") -> str:
        """Export in the specified format."""
        if fmt == "json":
            return self.to_json(report)
        elif fmt == "csv":
            return self.to_csv(report.get("events", []))
        elif fmt == "html":
            return self.to_html(report)
        else:
            raise ValueError(f"Unknown format: {fmt}")


_exporter: Optional[SecurityReportExporter] = None


def get_report_exporter() -> SecurityReportExporter:
    global _exporter
    if _exporter is None:
        _exporter = SecurityReportExporter()
    return _exporter
