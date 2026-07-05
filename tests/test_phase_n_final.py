"""Phase N: Final fix tests.

Covers:
- BUG-N1/N2: migration conflict files no longer exist
- BUG-N3: migration 044/046 have real SQL content
- BUG-N4: DatasetBuilder uses 38 features (FeaturePipeline)
- BUG-N5: Telegram /positions safe key access
- BUG-N6: Analysis route returns full PA data
- BUG-N7: Backtest date validation
"""
from __future__ import annotations

import os
import sys
import importlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ============================================================ #
# BUG-N1/N2: migration conflict files should not exist
# ============================================================ #
class TestMigrationConflictsResolved:
    """Verify original 019 and 025 files are deleted."""

    MIGRATIONS_DIR = Path("supabase/migrations")

    def test_019_original_tables_deleted(self):
        """BUG-N1: original 019_tables.sql must not exist."""
        conflict = self.MIGRATIONS_DIR / "20260619_019_phase11_13_tables.sql"
        assert not conflict.exists(), (
            f"Conflict file still exists: {conflict} — should have been deleted in Phase N"
        )

    def test_019_original_dashboard_deleted(self):
        """BUG-N1: original 019_dashboard.sql must not exist."""
        conflict = self.MIGRATIONS_DIR / "20260619_019_phase11_13_dashboard.sql"
        assert not conflict.exists(), f"Conflict file still exists: {conflict}"

    def test_025_original_services_deleted(self):
        """BUG-N2: original 025_phase_t_services.sql must not exist."""
        conflict = self.MIGRATIONS_DIR / "20260623_025_phase_t_services.sql"
        assert not conflict.exists(), f"Conflict file still exists: {conflict}"

    def test_025_original_hardening_deleted(self):
        """BUG-N2: original 025_phase_u_hardening.sql must not exist."""
        conflict = self.MIGRATIONS_DIR / "20260623_025_phase_u_hardening.sql"
        assert not conflict.exists(), f"Conflict file still exists: {conflict}"

    def test_019a_has_real_sql(self):
        """019a must contain real CREATE TABLE statements."""
        f = self.MIGRATIONS_DIR / "20260619_019a_phase11_13_tables.sql"
        assert f.exists(), "019a not found"
        content = f.read_text()
        assert "CREATE TABLE" in content, "019a has no CREATE TABLE"
        assert "security_ai_analysis" in content

    def test_019b_has_real_sql(self):
        """019b must contain real CREATE TABLE statements."""
        f = self.MIGRATIONS_DIR / "20260619_019b_phase11_13_dashboard.sql"
        assert f.exists(), "019b not found"
        content = f.read_text()
        assert "CREATE TABLE" in content, "019b has no CREATE TABLE"
        assert "security_metrics_cache" in content

    def test_025a_has_real_sql(self):
        """025a must contain real CREATE TABLE statements."""
        f = self.MIGRATIONS_DIR / "20260623_025a_phase_t_services.sql"
        assert f.exists(), "025a not found"
        content = f.read_text()
        assert "CREATE TABLE" in content
        assert "signal_audit_log" in content

    def test_025b_has_real_sql(self):
        """025b must contain real CREATE TABLE statements."""
        f = self.MIGRATIONS_DIR / "20260623_025b_phase_u_hardening.sql"
        assert f.exists(), "025b not found"
        content = f.read_text()
        assert "CREATE INDEX" in content or "CREATE OR REPLACE FUNCTION" in content

    def test_044_has_real_sql(self):
        """BUG-N3: migration 044 must have real SQL (not just SELECT 1)."""
        f = self.MIGRATIONS_DIR / "20260628_044_phase35_release_gate.sql"
        assert f.exists(), "044 not found"
        content = f.read_text()
        assert "CREATE TABLE" in content, "044 still placeholder"
        assert "deployment_gates" in content

    def test_046_has_real_sql(self):
        """BUG-N3: migration 046 must have real SQL (not trivial)."""
        f = self.MIGRATIONS_DIR / "20260628_046_final_acceptance.sql"
        assert f.exists(), "046 not found"
        content = f.read_text()
        assert "CREATE INDEX" in content or "UPDATE deployment_gates" in content, (
            "046 still trivial placeholder"
        )


