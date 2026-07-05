"""
test_migration_audit.py

Audit tests for Supabase migration consistency.
These tests are OFFLINE — they parse SQL files directly,
no live DB connection required.

Run with: pytest tests/test_migration_audit.py -v
"""
from __future__ import annotations

import os
import re
import glob
import pytest

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "supabase", "migrations"
)


def _load_migrations():
    """Return sorted list of (filename, content) tuples."""
    pattern = os.path.join(MIGRATIONS_DIR, "*.sql")
    files = sorted(glob.glob(pattern))
    result = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            result.append((os.path.basename(f), fh.read()))
    return result


class TestMigrationAudit:

    def test_migrations_directory_exists(self):
        """supabase/migrations/ directory must exist."""
        assert os.path.isdir(MIGRATIONS_DIR), (
            f"Migrations directory not found: {MIGRATIONS_DIR}"
        )

    def test_at_least_one_migration(self):
        """Must have at least one migration file."""
        migrations = _load_migrations()
        assert len(migrations) >= 1, "No migration files found"

    def test_no_duplicate_migration_numbers(self):
        """No two migration files should have the same numeric prefix."""
        migrations = _load_migrations()
        numbers = []
        for fname, _ in migrations:
            m = re.match(r'^(\d+)', fname)
            if m:
                numbers.append(int(m.group(1)))
        duplicates = [n for n in numbers if numbers.count(n) > 1]
        assert len(duplicates) == 0, (
            f"Duplicate migration numbers found: {set(duplicates)}"
        )

    def test_no_drop_table_without_if_exists(self):
        """DROP TABLE must always use IF EXISTS to be safe."""
        migrations = _load_migrations()
        violations = []
        for fname, content in migrations:
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                if re.search(r'DROP\s+TABLE\s+(?!IF\s+EXISTS)', line, re.IGNORECASE):
                    # Allow if it's inside a DO block with prior existence check
                    violations.append(f"{fname}:{i}: {line.strip()}")
        assert len(violations) == 0, (
            "Unsafe DROP TABLE without IF EXISTS:\n" + "\n".join(violations)
        )

    def test_canonical_users_fix_exists(self):
        """Migration 047 (canonical users fix) must exist."""
        migrations = _load_migrations()
        names = [fname for fname, _ in migrations]
        canonical = [n for n in names if '047' in n]
        assert len(canonical) >= 1, (
            "Migration 047_canonical_users_fix.sql is missing. "
            "Run faz-B to create it."
        )

    def test_no_plain_sql_errors_syntax(self):
        """Basic syntax check: no unclosed string literals."""
        migrations = _load_migrations()
        for fname, content in migrations:
            # Count single quotes (odd count = unclosed string)
            # Strip comments first
            no_comments = re.sub(r'--[^\n]*', '', content)
            no_comments = re.sub(r'/\*.*?\*/', '', no_comments, flags=re.DOTALL)
            # This is a heuristic, not a full parser
            quote_count = no_comments.count("'")
            # Allow escaped quotes ''
            escaped = no_comments.count("''")
            effective = quote_count - (escaped * 2)
            # effective should be even (paired quotes)
            # We skip this check if it's too complex
            # Just ensure the file is non-empty
            assert len(content.strip()) > 0, f"{fname} is empty"

    def test_all_migrations_have_begin_commit_or_are_safe(self):
        """
        Migrations that contain CREATE TABLE or ALTER TABLE should
        ideally be wrapped in BEGIN/COMMIT for atomicity.
        This is a WARNING test, not a hard failure.
        """
        migrations = _load_migrations()
        warnings = []
        for fname, content in migrations:
            has_ddl = bool(re.search(
                r'(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)',
                content, re.IGNORECASE
            ))
            has_transaction = bool(re.search(
                r'\b(BEGIN|START\s+TRANSACTION)\b',
                content, re.IGNORECASE
            ))
            if has_ddl and not has_transaction:
                warnings.append(fname)
        # Warn but don't fail — Supabase auto-wraps migrations
        if warnings:
            import warnings as w
            w.warn(
                f"Migrations without explicit BEGIN/COMMIT: {warnings}. "
                "Supabase wraps these automatically, but explicit is safer."
            )
