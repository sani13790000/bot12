from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

from supabase import Client, create_client

from backend.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[Client] = None
_lock = asyncio.Lock()
_last_healthy: float = 0.0
_HEALTH_TTL = 10.0


def _probe_sync(client: Client) -> None:
    client.table("signals").select("id").limit(1).execute()


async def _probe(client: Client) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _probe_sync, client)


def _create_client_sync() -> Client:
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
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


get_supabase_client = get_db_client


def get_supabase_client_sync() -> Optional[Client]:
    """Sync getter for legacy callers. DO NOT use in async context."""
    return _client


async def close_db_client() -> None:
    """Graceful shutdown - call from app lifespan."""
    global _client, _last_healthy
    if _client is not None:
        logger.info("DB client closed.")
        _client = None
        _last_healthy = 0.0


class DatabaseWrapper:
    """Async wrapper around synchronous Supabase client."""

    _TIMEOUT = 30.0

    async def _raw(self) -> Client:
        return await get_db_client()

    async def _run(self, fn):
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, fn),
                timeout=self._TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("DB call timed out after %.0fs", self._TIMEOUT)
            raise

    async def select_many(
        self,
        table: str,
        filters: Optional[dict] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        columns: str = "*",
    ) -> list:
        client = await self._raw()

        def _q():
            q = client.table(table).select(columns)
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            if order_by:
                q = q.order(order_by, desc=order_desc)
            q = q.range(offset, offset + limit - 1)
            return q.execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("select_many(%s) failed: %s", table, exc)
            raise

    async def select_one(
        self,
        table: str,
        filters: Optional[dict] = None,
        columns: str = "*",
    ) -> Optional[dict]:
        rows = await self.select_many(table, filters, limit=1, columns=columns)
        return rows[0] if rows else None

    async def select(
        self,
        table: str,
        filters: Optional[dict] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        columns: str = "*",
    ) -> list:
        """Alias for select_many() - backward compatibility."""
        return await self.select_many(
            table, filters, order_by, order_desc, limit, offset, columns
        )

    async def insert(self, table: str, data: dict, use_admin: bool = False) -> Optional[dict]:
        client = await self._raw()

        def _q():
            return client.table(table).insert(data).execute()

        try:
            result = await self._run(_q)
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("insert(%s) failed: %s", table, exc)
            raise

    async def update(self, table: str, filters: dict, data: dict) -> list:
        if not filters:
            raise ValueError("update() requires at least one filter")
        client = await self._raw()

        def _q():
            q = client.table(table).update(data)
            for k, v in filters.items():
                q = q.eq(k, v)
            return q.execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("update(%s) failed: %s", table, exc)
            raise

    async def upsert(self, table: str, data: dict, on_conflict: str = "id") -> Optional[dict]:
        client = await self._raw()

        def _q():
            return client.table(table).upsert(data, on_conflict=on_conflict).execute()

        try:
            result = await self._run(_q)
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("upsert(%s) failed: %s", table, exc)
            raise

    async def delete(self, table: str, filters: dict) -> list:
        if not filters:
            raise ValueError("delete() requires at least one filter")
        client = await self._raw()

        def _q():
            q = client.table(table).delete()
            for k, v in filters.items():
                q = q.eq(k, v)
            return q.execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("delete(%s) failed: %s", table, exc)
            raise

    async def health_check(self) -> dict:
        try:
            client = await asyncio.wait_for(get_db_client(), timeout=5.0)
            await asyncio.wait_for(_probe(client), timeout=5.0)
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}


db = DatabaseWrapper()


async def get_db() -> AsyncGenerator:
    """
    FastAPI dependency injection helper - THIS WAS THE MISSING PIECE (E-1).

    Usage in routes:
        from backend.database.connection import get_db

        @router.get("/")
        async def handler(db = Depends(get_db)):
            rows = await db.select("table", {"key": "value"})
    """
    yield db


__all__ = [
    "get_db_client",
    "get_supabase_client",
    "get_supabase_client_sync",
    "close_db_client",
    "DatabaseWrapper",
    "db",
    "get_db",
]
