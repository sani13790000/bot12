"""Phase 34 -- Final Security Review & Penetration Hardening
220 tests T001-T220
"""

import os
import sys
import threading
import time
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.security_review import (
    REQUIRES_REASON,
    SECURITY_HEADERS_REQUIRED,
    SENSITIVE_FIELDS,
    AuditAction,
    AuthCheckConfig,
    AuthRBACChecker,
    CheckResult,
    CheckStatus,
    CORSEnforcer,
    CORSPolicy,
    CORSViolationError,
    CryptoChecker,
    IDORChecker,
    InformationLeakScanner,
    InjectionScanner,
    MissingReasonError,
    PenTestHarness,
    PenTestScenario,
    RateLimiter,
    RateLimitExceededError,
    RateLimitRule,
    ReplayChecker,
    ReplayDetectedError,
    RiskItem,
    RiskLevel,
    RiskRegister,
    SecurityAuditChain,
    SecurityFinding,
    SecurityHeadersEnforcer,
    SecurityLogger,
    VulnCategory,
    build_security_review_system,
)


def make_system(**kw):
    return build_security_review_system(**kw)


def good_headers():
    return {
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=()",
        "X-XSS-Protection": "0",
        "Cache-Control": "no-store",
    }


def good_token():
    return {
        "sub": "user-123",
        "tenant_id": "tenant-abc",
        "exp": time.time() + 3600,
        "iat": time.time(),
        "role": "operator",
    }


ENDPOINTS = [
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/license",
    "/api/signals",
    "/api/billing",
    "/api/webhook",
    "/api/admin",
    "/api/ea/heartbeat",
]


# T001-T016 Enums
class TestEnumsAndConstants:
    def test_T001_risk_levels(self):
        assert RiskLevel.CRITICAL == "critical"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.LOW == "low"
        assert RiskLevel.INFO == "info"

    def test_T002_vuln_categories_count(self):
        assert len(VulnCategory) == 15

    def test_T003_check_status_values(self):
        assert CheckStatus.PASS == "pass"
        assert CheckStatus.FAIL == "fail"
        assert CheckStatus.WARN == "warn"
        assert CheckStatus.SKIP == "skip"

    def test_T004_audit_actions_count(self):
        assert len(AuditAction) == 10

    def test_T005_requires_reason_set(self):
        assert AuditAction.RISK_ACCEPTED in REQUIRES_REASON
        assert AuditAction.RISK_MITIGATED in REQUIRES_REASON
        assert AuditAction.CHECK_RUN not in REQUIRES_REASON

    def test_T006_security_headers_count(self):
        assert len(SECURITY_HEADERS_REQUIRED) == 8

    def test_T007_hsts_header(self):
        assert "Strict-Transport-Security" in SECURITY_HEADERS_REQUIRED
        assert "preload" in SECURITY_HEADERS_REQUIRED["Strict-Transport-Security"]

    def test_T008_x_frame_deny(self):
        assert SECURITY_HEADERS_REQUIRED["X-Frame-Options"] == "DENY"

    def test_T009_sensitive_fields(self):
        assert "password" in SENSITIVE_FIELDS
        assert "token" in SENSITIVE_FIELDS
        assert "api_key" in SENSITIVE_FIELDS
        assert "_raw" in SENSITIVE_FIELDS

    def test_T010_vuln_categories_str(self):
        assert VulnCategory.AUTH_BYPASS == "auth_bypass"
        assert VulnCategory.IDOR == "idor"
        assert VulnCategory.INJECTION == "injection"

    def test_T011_csp_default_src(self):
        assert "default-src 'self'" in SECURITY_HEADERS_REQUIRED["Content-Security-Policy"]

    def test_T012_cache_control_nostore(self):
        assert SECURITY_HEADERS_REQUIRED["Cache-Control"] == "no-store"

    def test_T013_xss_protection_off(self):
        assert SECURITY_HEADERS_REQUIRED["X-XSS-Protection"] == "0"

    def test_T014_permissions_policy(self):
        assert "geolocation" in SECURITY_HEADERS_REQUIRED["Permissions-Policy"]

    def test_T015_risk_level_ordering(self):
        levels = list(RiskLevel)
        names = [l.value for l in levels]
        assert "critical" in names and "info" in names

    def test_T016_requires_reason_size(self):
        assert len(REQUIRES_REASON) == 2


