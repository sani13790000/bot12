"""
Phase R Final Tests
BUG-R1: XGBoostTrainer - no internal DatasetBuilder (12 features)
BUG-R2: Migration prefix conflicts 030/042/045 resolved
BUG-R3: LearningPage is no longer a stub
BUG-R4: ModelPerformancePage is no longer a stub
"""
from __future__ import annotations
import ast, os, re, sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")
FRONTEND_PAGES = os.path.join(ROOT, "frontend", "src", "pages")
XGB_TRAINER = os.path.join(ROOT, "backend", "ai_prediction", "xgboost_trainer.py")
pytestmark = pytest.mark.phase_r


class TestXGBoostTrainerBugR1:
    def test_file_exists(self):
        assert os.path.exists(XGB_TRAINER)

    def test_no_internal_dataset_builder_class(self):
        """Internal DatasetBuilder class must not exist in xgboost_trainer.py."""
        with open(XGB_TRAINER) as f:
            content = f.read()
        tree = ast.parse(content)
        names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "DatasetBuilder" not in names, (
            f"Internal DatasetBuilder found: {names}. BUG-R1 not fixed."
        )

    def test_no_hardcoded_12_feature_cols(self):
        with open(XGB_TRAINER) as f:
            content = f.read()
        old_cols = ["macd_signal", "session_hour", "day_of_week", "pa_score", "volume_ratio"]
        found = sum(1 for c in old_cols if c in content)
        assert found < 3, f"Old 12-feature list present ({found}/5 old cols found)"

    def test_imports_from_dataset_builder(self):
        with open(XGB_TRAINER) as f:
            content = f.read()
        assert "from backend.ai_prediction.dataset_builder import DatasetBuilder" in content

    def test_no_synthetic_dataset_old_method(self):
        with open(XGB_TRAINER) as f:
            content = f.read()
        assert "_synthetic_dataset" not in content

    def test_importable(self):
        sys.path.insert(0, ROOT)
        try:
            from backend.ai_prediction.xgboost_trainer import XGBoostTrainer
            t = XGBoostTrainer()
            assert hasattr(t, "train_latest")
            assert hasattr(t, "is_model_loaded")
        except ImportError:
            pytest.skip("deps not installed")


class TestMigrationConflictsBugR2:
    def _files(self):
        if not os.path.exists(MIGRATIONS):
            pytest.skip()
        return [f for f in os.listdir(MIGRATIONS) if f.endswith(".sql")]

    def test_no_030_bare_conflict(self):
        assert not any("_030_" in f for f in self._files()), "_030_ bare conflict exists"

    def test_030a_030b_exist(self):
        files = self._files()
        assert any("_030a_" in f for f in files), "_030a_ missing"
        assert any("_030b_" in f for f in files), "_030b_ missing"

    def test_no_042_bare_conflict(self):
        assert not any("_042_" in f for f in self._files()), "_042_ bare conflict exists"

    def test_042a_042b_exist(self):
        files = self._files()
        assert any("_042a_" in f for f in files), "_042a_ missing"
        assert any("_042b_" in f for f in files), "_042b_ missing"

    def test_no_045_bare_conflict(self):
        assert not any("_045_" in f for f in self._files()), "_045_ bare conflict exists"

    def test_045a_045b_exist(self):
        files = self._files()
        assert any("_045a_" in f for f in files), "_045a_ missing"
        assert any("_045b_" in f for f in files), "_045b_ missing"

    def test_014_has_timestamp(self):
        files = self._files()
        assert "014_users_table.sql" not in files, "bare 014 still exists"
        assert any(f.endswith("_014_users_table.sql") for f in files)

    def test_no_bare_014(self):
        files = self._files()
        assert not any(re.match(r"^014_", f) for f in files)


class TestFrontendPagesBugR3R4:
    def _read(self, name):
        path = os.path.join(FRONTEND_PAGES, name)
        if not os.path.exists(path):
            pytest.skip(f"{name} not found")
        return open(path).read()

    def test_learning_not_stub(self):
        assert "در حال توسعه" not in self._read("LearningPage.tsx")

    def test_learning_calls_api(self):
        assert "self-learning" in self._read("LearningPage.tsx")

    def test_learning_shows_metrics(self):
        c = self._read("LearningPage.tsx")
        assert "total_retraining_cycles" in c or "current_auc" in c

    def test_model_not_stub(self):
        assert "در حال توسعه" not in self._read("ModelPerformancePage.tsx")

    def test_model_calls_api(self):
        assert "/ai/models" in self._read("ModelPerformancePage.tsx")

    def test_model_shows_auc(self):
        c = self._read("ModelPerformancePage.tsx")
        assert "auc" in c.lower() or "accuracy" in c.lower()

    def test_model_has_symbol_selector(self):
        assert "XAUUSD" in self._read("ModelPerformancePage.tsx")


class TestPhaseRSummary:
    def test_only_xgboosttrainer_class_in_trainer(self):
        if not os.path.exists(XGB_TRAINER):
            pytest.skip()
        tree = ast.parse(open(XGB_TRAINER).read())
        count = sum(1 for n in ast.walk(tree)
                    if isinstance(n, ast.ClassDef) and n.name == "DatasetBuilder")
        assert count == 0, f"{count} DatasetBuilder class(es) in xgboost_trainer.py"

    def test_migration_count_reasonable(self):
        if not os.path.exists(MIGRATIONS):
            pytest.skip()
        files = [f for f in os.listdir(MIGRATIONS) if f.endswith(".sql")]
        assert len(files) >= 45, f"Only {len(files)} migrations found"

    def test_no_placeholder_migrations(self):
        if not os.path.exists(MIGRATIONS):
            pytest.skip()
        for fname in os.listdir(MIGRATIONS):
            if not fname.endswith(".sql"):
                continue
            content = open(os.path.join(MIGRATIONS, fname)).read().strip()
            if len(content) < 100 and content.upper().startswith("SELECT"):
                pytest.fail(f"{fname} is a placeholder")
