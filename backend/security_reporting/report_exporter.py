"""
backend/security_reporting/report_exporter.py
Phase-6 — Report Exporter: JSON + HTML + optional PDF
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.logger import get_logger

LOGGER = get_logger(__name__)


class ReportExporter:
    """Exports security/compliance reports to multiple formats."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = Path(output_dir or "./reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_json(self, report: Dict[str, Any], filename: Optional[str] = None) -> Path:
        if filename is None:
            filename = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        LOGGER.info("Exported JSON report to %s", path)
        return path

    def to_html(self, report: Dict[str, Any], filename: Optional[str] = None) -> Path:
        if filename is None:
            filename = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
        path = self.output_dir / filename
        html = self._render_html(report)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        LOGGER.info("Exported HTML report to %s", path)
        return path

    def _render_html(self, report: Dict[str, Any]) -> str:
        title = report.get("title", "Security Report")
        sections = []
        for key, value in report.items():
            if key == "title":
                continue
            sections.append(f"<h2>{key}</h2><pre>{json.dumps(value, ensure_ascii=False, indent=2)}</pre>")
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
  <h1>{title}</h1>
  <p>Generated: {datetime.now(timezone.utc).isoformat()}</p>
  {'\n'.join(sections)}
</body>
</html>"""
