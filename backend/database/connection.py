"""Database connection — Supabase async client singleton with double-checked locking.

Fixes applied:
- asyncio.Lock for thread-safe singleton (race condition fix)
- double-checked locking pattern
- retry with exponential backoff on first connect
- clear error messages
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """Lazily create the lock inside the running event loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def get_db_client():
    """Return the Supabase client singleton.

    Thread-safe: uses asyncio.Lock with double-checked locking so only one
    coroutine ever calls create_client even under heavy concurrency.
    """
    global _client

    # Fast path — already initialised
    if _client is not None:
        return _client

    async with _get_lock():
        # Re-check inside the lock (another coroutine may have initialised it
        # while we were waiting)
        if _client is not None:
            return _client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set. "
                "Run: python3 startup_check.py to validate your .env file."
            )

        # Retry up to 3 times with exponential backoff
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                from supabase import create_client  # type: ignore[import]

                _client = create_client(url, key)
                logger.info("Supabase client initialised (attempt %d).", attempt + 1)
                return _client
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "Supabase connect attempt %d failed (%s) — retrying in %ds.",
                        attempt + 1, exc, wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Failed to connect to Supabase after 3 attempts: {last_exc}"
        ) from last_exc


async def close_db_client() -> None:
    """Tear down the client on application shutdown."""
    global _client
    _client = None
    logger.info("Supabase client closed.")
