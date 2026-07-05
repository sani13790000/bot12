"""فاز M — Migration Audit Tests (v2)
هدف: بررسی تضاد شماره، فایل‌های placeholder و SQL content
"""
import pytest
import os
import re
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent.parent / "supabase" / "migrations"


class TestMigrationFileStructure:
    """بررسی ساختار فایل‌های migration"""

    def test_migrations_dir_exists(self):
        assert MIGRATIONS_DIR.exists(), f"پوشه migrations وجود ندارد: {MIGRATIONS_DIR}"

    def test_migrations_dir_has_sql_files(self):
        sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
        assert len(sql_files) > 0, "هیچ فایل SQL در migrations وجود ندارد"

    def test_minimum_migration_count(self):
        """حداقل 40 فایل migration باید وجود داشته باشد"""
        sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
        assert len(sql_files) >= 40, f"تعداد migrations: {len(sql_files)} — انتظار: حداقل 40"


class TestMigrationNumberConflicts:
    """بررسی تضاد شماره‌گذاری"""

    def _get_prefix_map(self):
        """prefix سه رقمی اول هر فایل را استخراج کن"""
        prefix_map = {}
        for f in MIGRATIONS_DIR.glob("*.sql"):
            match = re.search(r'_(\d{3})[^\d]', f.name)
            if match:
                num = match.group(1)
                if num not in prefix_map:
                    prefix_map[num] = []
                prefix_map[num].append(f.name)
        return prefix_map

    def test_no_true_number_conflicts(self):
        """فایل‌هایی که prefix یکسان دارند باید a/b suffix داشته باشند"""
        prefix_map = self._get_prefix_map()
        conflicts = {}
        for num, files in prefix_map.items():
            if len(files) > 1:
                # بررسی کن a/b suffix دارند
                has_suffix = all(re.search(r'_0*' + num + r'[ab]_', f) for f in files)
                if not has_suffix:
                    conflicts[num] = files
        assert len(conflicts) == 0, \
            f"تضاد شماره در migrations: {conflicts}"

    def test_019_files_have_ab_suffix(self):
        """migration 019 باید a/b suffix داشته باشد"""
        files_019 = [f.name for f in MIGRATIONS_DIR.glob("*_019*.sql")]
        if len(files_019) > 1:
            for f in files_019:
                assert re.search(r'_019[ab]_', f) or re.search(r'_019_', f), \
                    f"فایل 019 بدون a/b suffix: {f}"

    def test_025_files_have_ab_suffix(self):
        """migration 025 باید a/b suffix داشته باشد"""
        files_025 = [f.name for f in MIGRATIONS_DIR.glob("*_025*.sql")]
        if len(files_025) > 1:
            for f in files_025:
                assert re.search(r'_025[ab]_', f) or re.search(r'_025_', f), \
                    f"فایل 025 بدون a/b suffix: {f}"

    def test_no_orphan_migration_in_root(self):
        """migration_025.sql یا فایل‌های مشابه در root نباید باشند"""
        root = MIGRATIONS_DIR.parent.parent
        orphans = list(root.glob("migration_*.sql"))
        assert len(orphans) == 0, f"فایل‌های orphan migration در root: {orphans}"


class TestMigrationContent:
    """بررسی محتوای SQL فایل‌ها"""

    def test_no_purely_placeholder_migrations(self):
        """فایل‌های migration نباید فقط comment باشند"""
        placeholder_files = []
        for f in MIGRATIONS_DIR.glob("*.sql"):
            content = f.read_text(encoding="utf-8").strip()
            # فایل‌هایی که فقط comment یا SELECT ساده دارند
            lines = [l.strip() for l in content.splitlines()
                     if l.strip() and not l.strip().startswith("--")]
            if len(lines) == 0:
                placeholder_files.append(f.name)
            elif len(lines) == 1 and lines[0].lower().startswith("select") and len(lines[0]) < 50:
                placeholder_files.append(f.name)
        assert len(placeholder_files) == 0, \
            f"فایل‌های placeholder: {placeholder_files}"

    def test_migrations_have_reasonable_size(self):
        """هر فایل migration باید حداقل 50 بایت داشته باشد"""
        tiny_files = []
        for f in MIGRATIONS_DIR.glob("*.sql"):
            if f.stat().st_size < 50:
                tiny_files.append(f"{f.name} ({f.stat().st_size} bytes)")
        assert len(tiny_files) == 0, f"فایل‌های خیلی کوچک: {tiny_files}"

    def test_no_unsafe_drop_without_if_exists(self):
        """DROP TABLE بدون IF EXISTS ریسک production دارد"""
        unsafe = []
        for f in MIGRATIONS_DIR.glob("*.sql"):
            content = f.read_text(encoding="utf-8")
            drops = re.findall(r'DROP\s+TABLE\s+(?!IF\s+EXISTS)', content, re.IGNORECASE)
            if drops:
                unsafe.append(f.name)
        assert len(unsafe) == 0, f"فایل‌های دارای DROP ناامن: {unsafe}"
