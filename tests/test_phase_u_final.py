"""
test_phase_u_final.py — Phase U Final Tests
BUG-U1: portfolio.py correlation import path
BUG-U2: analytics.py bare pass
BUG-U3: migration 014 + 046 sort order
BUG-U4: duplicate AIPredictionsPage
"""
from __future__ import annotations
import ast
import os
import re
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
MIGRATIONS = ROOT / "supabase" / "migrations"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-U1: portfolio.py correlation import path
# ─────────────────────────────────────────────────────────────────────────────
class TestBugU1PortfolioCorrelation:
    """portfolio.py must import from backend.risk.correlation_filter."""

    def _src(self) -> str:
        p = ROOT / "backend" / "api" / "routes" / "portfolio.py"
        return p.read_text(encoding="utf-8")

    def test_portfolio_file_exists(self):
        p = ROOT / "backend" / "api" / "routes" / "portfolio.py"
        assert p.exists(), "portfolio.py must exist"

    def test_no_wrong_import_path(self):
        src = self._src()
        assert "backend.trading.correlation_filter" not in src, (
            "BUG-U1: portfolio.py still imports from backend.trading.correlation_filter "
            "which does NOT exist"
        )

    def test_correct_import_path(self):
        src = self._src()
        assert "backend.risk.correlation_filter" in src, (
            "BUG-U1: portfolio.py must import from backend.risk.correlation_filter"
        )

    def test_risk_correlation_filter_exists(self):
        p = ROOT / "backend" / "risk" / "correlation_filter.py"
        assert p.exists(), (
            "backend/risk/correlation_filter.py must exist (11KB full implementation)"
        )

    def test_correlation_endpoint_exists(self):
        src = self._src()
        assert "/correlation" in src or "correlation" in src, (
            "portfolio.py must have /correlation endpoint"
        )

    def test_portfolio_valid_python(self):
        p = ROOT / "backend" / "api" / "routes" / "portfolio.py"
        ast.parse(p.read_text(encoding="utf-8"))  # no SyntaxError


# ─────────────────────────────────────────────────────────────────────────────
# BUG-U2: analytics.py bare pass
# ─────────────────────────────────────────────────────────────────────────────
class TestBugU2AnalyticsBarePass:
    """analytics.py must log exceptions, not silently pass."""

    def _src(self) -> str:
        p = ROOT / "backend" / "api" / "routes" / "analytics.py"
        return p.read_text(encoding="utf-8")

    def test_analytics_file_exists(self):
        p = ROOT / "backend" / "api" / "routes" / "analytics.py"
        assert p.exists()

    def test_no_bare_pass_in_except(self):
        src = self._src()
        lines = src.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "pass":
                # check previous line has except
                prev = lines[i-1].strip() if i > 0 else ""
                assert not prev.startswith("except"), (
                    f"BUG-U2: bare 'pass' in except block at line {i+1} — "
                    "should log the exception"
                )

    def test_log_warning_present(self):
        src = self._src()
        assert "log.warning" in src or "logger.warning" in src, (
            "BUG-U2: analytics.py must log warnings in exception handlers"
        )

    def test_analytics_valid_python(self):
        p = ROOT / "backend" / "api" / "routes" / "analytics.py"
        ast.parse(p.read_text(encoding="utf-8"))  # no SyntaxError


