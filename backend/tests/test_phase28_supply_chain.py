from __future__ import annotations

import copy
import hashlib
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from backend.core.supply_chain import (
    BANNED_PACKAGES,
    UNSAFE_PATTERNS,
    BuildRecord,
    BuildReproducer,
    BuildSignatureError,
    BuildSigner,
    BuildStatus,
    DependencyPinner,
    DepSpec,
    DriftDetector,
    DriftItem,
    DriftKind,
    DynamicLoadScanner,
    DynamicLoadViolation,
    LockfileEntry,
    LockfileIntegrity,
    PinStatus,
    ScanPattern,
    SupplyChainAuditChain,
    SupplyChainSystem,
    VulnerabilityScanner,
    VulnRecord,
    VulnSeverity,
)


def make_entry(name, version, sha256=None):
    return LockfileEntry(
        name=name,
        version=version,
        sha256=sha256 or hashlib.sha256(f"{name}{version}".encode()).hexdigest(),
    )


def make_spec(name, version, pin_op="=="):
    return DepSpec(name=name, version=version, pin_op=pin_op)


def make_vuln(cve_id, package, version, severity=VulnSeverity.HIGH):
    return VulnRecord(
        cve_id=cve_id,
        package=package,
        affected_versions=[version],
        severity=severity,
        description="test vuln",
    )


SAMPLE_REQS = "fastapi==0.115.0\nuvicorn==0.30.6\npydantic==2.9.2\nredis==5.1.1\nhttpx==0.28.0\n"
PINNED_REQS = "fastapi==0.115.0\npydantic==2.9.2\n"
UNPINNED_REQS = "fastapi>=0.100.0\npydantic~=2.0\nrequests\n"
BANNED_REQS = "fastapi==0.115.0\ndebug-toolbar==1.0.0\n"


class TestEnumsAndConstants:
    def test_T001_vuln_severity_values(self):
        assert VulnSeverity.CRITICAL.value == "critical"

    def test_T002_pin_status_values(self):
        assert PinStatus.PINNED.value == "pinned"

    def test_T003_build_status_values(self):
        assert BuildStatus.UNSIGNED.value == "unsigned"

    def test_T004_drift_kind_values(self):
        assert DriftKind.ADDED.value == "added"

    def test_T005_scan_pattern_exec(self):
        assert ScanPattern.EXEC.value == "exec("

    def test_T006_scan_pattern_eval(self):
        assert ScanPattern.EVAL.value == "eval("

    def test_T007_scan_pattern_pickle(self):
        assert ScanPattern.PICKLE_LOAD.value == "pickle.loads"

    def test_T008_unsafe_patterns_list(self):
        assert "exec(" in UNSAFE_PATTERNS and len(UNSAFE_PATTERNS) >= 8

    def test_T009_banned_packages_list(self):
        assert "debug-toolbar" in [b.lower() for b in BANNED_PACKAGES]

    def test_T010_dep_spec_pinned_true(self):
        assert make_spec("fastapi", "0.115.0", "==").pinned is True

    def test_T011_dep_spec_pinned_false(self):
        assert make_spec("fastapi", "0.100.0", ">=").pinned is False

    def test_T012_dep_spec_req_string(self):
        assert make_spec("fastapi", "0.115.0", "==").req_string == "fastapi==0.115.0"

    def test_T013_dep_spec_extras(self):
        s = DepSpec(name="uvicorn", version="0.30.6", pin_op="==", extras=["standard"])
        assert s.req_string == "uvicorn[standard]==0.30.6"

    def test_T014_lockfile_entry_verify_hash_ok(self):
        h = hashlib.sha256(b"wheel").hexdigest()
        e = LockfileEntry(name="pkg", version="1.0", sha256=h)
        assert e.verify_hash(h) is True

    def test_T015_lockfile_entry_verify_hash_fail(self):
        h = hashlib.sha256(b"wheel").hexdigest()
        e = LockfileEntry(name="pkg", version="1.0", sha256=h)
        assert e.verify_hash("deadbeef" * 8) is False

    def test_T016_vuln_record_affects(self):
        v = make_vuln("CVE-2024-001", "fastapi", "0.100.0")
        assert v.affects("0.100.0") is True and v.affects("0.115.0") is False


