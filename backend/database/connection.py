"""Supabase async database connection — thread-safe singleton.

Uses asyncio.Lock (double-checked locking) to prevent race conditions
when multiple coroutines call get_db_client() concurrently on startup.
"""
from __future__ import annotations

import logging
import os
import asyncio
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_lock: asyncio.Lock = asyncio.Lock()


async def get_db_client() -> Any:
    """Return the shared Supabase client, initialising on first call.

    Uses asyncio.Lock with double-checked locking to prevent race conditions
    when multiple coroutines call this function concurrently.

    Raises
    ------
    RuntimeError
        If the required environment variables are missing or the client
        cannot be created.
    """
    global _client
    # Fast path: already initialised (no lock needed)
    if _client is not None:
        return _client

    # Slow path: acquire lock and double-check
    async with _lock:
        if _client is not None:  # another coroutine already initialised
            return _client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
                "before the database client can be initialised."
            )

        try:
            from supabase import create_client  # type: ignore

            _client = create_client(url, key)
            logger.info("Supabase client initialised successfully.")
            return _client
        except Exception as exc:
            raise RuntimeError(f"Failed to create Supabase client: {exc}") from exc


def reset_client() -> None:
    """Reset the singleton (for testing only)."""
    global _client
    _client = None