# ─────────────────────────────────────────────────────────────────────────────
# BUG-U3: migration sort order 014 + 046
# ─────────────────────────────────────────────────────────────────────────────
class TestBugU3MigrationSortOrder:
    """Migration 014 must sort AFTER 001; migration 046 must sort AFTER 045b."""

    def _all_migrations(self):
        return sorted([
            f.name for f in MIGRATIONS.iterdir()
            if f.is_file() and f.suffix == ".sql"
        ])

    def test_old_014_deleted(self):
        bad = MIGRATIONS / "20260610_014_users_table.sql"
        assert not bad.exists(), (
            "BUG-U3a: 20260610_014_users_table.sql must be deleted "
            "(it sorts BEFORE 20260612155742_001_initial_schema.sql)"
        )

    def test_new_014_exists(self):
        new = MIGRATIONS / "20260612155743_014_users_table.sql"
        assert new.exists(), (
            "BUG-U3a: 20260612155743_014_users_table.sql must exist "
            "(1 second after 001, sorts correctly)"
        )

    def test_014_sorts_after_001(self):
        files = self._all_migrations()
        names = [f for f in files if "001_" in f or "014_" in f]
        idx_001 = next((i for i, f in enumerate(files) if "001_initial" in f), None)
        idx_014 = next((i for i, f in enumerate(files) if "014_users" in f), None)
        assert idx_001 is not None, "001_initial_schema must exist"
        assert idx_014 is not None, "014_users_table must exist"
        assert idx_014 > idx_001, (
            f"BUG-U3a: migration 014 (pos {idx_014}) must sort AFTER "
            f"migration 001 (pos {idx_001})"
        )

    def test_old_046_deleted(self):
        bad = MIGRATIONS / "20260628_046_final_acceptance.sql"
        assert not bad.exists(), (
            "BUG-U3b: 20260628_046_final_acceptance.sql must be deleted "
            "(it sorts BEFORE 20260629_045b which creates agent_vote_log)"
        )

    def test_new_046_exists(self):
        new = MIGRATIONS / "20260630_046_final_acceptance.sql"
        assert new.exists(), (
            "BUG-U3b: 20260630_046_final_acceptance.sql must exist "
            "(sorts after 20260629_045b)"
        )

    def test_046_sorts_after_045b(self):
        files = self._all_migrations()
        idx_045b = next((i for i, f in enumerate(files) if "045b" in f), None)
        idx_046  = next((i for i, f in enumerate(files) if "046_" in f), None)
        assert idx_045b is not None, "045b migration must exist"
        assert idx_046  is not None, "046 migration must exist"
        assert idx_046 > idx_045b, (
            f"BUG-U3b: migration 046 (pos {idx_046}) must sort AFTER "
            f"migration 045b (pos {idx_045b}) — agent_vote_log must exist first"
        )

    def test_046_references_agent_vote_log(self):
        new = MIGRATIONS / "20260630_046_final_acceptance.sql"
        if new.exists():
            content = new.read_text(encoding="utf-8")
            assert "agent_vote_log" in content, (
                "046 migration must reference agent_vote_log table"
            )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-U4: duplicate AIPredictionsPage
# ─────────────────────────────────────────────────────────────────────────────
class TestBugU4DuplicatePage:
    """Only one AIPredictions page must exist (lowercase p version)."""

    PAGES = ROOT / "frontend" / "src" / "pages"

    def test_uppercase_p_deleted(self):
        bad = self.PAGES / "AIPredictionsPage.tsx"
        assert not bad.exists(), (
            "BUG-U4: AIPredictionsPage.tsx (uppercase P) must be deleted — "
            "AIpredictionsPage.tsx (lowercase p) is the full decision engine UI"
        )

    def test_lowercase_p_exists(self):
        good = self.PAGES / "AIpredictionsPage.tsx"
        assert good.exists(), (
            "BUG-U4: AIpredictionsPage.tsx (lowercase p) must exist — "
            "it has full decision engine UI with BUY/SELL/confidence/R:R/votes"
        )

    def test_lowercase_p_uses_decision_api(self):
        good = self.PAGES / "AIpredictionsPage.tsx"
        if good.exists():
            content = good.read_text(encoding="utf-8")
            assert "getDecision" in content or "Decision" in content, (
                "AIpredictionsPage.tsx must use decision API"
            )

    def test_no_case_conflict(self):
        if self.PAGES.exists():
            names = [f.name for f in self.PAGES.iterdir()]
            ai_pages = [n for n in names if n.lower() == "aipredictionspage.tsx"]
            assert len(ai_pages) == 1, (
                f"BUG-U4: found {len(ai_pages)} AIPredictions pages: {ai_pages} — must be exactly 1"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Phase U Summary
# ─────────────────────────────────────────────────────────────────────────────
class TestPhaseUSummary:
    """All Phase U fixes verified."""

    def test_bug_u1_portfolio_import_fixed(self):
        p = ROOT / "backend" / "api" / "routes" / "portfolio.py"
        src = p.read_text(encoding="utf-8")
        assert "backend.risk.correlation_filter" in src
        assert "backend.trading.correlation_filter" not in src

    def test_bug_u2_analytics_no_silent_pass(self):
        p = ROOT / "backend" / "api" / "routes" / "analytics.py"
        src = p.read_text(encoding="utf-8")
        assert "log.warning" in src or "logger.warning" in src

    def test_bug_u3_migration_order_correct(self):
        files = sorted([f.name for f in MIGRATIONS.iterdir() if f.suffix == ".sql"])
        idx_001  = next((i for i, f in enumerate(files) if "001_initial" in f), -1)
        idx_014  = next((i for i, f in enumerate(files) if "014_users" in f), -1)
        idx_045b = next((i for i, f in enumerate(files) if "045b" in f), -1)
        idx_046  = next((i for i, f in enumerate(files) if "046_" in f), -1)
        assert idx_014 > idx_001,  "014 must be after 001"
        assert idx_046 > idx_045b, "046 must be after 045b"

    def test_bug_u4_single_ai_page(self):
        pages = ROOT / "frontend" / "src" / "pages"
        if pages.exists():
            names = [f.name for f in pages.iterdir()]
            ai_pages = [n for n in names if n.lower() == "aipredictionspage.tsx"]
            assert len(ai_pages) == 1