class TestLockfileIntegrity:
    def setup_method(self):
        self.lf = LockfileIntegrity()
        self.entries = [
            make_entry("fastapi", "0.115.0"),
            make_entry("pydantic", "2.9.2"),
            make_entry("redis", "5.1.1"),
        ]

    def test_T017_record_returns_64char(self):
        assert len(self.lf.record(self.entries)) == 64

    def test_T018_verify_same_entries_true(self):
        self.lf.record(self.entries)
        assert self.lf.verify(self.entries) is True

    def test_T019_verify_different_entries_false(self):
        self.lf.record(self.entries)
        assert self.lf.verify(self.entries + [make_entry("evil", "0.1.0")]) is False

    def test_T020_verify_no_record_false(self):
        assert LockfileIntegrity().verify(self.entries) is False

    def test_T021_stored_hash_after_record(self):
        h = self.lf.record(self.entries)
        assert self.lf.stored_hash == h

    def test_T022_stored_hash_none_before_record(self):
        assert LockfileIntegrity().stored_hash is None

    def test_T023_get_entry_found(self):
        self.lf.record(self.entries)
        assert self.lf.get_entry("fastapi").version == "0.115.0"

    def test_T024_get_entry_not_found(self):
        self.lf.record(self.entries)
        assert self.lf.get_entry("nonexistent") is None

    def test_T025_version_change_detected(self):
        self.lf.record(self.entries)
        assert (
            self.lf.verify(
                [
                    make_entry("fastapi", "0.200.0"),
                    make_entry("pydantic", "2.9.2"),
                    make_entry("redis", "5.1.1"),
                ]
            )
            is False
        )

    def test_T026_hash_change_detected(self):
        self.lf.record(self.entries)
        assert (
            self.lf.verify(
                [
                    LockfileEntry("fastapi", "0.115.0", sha256="a" * 64),
                    make_entry("pydantic", "2.9.2"),
                    make_entry("redis", "5.1.1"),
                ]
            )
            is False
        )

    def test_T027_order_independent(self):
        self.lf.record(self.entries)
        assert self.lf.verify(list(reversed(self.entries))) is True

    def test_T028_concurrent_record_and_verify(self):
        errors = []

        def worker(i):
            try:
                self.lf.record([make_entry(f"pkg{i}", f"1.{i}.0")])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_T029_compute_hash_deterministic(self):
        assert self.lf.compute_hash(self.entries) == self.lf.compute_hash(self.entries)

    def test_T030_empty_lockfile_hash(self):
        assert len(self.lf.compute_hash([])) == 64

    def test_T031_single_entry_hash(self):
        assert len(self.lf.compute_hash([make_entry("only", "1.0.0")])) == 64

    def test_T032_record_updates_stored_hash(self):
        h1 = self.lf.record(self.entries)
        h2 = self.lf.record([make_entry("new", "2.0.0")])
        assert h1 != h2 and self.lf.stored_hash == h2


class TestDependencyPinner:
    def setup_method(self):
        self.pinner = DependencyPinner()

    def test_T033_parse_pinned_line(self):
        s = self.pinner.parse_line("fastapi==0.115.0")
        assert s.name == "fastapi" and s.version == "0.115.0" and s.pin_op == "=="

    def test_T034_parse_unpinned_ge(self):
        assert not self.pinner.parse_line("fastapi>=0.100.0").pinned

    def test_T035_parse_comment_returns_none(self):
        assert self.pinner.parse_line("# comment") is None

    def test_T036_parse_empty_returns_none(self):
        assert self.pinner.parse_line("") is None

    def test_T037_parse_flag_line_returns_none(self):
        assert self.pinner.parse_line("--extra-index-url https://pypi.org") is None

    def test_T038_parse_requirements_count(self):
        assert len(self.pinner.parse_requirements(SAMPLE_REQS)) == 5

    def test_T039_check_pinned_all_pinned(self):
        assert self.pinner.check_pinned(self.pinner.parse_requirements(PINNED_REQS)) == []

    def test_T040_check_pinned_detects_unpinned(self):
        assert len(self.pinner.check_pinned(self.pinner.parse_requirements(UNPINNED_REQS))) >= 2

    def test_T041_check_banned_detects_banned(self):
        banned = self.pinner.check_banned(self.pinner.parse_requirements(BANNED_REQS))
        assert any(s.name.lower() == "debug-toolbar" for s in banned)

    def test_T042_check_banned_none_present(self):
        assert self.pinner.check_banned(self.pinner.parse_requirements(PINNED_REQS)) == []

    def test_T043_enforce_clean_returns_empty(self):
        u, b = self.pinner.enforce(PINNED_REQS)
        assert u == [] and b == []

    def test_T044_enforce_detects_unpinned(self):
        u, _ = self.pinner.enforce(UNPINNED_REQS)
        assert len(u) >= 2

    def test_T045_enforce_detects_banned(self):
        _, b = self.pinner.enforce(BANNED_REQS)
        assert len(b) >= 1

    def test_T046_pin_all_forces_eq(self):
        for s in self.pinner.pin_all(self.pinner.parse_requirements(UNPINNED_REQS)):
            assert s.pin_op == "=="

    def test_T047_pin_all_no_mutate_original(self):
        specs = self.pinner.parse_requirements(UNPINNED_REQS)
        orig = [s.pin_op for s in specs]
        self.pinner.pin_all(specs)
        assert [s.pin_op for s in specs] == orig

    def test_T048_generate_requirements_output(self):
        out = self.pinner.generate_requirements(self.pinner.parse_requirements(PINNED_REQS))
        assert "fastapi==0.115.0" in out

    def test_T049_parse_extras(self):
        s = self.pinner.parse_line("uvicorn[standard]==0.30.6")
        assert "standard" in s.extras

    def test_T050_parse_tilde_eq(self):
        s = self.pinner.parse_line("requests~=2.28.0")
        assert s.pin_op == "~=" and not s.pinned

    def test_T051_parse_name_with_dash(self):
        assert self.pinner.parse_line("python-dotenv==1.0.1").name == "python-dotenv"

    def test_T052_banned_case_insensitive(self):
        specs = self.pinner.parse_requirements("DEBUG-TOOLBAR==1.0.0\n")
        assert len(self.pinner.check_banned(specs)) >= 1


