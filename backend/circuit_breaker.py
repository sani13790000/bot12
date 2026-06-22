"""circuit_breaker.py -- Phase P Fix P-12a/b/c/d."""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("circuit_breaker")
_MAX_REGISTRY_SIZE = 500
_HALF_OPEN_TIMEOUT_S = 120.0

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
    half_open_entered: Optional[float] = None
    total_calls:       int             = 0
    total_failures:    int             = 0

class CircuitBreaker:
    """Async circuit breaker -- fully asyncio-safe. FIX P-12a: asyncio.Lock only."""

    def __init__(self, name: str, config: Optional[BreakerConfig] = None) -> None:
        self.name   = name
        self.config = config or BreakerConfig()
        self.stats  = BreakerStats()
        self._lock  = asyncio.Lock()  # FIX P-12a: was threading.Lock in some paths
        self._cbs: List[Callable] = []

    def on_state_change(self, cb: Callable) -> None:
        self._cbs.append(cb)

    async def _fire_callbacks(self, old: State, new: State) -> None:
        """FIX P-12d: callbacks in try/except -- never crash the breaker."""
        for cb in self._cbs:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(self.name, old, new)
                else:
                    cb(self.name, old, new)
            except Exception as exc:
                logger.warning("[CB:%s] callback raised: %s", self.name, exc)

    async def open(self, reason: str = "") -> None:
        async with self._lock:
            old = self.stats.state
            self.stats.state = State.OPEN
            self.stats.last_failure_time = time.monotonic()
            logger.warning("[CB:%s] OPEN -- %s", self.name, reason)
        await self._fire_callbacks(old, State.OPEN)

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            state = self.stats.state
            now = time.monotonic()
            if state == State.HALF_OPEN:
                entered = self.stats.half_open_entered or now
                if now - entered > _HALF_OPEN_TIMEOUT_S:
                    logger.warning("[CB:%s] HALF_OPEN timeout, reset to CLOSED", self.name)
                    self._transition_locked(State.CLOSED)
                    state = State.CLOSED
            if state == State.OPEN:
                elapsed = now - (self.stats.last_failure_time or 0)
                if elapsed >= self.config.recovery_timeout:
                    self._transition_locked(State.HALF_OPEN)
                    state = State.HALF_OPEN
                else:
                    raise RuntimeError(
                        f"CircuitBreaker '{self.name}' is OPEN "
                        f"(retry in {self.config.recovery_timeout - elapsed:.1f}s)"
                    )
            if state == State.HALF_OPEN:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    raise RuntimeError(f"CircuitBreaker '{self.name}' HALF_OPEN max calls")
                self.stats.half_open_calls += 1
            self.stats.total_calls += 1
        # FIX: lock released BEFORE fn() -- no deadlock
        try:
            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) \
                     else fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    def _transition_locked(self, new_state: State) -> None:
        self.stats.state = new_state
        if new_state == State.HALF_OPEN:
            self.stats.half_open_calls = 0
            self.stats.half_open_entered = time.monotonic()
        elif new_state == State.CLOSED:
            self.stats.failures = 0
            self.stats.successes = 0
            self.stats.half_open_entered = None

    async def _on_success(self) -> None:
        old = new = None
        async with self._lock:
            self.stats.successes += 1
            self.stats.last_success_time = time.monotonic()
            if (self.stats.state == State.HALF_OPEN
                    and self.stats.successes >= self.config.success_threshold):
                old = State.HALF_OPEN
                self._transition_locked(State.CLOSED)
                new = State.CLOSED
                logger.info("[CB:%s] CLOSED after recovery", self.name)
        if old and new:
            await self._fire_callbacks(old, new)

    async def _on_failure(self) -> None:
        old = new = None
        async with self._lock:
            self.stats.failures += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.monotonic()
            if self.stats.state == State.HALF_OPEN:
                old = State.HALF_OPEN
                self._transition_locked(State.OPEN)
                new = State.OPEN
            elif (self.stats.state == State.CLOSED
                  and self.stats.failures >= self.config.failure_threshold):
                old = State.CLOSED
                self._transition_locked(State.OPEN)
                new = State.OPEN
                logger.warning("[CB:%s] OPEN -- threshold reached", self.name)
        if old and new:
            await self._fire_callbacks(old, new)

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name, "state": self.stats.state.value,
            "failures": self.stats.failures, "successes": self.stats.successes,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "half_open_calls": self.stats.half_open_calls,
        }

_registry: Dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()

async def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
    """FIX P-12b: registry capped at _MAX_REGISTRY_SIZE."""
    async with _registry_lock:
        if name not in _registry:
            if len(_registry) >= _MAX_REGISTRY_SIZE:
                oldest = next(iter(_registry))
                del _registry[oldest]
                logger.warning("[CB] registry full, evicted '%s'", oldest)
            _registry[name] = CircuitBreaker(name, config)
        return _registry[name]

def get_all_statuses() -> Dict[str, Dict[str, Any]]:
    return {n: cb.get_status() for n, cb in _registry.items()}
