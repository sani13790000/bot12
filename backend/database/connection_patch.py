"""
backend/database/connection_patch.py — Phase S
S-4a: Supabase client lazy init with 3x retry + timeout
S-4b: background DB health probe every 30s
S-4c: asyncio.Lock prevents concurrent init race
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("database.connection")

_DB_INIT_TIMEOUT_S   = 10.0
_DB_PROBE_INTERVAL_S = 30.0
_DB_MAX_RETRIES      = 3
_DB_RETRY_DELAY_S    = 2.0

_client          = None
_client_lock:    asyncio.Lock   = asyncio.Lock()
_health_task:    Optional[asyncio.Task] = None
_last_probe_ok:  float          = 0.0
_probe_failures: int            = 0


async def get_db_client_safe():
    """S-4a + S-4c: Lazy init with retry and async lock."""
    global _client
    if _client is not None:
        return _client

    async with _client_lock:
        if _client is not None:
            return _client

        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")

        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set."
            )

        for attempt in range(1, _DB_MAX_RETRIES + 1):
            try:
                logger.info("DB: init attempt %d/%d", attempt, _DB_MAX_RETRIES)
                client = await asyncio.wait_for(
                    asyncio.to_thread(_create_supabase_client, url, key),
                    timeout=_DB_INIT_TIMEOUT_S,
                )
                _client = client
                logger.info("DB: client initialized OK (attempt %d)", attempt)
                return _client
            except asyncio.TimeoutError:
                logger.error("DB: init timeout (attempt %d/%d)", attempt, _DB_MAX_RETRIES)
            except Exception as exc:
                logger.error("DB: init error (attempt %d/%d): %s", attempt, _DB_MAX_RETRIES, exc)
            if attempt < _DB_MAX_RETRIES:
                await asyncio.sleep(_DB_RETRY_DELAY_S * attempt)

        raise RuntimeError(
            f"Failed to initialize Supabase client after {_DB_MAX_RETRIES} attempts."
        )


def _create_supabase_client(url: str, key: str):
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        raise RuntimeError("supabase-py not installed")


async def _health_probe_loop() -> None:
    global _last_probe_ok, _probe_failures
    while True:
        await asyncio.sleep(_DB_PROBE_INTERVAL_S)
        try:
            client = await get_db_client_safe()
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: client.table("system_health").select("id").limit(1).execute()
                ),
                timeout=5.0,
            )
            _last_probe_ok  = time.monotonic()
            _probe_failures = 0
        except Exception as exc:
            _probe_failures += 1
            logger.warning("DB health probe FAIL #%d: %s", _probe_failures, exc)


async def start_db_health_probe() -> None:
    """S-4b: start background health probe."""
    global _health_task
    if _health_task is None or _health_task.done():
        _health_task = asyncio.create_task(
            _health_probe_loop(), name="db_health_probe"
        )


def get_db_health() -> dict:
    return {
        "last_probe_ok_s_ago": (
            round(time.monotonic() - _last_probe_ok, 1) if _last_probe_ok else None
        ),
        "consecutive_failures": _probe_failures,
        "healthy": _probe_failures == 0 and _last_probe_ok > 0,
    }