class TestVulnerabilityScanner:
    def setup_method(self):
        self.scanner = VulnerabilityScanner()
        self.specs = [
            make_spec("fastapi", "0.100.0"),
            make_spec("pydantic", "1.9.0"),
            make_spec("redis", "4.0.0"),
        ]
        self.vulns = [
            make_vuln("CVE-2024-001", "fastapi", "0.100.0", VulnSeverity.CRITICAL),
            make_vuln("CVE-2024-002", "pydantic", "1.9.0", VulnSeverity.HIGH),
            make_vuln("CVE-2024-003", "redis", "3.5.0", VulnSeverity.MEDIUM),
        ]

    def test_T053_scan_finds_critical(self):
        self.scanner.load_db(self.vulns)
        assert any(v.cve_id == "CVE-2024-001" for v in self.scanner.scan(self.specs))

    def test_T054_scan_finds_high(self):
        self.scanner.load_db(self.vulns)
        assert any(v.cve_id == "CVE-2024-002" for v in self.scanner.scan(self.specs))

    def test_T055_scan_skips_non_matching_version(self):
        self.scanner.load_db(self.vulns)
        assert not any(v.cve_id == "CVE-2024-003" for v in self.scanner.scan(self.specs))

    def test_T056_scan_sorted_by_severity(self):
        self.scanner.load_db(self.vulns)
        from backend.core.supply_chain import _SEV_RANK

        found = self.scanner.scan(self.specs)
        for i in range(len(found) - 1):
            assert _SEV_RANK[found[i].severity] >= _SEV_RANK[found[i + 1].severity]

    def test_T057_has_critical_true(self):
        self.scanner.load_db(self.vulns)
        assert self.scanner.has_critical(self.specs) is True

    def test_T058_has_critical_false(self):
        self.scanner.load_db([make_vuln("X", "pydantic", "1.9.0", VulnSeverity.HIGH)])
        assert self.scanner.has_critical([make_spec("pydantic", "1.9.0")]) is False

    def test_T059_summary_keys(self):
        self.scanner.load_db(self.vulns)
        s = self.scanner.summary(self.specs)
        assert all(sev.value in s for sev in VulnSeverity)

    def test_T060_summary_critical_count(self):
        self.scanner.load_db(self.vulns)
        assert self.scanner.summary(self.specs)["critical"] >= 1

    def test_T061_empty_db_no_vulns(self):
        self.scanner.load_db([])
        assert self.scanner.scan(self.specs) == []

    def test_T062_add_vuln_incremental(self):
        self.scanner.load_db([])
        self.scanner.add_vuln(make_vuln("CVE-NEW", "fastapi", "0.100.0", VulnSeverity.CRITICAL))
        assert any(v.cve_id == "CVE-NEW" for v in self.scanner.scan(self.specs))

    def test_T063_hook_called_on_scan(self):
        results = []
        self.scanner.add_hook(lambda found: results.append(len(found)))
        self.scanner.load_db(self.vulns)
        self.scanner.scan(self.specs)
        assert len(results) == 1

    def test_T064_hook_exception_does_not_break(self):
        self.scanner.add_hook(lambda _: 1 / 0)
        self.scanner.load_db(self.vulns)
        assert isinstance(self.scanner.scan(self.specs), list)

    def test_T065_case_insensitive_package_match(self):
        self.scanner.load_db([make_vuln("CVE-CI", "FastAPI", "0.100.0", VulnSeverity.HIGH)])
        assert any(
            v.cve_id == "CVE-CI" for v in self.scanner.scan([make_spec("fastapi", "0.100.0")])
        )

    def test_T066_concurrent_scan_safe(self):
        self.scanner.load_db(self.vulns)
        errors = []

        def worker():
            try:
                self.scanner.scan(self.specs)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_T067_no_specs_returns_empty(self):
        self.scanner.load_db(self.vulns)
        assert self.scanner.scan([]) == []

    def test_T068_multiple_vulns_same_package(self):
        self.scanner.load_db(
            [
                make_vuln("CVE-A", "fastapi", "0.100.0", VulnSeverity.HIGH),
                make_vuln("CVE-B", "fastapi", "0.100.0", VulnSeverity.CRITICAL),
            ]
        )
        found = self.scanner.scan([make_spec("fastapi", "0.100.0")])
        ids = [v.cve_id for v in found]
        assert "CVE-A" in ids and "CVE-B" in ids


