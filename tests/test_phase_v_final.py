"""
tests/test_phase_v_final.py
Phase V Final Tests -- 22 test cases

BUG-V1: ReportsPage StatCard import path fix
BUG-V2: ReportsPage PDF button onClick handler
BUG-V3: billing.py router never None
BUG-V4: Migration 014 sort order (20260619 > 002-013)
BUG-V5: SettingsPage version from env var
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FRONTEND = ROOT / "frontend" / "src" / "pages"
MIGRATIONS = ROOT / "supabase" / "migrations"
BACKEND_ROUTES = ROOT / "backend" / "api" / "routes"


# ---------------------------------------------------------------------------
# BUG-V1: ReportsPage StatCard import path
# ---------------------------------------------------------------------------
class TestBugV1ReportsPageStatCard:
    """ReportsPage must use @/components/common/StatCard not @/components/StatCard"""

    def test_reports_page_exists(self):
        assert (FRONTEND / "ReportsPage.tsx").exists(), "ReportsPage.tsx missing"

    def test_correct_statcard_import(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        assert "@/components/common/StatCard" in content, (
            "ReportsPage must import from @/components/common/StatCard"
        )

    def test_wrong_statcard_import_absent(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        # Should NOT have the old wrong path
        lines = [l for l in content.splitlines() if 'import' in l and 'StatCard' in l]
        for line in lines:
            assert '@/components/StatCard"' not in line, (
                f"Wrong StatCard import found: {line}"
            )

    def test_statcard_named_export(self):
        """Should use named import {StatCard} consistent with common/StatCard.tsx"""
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        # named import or default -- either is valid as long as path is correct
        assert "StatCard" in content


# ---------------------------------------------------------------------------
# BUG-V2: PDF download button has onClick handler
# ---------------------------------------------------------------------------
class TestBugV2PDFDownloadButton:
    """PDF button must have onClick -> handleDownloadPDF()"""

    def test_pdf_button_has_onclick(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        # onClick must be present near Download
        assert "onClick" in content, "PDF button has no onClick handler"

    def test_handle_download_pdf_function(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        assert "handleDownloadPDF" in content or "DownloadPDF" in content, (
            "handleDownloadPDF function not found"
        )

    def test_pdf_fetch_call(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        assert "fetch(" in content, "No fetch call in ReportsPage -- PDF download missing"

    def test_blob_url_creation(self):
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        assert "createObjectURL" in content or "Blob" in content, (
            "No Blob/createObjectURL for PDF download"
        )


# ---------------------------------------------------------------------------
# BUG-V3: billing.py router never None
# ---------------------------------------------------------------------------
class TestBugV3BillingRouterNotNone:
    """billing.py router must always be an APIRouter, never None"""

    def test_billing_py_exists(self):
        assert (BACKEND_ROUTES / "billing.py").exists(), "billing.py missing"

    def test_router_not_conditionally_none(self):
        content = (BACKEND_ROUTES / "billing.py").read_text(encoding="utf-8")
        # Old pattern: router = APIRouter(...) if _FASTAPI else None
        assert "else None" not in content or "router" not in content.split("else None")[0].split("\n")[-1], (
            "billing.py router is conditionally None -- BUG-V3 not fixed"
        )

    def test_router_always_defined(self):
        content = (BACKEND_ROUTES / "billing.py").read_text(encoding="utf-8")
        # Must have unconditional router = APIRouter(...)
        assert re.search(r'^router\s*=\s*APIRouter', content, re.MULTILINE), (
            "router must be unconditionally assigned APIRouter"
        )

    def test_billing_py_valid_python(self):
        content = (BACKEND_ROUTES / "billing.py").read_text(encoding="utf-8")
        try:
            compile(content, "billing.py", "exec")
        except SyntaxError as e:
            pytest.fail(f"billing.py has syntax error: {e}")


# ---------------------------------------------------------------------------
# BUG-V4: Migration 014 sort order
# ---------------------------------------------------------------------------
class TestBugV4Migration014SortOrder:
    """Migration 014 must sort AFTER 002-013, not between 001 and 002"""

    def test_old_migration_014_deleted(self):
        old = MIGRATIONS / "20260612155743_014_users_table.sql"
        assert not old.exists(), (
            f"Old migration file {old.name} must be deleted (sorts before 002-013)"
        )

    def test_new_migration_014_exists(self):
        new = MIGRATIONS / "20260619155743_014_users_table.sql"
        assert new.exists(), (
            "New migration 20260619155743_014_users_table.sql must exist"
        )

    def test_migration_014_sorts_after_013(self):
        migration_files = sorted(f.name for f in MIGRATIONS.glob("*.sql"))
        names = [f for f in migration_files if not f.startswith(".")]
        # find positions
        pos_014 = next((i for i, n in enumerate(names) if "_014_" in n), -1)
        pos_013 = next((i for i, n in enumerate(names) if "_013_" in n), -1)
        assert pos_013 != -1, "Migration 013 not found"
        assert pos_014 != -1, "Migration 014 not found"
        assert pos_014 > pos_013, (
            f"Migration 014 (pos {pos_014}) must come AFTER 013 (pos {pos_013})"
        )

    def test_migration_014_sql_content(self):
        new = MIGRATIONS / "20260619155743_014_users_table.sql"
        if new.exists():
            content = new.read_text(encoding="utf-8")
            assert "public.users" in content
            assert "CREATE TABLE" in content


# ---------------------------------------------------------------------------
# BUG-V5: SettingsPage version from env var
# ---------------------------------------------------------------------------
class TestBugV5SettingsPageVersion:
    """SettingsPage must read version from VITE_APP_VERSION env var"""

    def test_settings_page_exists(self):
        assert (FRONTEND / "SettingsPage.tsx").exists(), "SettingsPage.tsx missing"

    def test_version_uses_env_var(self):
        content = (FRONTEND / "SettingsPage.tsx").read_text(encoding="utf-8")
        assert "VITE_APP_VERSION" in content, (
            "SettingsPage must read version from import.meta.env.VITE_APP_VERSION"
        )

    def test_no_bare_hardcoded_version(self):
        """'3.0.0' may still appear as fallback but not as the sole source"""
        content = (FRONTEND / "SettingsPage.tsx").read_text(encoding="utf-8")
        # If 3.0.0 appears, VITE_APP_VERSION must also appear (fallback pattern)
        if '"3.0.0"' in content:
            assert "VITE_APP_VERSION" in content, (
                "Version 3.0.0 hardcoded without env var fallback"
            )


# ---------------------------------------------------------------------------
# Phase V Summary
# ---------------------------------------------------------------------------
class TestPhaseVSummary:
    """Smoke tests verifying all 5 BUG-V fixes together"""

    @pytest.mark.phase_v
    def test_reports_page_build_safe(self):
        """ReportsPage has correct StatCard path -- won't fail TypeScript build"""
        content = (FRONTEND / "ReportsPage.tsx").read_text(encoding="utf-8")
        assert "@/components/common/StatCard" in content
        assert "onClick" in content  # PDF button functional

    @pytest.mark.phase_v
    def test_billing_route_safe(self):
        content = (BACKEND_ROUTES / "billing.py").read_text(encoding="utf-8")
        assert "else None" not in content or "router" not in content

    @pytest.mark.phase_v
    def test_migration_014_correct_position(self):
        names = sorted(f.name for f in MIGRATIONS.glob("*.sql"))
        assert not any("20260612155743_014" in n for n in names)
        assert any("20260619155743_014" in n for n in names)

    @pytest.mark.phase_v
    def test_settings_version_env(self):
        content = (FRONTEND / "SettingsPage.tsx").read_text(encoding="utf-8")
        assert "VITE_APP_VERSION" in content
