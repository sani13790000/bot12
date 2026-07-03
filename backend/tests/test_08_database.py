"""
test_08_database.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تست‌های Database layer:
- DatabaseWrapper با mock Supabase client
- connection health check
- CRUD operations
- connection pool
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDatabaseWrapper:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_client = MagicMock()
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "t001", "symbol": "EURUSD"}]
        mock_execute.error = None

        mock_select = MagicMock()
        mock_select.execute = MagicMock(return_value=mock_execute)
        mock_select.eq = MagicMock(return_value=mock_select)
        mock_select.limit = MagicMock(return_value=mock_select)
        mock_select.order = MagicMock(return_value=mock_select)

        mock_insert_exec = MagicMock()
        mock_insert_exec.data = [{"id": "new-001"}]
        mock_insert_exec.error = None
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=mock_insert_exec)

        mock_update_exec = MagicMock()
        mock_update_exec.data = [{"id": "t001", "status": "closed"}]
        mock_update_exec.error = None
        mock_update = MagicMock()
        mock_update.eq = MagicMock(return_value=mock_update)
        mock_update.execute = MagicMock(return_value=mock_update_exec)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)
        mock_table.insert = MagicMock(return_value=mock_insert)
        mock_table.update = MagicMock(return_value=mock_update)
        mock_table.delete = MagicMock(return_value=mock_update)
        self.mock_client.table = MagicMock(return_value=mock_table)
        self.mock_client.rpc = MagicMock(return_value=mock_execute)

    def test_wrapper_initializes(self) -> None:
        from backend.database.connection import DatabaseWrapper
        with patch("backend.database.connection.create_client", return_value=self.mock_client):
            db = DatabaseWrapper()
            assert db is not None

    def test_ping_returns_true(self) -> None:
        from backend.database.connection import DatabaseWrapper
        with patch("backend.database.connection.create_client", return_value=self.mock_client):
            db = DatabaseWrapper()
            result = db.ping()
            assert result is True

    def test_select_returns_list(self) -> None:
        from backend.database.connection import DatabaseWrapper
        with patch("backend.database.connection.create_client", return_value=self.mock_client):
            db = DatabaseWrapper()
            result = db.select("trades")
            assert isinstance(result, list)

    def test_insert_returns_dict(self) -> None:
        from backend.database.connection import DatabaseWrapper
        with patch("backend.database.connection.create_client", return_value=self.mock_client):
            db = DatabaseWrapper()
            result = db.insert("trades", {"symbol": "EURUSD", "direction": "buy"})
            assert isinstance(result, dict)

    def test_update_called(self) -> None:
        from backend.database.connection import DatabaseWrapper
        with patch("backend.database.connection.create_client", return_value=self.mock_client):
            db = DatabaseWrapper()
            db.update("trades", "t001", {"status": "closed"})
            self.mock_client.table.assert_called()


class TestConnectionHealth:

    def test_health_module_importable(self) -> None:
        from backend.database import connection_health
        assert connection_health is not None

    def test_health_checker_exists(self) -> None:
        from backend.database.connection_health import ConnectionHealthChecker
        checker = ConnectionHealthChecker()
        assert checker is not None

    def test_health_report_structure(self) -> None:
        from backend.database.connection_health import ConnectionHealthChecker
        checker = ConnectionHealthChecker()
        report = checker.get_report()
        assert isinstance(report, dict)


class TestQueryOptimizer:

    def test_optimizer_importable(self) -> None:
        from backend.database import query_optimizer
        assert query_optimizer is not None

    def test_optimizer_class_exists(self) -> None:
        from backend.database.query_optimizer import QueryOptimizer
        opt = QueryOptimizer()
        assert opt is not None


class TestConnectionPoolMonitor:

    def test_pool_monitor_importable(self) -> None:
        from backend.database import connection_pool_monitor
        assert connection_pool_monitor is not None

    def test_pool_monitor_class_exists(self) -> None:
        from backend.database.connection_pool_monitor import ConnectionPoolMonitor
        monitor = ConnectionPoolMonitor()
        assert monitor is not None

    def test_pool_stats_structure(self) -> None:
        from backend.database.connection_pool_monitor import ConnectionPoolMonitor
        monitor = ConnectionPoolMonitor()
        stats = monitor.get_stats()
        assert isinstance(stats, dict)


class TestGetDbDependency:

    def test_get_db_importable(self) -> None:
        from backend.database.connection import get_db
        assert callable(get_db)

    def test_db_singleton_importable(self) -> None:
        from backend.database.connection import db
        assert db is not None

    def test_get_db_is_generator(self) -> None:
        from backend.database.connection import get_db
        import inspect
        assert inspect.isgeneratorfunction(get_db)