class TestDriftDetector:
    def setup_method(self):
        self.detector = DriftDetector()
        self.lockfile = {"fastapi": "0.115.0", "pydantic": "2.9.2", "redis": "5.1.1"}
        self.current = {"fastapi": "0.115.0", "pydantic": "2.9.2", "redis": "5.1.1"}

    def test_T069_no_drift_clean(self):
        assert self.detector.detect(self.lockfile, self.current) == []

    def test_T070_version_drift_detected(self):
        c = dict(self.current)
        c["fastapi"] = "0.200.0"
        assert any(i.kind == DriftKind.VERSION for i in self.detector.detect(self.lockfile, c))

    def test_T071_added_package_detected(self):
        c = dict(self.current)
        c["evil-pkg"] = "1.0.0"
        assert any(i.kind == DriftKind.ADDED for i in self.detector.detect(self.lockfile, c))

    def test_T072_removed_package_detected(self):
        c = dict(self.current)
        del c["redis"]
        assert any(i.kind == DriftKind.REMOVED for i in self.detector.detect(self.lockfile, c))

    def test_T073_drift_expected_value(self):
        c = dict(self.current)
        c["fastapi"] = "0.200.0"
        item = next(
            i for i in self.detector.detect(self.lockfile, c) if i.kind == DriftKind.VERSION
        )
        assert item.expected == "0.115.0" and item.actual == "0.200.0"

    def test_T074_is_clean_false_on_drift(self):
        c = dict(self.current)
        c["fastapi"] = "0.200.0"
        assert not self.detector.is_clean(self.detector.detect(self.lockfile, c))

    def test_T075_case_insensitive_match(self):
        assert self.detector.detect({"FastAPI": "0.115.0"}, {"fastapi": "0.115.0"}) == []

    def test_T076_hash_drift_detected(self):
        items = self.detector.detect_hash_drift(
            [LockfileEntry("fastapi", "0.115.0", sha256="a" * 64)], {"fastapi": "b" * 64}
        )
        assert any(i.kind == DriftKind.HASH for i in items)

    def test_T077_hash_drift_clean(self):
        h = "a" * 64
        assert (
            self.detector.detect_hash_drift(
                [LockfileEntry("fastapi", "0.115.0", sha256=h)], {"fastapi": h}
            )
            == []
        )

    def test_T078_hash_drift_missing_actual_ok(self):
        assert (
            self.detector.detect_hash_drift(
                [LockfileEntry("fastapi", "0.115.0", sha256="a" * 64)], {}
            )
            == []
        )

    def test_T079_empty_lockfile_all_added(self):
        items = self.detector.detect({}, self.current)
        assert all(i.kind == DriftKind.ADDED for i in items) and len(items) == 3

    def test_T080_empty_current_all_removed(self):
        items = self.detector.detect(self.lockfile, {})
        assert all(i.kind == DriftKind.REMOVED for i in items) and len(items) == 3

    def test_T081_multiple_drift_types(self):
        kinds = {
            i.kind
            for i in self.detector.detect(self.lockfile, {"fastapi": "0.200.0", "newpkg": "1.0.0"})
        }
        assert DriftKind.VERSION in kinds and DriftKind.ADDED in kinds

    def test_T082_drift_item_dataclass(self):
        d = DriftItem(DriftKind.ADDED, "newpkg", actual="1.0.0")
        assert d.kind == DriftKind.ADDED and d.package == "newpkg"

    def test_T083_large_env_performance(self):
        lock = {f"pkg{i}": f"1.{i}.0" for i in range(200)}
        assert self.detector.detect(lock, lock) == []

    def test_T084_supply_chain_attack_hash_mismatch(self):
        items = self.detector.detect_hash_drift(
            [LockfileEntry("requests", "2.28.0", sha256="legit" + "a" * 59)],
            {"requests": "evil" + "b" * 60},
        )
        assert any(i.kind == DriftKind.HASH for i in items)


class TestDynamicLoadScanner:
    def setup_method(self):
        self.scanner = DynamicLoadScanner()

    def test_T085_detect_exec(self):
        assert any(
            v.pattern == "exec(" for v in self.scanner.scan_source('exec("import os")', "test.py")
        )

    def test_T086_detect_eval(self):
        assert any(
            v.pattern == "eval("
            for v in self.scanner.scan_source("result = eval(user_input)", "test.py")
        )

    def test_T087_detect_pickle_loads(self):
        assert any(
            v.pattern == "pickle.loads"
            for v in self.scanner.scan_source("obj = pickle.loads(data)", "test.py")
        )

    def test_T088_detect_dynamic_import(self):
        assert any(
            "importlib" in v.pattern
            for v in self.scanner.scan_source("mod = importlib.import_module(name)", "test.py")
        )

    def test_T089_comment_ignored(self):
        assert self.scanner.scan_source('# exec("bad")', "test.py") == []

    def test_T090_clean_source_no_violations(self):
        assert (
            self.scanner.scan_source("import fastapi\nfrom pydantic import BaseModel\n", "clean.py")
            == []
        )

    def test_T091_violation_has_line_no(self):
        assert self.scanner.scan_source("x = 1\ny = eval(z)\n", "test.py")[0].line_no == 2

    def test_T092_violation_severity_critical_for_exec(self):
        viols = [
            v for v in self.scanner.scan_source("exec(code)", "test.py") if v.pattern == "exec("
        ]
        assert viols[0].severity == VulnSeverity.CRITICAL

    def test_T093_violation_severity_high_for_subprocess(self):
        viols = [
            v
            for v in self.scanner.scan_source("p = subprocess.Popen(cmd)", "test.py")
            if v.pattern == "subprocess.Popen"
        ]
        assert viols[0].severity == VulnSeverity.HIGH

    def test_T094_scan_files_multiple(self):
        assert (
            len(
                self.scanner.scan_files({"a.py": "eval(x)", "b.py": "exec(y)", "c.py": "import os"})
            )
            >= 2
        )

    def test_T095_has_critical_violation_true(self):
        assert self.scanner.has_critical_violation({"bad.py": "exec(cmd)"}) is True

    def test_T096_has_critical_violation_false(self):
        assert self.scanner.has_critical_violation({"good.py": "import os"}) is False

    def test_T097_summary_keys(self):
        assert all(
            sev.value in self.scanner.summary({"test.py": "eval(x)"}) for sev in VulnSeverity
        )

    def test_T098_custom_patterns(self):
        assert (
            len(
                DynamicLoadScanner(patterns=["DANGER"]).scan_source(
                    'x = DANGER("do it")', "test.py"
                )
            )
            >= 1
        )

    def test_T099_multiline_source(self):
        src = "\n".join(["x = 1"] * 50 + ["eval(bad)"] + ["y = 2"] * 50)
        assert self.scanner.scan_source(src, "long.py")[0].line_no == 51

    def test_T100_marshal_loads_detected(self):
        assert any(
            "marshal" in v.pattern
            for v in self.scanner.scan_source("code = marshal.loads(data)", "test.py")
        )


