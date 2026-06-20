"""
backend/database/connection.py

FIX-2 (CRITICAL): Added get_supabase_client alias.
  - rbac_service.py imports get_supabase_client which did not exist
  - Now aliased to get_db_client
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
_HEALTH_TTL = 30.0


def _probe_sync(client: Client) -> None:
    client.table("signals").select("id").limit(1).execute()


async def _probe(client: Client) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _probe_sync, client)


def _create_client_sync() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def _create_client_with_retry() -> Client:
    global _last_healthy
    for attempt, delay in enumerate([1, 2, 4], start=1):
        try:
            client = await asyncio.get_running_loop().run_in_executor(None, _create_client_sync)
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
    global _client, _last_healthy

    if _client is not None and (time.monotonic() - _last_healthy) < _HEALTH_TTL:
        return _client

    async with _lock:
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


# FIX-2: alias for rbac_service.py and other legacy imports
get_supabase_client = get_db_client


async def close_db_client() -> None:
    global _client
    if _client is not None:
        logger.info("DB client closed.")
        _client = None
