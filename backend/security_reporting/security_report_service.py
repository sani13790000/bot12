"""
backend/security_reporting/security_report_service.py
Galaxy Vast AI — Security Report Service
"""
from __future__ import annotations
import logging, time, uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

@dataclass
class SecurityEvent:
    event_id: str; category: str; severity: str; message: str; source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict); resolved: bool = False

@dataclass
class SecurityReport:
    report_id: str; title: str; generated_at: datetime; period_start: datetime; period_end: datetime
    total_events: int = 0; critical_events: int = 0; warning_events: int = 0; info_events: int = 0
    top_categories: List[str] = field(default_factory=list)
    events: List[SecurityEvent] = field(default_factory=list); summary: str = ""

class SecurityReportService:
    def __init__(self, max_events=10000):
        self._events: List[SecurityEvent] = []; self._max = max_events
        self._log = logging.getLogger(self.__class__.__name__)
    def record_event(self, category, severity, message, source="system", **meta) -> str:
        eid = str(uuid.uuid4())[:12]
        self._events.append(SecurityEvent(event_id=eid, category=category, severity=severity, message=message, source=source, metadata=meta))
        if len(self._events) > self._max: self._events = self._events[-self._max//2:]
        return eid
    def get_events(self, category=None, severity=None, limit=100):
        evts = self._events
        if category: evts=[e for e in evts if e.category==category]
        if severity: evts=[e for e in evts if e.severity.upper()==severity.upper()]
        return evts[-limit:]
    def generate_report(self, title="Security Audit", period_hours=24.0) -> SecurityReport:
        now = datetime.now(timezone.utc); cutoff = time.time() - period_hours*3600
        evts=[e for e in self._events if e.timestamp.timestamp()>=cutoff]
        cats={}
        for e in evts: cats[e.category]=cats.get(e.category,0)+1
        top=sorted(cats,key=lambda k:cats[k],reverse=True)[:5]
        crit=sum(1 for e in evts if e.severity.upper()=="CRITICAL")
        warn=sum(1 for e in evts if e.severity.upper()=="WARNING")
        info=sum(1 for e in evts if e.severity.upper()=="INFO")
        return SecurityReport(
            report_id=str(uuid.uuid4())[:12], title=title, generated_at=now,
            period_start=datetime.fromtimestamp(cutoff,tz=timezone.utc), period_end=now,
            total_events=len(evts), critical_events=crit, warning_events=warn, info_events=info,
            top_categories=top, events=evts[-50:],
            summary=f"{len(evts)} events in {period_hours:.0f}h: {crit} critical, {warn} warnings")
    def to_dict(self, r):
        return {"report_id":r.report_id,"title":r.title,"generated_at":r.generated_at.isoformat(),
                "total_events":r.total_events,"critical":r.critical_events,"summary":r.summary}

_svc: Optional[SecurityReportService] = None
def get_security_report_service():
    global _svc
    if _svc is None: _svc = SecurityReportService()
    return _svc