class TestBuildSigner:
    def setup_method(self):
        self.signer = BuildSigner(b"test-secret-phase28")
        self.record = BuildRecord(
            commit_sha="abc123",
            branch="main",
            python_ver="3.11",
            lockfile_hash="a" * 64,
            deps_count=42,
            built_by="ci",
            artifact_ids=["art-1", "art-2"],
        )

    def test_T101_sign_sets_signature(self):
        assert len(self.signer.sign(self.record).signature) == 64

    def test_T102_sign_sets_status_signed(self):
        assert self.signer.sign(self.record).status == BuildStatus.SIGNED

    def test_T103_verify_signed_true(self):
        assert self.signer.verify(self.signer.sign(self.record)) is True

    def test_T104_verify_tampered_false(self):
        r = self.signer.sign(self.record)
        r.commit_sha = "evil123"
        assert self.signer.verify(r) is False

    def test_T105_verify_unsigned_false(self):
        assert self.signer.verify(self.record) is False

    def test_T106_verify_or_raise_ok(self):
        self.signer.verify_or_raise(self.signer.sign(self.record))

    def test_T107_verify_or_raise_raises(self):
        r = self.signer.sign(self.record)
        r.branch = "evil"
        with pytest.raises(BuildSignatureError):
            self.signer.verify_or_raise(r)

    def test_T108_wrong_secret_verify_fails(self):
        assert BuildSigner(b"wrong").verify(self.signer.sign(self.record)) is False

    def test_T109_string_secret_accepted(self):
        signer = BuildSigner("string-secret")
        r = copy.copy(self.record)
        signer.sign(r)
        assert signer.verify(r) is True

    def test_T110_signature_is_64_char_hex(self):
        r = self.signer.sign(self.record)
        assert len(r.signature) == 64 and int(r.signature, 16) >= 0

    def test_T111_artifact_ids_order_independent(self):
        r1 = copy.copy(self.record)
        r1.artifact_ids = ["art-2", "art-1"]
        r2 = copy.copy(self.record)
        r2.artifact_ids = ["art-1", "art-2"]
        self.signer.sign(r1)
        self.signer.sign(r2)
        assert r1.signature == r2.signature

    def test_T112_lockfile_hash_tamper_detected(self):
        r = self.signer.sign(self.record)
        r.lockfile_hash = "b" * 64
        assert self.signer.verify(r) is False


class TestBuildReproducer:
    def setup_method(self):
        self.reproducer = BuildReproducer()
        self.entries = [make_entry("fastapi", "0.115.0"), make_entry("pydantic", "2.9.2")]

    def _build(self, **kw):
        kw.setdefault("commit_sha", "abc")
        kw.setdefault("branch", "main")
        kw.setdefault("python_ver", "3.11")
        kw.setdefault("lockfile_entries", self.entries)
        kw.setdefault("artifact_ids", [])
        kw.setdefault("built_by", "ci")
        return self.reproducer.create_build(**kw)

    def test_T113_create_build_returns_record(self):
        assert self._build().build_id

    def test_T114_create_build_status_verified(self):
        assert self._build().status == BuildStatus.VERIFIED

    def test_T115_verify_build_ok(self):
        b = self._build()
        ok, msg = self.reproducer.verify_build(b.build_id)
        assert ok and msg == "ok"

    def test_T116_verify_build_not_found(self):
        ok, msg = self.reproducer.verify_build("nonexistent")
        assert not ok and msg == "build_not_found"

    def test_T117_is_reproducible_true(self):
        b = self._build()
        assert self.reproducer.is_reproducible(b.build_id, self.entries, "abc", "3.11") is True

    def test_T118_is_reproducible_false_wrong_commit(self):
        b = self._build()
        assert self.reproducer.is_reproducible(b.build_id, self.entries, "evil", "3.11") is False

    def test_T119_is_reproducible_false_tampered_lockfile(self):
        b = self._build()
        assert (
            self.reproducer.is_reproducible(
                b.build_id, [make_entry("evil", "0.0.1")], "abc", "3.11"
            )
            is False
        )

    def test_T120_list_builds_sorted(self):
        for i in range(3):
            self._build()
        builds = self.reproducer.list_builds()
        assert len(builds) >= 3
        for i in range(len(builds) - 1):
            assert builds[i].built_at >= builds[i + 1].built_at

    def test_T121_concurrent_create_builds(self):
        errors = []

        def worker():
            try:
                self._build()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors and len(self.reproducer.list_builds()) >= 20

    def test_T122_env_vars_hash_set(self):
        assert self._build(env={"PYTHON_ENV": "prod"}).env_vars_hash != ""

    def test_T123_different_env_different_hash(self):
        b1 = self._build(env={"ENV": "prod"})
        b2 = self._build(env={"ENV": "staging"})
        assert b1.env_vars_hash != b2.env_vars_hash

    def test_T124_get_build_returns_record(self):
        b = self._build()
        assert self.reproducer.get(b.build_id).build_id == b.build_id


