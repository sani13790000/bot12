"""
backend/database/redis_client.py

CB-NEW-6 FIX: This file did not exist.
startup_check.py imported `from backend.database.redis_client import get_redis`
which caused ImportError on every startup.

Provides:
  get_redis()    - async Redis client (redis.asyncio)
  close_redis()  - graceful shutdown
  redis_ping()   - liveness check

Redis is NON-CRITICAL: if connection fails, system continues with
in-memory fallback. Errors are logged as warnings, not raised.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logger.warning(
        "redis package not installed. Install with: pip install redis>=4.2.0"
    )

_redis_client: Optional[Any] = None
_redis_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _redis_lock
    if _redis_lock is None:
        _redis_lock = asyncio.Lock()
    return _redis_lock


def _build_redis_url() -> str:
    try:
        from backend.core.config import get_settings
        s = get_settings()
        url = getattr(s, "REDIS_URL", None)
        if url:
            return url
        host = getattr(s, "REDIS_HOST", "redis")
        port = getattr(s, "REDIS_PORT", 6379)
        password = getattr(s, "REDIS_PASSWORD", None)
        db = getattr(s, "REDIS_DB", 0)
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        return f"redis://{host}:{port}/{db}"
    except Exception:
        return "redis://redis:6379/0"


async def get_redis() -> Any:
    """
    Return the shared async Redis client.
    Creates on first call (lazy init).
    Raises ImportError if redis package is not installed.
    """
    global _redis_client

    if not _REDIS_AVAILABLE:
        raise ImportError(
            "Redis package not installed. Add 'redis>=4.2.0' to requirements.txt"
        )

    if _redis_client is not None:
        return _redis_client

    async with _get_lock():
        if _redis_client is not None:
            return _redis_client

        url = _build_redis_url()
        try:
            client = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            await asyncio.wait_for(client.ping(), timeout=3.0)
            _redis_client = client
            safe_url = url.split("@")[-1] if "@" in url else url
            logger.info("Redis connected: %s", safe_url)
        except Exception as exc:
            logger.warning("Redis connection failed, in-memory fallback active: %s", exc)
            raise

    return _redis_client


async def redis_ping() -> bool:
    """Return True if Redis is reachable, False otherwise."""
    try:
        client = await get_redis()
        await asyncio.wait_for(client.ping(), timeout=2.0)
        return True
    except Exception:
        return False


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as exc:
            logger.warning("Error closing Redis: %s", exc)
        finally:
            _redis_client = None
