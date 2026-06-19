"""Institutional data store — Supabase persistence with in-memory fallback.

Fixes applied:
- MEDIUM: httpx.AsyncClient singleton (connection pooling, not new client per call)
- LOW: time.gmtime() replaced with datetime.now(UTC) for correct UTC timestamps
- HIGH: MAX_MEMORY_RECORDS enforced to prevent OOM when Supabase is down
- MEDIUM: retry with asyncio.sleep(0.5) on transient failures
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
MAX_MEMORY_RECORDS = 10_000

# ---------------------------------------------------------------------------
# httpx singleton — one AsyncClient for the lifetime of the process
# ---------------------------------------------------------------------------
_http_client: Optional[Any] = None
_http_lock = asyncio.Lock()


async def _get_http_client():
    """Return a shared httpx.AsyncClient (created lazily, never closed)."""
    global _http_client
    if _http_client is None or getattr(_http_client, "is_closed", False):
        async with _http_lock:
            if _http_client is None or getattr(_http_client, "is_closed", False):
                import httpx
                _http_client = httpx.AsyncClient(
                    timeout=10.0,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
    return _http_client


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string (replaces time.gmtime())."""
    return datetime.now(timezone.utc).isoformat()


class InstitutionalDataStore:
    """Supabase-backed data store with in-memory fallback."""

    def __init__(self) -> None:
        import os
        self._url: str = os.environ.get("SUPABASE_URL", "")
        self._key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._available: bool = bool(self._url and self._key)
        self._memory_store: Dict[str, List[Dict]] = {}

    async def initialize(self) -> None:
        """Verify Supabase connectivity; disable if unreachable."""
        if not self._available:
            logger.warning("DataStore: Supabase credentials missing — using in-memory only")
            return
        try:
            client = await _get_http_client()
            resp = await client.get(
                f"{self._url}/rest/v1/",
                headers={"apikey": self._key, "Authorization": f"Bearer {self._key}"},
                timeout=5.0,
            )
            if resp.status_code not in (200, 404):
                logger.warning("DataStore: Supabase ping returned %s — falling back to memory", resp.status_code)
                self._available = False
            else:
                logger.info("DataStore: Supabase connection verified (status=%s)", resp.status_code)
        except Exception as exc:
            logger.warning("DataStore: Supabase unreachable — in-memory mode: %s", exc)
            self._available = False

    async def _upsert(self, table: str, record: Dict[str, Any]) -> Optional[str]:
        """Write to Supabase with retry; fall back to memory on failure."""
        if self._available:
            for attempt in range(_MAX_RETRIES):
                try:
                    client = await _get_http_client()
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
                client = await _get_http_client()
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

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def save_backtest_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_backtests", {
            **result,
            "created_at": _utc_now_iso(),
        })

    async def save_trade(self, trade: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_trades", {
            **trade,
            "created_at": _utc_now_iso(),
        })

    async def save_monte_carlo_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_monte_carlo", {
            **result,
            "created_at": _utc_now_iso(),
        })

    async def save_wfo_result(self, result: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_wfo_results", {
            **result,
            "created_at": _utc_now_iso(),
        })

    async def save_replay_session(self, session: Dict[str, Any]) -> Optional[str]:
        return await self._upsert("institutional_replay_sessions", {
            **session,
            "created_at": _utc_now_iso(),
        })

    async def get_backtest_results(self, limit: int = 50) -> List[Dict]:
        return await self._fetch("institutional_backtests", limit)

    async def get_trades(self, limit: int = 100) -> List[Dict]:
        return await self._fetch("institutional_trades", limit)

    async def get_monte_carlo_results(self, limit: int = 20) -> List[Dict]:
        return await self._fetch("institutional_monte_carlo", limit)

    async def get_wfo_results(self, limit: int = 20) -> List[Dict]:
        return await self._fetch("institutional_wfo_results", limit)

    async def get_replay_sessions(self, limit: int = 20) -> List[Dict]:
        return await self._fetch("institutional_replay_sessions", limit)

    def memory_stats(self) -> Dict[str, int]:
        """Return memory store record counts per table."""
        return {k: len(v) for k, v in self._memory_store.items()}


# Module-level singleton
data_store = InstitutionalDataStore()
