"""Tests for the /health endpoint and database connection."""
from __future__ import annotations

import pytest


def test_import_connection() -> None:
    """database.connection module must be importable."""
    from backend.database import connection  # noqa: F401


def test_reset_client() -> None:
    """reset_client() must not raise."""
    from backend.database.connection import reset_client

    reset_client()


def test_pool_monitor_get_status() -> None:
    """Pool monitor must return a status dict with expected keys."""
    from backend.database.connection_pool_monitor import ConnectionPoolMonitor

    monitor = ConnectionPoolMonitor(interval=60)
    status = monitor.get_status()
    assert "healthy" in status
    assert "latency_ms" in status
    assert "consecutive_failures" in status
