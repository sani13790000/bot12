from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("circuit_breaker")


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerConfig:
    failure_threshold:   int   = 5
    recovery_timeout:    float = 30.0
    half_open_max_calls: int   = 3
    success_threshold:   int   = 2


@dataclass
class BreakerStats:
    failures:          int             = 0
    successes:         int             = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state:             State           = State.CLOSED
    half_open_calls:   int             = 0
    total_calls:       int             = 0
    total_failures:    int             = 0


class CircuitBreaker:
    """
    Async circuit breaker - DEADLOCK-FREE.

    FIX (F-5 DEADLOCK): Previously call() held _lock then called _ok()/_fail()
    which also tried to acquire _lock -> asyncio.Lock is NOT reentrant -> deadlock.

    Fix: _transition_locked() is lock-free (called only while lock is held).
         call() releases lock BEFORE fn() runs.
         _on_success() and _on_failure() acquire lock independently.
    """

    def __init__(self, name: str, config: Optional[BreakerConfig] = None) -> None:
        self.name   = name
        self.config = config or BreakerConfig()
        self.stats  = BreakerStats()
        self._lock  = asyncio.Lock()
        self._cbs: list = []

    def on_state_change(self, cb: Callable) -> None:
        self._cbs.append(cb)

    async def open(self, reason: str = "") -> None:
        async with self._lock:
            await self._transition_locked(State.OPEN)
        logger.warning("CircuitBreaker %s force-opened: %s", self.name, reason)

    async def close(self, reason: str = "") -> None:
        async with self._lock:
            self.stats.failures  = 0
            self.stats.successes = 0
            await self._transition_locked(State.CLOSED)
        logger.info("CircuitBreaker %s force-closed: %s", self.name, reason)

    async def call(self, fn: Callable, *a: Any, **kw: Any) -> Any:
        # Lock only for state check -- released BEFORE fn() runs
        async with self._lock:
            self.stats.total_calls += 1
            if self.stats.state == State.OPEN:
                elapsed = time.time() - (self.stats.last_failure_time or 0)
                if elapsed > self.config.recovery_timeout:
                    await self._transition_locked(State.HALF_OPEN)
                else:
                    raise CircuitBreakerOpenError(
                        self.name, int(self.config.recovery_timeout - elapsed)
                    )
            if self.stats.state == State.HALF_OPEN:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(self.name, int(self.config.recovery_timeout))
                self.stats.half_open_calls += 1
        # Lock released -- fn() runs without holding lock
        try:
            result = await fn(*a, **kw)
            await self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        async with self._lock:
            self.stats.last_success_time = time.time()
            self.stats.failures          = 0
            if self.stats.state == State.HALF_OPEN:
                self.stats.successes += 1
                if self.stats.successes >= self.config.success_threshold:
                    await self._transition_locked(State.CLOSED)

    async def _on_failure(self) -> None:
        async with self._lock:
            self.stats.failures       += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.time()
            if self.stats.state in (State.OPEN, State.HALF_OPEN):
                await self._transition_locked(State.OPEN)
            elif self.stats.failures >= self.config.failure_threshold:
                await self._transition_locked(State.OPEN)

    async def _transition_locked(self, new: State) -> None:
        """Lock-free transition -- MUST be called while self._lock is held."""
        old = self.stats.state
        if old == new:
            return
        self.stats.state = new
        if new == State.HALF_OPEN:
            self.stats.half_open_calls = 0
            self.stats.successes       = 0
        logger.warning("CircuitBreaker %s: %s -> %s", self.name, old.value, new.value)
        for cb in self._cbs:
            try:
                r = cb(old, new)
                if asyncio.iscoroutine(r):
                    await r
            except Exception as exc:
                logger.error("CB callback error: %s", exc)

    def to_dict(self) -> dict:
        return {
            "name":              self.name,
            "state":             self.stats.state.value,
            "failures":          self.stats.failures,
            "successes":         self.stats.successes,
            "total_calls":       self.stats.total_calls,
            "total_failures":    self.stats.total_failures,
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time,
        }


class CircuitBreakerOpenError(Exception):
    def __init__(self, service: str, retry_after: int) -> None:
        self.service     = service
        self.retry_after = retry_after
        super().__init__(f"CB {service} OPEN retry_after={retry_after}s")


class CircuitBreakerManager:
    """Thread-safe registry of all circuit breakers."""

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def get(self, name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        elif config is not None:
            logger.debug("get(%s): config ignored, breaker already exists.", name)
        return self._breakers[name]

    async def get_async(self, name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
        async with self._lock:
            return self.get(name, config)

    def all_status(self) -> Dict[str, dict]:
        return {name: cb.to_dict() for name, cb in self._breakers.items()}

    def open_count(self) -> int:
        return sum(1 for cb in self._breakers.values() if cb.stats.state == State.OPEN)


circuit_breaker_manager = CircuitBreakerManager()
_BREAKERS: Dict[str, CircuitBreaker] = circuit_breaker_manager._breakers


def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
    return circuit_breaker_manager.get(name, config)


def circuit_breaker(service_name: str, config: Optional[BreakerConfig] = None):
    breaker = get_breaker(service_name, config)
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*a: Any, **kw: Any) -> Any:
            return await breaker.call(func, *a, **kw)
        return wrapper
    return decorator
