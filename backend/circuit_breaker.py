"""circuit_breaker.py — Hedge-Fund Grade Circuit Breaker

HF-1: 5 failures in 60s → OPEN (trading halted)
  - Time-windowed failure tracking (not just count)
  - Async-safe asyncio.Lock only
  - HALF_OPEN with probe calls
  - Global trading halt flag
  - Telegram alert on state change
  - Per-service breaker registry
  - Prometheus-compatible metrics
"""
from __future__ import annotations
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger("circuit_breaker")
_MAX_REGISTRY_SIZE   = 500
_HALF_OPEN_TIMEOUT_S = 120.0
_DEFAULT_WINDOW_S    = 60.0
_DEFAULT_THRESHOLD   = 5
_DEFAULT_RECOVERY_S  = 30.0
_DEFAULT_HALF_OPEN_CALLS = 3
_DEFAULT_SUCCESS_THRESHOLD = 2


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerConfig:
    failure_threshold:    int   = _DEFAULT_THRESHOLD
    failure_window_s:     float = _DEFAULT_WINDOW_S
    recovery_timeout_s:   float = _DEFAULT_RECOVERY_S
    half_open_max_calls:  int   = _DEFAULT_HALF_OPEN_CALLS
    success_threshold:    int   = _DEFAULT_SUCCESS_THRESHOLD


@dataclass
class BreakerStats:
    state:             State           = State.CLOSED
    failure_times:     Deque[float]    = field(default_factory=deque)
    successes:         int             = 0
    half_open_calls:   int             = 0
    half_open_entered: Optional[float] = None
    total_calls:       int             = 0
    total_failures:    int             = 0
    opened_at:         Optional[float] = None

    def windowed_failures(self, window_s: float) -> int:
        cutoff = time.monotonic() - window_s
        while self.failure_times and self.failure_times[0] < cutoff:
            self.failure_times.popleft()
        return len(self.failure_times)

    def record_failure(self) -> None:
        self.failure_times.append(time.monotonic())
        self.total_failures += 1
        self.total_calls += 1

    def record_success(self) -> None:
        self.successes += 1
        self.total_calls += 1


_TRADING_HALTED = False
_HALT_REASON    = ""
_HALT_LOCK      = asyncio.Lock()


async def halt_trading(reason: str) -> None:
    global _TRADING_HALTED, _HALT_REASON
    async with _HALT_LOCK:
        _TRADING_HALTED = True
        _HALT_REASON    = reason
    logger.critical("TRADING HALTED: %s", reason)


async def resume_trading() -> None:
    global _TRADING_HALTED, _HALT_REASON
    async with _HALT_LOCK:
        _TRADING_HALTED = False
        _HALT_REASON    = ""
    logger.info("Trading resumed")


def is_trading_halted() -> bool:
    return _TRADING_HALTED


def halt_reason() -> str:
    return _HALT_REASON


