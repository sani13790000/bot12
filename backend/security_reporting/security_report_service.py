"""
backend/security_reporting/security_report_service.py
Galaxy Vast AI — Security Report Service

Generates, stores, and serves security audit reports.
Supports scheduled generation and on-demand export.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SecurityEvent:
    event_id: str
    category: str
    severity: str
    message: str
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


@dataclass
class SecurityReport:
    report_id: str
    title: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    total_events: int = 0
    critical_events: int = 0
    warning_events: int = 0
    info_events: int = 0
    top_categories: List[str] = field(default_factory=list)
    events: List[SecurityEvent] = field(default_factory=list)
    summary: str = ""


class SecurityReportService:
    """Manages security event collection and report generation."""

    def __init__(self, max_events: int = 10_000) -> None:
        self._events: List[SecurityEvent] = []
        self._max = max_events
        self._log = logging.getLogger(self.__class__.__name__)

    def record_event(
        self,
        category: str,
        severity: str,
        message: str,
        source: str = "system",
        **metadata,
    ) -> str:
        """Record a security event. Returns event_id."""
        import uuid
        eid = str(uuid.uuid4())[:12]
        evt = SecurityEvent(
            event_id=eid,
            category=category,
            severity=severity,
            message=message,
            source=source,
            metadata=metadata,
        )
        self._events.append(evt)
        if len(self._events) > self._max:
            self._events = self._events[-self._max // 2:]
        return eid

    def get_events(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[SecurityEvent]:
        events = self._events
        if category:
            events = [e for e in events if e.category == category]
        if severity:
            events = [e for e in events if e.severity.upper() == severity.upper()]
        return events[-limit:]

    def generate_report(
        self,
        title: str = "Security Audit Report",
        period_hours: float = 24.0,
    ) -> SecurityReport:
        """Generate a report for the last period_hours."""
        import uuid
        now = datetime.now(timezone.utc)
        cutoff_ts = time.time() - (period_hours * 3600)
        period_events = [
            e for e in self._events
            if e.timestamp.timestamp() >= cutoff_ts
        ]
        cats = {}
        for e in period_events:
            cats[e.category] = cats.get(e.category, 0) + 1
        top_cats = sorted(cats, key=lambda k: cats[k], reverse=True)[:5]
        critical = sum(1 for e in period_events if e.severity.upper() == "CRITICAL")
        warning = sum(1 for e in period_events if e.severity.upper() == "WARNING")
        info = sum(1 for e in period_events if e.severity.upper() == "INFO")
        return SecurityReport(
            report_id=str(uuid.uuid4())[:12],
            title=title,
            generated_at=now,
            period_start=datetime.fromtimestamp(cutoff_ts, tz=timezone.utc),
            period_end=now,
            total_events=len(period_events),
            critical_events=critical,
            warning_events=warning,
            info_events=info,
            top_categories=top_cats,
            events=period_events[-50:],
            summary=f"{len(period_events)} events in last {period_hours:.0f}h: {critical} critical, {warning} warnings",
        )

    def to_dict(self, report: SecurityReport) -> Dict[str, Any]:
        return {
            "report_id": report.report_id,
            "title": report.title,
            "generated_at": report.generated_at.isoformat(),
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "total_events": report.total_events,
            "critical_events": report.critical_events,
            "warning_events": report.warning_events,
            "info_events": report.info_events,
            "top_categories": report.top_categories,
            "summary": report.summary,
        }


_service: Optional[SecurityReportService] = None


def get_security_report_service() -> SecurityReportService:
    global _service
    if _service is None:
        _service = SecurityReportService()
    return _service
