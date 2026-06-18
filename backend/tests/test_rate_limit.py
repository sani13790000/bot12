"""
تست‌های Rate Limiting
"""
from __future__ import annotations
import time
import pytest
from collections import defaultdict, deque
from typing import Dict, Deque


# ─── InMemoryRateLimiter (mirror of backend/middleware/rate_limit.py) ──────────────────
class InMemoryRateLimiter:
    """Sliding-window rate limiter (بدون Redis)."""

    def __init__(self):
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        dq = self._windows[key]
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    def remaining(self, key: str, limit: int, window: float) -> int:
        now = time.monotonic()
        dq = self._windows[key]
        recent = sum(1 for t in dq if t > now - window)
        return max(0, limit - recent)

    def reset(self, key: str):
        self._windows[key].clear()


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestInMemoryRateLimiter:

    def test_allows_within_limit(self):
        rl = InMemoryRateLimiter()
        for i in range(5):
            assert rl.is_allowed("user:1", limit=5, window=60.0) is True

    def test_blocks_at_limit(self):
        rl = InMemoryRateLimiter()
        for _ in range(5):
            rl.is_allowed("user:2", limit=5, window=60.0)
        assert rl.is_allowed("user:2", limit=5, window=60.0) is False

    def test_different_keys_independent(self):
        rl = InMemoryRateLimiter()
        for _ in range(5):
            rl.is_allowed("user:a", limit=5, window=60.0)
        # user:b هنوز block نشده
        assert rl.is_allowed("user:b", limit=5, window=60.0) is True

    def test_remaining_decrements(self):
        rl = InMemoryRateLimiter()
        assert rl.remaining("user:3", limit=5, window=60.0) == 5
        rl.is_allowed("user:3", limit=5, window=60.0)
        assert rl.remaining("user:3", limit=5, window=60.0) == 4

    def test_reset_clears_window(self):
        rl = InMemoryRateLimiter()
        for _ in range(5):
            rl.is_allowed("user:4", limit=5, window=60.0)
        assert rl.is_allowed("user:4", limit=5, window=60.0) is False
        rl.reset("user:4")
        assert rl.is_allowed("user:4", limit=5, window=60.0) is True

    def test_limit_1_allows_once(self):
        rl = InMemoryRateLimiter()
        assert rl.is_allowed("k", limit=1, window=60.0) is True
        assert rl.is_allowed("k", limit=1, window=60.0) is False

    def test_different_limits_per_key(self):
        rl = InMemoryRateLimiter()
        # auth endpoint: 5/min
        for _ in range(5):
            rl.is_allowed("ip:1:/auth", limit=5, window=60.0)
        assert rl.is_allowed("ip:1:/auth", limit=5, window=60.0) is False
        # signals endpoint: 30/min — هنوز block نشده
        for _ in range(10):
            assert rl.is_allowed("ip:1:/signals", limit=30, window=60.0) is True


class TestRateLimitEndpointRules:

    def test_auth_rule_5_per_minute(self):
        rl = InMemoryRateLimiter()
        key = "auth:ip"
        for i in range(5):
            assert rl.is_allowed(key, 5, 60.0) is True, f"Request {i+1} blocked early"
        assert rl.is_allowed(key, 5, 60.0) is False, "6th request should be blocked"

    def test_signals_rule_30_per_minute(self):
        rl = InMemoryRateLimiter()
        key = "signals:ip"
        for i in range(30):
            assert rl.is_allowed(key, 30, 60.0) is True, f"Request {i+1} blocked early"
        assert rl.is_allowed(key, 30, 60.0) is False

    def test_research_rule_5_per_minute(self):
        rl = InMemoryRateLimiter()
        key = "research:ip"
        for i in range(5):
            assert rl.is_allowed(key, 5, 60.0) is True
        assert rl.is_allowed(key, 5, 60.0) is False
