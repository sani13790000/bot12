"""
backend/core/auth_hardening.py
Phase S - Auth Hardening
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._store: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self._window
        requests = self._store[key]
        self._store[key] = [t for t in requests if t > window_start]
        if len(self._store[key]) >= self._max:
            return False
        self._store[key].append(now)
        return True

    def reset(self, key: str) -> None:
        self._store.pop(key, None)


class TokenBlacklist:
    """JWT token blacklist."""

    def __init__(self) -> None:
        self._blacklist: Dict[str, float] = {}

    def add(self, jti: str, expires_at: float) -> None:
        self._blacklist[jti] = expires_at
        self.purge_expired()

    def is_blacklisted(self, jti: str) -> bool:
        if jti not in self._blacklist:
            return False
        if time.time() > self._blacklist[jti]:
            del self._blacklist[jti]
            return False
        return True

    def purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._blacklist.items() if v < now]
        for k in expired:
            del self._blacklist[k]


_rate_limiter = RateLimiter()
_token_blacklist = TokenBlacklist()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


def get_token_blacklist() -> TokenBlacklist:
    return _token_blacklist
