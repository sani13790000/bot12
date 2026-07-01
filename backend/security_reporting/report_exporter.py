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
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class ReportExporter:
    """Export security reports in various formats."""

    def to_json(self, data: Dict[str, Any]) -> str:
        return json.dumps(data, indent=2, default=str)

    def to_csv(self, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return ''
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def to_markdown(self, data: Dict[str, Any]) -> str:
        lines = [f'# Security Report', f'Generated: {datetime.utcnow().isoformat()}', '']
        for k, v in data.items():
            lines.append(f'## {k}')
            lines.append(f'{v}')
            lines.append('')
        return '\n'.join(lines)

    def export(self, data: Dict[str, Any], fmt: str = 'json') -> str:
        if fmt == 'csv':
            return self.to_csv(data.get('events', []))
        if fmt == 'markdown':
            return self.to_markdown(data)
        return self.to_json(data)


_exporter: Optional[ReportExporter] = None


def get_exporter() -> ReportExporter:
    global _exporter
    if _exporter is None:
        _exporter = ReportExporter()
    return _exporter