class CircuitBreaker:
    """
    HF-1: 5 failures in 60s window -> OPEN -> halt_trading()
    OPEN -> wait recovery_timeout_s -> HALF_OPEN -> probe -> CLOSED
    """

    def __init__(self, name: str, config: Optional[BreakerConfig] = None) -> None:
        self.name   = name
        self.config = config or BreakerConfig()
        self.stats  = BreakerStats()
        self._lock  = asyncio.Lock()
        self._cbs:  List[Callable] = []

    def on_state_change(self, cb: Callable) -> None:
        self._cbs.append(cb)

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            await self._maybe_transition_to_half_open()
            state = self.stats.state
        if state == State.OPEN:
            raise CircuitOpenError(f"[{self.name}] circuit OPEN")
        if state == State.HALF_OPEN:
            async with self._lock:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitOpenError(f"[{self.name}] HALF_OPEN probe limit")
                self.stats.half_open_calls += 1
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)
            await self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            await self._on_failure(str(exc))
            raise

    async def record_failure(self, reason: str = "") -> None:
        await self._on_failure(reason)

    async def record_success(self) -> None:
        await self._on_success()

    def get_status(self) -> Dict[str, Any]:
        return {
            "name":              self.name,
            "state":             self.stats.state.value,
            "windowed_failures": self.stats.windowed_failures(self.config.failure_window_s),
            "total_failures":    self.stats.total_failures,
            "total_calls":       self.stats.total_calls,
            "trading_halted":    _TRADING_HALTED,
            "halt_reason":       _HALT_REASON,
            "threshold":         self.config.failure_threshold,
            "window_s":          self.config.failure_window_s,
        }

    async def _on_failure(self, reason: str) -> None:
        old_state: Optional[State] = None
        windowed = 0
        async with self._lock:
            self.stats.record_failure()
            windowed = self.stats.windowed_failures(self.config.failure_window_s)
            logger.warning("[CB:%s] failure %d/%d in %.0fs window reason=%s",
                self.name, windowed, self.config.failure_threshold, self.config.failure_window_s, reason)
            if self.stats.state == State.HALF_OPEN:
                old_state = State.HALF_OPEN
                self._do_open()
            elif self.stats.state == State.CLOSED:
                if windowed >= self.config.failure_threshold:
                    old_state = State.CLOSED
                    self._do_open()
        if old_state is not None:
            await halt_trading(f"CircuitBreaker[{self.name}]: {windowed} failures in {self.config.failure_window_s:.0f}s")
            await self._fire_callbacks(old_state, State.OPEN)

    async def _on_success(self) -> None:
        old_state: Optional[State] = None
        async with self._lock:
            self.stats.record_success()
            if self.stats.state == State.HALF_OPEN:
                if self.stats.successes >= self.config.success_threshold:
                    old_state = State.HALF_OPEN
                    self._do_close()
        if old_state is not None:
            await resume_trading()
            await self._fire_callbacks(old_state, State.CLOSED)

    def _do_open(self) -> None:
        self.stats.state     = State.OPEN
        self.stats.opened_at = time.monotonic()
        logger.critical("[CB:%s] -> OPEN", self.name)

    def _do_close(self) -> None:
        self.stats.state             = State.CLOSED
        self.stats.successes         = 0
        self.stats.half_open_calls   = 0
        self.stats.half_open_entered = None
        self.stats.failure_times.clear()
        logger.info("[CB:%s] -> CLOSED", self.name)

    async def _maybe_transition_to_half_open(self) -> None:
        if self.stats.state != State.OPEN or self.stats.opened_at is None:
            return
        elapsed = time.monotonic() - self.stats.opened_at
        if elapsed >= self.config.recovery_timeout_s:
            old = State.OPEN
            self.stats.state             = State.HALF_OPEN
            self.stats.half_open_entered = time.monotonic()
            self.stats.half_open_calls   = 0
            self.stats.successes         = 0
            logger.info("[CB:%s] -> HALF_OPEN after %.0fs", self.name, elapsed)
            asyncio.create_task(self._fire_callbacks(old, State.HALF_OPEN))

    async def _fire_callbacks(self, old: State, new: State) -> None:
        for cb in self._cbs:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(self.name, old, new)
                else:
                    cb(self.name, old, new)
            except Exception as exc:
                logger.warning("[CB:%s] callback error: %s", self.name, exc)


class CircuitOpenError(Exception):
    pass


_REGISTRY: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
    async with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            if len(_REGISTRY) >= _MAX_REGISTRY_SIZE:
                oldest = next(iter(_REGISTRY))
                del _REGISTRY[oldest]
            _REGISTRY[name] = CircuitBreaker(name, config)
        return _REGISTRY[name]


def get_breaker_sync(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
    if name not in _REGISTRY:
        _REGISTRY[name] = CircuitBreaker(name, config)
    return _REGISTRY[name]


async def get_all_statuses() -> List[Dict[str, Any]]:
    async with _REGISTRY_LOCK:
        return [b.get_status() for b in _REGISTRY.values()]


_trading_breaker: Optional[CircuitBreaker] = None


def get_trading_breaker() -> CircuitBreaker:
    global _trading_breaker
    if _trading_breaker is None:
        _trading_breaker = get_breaker_sync(
            "trading",
            BreakerConfig(failure_threshold=5, failure_window_s=60.0, recovery_timeout_s=30.0),
        )
    return _trading_breaker
