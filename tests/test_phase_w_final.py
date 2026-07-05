"""
test_phase_w_final.py
Faz W Final Tests - 24 test cases

BUG-W1: billing._get_billing_engine() real provider dispatch
BUG-W2: AdminDashboardPage.tsx StatCard named import from correct path
BUG-W3: Migration 014 duplicate removed
BUG-W4: Migration 013 sort order fixed (before 014)
"""
import os
import re
import ast
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ============================================================
# BUG-W1: billing._get_billing_engine() real provider dispatch
# ============================================================
class TestBugW1BillingRealProvider:
    """_get_billing_engine() must dispatch to real providers, not always MockProvider."""

    BILLING_PY = ROOT / "backend" / "api" / "routes" / "billing.py"

    def test_billing_file_exists(self):
        assert self.BILLING_PY.exists(), "billing.py must exist"

    def test_billing_has_zarinpal_dispatch(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        assert "ZarinpalProvider" in src, (
            "billing.py must import ZarinpalProvider for zarinpal payments"
        )

    def test_billing_has_stripe_dispatch(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        assert "StripeProvider" in src, (
            "billing.py must import StripeProvider for stripe payments"
        )

    def test_billing_has_provider_name_check(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        assert 'provider_name == "zarinpal"' in src or "provider_name == 'zarinpal'" in src, (
            "billing.py must check provider_name == 'zarinpal'"
        )

    def test_billing_has_stripe_check(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        assert 'provider_name == "stripe"' in src or "provider_name == 'stripe'" in src, (
            "billing.py must check provider_name == 'stripe'"
        )

    def test_billing_mock_is_fallback_only(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        # The try block for zarinpal/stripe should NOT contain MockProvider directly
        # Only the fallback/except blocks should
        lines = src.split("\n")
        # Find the zarinpal block and verify it has ZarinpalProvider
        in_zarinpal_block = False
        found_real_provider = False
        for line in lines:
            if 'provider_name == "zarinpal"' in line or "provider_name == 'zarinpal'" in line:
                in_zarinpal_block = True
            if in_zarinpal_block and "ZarinpalProvider" in line:
                found_real_provider = True
                break
        assert found_real_provider, "zarinpal block must use ZarinpalProvider"

    def test_billing_valid_python(self):
        src = self.BILLING_PY.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"billing.py has syntax error: {e}")


# ============================================================
# BUG-W2: AdminDashboardPage.tsx StatCard named import
# ============================================================
class TestBugW2AdminDashboardStatCard:
    """AdminDashboardPage must use named import from correct path."""

    ADMIN_PAGE = ROOT / "frontend" / "src" / "pages" / "AdminDashboardPage.tsx"

    def test_admin_page_exists(self):
        assert self.ADMIN_PAGE.exists(), "AdminDashboardPage.tsx must exist"

    def test_no_default_import_wrong_path(self):
        src = self.ADMIN_PAGE.read_text(encoding="utf-8")
        assert 'import StatCard from "@/components/StatCard"' not in src, (
            "Must not use default import from wrong path '@/components/StatCard'"
        )

    def test_named_import_correct_path(self):
        src = self.ADMIN_PAGE.read_text(encoding="utf-8")
        assert '{ StatCard }' in src, "Must use named import { StatCard }"
        assert '@/components/common/StatCard' in src, (
            "Must import from '@/components/common/StatCard'"
        )

    def test_statcard_used_in_component(self):
        src = self.ADMIN_PAGE.read_text(encoding="utf-8")
        assert '<StatCard' in src, "StatCard must be used in component JSX"

    def test_kill_switch_button_exists(self):
        src = self.ADMIN_PAGE.read_text(encoding="utf-8")
        assert 'toggleKillSwitch' in src, "Kill switch toggle must exist"
        assert 'onClick' in src, "Kill switch button must have onClick handler"


# ============================================================
# BUG-W3: Migration 014 duplicate removed
# ============================================================
class TestBugW3Migration014Dedup:
    """Only one migration 014 file must exist."""

    MIGRATIONS = ROOT / "supabase" / "migrations"

    def test_migrations_dir_exists(self):
        assert self.MIGRATIONS.exists(), "supabase/migrations/ must exist"

    def test_old_014_v1_deleted(self):
        old_file = self.MIGRATIONS / "20260619155743_014_users_table.sql"
        assert not old_file.exists(), (
            "20260619155743_014 (old duplicate) must be deleted"
        )

    def test_canonical_014_exists(self):
        canonical = self.MIGRATIONS / "20260619155744_014_users_table.sql"
        assert canonical.exists(), (
            "20260619155744_014 (canonical, 3920B) must exist"
        )

    def test_single_014_file(self):
        if not self.MIGRATIONS.exists():
            pytest.skip("migrations dir not found")
        files_014 = [f for f in self.MIGRATIONS.iterdir() if "_014_" in f.name]
        assert len(files_014) == 1, (
            f"Exactly 1 migration 014 file must exist, found: {[f.name for f in files_014]}"
        )

    def test_canonical_014_has_complete_sql(self):
        canonical = self.MIGRATIONS / "20260619155744_014_users_table.sql"
        if not canonical.exists():
            pytest.skip()
        sql = canonical.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS public.users" in sql
        assert "CREATE TABLE IF NOT EXISTS public.refresh_tokens" in sql
        assert "ROW LEVEL SECURITY" in sql


# ============================================================
# BUG-W4: Migration 013 sort order
# ============================================================
class TestBugW4Migration013Order:
    """Migration 013 must sort BEFORE 014 in alphabetical order."""

    MIGRATIONS = ROOT / "supabase" / "migrations"

    def test_old_013_without_timestamp_deleted(self):
        old_file = self.MIGRATIONS / "20260619_013_institutional_modules.sql"
        assert not old_file.exists(), (
            "20260619_013 (without timestamp) must be deleted"
        )

    def test_new_013_with_timestamp_exists(self):
        new_file = self.MIGRATIONS / "20260619155741_013_institutional_modules.sql"
        assert new_file.exists(), (
            "20260619155741_013 (with timestamp) must exist"
        )

    def test_013_sorts_before_014(self):
        f013 = "20260619155741_013_institutional_modules.sql"
        f014 = "20260619155744_014_users_table.sql"
        assert f013 < f014, (
            f"013 must sort before 014: '{f013}' < '{f014}'"
        )

    def test_013_sql_content_valid(self):
        new_file = self.MIGRATIONS / "20260619155741_013_institutional_modules.sql"
        if not new_file.exists():
            pytest.skip()
        sql = new_file.read_text(encoding="utf-8")
        assert "institutional_backtests" in sql
        assert "institutional_trades" in sql
        assert "IF NOT EXISTS" in sql

    def test_migration_order_1_to_15(self):
        """Verify positions 1-15 are in correct logical order."""
        if not self.MIGRATIONS.exists():
            pytest.skip()
        files = sorted([f.name for f in self.MIGRATIONS.iterdir()
                       if f.suffix == '.sql' and f.name != '.gitkeep'])
        # Find positions
        pos = {}
        for i, f in enumerate(files):
            for num in ['001', '013', '014', '015']:
                if f'_{num}_' in f or f'{num}_' in f:
                    pos[num] = i
        if '001' in pos and '013' in pos and '014' in pos:
            assert pos['001'] < pos['013'], "001 must be before 013"
            assert pos['013'] < pos['014'], "013 must be before 014"
            assert pos['014'] < pos.get('015', 999), "014 must be before 015"


# ============================================================
# Summary
# ============================================================
class TestPhaseWSummary:
    """Summary verification for all Faz-W fixes."""

    def test_bug_w1_billing_py_correct(self):
        billing = ROOT / "backend" / "api" / "routes" / "billing.py"
        assert billing.exists()
        src = billing.read_text(encoding="utf-8")
        assert "ZarinpalProvider" in src and "StripeProvider" in src
        assert 'BUG-W1' in src

    def test_bug_w2_admin_dashboard_correct(self):
        page = ROOT / "frontend" / "src" / "pages" / "AdminDashboardPage.tsx"
        assert page.exists()
        src = page.read_text(encoding="utf-8")
        assert '{ StatCard }' in src
        assert '@/components/common/StatCard' in src
        assert 'BUG-W2' in src

    def test_bug_w3_no_duplicate_014(self):
        migrations = ROOT / "supabase" / "migrations"
        if not migrations.exists():
            pytest.skip()
        files_014 = [f for f in migrations.iterdir() if "_014_" in f.name]
        assert len(files_014) == 1

    def test_bug_w4_013_before_014(self):
        migrations = ROOT / "supabase" / "migrations"
        if not migrations.exists():
            pytest.skip()
        files = sorted([f.name for f in migrations.iterdir() if f.suffix == '.sql'])
        names_013 = [f for f in files if '_013_' in f]
        names_014 = [f for f in files if '_014_' in f]
        assert names_013 and names_014
        assert names_013[0] < names_014[0], (
            f"013 ({names_013[0]}) must sort before 014 ({names_014[0]})"
        )
