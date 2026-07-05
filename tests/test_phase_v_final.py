"""
tests/test_phase_v_final.py
Phase V Final Tests — 24 test cases

BUG-V1: ReportsPage StatCard named import + PDF handler
BUG-V2: billing.py router=None guard removed
BUG-V3: SettingsPage version from env
BUG-V4: Migration 014 sort order (after 013, not between 001-002)
"""
import ast
import os
import re
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONTEND = ROOT / "frontend" / "src" / "pages"
MIGRATIONS = ROOT / "supabase" / "migrations"
BACKEND_ROUTES = ROOT / "backend" / "api" / "routes"


# =============================================================================
# BUG-V1: ReportsPage StatCard named import + PDF handler
# =============================================================================
class TestBugV1ReportsPageStatCard:
    """ReportsPage.tsx must use named import and have working PDF handler."""

    def _content(self) -> str:
        p = FRONTEND / "ReportsPage.tsx"
        assert p.exists(), "ReportsPage.tsx must exist"
        return p.read_text(encoding="utf-8")

    @pytest.mark.phase_v
    def test_named_import_path(self):
        """Must import StatCard from @/components/common/StatCard."""
        content = self._content()
        assert "@/components/common/StatCard" in content, (
            "ReportsPage must import from @/components/common/StatCard"
        )

    @pytest.mark.phase_v
    def test_no_wrong_import_path(self):
        """Must NOT import from @/components/StatCard (wrong path)."""
        content = self._content()
        wrong = re.search(r'from ["\']@/components/StatCard["\']', content)
        assert wrong is None, "ReportsPage must not use @/components/StatCard (missing common/)"

    @pytest.mark.phase_v
    def test_named_import_syntax(self):
        """Must use named import: { StatCard } not default import."""
        content = self._content()
        assert "{ StatCard }" in content, (
            "StatCard must be a named import: import { StatCard } from ..."
        )

    @pytest.mark.phase_v
    def test_pdf_handler_exists(self):
        """handleDownloadPDF function must exist."""
        content = self._content()
        assert "handleDownloadPDF" in content, (
            "ReportsPage must have handleDownloadPDF function"
        )

    @pytest.mark.phase_v
    def test_pdf_button_has_onclick(self):
        """Download button must have onClick handler."""
        content = self._content()
        assert "onClick={handleDownloadPDF}" in content, (
            "Download PDF button must have onClick={handleDownloadPDF}"
        )

    @pytest.mark.phase_v
    def test_pdf_uses_fetch(self):
        """handleDownloadPDF must use fetch API."""
        content = self._content()
        assert "fetch(" in content, "handleDownloadPDF must use fetch()"

    @pytest.mark.phase_v
    def test_pdf_creates_blob(self):
        """handleDownloadPDF must create Blob URL."""
        content = self._content()
        assert "createObjectURL" in content, (
            "handleDownloadPDF must use URL.createObjectURL for download"
        )


# =============================================================================
# BUG-V2: billing.py router=None guard removed
# =============================================================================
class TestBugV2BillingRouterNone:
    """billing.py router must always be created, no None fallback."""

    def _content(self) -> str:
        p = BACKEND_ROUTES / "billing.py"
        assert p.exists(), "billing.py must exist"
        return p.read_text(encoding="utf-8")

    @pytest.mark.phase_v
    def test_no_router_none_guard(self):
        """router must NOT be assigned None."""
        content = self._content()
        assert "router = APIRouter" in content
        # Must not have the pattern: router = ... if _FASTAPI else None
        assert "else None" not in content or "router" not in content.split("else None")[0].split("\n")[-1], (
            "billing.py router must not fallback to None"
        )

    @pytest.mark.phase_v
    def test_router_always_apirouter(self):
        """router = APIRouter(...) must be unconditional."""
        content = self._content()
        lines = [l.strip() for l in content.splitlines()]
        router_lines = [l for l in lines if l.startswith("router = APIRouter")]
        assert len(router_lines) >= 1, "router must be assigned APIRouter unconditionally"

    @pytest.mark.phase_v
    def test_provider_config_read(self):
        """_get_billing_engine must read from settings."""
        content = self._content()
        assert "BILLING_PROVIDER" in content, (
            "_get_billing_engine must read BILLING_PROVIDER from settings"
        )

    @pytest.mark.phase_v
    def test_valid_python(self):
        """billing.py must be valid Python."""
        p = BACKEND_ROUTES / "billing.py"
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            pytest.fail(f"billing.py has syntax error: {e}")


