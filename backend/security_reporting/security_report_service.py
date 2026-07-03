"""
backend/security_reporting/security_report_service.py
Galaxy Vast AI — Security Report Service
"""
from __future__ import annotations
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class SecurityReportService:
    """Collects and serves security events and reports."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._started_at = time.time()

    def record_event(self, event_type: str, **kwargs: Any) -> None:
        self._events.append({
            "type": event_type,
            "ts": time.time(),
            **kwargs,
        })
        # Cap at 10_000 events
        if len(self._events) > 10_000:
            self._events = self._events[-10_000:]

    def get_events(
        self,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        events = self._events
        if event_type:
            events = [e for e in events if e.get("type") == event_type]
        return events[-limit:]

    def generate_report(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for e in self._events:
            t = e.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_events": len(self._events),
            "by_type": by_type,
            "uptime_s": time.time() - self._started_at,
        }

    def clear(self) -> None:
        self._events.clear()


_service: SecurityReportService | None = None


def get_security_report_service() -> SecurityReportService:
    global _service
    if _service is None:
        _service = SecurityReportService()
    return _service


__all__ = ["SecurityReportService", "get_security_report_service"]
