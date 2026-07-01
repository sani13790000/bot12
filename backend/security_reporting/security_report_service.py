"""
backend/security_reporting/security_report_service.py
Phase-6 — Security Report Service
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
__all__ = ["SecurityReportService", "SecurityEvent", "get_report_service"]


@dataclass
class SecurityEvent:
    event_type: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_ip: str = ""
    user_id: str = ""


class SecurityReportService:
    """Collects and exports security events."""

    def __init__(self, max_events: int = 10000) -> None:
        self._events: List[SecurityEvent] = []
        self._max = max_events

    def record(self, event: SecurityEvent) -> None:
        self._events.append(event)
        if len(self._events) > self._max:
            self._events = self._events[-self._max:]
        if event.severity in ("HIGH", "CRITICAL"):
            logger.warning("Security event [%s]: %s", event.event_type, event.message)

    def get_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[SecurityEvent]:
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if severity:
            events = [e for e in events if e.severity == severity]
        return events[-limit:]

    def summary(self) -> Dict[str, int]:
        by_severity: Dict[str, int] = {}
        for e in self._events:
            by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
        return by_severity

    def clear(self) -> None:
        self._events.clear()


_service: Optional[SecurityReportService] = None

def get_report_service() -> SecurityReportService:
    global _service
    if _service is None:
        _service = SecurityReportService()
    return _service
