"""Institutional Data Store — Supabase persistence with in-memory fallback.

Fixes applied:
- Added initialize() method (was exported in __init__.py but not defined)
- Added MAX_MEMORY_RECORDS cap to prevent OOM when Supabase is down
- Added retry logic (2 attempts) for transient HTTP failures
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum records kept per table in the in-memory fallback store
MAX_MEMORY_RECORDS = 10_000
# Retry attempts for Supabase HTTP calls
_MAX_RETRIES = 2


class InstitutionalDataStore:
    """Persist institutional analysis results to Supabase.

    Falls back to an in-memory dict when Supabase is unavailable so the
    rest of the system can continue operating.
    """

    def __init__(self) -> None:
        self._url: str = os.environ.get("SUPABASE_URL", "")
        self._key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._available: bool = bool(self._url and self._key)
        self._memory_store: Dict[str, List[Dict]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Test the Supabase connection during application startup."""
        if not self._available:
            logger.warning(
                "DataStore: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — "
                "using in-memory fallback only."
            )
            return

        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._url}/rest/v1/",
                    headers={"apikey": self._key},
                )
            if resp.status_code in (200, 404):
                logger.info("DataStore: Supabase connection OK.")
            else:
                logger.warning(
                    "DataStore: Supabase returned %s — switching to in-memory.",
                    resp.status_code,
                )
                self._available = False
        except Exception as exc:
            logger.warning("DataStore: Supabase ping failed (%s) — in-memory mode.", exc)
            self._available = False

    # ------------------------------------------------------------------
    # Public save helpers
    # ------------------------------------------------------------------

    async def save_backtest_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_backtests", result)

    async def save_trade(self, trade: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_trades", trade)

    async def save_monte_carlo_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_monte_carlo", result)

    async def save_wfo_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_wfo_results", result)

    async def save_replay_session(self, session: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_replay_sessions", session)

    async def get_recent_backtests(self, limit: int = 10) -> List[Dict]:
        return await self._fetch("institutional_backtests", limit)

    async def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        return await self._fetch("institutional_trades", limit)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upsert(
        self, table: str, record: Dict[str, Any]
    ) -> Optional[str]:
        record.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        if self._available:
            for attempt in range(_MAX_RETRIES):
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            f"{self._url}/rest/v1/{table}",
                            headers={
                                "apikey": self._key,
                                "Authorization": f"Bearer {self._key}",
                                "Content-Type": "application/json",
                                "Prefer": "return=representation",
                            },
                            json=record,
                        )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        if isinstance(data, list) and data:
                            return data[0].get("id")
                        return None
                    # Non-2xx: retry once then fall through to memory
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(0.5)
                except Exception as exc:
                    logger.warning("DataStore upsert attempt %d failed: %s", attempt + 1, exc)
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(0.5)

        # In-memory fallback
        bucket = self._memory_store.setdefault(table, [])
        bucket.append(record)
        # Enforce size cap to prevent OOM
        if len(bucket) > MAX_MEMORY_RECORDS:
            self._memory_store[table] = bucket[-MAX_MEMORY_RECORDS:]
        return None

    async def _fetch(self, table: str, limit: int) -> List[Dict]:
        if self._available:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{self._url}/rest/v1/{table}",
                        headers={
                            "apikey": self._key,
                            "Authorization": f"Bearer {self._key}",
                        },
                        params={"limit": limit, "order": "created_at.desc"},
                    )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as exc:
                logger.warning("DataStore fetch failed: %s", exc)

        return list(reversed(self._memory_store.get(table, [])[-limit:]))


# Module-level singleton
data_store = InstitutionalDataStore()