class TestSupplyChainAuditChain:
    def setup_method(self):
        self.chain = SupplyChainAuditChain(b"test-secret")

    def test_T125_record_returns_entry(self):
        e = self.chain.record("scan", "ci", {"deps": 10})
        assert e.seq == 1 and e.action == "scan"

    def test_T126_chain_hash_is_64_char(self):
        assert len(self.chain.record("scan", "ci").chain_hash) == 64

    def test_T127_verify_chain_empty(self):
        assert self.chain.verify_chain() is True

    def test_T128_verify_chain_after_records(self):
        for i in range(10):
            self.chain.record(f"action{i}", "ci")
        assert self.chain.verify_chain() is True

    def test_T129_detect_tampered_empty(self):
        assert self.chain.detect_tampered() == []

    def test_T130_detect_tampered_after_tamper(self):
        e = self.chain.record("scan", "ci")
        e.action = "hacked"
        assert e.seq in self.chain.detect_tampered()

    def test_T131_seq_monotone(self):
        assert [self.chain.record(f"a{i}", "ci").seq for i in range(5)] == list(range(1, 6))

    def test_T132_query_by_action(self):
        self.chain.record("scan", "ci")
        self.chain.record("build", "ci")
        self.chain.record("scan", "ci")
        assert len(self.chain.query(action="scan")) == 2

    def test_T133_query_by_actor(self):
        self.chain.record("scan", "alice")
        self.chain.record("scan", "bob")
        assert all(e.actor == "alice" for e in self.chain.query(actor="alice"))

    def test_T134_query_most_recent_first(self):
        for i in range(5):
            self.chain.record("act", "ci")
        seqs = [e.seq for e in self.chain.query(limit=5)]
        assert seqs == sorted(seqs, reverse=True)

    def test_T135_size_increments(self):
        assert self.chain.size == 0
        self.chain.record("a", "ci")
        self.chain.record("b", "ci")
        assert self.chain.size == 2

    def test_T136_genesis_is_64_char(self):
        assert len(self.chain._genesis) == 64

    def test_T137_different_secrets_different_genesis(self):
        assert SupplyChainAuditChain(b"s1")._genesis != SupplyChainAuditChain(b"s2")._genesis

    def test_T138_concurrent_records_unique_seqs(self):
        seqs = []
        lock = threading.Lock()

        def worker():
            e = self.chain.record("concurrent", "ci")
            with lock:
                seqs.append(e.seq)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seqs)) == 50

    def test_T139_verify_chain_after_concurrent(self):
        def worker():
            self.chain.record("action", "ci")

        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert self.chain.verify_chain() is True

    def test_T140_detail_stored_correctly(self):
        e = self.chain.record("scan", "ci", {"count": 42, "flag": True})
        assert e.detail["count"] == 42 and e.detail["flag"] is True

    def test_T141_prev_hash_chain(self):
        e1 = self.chain.record("a", "ci")
        e2 = self.chain.record("b", "ci")
        assert e2.prev_hash == e1.chain_hash

    def test_T142_tamper_detail_detected(self):
        e = self.chain.record("scan", "ci", {"count": 10})
        e.detail["count"] = 999
        assert e.seq in self.chain.detect_tampered()

    def test_T143_100_record_chain_valid(self):
        for i in range(100):
            self.chain.record(f"act{i}", "ci", {"i": i})
        assert self.chain.verify_chain() is True and self.chain.size == 100

    def test_T144_query_limit_respected(self):
        for i in range(20):
            self.chain.record("act", "ci")
        assert len(self.chain.query(limit=5)) == 5


