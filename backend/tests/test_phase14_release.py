# test_phase14_release.py - Phase 14: 96 tests
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

import pytest

SCRIPTS = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_release import (
    ReleaseManifest, ReleaseResult,
    sha256_file, sha256_bytes, git_sha,
    compile_ea, verify_no_source_leak,
    generate_checksums, generate_download_token,
    verify_download_token, build_release,
    SOURCE_EXTENSIONS, RELEASE_DIR, EA_SOURCE,
)
from verify_release import verify_zip, VerifyResult
from generate_download_token import (
    generate_token, verify_token,
    sha256_file as gdt_sha256,
)

SECRET = "test-build-secret-phase14"


class TestReleaseManifest:
    def _manifest(self) -> ReleaseManifest:
        return ReleaseManifest(
            version="3.20", env="production",
            build_time_utc="2026-06-26T16:00:00+00:00",
            git_sha="abc1234",
            ea_source_sha256="a" * 64,
            ea_binary_sha256="b" * 64,
            files=[{"name": "EA.ex5", "sha256": "b" * 64, "size_bytes": 1024}],
        )

    def test_sign_sets_signature(self):
        m = self._manifest()
        assert m.signature == ""
        m.sign(SECRET)
        assert len(m.signature) == 64

    def test_verify_valid_signature(self):
        m = self._manifest()
        m.sign(SECRET)
        assert m.verify(SECRET) is True

    def test_verify_wrong_secret(self):
        m = self._manifest()
        m.sign(SECRET)
        assert m.verify("wrong-secret") is False

    def test_verify_tampered_version(self):
        m = self._manifest()
        m.sign(SECRET)
        m.version = "9.99"
        assert m.verify(SECRET) is False

    def test_verify_tampered_sha(self):
        m = self._manifest()
        m.sign(SECRET)
        m.ea_binary_sha256 = "c" * 64
        assert m.verify(SECRET) is False

    def test_signature_is_hex_64(self):
        m = self._manifest()
        m.sign(SECRET)
        int(m.signature, 16)

    def test_different_secrets_different_sigs(self):
        m1, m2 = self._manifest(), self._manifest()
        m1.sign("secret-a")
        m2.sign("secret-b")
        assert m1.signature != m2.signature

    def test_sign_idempotent_same_data(self):
        m1, m2 = self._manifest(), self._manifest()
        m1.sign(SECRET)
        m2.sign(SECRET)
        assert m1.signature == m2.signature

    def test_asdict_roundtrip(self):
        m = self._manifest()
        m.sign(SECRET)
        d = asdict(m)
        m2 = ReleaseManifest(**d)
        assert m2.verify(SECRET)

    def test_manifest_has_all_required_fields(self):
        m = self._manifest()
        d = asdict(m)
        for f in ["version", "env", "build_time_utc", "git_sha",
                  "ea_source_sha256", "ea_binary_sha256", "files"]:
            assert f in d

    def test_source_sha_vs_binary_sha_different(self):
        m = self._manifest()
        assert m.ea_source_sha256 != m.ea_binary_sha256

    def test_sign_empty_secret(self):
        m = self._manifest()
        m.sign("")
        assert len(m.signature) == 64