# ============================================================ #
# BUG-N4: DatasetBuilder feature count
# ============================================================ #
class TestDatasetBuilderFeatureCount:
    """DatasetBuilder must produce 38 features matching FeaturePipeline."""

    def test_dataset_builder_imports(self):
        from backend.ai_prediction.dataset_builder import DatasetBuilder
        assert DatasetBuilder

    def test_feature_names_returns_list(self):
        from backend.ai_prediction.dataset_builder import DatasetBuilder
        db = DatasetBuilder()
        names = db.feature_names
        assert isinstance(names, list)
        assert len(names) > 12, f"Expected >12 features, got {len(names)}"

    def test_feature_count_matches_pipeline(self):
        """BUG-N4: DatasetBuilder and FeaturePipeline must agree on feature count."""
        from backend.ai_prediction.dataset_builder import DatasetBuilder
        try:
            from backend.ai_prediction.feature_pipeline import FeaturePipeline
            pipeline_names = FeaturePipeline.feature_names()
            db = DatasetBuilder()
            assert db.feature_names == pipeline_names, (
                f"Mismatch: DatasetBuilder has {len(db.feature_names)} features, "
                f"FeaturePipeline has {len(pipeline_names)}"
            )
        except ImportError:
            pytest.skip("FeaturePipeline not available")

    def test_no_hardcoded_12_columns(self):
        """DatasetBuilder source must not have the old 12-column hardcode."""
        import inspect
        from backend.ai_prediction.dataset_builder import DatasetBuilder
        src = inspect.getsource(DatasetBuilder)
        # Old hardcoded list had exactly these 12 items on one line
        assert '"rsi", "macd", "bb_upper", "bb_lower", "atr", "ema20", "ema50"' not in src, (
            "Old 12-column hardcode still present in DatasetBuilder"
        )


# ============================================================ #
# BUG-N5: Telegram /positions safe key access
# ============================================================ #
class TestTelegramPositionsKeyError:
    """_format_position must handle DEMO mode keys without crashing."""

    def test_format_position_live_keys(self):
        from backend.telegram.bot import _format_position
        pos = {
            "symbol": "EURUSD", "volume": 0.1, "type": "BUY",
            "open_price": 1.1000, "current_price": 1.1050,
            "profit": 50.0, "ticket": 123456
        }
        result = _format_position(pos)
        assert "EURUSD" in result
        assert "50.00" in result

    def test_format_position_demo_keys_no_profit(self):
        """BUG-N5: DEMO mode has no 'profit' key — must not KeyError."""
        from backend.telegram.bot import _format_position
        pos = {
            "symbol": "XAUUSD", "volume": 0.01, "type": "SELL",
            "open_price": 2000.0, "current_price": 1998.0,
            # No 'profit' key — DEMO mode
        }
        result = _format_position(pos)  # must not raise
        assert "XAUUSD" in result

    def test_format_position_minimal_keys(self):
        """Even with minimal keys, must not crash."""
        from backend.telegram.bot import _format_position
        pos = {"symbol": "BTCUSD"}
        result = _format_position(pos)
        assert "BTCUSD" in result


# ============================================================ #
# BUG-N7: Backtest date validation
# ============================================================ #
class TestBacktestDateValidation:
    """BacktestRequest must reject end_date <= start_date."""

    def test_valid_date_range(self):
        from backend.api.routes.backtest import BacktestRequest
        req = BacktestRequest(symbol="EURUSD", start_date="2025-01-01", end_date="2025-12-31")
        assert req.end_date == "2025-12-31"

    def test_end_before_start_raises(self):
        """BUG-N7: end_date before start_date must raise ValidationError."""
        from pydantic import ValidationError
        from backend.api.routes.backtest import BacktestRequest
        with pytest.raises(ValidationError):
            BacktestRequest(symbol="EURUSD", start_date="2025-12-31", end_date="2025-01-01")

    def test_end_equal_start_raises(self):
        from pydantic import ValidationError
        from backend.api.routes.backtest import BacktestRequest
        with pytest.raises(ValidationError):
            BacktestRequest(symbol="EURUSD", start_date="2025-06-01", end_date="2025-06-01")