class TestSupplyChainAdmin:
    def setup_method(self):
        self.sys = SupplyChainSystem()
        self.entries = [make_entry("fastapi", "0.115.0"), make_entry("pydantic", "2.9.2")]
        self.env = {"fastapi": "0.115.0", "pydantic": "2.9.2"}

    def test_T145_full_scan_clean(self):
        r = self.sys.admin.full_scan(PINNED_REQS, self.entries, self.env, {})
        assert r["unpinned_count"] == 0 and r["pass"] is True

    def test_T146_full_scan_detects_unpinned(self):
        r = self.sys.admin.full_scan(UNPINNED_REQS, self.entries, self.env, {})
        assert r["unpinned_count"] >= 2 and r["pass"] is False

    def test_T147_full_scan_detects_dynamic_load(self):
        r = self.sys.admin.full_scan(PINNED_REQS, self.entries, self.env, {"bad.py": "exec(cmd)"})
        assert r["dynamic_load_count"] >= 1 and r["pass"] is False

    def test_T148_full_scan_audited(self):
        self.sys.admin.full_scan(PINNED_REQS, self.entries, self.env, {})
        assert len(self.sys.audit.query(action="full_scan")) >= 1

    def test_T149_generate_sbom_structure(self):
        sbom = self.sys.admin.generate_sbom(
            self.sys.parse_requirements(PINNED_REQS), self.entries, "build-1"
        )
        assert "components" in sbom and sbom["sbom_version"] == "1.0"

    def test_T150_generate_sbom_sha256_present(self):
        sbom = self.sys.admin.generate_sbom(
            self.sys.parse_requirements(PINNED_REQS), self.entries, "b1"
        )
        assert all("sha256" in c for c in sbom["components"])

    def test_T151_generate_sbom_audited(self):
        self.sys.admin.generate_sbom(self.sys.parse_requirements(PINNED_REQS), self.entries, "b1")
        assert len(self.sys.audit.query(action="sbom_generated")) >= 1

    def test_T152_policy_gate_passes_clean(self):
        passed, reasons = self.sys.admin.policy_gate(PINNED_REQS, [], {})
        assert passed and reasons == []

    def test_T153_policy_gate_blocks_unpinned(self):
        passed, reasons = self.sys.admin.policy_gate(UNPINNED_REQS, [], {}, block_on_unpinned=True)
        assert not passed and any("unpinned" in r for r in reasons)

    def test_T154_policy_gate_blocks_critical_vuln(self):
        passed, reasons = self.sys.admin.policy_gate(
            "fastapi==0.100.0\n",
            [make_vuln("CVE-CRIT", "fastapi", "0.100.0", VulnSeverity.CRITICAL)],
            {},
            block_on_critical_vuln=True,
        )
        assert not passed and any("critical" in r for r in reasons)

    def test_T155_policy_gate_blocks_dynamic_load(self):
        passed, reasons = self.sys.admin.policy_gate(
            PINNED_REQS, [], {"bad.py": "eval(x)"}, block_on_dynamic_load=True
        )
        assert not passed and any("dynamic" in r for r in reasons)

    def test_T156_policy_gate_blocks_banned(self):
        passed, reasons = self.sys.admin.policy_gate(BANNED_REQS, [], {}, block_on_banned=True)
        assert not passed and any("banned" in r for r in reasons)

    def test_T157_policy_gate_audited(self):
        self.sys.admin.policy_gate(PINNED_REQS, [], {})
        assert len(self.sys.audit.query(action="policy_gate")) >= 1

    def test_T158_full_scan_detects_banned(self):
        assert (
            self.sys.admin.full_scan(BANNED_REQS, self.entries, self.env, {})["banned_count"] >= 1
        )

    def test_T159_direct_vuln_scan(self):
        self.sys.scanner.load_db([make_vuln("CVE-X", "fastapi", "0.115.0", VulnSeverity.HIGH)])
        assert len(self.sys.scanner.scan(self.sys.parse_requirements(PINNED_REQS))) >= 1

    def test_T160_sbom_build_id_present(self):
        assert (
            self.sys.admin.generate_sbom(
                self.sys.parse_requirements(PINNED_REQS), self.entries, "build-999"
            )["build_id"]
            == "build-999"
        )

    def test_T161_sbom_dev_flag(self):
        assert (
            self.sys.admin.generate_sbom(
                [DepSpec("pytest", "8.3.3", pin_op="==", is_dev=True)], [], "b"
            )["components"][0]["is_dev"]
            is True
        )

    def test_T162_policy_gate_no_block_flags(self):
        passed, _ = self.sys.admin.policy_gate(
            UNPINNED_REQS,
            [],
            {"bad.py": "eval(x)"},
            block_on_unpinned=False,
            block_on_dynamic_load=False,
            block_on_critical_vuln=False,
            block_on_banned=False,
        )
        assert passed is True

    def test_T163_full_scan_drift_count(self):
        r = self.sys.admin.full_scan(
            PINNED_REQS, self.entries, {"fastapi": "0.200.0", "pydantic": "2.9.2"}, {}
        )
        assert r["drift_count"] >= 1

    def test_T164_record_lockfile_and_verify(self):
        h = self.sys.record_lockfile(self.entries)
        assert len(h) == 64 and self.sys.lockfile.verify(self.entries) is True


