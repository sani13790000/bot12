"""
faz 9 - Distributed Tracing
Span-based tracing ba correlation_id propagation
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from .structured_logger import get_logger, _trace_id

logger = get_logger("tracing")


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    status: str = "OK"  # OK | ERROR
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def set_tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    def add_event(self, name: str, attrs: Optional[Dict] = None) -> None:
        self.events.append(
            {"name": name, "timestamp": time.time(), "attrs": attrs or {}}
        )

    def finish(self, error: Optional[Exception] = None) -> None:
        self.end_time = time.time()
        if error:
            self.status = "ERROR"
            self.error = str(error)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error": self.error,
            "tags": self.tags,
            "events": self.events,
        }


class Tracer:
    """Lightweight tracer ba in-memory span storage"""

    MAX_SPANS = 1000

    def __init__(self) -> None:
        self._spans: List[Span] = []
        self._active: Dict[str, Span] = {}

    @asynccontextmanager
    async def start_span(
        self,
        name: str,
        tags: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None,
    ) -> AsyncGenerator[Span, None]:
        """Async context manager baraye span lifecycle"""
        trace_id = _trace_id.get() or str(uuid.uuid4())[:8]
        span = Span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            tags=tags or {},
        )
        self._active[span.span_id] = span

        try:
            yield span
            span.finish()
        except Exception as e:
            span.finish(error=e)
            raise
        finally:
            self._active.pop(span.span_id, None)
            self._spans.append(span)
            if len(self._spans) > self.MAX_SPANS:
                self._spans = self._spans[-self.MAX_SPANS:]

            # Log slow spans
            if span.duration_ms > 500:
                logger.warning(
                    f"Slow span: {name} took {span.duration_ms:.1f}ms",
                    trace_id=trace_id,
                    span_id=span.span_id,
                    duration_ms=span.duration_ms,
                )

    def get_trace(self, trace_id: str) -> List[Dict]:
        return [
            s.to_dict()
            for s in self._spans
            if s.trace_id == trace_id
        ]

    def get_recent_spans(self, limit: int = 100) -> List[Dict]:
        return [s.to_dict() for s in self._spans[-limit:]]

    def get_active_spans(self) -> List[Dict]:
        return [s.to_dict() for s in self._active.values()]

    def get_slow_spans(
        self, threshold_ms: float = 500.0, limit: int = 50
    ) -> List[Dict]:
        slow = [
            s.to_dict()
            for s in self._spans
            if s.duration_ms >= threshold_ms
        ]
        return slow[-limit:]

    def summary(self) -> Dict[str, Any]:
        if not self._spans:
            return {"total": 0}
        durations = [s.duration_ms for s in self._spans]
        errors = [s for s in self._spans if s.status == "ERROR"]
        return {
            "total": len(self._spans),
            "active": len(self._active),
            "errors": len(errors),
            "avg_duration_ms": round(sum(durations) / len(durations), 2),
            "max_duration_ms": round(max(durations), 2),
            "p95_duration_ms": round(
                sorted(durations)[int(len(durations) * 0.95)], 2
            ),
        }


# Singleton
tracer = Tracer()
