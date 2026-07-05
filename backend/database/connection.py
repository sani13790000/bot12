from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from supabase import Client, create_client

from backend.core.config import get_settings as _get_settings

logger = logging.getLogger(__name__)

_client: Optional[Client] = None

# CB-NEW-7 FIX: asyncio.Lock() at module level causes RuntimeError in Python 3.12+
# when imported outside an async context. With --workers 2 each process has its
# own lock providing no cross-process safety. Solution: lazy init inside the
# running event loop using double-checked pattern.
_lock: Optional[asyncio.Lock] = None

_last_healthy: float = 0.0
_HEALTH_TTL = 30.0


def _get_lock() -> asyncio.Lock:
    """Lazy-init the asyncio.Lock inside the running event loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _probe_sync(client: Client) -> None:
    client.table("signals").select("id").limit(1).execute()


async def _probe(client: Client) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _probe_sync, client)


def _create_client_sync() -> Client:
    return create_client(
        _get_settings().SUPABASE_URL,
        _get_settings().SUPABASE_SERVICE_KEY,
    )


async def _create_client_with_retry() -> Client:
    global _last_healthy
    for attempt, delay in enumerate([1, 2, 4], start=1):
        try:
            client = await asyncio.get_running_loop().run_in_executor(
                None, _create_client_sync
            )
            await asyncio.wait_for(_probe(client), timeout=5.0)
            _last_healthy = time.monotonic()
            logger.info("DB client connected (attempt %d)", attempt)
            return client
        except Exception as exc:
            logger.warning("DB connect attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(delay)
    raise RuntimeError("Could not connect to Supabase after 3 attempts")


async def get_db_client() -> Client:
    """Primary async getter - use in all async contexts."""
    global _client, _last_healthy

    # Fast path
    if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
        return _client

    # Slow path with lazy-init lock (CB-NEW-7 FIX)
    async with _get_lock():
        if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
            return _client
        if _client is None:
            _client = await _create_client_with_retry()
        else:
            try:
                await asyncio.wait_for(_probe(_client), timeout=5.0)
                _last_healthy = time.monotonic()
            except Exception as exc:
                logger.warning("DB health probe failed, reconnecting: %s", exc)
                _client = await _create_client_with_retry()
        return _client


get_supabase_client = get_db_client


def get_supabase_client_sync() -> Optional[Client]:
    """Sync getter for legacy callers. DO NOT use in async context."""
    return _client