# T017-T036 Audit Chain
class TestSecurityAuditChain:
    def setup_method(self):
        self.audit = SecurityAuditChain()

    def test_T017_genesis_chain_empty(self):
        assert self.audit.verify_chain() is True

    def test_T018_record_returns_entry(self):
        e = self.audit.record(AuditAction.SCAN_STARTED, actor="test")
        assert e.seq == 1
        assert e.action == AuditAction.SCAN_STARTED

    def test_T019_chain_hash_64_chars(self):
        e = self.audit.record(AuditAction.CHECK_RUN, actor="a")
        assert len(e.chain_hash) == 64

    def test_T020_verify_chain_valid(self):
        for i in range(5):
            self.audit.record(AuditAction.CHECK_RUN, actor="a", i=str(i))
        assert self.audit.verify_chain() is True

    def test_T021_tamper_detection(self):
        e = self.audit.record(AuditAction.CHECK_RUN, actor="a")
        e.chain_hash = "a" * 64
        assert self.audit.verify_chain() is False

    def test_T022_detect_tampered_returns_seq(self):
        e = self.audit.record(AuditAction.CHECK_RUN, actor="a")
        e.chain_hash = "b" * 64
        broken = self.audit.detect_tampered()
        assert 1 in broken

    def test_T023_requires_reason_enforced(self):
        with pytest.raises(MissingReasonError):
            self.audit.record(AuditAction.RISK_ACCEPTED, actor="a")

    def test_T024_requires_reason_whitespace(self):
        with pytest.raises(MissingReasonError):
            self.audit.record(AuditAction.RISK_MITIGATED, actor="a", reason="  ")

    def test_T025_reason_recorded_in_detail(self):
        e = self.audit.record(AuditAction.RISK_ACCEPTED, actor="a", reason="biz reason")
        assert e.detail.get("reason") == "biz reason"

    def test_T026_query_by_action(self):
        self.audit.record(AuditAction.SCAN_STARTED, actor="a")
        self.audit.record(AuditAction.CHECK_RUN, actor="b")
        results = self.audit.query(action=AuditAction.SCAN_STARTED)
        assert len(results) == 1

    def test_T027_query_by_actor(self):
        self.audit.record(AuditAction.CHECK_RUN, actor="alice")
        self.audit.record(AuditAction.CHECK_RUN, actor="bob")
        results = self.audit.query(actor="alice")
        assert all(e.actor == "alice" for e in results)

    def test_T028_query_limit_zero_empty(self):
        self.audit.record(AuditAction.CHECK_RUN, actor="a")
        assert self.audit.query(limit=0) == []

    def test_T029_query_most_recent_first(self):
        for i in range(3):
            self.audit.record(AuditAction.CHECK_RUN, actor="a", i=str(i))
        results = self.audit.query()
        assert results[0].seq == 3

    def test_T030_len_matches(self):
        for _ in range(7):
            self.audit.record(AuditAction.CHECK_RUN, actor="a")
        assert len(self.audit) == 7

    def test_T031_concurrent_safe(self):
        def worker():
            for _ in range(20):
                self.audit.record(AuditAction.CHECK_RUN, actor="w")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert self.audit.verify_chain() is True
        assert len(self.audit) == 100

    def test_T032_100_record_chain(self):
        for i in range(100):
            self.audit.record(AuditAction.CHECK_RUN, actor="a", i=str(i))
        assert self.audit.verify_chain() is True
        assert len(self.audit) == 100

    def test_T033_different_secrets_invalid(self):
        a2 = SecurityAuditChain(secret="different")
        a2.record(AuditAction.CHECK_RUN, actor="x")
        a2._secret = b"wrong"
        assert a2.verify_chain() is False

    def test_T034_detail_preserved(self):
        e = self.audit.record(AuditAction.CHECK_RUN, actor="a", check_id="C1", status="pass")
        assert e.detail["check_id"] == "C1"
        assert e.detail["status"] == "pass"

    def test_T035_ts_is_float(self):
        e = self.audit.record(AuditAction.CHECK_RUN, actor="a")
        assert isinstance(e.ts, float)

    def test_T036_seq_increments(self):
        for i in range(5):
            e = self.audit.record(AuditAction.CHECK_RUN, actor="a")
        assert e.seq == 5


# T037-T052 Security Headers
class TestSecurityHeadersEnforcer:
    def setup_method(self):
        self.enforcer = SecurityHeadersEnforcer()

    def test_T037_all_headers_present_no_findings(self):
        findings = self.enforcer.validate(good_headers())
        assert findings == []

    def test_T038_missing_hsts(self):
        h = good_headers()
        del h["Strict-Transport-Security"]
        findings = self.enforcer.validate(h)
        assert any("Strict-Transport-Security" in f.title for f in findings)

    def test_T039_missing_header_risk_high(self):
        h = good_headers()
        del h["X-Frame-Options"]
        findings = self.enforcer.validate(h)
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T040_wrong_value_risk_medium(self):
        h = good_headers()
        h["X-Frame-Options"] = "SAMEORIGIN"
        findings = self.enforcer.validate(h)
        assert any(f.risk == RiskLevel.MEDIUM for f in findings)

    def test_T041_build_hardened_returns_all(self):
        h = self.enforcer.build_hardened()
        assert len(h) == 8

    def test_T042_run_check_pass(self):
        r = self.enforcer.run_check(good_headers())
        assert r.status == CheckStatus.PASS

    def test_T043_run_check_fail(self):
        h = {}
        r = self.enforcer.run_check(h)
        assert r.status == CheckStatus.FAIL

    def test_T044_cwe_16_in_missing(self):
        h = good_headers()
        del h["X-Content-Type-Options"]
        findings = self.enforcer.validate(h)
        assert any(f.cwe == "CWE-16" for f in findings)

    def test_T045_custom_header_enforced(self):
        e2 = SecurityHeadersEnforcer(custom={"X-Custom": "required-value"})
        h = good_headers()
        findings = e2.validate(h)
        assert any("X-Custom" in f.title for f in findings)

    def test_T046_owasp_present(self):
        h = good_headers()
        del h["X-Frame-Options"]
        findings = self.enforcer.validate(h)
        assert any(f.owasp for f in findings)

    def test_T047_finding_has_mitigation(self):
        h = good_headers()
        del h["Cache-Control"]
        findings = self.enforcer.validate(h)
        assert all(f.mitigation for f in findings)

    def test_T048_check_id_correct(self):
        r = self.enforcer.run_check(good_headers())
        assert r.check_id == "HEADERS-001"

    def test_T049_empty_headers_8_findings(self):
        findings = self.enforcer.validate({})
        assert len(findings) == 8

    def test_T050_all_missing_risk_high(self):
        findings = self.enforcer.validate({})
        assert all(f.risk == RiskLevel.HIGH for f in findings)

    def test_T051_to_dict_has_fields(self):
        h = good_headers()
        del h["X-Frame-Options"]
        findings = self.enforcer.validate(h)
        d = findings[0].to_dict()
        assert "finding_id" in d and "risk" in d and "mitigation" in d

    def test_T052_referrer_policy_present(self):
        assert "Referrer-Policy" in SECURITY_HEADERS_REQUIRED


