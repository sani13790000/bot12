"""
backend/database/redis_client.py
Galaxy Vast AI Trading Platform

FIXES APPLIED:
  BUG-R4-1: init_redis() function added — main.py imports it in lifespan()
  BUG-R4-7: _build_redis_url() now uses REDIS_URL_WITH_AUTH (password injected)
             instead of bare REDIS_URL — fixes NOAUTH error
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_redis_client: Optional[object] = None


def _build_redis_url() -> str:
    """
    BUG-R4-7 FIX: Use REDIS_URL_WITH_AUTH (password injected) not bare REDIS_URL.
    Previously returned settings.REDIS_URL which has NO password => NOAUTH error.
    """
    try:
        from backend.core.config import get_settings

        s = get_settings()
        # BUG-R4-7 FIX: REDIS_URL_WITH_AUTH injects password automatically
        url = getattr(s, "REDIS_URL_WITH_AUTH", None)
        if url:
            return url
        url = getattr(s, "REDIS_URL", None)
        if url:
            return url
    except Exception:
        pass
    return "redis://localhost:6379/0"


async def get_redis():
    """
    Lazy-init async Redis client (singleton).
    Returns connected client or None if Redis unavailable.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis

        url = _build_redis_url()
        client = aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await client.ping()
        _redis_client = client
        log_url = url.split("@")[-1] if "@" in url else url
        logger.info("[Redis] connected: %s", log_url)
        return _redis_client
    except ImportError:
        logger.warning("[Redis] redis package not installed -- cache disabled")
        return None
    except Exception as exc:
        logger.error("[Redis] connection failed: %s", exc)
        return None


async def init_redis():
    """
    BUG-R4-1 FIX: main.py calls init_redis() in lifespan().
    Previously AttributeError because this function did not exist.
    Returns the connected client (or None on failure).
    """
    client = await get_redis()
    if client:
        logger.info("[Redis] initialized successfully")
    else:
        logger.warning("[Redis] init failed -- cache will be unavailable")
    return client


async def redis_ping() -> bool:
    """Return True if Redis is reachable."""
    try:
        client = await get_redis()
        if client is None:
            return False
        await client.ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        logger.info("[Redis] connection closed")