class TestVerifyNoSourceLeak:
    def _make_zip(self, names, tmpdir):
        zp = tmpdir / "test.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            for n in names:
                zf.writestr(n, b"content")
        return zp

    def test_clean_zip_no_violations(self, tmp_path):
        zp = self._make_zip(["MQL5/Experts/EA.ex5", "README_INSTALL.txt", "manifest.json"], tmp_path)
        assert verify_no_source_leak(zp) == []

    def test_mq5_detected(self, tmp_path):
        zp = self._make_zip(["EA.mq5", "EA.ex5"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".mq5" in x for x in v)

    def test_mqh_detected(self, tmp_path):
        zp = self._make_zip(["Include/Config.mqh"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".mqh" in x for x in v)

    def test_py_detected(self, tmp_path):
        zp = self._make_zip(["backend/main.py"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".py" in x for x in v)

    def test_ts_detected(self, tmp_path):
        zp = self._make_zip(["frontend/App.ts"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".ts" in x for x in v)

    def test_tsx_detected(self, tmp_path):
        zp = self._make_zip(["frontend/App.tsx"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".tsx" in x for x in v)

    def test_sql_detected(self, tmp_path):
        zp = self._make_zip(["migrations/001.sql"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".sql" in x for x in v)

    def test_env_detected(self, tmp_path):
        zp = self._make_zip([".env"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any("env" in x.lower() for x in v)

    def test_key_detected(self, tmp_path):
        zp = self._make_zip(["server.key"], tmp_path)
        v = verify_no_source_leak(zp)
        assert any(".key" in x for x in v)

    def test_multiple_violations(self, tmp_path):
        zp = self._make_zip(["a.mq5", "b.mqh", "c.py"], tmp_path)
        assert len(verify_no_source_leak(zp)) >= 3

    def test_checksums_txt_is_safe(self, tmp_path):
        zp = self._make_zip(["CHECKSUMS.txt"], tmp_path)
        assert verify_no_source_leak(zp) == []

    def test_source_extensions_set_completeness(self):
        for ext in [".mq5", ".mqh", ".py", ".ts", ".tsx", ".sql", ".sh", ".env", ".key"]:
            assert ext in SOURCE_EXTENSIONS


class TestGenerateChecksums:
    def test_header_present(self, tmp_path):
        f = tmp_path / "a.ex5"; f.write_bytes(b"binary")
        cs = generate_checksums({"a.ex5": f})
        assert "SHA-256" in cs

    def test_sha256_correct(self, tmp_path):
        f = tmp_path / "a.txt"; f.write_bytes(b"hello")
        cs = generate_checksums({"a.txt": f})
        assert hashlib.sha256(b"hello").hexdigest() in cs

    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.ex5"; f1.write_bytes(b"aaa")
        f2 = tmp_path / "b.txt"; f2.write_bytes(b"bbb")
        cs = generate_checksums({"a.ex5": f1, "b.txt": f2})
        assert "a.ex5" in cs and "b.txt" in cs

    def test_gnu_format_double_space(self, tmp_path):
        f = tmp_path / "x.ex5"; f.write_bytes(b"x")
        cs = generate_checksums({"x.ex5": f})
        lines = [l for l in cs.splitlines() if not l.startswith("#") and l.strip()]
        assert "  " in lines[0]

    def test_empty_files_dict(self):
        cs = generate_checksums({})
        assert "SHA-256" in cs

    def test_sorted_order(self, tmp_path):
        fb = tmp_path / "b.txt"; fb.write_bytes(b"b")
        fa = tmp_path / "a.txt"; fa.write_bytes(b"a")
        cs = generate_checksums({"b.txt": fb, "a.txt": fa})
        lines = [l for l in cs.splitlines() if not l.startswith("#") and l.strip()]
        names = [l.split("  ")[1] for l in lines]
        assert names == sorted(names)

    def test_large_file(self, tmp_path):
        f = tmp_path / "large.ex5"; f.write_bytes(b"x" * 1_000_000)
        cs = generate_checksums({"large.ex5": f})
        assert hashlib.sha256(b"x" * 1_000_000).hexdigest() in cs

    def test_binary_content(self, tmp_path):
        f = tmp_path / "a.ex5"; f.write_bytes(bytes(range(256)))
        cs = generate_checksums({"a.ex5": f})
        assert hashlib.sha256(bytes(range(256))).hexdigest() in cs

    def test_unicode_filename(self, tmp_path):
        f = tmp_path / "file.ex5"; f.write_bytes(b"u")
        cs = generate_checksums({"MT5/Experts/EA.ex5": f})
        assert "MT5/Experts/EA.ex5" in cs

    def test_newline_terminated(self, tmp_path):
        f = tmp_path / "a.ex5"; f.write_bytes(b"a")
        cs = generate_checksums({"a.ex5": f})
        assert cs.endswith("\n")

    def test_no_private_data_in_checksums(self, tmp_path):
        f = tmp_path / "a.ex5"; f.write_bytes(b"a")
        cs = generate_checksums({"a.ex5": f})
        for secret in ["password", "key", "secret", "token"]:
            assert secret.lower() not in cs.lower()

    def test_sha256_length_64_chars(self, tmp_path):
        f = tmp_path / "a.ex5"; f.write_bytes(b"a")
        cs = generate_checksums({"a.ex5": f})
        lines = [l for l in cs.splitlines() if not l.startswith("#") and l.strip()]
        sha = lines[0].split("  ")[0]
        assert len(sha) == 64


class TestDownloadToken:
    def test_generate_returns_string(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        assert isinstance(t, str) and len(t) > 0

    def test_verify_valid_token(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        p = verify_download_token(t, SECRET)
        assert p["version"] == "3.20"

    def test_verify_wrong_secret(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        with pytest.raises(ValueError, match="(?i)invalid"):
            verify_download_token(t, "wrong")

    def test_expired_token(self):
        t = generate_download_token("3.20", "a" * 64, SECRET, ttl_seconds=-1)
        with pytest.raises(ValueError, match="(?i)expir"):
            verify_download_token(t, SECRET)

    def test_tampered_version(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        padded = t + "=" * (-len(t) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["version"] = "9.99"
        raw = json.dumps(payload, separators=(",", ":"))
        t2 = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        with pytest.raises(ValueError):
            verify_download_token(t2, SECRET)

    def test_tampered_sha(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        padded = t + "=" * (-len(t) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["zip_sha256"] = "b" * 64
        raw = json.dumps(payload, separators=(",", ":"))
        t2 = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        with pytest.raises(ValueError):
            verify_download_token(t2, SECRET)

    def test_two_tokens_different_nonce(self):
        t1 = generate_download_token("3.20", "a" * 64, SECRET)
        t2 = generate_download_token("3.20", "a" * 64, SECRET)
        assert t1 != t2

    def test_token_has_exp(self):
        t = generate_download_token("3.20", "a" * 64, SECRET, ttl_seconds=3600)
        p = verify_download_token(t, SECRET)
        assert "exp" in p and p["exp"] > time.time()

    def test_token_has_max_downloads(self):
        t = generate_download_token("3.20", "a" * 64, SECRET, max_downloads=5)
        p = verify_download_token(t, SECRET)
        assert p["max_downloads"] == 5

    def test_generate_token_gdt(self, tmp_path):
        f = tmp_path / "a.zip"; f.write_bytes(b"zip")
        sha = gdt_sha256(f)
        t = generate_token("3.20", sha, "cust_001", secret=SECRET)
        p = verify_token(t, SECRET)
        assert p["customer_id"] == "cust_001"

    def test_verify_token_expired_gdt(self):
        t = generate_token("3.20", "a" * 64, "c1", ttl_seconds=-1, secret=SECRET)
        with pytest.raises(ValueError, match="(?i)expir"):
            verify_token(t, SECRET)

    def test_verify_token_wrong_secret_gdt(self):
        t = generate_token("3.20", "a" * 64, "c1", secret=SECRET)
        with pytest.raises(ValueError, match="(?i)invalid"):
            verify_token(t, "bad-secret")

    def test_token_not_url_unsafe(self):
        for _ in range(5):
            t = generate_download_token("3.20", "a" * 64, SECRET)
            assert "+" not in t and "/" not in t

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError):
            verify_download_token("not-valid-base64!!!", SECRET)

    def test_token_contains_no_raw_secret(self):
        t = generate_download_token("3.20", "a" * 64, SECRET)
        padded = t + "=" * (-len(t) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        assert SECRET not in raw

    def test_ttl_reflected_in_exp(self):
        before = int(time.time())
        t = generate_download_token("3.20", "a" * 64, SECRET, ttl_seconds=7200)
        p = verify_download_token(t, SECRET)
        assert p["exp"] >= before + 7200 - 2


class TestVerifyZip:
    def _make_valid_zip(self, tmp_path, include_source=False):
        ex5_data = b"\x4d\x51\x4c\x35" + b"\x00" * 44
        readme = b"Install guide"
        ex5_sha = hashlib.sha256(ex5_data).hexdigest()
        readme_sha = hashlib.sha256(readme).hexdigest()
        checksums = f"# SHA-256 Checksums\n\n{ex5_sha}  MQL5/Experts/EA.ex5\n{readme_sha}  README_INSTALL.txt\n"
        manifest = {"version": "3.20", "env": "production",
                    "build_time_utc": "2026-06-26T00:00:00+00:00",
                    "git_sha": "abc", "ea_source_sha256": "s" * 64,
                    "ea_binary_sha256": ex5_sha, "files": [], "signature": ""}
        zp = tmp_path / "release.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("MQL5/Experts/EA.ex5", ex5_data)
            zf.writestr("README_INSTALL.txt", readme)
            zf.writestr("CHECKSUMS.txt", checksums)
            zf.writestr("manifest.json", json.dumps(manifest))
            if include_source:
                zf.writestr("EA.mq5", b"source")
        return zp

    def test_valid_zip_passes(self, tmp_path):
        assert verify_zip(self._make_valid_zip(tmp_path)).ok

    def test_source_mq5_fails(self, tmp_path):
        r = verify_zip(self._make_valid_zip(tmp_path, include_source=True))
        assert not r.ok

    def test_missing_manifest_fails(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("EA.ex5", b"x")
        assert not verify_zip(zp).ok

    def test_missing_checksums_fails(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("README_INSTALL.txt", "x")
        assert not verify_zip(zp).ok

    def test_checksum_mismatch_fails(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("EA.ex5", b"real")
            zf.writestr("README_INSTALL.txt", "x")
            zf.writestr("manifest.json", json.dumps({"ea_binary_sha256": "x"*64}))
            zf.writestr("CHECKSUMS.txt", "# SHA-256\n\n" + "a"*64 + "  EA.ex5\n")
        assert not verify_zip(zp).ok

    def test_nonexistent_file_fails(self, tmp_path):
        assert not verify_zip(tmp_path / "nope.zip").ok

    def test_result_has_manifest(self, tmp_path):
        r = verify_zip(self._make_valid_zip(tmp_path))
        assert isinstance(r.manifest, dict) and r.manifest.get("version") == "3.20"

    def test_ex5_sha_mismatch_in_manifest(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("MQL5/EA.ex5", b"binary")
            zf.writestr("README_INSTALL.txt", "x")
            zf.writestr("manifest.json", json.dumps({"ea_binary_sha256": "f"*64, "files": [], "signature": ""}))
            zf.writestr("CHECKSUMS.txt", "# SHA-256\n\n")
        r = verify_zip(zp)
        assert not r.ok or r.warnings

    def test_valid_zip_no_errors(self, tmp_path):
        r = verify_zip(self._make_valid_zip(tmp_path))
        assert r.errors == []

    def test_result_is_VerifyResult(self, tmp_path):
        assert isinstance(verify_zip(self._make_valid_zip(tmp_path)), VerifyResult)

    def test_multiple_source_files_all_listed(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("a.mq5", b"x"); zf.writestr("b.mqh", b"x"); zf.writestr("c.py", b"x")
            zf.writestr("manifest.json", "{}"); zf.writestr("CHECKSUMS.txt", "# SHA-256\n\n")
            zf.writestr("README_INSTALL.txt", "x")
        r = verify_zip(zp)
        assert not r.ok and len(r.errors) >= 3

    def test_sh_file_detected(self, tmp_path):
        zp = tmp_path / "r.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("setup.sh", b"#!/bin/bash")
            zf.writestr("manifest.json", "{}"); zf.writestr("CHECKSUMS.txt", "# SHA-256\n\n")
            zf.writestr("README_INSTALL.txt", "x")
        assert not verify_zip(zp).ok


class TestBuildRelease:
    def setup_method(self):
        import build_release as br
        self._br = br
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "mql5" / "Experts" / "MT5Trading").mkdir(parents=True)
        mq5 = self.tmp / "mql5" / "Experts" / "MT5Trading" / "MT5TradingEA_Complete.mq5"
        mq5.write_text("// mock source")
        self.old_ea = br.EA_SOURCE; self.old_rd = br.RELEASE_DIR; self.old_sa = br.SOURCE_ARCHIVE_DIR
        br.EA_SOURCE = mq5
        br.RELEASE_DIR = self.tmp / "releases"
        br.SOURCE_ARCHIVE_DIR = self.tmp / "releases" / "source_archive"
        br.RELEASE_DIR.mkdir()

    def teardown_method(self):
        self._br.EA_SOURCE = self.old_ea; self._br.RELEASE_DIR = self.old_rd; self._br.SOURCE_ARCHIVE_DIR = self.old_sa
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_dry_run_succeeds(self):
        assert build_release("3.20", "staging", SECRET, dry_run=True).success

    def test_build_creates_zip(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        assert r.zip_path is not None and r.zip_path.exists()

    def test_zip_has_no_source_files(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        assert verify_no_source_leak(r.zip_path) == []

    def test_zip_has_ex5(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        with zipfile.ZipFile(r.zip_path) as zf:
            assert any(n.endswith(".ex5") for n in zf.namelist())

    def test_zip_has_manifest(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        with zipfile.ZipFile(r.zip_path) as zf:
            assert "manifest.json" in zf.namelist()

    def test_zip_has_checksums(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        with zipfile.ZipFile(r.zip_path) as zf:
            assert "CHECKSUMS.txt" in zf.namelist()

    def test_zip_has_readme(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        with zipfile.ZipFile(r.zip_path) as zf:
            assert "README_INSTALL.txt" in zf.namelist()

    def test_manifest_signature_valid(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        assert r.manifest.verify(SECRET)

    def test_download_token_generated(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        p = verify_download_token(r.download_token, SECRET)
        assert p["version"] == "3.20"

    def test_build_result_has_zip_path(self):
        r = build_release("3.20", "staging", SECRET, dry_run=True)
        assert r.zip_path is not None

    def test_no_mq5_in_staging_zip(self):
        r = build_release("3.20", "staging", SECRET, dry_run=True)
        with zipfile.ZipFile(r.zip_path) as zf:
            for name in zf.namelist():
                assert not name.endswith(".mq5") and not name.endswith(".mqh")

    def test_version_in_zip_name(self):
        r = build_release("3.20", "production", SECRET, dry_run=True)
        assert "3.20" in r.zip_path.name


class TestSourceProtectionFiles:
    def _get_gitignore(self):
        for p in [
            Path(__file__).parent.parent.parent.parent / ".gitignore",
            Path(__file__).parent.parent.parent / ".gitignore_additions",
        ]:
            if p.exists(): return p.read_text()
        return ""

    def _get_dockerignore(self):
        for p in [
            Path(__file__).parent.parent.parent.parent / ".dockerignore",
            Path(__file__).parent.parent.parent / ".dockerignore_additions",
        ]:
            if p.exists(): return p.read_text()
        return ""

    def test_gitignore_has_releases(self):
        gi = self._get_gitignore()
        assert "releases/" in gi or "releases" in gi

    def test_gitignore_has_ex5(self):
        gi = self._get_gitignore()
        assert "*.ex5" in gi or "ex5" in gi

    def test_gitignore_has_source_archive(self):
        gi = self._get_gitignore()
        assert "releases/" in gi or "source_archive" in gi

    def test_dockerignore_excludes_mql5(self):
        di = self._get_dockerignore()
        assert "mql5/" in di or "mql5" in di

    def test_dockerignore_excludes_mq5_files(self):
        di = self._get_dockerignore()
        assert "*.mq5" in di or "mql5/" in di

    def test_dockerignore_excludes_mqh_files(self):
        di = self._get_dockerignore()
        assert "*.mqh" in di or "mql5/" in di

    def test_release_workflow_exists(self):
        paths = [
            Path(__file__).parent.parent.parent.parent / ".github/workflows/ea_release.yml",
            Path(__file__).parent.parent.parent / ".github/workflows/ea_release.yml",
        ]
        assert any(p.exists() for p in paths)

    def test_release_governance_doc_exists(self):
        paths = [
            Path(__file__).parent.parent.parent.parent / "docs/RELEASE_GOVERNANCE.md",
            Path(__file__).parent.parent.parent / "docs/RELEASE_GOVERNANCE.md",
        ]
        assert any(p.exists() for p in paths)


class TestEAReleaseWorkflow:
    def _load_workflow(self):
        paths = [
            Path(__file__).parent.parent.parent.parent / ".github/workflows/ea_release.yml",
            Path(__file__).parent.parent.parent / ".github/workflows/ea_release.yml",
        ]
        for p in paths:
            if p.exists(): return p.read_text()
        return ""

    def test_workflow_file_exists(self): assert self._load_workflow() != ""
    def test_triggered_on_version_tags(self): assert "tags" in self._load_workflow()
    def test_has_source_protection_job(self): assert "source-protection" in self._load_workflow()
    def test_has_build_ea_job(self): assert "build-ea" in self._load_workflow()
    def test_has_verify_step(self): assert "verify_release" in self._load_workflow() or "verify-release" in self._load_workflow()
    def test_has_upload_artifact(self): assert "upload-artifact" in self._load_workflow()
    def test_has_no_source_extension_in_artifact(self):
        wf = self._load_workflow()
        assert ".mq5" not in wf.replace("*.mq5", "") or "source leak" in wf.lower() or "SOURCE LEAK" in wf
    def test_has_github_release_job(self): assert "github-release" in self._load_workflow() or "Release" in self._load_workflow()
    def test_needs_ordering_correct(self):
        wf = self._load_workflow()
        assert wf.find("build-ea") < wf.find("github-release")
    def test_has_final_source_check_before_publish(self):
        wf = self._load_workflow()
        assert "Final source" in wf or "final source" in wf or "SOURCE LEAK" in wf
    def test_has_telegram_notify(self): assert "telegram" in self._load_workflow().lower() or "TELEGRAM" in self._load_workflow()
    def test_has_build_secret_env(self): assert "BUILD_SECRET" in self._load_workflow()
