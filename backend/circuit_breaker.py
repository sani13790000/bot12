from __future__ import annotations
import time, asyncio, logging
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from functools import wraps

logger = logging.getLogger('circuit_breaker')

class State(str, Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'

@dataclass
class BreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2

@dataclass
class BreakerStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state: State = State.CLOSED
    half_open_calls: int = 0
    total_calls: int = 0
    total_failures: int = 0

class CircuitBreaker:
    def __init__(self, name: str, config: Optional[BreakerConfig] = None) -> None:
        self.name = name
        self.config = config or BreakerConfig()
        self.stats = BreakerStats()
        self._lock = asyncio.Lock()
        self._cbs: list = []

    def on_state_change(self, cb) -> None:
        self._cbs.append(cb)

    async def _transition(self, new: State) -> None:
        old = self.stats.state
        if old != new:
            self.stats.state = new
            logger.warning(f'CircuitBreaker {self.name}: {old.value} -> {new.value}')
            for cb in self._cbs:
                try:
                    r = cb(old, new)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception as e:
                    logger.error(f'CB error: {e}')
        if new == State.HALF_OPEN:
            self.stats.half_open_calls = 0
            self.stats.successes = 0

    async def call(self, fn: Callable, *a, **kw) -> Any:
        async with self._lock:
            self.stats.total_calls += 1
            if self.stats.state == State.OPEN:
                elapsed = time.time() - (self.stats.last_failure_time or 0)
                if elapsed > self.config.recovery_timeout:
                    await self._transition(State.HALF_OPEN)
                else:
                    raise CircuitBreakerOpenError(self.name, int(self.config.recovery_timeout - elapsed))
            if self.stats.state == State.HALF_OPEN:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(self.name, int(self.config.recovery_timeout))
                self.stats.half_open_calls += 1
        try:
            result = await fn(*a, **kw)
            await self._ok()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception:
            await self._fail()
            raise

    async def _ok(self) -> None:
        async with self._lock:
            self.stats.last_success_time = time.time()
            self.stats.failures = 0
            if self.stats.state == State.HALF_OPEN:
                self.stats.successes += 1
                if self.stats.successes >= self.config.success_threshold:
                    await self._transition(State.CLOSED)

    async def _fail(self) -> None:
        async with self._lock:
            self.stats.failures += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.time()
            if self.stats.state in (State.OPEN, State.HALF_OPEN):
                await self._transition(State.OPEN)
            elif self.stats.failures >= self.config.failure_threshold:
                await self._transition(State.OPEN)

    def to_dict(self) -> dict:
        return {'name': self.name, 'state': self.stats.state.value,
                'failures': self.stats.failures, 'successes': self.stats.successes,
                'total_calls': self.stats.total_calls, 'total_failures': self.stats.total_failures,
                'last_failure_time': self.stats.last_failure_time,
                'last_success_time': self.stats.last_success_time}

class CircuitBreakerOpenError(Exception):
    def __init__(self, service: str, retry_after: int):
        self.service = service
        self.retry_after = retry_after
        super().__init__(f'CB {service} OPEN retry_after={retry_after}s')

_BREAKERS: Dict[str, CircuitBreaker] = {}

def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
    if name not in _BREAKERS:
        _BREAKERS[name] = CircuitBreaker(name, config)
    return _BREAKERS[name]

def circuit_breaker(service_name: str, config: Optional[BreakerConfig] = None):
    breaker = get_breaker(service_name, config)
    def decorator(func):
        @wraps(func)
        async def wrapper(*a, **kw):
            return await breaker.call(func, *a, **kw)
        return wrapper
    return decorator
