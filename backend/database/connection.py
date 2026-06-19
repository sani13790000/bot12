"""
backend/database/connection.py — FIXED
Issues fixed:
1. Blocking supabase .execute() in async context → wrapped in run_in_executor
2. Health probe blocks event loop every 30s under load
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
_HEALTH_TTL = 30.0   # re-probe after 30 s


def _probe_sync(client: Client) -> None:
    """Blocking health probe — must be called via run_in_executor."""
    client.table("signals").select("id").limit(1).execute()


async def _probe(client: Client) -> None:
    """Non-blocking wrapper around the synchronous Supabase probe."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _probe_sync, client)


async def get_db_client() -> Client:
    """Return the shared Supabase client (singleton, thread-safe)."""
    global _client, _last_healthy  # noqa: PLW0603

    # Fast path: healthy client exists and within TTL
    if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
        return _client

    async with _lock:
        # Double-checked locking after acquiring lock
        if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
            return _client

        if _client is None:
            _client = await _create_client_with_retry()
        else:
            # Health probe — non-blocking
            try:
                await asyncio.wait_for(_probe(_client), timeout=5.0)
                _last_healthy = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                logger.warning("DB health probe failed, reconnecting: %s", exc)
                _client = await _create_client_with_retry()

    return _client


async def _create_client_with_retry(max_attempts: int = 3) -> Client:
    """Create Supabase client with exponential-backoff retry."""
    global _last_healthy  # noqa: PLW0603
    last_exc: Optional[Exception] = None
    loop = asyncio.get_running_loop()

    for attempt in range(1, max_attempts + 1):
        try:
            # create_client is synchronous — offload to executor
            client: Client = await loop.run_in_executor(
                None,
                lambda: create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY),
            )
            # Lightweight probe — also synchronous
            await asyncio.wait_for(_probe(client), timeout=5.0)
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

    assert last_exc is not None
    raise RuntimeError(
        f"DB: Supabase unreachable after {max_attempts} attempts: {last_exc}"
    ) from last_exc


async def close_db_client() -> None:
    """Release the DB client (called on shutdown)."""
    global _client  # noqa: PLW0603
    _client = None
    logger.info("DB: client released")
