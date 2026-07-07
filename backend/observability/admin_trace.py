"""
backend/observability/admin_trace.py — Phase 15 (NEW FILE)
P15-OBS-TRACE-1: AdminTracer — structured event trail
P15-OBS-TRACE-2: issue_trace() — admin quick trace
P15-OBS-TRACE-3: per-user timeline
P15-OBS-TRACE-4: correlated_events()
P15-OBS-TRACE-5: export_csv()
"""

from __future__ import annotations

import csv
import io
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceEvent:
    event_id: str
    trace_id: str
    category: str
    action: str
    level: str
    user_id: Optional[str]
    device_id: Optional[str]
    detail: Dict[str, Any]
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "category": self.category,
            "action": self.action,
            "level": self.level,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "detail": self.detail,
            "ts": self.ts,
        }


class AdminTracer:
    _MAX_EVENTS = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[TraceEvent] = []
        self._idx_user: Dict[str, List[int]] = {}
        self._idx_trace: Dict[str, List[int]] = {}
        self._idx_category: Dict[str, List[int]] = {}

    def record(
        self,
        category: str,
        action: str,
        level: str = "INFO",
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> str:
        tid = trace_id or str(uuid.uuid4())[:8]
        eid = str(uuid.uuid4())[:12]
        event = TraceEvent(
            event_id=eid,
            trace_id=tid,
            category=category,
            action=action,
            level=level,
            user_id=user_id,
            device_id=device_id,
            detail=detail or {},
        )
        with self._lock:
            idx = len(self._events)
            self._events.append(event)
            if user_id:
                self._idx_user.setdefault(user_id, []).append(idx)
            self._idx_trace.setdefault(tid, []).append(idx)
            self._idx_category.setdefault(category, []).append(idx)
            if len(self._events) > self._MAX_EVENTS:
                self._gc()
        return eid

    def record_license_failure(
        self,
        reason: str,
        user_id: str,
        device_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        return self.record(
            "license",
            "license_failure",
            "CRITICAL",
            user_id=user_id,
            device_id=device_id,
            trace_id=trace_id,
            detail={"reason": reason},
        )

    def record_heartbeat_loss(
        self,
        device_id: str,
        gap_s: float,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        return self.record(
            "heartbeat",
            "heartbeat_loss",
            "CRITICAL",
            user_id=user_id,
            device_id=device_id,
            trace_id=trace_id,
            detail={"gap_s": gap_s},
        )

    def record_kill_switch(self, actor: str, reason: str, trace_id: Optional[str] = None) -> str:
        return self.record(
            "kill_switch",
            "kill_switch_activated",
            "CRITICAL",
            user_id=actor,
            trace_id=trace_id,
            detail={"actor": actor, "reason": reason},
        )

    def record_reconciliation_mismatch(
        self, symbol: str, broker_qty: float, local_qty: float, trace_id: Optional[str] = None
    ) -> str:
        return self.record(
            "reconciliation",
            "reconciliation_mismatch",
            "CRITICAL",
            trace_id=trace_id,
            detail={
                "symbol": symbol,
                "broker": broker_qty,
                "local": local_qty,
                "delta": abs(broker_qty - local_qty),
            },
        )

    def record_drawdown(
        self, pct: float, equity_usd: Optional[float] = None, trace_id: Optional[str] = None
    ) -> str:
        level = "CRITICAL" if pct >= 10.0 else "WARNING"
        return self.record(
            "drawdown",
            "drawdown_alert",
            level,
            trace_id=trace_id,
            detail={"pct": pct, "equity_usd": equity_usd},
        )

    def issue_trace(
        self,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        category: Optional[str] = None,
        since_ts: Optional[float] = None,
        until_ts: Optional[float] = None,
        level: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if user_id and user_id in self._idx_user:
                indices = self._idx_user[user_id]
                events = [self._events[i] for i in indices if i < len(self._events)]
            elif trace_id and trace_id in self._idx_trace:
                indices = self._idx_trace[trace_id]
                events = [self._events[i] for i in indices if i < len(self._events)]
            elif category and category in self._idx_category:
                indices = self._idx_category[category]
                events = [self._events[i] for i in indices if i < len(self._events)]
            else:
                events = list(self._events)
        if since_ts:
            events = [e for e in events if e.ts >= since_ts]
        if until_ts:
            events = [e for e in events if e.ts <= until_ts]
        if level:
            events = [e for e in events if e.level == level]
        events = sorted(events, key=lambda e: e.ts)[-limit:]
        return [e.to_dict() for e in events]

    def user_timeline(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self.issue_trace(user_id=user_id, limit=limit)

    def correlated_events(self, trace_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.issue_trace(trace_id=trace_id, limit=limit)

    def export_csv(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 5000,
    ) -> str:
        events = self.issue_trace(
            user_id=user_id, category=category, since_ts=since_ts, limit=limit
        )
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "ts",
                "event_id",
                "trace_id",
                "category",
                "action",
                "level",
                "user_id",
                "device_id",
                "detail",
            ],
        )
        writer.writeheader()
        for ev in events:
            writer.writerow({**ev, "detail": str(ev.get("detail", {}))})
        return buf.getvalue()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._events)
            by_category: Dict[str, int] = {}
            by_level: Dict[str, int] = {}
            for ev in self._events:
                by_category[ev.category] = by_category.get(ev.category, 0) + 1
                by_level[ev.level] = by_level.get(ev.level, 0) + 1
        return {
            "total_events": total,
            "by_category": by_category,
            "by_level": by_level,
            "users_tracked": len(self._idx_user),
            "traces_tracked": len(self._idx_trace),
        }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._idx_user.clear()
            self._idx_trace.clear()
            self._idx_category.clear()

    def _gc(self) -> None:
        keep = int(self._MAX_EVENTS * 0.8)
        self._events = self._events[-keep:]
        self._idx_user.clear()
        self._idx_trace.clear()
        self._idx_category.clear()
        for i, ev in enumerate(self._events):
            if ev.user_id:
                self._idx_user.setdefault(ev.user_id, []).append(i)
            self._idx_trace.setdefault(ev.trace_id, []).append(i)
            self._idx_category.setdefault(ev.category, []).append(i)


admin_tracer = AdminTracer()
