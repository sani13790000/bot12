"""Retry policies for Galaxy Vast AI Trading Platform.

Provides:
- Exponential backoff with jitter
- Per-service configurable policies
- tenacity-based decorators
- Async-safe
"""
from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core retry logic
# ---------------------------------------------------------------------------
async def retry_async(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff: float = 2.0,
    jitter: float = 0.2,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff + jitter.

    Args:
        func: async callable to retry
        max_attempts: total attempts (including first)
        base_delay: initial wait in seconds
        max_delay: cap on wait time
        backoff: multiplier per attempt
        jitter: random fraction to add (avoids thundering herd)
        retryable_exceptions: only retry on these
        on_retry: callback(attempt, exc) on each retry
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay * (backoff ** (attempt - 1)), max_delay)
            delay += random.uniform(0, jitter * delay)  # jitter
            logger.warning(
                "[retry] %s failed (attempt %d/%d): %s. Retrying in %.2fs ...",
                getattr(func, "__name__", str(func)),
                attempt,
                max_attempts,
                exc,
                delay,
            )
            if on_retry:
                on_retry(attempt, exc)
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Decorator factories
# ---------------------------------------------------------------------------
def with_retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator: add retry policy to an async function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(
                func,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff=backoff,
                retryable_exceptions=retryable_exceptions,
                **kwargs,
            )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Pre-built policies
# ---------------------------------------------------------------------------

# DB operations: 3 attempts, start at 1s
db_retry = with_retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    backoff=2.0,
)

# External HTTP calls: 3 attempts, start at 0.5s
http_retry = with_retry(
    max_attempts=3,
    base_delay=0.5,
    max_delay=15.0,
    backoff=2.0,
)

# Redis: 2 attempts fast
redis_retry = with_retry(
    max_attempts=2,
    base_delay=0.1,
    max_delay=1.0,
    backoff=2.0,
)

# Critical business logic: 5 attempts
critical_retry = with_retry(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    backoff=2.0,
)
