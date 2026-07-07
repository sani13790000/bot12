"""
backend/core/retry.py
Galaxy Vast AI Trading Platform — Enterprise Retry Mechanism

Features:
  - RetryConfig dataclass (frozen, shareable)
  - RetryStrategy: FIXED | EXPONENTIAL | LINEAR
  - Jitter: +-20% random noise on sleep
  - exception_filter: retry only on specific exception types
  - on_retry callback for metrics/alerts
  - async_retry / sync_retry decorators
  - Pre-defined configs: MT5_RETRY, DB_RETRY, RISK_RETRY
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional, Tuple, Type, TypeVar

logger = logging.getLogger("core.retry")
F = TypeVar("F", bound=Callable[..., Any])
CF = TypeVar("CF", bound=Callable[..., Coroutine[Any, Any, Any]])


class RetryStrategy(str, Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    jitter: bool = True
    reraise: bool = True
    retry_on: Tuple[Type[BaseException], ...] = field(default_factory=tuple)
    no_retry_on: Tuple[Type[BaseException], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts >= 1")
        if self.base_delay_s < 0:
            raise ValueError("base_delay_s >= 0")

    def sleep_for(self, attempt: int) -> float:
        if self.strategy is RetryStrategy.FIXED:
            d = self.base_delay_s
        elif self.strategy is RetryStrategy.EXPONENTIAL:
            d = self.base_delay_s * (2**attempt)
        else:
            d = self.base_delay_s * (attempt + 1)
        d = min(d, self.max_delay_s)
        if self.jitter:
            d *= random.uniform(0.8, 1.2)
        return max(0.0, d)

    def should_retry(self, exc: BaseException) -> bool:
        if self.no_retry_on and isinstance(exc, self.no_retry_on):
            return False
        if self.retry_on:
            return isinstance(exc, self.retry_on)
        return True


MT5_RETRY = RetryConfig(
    max_attempts=3,
    base_delay_s=0.5,
    max_delay_s=10.0,
    strategy=RetryStrategy.EXPONENTIAL,
    retry_on=(ConnectionError, TimeoutError, OSError),
)
DB_RETRY = RetryConfig(
    max_attempts=5, base_delay_s=0.2, max_delay_s=5.0, strategy=RetryStrategy.EXPONENTIAL
)
RISK_RETRY = RetryConfig(
    max_attempts=2, base_delay_s=0.1, max_delay_s=1.0, strategy=RetryStrategy.FIXED
)


async def with_retry_async(
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    config: RetryConfig = RetryConfig(),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    operation_name: str = "operation",
) -> Any:
    last_exc: Optional[BaseException] = None
    for attempt in range(config.max_attempts):
        try:
            return await coro_factory()
        except BaseException as exc:
            last_exc = exc
            if not config.should_retry(exc):
                logger.warning("[retry] %s: non-retryable %s", operation_name, type(exc).__name__)
                raise
            if attempt == config.max_attempts - 1:
                logger.error(
                    "[retry] %s: exhausted %d attempts: %s",
                    operation_name,
                    config.max_attempts,
                    exc,
                )
                break
            sleep_s = config.sleep_for(attempt)
            logger.warning(
                "[retry] %s: attempt %d/%d failed (%s) — retrying in %.2fs",
                operation_name,
                attempt + 1,
                config.max_attempts,
                exc,
                sleep_s,
            )
            if on_retry:
                try:
                    on_retry(attempt + 1, exc, sleep_s)
                except Exception as _cb_exc:  # noqa: H-5 — callback failure must not abort retry
                    logger.debug("[retry] on_retry callback error (non-fatal): %s", _cb_exc)
            await asyncio.sleep(sleep_s)
    if config.reraise and last_exc is not None:
        raise last_exc
    return None


def with_retry_sync(
    func: Callable[[], Any],
    config: RetryConfig = RetryConfig(),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    operation_name: str = "operation",
) -> Any:
    last_exc: Optional[BaseException] = None
    for attempt in range(config.max_attempts):
        try:
            return func()
        except BaseException as exc:
            last_exc = exc
            if not config.should_retry(exc):
                raise
            if attempt == config.max_attempts - 1:
                break
            sleep_s = config.sleep_for(attempt)
            if on_retry:
                try:
                    on_retry(attempt + 1, exc, sleep_s)
                except Exception as _cb_exc:  # noqa: H-5
                    logger.debug("[retry] on_retry callback error (non-fatal): %s", _cb_exc)
            time.sleep(sleep_s)
    if config.reraise and last_exc is not None:
        raise last_exc
    return None


def async_retry(
    config: RetryConfig = RetryConfig(),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> Callable[[CF], CF]:
    def decorator(fn: CF) -> CF:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_retry_async(
                lambda: fn(*args, **kwargs),
                config=config,
                on_retry=on_retry,
                operation_name=fn.__qualname__,
            )

        return wrapper  # type: ignore[return-value]

    return decorator


def sync_retry(
    config: RetryConfig = RetryConfig(),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return with_retry_sync(
                lambda: fn(*args, **kwargs),
                config=config,
                on_retry=on_retry,
                operation_name=fn.__qualname__,
            )

        return wrapper  # type: ignore[return-value]

    return decorator
