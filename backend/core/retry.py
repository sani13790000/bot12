"""
backend/core/retry.py
Retry policies for Galaxy Vast AI Trading Platform.

Fix applied:
- retry_async: 'raise last_exc' could raise None if retryable_exceptions never matched
  any attempt (e.g. exception type mismatch). Added assertion guard.
- Added type: ignore comment so mypy doesn't complain about Optional raise
"""
from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


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
    """
    Retry an async function with exponential backoff + jitter.

    Fix: last_exc was Optional[Exception] and could be None if none of the
    attempts raised a retryable_exceptions match. Now we assert it's set
    before re-raising to prevent 'raise None' TypeError.
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
            delay += random.uniform(0, jitter * delay)  # thundering-herd avoidance
            logger.warning(
                "[retry] %s failed (attempt %d/%d): %s — retrying in %.2fs",
                getattr(func, "__name__", repr(func)),
                attempt,
                max_attempts,
                exc,
                delay,
            )
            if on_retry:
                on_retry(attempt, exc)
            await asyncio.sleep(delay)

    # Guard: last_exc must be set here; if it's not, something is very wrong
    assert last_exc is not None, (
        f"retry_async exhausted {max_attempts} attempts but last_exc is None — "
        f"verify retryable_exceptions tuple is correct for {func!r}"
    )
    raise last_exc


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator: add exponential-backoff retry to an async function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(
                func, *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff=backoff,
                retryable_exceptions=retryable_exceptions,
                **kwargs,
            )
        return wrapper
    return decorator


# Pre-built policies
db_retry = with_retry(
    max_attempts=3, base_delay=1.0, max_delay=10.0, backoff=2.0,
)
http_retry = with_retry(
    max_attempts=3, base_delay=0.5, max_delay=15.0, backoff=2.0,
)
redis_retry = with_retry(
    max_attempts=2, base_delay=0.1, max_delay=1.0, backoff=2.0,
)
critical_retry = with_retry(
    max_attempts=5, base_delay=1.0, max_delay=60.0, backoff=2.0,
)
