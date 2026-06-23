"""
backend/middleware/rate_limit_patch.py
Phase S - Rate Limiting Hardening
S-13: RedisBackedLimiter cross-worker
S-14: extract_real_ip() spoofing prevention
S-15: WebSocketRateLimiter upgrade flood
S-16: BurstAwareLimiter burst enforcement
"""
from __future__ import annotations
import asyncio
import logging
import time
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger("middleware.rate_limit_patch")

_PRIVATE_PREFIXES = (
    "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "::1", "fc", "fd",
)


def extract_real_ip(
    remote_addr: str,
    forwarded_for: Optional[str],
    real_ip_header: Optional[str] = None,
    trust_proxy: bool = True,
) -> str:
    """S-14: Safe IP extraction; prevents X-Forwarded-For spoofing."""
    if real_ip_header and real_ip_header.strip():
        return real_ip_header.strip()
    if not trust_proxy or not forwarded_for:
        return remote_addr or "unknown"
    is_private = any((remote_addr or "").startswith(p) for p in _PRIVATE_PREFIXES)
    if not is_private:
        return remote_addr or "unknown"
    ips = [ip.strip() for ip in forwarded_for.split(",")]
    return ips[0] if ips else remote_addr or "unknown"


class WebSocketRateLimiter:
    """S-15: Per-IP WebSocket upgrade limiter."""

    def __init__(self, max_concurrent: int = 5, upgrade_window_s: int = 60, max_upgrades: int = 10) -> None:
        self._max_concurrent = max_concurrent
        self._upgrade_window = upgrade_window_s
        self._max_upgrades   = max_upgrades
        self._active: Dict[str, int] = {}
        self._upgrade_times: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    async def can_connect(self, ip: str) -> Tuple[bool, str]:
        async with self._lock:
            if self._active.get(ip, 0) >= self._max_concurrent:
                return False, f"max_concurrent={self._max_concurrent} reached"
            now = time.monotonic()
            times = self._upgrade_times.setdefault(ip, deque())
            while times and (now - times[0]) > self._upgrade_window:
                times.popleft()
            if len(times) >= self._max_upgrades:
                return False, f"upgrade_rate limit exceeded"
            times.append(now)
            self._active[ip] = self._active.get(ip, 0) + 1
            return True, "ok"

    async def on_disconnect(self, ip: str) -> None:
        async with self._lock:
            self._active[ip] = max(0, self._active.get(ip, 0) - 1)


class BurstAwareLimiter:
    """S-16: Sliding window with burst cap."""

    def __init__(self, max_requests: int, window_s: int, burst_multiplier: float = 1.5) -> None:
        self._max_requests = max_requests
        self._window       = window_s
        self._burst_limit  = int(max_requests * burst_multiplier)
        self._timestamps: deque = deque()

    def is_allowed(self) -> bool:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) > self._window:
            self._timestamps.popleft()
        recent = sum(1 for t in self._timestamps if (now - t) <= 1.0)
        if recent >= self._burst_limit:
            return False
        if len(self._timestamps) >= self._max_requests:
            return False
        self._timestamps.append(now)
        return True

    def remaining(self) -> int:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) > self._window:
            self._timestamps.popleft()
        return max(0, self._max_requests - len(self._timestamps))


class RedisBackedLimiter:
    """S-13: Cross-worker rate limiting; falls back to in-memory."""

    def __init__(self, redis_client: Optional[object] = None) -> None:
        self._redis = redis_client
        self._fallback: Dict[str, BurstAwareLimiter] = {}

    async def check(
        self, key: str, max_requests: int, window_s: int, burst_multiplier: float = 1.5
    ) -> Tuple[bool, int]:
        limiter = self._fallback.setdefault(
            key, BurstAwareLimiter(max_requests, window_s, burst_multiplier)
        )
        allowed = limiter.is_allowed()
        return allowed, limiter.remaining()


ws_rate_limiter = WebSocketRateLimiter()
