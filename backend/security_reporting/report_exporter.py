"""
backend/security_reporting/report_exporter.py
Galaxy Vast AI — Security Report Exporter
"""
from __future__ import annotations
import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ReportExporter:
    """Export security reports in multiple formats."""

    SUPPORTED_FORMATS = ("json", "csv", "txt")

    def export(
        self,
        data: dict[str, Any] | list[dict[str, Any]],
        fmt: str = "json",
    ) -> str:
        fmt = fmt.lower()
        if fmt == "json":
            return self._to_json(data)
        if fmt == "csv":
            return self._to_csv(data)
        if fmt == "txt":
            return self._to_txt(data)
        raise ValueError(f"Unsupported format: {fmt}. Choose from {self.SUPPORTED_FORMATS}")

    def _to_json(self, data: Any) -> str:
        return json.dumps(data, indent=2, default=str)

    def _to_csv(self, data: Any) -> str:
        if isinstance(data, dict):
            data = [data]
        if not data:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
        return buf.getvalue()

    def _to_txt(self, data: Any) -> str:
        lines = [f"Security Report — {datetime.utcnow().isoformat()}", "="*60]
        if isinstance(data, dict):
            for k, v in data.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                lines.append(str(item))
        return "\n".join(lines)


__all__ = ["ReportExporter"]
