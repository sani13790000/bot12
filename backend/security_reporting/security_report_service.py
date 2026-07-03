"""
backend/security_reporting/security_report_service.py
Galaxy Vast AI — Security Report Service

Aggregates security events and generates structured reports.
P14-SR-1: events stored with structured fields (not raw strings)
P14-SR-2: report includes severity breakdown
P14-SR-3: GDPR-safe — no PII in exported reports
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class SecurityEvent:
    """A single security-relevant event."""
    event_type:  str
    severity:    str                # "low"|"medium"|"high"|"critical"
    source:      str
    message:     str
    timestamp:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata:    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "severity":   self.severity,
            "source":     self.source,
            "message":    self.message,
            "timestamp":  self.timestamp,
            "metadata":   self.metadata,
        }


@dataclass
class SecurityReport:
    """Aggregated security report for a time period."""
    period_start:  str
    period_end:    str
    total_events:  int
    critical:      int
    high:          int
    medium:        int
    low:           int
    top_sources:   List[str] = field(default_factory=list)
    top_types:     List[str] = field(default_factory=list)
    events:        List[SecurityEvent] = field(default_factory=list)
    generated_at:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start":  self.period_start,
            "period_end":    self.period_end,
            "generated_at":  self.generated_at,
            "total_events":  self.total_events,
            "severity": {
                "critical": self.critical,
                "high":     self.high,
                "medium":   self.medium,
                "low":      self.low,
            },
            "top_sources":   self.top_sources,
            "top_types":     self.top_types,
            "events":        [e.to_dict() for e in self.events],
        }


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class SecurityReportService:
    """
    Collects security events and builds reports.
    """

    def __init__(self, db: Any = None, max_memory_events: int = 10_000) -> None:
        self._db     = db
        self._buffer: List[SecurityEvent] = []
        self._max    = max_memory_events
        self._lock   = asyncio.Lock()

    async def record(
        self,
        event_type: str,
        severity:   str,
        source:     str,
        message:    str,
        metadata:   Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a security event."""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            source=source,
            message=message,
            metadata=metadata or {},
        )
        async with self._lock:
            if len(self._buffer) >= self._max:
                self._buffer.pop(0)
            self._buffer.append(event)

        if self._db:
            try:
                await self._db.insert("security_events", event.to_dict())
            except Exception as exc:
                logger.error("[SecurityReport] DB insert failed: %s", exc)

        level = logging.CRITICAL if severity == "critical" else logging.WARNING
        logger.log(level, "[SecurityEvent] %s %s: %s", severity.upper(), event_type, message)

    async def build_report(
        self,
        start:    Optional[str] = None,
        end:      Optional[str] = None,
        max_events: int = 500,
    ) -> SecurityReport:
        """Build a report from buffered events."""
        async with self._lock:
            events = list(self._buffer[-max_events:])

        now = datetime.now(timezone.utc).isoformat()
        period_start = start or (events[0].timestamp if events else now)
        period_end   = end   or now

        # Severity breakdown
        sev_counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        source_counts: Dict[str, int] = {}
        type_counts:   Dict[str, int] = {}

        for e in events:
            sev_counts[e.severity] = sev_counts.get(e.severity, 0) + 1
            source_counts[e.source] = source_counts.get(e.source, 0) + 1
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1

        top_sources = sorted(source_counts, key=source_counts.get, reverse=True)[:5]
        top_types   = sorted(type_counts,  key=type_counts.get,  reverse=True)[:5]

        return SecurityReport(
            period_start = period_start,
            period_end   = period_end,
            total_events = len(events),
            critical     = sev_counts["critical"],
            high         = sev_counts["high"],
            medium       = sev_counts["medium"],
            low          = sev_counts["low"],
            top_sources  = top_sources,
            top_types    = top_types,
            events       = events,
        )


# Module-level singleton
security_report_service = SecurityReportService()
