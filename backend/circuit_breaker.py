from enum import Enum

class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

"""
backend/circuit_breaker.py
Galaxy Vast AI — Circuit Breaker
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    timeout: float = 30.0


class CircuitBreaker:
    """Async circuit breaker implementation."""

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = State.CLOSED
        self._failures = 0
        self._successes = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            if self._state == State.OPEN:
                if (time.time() - (self._last_failure_time or 0)) > self._config.recovery_timeout:
                    self._state = State.HALF_OPEN
                    self._successes = 0
                else:
                    raise RuntimeError(f"Circuit breaker {self._name!r} is OPEN")
        try:
            result = await asyncio.wait_for(asyncio.coroutine(func)(*args, **kwargs)
                                            if asyncio.iscoroutinefunction(func)
                                            else asyncio.get_event_loop().run_in_executor(None, func, *args),
                                            timeout=self._config.timeout)
            await self._on_success()
            return result
        except Exception as exc:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            if self._state == State.HALF_OPEN:
                self._successes += 1
                if self._successes >= self._config.success_threshold:
                    self._state = State.CLOSED
                    _LOG.info("Circuit breaker %r closed.", self._name)

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self._config.failure_threshold:
                self._state = State.OPEN
                _LOG.warning("Circuit breaker %r opened (failures=%d)", self._name, self._failures)
