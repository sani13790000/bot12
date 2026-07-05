"""
test_phase_x_final.py
Phase X final tests: BUG-X1 (double prefix), BUG-X2 (fake JWT), BUG-X3 (migration_024 path)

BUG-X1: billing.py APIRouter no longer has prefix="/billing"
         (main.py provides prefix — was causing /billing/billing/* double prefix)
BUG-X2: _get_current_user_id() and _require_admin() now use real Depends(get_current_user)
         (old code returned hardcoded strings without decoding JWT)
BUG-X3: migration_024.sql tables (ml_models, decisions, session_events, db_health_log)
         now live in supabase/migrations/20260623_024b_phase_s_ml_tables.sql
         (old file was in backend/database/migrations/ which Supabase CLI never scans)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BILLING_FILE = ROOT / "backend" / "api" / "routes" / "billing.py"
MIGRATION_DIR = ROOT / "supabase" / "migrations"
MIGRATION_024B = MIGRATION_DIR / "20260623_024b_phase_s_ml_tables.sql"
MIGRATION_024A = MIGRATION_DIR / "20260623_024_phase_s_hardening.sql"


# ===========================================================================
# TestBugX1BillingDoublePrefix
# ===========================================================================
class TestBugX1BillingDoublePrefix:
    """BUG-X1: billing.py router must NOT define prefix='/billing' —
    main.py already passes prefix='/billing' to include_router."""

    def test_billing_file_exists(self):
        assert BILLING_FILE.exists(), "billing.py route file must exist"

    def test_no_prefix_in_router_definition(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        # router = APIRouter(...) must NOT have prefix="/billing"
        # Allow prefix in comments but not in the actual APIRouter() call
        lines = src.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "APIRouter(" in line and 'prefix="/billing"' in line:
                pytest.fail(
                    f"BUG-X1 still present: APIRouter has prefix='/billing' — "
                    f"causes double prefix /billing/billing/*\nLine: {line.strip()}"
                )

    def test_router_has_no_prefix_arg(self):
        """Confirm router = APIRouter(tags=[...]) without prefix."""
        src = BILLING_FILE.read_text(encoding="utf-8")
        # Find the router assignment line
        for line in src.splitlines():
            if re.match(r'^router\s*=\s*APIRouter\(', line.strip()):
                assert 'prefix=' not in line, (
                    f"BUG-X1: router definition still has prefix arg: {line.strip()}"
                )
                return
        # if not found on one line, check multiline — just ensure no prefix=/billing
        match = re.search(r'router\s*=\s*APIRouter\([^)]+\)', src, re.DOTALL)
        if match:
            assert 'prefix=' not in match.group(), "BUG-X1: router has prefix arg"

    def test_endpoints_reachable_without_double_prefix(self):
        """Endpoints like /checkout should exist directly under the billing router."""
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert '@router.post("/checkout"' in src, "checkout endpoint must be defined"
        assert '@router.get("/subscription"' in src, "subscription endpoint must be defined"
        assert '@router.get("/invoices"' in src, "invoices endpoint must be defined"

    def test_billing_file_valid_python(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"billing.py has syntax error: {e}")


# ===========================================================================
# TestBugX2FakeJWTAuth
# ===========================================================================
class TestBugX2FakeJWTAuth:
    """BUG-X2: _get_current_user_id() and _require_admin() must NOT
    return hardcoded strings. They must use real JWT via get_current_user."""

    def test_no_user_from_jwt_hardcode(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert '"user_from_jwt"' not in src, (
            'BUG-X2 still present: hardcoded "user_from_jwt" found in billing.py'
        )

    def test_no_admin_user_hardcode(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert '"admin_user"' not in src, (
            'BUG-X2 still present: hardcoded "admin_user" found in billing.py'
        )

    def test_get_current_user_imported(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert 'get_current_user' in src, (
            "BUG-X2: get_current_user must be imported and used in billing.py"
        )

    def test_depends_get_current_user_used(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert 'Depends(get_current_user)' in src, (
            "BUG-X2: Depends(get_current_user) must be used in _get_current_user_id or _require_admin"
        )

    def test_require_admin_checks_role(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        # _require_admin must check role attribute
        assert 'role' in src, (
            "BUG-X2: _require_admin must check user role attribute"
        )
        assert 'HTTP_403_FORBIDDEN' in src or '403' in src, (
            "BUG-X2: _require_admin must raise 403 for non-admin users"
        )

    def test_get_current_user_from_core_deps(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert 'core.deps' in src or 'from ...core.deps' in src, (
            "BUG-X2: get_current_user must be imported from backend.core.deps"
        )


# ===========================================================================
# TestBugX3Migration024Path
# ===========================================================================
class TestBugX3Migration024Path:
    """BUG-X3: ml_models, decisions, session_events, db_health_log tables
    must be in supabase/migrations/ (not backend/database/migrations/)."""

    def test_migration_024b_exists(self):
        assert MIGRATION_024B.exists(), (
            f"BUG-X3: {MIGRATION_024B.name} must exist in supabase/migrations/"
        )

    def test_ml_models_table_in_024b(self):
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        assert 'ml_models' in sql, "BUG-X3: ml_models table must be in 024b migration"
        assert 'CREATE TABLE IF NOT EXISTS ml_models' in sql

    def test_decisions_table_in_024b(self):
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        assert 'decisions' in sql, "BUG-X3: decisions table must be in 024b migration"

    def test_session_events_in_024b(self):
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        assert 'session_events' in sql, "BUG-X3: session_events must be in 024b migration"

    def test_db_health_log_in_024b(self):
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        assert 'db_health_log' in sql, "BUG-X3: db_health_log must be in 024b migration"

    def test_024b_non_overlapping_with_024a(self):
        """024b must NOT duplicate tables already in 024a (refresh_tokens, audit indexes)."""
        if not MIGRATION_024A.exists():
            pytest.skip("024a not found")
        sql_b = MIGRATION_024B.read_text(encoding="utf-8")
        # 024a has refresh_tokens — 024b must NOT redefine it
        assert 'CREATE TABLE IF NOT EXISTS refresh_tokens' not in sql_b, (
            "BUG-X3: 024b must not duplicate refresh_tokens from 024a"
        )

    def test_024b_has_begin_commit(self):
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        assert 'BEGIN;' in sql, "migration 024b must have BEGIN;"
        assert 'COMMIT;' in sql, "migration 024b must have COMMIT;"

    def test_024b_sort_order_after_024a(self):
        """024b must sort after 024a alphabetically."""
        files = sorted(p.name for p in MIGRATION_DIR.glob("*.sql"))
        names_024 = [f for f in files if '_024' in f]
        assert len(names_024) >= 2, f"Expected at least 2 migration 024 files, got: {names_024}"
        idx_a = next((i for i, f in enumerate(files) if '024_phase_s_hardening' in f), None)
        idx_b = next((i for i, f in enumerate(files) if '024b_phase_s_ml_tables' in f), None)
        assert idx_a is not None, "024a not found in migration dir"
        assert idx_b is not None, "024b not found in migration dir"
        assert idx_b > idx_a, f"BUG-X3: 024b ({idx_b}) must sort after 024a ({idx_a})"


# ===========================================================================
# TestPhaseXSummary
# ===========================================================================
class TestPhaseXSummary:
    """Phase X: all 3 bugs verified fixed."""

    def test_billing_no_double_prefix(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        for line in src.splitlines():
            if line.strip().startswith("#"):
                continue
            if "APIRouter(" in line and 'prefix="/billing"' in line:
                pytest.fail("BUG-X1 regression: double prefix still present")

    def test_billing_no_fake_auth(self):
        src = BILLING_FILE.read_text(encoding="utf-8")
        assert '"user_from_jwt"' not in src, "BUG-X2 regression: fake user_id"
        assert '"admin_user"' not in src, "BUG-X2 regression: fake admin"

    def test_migration_024b_complete(self):
        assert MIGRATION_024B.exists()
        sql = MIGRATION_024B.read_text(encoding="utf-8")
        for table in ('ml_models', 'decisions', 'session_events', 'db_health_log'):
            assert table in sql, f"BUG-X3: {table} missing from 024b"

    def test_phase_x_all_bugs_fixed(self):
        """Composite: all phase X bugs fixed."""
        src = BILLING_FILE.read_text(encoding="utf-8")
        bugs_found = []
        # X1
        for line in src.splitlines():
            if line.strip().startswith("#"): continue
            if "APIRouter(" in line and 'prefix="/billing"' in line:
                bugs_found.append("X1: double prefix")
                break
        # X2
        if '"user_from_jwt"' in src:
            bugs_found.append("X2: fake user_id")
        if '"admin_user"' in src:
            bugs_found.append("X2: fake admin")
        # X3
        if not MIGRATION_024B.exists():
            bugs_found.append("X3: 024b migration missing")
        assert not bugs_found, f"Phase X bugs still present: {bugs_found}"
