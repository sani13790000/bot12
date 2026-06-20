"""
backend/database/__init__.py

FIX-1 (CRITICAL): Added DatabaseWrapper 'db' singleton.
  - trades.py, signals.py, audit_service.py all import from ...database import db
  - Previously only get_db_client was exported -> ImportError at module load
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.database.connection import close_db_client, get_db_client

__all__ = ["get_db_client", "close_db_client", "db"]

logger = logging.getLogger(__name__)


class DatabaseWrapper:
    """Thin async wrapper around Supabase client."""

    async def _client(self):
        return await get_db_client()

    async def _run(self, fn):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn)

    async def select_many(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        select: str = "*",
        use_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        client = await self._client()

        def _q():
            q = client.table(table).select(select)
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
            return []

    async def select_one(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        select: str = "*",
    ) -> Optional[Dict[str, Any]]:
        client = await self._client()

        def _q():
            q = client.table(table).select(select)
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            return q.maybe_single().execute()

        try:
            result = await self._run(_q)
            return result.data
        except Exception as exc:
            logger.error("select_one(%s) failed: %s", table, exc)
            return None

    async def insert(
        self,
        table: str,
        data: Dict[str, Any],
        use_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        client = await self._client()

        def _q():
            return client.table(table).insert(data).execute()

        try:
            result = await self._run(_q)
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.error("insert(%s) failed: %s", table, exc)
            return None

    async def update(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        client = await self._client()

        def _q():
            q = client.table(table)
            for k, v in filters.items():
                q = q.eq(k, v)
            return q.update(data).execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("update(%s) failed: %s", table, exc)
            return []

    async def delete(
        self,
        table: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        client = await self._client()

        def _q():
            q = client.table(table)
            for k, v in filters.items():
                q = q.eq(k, v)
            return q.delete().execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("delete(%s) failed: %s", table, exc)
            return []


db = DatabaseWrapper()
