"""Tests for InstitutionalDataStore."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_data_store_initialize_no_creds() -> None:
    """initialize() should not raise even without Supabase credentials."""
    import os
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    from backend.institutional.data_store import InstitutionalDataStore
    store = InstitutionalDataStore()
    await store.initialize()  # should not raise
    assert store._available is False


@pytest.mark.asyncio
async def test_memory_fallback() -> None:
    """Data should be stored in memory when Supabase is unavailable."""
    from backend.institutional.data_store import InstitutionalDataStore
    store = InstitutionalDataStore()
    store._available = False  # force in-memory
    result = await store.save_backtest_result({"symbol": "XAUUSD", "net_pnl": 100.0})
    assert result is None  # in-memory returns None ID
    records = await store.get_backtest_results(limit=10)
    assert len(records) >= 1


@pytest.mark.asyncio
async def test_memory_cap_enforced() -> None:
    """Memory store should not exceed MAX_MEMORY_RECORDS."""
    from backend.institutional.data_store import InstitutionalDataStore, MAX_MEMORY_RECORDS
    store = InstitutionalDataStore()
    store._available = False
    # Insert MAX + 10 records
    for i in range(MAX_MEMORY_RECORDS + 10):
        await store._upsert("test_table", {"i": i})
    assert len(store._memory_store.get("test_table", [])) <= MAX_MEMORY_RECORDS


def test_utc_now_iso() -> None:
    from backend.institutional.data_store import _utc_now_iso
    ts = _utc_now_iso()
    assert "T" in ts  # ISO 8601 format
    assert "+" in ts or "Z" in ts or ts.endswith("+00:00")


def test_memory_stats() -> None:
    from backend.institutional.data_store import InstitutionalDataStore
    store = InstitutionalDataStore()
    store._memory_store = {"table_a": [{}, {}], "table_b": [{}]}
    stats = store.memory_stats()
    assert stats["table_a"] == 2
    assert stats["table_b"] == 1
