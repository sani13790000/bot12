"""Request tracing utilities for Galaxy Vast platform."""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable: current request trace ID
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """Generate a new trace ID and store in context."""
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> Optional[str]:
    """Return current trace ID (or None if not set)."""
    return _trace_id_var.get()


class Timer:
    """Context manager for timing code blocks."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.perf_counter() - self._start