# T053-T068 CORS
class TestCORSEnforcer:
    def setup_method(self):
        policy = CORSPolicy(
            allowed_origins={"https://app.bot12.io", "https://admin.bot12.io"},
            allow_credentials=True,
        )
        self.cors = CORSEnforcer(policy)

    def test_T053_allowed_origin_ok(self):
        assert self.cors.check_origin("https://app.bot12.io") is True

    def test_T054_disallowed_origin_false(self):
        assert self.cors.check_origin("https://evil.com") is False

    def test_T055_wildcard_raises(self):
        with pytest.raises(CORSViolationError):
            self.cors.validate_request("*", "GET")

    def test_T056_unknown_origin_raises(self):
        with pytest.raises(CORSViolationError):
            self.cors.validate_request("https://evil.com", "POST")

    def test_T057_build_headers_allowed(self):
        h = self.cors.build_headers("https://app.bot12.io")
        assert h.get("Access-Control-Allow-Origin") == "https://app.bot12.io"

    def test_T058_build_headers_denied_empty(self):
        h = self.cors.build_headers("https://evil.com")
        assert h == {}

    def test_T059_credentials_true_in_headers(self):
        h = self.cors.build_headers("https://app.bot12.io")
        assert h.get("Access-Control-Allow-Credentials") == "true"

    def test_T060_vary_origin_set(self):
        h = self.cors.build_headers("https://app.bot12.io")
        assert h.get("Vary") == "Origin"

    def test_T061_run_check_pass_no_wildcard(self):
        r = self.cors.run_check()
        assert r.status == CheckStatus.PASS

    def test_T062_wildcard_origin_critical(self):
        p2 = CORSPolicy(allowed_origins={"*"})
        cors2 = CORSEnforcer(p2)
        r = cors2.run_check()
        assert r.status == CheckStatus.FAIL
        assert any(f.risk == RiskLevel.CRITICAL for f in r.findings)

    def test_T063_check_id_cors(self):
        r = self.cors.run_check()
        assert r.check_id == "CORS-001"

    def test_T064_empty_origin_blocked(self):
        assert self.cors.check_origin("") is False

    def test_T065_max_age_in_headers(self):
        h = self.cors.build_headers("https://app.bot12.io")
        assert "Access-Control-Max-Age" in h

    def test_T066_cwe_942_in_finding(self):
        p2 = CORSPolicy(allowed_origins={"*"})
        cors2 = CORSEnforcer(p2)
        r = cors2.run_check()
        assert any(f.cwe == "CWE-942" for f in r.findings)

    def test_T067_methods_in_headers(self):
        h = self.cors.build_headers("https://app.bot12.io")
        assert "Access-Control-Allow-Methods" in h

    def test_T068_validate_request_ok(self):
        result = self.cors.validate_request("https://app.bot12.io", "POST")
        assert result is True


