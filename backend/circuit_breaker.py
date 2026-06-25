"""circuit_breaker.py - Hedge-Fund Grade Circuit Breaker v2 (HF-1)

HF-1: 5 failure states tracked per window
HF-2: HALF_OPEN probing with configurable call limit
HF-3: async context manager (__aenter__/__aexit__)
HF-4: global HALT flag (halt_trading / resume_trading)
HF-5: per-instance callback hooks (on_open/on_close/on_half_open)
C-3 FIX: callback dedup + remove_on_* methods to prevent memory leak
CONFLICT-FIX-1: lazy asyncio.Lock init (no module-level event-loop dependency)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("circuit_breaker")

# ── Lazy global lock helpers ──────────────────────────────────────────────────
_HALT_LOCK: Optional[asyncio.Lock] = None
_REGISTRY_LOCK: Optional[asyncio.Lock] = None


def _get_halt_lock() -> asyncio.Lock:
    global _HALT_LOCK
    if _HALT_LOCK is None:
        _HALT_LOCK = asyncio.Lock()
    return _HALT_LOCK


def _get_registry_lock() -> asyncio.Lock:
    global _REGISTRY_LOCK
    if _REGISTRY_LOCK is None:
        _REGISTRY_LOCK = asyncio.Lock()
    return _REGISTRY_LOCK


# ── Global halt flag ──────────────────────────────────────────────────────────
_HALT: bool = False
_REGISTRY: Dict[str, "CircuitBreaker"] = {}


async def halt_trading(reason: str = "") -> None:
    global _HALT
    async with _get_halt_lock():
        _HALT = True
    logger.critical("[CB] TRADING HALTED — %s", reason)


async def resume_trading(reason: str = "") -> None:
    global _HALT
    async with _get_halt_lock():
        _HALT = False
    logger.info("[CB] Trading resumed — %s", reason)


def is_halted() -> bool:
    return _HALT


async def get_breaker(name: str, config: Optional["BreakerConfig"] = None) -> "CircuitBreaker":
    async with _get_registry_lock():
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, config)
        return _REGISTRY[name]


async def get_all_breakers() -> Dict[str, "CircuitBreaker"]:
    async with _get_registry_lock():
        return dict(_REGISTRY)


# ── Models ────────────────────────────────────────────────────────────────────
class BreakerState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    def __init__(self, name: str, state: BreakerState, reason: str = "") -> None:
        self.name   = name
        self.state  = state
        self.reason = reason
        super().__init__(f"Circuit '{name}' is {state.value}: {reason}")


@dataclass
class BreakerConfig:
    failure_threshold:    int   = 5
    failure_window_s:     float = 60.0
    recovery_timeout_s:   float = 30.0
    success_threshold:    int   = 2
    half_open_max_calls:  int   = 3
    timeout_s:            float = 0.0   # 0 = no per-call timeout


@dataclass
class BreakerStats:
    state:               BreakerState = BreakerState.CLOSED
    failure_times:       List[float]  = field(default_factory=list)
    successes:           int          = 0
    half_open_calls:     int          = 0
    opened_at:           Optional[float] = None
    half_open_entered:   Optional[float] = None
    last_failure_reason: str             = ""

    def record_success(self) -> None:
        if self.state == BreakerState.CLOSED:
            self.failure_times.clear()
        self.successes += 1

    def record_failure(self, reason: str = "", window_s: float = 60.0) -> None:
        now = time.monotonic()
        self.failure_times = [t for t in self.failure_times if now - t < window_s]
        self.failure_times.append(now)
        self.last_failure_reason = reason
        self.successes = 0

    def failure_count(self, window_s: float = 60.0) -> int:
        now = time.monotonic()
        return sum(1 for t in self.failure_times if now - t < window_s)


# ── CircuitBreaker ────────────────────────────────────────────────────────────
class CircuitBreaker:
    """Async circuit breaker with CLOSED → OPEN → HALF_OPEN FSM."""

    def __init__(self, name: str, config: Optional[BreakerConfig] = None,
                 alert_callback: Optional[Callable] = None) -> None:
        self.name   = name
        self.config = config or BreakerConfig()
        self._stats = BreakerStats()
        self._lock  = asyncio.Lock()
        self._alert = alert_callback
        self._on_open:      List[Callable] = []
        self._on_close:     List[Callable] = []
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
            self._stats.record_failure(reason, self.config.failure_window_s)
            if self._stats.state != BreakerState.OPEN:
                count = self._stats.failure_count(self.config.failure_window_s)
                if count >= self.config.failure_threshold:
                    self._stats.last_failure_reason = reason
                    await self._transition(BreakerState.OPEN)

    async def _check_state(self) -> bool:
        now = time.monotonic()
        state = self._stats.state
        if state == BreakerState.CLOSED:
            return True
        if state == BreakerState.OPEN:
            if (self._stats.opened_at is not None
                    and now - self._stats.opened_at >= self.config.recovery_timeout_s):
                await self._transition(BreakerState.HALF_OPEN)
                return True
            return False
        # HALF_OPEN
        if self._stats.half_open_calls >= self.config.half_open_max_calls:
            return False
        self._stats.half_open_calls += 1
        return True

    async def _transition(self, new_state: BreakerState) -> None:
        now = time.monotonic()
        old = self._stats.state
        self._stats.state = new_state
        if new_state == BreakerState.OPEN:
            self._stats.opened_at        = now
            self._stats.successes        = 0
            self._stats.half_open_calls  = 0
            logger.error("[CB:%s] OPEN — %s", self.name, self._stats.last_failure_reason)
            await self._fire_callbacks(self._on_open)
        elif new_state == BreakerState.HALF_OPEN:
            self._stats.half_open_entered = now
            self._stats.half_open_calls   = 0
            self._stats.successes         = 0
            logger.warning("[CB:%s] HALF_OPEN", self.name)
            await self._fire_callbacks(self._on_half_open)
        elif new_state == BreakerState.CLOSED:
            self._stats.opened_at         = None
            self._stats.half_open_entered = None
            self._stats.successes         = 0
            self._stats.half_open_calls   = 0
            logger.info("[CB:%s] CLOSED (recovered)", self.name)
            await self._fire_callbacks(self._on_close)
        if self._alert:
            try:
                await self._alert(self.name, old, new_state)
            except Exception as exc:
                logger.debug("[CB:%s] alert callback error: %s", self.name, exc)

    async def _fire_callbacks(self, cbs: List[Callable]) -> None:
        for cb in list(cbs):
            try:
                result = cb(self.name)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.debug("[CB:%s] callback error: %s", self.name, exc)

    def status(self) -> Dict[str, Any]:
        return {
            "name":    self.name,
            "state":   self._stats.state.value,
            "failures": self._stats.failure_count(self.config.failure_window_s),
            "last_failure_reason": self._stats.last_failure_reason,
            "config": {
                "threshold": self.config.failure_threshold,
                "window_s":  self.config.failure_window_s,
                "recovery_s": self.config.recovery_timeout_s,
            },
        }

    # ── Callback registration (C-3 FIX: dedup + remove) ──────────────────────
    def add_on_open(self, cb: Callable) -> None:
        """Register callback for OPEN transition. Dedup to prevent memory leak."""
        if cb not in self._on_open:
            self._on_open.append(cb)

    def add_on_close(self, cb: Callable) -> None:
        """Register callback for CLOSED transition. Dedup to prevent memory leak."""
        if cb not in self._on_close:
            self._on_close.append(cb)

    def add_on_half_open(self, cb: Callable) -> None:
        """Register callback for HALF_OPEN transition. Dedup to prevent memory leak."""
        if cb not in self._on_half_open:
            self._on_half_open.append(cb)

    def remove_on_open(self, cb: Callable) -> None:
        """Unregister open callback. Call on component teardown."""
        self._on_open = [x for x in self._on_open if x is not cb]

    def remove_on_close(self, cb: Callable) -> None:
        """Unregister close callback. Call on component teardown."""
        self._on_close = [x for x in self._on_close if x is not cb]

    def remove_on_half_open(self, cb: Callable) -> None:
        """Unregister half-open callback. Call on component teardown."""
        self._on_half_open = [x for x in self._on_half_open if x is not cb]

    # ── Context manager ───────────────────────────────────────────────────────
    async def __aenter__(self) -> "CircuitBreaker":
        if not await self.can_execute():
            raise CircuitOpenError(self.name, self._stats.state, self._stats.last_failure_reason)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure(reason=str(exc_val) if exc_val else type(exc_type).__name__)
