"""
تست‌های CircuitBreaker
"""
from __future__ import annotations
import asyncio
import time
import pytest
from enum import Enum
from typing import Callable


# ─── Inline CircuitBreaker (mirror of backend/circuit_breaker.py) ────────────────────
class CBState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: float = 30.0, half_open_max: int = 1):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max
        self._state = CBState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_attempts = 0

    @property
    def state(self):
        return self._state

    def record_success(self):
        self._failure_count = 0
        self._half_open_attempts = 0
        self._state = CBState.CLOSED

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = CBState.OPEN

    def _check_recovery(self):
        if self._state == CBState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                self._state = CBState.HALF_OPEN
                self._half_open_attempts = 0

    def is_open(self) -> bool:
        self._check_recovery()
        return self._state == CBState.OPEN

    async def call(self, fn, *args, **kwargs):
        self._check_recovery()
        if self._state == CBState.OPEN:
            raise CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN")
        if self._state == CBState.HALF_OPEN:
            if self._half_open_attempts >= self._half_open_max:
                raise CircuitBreakerOpenError(f"Circuit '{self.name}' HALF_OPEN max reached")
            self._half_open_attempts += 1
        try:
            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure()
            raise


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestCircuitBreakerStates:

    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CBState.CLOSED
        assert cb.is_open() is False

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CBState.OPEN
        assert cb.is_open() is True

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CBState.CLOSED
        assert cb._failure_count == 0

    def test_below_threshold_stays_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CBState.CLOSED

    def test_half_open_after_recovery(self, monkeypatch):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.0)
        cb.record_failure()  # open
        assert cb.state == CBState.OPEN
        cb._check_recovery()
        assert cb.state == CBState.HALF_OPEN

    def test_half_open_to_closed_on_success(self, monkeypatch):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.0)
        cb.record_failure()
        cb._check_recovery()
        assert cb.state == CBState.HALF_OPEN
        cb.record_success()
        assert cb.state == CBState.CLOSED


class TestCircuitBreakerCall:

    @pytest.mark.asyncio
    async def test_successful_async_call(self):
        cb = CircuitBreaker("test")
        async def good():
            return 42
        result = await cb.call(good)
        assert result == 42
        assert cb.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_failed_async_call_increments(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        async def bad():
            raise ValueError("fail")
        with pytest.raises(ValueError):
            await cb.call(bad)
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_open_circuit_raises_immediately(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()  # open
        async def should_not_run():
            return "should not get here"
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(should_not_run)

    @pytest.mark.asyncio
    async def test_sync_call_works(self):
        cb = CircuitBreaker("test")
        def sync_fn():
            return "sync_result"
        result = await cb.call(sync_fn)
        assert result == "sync_result"

    @pytest.mark.asyncio
    async def test_multiple_failures_open_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        async def bad():
            raise RuntimeError("error")
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(bad)
        assert cb.is_open() is True
