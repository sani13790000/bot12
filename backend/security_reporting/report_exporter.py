"""
backend/security_reporting/report_exporter.py
Galaxy Vast AI — Security Report Exporter

Exports security reports in multiple formats:
- JSON (raw)
- CSV (summary)
- PDF (via reportlab if available, else text fallback)
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
    """
    Exports security reports in JSON, CSV, or PDF format.
    """

    # ------------------------------------------------------------------ #
    # JSON
    # ------------------------------------------------------------------ #

    def to_json(
        self,
        report: Dict[str, Any],
        indent: int = 2,
        pretty: bool = True,
    ) -> str:
        """Serialise report to JSON string."""
        return json.dumps(report, indent=indent if pretty else None, default=str)

    # ------------------------------------------------------------------ #
    # CSV
    # ------------------------------------------------------------------ #

    def to_csv(
        self,
        events: List[Dict[str, Any]],
        fields: Optional[List[str]] = None,
    ) -> str:
        """
        Export a list of security events to CSV.

        Args:
            events: List of event dicts.
            fields: Column names to include; auto-detected if None.
        """
        if not events:
            return ""

        columns = fields or sorted({k for event in events for k in event})

        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for event in events:
            writer.writerow({k: event.get(k, "") for k in columns})
        return buf.getvalue()

    # ------------------------------------------------------------------ #
    # PDF (reportlab) with text fallback
    # ------------------------------------------------------------------ #

    def to_pdf(self, report: Dict[str, Any], title: str = "Security Report") -> bytes:
        """
        Export report as PDF.
        Falls back to UTF-8 text if reportlab is not installed.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4)
            styles = getSampleStyleSheet()
            story = [
                Paragraph(title, styles["Title"]),
                Spacer(1, 12),
                Paragraph(
                    f"Generated: {datetime.now(timezone.utc).isoformat()}",
                    styles["Normal"],
                ),
                Spacer(1, 12),
                Paragraph(
                    json.dumps(report, indent=2, default=str).replace("\n", "<br/>"),
                    styles["Code"],
                ),
            ]
            doc.build(story)
            return buf.getvalue()

        except ImportError:
            logger.warning("[ReportExporter] reportlab not installed; falling back to text PDF")
            text = f"{title}\n{'=' * len(title)}\n"
            text += f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
            text += json.dumps(report, indent=2, default=str)
            return text.encode("utf-8")


# Module-level singleton
report_exporter = SecurityReportExporter()
