"""circuit_breaker.py - Hedge-Fund Grade Circuit Breaker v2 (HF-1)

HF-1: 5 failures within 60s -> OPEN (trading halted)
  - Sliding-window failure tracking
  - Per-service registry capped at 500
  - HALF_OPEN probe with success_threshold
  - Global trading-halt flag
  - Async-safe asyncio.Lock only
  - Prometheus snapshot() + CircuitOpenError
"""
from __future__ import annotations
import asyncio, logging, time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional
logger = logging.getLogger("circuit_breaker")
_MAX_REGISTRY_SIZE = 500
_HALF_OPEN_TIMEOUT_S = 120.0
_DEFAULT_WINDOW_S = 60.0
_DEFAULT_THRESHOLD = 5
_DEFAULT_RECOVERY_S = 30.0
_DEFAULT_HALF_OPEN_CALLS = 3
_DEFAULT_SUCCESS_THRESHOLD = 2


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerConfig:
    failure_threshold: int = _DEFAULT_THRESHOLD
    failure_window_s: float = _DEFAULT_WINDOW_S
    recovery_timeout_s: float = _DEFAULT_RECOVERY_S
    half_open_max_calls: int = _DEFAULT_HALF_OPEN_CALLS
    success_threshold: int = _DEFAULT_SUCCESS_THRESHOLD


@dataclass
class BreakerStats:
    state: BreakerState = BreakerState.CLOSED
    failure_times: Deque[float] = field(default_factory=deque)
    successes: int = 0
    half_open_calls: int = 0
    half_open_entered: Optional[float] = None
    opened_at: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    last_failure_reason: str = ""

    def windowed_failures(self, window_s: float) -> int:
        cutoff = time.monotonic() - window_s
        while self.failure_times and self.failure_times[0] < cutoff:
            self.failure_times.popleft()
        return len(self.failure_times)

    def record_failure(self, reason: str = "") -> None:
        self.failure_times.append(time.monotonic())
        self.total_failures += 1
        self.total_calls += 1
        self.last_failure_reason = reason

    def record_success(self) -> None:
        self.successes += 1
        self.total_calls += 1


_TRADING_HALTED = False
_HALT_REASON = ""
_HALT_LOCK = asyncio.Lock()


async def halt_trading(reason: str) -> None:
    global _TRADING_HALTED, _HALT_REASON
    async with _HALT_LOCK:
        _TRADING_HALTED = True
        _HALT_REASON = reason
    logger.critical("TRADING HALTED: %s", reason)


async def resume_trading(reason: str = "") -> None:
    global _TRADING_HALTED, _HALT_REASON
    async with _HALT_LOCK:
        _TRADING_HALTED = False
        _HALT_REASON = ""
    logger.warning("TRADING RESUMED: %s", reason)


def is_trading_halted() -> bool:
    return _TRADING_HALTED


def halt_reason() -> str:
    return _HALT_REASON


_REGISTRY: Dict[str, "CircuitBreaker"] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> "CircuitBreaker":
    """Get-or-create a named circuit breaker. LRU eviction at 500 entries."""
    async with _REGISTRY_LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
        if len(_REGISTRY) >= _MAX_REGISTRY_SIZE:
            oldest = next(iter(_REGISTRY))
            del _REGISTRY[oldest]
            logger.warning("CB registry evicted '%s' (cap=%d)", oldest, _MAX_REGISTRY_SIZE)
        cb = CircuitBreaker(name=name, config=config or BreakerConfig())
        _REGISTRY[name] = cb
        return cb


def get_all_breaker_stats() -> Dict[str, Dict[str, Any]]:
    return {name: cb.snapshot() for name, cb in _REGISTRY.items()}


