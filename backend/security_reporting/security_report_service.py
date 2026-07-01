"""
backend/security_reporting/security_report_service.py
Galaxy Vast AI — Security Report Service
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class SecurityReportService:
    """Service for generating and managing security reports."""

    def __init__(self) -> None:
        self._reports: List[Dict[str, Any]] = []

    def generate_report(self, period: str = '24h') -> Dict[str, Any]:
        return {
            'period': period,
            'generated_at': time.time(),
            'events': self._reports[-100:],
            'summary': {'total_events': len(self._reports)},
        }

    def record_event(self, event_type: str, details: Dict[str, Any]) -> None:
        self._reports.append({
            'type': event_type,
            'ts': time.time(),
            **details,
        })

    def get_recent_events(self, n: int = 100) -> List[Dict[str, Any]]:
        return self._reports[-n:]

    def clear(self) -> None:
        self._reports.clear()


_service: Optional[SecurityReportService] = None


def get_security_report_service() -> SecurityReportService:
    global _service
    if _service is None:
        _service = SecurityReportService()
    return _service
