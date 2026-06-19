"""
Institutional data store — Supabase-backed with in-memory fallback.

Performance improvements in this version:
  * Singleton httpx.AsyncClient with connection pool + keep-alive
  * Batch write: collect up to BATCH_SIZE records then flush in ONE request
  * Background flush task every FLUSH_INTERVAL_SECONDS
  * _utc_now_iso uses datetime.now(timezone.utc) — no deprecated gmtime()
  * MAX_MEMORY_RECORDS caps in-memory lists to avoid unbounded growth
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────
MAX_MEMORY_RECORDS = 10_000
BATCH_SIZE = 100          # flush after this many queued writes
FLUSH_INTERVAL_SECONDS = 5.0
_RETRY_ATTEMPTS = 2
_RETRY_DELAY = 0.5


# ── HTTP client singleton ──────────────────────────────
_http_client: Optional[httpx.AsyncClient] = None
_http_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    """Return (or create) a shared AsyncClient with connection pool."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        async with _http_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    base_url=settings.SUPABASE_URL,
                    headers={
                        "apikey": settings.SUPABASE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                        keepalive_expiry=30,
                    ),
                    http2=True,
                )
    return _http_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── DataStore ──────────────────────────────────────────
class DataStore:
    """Institutional data store with Supabase backend and memory fallback."""

    def __init__(self) -> None:
        # In-memory stores — all capped with deque
        self._signals: deque[Dict[str, Any]] = deque(maxlen=MAX_MEMORY_RECORDS)
        self._decisions: deque[Dict[str, Any]] = deque(maxlen=MAX_MEMORY_RECORDS)
        self._trades: deque[Dict[str, Any]] = deque(maxlen=MAX_MEMORY_RECORDS)
        self._analysis: deque[Dict[str, Any]] = deque(maxlen=MAX_MEMORY_RECORDS)

        # Pending batch queues
        self._pending_signals: List[Dict[str, Any]] = []
        self._pending_decisions: List[Dict[str, Any]] = []
        self._batch_lock = asyncio.Lock()

        self._initialized = False
        self._flush_task: Optional[asyncio.Task[None]] = None

    # ── Lifecycle ─────────────────────────────────────

    async def initialize(self) -> None:
        if self._initialized:
            return
        client = await _get_http_client()
        for attempt in range(1, _RETRY_ATTEMPTS + 2):
            try:
                r = await client.get("/rest/v1/signals?limit=1")
                r.raise_for_status()
                self._initialized = True
                logger.info("data_store: Supabase connected")
                self._flush_task = asyncio.create_task(
                    self._periodic_flush(), name="data-store-flush"
                )
                return
            except Exception as exc:  # noqa: BLE001
                if attempt <= _RETRY_ATTEMPTS:
                    logger.warning(
                        "data_store: connect attempt %d failed: %s", attempt, exc
                    )
                    await asyncio.sleep(_RETRY_DELAY)
                else:
                    logger.error(
                        "data_store: Supabase unavailable, using memory fallback: %s",
                        exc,
                    )
                    self._initialized = True  # continue in memory mode

    async def shutdown(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        await self._flush_all()  # final flush
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()

    # ── Batch write ─────────────────────────────────────

    async def _post_batch(
        self, table: str, records: List[Dict[str, Any]]
    ) -> bool:
        if not records:
            return True
        try:
            client = await _get_http_client()
            r = await client.post(f"/rest/v1/{table}", json=records)
            r.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("data_store._post_batch %s failed: %s", table, exc)
            return False

    async def _flush_all(self) -> None:
        async with self._batch_lock:
            signals, self._pending_signals = self._pending_signals, []
            decisions, self._pending_decisions = self._pending_decisions, []
        await asyncio.gather(
            self._post_batch("signals", signals),
            self._post_batch("decisions", decisions),
            return_exceptions=True,
        )

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
            try:
                await self._flush_all()
            except Exception as exc:  # noqa: BLE001
                logger.debug("data_store periodic flush error: %s", exc)

    # ── Signal write ────────────────────────────────────

    async def store_signal(self, signal: Dict[str, Any]) -> None:
        record = {**signal, "created_at": _utc_now_iso()}
        self._signals.append(record)
        async with self._batch_lock:
            self._pending_signals.append(record)
            if len(self._pending_signals) >= BATCH_SIZE:
                pending, self._pending_signals = self._pending_signals, []
        if len(pending) >= BATCH_SIZE:  # type: ignore[possibly-undefined]
            await self._post_batch("signals", pending)

    async def store_decision(self, decision: Dict[str, Any]) -> None:
        record = {**decision, "created_at": _utc_now_iso()}
        self._decisions.append(record)
        async with self._batch_lock:
            self._pending_decisions.append(record)
            if len(self._pending_decisions) >= BATCH_SIZE:
                pending, self._pending_decisions = self._pending_decisions, []
        if len(pending) >= BATCH_SIZE:  # type: ignore[possibly-undefined]
            await self._post_batch("decisions", pending)

    async def store_trade(self, trade: Dict[str, Any]) -> None:
        record = {**trade, "created_at": _utc_now_iso()}
        self._trades.append(record)
        # trades are lower volume — write immediately
        await self._post_batch("trades", [record])

    async def store_analysis(self, analysis: Dict[str, Any]) -> None:
        record = {**analysis, "created_at": _utc_now_iso()}
        self._analysis.append(record)
        await self._post_batch("analysis_results", [record])

    # ── Reads ───────────────────────────────────────────

    def get_latest_signals(self, n: int = 100) -> List[Dict[str, Any]]:
        return list(self._signals)[-n:]

    def get_latest_decisions(self, n: int = 100) -> List[Dict[str, Any]]:
        return list(self._decisions)[-n:]

    def get_latest_trades(self, n: int = 100) -> List[Dict[str, Any]]:
        return list(self._trades)[-n:]

    def get_latest_analysis(self, n: int = 100) -> List[Dict[str, Any]]:
        return list(self._analysis)[-n:]

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "signals": len(self._signals),
            "decisions": len(self._decisions),
            "trades": len(self._trades),
            "analysis": len(self._analysis),
            "pending_signals": len(self._pending_signals),
            "pending_decisions": len(self._pending_decisions),
        }


# ── Singleton ─────────────────────────────────────
data_store = DataStore()