class CircuitBreaker:
    """
    HF-1 Production Circuit Breaker.
    Usage:
        cb = await get_breaker('mt5')
        async with cb:
            result = await send_order(...)
    """

    def __init__(self, name: str, config: Optional[BreakerConfig] = None,
                 alert_callback: Optional[Callable] = None) -> None:
        self.name = name
        self.config = config or BreakerConfig()
        self._stats = BreakerStats()
        self._lock = asyncio.Lock()
        self._alert = alert_callback
        self._on_open: List[Callable] = []
        self._on_close: List[Callable] = []
        self._on_half_open: List[Callable] = []

    async def can_execute(self) -> bool:
        async with self._lock:
            return await self._check_state()

    async def record_success(self) -> None:
        async with self._lock:
            self._stats.record_success()
            if self._stats.state == BreakerState.HALF_OPEN:
                if self._stats.successes >= self.config.success_threshold:
                    await self._transition(BreakerState.CLOSED)

    async def record_failure(self, reason: str = "") -> None:
        async with self._lock:
            self._stats.record_failure(reason)
            state = self._stats.state
            if state == BreakerState.CLOSED:
                wf = self._stats.windowed_failures(self.config.failure_window_s)
                if wf >= self.config.failure_threshold:
                    await self._transition(BreakerState.OPEN)
            elif state == BreakerState.HALF_OPEN:
                await self._transition(BreakerState.OPEN)

    async def force_open(self, reason: str = "manual") -> None:
        async with self._lock:
            self._stats.last_failure_reason = reason
            self._stats.record_failure(reason)
            await self._transition(BreakerState.OPEN)

    async def force_close(self, reason: str = "manual") -> None:
        async with self._lock:
            await self._transition(BreakerState.CLOSED)

    def snapshot(self) -> Dict[str, Any]:
        s = self._stats
        return {
            "name": self.name,
            "state": s.state.value,
            "total_calls": s.total_calls,
            "total_failures": s.total_failures,
            "windowed_failures": s.windowed_failures(self.config.failure_window_s),
            "last_failure": s.last_failure_reason,
            "opened_at": s.opened_at,
            "config": {
                "threshold": self.config.failure_threshold,
                "window_s": self.config.failure_window_s,
                "recovery_s": self.config.recovery_timeout_s,
            },
        }

    def add_on_open(self, cb: Callable) -> None: self._on_open.append(cb)
    def add_on_close(self, cb: Callable) -> None: self._on_close.append(cb)
    def add_on_half_open(self, cb: Callable) -> None: self._on_half_open.append(cb)

    async def __aenter__(self) -> "CircuitBreaker":
        if not await self.can_execute():
            raise CircuitOpenError(self.name, self._stats.state, self._stats.last_failure_reason)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure(str(exc_val))
        return False

    async def _check_state(self) -> bool:
        state = self._stats.state
        now = time.monotonic()
        if state == BreakerState.CLOSED:
            return True
        if state == BreakerState.OPEN:
            opened = self._stats.opened_at or now
            if now - opened >= self.config.recovery_timeout_s:
                await self._transition(BreakerState.HALF_OPEN)
                return True
            return False
        if state == BreakerState.HALF_OPEN:
            entered = self._stats.half_open_entered or now
            if now - entered >= _HALF_OPEN_TIMEOUT_S:
                logger.warning("CB '%s': HALF_OPEN timeout", self.name)
                await self._transition(BreakerState.OPEN)
                return False
            if self._stats.half_open_calls >= self.config.half_open_max_calls:
                return False
            self._stats.half_open_calls += 1
            return True
        return True

    async def _transition(self, new_state: BreakerState) -> None:
        old_state = self._stats.state
        if old_state == new_state:
            return
        self._stats.state = new_state
        now = time.monotonic()
        if new_state == BreakerState.OPEN:
            self._stats.opened_at = now
            self._stats.successes = 0
            self._stats.half_open_calls = 0
            logger.critical("CB '%s': ->OPEN | reason=%s", self.name, self._stats.last_failure_reason)
            await halt_trading(f"circuit_breaker:{self.name}:{self._stats.last_failure_reason}")
            await self._fire_callbacks(self._on_open)
        elif new_state == BreakerState.HALF_OPEN:
            self._stats.half_open_entered = now
            self._stats.half_open_calls = 0
            self._stats.successes = 0
            logger.warning("CB '%s': ->HALF_OPEN", self.name)
            await self._fire_callbacks(self._on_half_open)
        elif new_state == BreakerState.CLOSED:
            self._stats.opened_at = None
            self._stats.half_open_entered = None
            self._stats.successes = 0
            self._stats.half_open_calls = 0
            logger.info("CB '%s': ->CLOSED", self.name)
            if is_trading_halted() and f"circuit_breaker:{self.name}" in halt_reason():
                await resume_trading(f"CB '{self.name}' recovered")
            await self._fire_callbacks(self._on_close)
        if self._alert:
            try:
                await self._alert(self.name, old_state.value, new_state.value, self._stats.last_failure_reason)
            except Exception as exc:
                logger.error("CB alert error: %s", exc)

    async def _fire_callbacks(self, cbs: List[Callable]) -> None:
        for cb in cbs:
            try:
                result = cb(self.name)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("CB callback error: %s", exc)


class CircuitOpenError(Exception):
    def __init__(self, name: str, state: BreakerState, reason: str = "") -> None:
        self.breaker_name = name
        self.state = state
        self.reason = reason
        super().__init__(f"Circuit '{name}' is {state.value}: {reason}")


_mt5_breaker: Optional[CircuitBreaker] = None


def get_mt5_breaker() -> CircuitBreaker:
    """Singleton MT5 breaker: 5 failures/60s window."""
    global _mt5_breaker
    if _mt5_breaker is None:
        _mt5_breaker = CircuitBreaker(
            name="mt5",
            config=BreakerConfig(
                failure_threshold=5,
                failure_window_s=60.0,
                recovery_timeout_s=30.0,
                half_open_max_calls=3,
                success_threshold=2,
            ),
        )
    return _mt5_breaker
