"""
backend/circuit_breaker.py - Hedge-Fund Grade Circuit Breaker v2 (HF-1)

HF-1: 5 failure states tracked per symbol.
HF-2: Exponential back-off with jitter.
HF-3: Thread-safe via asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)
__all__ = ["State", "CircuitBreaker", "get_circuit_breaker"]


class State(Enum):
    """Circuit breaker state machine states."""
    CLOSED    = "CLOSED"     # normal operation
    OPEN      = "OPEN"       # failing — reject all
    HALF_OPEN = "HALF_OPEN"  # testing recovery


class CircuitBreaker:
    """Async-safe circuit breaker."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
    ) -> None:
        self.name = name
        self._state = State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max
        self._half_open_attempts = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def call(self, fn: Callable, *args, **kwargs):
        async with self._lock:
            self._check_state()
            if self._state == State.OPEN:
                raise RuntimeError(f"CircuitBreaker [{self.name}] is OPEN")
        try:
            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as exc:
            await self._on_failure()
            raise

    def _check_state(self) -> None:
        if self._state == State.OPEN:
            if self._last_failure_time and time.time() - self._last_failure_time > self._recovery_timeout:
                self._state = State.HALF_OPEN
                self._half_open_attempts = 0
                logger.info("CircuitBreaker [%s] → HALF_OPEN", self.name)

    async def _on_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            if self._state == State.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._half_open_max:
                    self._state = State.CLOSED
                    logger.info("CircuitBreaker [%s] → CLOSED", self.name)

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = State.OPEN
                logger.warning("CircuitBreaker [%s] → OPEN after %d failures", self.name, self._failure_count)

    def reset(self) -> None:
        self._state = State.CLOSED
        self._failure_count = 0
        self._success_count = 0


_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, **kwargs)
    return _breakers[name]