# =============================================================================
# BUG-V3: SettingsPage version from env
# =============================================================================
class TestBugV3SettingsPageVersion:
    """SettingsPage.tsx must read version from env, not hardcode."""

    def _content(self) -> str:
        p = FRONTEND / "SettingsPage.tsx"
        assert p.exists(), "SettingsPage.tsx must exist"
        return p.read_text(encoding="utf-8")

    @pytest.mark.phase_v
    def test_version_from_env(self):
        """Version must come from import.meta.env.VITE_APP_VERSION."""
        content = self._content()
        assert "VITE_APP_VERSION" in content, (
            "SettingsPage must read version from VITE_APP_VERSION env"
        )

    @pytest.mark.phase_v
    def test_no_hardcoded_version_in_inline(self):
        """'3.0.0' must not appear inline in JSX data array."""
        content = self._content()
        # Check that 3.0.0 is only used as fallback, not as primary value
        # It's acceptable as ?? fallback but not as the only value
        lines = content.splitlines()
        for line in lines:
            if '"3.0.0"' in line and 'VITE_APP_VERSION' not in line and '??' not in line:
                pytest.fail(f"Hardcoded version '3.0.0' found without env fallback: {line.strip()}")

    @pytest.mark.phase_v
    def test_app_version_constant(self):
        """APP_VERSION constant must be defined."""
        content = self._content()
        assert "APP_VERSION" in content, "APP_VERSION constant must be defined"


# =============================================================================
# BUG-V4: Migration 014 sort order
# =============================================================================
class TestBugV4Migration014SortOrder:
    """Migration 014 must sort AFTER migrations 002-013."""

    def _migration_files(self) -> list:
        return sorted([f.name for f in MIGRATIONS.glob("*.sql")])

    @pytest.mark.phase_v
    def test_old_014_deleted(self):
        """Old 20260612155743_014 must be deleted."""
        old = MIGRATIONS / "20260612155743_014_users_table.sql"
        assert not old.exists(), (
            "Old 20260612155743_014_users_table.sql must be deleted (sorted before 002-013)"
        )

    @pytest.mark.phase_v
    def test_new_014_exists(self):
        """New 20260619155744_014 must exist."""
        new = MIGRATIONS / "20260619155744_014_users_table.sql"
        assert new.exists(), (
            "New 20260619155744_014_users_table.sql must exist (sorts after 013)"
        )

    @pytest.mark.phase_v
    def test_014_sorts_after_013(self):
        """014 must sort after 013 in alphabetical order."""
        files = self._migration_files()
        files_014 = [f for f in files if "_014_" in f]
        files_013 = [f for f in files if "_013_" in f]
        assert files_014, "014 migration must exist"
        assert files_013, "013 migration must exist"
        pos_014 = files.index(files_014[0])
        pos_013 = files.index(files_013[0])
        assert pos_014 > pos_013, (
            f"014 ({files_014[0]}) must sort after 013 ({files_013[0]}), "
            f"but got positions: 013={pos_013}, 014={pos_014}"
        )

    @pytest.mark.phase_v
    def test_014_sorts_after_002(self):
        """014 must sort after 002 in alphabetical order."""
        files = self._migration_files()
        files_014 = [f for f in files if "_014_" in f]
        files_002 = [f for f in files if "_002_" in f]
        assert files_014, "014 migration must exist"
        assert files_002, "002 migration must exist"
        pos_014 = files.index(files_014[0])
        pos_002 = files.index(files_002[0])
        assert pos_014 > pos_002, (
            f"014 must sort after 002, but positions: 002={pos_002}, 014={pos_014}"
        )

    @pytest.mark.phase_v
    def test_014_sql_content_valid(self):
        """New 014 migration must have real SQL content."""
        new = MIGRATIONS / "20260619155744_014_users_table.sql"
        if new.exists():
            content = new.read_text(encoding="utf-8")
            assert "CREATE TABLE" in content, "014 migration must have CREATE TABLE"
            assert "public.users" in content, "014 migration must create public.users"
            assert "BEGIN" in content and "COMMIT" in content, "014 must use transaction"


# =============================================================================
# Summary
# =============================================================================
class TestPhaseVSummary:
    """Integration summary for Phase V."""

    @pytest.mark.phase_v
    def test_reports_page_exists(self):
        assert (FRONTEND / "ReportsPage.tsx").exists()

    @pytest.mark.phase_v
    def test_billing_route_exists(self):
        assert (BACKEND_ROUTES / "billing.py").exists()

    @pytest.mark.phase_v
    def test_settings_page_exists(self):
        assert (FRONTEND / "SettingsPage.tsx").exists()

    @pytest.mark.phase_v
    def test_all_bugs_addressed(self):
        """All 4 bugs from Phase V must be fixed."""
        bugs = {
            "V1a": (FRONTEND / "ReportsPage.tsx").exists(),
            "V1b": "handleDownloadPDF" in (FRONTEND / "ReportsPage.tsx").read_text(),
            "V2":  "else None" not in (BACKEND_ROUTES / "billing.py").read_text(),
            "V3":  "VITE_APP_VERSION" in (FRONTEND / "SettingsPage.tsx").read_text(),
            "V4":  not (ROOT / "supabase/migrations/20260612155743_014_users_table.sql").exists(),
        }
        failed = [k for k, v in bugs.items() if not v]
        assert not failed, f"These Phase V bugs not fixed: {failed}"
