"""
backend/execution/order_state_machine_patch.py
Phase S - Order State Machine Hardening
S-17: SignalIdempotencyGuard duplicate order prevention
S-18: dispatch_callbacks_safe isolated callback execution
S-19: CompletedOrderEvictionIndex O(1) eviction
S-20: StateMachineMetrics hung order detection
"""
from __future__ import annotations
import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("execution.order_state_machine_patch")


class SignalIdempotencyGuard:
    """S-17: Prevents duplicate orders from same signal_id."""
    _TTL_S = 300

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def register(self, signal_id: str, order_id: str) -> bool:
        async with self._lock:
            self._purge_expired()
            if signal_id in self._seen:
                logger.warning("[Idempotency] Duplicate signal_id=%s blocked", signal_id)
                return False
            self._seen[signal_id] = time.monotonic()
            return True

    async def release(self, signal_id: str) -> None:
        async with self._lock:
            self._seen.pop(signal_id, None)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, ts in self._seen.items() if (now - ts) > self._TTL_S]
        for sid in expired:
            del self._seen[sid]


async def dispatch_callbacks_safe(callbacks: list, *args: Any) -> None:
    """S-18: Run all callbacks; isolate each one from exceptions."""
    for cb in callbacks:
        try:
            result = cb(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.error("[StateMachine] Callback %s error: %s", getattr(cb, "__name__", cb), exc)


class CompletedOrderEvictionIndex:
    """S-19: O(1) append eviction index for completed orders."""

    def __init__(self, ttl_hours: int = 24, cap: int = 10_000) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._cap = cap
        self._index: List[tuple] = []

    def add(self, order_id: str, completed_at: datetime) -> None:
        self._index.append((completed_at, order_id))

    def get_expired(self) -> List[str]:
        now = datetime.now(timezone.utc)
        return [oid for ts, oid in self._index if (now - ts) > self._ttl]

    def remove(self, order_ids: Set[str]) -> None:
        self._index = [(ts, oid) for ts, oid in self._index if oid not in order_ids]

    def is_over_cap(self, current_count: int) -> bool:
        return current_count >= self._cap


class StateMachineMetrics:
    """S-20: Transition counts + hung order detection."""

    def __init__(self) -> None:
        self._transition_counts: Dict[str, int] = defaultdict(int)
        self._active_count: int = 0
        self._hung_threshold_s: float = 120.0
        self._active_since: Dict[str, float] = {}

    def record_transition(self, from_state: str, to_state: str) -> None:
        self._transition_counts[f"{from_state}->{to_state}"] += 1

    def record_created(self, order_id: str) -> None:
        self._active_count += 1
        self._active_since[order_id] = time.monotonic()

    def record_terminal(self, order_id: str) -> None:
        self._active_count = max(0, self._active_count - 1)
        self._active_since.pop(order_id, None)

    def get_hung_orders(self) -> List[str]:
        now = time.monotonic()
        return [oid for oid, ts in self._active_since.items() if (now - ts) > self._hung_threshold_s]

    def snapshot(self) -> Dict[str, Any]:
        hung = self.get_hung_orders()
        return {
            "active_orders": self._active_count,
            "hung_orders": len(hung),
            "hung_order_ids": hung[:10],
            "transitions": dict(self._transition_counts),
        }


signal_idempotency_guard = SignalIdempotencyGuard()
state_machine_metrics    = StateMachineMetrics()
eviction_index           = CompletedOrderEvictionIndex()
