from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.database.connection import close_db_client, get_db_client

__all__ = ["get_db_client", "close_db_client", "db"]

logger = logging.getLogger(__name__)

_DB_TIMEOUT = 30.0


class DatabaseWrapper:
    """
    Thin async wrapper around synchronous Supabase client.

    Safety guarantees:
    - delete() requires non-empty filters -> no accidental full-table wipe (G-1)
    - All calls have _DB_TIMEOUT timeout -> no silent hangs (G-4)
    - upsert() added for session_service and auth (G-2)
    - select() param renamed from 'select' to 'columns' (G-3)
    """

    async def _client(self):
        return await get_db_client()

    async def _run(self, fn):
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, fn),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("DB call timed out after %.0fs", _DB_TIMEOUT)
            raise

    async def select_many(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        columns: str = "*",
    ) -> List[Dict[str, Any]]:
        client = await self._client()

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
        filters: Optional[Dict[str, Any]] = None,
        columns: str = "*",
    ) -> Optional[Dict[str, Any]]:
        rows = await self.select_many(table, filters, limit=1, columns=columns)
        return rows[0] if rows else None

    async def select(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        columns: str = "*",
    ) -> List[Dict[str, Any]]:
        """Alias for select_many() - F-1 backward compat."""
        return await self.select_many(
            table, filters, order_by, order_desc, limit, offset, columns
        )

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
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("insert(%s) failed: %s", table, exc)
            raise

    async def insert_many(
        self,
        table: str,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        client = await self._client()

        def _q():
            return client.table(table).insert(rows).execute()

        try:
            result = await self._run(_q)
            return result.data or []
        except Exception as exc:
            logger.error("insert_many(%s) failed: %s", table, exc)
            raise

    async def update(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not filters:
            raise ValueError(
                f"db.update({table!r}): filters must not be empty"
            )
        client = await self._client()

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

    async def delete(
        self,
        table: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        # G-1 CRITICAL: empty filters would delete ALL rows
        if not filters:
            raise ValueError(
                f"db.delete({table!r}): filters must not be empty - "
                "refusing to delete entire table"
            )
        client = await self._client()

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

    async def upsert(
        self,
        table: str,
        data: Dict[str, Any],
        on_conflict: str = "id",
    ) -> Optional[Dict[str, Any]]:
        """G-2: missing upsert caused session_service crash."""
        client = await self._client()

        def _q():
            return (
                client.table(table)
                .upsert(data, on_conflict=on_conflict)
                .execute()
            )

        try:
            result = await self._run(_q)
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("upsert(%s) failed: %s", table, exc)
            raise

    async def count(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        client = await self._client()

        def _q():
            q = client.table(table).select("id", count="exact")
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            return q.execute()

        try:
            result = await self._run(_q)
            return result.count or 0
        except Exception as exc:
            logger.error("count(%s) failed: %s", table, exc)
            return 0


# Module-level singleton
db = DatabaseWrapper()