class TestSupplyChainSystemIntegration:
    def setup_method(self):
        self.sys = SupplyChainSystem()
        self.entries = [
            make_entry("fastapi", "0.115.0"),
            make_entry("pydantic", "2.9.2"),
            make_entry("redis", "5.1.1"),
        ]

    def _build(self, **kw):
        kw.setdefault("commit_sha", "abc")
        kw.setdefault("branch", "main")
        kw.setdefault("python_ver", "3.11")
        kw.setdefault("lockfile_entries", self.entries)
        kw.setdefault("artifact_ids", [])
        kw.setdefault("built_by", "ci")
        return self.sys.create_build(**kw)

    def test_T165_full_e2e_clean_build(self):
        u, b = self.sys.pinner.enforce(PINNED_REQS)
        assert u == [] and b == []
        lf = self.sys.record_lockfile(self.entries)
        assert len(lf) == 64
        ok, msg = self.sys.builds.verify_build(self._build().build_id)
        assert ok and msg == "ok"

    def test_T166_e2e_attack_scenario(self):
        self.sys.record_lockfile(self.entries)
        tampered = [LockfileEntry("fastapi", "0.115.0", sha256="evil" + "a" * 60)] + self.entries[
            1:
        ]
        assert self.sys.lockfile.verify(tampered) is False
        assert any(
            i.kind == DriftKind.HASH
            for i in self.sys.drift.detect_hash_drift(self.entries, {"fastapi": "evil" + "a" * 60})
        )

    def test_T167_e2e_dynamic_load_blocked(self):
        passed, _ = self.sys.admin.policy_gate(
            PINNED_REQS,
            [],
            {"backdoor.py": 'exec(open("cmd.sh").read())'},
            block_on_dynamic_load=True,
        )
        assert passed is False

    def test_T168_e2e_sbom_and_audit_chain(self):
        sbom = self.sys.admin.generate_sbom(
            self.sys.parse_requirements(SAMPLE_REQS), self.entries, "build-2"
        )
        assert sbom["total"] == 5 and self.sys.audit.verify_chain() is True

    def test_T169_e2e_reproducible_build(self):
        b = self._build()
        assert self.sys.builds.is_reproducible(b.build_id, self.entries, "abc", "3.11") is True

    def test_T170_audit_chain_100_ops(self):
        for i in range(100):
            self.sys.audit.record(f"op{i}", "ci", {"i": i})
        assert self.sys.audit.verify_chain() is True

    def test_T171_concurrent_full_scans(self):
        errors = []

        def worker():
            try:
                self.sys.admin.full_scan(
                    PINNED_REQS, self.entries, {"fastapi": "0.115.0", "pydantic": "2.9.2"}, {}
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_T172_lockfile_tamper_after_record(self):
        self.sys.record_lockfile(self.entries)
        assert self.sys.lockfile.verify(self.entries + [make_entry("extra", "9.9.9")]) is False

    def test_T173_build_signature_tamper_detected(self):
        b = self._build()
        b.branch = "evil-branch"
        assert not self.sys.signer.verify(b)

    def test_T174_full_scan_returns_total_deps(self):
        assert (
            self.sys.admin.full_scan(
                SAMPLE_REQS, self.entries, {"fastapi": "0.115.0", "pydantic": "2.9.2"}, {}
            )["total_deps"]
            == 5
        )

    def test_T175_policy_gate_all_reasons_listed(self):
        passed, reasons = self.sys.admin.policy_gate(
            UNPINNED_REQS,
            [make_vuln("CVE-X", "fastapi", "0.100.0", VulnSeverity.CRITICAL)],
            {"bad.py": "eval(x)"},
            block_on_unpinned=True,
            block_on_dynamic_load=True,
            block_on_critical_vuln=True,
        )
        assert not passed and len(reasons) >= 2

    def test_T176_system_audit_chain_isolated(self):
        s1 = SupplyChainSystem(b"secret1")
        s2 = SupplyChainSystem(b"secret2")
        assert s1.audit._genesis != s2.audit._genesis


SQL_PATH = os.path.join(os.path.dirname(__file__), "../../supabase/migration_037.sql")


@pytest.fixture(scope="module")
def sql_content():
    if not os.path.exists(SQL_PATH):
        pytest.skip("migration_037.sql not found")
    with open(SQL_PATH) as f:
        return f.read()


class TestSQLMigration:
    def test_T177_sql_file_exists(self, sql_content):
        assert len(sql_content) > 100

    def test_T178_begins_with_begin(self, sql_content):
        assert "BEGIN" in sql_content.upper()

    def test_T179_supply_chain_runs_table(self, sql_content):
        assert "supply_chain_runs" in sql_content

    def test_T180_lockfile_records_table(self, sql_content):
        assert "lockfile_records" in sql_content

    def test_T181_build_records_table(self, sql_content):
        assert "build_records" in sql_content

    def test_T182_vuln_scan_results_table(self, sql_content):
        assert "vuln_scan_results" in sql_content

    def test_T183_dynamic_load_violations_table(self, sql_content):
        assert "dynamic_load_violations" in sql_content

    def test_T184_rls_enabled(self, sql_content):
        assert "ROW LEVEL SECURITY" in sql_content.upper() or "ENABLE ROW" in sql_content.upper()

    def test_T185_tenant_id_column(self, sql_content):
        assert "tenant_id" in sql_content

    def test_T186_chain_hash_column(self, sql_content):
        assert "chain_hash" in sql_content

    def test_T187_indexes_present(self, sql_content):
        assert "CREATE INDEX" in sql_content.upper()

    def test_T188_immutable_trigger(self, sql_content):
        assert "TRIGGER" in sql_content.upper()

    def test_T189_cleanup_function(self, sql_content):
        assert "cleanup" in sql_content.lower() or "FUNCTION" in sql_content.upper()

    def test_T190_commit_present(self, sql_content):
        assert "COMMIT" in sql_content.upper()

    def test_T191_if_not_exists(self, sql_content):
        assert "IF NOT EXISTS" in sql_content.upper()

    def test_T192_supply_chain_audit_log_table(self, sql_content):
        assert "supply_chain_audit" in sql_content


class TestEdgeCasesAndCoverage:
    def test_T193_dep_spec_no_version(self):
        assert DepSpec(name="pkg", version="", pin_op="").req_string == "pkg"

    def test_T194_build_record_default_status(self):
        assert BuildRecord().status == BuildStatus.UNSIGNED

    def test_T195_vuln_record_affects_false(self):
        assert make_vuln("CVE-X", "pkg", "1.0.0").affects("2.0.0") is False

    def test_T196_drift_item_defaults(self):
        d = DriftItem(DriftKind.ADDED, "pkg")
        assert d.expected == "" and d.actual == ""

    def test_T197_dynamic_load_violation_defaults(self):
        assert DynamicLoadViolation("f.py", 1, "eval(", "eval(x)").severity == VulnSeverity.HIGH

    def test_T198_scanner_empty_patterns(self):
        assert DynamicLoadScanner(patterns=[]).scan_source("safe_function(x)", "test.py") == []

    def test_T199_pinner_no_version_spec(self):
        assert DepSpec(name="requests", version="2.28.0", pin_op="==").pinned is True

    def test_T200_build_signer_empty_artifact_ids(self):
        signer = BuildSigner(b"secret")
        b = BuildRecord(artifact_ids=[])
        signer.sign(b)
        assert signer.verify(b) is True

    def test_T201_audit_chain_query_limit_zero(self):
        chain = SupplyChainAuditChain(b"secret")
        for i in range(10):
            chain.record("act", "ci")
        assert chain.query(limit=0) == []

    def test_T202_lockfile_entry_source_url(self):
        e = LockfileEntry("pkg", "1.0", "a" * 64, source_url="https://pypi.org/simple/pkg/")
        assert e.source_url.startswith("https://")

    def test_T203_system_components_not_none(self):
        s = SupplyChainSystem()
        assert all(
            getattr(s, attr) is not None
            for attr in [
                "pinner",
                "scanner",
                "drift",
                "dyn",
                "lockfile",
                "signer",
                "builds",
                "audit",
                "admin",
            ]
        )

    def test_T204_banned_packages_all_lowercase_or_hyphen(self):
        for b in BANNED_PACKAGES:
            assert b == b.lower() or "-" in b
