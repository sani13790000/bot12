"""
backend/database/connection_patch.py
Phase S - Database Connection Hardening
S-1: with_retry() exponential backoff
S-2: ConnectionHealth tracker
S-3: sync_in_thread() async wrapper
S-4: run_with_timeout() hard timeout
"""
from __future__ import annotations
import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("database.connection_patch")

RETRY_ATTEMPTS   = 3
RETRY_BASE_DELAY = 0.5
RETRY_MAX_DELAY  = 4.0
QUERY_TIMEOUT    = 10.0

RETRYABLE_MSGS = (
    "connection reset", "connection refused", "network",
    "timeout", "503", "502", "temporarily unavailable", "pool exhausted",
)

F = TypeVar("F", bound=Callable[..., Any])


def _is_retryable(exc: Exception) -> bool:
    return any(m in str(exc).lower() for m in RETRYABLE_MSGS)


def with_retry(fn: F) -> F:
    """S-1: Exponential-backoff retry for transient DB errors."""
    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == RETRY_ATTEMPTS:
                    raise
                delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
                logger.warning("[DB] Transient error attempt %d/%d (retry %.1fs): %s", attempt, RETRY_ATTEMPTS, delay, exc)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]
    return wrapper  # type: ignore[return-value]


async def run_with_timeout(coro: Any, timeout: float = QUERY_TIMEOUT) -> Any:
    """S-4: Hard timeout wrapper."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("[DB] Query exceeded timeout=%.1fs", timeout)
        raise


def sync_in_thread(fn: Callable[..., Any]) -> Callable[..., Any]:
    """S-3: Run blocking DB call in thread pool."""
    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)
    return wrapper


class ConnectionHealth:
    """S-2: Stale-connection detection."""
    _STALE_AFTER_S = 30.0

    def __init__(self) -> None:
        self._last_ok: float = 0.0
        self._healthy: bool = False

    def mark_ok(self) -> None:
        self._last_ok = time.monotonic()
        self._healthy = True

    def mark_failed(self) -> None:
        self._healthy = False

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self._last_ok) > self._STALE_AFTER_S

    @property
    def is_healthy(self) -> bool:
        return self._healthy and not self.is_stale

    async def probe(self, db_client: Any) -> bool:
        try:
            await run_with_timeout(
                asyncio.to_thread(lambda: db_client.table("system_health").select("id").limit(1).execute()),
                timeout=3.0,
            )
            self.mark_ok()
            return True
        except Exception as exc:
            self.mark_failed()
            logger.warning("[DB] Health probe failed: %s", exc)
            return False


connection_health = ConnectionHealth()
