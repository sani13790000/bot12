"""Request tracing for Galaxy Vast. Phase L fixes L-13/L-17/L-18."""
from __future__ import annotations

import time
import uuid
from collections import deque
from contextvars import ContextVar
from typing import Any, Deque, Dict, List, Optional

_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_MAX_SPANS = 1000


def new_trace_id() -> str:
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> Optional[str]:
    return _trace_id_var.get()


class Timer:
    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.perf_counter() - self._start


class Span:
    def __init__(self, name: str, trace_id: Optional[str] = None) -> None:
        self.span_id = str(uuid.uuid4())[:8]
        self.trace_id = trace_id or get_trace_id() or new_trace_id()
        self.name = name
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.tags: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def finish(self, error: Optional[str] = None) -> "Span":
        self.end_time = time.perf_counter()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.error = error
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "tags": self.tags,
            "finished": self.end_time is not None,
        }


class Tracer:
    """In-process span collector. FIX L-13/L-17."""

    def __init__(self, max_spans: int = _MAX_SPANS) -> None:
        self._spans: Deque[Span] = deque(maxlen=max_spans)
        self._active: Dict[str, Span] = {}

    def start_span(self, name: str) -> Span:
        span = Span(name)
        self._active[span.span_id] = span
        return span

    def finish_span(self, span: Span, error: Optional[str] = None) -> None:
        span.finish(error=error)
        self._active.pop(span.span_id, None)
        self._spans.append(span)

    def get_recent_spans(self, limit: int = 100) -> List[Dict[str, Any]]:
        items = list(self._spans)
        items.reverse()
        return [s.to_dict() for s in items[:limit]]

    def get_active_spans(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._active.values()]

    def get_slow_spans(self, threshold_ms: float = 500.0) -> List[Dict[str, Any]]:
        return [
            s.to_dict()
            for s in reversed(list(self._spans))
            if s.duration_ms >= threshold_ms
        ]

    def summary(self) -> Dict[str, Any]:
        spans = list(self._spans)
        if not spans:
            return {"total": 0, "errors": 0, "avg_duration_ms": 0.0}
        durations = [s.duration_ms for s in spans if s.end_time is not None]
        errors = sum(1 for s in spans if s.error)
        return {
            "total": len(spans),
            "errors": errors,
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "max_duration_ms": max(durations, default=0.0),
        }

    def clear(self) -> None:
        self._spans.clear()
        self._active.clear()


tracer = Tracer()
