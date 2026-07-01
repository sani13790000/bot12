"""circuit_breaker.py - Hedge-Fund Grade Circuit Breaker."""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

_LOG = logging.getLogger(__name__)


class State(str, Enum):
    CLOSED = 'CLOSED'
    OPEN = 'OPEN'
    HALF_OPEN = 'HALF_OPEN'


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(
        self,
        name: str = 'default',
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._success_count = 0
        self._total_calls = 0

    @property
    def state(self) -> State:
        if self._state == State.OPEN:
            if self._last_failure_time and time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = State.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def is_open(self) -> bool:
        return self.state == State.OPEN

    def is_closed(self) -> bool:
        return self.state == State.CLOSED

    def is_half_open(self) -> bool:
        return self.state == State.HALF_OPEN

    def call_succeeded(self) -> None:
        self._success_count += 1
        self._failure_count = 0
        if self._state == State.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self._half_open_max_calls:
                self._state = State.CLOSED
                _LOG.info('CircuitBreaker[%s] closed after recovery', self.name)

    def call_failed(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == State.HALF_OPEN or self._failure_count >= self._failure_threshold:
            self._state = State.OPEN
            _LOG.warning(
                'CircuitBreaker[%s] opened after %d failures',
                self.name,
                self._failure_count,
            )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        if self.is_open():
            raise RuntimeError(f'CircuitBreaker[{self.name}] is OPEN')
        self._total_calls += 1
        try:
            result = await func(*args, **kwargs)
            self.call_succeeded()
            return result
        except Exception:
            self.call_failed()
            raise

    def reset(self) -> None:
        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def stats(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self._failure_count,
            'success_count': self._success_count,
            'total_calls': self._total_calls,
        }


_registry: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str = 'default', **kwargs: Any) -> CircuitBreaker:
    if name not in _registry:
        _registry[name] = CircuitBreaker(name=name, **kwargs)
    return _registry[name]