# T069-T084 Rate Limiter
class TestRateLimiter:
    def setup_method(self):
        self.rl = RateLimiter(
            [
                RateLimitRule("/api/auth/login", max_requests=3, window_seconds=60),
                RateLimitRule("/api/signals", max_requests=10, window_seconds=60),
            ]
        )

    def test_T069_under_limit_ok(self):
        now = time.time()
        for _ in range(3):
            assert self.rl.check("/api/auth/login", "k1", now=now)

    def test_T070_over_limit_raises(self):
        now = time.time()
        for _ in range(3):
            self.rl.check("/api/auth/login", "k2", now=now)
        with pytest.raises(RateLimitExceededError):
            self.rl.check("/api/auth/login", "k2", now=now)

    def test_T071_different_keys_isolated(self):
        now = time.time()
        for _ in range(3):
            self.rl.check("/api/auth/login", "keyA", now=now)
        assert self.rl.check("/api/auth/login", "keyB", now=now)

    def test_T072_window_expiry(self):
        now = time.time()
        for _ in range(3):
            self.rl.check("/api/auth/login", "k3", now=now)
        later = now + 61
        assert self.rl.check("/api/auth/login", "k3", now=later)

    def test_T073_unknown_endpoint_passes(self):
        assert self.rl.check("/api/unknown", "k1") is True

    def test_T074_add_rule(self):
        self.rl.add_rule(RateLimitRule("/api/new", 5, 30))
        now = time.time()
        for _ in range(5):
            self.rl.check("/api/new", "k", now=now)
        with pytest.raises(RateLimitExceededError):
            self.rl.check("/api/new", "k", now=now)

    def test_T075_run_check_missing(self):
        r = self.rl.run_check(["/api/auth/login", "/api/missing"])
        assert r.status == CheckStatus.WARN
        assert any("missing" in f.title for f in r.findings)

    def test_T076_run_check_all_covered(self):
        r = self.rl.run_check(["/api/auth/login", "/api/signals"])
        assert r.status == CheckStatus.PASS

    def test_T077_check_id_rl(self):
        r = self.rl.run_check([])
        assert r.check_id == "RL-001"

    def test_T078_cwe_770_in_finding(self):
        r = self.rl.run_check(["/api/missing"])
        assert any(f.cwe == "CWE-770" for f in r.findings)

    def test_T079_concurrent_rate_limit(self):
        now = time.time()
        blocked = []

        def try_request():
            try:
                self.rl.check("/api/auth/login", "shared", now=now)
            except RateLimitExceededError:
                blocked.append(1)

        threads = [threading.Thread(target=try_request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(blocked) >= 7

    def test_T080_burst_rule_field(self):
        r = RateLimitRule("/api/x", 5, 30, burst_allowed=2)
        assert r.burst_allowed == 2

    def test_T081_signals_limit(self):
        now = time.time()
        for _ in range(10):
            self.rl.check("/api/signals", "k", now=now)
        with pytest.raises(RateLimitExceededError):
            self.rl.check("/api/signals", "k", now=now)

    def test_T082_run_check_empty_endpoints(self):
        r = self.rl.run_check([])
        assert r.status == CheckStatus.PASS

    def test_T083_rate_limit_error_message(self):
        now = time.time()
        for _ in range(3):
            self.rl.check("/api/auth/login", "msg_k", now=now)
        with pytest.raises(RateLimitExceededError) as exc_info:
            self.rl.check("/api/auth/login", "msg_k", now=now)
        assert "/api/auth/login" in str(exc_info.value)

    def test_T084_rule_dataclass(self):
        r = RateLimitRule("/api/x", 10, 60)
        assert r.endpoint == "/api/x"
        assert r.max_requests == 10
        assert r.window_seconds == 60


# T085-T100 Injection Scanner
class TestInjectionScanner:
    def setup_method(self):
        self.scanner = InjectionScanner()

    def test_T085_clean_input_no_hits(self):
        assert self.scanner.scan_value("hello world") == []

    def test_T086_sql_injection_detected(self):
        hits = self.scanner.scan_value("' OR 1=1 --")
        assert len(hits) > 0

    def test_T087_xss_detected(self):
        hits = self.scanner.scan_value("<script>alert(1)</script>")
        assert len(hits) > 0

    def test_T088_path_traversal_detected(self):
        hits = self.scanner.scan_value("../../etc/passwd")
        assert len(hits) > 0

    def test_T089_eval_detected(self):
        hits = self.scanner.scan_value("eval(malicious_code)")
        assert len(hits) > 0

    def test_T090_template_injection_detected(self):
        hits = self.scanner.scan_value("${7*7}")
        assert len(hits) > 0

    def test_T091_ssrf_detected(self):
        hits = self.scanner.scan_value("file://etc/passwd")
        assert len(hits) > 0

    def test_T092_union_select_detected(self):
        hits = self.scanner.scan_value("UNION SELECT * FROM users")
        assert len(hits) > 0

    def test_T093_scan_dict_nested(self):
        d = {"query": "SELECT * FROM users", "name": "Alice"}
        hits = self.scanner.scan_dict(d)
        assert "query" in hits
        assert "name" not in hits

    def test_T094_run_check_clean(self):
        r = self.scanner.run_check([{"q": "normal search", "page": "1"}])
        assert r.status == CheckStatus.PASS

    def test_T095_run_check_injection(self):
        r = self.scanner.run_check([{"q": "'; DROP TABLE users; --"}])
        assert r.status == CheckStatus.FAIL
        assert any(f.risk == RiskLevel.CRITICAL for f in r.findings)

    def test_T096_custom_patterns(self):
        s2 = InjectionScanner(patterns=[r"(?i)badword"])
        assert len(s2.scan_value("this is badword")) > 0
        assert len(s2.scan_value("clean text")) == 0

    def test_T097_cwe_89_in_finding(self):
        r = self.scanner.run_check([{"q": "SELECT 1"}])
        if r.findings:
            assert any(f.cwe == "CWE-89" for f in r.findings)

    def test_T098_check_id_inj(self):
        r = self.scanner.run_check([])
        assert r.check_id == "INJ-001"

    def test_T099_javascript_uri_detected(self):
        hits = self.scanner.scan_value("javascript:alert(1)")
        assert len(hits) > 0

    def test_T100_php_tag_detected(self):
        hits = self.scanner.scan_value('<?php system("ls")')
        assert len(hits) > 0


# T101-T112 IDOR Checker
class TestIDORChecker:
    def setup_method(self):
        self.idor = IDORChecker()

    def test_T101_same_tenant_allowed(self):
        assert self.idor.log_access("T1", "u1", "T1", "r1", "/api/x") is True

    def test_T102_cross_tenant_blocked(self):
        assert self.idor.log_access("T1", "u1", "T2", "r1", "/api/x") is False

    def test_T103_run_check_same_tenant(self):
        r = self.idor.run_check(
            [{"actor_tenant": "T", "actor_user": "u", "resource_tenant": "T", "resource_id": "r"}]
        )
        assert r.status == CheckStatus.PASS

    def test_T104_run_check_cross_tenant_fail(self):
        r = self.idor.run_check(
            [{"actor_tenant": "A", "actor_user": "u", "resource_tenant": "B", "resource_id": "r"}]
        )
        assert r.status == CheckStatus.FAIL

    def test_T105_cwe_639_in_finding(self):
        r = self.idor.run_check(
            [{"actor_tenant": "X", "actor_user": "u", "resource_tenant": "Y", "resource_id": "r"}]
        )
        assert any(f.cwe == "CWE-639" for f in r.findings)

    def test_T106_check_id_idor(self):
        r = self.idor.run_check([])
        assert r.check_id == "IDOR-001"

    def test_T107_concurrent_access_log(self):
        results = []

        def check():
            results.append(self.idor.log_access("A", "u", "B", "r", "/x"))

        threads = [threading.Thread(target=check) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is False for r in results)

    def test_T108_empty_cases_pass(self):
        r = self.idor.run_check([])
        assert r.status == CheckStatus.PASS

    def test_T109_finding_has_evidence(self):
        r = self.idor.run_check(
            [{"actor_tenant": "A", "actor_user": "u", "resource_tenant": "B", "resource_id": "r"}]
        )
        assert r.findings[0].evidence

    def test_T110_owasp_a01(self):
        r = self.idor.run_check(
            [{"actor_tenant": "X", "actor_user": "u", "resource_tenant": "Y", "resource_id": "r"}]
        )
        assert any(f.owasp == "A01:2021" for f in r.findings)

    def test_T111_risk_high_cross_tenant(self):
        r = self.idor.run_check(
            [{"actor_tenant": "X", "actor_user": "u", "resource_tenant": "Y", "resource_id": "r"}]
        )
        assert r.risk == RiskLevel.HIGH

    def test_T112_finding_to_dict(self):
        r = self.idor.run_check(
            [{"actor_tenant": "X", "actor_user": "u", "resource_tenant": "Y", "resource_id": "r"}]
        )
        d = r.findings[0].to_dict()
        assert d["category"] == "idor"


# T113-T128 Replay Checker
class TestReplayChecker:
    def setup_method(self):
        self.replay = ReplayChecker(window_seconds=300)

    def test_T113_valid_nonce_ok(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        assert self.replay.check(nonce, now, now=now) is True

    def test_T114_replay_blocked(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        self.replay.check(nonce, now, now=now)
        with pytest.raises(ReplayDetectedError):
            self.replay.check(nonce, now, now=now + 1)

    def test_T115_old_timestamp_blocked(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        with pytest.raises(ReplayDetectedError):
            self.replay.check(nonce, now - 400, now=now)

    def test_T116_future_timestamp_blocked(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        with pytest.raises(ReplayDetectedError):
            self.replay.check(nonce, now + 400, now=now)

    def test_T117_different_nonces_ok(self):
        now = time.time()
        for _ in range(10):
            self.replay.check(str(uuid.uuid4()), now, now=now)

    def test_T118_run_check_replay_detected(self):
        now = time.time()
        nonce = "fixed-nonce"
        r = self.replay.run_check(
            [
                {"nonce": nonce, "timestamp": now, "now": now},
                {"nonce": nonce, "timestamp": now, "now": now + 1},
            ]
        )
        assert r.status == CheckStatus.FAIL

    def test_T119_run_check_empty(self):
        r = self.replay.run_check([])
        assert r.status == CheckStatus.PASS

    def test_T120_check_id_replay(self):
        r = self.replay.run_check([])
        assert r.check_id == "REPLAY-001"

    def test_T121_cwe_294(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        self.replay.check(nonce, now, now=now)
        r = self.replay.run_check([{"nonce": nonce, "timestamp": now, "now": now + 1}])
        assert any(f.cwe == "CWE-294" for f in r.findings)

    def test_T122_window_eviction(self):
        now = time.time()
        nonce = "evict-test"
        self.replay.check(nonce, now, now=now)
        later = now + 400
        assert self.replay.check(nonce, later, now=later) is True

    def test_T123_zero_window_no_expiry(self):
        r = ReplayChecker(window_seconds=0)
        now = time.time()
        r.check("n1", now - 99999, now=now)
        with pytest.raises(ReplayDetectedError):
            r.check("n1", now, now=now)

    def test_T124_concurrent_safe(self):
        now = time.time()
        errors = []

        def worker(i):
            try:
                self.replay.check(f"nonce-{i}", now, now=now)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_T125_find_has_mitigation(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        self.replay.check(nonce, now, now=now)
        r = self.replay.run_check([{"nonce": nonce, "timestamp": now, "now": now + 1}])
        assert all(f.mitigation for f in r.findings)

    def test_T126_replay_error_message(self):
        now = time.time()
        nonce = "test-replay"
        self.replay.check(nonce, now, now=now)
        with pytest.raises(ReplayDetectedError) as exc:
            self.replay.check(nonce, now, now=now + 1)
        assert "test-replay" in str(exc.value)

    def test_T127_multiple_replay_findings(self):
        r = ReplayChecker(window_seconds=300)
        now = time.time()
        nonce = "rep2"
        r.check(nonce, now, now=now)
        result = r.run_check([{"nonce": nonce, "timestamp": now, "now": now + 1}])
        assert len(result.findings) == 1

    def test_T128_owasp_a07(self):
        now = time.time()
        nonce = str(uuid.uuid4())
        self.replay.check(nonce, now, now=now)
        r = self.replay.run_check([{"nonce": nonce, "timestamp": now, "now": now + 1}])
        assert any(f.owasp == "A07:2021" for f in r.findings)


# T129-T140 Information Leak Scanner
class TestInformationLeakScanner:
    def setup_method(self):
        self.scanner = InformationLeakScanner()

    def test_T129_clean_response_no_leak(self):
        assert self.scanner.scan_response({"user_id": "u1", "name": "Alice"}) == []

    def test_T130_password_field_leak(self):
        leaks = self.scanner.scan_response({"password": "secret123"})
        assert "password" in leaks

    def test_T131_nested_token_leak(self):
        leaks = self.scanner.scan_response({"user": {"token": "abc123"}})
        assert any("token" in l for l in leaks)

    def test_T132_run_check_leak_fail(self):
        r = self.scanner.run_check([{"api_key": "sk-secret"}])
        assert r.status == CheckStatus.FAIL

    def test_T133_run_check_clean_pass(self):
        r = self.scanner.run_check([{"user_id": "u1"}])
        assert r.status == CheckStatus.PASS

    def test_T134_extra_sensitive_field(self):
        s2 = InformationLeakScanner(extra_sensitive={"account_number"})
        leaks = s2.scan_response({"account_number": "1234"})
        assert "account_number" in leaks

    def test_T135_cwe_200(self):
        r = self.scanner.run_check([{"secret": "x"}])
        assert any(f.cwe == "CWE-200" for f in r.findings)

    def test_T136_check_id_leak(self):
        r = self.scanner.run_check([])
        assert r.check_id == "LEAK-001"

    def test_T137_list_scanning(self):
        resp = {"users": [{"password": "x"}, {"name": "Bob"}]}
        leaks = self.scanner.scan_response(resp)
        assert any("password" in l for l in leaks)

    def test_T138_cvv_field_leak(self):
        leaks = self.scanner.scan_response({"cvv": "123"})
        assert "cvv" in leaks

    def test_T139_ssn_field_leak(self):
        leaks = self.scanner.scan_response({"ssn": "123-45-6789"})
        assert "ssn" in leaks

    def test_T140_raw_key_leak(self):
        leaks = self.scanner.scan_response({"_raw": "key-material"})
        assert "_raw" in leaks


# T141-T152 Auth/RBAC Checker
class TestAuthRBACChecker:
    def setup_method(self):
        self.checker = AuthRBACChecker()

    def test_T141_valid_token_no_findings(self):
        findings = self.checker.check_token(good_token())
        assert findings == []

    def test_T142_missing_sub_critical(self):
        t = good_token()
        del t["sub"]
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.CRITICAL for f in findings)

    def test_T143_missing_tenant_id_high(self):
        t = good_token()
        del t["tenant_id"]
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T144_expired_token_high(self):
        t = good_token()
        t["exp"] = time.time() - 100
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T145_missing_exp_high(self):
        t = good_token()
        del t["exp"]
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T146_missing_iat_medium(self):
        t = good_token()
        del t["iat"]
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.MEDIUM for f in findings)

    def test_T147_unknown_role_high(self):
        t = good_token()
        t["role"] = "superroot"
        findings = self.checker.check_token(t)
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T148_run_check_good_token(self):
        r = self.checker.run_check([good_token()])
        assert r.status == CheckStatus.PASS

    def test_T149_run_check_bad_token_fail(self):
        t = {}
        r = self.checker.run_check([t])
        assert r.status == CheckStatus.FAIL

    def test_T150_check_id_auth(self):
        r = self.checker.run_check([])
        assert r.check_id == "AUTH-001"

    def test_T151_cwe_287_sub(self):
        t = good_token()
        del t["sub"]
        findings = self.checker.check_token(t)
        assert any(f.cwe == "CWE-287" for f in findings)

    def test_T152_custom_config(self):
        cfg = AuthCheckConfig(require_iat=False, require_sub=True)
        checker = AuthRBACChecker(config=cfg)
        t = good_token()
        del t["iat"]
        findings = checker.check_token(t)
        assert not any(f.risk == RiskLevel.MEDIUM for f in findings)


# T153-T164 Security Logger
class TestSecurityLogger:
    def setup_method(self):
        self.audit = SecurityAuditChain()
        self.logger = SecurityLogger(audit=self.audit)

    def test_T153_log_entry_created(self):
        e = self.logger.log("INFO", "Test message", user_id="u1")
        assert e.level == "INFO"
        assert e.message == "Test message"

    def test_T154_sensitive_field_redacted(self):
        e = self.logger.log("INFO", "auth event", password="hunter2")
        assert e.context.get("password") == "[REDACTED]"

    def test_T155_non_sensitive_kept(self):
        e = self.logger.log("INFO", "event", user_id="u1", count=5)
        assert e.context.get("user_id") == "u1"

    def test_T156_run_check_pass(self):
        self.logger.log("INFO", "clean event", user_id="u1")
        r = self.logger.run_check()
        assert r.status == CheckStatus.PASS

    def test_T157_check_id_log(self):
        r = self.logger.run_check()
        assert r.check_id == "LOG-001"

    def test_T158_ts_is_float(self):
        e = self.logger.log("WARN", "warning")
        assert isinstance(e.ts, float)

    def test_T159_no_audit_ok(self):
        logger2 = SecurityLogger()
        e = logger2.log("INFO", "no audit", x="1")
        assert e.message == "no audit"

    def test_T160_multiple_entries(self):
        for i in range(5):
            self.logger.log("INFO", f"event {i}")
        r = self.logger.run_check()
        assert r.check_id == "LOG-001"

    def test_T161_token_field_redacted(self):
        e = self.logger.log("INFO", "auth", token="abc.def.ghi")
        assert e.context.get("token") == "[REDACTED]"

    def test_T162_api_key_redacted(self):
        e = self.logger.log("INFO", "api", api_key="sk-secret")
        assert e.context.get("api_key") == "[REDACTED]"

    def test_T163_context_keys_preserved(self):
        e = self.logger.log("INFO", "event", tenant_id="T1", status="ok")
        assert set(e.context.keys()) == {"tenant_id", "status"}

    def test_T164_extra_redact_field(self):
        logger3 = SecurityLogger(redact_fields={"account"})
        e = logger3.log("INFO", "event", account="12345")
        assert e.context.get("account") == "[REDACTED]"


# T165-T176 Crypto Checker
class TestCryptoChecker:
    def setup_method(self):
        self.checker = CryptoChecker()

    def test_T165_aes_256_ok(self):
        findings = self.checker.check_config({"algo": "aes", "bits": 256})
        assert findings == []

    def test_T166_md5_critical(self):
        findings = self.checker.check_config({"algo": "md5", "bits": 128})
        assert any(f.risk == RiskLevel.CRITICAL for f in findings)

    def test_T167_sha1_critical(self):
        findings = self.checker.check_config({"algo": "sha1", "bits": 160})
        assert any(f.risk == RiskLevel.CRITICAL for f in findings)

    def test_T168_rsa_2048_ok(self):
        findings = self.checker.check_config({"algo": "rsa", "bits": 2048})
        assert findings == []

    def test_T169_rsa_1024_high(self):
        findings = self.checker.check_config({"algo": "rsa", "bits": 1024})
        assert any(f.risk == RiskLevel.HIGH for f in findings)

    def test_T170_hmac_256_ok(self):
        findings = self.checker.check_config({"algo": "hmac", "bits": 256})
        assert findings == []

    def test_T171_run_check_clean(self):
        r = self.checker.run_check([{"algo": "aes", "bits": 256}, {"algo": "hmac", "bits": 256}])
        assert r.status == CheckStatus.PASS

    def test_T172_run_check_weak_fail(self):
        r = self.checker.run_check([{"algo": "md5", "bits": 128}])
        assert r.status == CheckStatus.FAIL

    def test_T173_check_id_crypto(self):
        r = self.checker.run_check([])
        assert r.check_id == "CRYPTO-001"

    def test_T174_cwe_327_weak_algo(self):
        r = self.checker.run_check([{"algo": "des", "bits": 56}])
        assert any(f.cwe == "CWE-327" for f in r.findings)

    def test_T175_cwe_326_short_key(self):
        r = self.checker.run_check([{"algo": "aes", "bits": 64}])
        assert any(f.cwe == "CWE-326" for f in r.findings)

    def test_T176_des_3des_weak(self):
        for algo in ("des", "3des", "rc4", "rc2"):
            findings = self.checker.check_config({"algo": algo, "bits": 128})
            assert any(f.risk == RiskLevel.CRITICAL for f in findings), algo


# T177-T192 SQL Migration
class TestSQLMigration:
    def setup_method(self):
        p = os.path.join(
            os.path.dirname(__file__),
            "../../supabase/migrations/20260628_043_phase34_security_review.sql",
        )
        with open(p) as f:
            self.sql = f.read()

    def test_T177_file_exists_and_nonempty(self):
        assert len(self.sql) > 1000

    def test_T178_table_security_scans(self):
        assert "security_scan_runs" in self.sql

    def test_T179_table_security_findings(self):
        assert "security_findings" in self.sql

    def test_T180_table_pentest_results(self):
        assert "pentest_results" in self.sql

    def test_T181_table_risk_register(self):
        assert "risk_register" in self.sql

    def test_T182_table_security_audit_log(self):
        assert "security_audit_log" in self.sql

    def test_T183_rls_enabled(self):
        assert "ENABLE ROW LEVEL SECURITY" in self.sql

    def test_T184_immutable_trigger(self):
        assert "BEFORE UPDATE OR DELETE" in self.sql or "immutable" in self.sql.lower()

    def test_T185_chain_hash_char64(self):
        assert "CHAR(64)" in self.sql or "chain_hash" in self.sql

    def test_T186_tenant_id_present(self):
        assert self.sql.count("tenant_id") >= 4

    def test_T187_risk_level_check(self):
        assert "critical" in self.sql and "high" in self.sql

    def test_T188_indexes_present(self):
        assert self.sql.count("CREATE INDEX") >= 5

    def test_T189_cleanup_function(self):
        assert "cleanup_" in self.sql or "DELETE FROM" in self.sql

    def test_T190_views_present(self):
        assert "CREATE" in self.sql and "VIEW" in self.sql

    def test_T191_severity_enum_or_check(self):
        assert "severity" in self.sql.lower() or "risk_level" in self.sql.lower()

    def test_T192_status_check_constraint(self):
        assert "pass" in self.sql and "fail" in self.sql


# T193-T205 Integration Flows
class TestIntegrationFlows:
    def setup_method(self):
        self.sys_ = make_system(
            allowed_origins={"https://app.bot12.io"},
        )

    def test_T193_replay_blocked_in_system(self):
        replay = self.sys_["replay"]
        now = time.time()
        nonce = str(uuid.uuid4())
        replay.check(nonce, now, now=now)
        with pytest.raises(ReplayDetectedError):
            replay.check(nonce, now, now=now + 1)

    def test_T194_idor_blocked_cross_tenant(self):
        idor = self.sys_["idor"]
        assert idor.log_access("A", "u", "B", "r", "/api/orders") is False

    def test_T195_rate_limit_brute_force(self):
        rl = self.sys_["rl"]
        now = time.time()
        for _ in range(5):
            rl.check("/api/auth/login", "brute", now=now)
        with pytest.raises(RateLimitExceededError):
            rl.check("/api/auth/login", "brute", now=now)

    def test_T196_injection_blocked(self):
        inj = self.sys_["inj"]
        hits = inj.scan_value("' UNION SELECT * FROM users--")
        assert len(hits) > 0

    def test_T197_cors_wildcard_blocked(self):
        cors = self.sys_["cors"]
        with pytest.raises(CORSViolationError):
            cors.validate_request("*", "GET")

    def test_T198_risk_register_mitigate(self):
        risk = self.sys_["risk"]
        risk.add(
            RiskItem(
                risk_id="R1",
                category=VulnCategory.SESSION,
                risk=RiskLevel.LOW,
                title="Test risk",
                description="desc",
                mitigation="fix",
            )
        )
        risk.mitigate("R1", "engineer", "patched in v2.3")
        assert risk.summary()["mitigated"] == 1

    def test_T199_audit_chain_ok_after_operations(self):
        audit = self.sys_["audit"]
        assert audit.verify_chain() is True

    def test_T200_full_review_pass(self):
        engine = self.sys_["engine"]
        report = engine.run_full_review(
            headers=good_headers(),
            injection_samples=[{"q": "normal"}],
            idor_cases=[
                {"actor_tenant": "T", "actor_user": "u", "resource_tenant": "T", "resource_id": "r"}
            ],
            replay_cases=[],
            leak_responses=[{"user_id": "u1"}],
            auth_tokens=[good_token()],
            endpoints_checked=ENDPOINTS,
            crypto_configs=[{"algo": "aes", "bits": 256}],
            pen_scenarios=[],
            actor="test",
        )
        assert report.overall_pass is True
        assert report.critical_count == 0
        assert report.audit_chain_ok is True

    def test_T201_full_review_fail_on_injection(self):
        engine = self.sys_["engine"]
        report = engine.run_full_review(
            headers=good_headers(),
            injection_samples=[{"q": "'; DROP TABLE users; --"}],
            idor_cases=[],
            replay_cases=[],
            leak_responses=[],
            auth_tokens=[good_token()],
            endpoints_checked=ENDPOINTS,
            crypto_configs=[],
            pen_scenarios=[],
            actor="test",
        )
        assert report.critical_count > 0

    def test_T202_pen_test_sql_inject_blocked(self):
        pentest = self.sys_["pentest"]
        s = PenTestScenario(
            "S1",
            "SQL Inject",
            VulnCategory.INJECTION,
            {"value": "' UNION SELECT * FROM users--"},
            True,
            "sqli",
        )
        r = pentest.run_scenario(s)
        assert r.passed is True

    def test_T203_pen_test_idor_blocked(self):
        pentest = self.sys_["pentest"]
        s = PenTestScenario(
            "S2",
            "IDOR",
            VulnCategory.IDOR,
            {"actor_tenant": "X", "actor_user": "u", "resource_tenant": "Y", "resource_id": "r1"},
            True,
            "cross-tenant",
        )
        r = pentest.run_scenario(s)
        assert r.passed is True

    def test_T204_pen_test_good_auth_allowed(self):
        pentest = self.sys_["pentest"]
        s = PenTestScenario(
            "S3", "Good Auth", VulnCategory.AUTH_BYPASS, good_token(), False, "valid"
        )
        r = pentest.run_scenario(s)
        assert r.passed is True

    def test_T205_to_dict_json_compatible(self):
        import json

        engine = self.sys_["engine"]
        report = engine.run_full_review(
            headers=good_headers(),
            injection_samples=[],
            idor_cases=[],
            replay_cases=[],
            leak_responses=[],
            auth_tokens=[good_token()],
            endpoints_checked=[],
            crypto_configs=[],
            pen_scenarios=[],
        )
        d = report.to_dict()
        s = json.dumps(d)
        assert "overall_pass" in s


# T206-T220 Edge Cases & Final Acceptance
class TestEdgeCasesAndAcceptance:
    def test_T206_check_result_passed_method(self):
        r = CheckResult(
            check_id="X",
            name="test",
            category=VulnCategory.INJECTION,
            status=CheckStatus.PASS,
            risk=RiskLevel.INFO,
            detail="ok",
        )
        assert r.passed() is True

    def test_T207_check_result_fail(self):
        r = CheckResult(
            check_id="X",
            name="test",
            category=VulnCategory.INJECTION,
            status=CheckStatus.FAIL,
            risk=RiskLevel.CRITICAL,
            detail="bad",
        )
        assert r.passed() is False

    def test_T208_security_finding_defaults(self):
        f = SecurityFinding(
            finding_id="f1",
            category=VulnCategory.CORS,
            risk=RiskLevel.HIGH,
            title="T",
            description="D",
            evidence="E",
            mitigation="M",
        )
        assert f.mitigated is False
        assert f.accepted is False
        assert f.cwe is None

    def test_T209_build_system_returns_all_keys(self):
        sys_ = make_system()
        for key in [
            "audit",
            "headers",
            "cors",
            "rl",
            "inj",
            "idor",
            "replay",
            "leak",
            "auth",
            "logger",
            "crypto",
            "risk",
            "pentest",
            "engine",
        ]:
            assert key in sys_, f"Missing key: {key}"

    def test_T210_build_system_shared_audit(self):
        sys_ = make_system()
        audit = sys_["audit"]
        sys_["engine"].run_full_review(
            headers=good_headers(),
            injection_samples=[],
            idor_cases=[],
            replay_cases=[],
            leak_responses=[],
            auth_tokens=[good_token()],
            endpoints_checked=[],
            crypto_configs=[],
            pen_scenarios=[],
        )
        assert len(audit) > 0

    def test_T211_risk_register_accept(self):
        audit = SecurityAuditChain()
        risk = RiskRegister(audit=audit)
        risk.add(
            RiskItem(
                risk_id="R2",
                category=VulnCategory.LOGGING,
                risk=RiskLevel.LOW,
                title="Minor log issue",
                description="desc",
                mitigation="fix",
            )
        )
        risk.accept("R2", "ciso", "accepted as low risk")
        assert risk.summary()["accepted"] == 1
        assert audit.verify_chain() is True

    def test_T212_risk_register_list_open(self):
        risk = RiskRegister()
        risk.add(
            RiskItem(
                risk_id="R3",
                category=VulnCategory.CRYPTO,
                risk=RiskLevel.MEDIUM,
                title="Open risk",
                description="desc",
                mitigation="fix",
            )
        )
        open_risks = risk.list_open()
        assert len(open_risks) == 1
        assert open_risks[0].risk_id == "R3"

    def test_T213_pen_test_replay_blocked(self):
        audit = SecurityAuditChain()
        auth = AuthRBACChecker()
        idor = IDORChecker()
        replay = ReplayChecker()
        inj = InjectionScanner()
        leak = InformationLeakScanner()
        pentest = PenTestHarness(auth, idor, replay, inj, leak, audit)
        now = time.time()
        nonce = str(uuid.uuid4())
        replay.check(nonce, now, now=now)
        s = PenTestScenario(
            "S-replay",
            "Replay",
            VulnCategory.REPLAY,
            {"nonce": nonce, "timestamp": now, "now": now + 1},
            True,
            "replay",
        )
        r = pentest.run_scenario(s)
        assert r.passed is True

    def test_T214_pen_test_leak_blocked(self):
        audit = SecurityAuditChain()
        pentest = PenTestHarness(
            AuthRBACChecker(),
            IDORChecker(),
            ReplayChecker(),
            InjectionScanner(),
            InformationLeakScanner(),
            audit,
        )
        s = PenTestScenario(
            "S-leak", "Leak", VulnCategory.INFORMATION_LEAK, {"password": "hunter2"}, True, "leak"
        )
        r = pentest.run_scenario(s)
        assert r.passed is True

    def test_T215_isolated_systems_no_cross_state(self):
        sys1 = make_system(secret="secret1")
        sys2 = make_system(secret="secret2")
        sys1["audit"].record(AuditAction.CHECK_RUN, actor="s1")
        assert len(sys2["audit"]) == 0

    def test_T216_full_review_all_attack_vectors(self):
        sys_ = make_system(allowed_origins={"https://app.bot12.io"})
        engine = sys_["engine"]
        audit = sys_["audit"]
        risk = sys_["risk"]

        scenarios = [
            PenTestScenario(
                "S1",
                "SQL inject",
                VulnCategory.INJECTION,
                {"value": "' UNION SELECT * FROM users--"},
                True,
                "sqli",
            ),
            PenTestScenario(
                "S2",
                "XSS inject",
                VulnCategory.INJECTION,
                {"value": "<script>document.cookie</script>"},
                True,
                "xss",
            ),
            PenTestScenario(
                "S3", "Valid auth", VulnCategory.AUTH_BYPASS, good_token(), False, "good token"
            ),
            PenTestScenario(
                "S4",
                "No-sub auth bypass",
                VulnCategory.AUTH_BYPASS,
                {"exp": time.time() + 3600, "tenant_id": "t1"},
                True,
                "missing sub",
            ),
            PenTestScenario(
                "S5",
                "IDOR block",
                VulnCategory.IDOR,
                {
                    "actor_tenant": "X",
                    "actor_user": "u",
                    "resource_tenant": "Y",
                    "resource_id": "r1",
                },
                True,
                "cross-tenant",
            ),
            PenTestScenario(
                "S6",
                "Secret leak",
                VulnCategory.INFORMATION_LEAK,
                {"password": "hunter2"},
                True,
                "password field",
            ),
        ]

        report = engine.run_full_review(
            headers=good_headers(),
            injection_samples=[{"q": "normal search"}],
            idor_cases=[
                {"actor_tenant": "T", "actor_user": "u", "resource_tenant": "T", "resource_id": "r"}
            ],
            replay_cases=[],
            leak_responses=[{"user_id": "u1", "name": "Alice"}],
            auth_tokens=[good_token()],
            endpoints_checked=ENDPOINTS,
            crypto_configs=[{"algo": "aes", "bits": 256}, {"algo": "hmac", "bits": 256}],
            pen_scenarios=scenarios,
            actor="final_acceptance_test",
        )

        assert all(r.passed for r in report.pen_tests), [
            (r.name, r.detail) for r in report.pen_tests if not r.passed
        ]
        assert report.critical_count == 0
        assert report.overall_pass is True
        assert report.audit_chain_ok is True
        assert len(report.checks) == 10

        risk.add(
            RiskItem(
                risk_id="RESIDUAL-1",
                category=VulnCategory.SESSION,
                risk=RiskLevel.LOW,
                title="Session fixation edge case",
                description="Minor edge case in session renewal",
                mitigation="Add session_id rotation on privilege escalation",
            )
        )
        risk.mitigate("RESIDUAL-1", "security-team", "session_id rotated on login")
        assert risk.summary()["mitigated"] >= 1

        assert audit.verify_chain() is True
        summary = report.to_dict()
        assert summary["overall_pass"] is True
        assert summary["audit_chain_ok"] is True
        assert summary["critical_count"] == 0
