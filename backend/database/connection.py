"""
Supabase client singleton with asyncio.Lock, exponential-backoff retry,
and lightweight health probe.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from supabase import Client, create_client

from backend.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[Client] = None
_lock = asyncio.Lock()
_last_healthy: float = 0.0
_HEALTH_TTL = 30.0   # re-probe after 30s


async def get_db_client() -> Client:
    """Return the shared Supabase client (singleton, thread-safe)."""
    global _client, _last_healthy  # noqa: PLW0603

    # Fast path: healthy client exists
    if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
        return _client

    async with _lock:
        # Double-checked locking
        if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
            return _client

        if _client is None:
            _client = await _create_client_with_retry()
        else:
            # Health probe
            try:
                _client.table("signals").select("id").limit(1).execute()
                _last_healthy = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                logger.warning("DB health probe failed, reconnecting: %s", exc)
                _client = await _create_client_with_retry()

    return _client


async def _create_client_with_retry(
    max_attempts: int = 3,
) -> Client:
    """Create Supabase client with exponential-backoff retry."""
    global _last_healthy  # noqa: PLW0603
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY,
            )
            # Lightweight probe
            client.table("signals").select("id").limit(1).execute()
            _last_healthy = time.monotonic()
            logger.info("DB: Supabase connected (attempt %d)", attempt)
            return client
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            delay = 2 ** (attempt - 1)  # 1s, 2s, 4s
            logger.warning(
                "DB: connection attempt %d/%d failed: %s (retry in %ds)",
                attempt, max_attempts, exc, delay,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
    raise RuntimeError(
        f"DB: Supabase unreachable after {max_attempts} attempts: {last_exc}"
    )


async def close_db_client() -> None:
    """Close the DB client (called on shutdown)."""
    global _client  # noqa: PLW0603
    _client = None
    logger.info("DB: client released")
