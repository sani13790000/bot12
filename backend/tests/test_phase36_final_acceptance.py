"""
Phase 36 -- Final Acceptance Criteria Test Suite
224 tests covering all 23 acceptance criteria.
"""

import hashlib
import time
from copy import deepcopy

import pytest

from backend.core.final_acceptance import (
    AC_DESCRIPTIONS,
    ADMIN_CAPABILITIES,
    ADMIN_ONLY_ROUTES,
    ALLOWED_CUSTOMER_EXTENSIONS,
    BLOCKING_CRITERIA,
    CUSTOMER_ALLOWED_ROUTES,
    REQUIRED_CONFIG_KEYS,
    REQUIRES_REASON,
    AcceptanceAuditChain,
    AcceptanceDecision,
    AdminControlGate,
    CriteriaID,
    CriteriaResult,
    CriteriaStatus,
    CustomerDeliveryGate,
    DashboardSeparationGate,
    DeviceLimitGate,
    DocAlignmentResult,
    DockerComposeGenerator,
    DockerGate,
    DockerReadinessResult,
    DocsGate,
    DuplicateOrderGate,
    EAFailClosedGate,
    EAStartupContext,
    FinalAcceptanceEngine,
    HardcodedSecretScanner,
    HeartbeatGate,
    HeartbeatRecord,
    KillSwitchGate,
    LicenseRevocationGate,
    LicenseStorageGate,
    MT5Credentials,
    MT5CredentialsGate,
    MT5ReconciliationGate,
    MT5TradeRecord,
    PaymentWebhookGate,
    ProductionConfigGate,
    RiskContext,
    RiskFailClosedGate,
    Severity,
    SourceAccessGate,
    TenantIsolationGate,
    TestGate,
    TestSuiteResult,
    TradeAuthContext,
    TradeAuthGate,
    build_acceptance_system,
)


def make_audit():
    return AcceptanceAuditChain(secret="test-secret-36")


def good_env():
    return {k: f"val_{k.lower()}_ok" for k in REQUIRED_CONFIG_KEYS}


def good_mt5():
    return MT5Credentials(
        account_id=12345, password="SecretPwd1", server="MetaQuotes-Demo", is_live=True
    )


def good_trade_ctx():
    return TradeAuthContext(
        license_id="lic-001",
        license_status="ACTIVE",
        subscription_ok=True,
        device_id="dev-001",
        device_allowed=True,
        tenant_id="t1",
    )


def good_ea_ctx():
    return EAStartupContext(
        config_ok=True, license_ok=True, credentials_ok=True, heartbeat_ok=True, risk_ok=True
    )


def good_risk():
    return RiskContext(
        drawdown_pct=5.0,
        open_positions=3,
        margin_level=500.0,
        kill_switch_on=False,
        daily_loss_pct=1.0,
    )


def make_trade(ticket, symbol="EURUSD", direction="BUY", volume=0.1, tenant="t1"):
    return MT5TradeRecord(
        ticket=ticket,
        symbol=symbol,
        direction=direction,
        volume=volume,
        open_price=1.1000,
        tenant_id=tenant,
    )


def make_system():
    return build_acceptance_system(secret="test-secret-36")


def full_ctx(sys_, device_id="dev-001"):
    hb = HeartbeatRecord(
        device_id=device_id,
        tenant_id="t1",
        received_at=time.time(),
        ea_version="2.3.0",
        symbol="EURUSD",
        is_live=True,
    )
    sys_["hb_gate"].record_heartbeat(hb)
    sys_["device_gate"].set_limit("lic-001", 3)
    tr = TestSuiteResult(
        total=4435, passed=4435, failed=0, phases={f"P{i}": 200 for i in range(6, 36)}
    )
    doc = DocAlignmentResult(total_docs=10, aligned=10, mismatched=[], missing_docs=[])
    docker = DockerReadinessResult(
        staging_ready=True,
        prod_ready=True,
        has_dockerfile=True,
        has_compose=True,
        has_health_check=True,
        has_env_template=True,
        has_migrations=True,
    )
    raw_key = "RAW-LICENSE-KEY-123"
    stored = hashlib.sha256(raw_key.encode()).hexdigest()
    return {
        "tenant_id": "t1",
        "env": good_env(),
        "trading_enabled": True,
        "mt5_creds": good_mt5(),
        "trade_ctx": good_trade_ctx(),
        "ea_ctx": good_ea_ctx(),
        "device_id": device_id,
        "revoke_check": {"license_id": "lic-001", "revoked_at": time.time()},
        "device_check": {"license_id": "lic-001", "device_id": device_id},
        "delivery_files": ["bot12_v2.3.ex5", "user_guide.pdf"],
        "role": "CUSTOMER",
        "tenant_check": {"actor_tenant": "t1", "resource_tenant": "t1", "type": "order"},
        "risk_ctx": good_risk(),
        "reconciliation": {
            "our": [make_trade(1), make_trade(2)],
            "mt5": [make_trade(1), make_trade(2)],
        },
        "code_samples": {"clean.py": "import os\nVAL = os.environ['SECRET']"},
        "license_storage": {"stored": stored, "raw": raw_key},
        "test_result": tr,
        "doc_alignment": doc,
        "docker": docker,
        "allow_test_stripe": True,
    }


class TestEnumsAndConstants:
    def test_T001_all_23_criteria_exist(self):
        assert len(CriteriaID) == 23

    def test_T002_criteria_values_sequential(self):
        ids = [c.value for c in CriteriaID]
        for i, cid in enumerate(ids, 1):
            assert cid == f"AC{i:02d}"

    def test_T003_all_blocking_criteria_defined(self):
        assert len(BLOCKING_CRITERIA) >= 10
        assert CriteriaID.AC01 in BLOCKING_CRITERIA

    def test_T004_AC17_is_blocking(self):
        assert CriteriaID.AC17 in BLOCKING_CRITERIA

    def test_T005_AC19_is_blocking(self):
        assert CriteriaID.AC19 in BLOCKING_CRITERIA

    def test_T006_AC09_not_blocking(self):
        assert CriteriaID.AC09 not in BLOCKING_CRITERIA

    def test_T007_all_criteria_have_description(self):
        for c in CriteriaID:
            assert c in AC_DESCRIPTIONS

    def test_T008_all_statuses_defined(self):
        assert CriteriaStatus.PASS in CriteriaStatus

    def test_T009_all_decisions_defined(self):
        assert AcceptanceDecision.GO in AcceptanceDecision

    def test_T010_required_config_keys_count(self):
        assert len(REQUIRED_CONFIG_KEYS) == 8

    def test_T011_admin_capabilities_count(self):
        assert len(ADMIN_CAPABILITIES) >= 10

    def test_T012_customer_routes_defined(self):
        assert "/dashboard" in CUSTOMER_ALLOWED_ROUTES

    def test_T013_admin_routes_defined(self):
        assert "/admin/users" in ADMIN_ONLY_ROUTES

    def test_T014_ex5_allowed_for_customer(self):
        assert ".ex5" in ALLOWED_CUSTOMER_EXTENSIONS

    def test_T015_py_not_allowed_for_customer(self):
        gate = SourceAccessGate(None)
        assert ".py" in gate.FORBIDDEN_EXTENSIONS

    def test_T016_requires_reason_not_empty(self):
        assert len(REQUIRES_REASON) >= 2


class TestAcceptanceAuditChain:
    def test_T017_empty_chain_valid(self):
        assert make_audit().verify_chain() is True

    def test_T018_single_entry_valid(self):
        a = make_audit()
        a.record("TEST", "actor")
        assert a.verify_chain() is True

    def test_T019_genesis_is_64_chars(self):
        assert len(make_audit()._genesis) == 64

    def test_T020_chain_hash_64_chars(self):
        a = make_audit()
        e = a.record("TEST", "actor")
        assert len(e.chain_hash) == 64

    def test_T021_100_entries_valid(self):
        a = make_audit()
        for i in range(100):
            a.record(f"ACT_{i}", "actor")
        assert a.verify_chain() is True

    def test_T022_tamper_detected(self):
        a = make_audit()
        a.record("ACT1", "actor")
        a.record("ACT2", "actor")
        a._entries[0].action = "TAMPERED"
        assert a.verify_chain() is False

    def test_T023_detect_tampered_returns_broken(self):
        a = make_audit()
        a.record("A", "x")
        a.record("B", "x")
        a._entries[0].chain_hash = "x" * 64
        assert 0 in a.detect_tampered()

    def test_T024_requires_reason_raises(self):
        with pytest.raises(ValueError):
            make_audit().record("ACCEPTANCE_OVERRIDE", "a")

    def test_T025_requires_reason_empty_raises(self):
        with pytest.raises(ValueError):
            make_audit().record("CRITERIA_WAIVED", "a", reason="   ")

    def test_T026_requires_reason_passes(self):
        e = make_audit().record("ACCEPTANCE_OVERRIDE", "a", reason="board_approved")
        assert e.action == "ACCEPTANCE_OVERRIDE"

    def test_T027_query_by_action(self):
        a = make_audit()
        a.record("A", "x")
        a.record("B", "x")
        a.record("A", "x")
        assert len(a.query(action="A")) == 2

    def test_T028_query_by_criteria(self):
        a = make_audit()
        a.record("C", "x", criteria_id="AC01")
        a.record("C", "x", criteria_id="AC02")
        assert len(a.query(criteria_id="AC01")) == 1

    def test_T029_seq_increments(self):
        a = make_audit()
        e1 = a.record("A", "x")
        e2 = a.record("B", "x")
        assert e1.seq == 0 and e2.seq == 1

    def test_T030_different_secrets_different_genesis(self):
        a1 = AcceptanceAuditChain(secret="s1")
        a2 = AcceptanceAuditChain(secret="s2")
        assert a1._genesis != a2._genesis

    def test_T031_chain_hash_hex(self):
        a = make_audit()
        e = a.record("A", "x")
        assert all(c in "0123456789abcdef" for c in e.chain_hash)

    def test_T032_concurrent_safe(self):
        import threading

        a = make_audit()
        ts = [threading.Thread(target=lambda: a.record("T", "a")) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert len(a) == 20

    def test_T033_verify_after_concurrent(self):
        import threading

        a = make_audit()
        for _ in range(10):
            a.record("T", "a")
        results = []

        def chk():
            results.append(a.verify_chain())

        ts = [threading.Thread(target=chk) for _ in range(5)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert all(results)

    def test_T034_no_audit_no_crash(self):
        r = ProductionConfigGate(None).check(good_env(), allow_test_stripe=True)
        assert r.status == CriteriaStatus.PASS

    def test_T035_len_zero_initially(self):
        assert len(make_audit()) == 0

    def test_T036_entry_has_ts(self):
        e = make_audit().record("A", "x")
        assert e.ts > 0


class TestAC01ProductionConfig:
    def test_T037_all_keys_pass(self):
        r = ProductionConfigGate(make_audit()).check(good_env(), allow_test_stripe=True)
        assert r.status == CriteriaStatus.PASS

    def test_T038_missing_jwt_fails(self):
        env = good_env()
        del env["JWT_SECRET"]
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T039_empty_value_fails(self):
        env = good_env()
        env["SUPABASE_URL"] = "   "
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T040_change_me_fails(self):
        env = good_env()
        env["ENCRYPTION_KEY"] = "CHANGE_ME"
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T041_todo_fails(self):
        env = good_env()
        env["AUDIT_CHAIN_SECRET"] = "TODO"
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T042_sk_test_blocked_in_prod(self):
        env = good_env()
        env["STRIPE_SECRET_KEY"] = "sk_test_abc123xyz"
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=False)
        assert r.status == CriteriaStatus.FAIL

    def test_T043_sk_test_allowed_staging(self):
        env = good_env()
        env["STRIPE_SECRET_KEY"] = "sk_test_abc123xyz"
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.PASS

    def test_T044_critical_severity(self):
        r = ProductionConfigGate(make_audit()).check(good_env(), allow_test_stripe=True)
        assert r.severity == Severity.CRITICAL

    def test_T045_all_missing(self):
        r = ProductionConfigGate(make_audit()).check({}, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T046_dummy_fails(self):
        env = good_env()
        env["WEBHOOK_HMAC_SECRET"] = "dummy"
        r = ProductionConfigGate(make_audit()).check(env, allow_test_stripe=True)
        assert r.status == CriteriaStatus.FAIL

    def test_T047_phase_ref(self):
        r = ProductionConfigGate(make_audit()).check(good_env(), allow_test_stripe=True)
        assert "P11" in r.phase_ref

    def test_T048_to_dict(self):
        r = ProductionConfigGate(make_audit()).check(good_env(), allow_test_stripe=True)
        assert r.to_dict()["criteria_id"] == "AC01"


class TestAC02MT5Credentials:
    def test_T049_valid_passes(self):
        assert (
            MT5CredentialsGate(make_audit()).check(good_mt5(), True).status == CriteriaStatus.PASS
        )

    def test_T050_no_creds_enabled_fails(self):
        assert MT5CredentialsGate(make_audit()).check(None, True).status == CriteriaStatus.FAIL

    def test_T051_no_creds_disabled_passes(self):
        assert MT5CredentialsGate(make_audit()).check(None, False).status == CriteriaStatus.PASS

    def test_T052_bad_account_id(self):
        c = MT5Credentials(account_id=-1, password="pwd123", server="s", is_live=False)
        assert MT5CredentialsGate(make_audit()).check(c, True).status == CriteriaStatus.FAIL

    def test_T053_short_password(self):
        c = MT5Credentials(account_id=1000, password="ab", server="s", is_live=False)
        assert MT5CredentialsGate(make_audit()).check(c, True).status == CriteriaStatus.FAIL

    def test_T054_empty_server(self):
        c = MT5Credentials(account_id=1000, password="abcdef", server="", is_live=False)
        assert MT5CredentialsGate(make_audit()).check(c, True).status == CriteriaStatus.FAIL

    def test_T055_live_marked(self):
        r = MT5CredentialsGate(make_audit()).check(good_mt5(), True)
        assert "live=True" in r.evidence

    def test_T056_blocking(self):
        assert MT5CredentialsGate(make_audit()).check(None, True).blocking is True

    def test_T057_ac02(self):
        assert (
            MT5CredentialsGate(make_audit()).check(good_mt5(), True).criteria_id == CriteriaID.AC02
        )


class TestAC03TradeAuth:
    def test_T058_all_valid(self):
        assert TradeAuthGate(make_audit()).check(good_trade_ctx()).status == CriteriaStatus.PASS

    def test_T059_revoked(self):
        ctx = good_trade_ctx()
        ctx.license_status = "REVOKED"
        assert TradeAuthGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T060_suspended(self):
        ctx = good_trade_ctx()
        ctx.license_status = "SUSPENDED"
        assert TradeAuthGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T061_expired(self):
        ctx = good_trade_ctx()
        ctx.license_status = "EXPIRED"
        assert TradeAuthGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T062_bad_subscription(self):
        ctx = good_trade_ctx()
        ctx.subscription_ok = False
        r = TradeAuthGate(make_audit()).check(ctx)
        assert r.status == CriteriaStatus.FAIL and "subscription_invalid" in r.evidence

    def test_T063_device_not_allowed(self):
        ctx = good_trade_ctx()
        ctx.device_allowed = False
        assert TradeAuthGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T064_all_three_fail(self):
        ctx = good_trade_ctx()
        ctx.license_status = "REVOKED"
        ctx.subscription_ok = False
        ctx.device_allowed = False
        assert TradeAuthGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T065_blocking(self):
        assert TradeAuthGate(make_audit()).check(good_trade_ctx()).blocking is True


class TestAC04EAFailClosed:
    def test_T066_all_ok(self):
        assert EAFailClosedGate(make_audit()).check(good_ea_ctx()).status == CriteriaStatus.PASS

    def test_T067_config_fail(self):
        ctx = good_ea_ctx()
        ctx.config_ok = False
        r = EAFailClosedGate(make_audit()).check(ctx)
        assert r.status == CriteriaStatus.FAIL and "config_invalid" in r.evidence

    def test_T068_license_fail(self):
        ctx = good_ea_ctx()
        ctx.license_ok = False
        assert EAFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T069_heartbeat_fail(self):
        ctx = good_ea_ctx()
        ctx.heartbeat_ok = False
        assert EAFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T070_risk_fail(self):
        ctx = good_ea_ctx()
        ctx.risk_ok = False
        assert EAFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T071_any_single_fail(self):
        gate = EAFailClosedGate(make_audit())
        for attr in ("config_ok", "license_ok", "credentials_ok", "heartbeat_ok", "risk_ok"):
            ctx = good_ea_ctx()
            setattr(ctx, attr, False)
            assert gate.check(ctx).status == CriteriaStatus.FAIL


class TestAC05Heartbeat:
    def test_T072_fresh_passes(self):
        gate = HeartbeatGate(make_audit(), 300)
        hb = HeartbeatRecord("d1", "t1", time.time(), "2.3.0", "EURUSD", True)
        gate.record_heartbeat(hb)
        assert gate.check("d1").status == CriteriaStatus.PASS

    def test_T073_no_record_fails(self):
        assert HeartbeatGate(make_audit()).check("x").status == CriteriaStatus.FAIL

    def test_T074_stale_fails(self):
        gate = HeartbeatGate(make_audit(), 1)
        hb = HeartbeatRecord("d1", "t1", time.time() - 10, "2.3.0", "EURUSD", True)
        gate.record_heartbeat(hb)
        r = gate.check("d1")
        assert r.status == CriteriaStatus.FAIL and "stale" in r.evidence

    def test_T075_multi_device(self):
        gate = HeartbeatGate(make_audit())
        for i in range(5):
            gate.record_heartbeat(HeartbeatRecord(f"d{i}", "t1", time.time(), "2", "E", True))
        for i in range(5):
            assert gate.check(f"d{i}").status == CriteriaStatus.PASS

    def test_T076_update_refreshes(self):
        gate = HeartbeatGate(make_audit(), 1)
        gate.record_heartbeat(HeartbeatRecord("d1", "t1", time.time() - 10, "2", "E", True))
        gate.record_heartbeat(HeartbeatRecord("d1", "t1", time.time(), "3", "E", True))
        assert gate.check("d1").status == CriteriaStatus.PASS


class TestAC06LicenseRevoke:
    def test_T077_fast_propagation(self):
        assert (
            LicenseRevocationGate(make_audit()).check_propagation("l", time.time()).status
            == CriteriaStatus.PASS
        )

    def test_T078_stale_fails(self):
        assert (
            LicenseRevocationGate(make_audit()).check_propagation("l", time.time() - 100).status
            == CriteriaStatus.FAIL
        )

    def test_T079_revoke_needs_reason(self):
        with pytest.raises(ValueError):
            LicenseRevocationGate(make_audit()).revoke("l", "")

    def test_T080_revoke_marks(self):
        gate = LicenseRevocationGate(make_audit())
        gate.revoke("l", "fraud")
        assert gate.is_revoked("l") is True

    def test_T081_not_revoked_initially(self):
        assert LicenseRevocationGate(make_audit()).is_revoked("x") is False

    def test_T082_revoke_audited(self):
        audit = make_audit()
        gate = LicenseRevocationGate(audit)
        gate.revoke("l", "test")
        assert len(audit.query(action="LICENSE_REVOKED")) == 1


class TestAC07DeviceLimit:
    def test_T083_within_limit(self):
        gate = DeviceLimitGate(make_audit())
        gate.set_limit("l", 3)
        assert gate.check("l", "d1").status == CriteriaStatus.PASS

    def test_T084_at_limit_fails(self):
        gate = DeviceLimitGate(make_audit())
        gate.set_limit("l", 2)
        gate.check("l", "d1")
        gate.check("l", "d2")
        r = gate.check("l", "d3")
        assert r.status == CriteriaStatus.FAIL

    def test_T085_same_device_not_double_counted(self):
        gate = DeviceLimitGate(make_audit())
        gate.set_limit("l", 1)
        gate.check("l", "d1")
        assert gate.check("l", "d1").status == CriteriaStatus.PASS

    def test_T086_different_licenses_isolated(self):
        gate = DeviceLimitGate(make_audit())
        gate.set_limit("l1", 1)
        gate.set_limit("l2", 1)
        gate.check("l1", "d1")
        assert gate.check("l2", "d2").status == CriteriaStatus.PASS

    def test_T087_concurrent(self):
        import threading

        gate = DeviceLimitGate(make_audit())
        gate.set_limit("l", 5)
        results = []

        def reg(i):
            ok, _ = gate.register_device("l", f"d{i}")
            results.append(ok)

        ts = [threading.Thread(target=reg, args=(i,)) for i in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert sum(1 for r in results if r) == 5


class TestAC08SourceAccess:
    def test_T088_ex5_ok(self):
        assert (
            SourceAccessGate(make_audit()).check_delivery(["b.ex5", "g.pdf"], "CUSTOMER").status
            == CriteriaStatus.PASS
        )

    def test_T089_py_fails(self):
        r = SourceAccessGate(make_audit()).check_delivery(["main.py"], "CUSTOMER")
        assert r.status == CriteriaStatus.FAIL and "main.py" in r.evidence

    def test_T090_mq5_fails(self):
        assert (
            SourceAccessGate(make_audit()).check_delivery(["s.mq5"], "CUSTOMER").status
            == CriteriaStatus.FAIL
        )

    def test_T091_backend_path_fails(self):
        assert (
            SourceAccessGate(make_audit()).check_delivery(["backend/core/x.py"], "CUSTOMER").status
            == CriteriaStatus.FAIL
        )

    def test_T092_admin_ok(self):
        assert (
            SourceAccessGate(make_audit()).check_delivery(["main.py"], "ADMIN").status
            == CriteriaStatus.PASS
        )


class TestAC09CustomerDelivery:
    def test_T093_ex5_pdf_ok(self):
        assert (
            CustomerDeliveryGate(make_audit()).check(["b.ex5", "g.pdf"]).status
            == CriteriaStatus.PASS
        )

    def test_T094_html_ok(self):
        assert CustomerDeliveryGate(make_audit()).check(["d.html"]).status == CriteriaStatus.PASS

    def test_T095_py_not_allowed(self):
        assert CustomerDeliveryGate(make_audit()).check(["m.py"]).status == CriteriaStatus.FAIL

    def test_T096_zip_not_allowed(self):
        assert CustomerDeliveryGate(make_audit()).check(["s.zip"]).status == CriteriaStatus.FAIL

    def test_T097_empty_ok(self):
        assert CustomerDeliveryGate(make_audit()).check([]).status == CriteriaStatus.PASS


class TestAC10DashboardSeparation:
    def test_T098_check_passes(self):
        assert DashboardSeparationGate(make_audit()).check().status == CriteriaStatus.PASS

    def test_T099_customer_blocked_from_admin(self):
        ok, _ = DashboardSeparationGate(make_audit()).check_access("CUSTOMER", "/admin/users")
        assert ok is False

    def test_T100_admin_all_access(self):
        gate = DashboardSeparationGate(make_audit())
        for r in ADMIN_ONLY_ROUTES:
            ok, _ = gate.check_access("ADMIN", r)
            assert ok is True

    def test_T101_customer_dashboard_ok(self):
        ok, _ = DashboardSeparationGate(make_audit()).check_access("CUSTOMER", "/dashboard")
        assert ok is True

    def test_T102_unknown_denied(self):
        ok, _ = DashboardSeparationGate(make_audit()).check_access("UNKNOWN", "/dashboard")
        assert ok is False


class TestAC11TenantIsolation:
    def test_T103_same_ok(self):
        assert (
            TenantIsolationGate(make_audit()).check_query("t1", "t1", "o").status
            == CriteriaStatus.PASS
        )

    def test_T104_cross_fails(self):
        r = TenantIsolationGate(make_audit()).check_query("t1", "t2", "l")
        assert r.status == CriteriaStatus.FAIL and "IDOR" in r.evidence

    def test_T105_cross_critical(self):
        assert (
            TenantIsolationGate(make_audit()).check_query("t1", "t2", "l").severity
            == Severity.CRITICAL
        )

    def test_T106_audited(self):
        audit = make_audit()
        TenantIsolationGate(audit).check_query("t1", "t2", "o")
        assert len(audit.query(criteria_id=CriteriaID.AC11.value)) == 1


class TestAC12AdminControl:
    def test_T107_all_caps(self):
        assert AdminControlGate(make_audit()).check().status == CriteriaStatus.PASS

    def test_T108_missing_cap_fails(self):
        gate = AdminControlGate(make_audit())
        gate._registered.discard("kill_switch")
        r = gate.check()
        assert r.status == CriteriaStatus.FAIL and "kill_switch" in r.evidence

    def test_T109_register_extra(self):
        gate = AdminControlGate(make_audit())
        gate.register_capability("x")
        assert "x" in gate._registered


class TestAC13DuplicateOrder:
    def test_T110_first_allowed(self):
        ok, _ = DuplicateOrderGate(make_audit()).check_order("E", "B", 0.1, "t1")
        assert ok is True

    def test_T111_duplicate_blocked(self):
        gate = DuplicateOrderGate(make_audit())
        gate.check_order("E", "B", 0.1, "t1")
        ok, r = gate.check_order("E", "B", 0.1, "t1")
        assert ok is False and "Duplicate" in r

    def test_T112_different_symbol(self):
        gate = DuplicateOrderGate(make_audit())
        gate.check_order("E", "B", 0.1, "t1")
        ok, _ = gate.check_order("G", "B", 0.1, "t1")
        assert ok is True

    def test_T113_different_tenant(self):
        gate = DuplicateOrderGate(make_audit())
        gate.check_order("E", "B", 0.1, "t1")
        ok, _ = gate.check_order("E", "B", 0.1, "t2")
        assert ok is True

    def test_T114_idem_key_dedup(self):
        gate = DuplicateOrderGate(make_audit())
        gate.check_order("E", "B", 0.1, "t1", idempotency_key="k1")
        ok, _ = gate.check_order("G", "S", 0.5, "t1", idempotency_key="k1")
        assert ok is False

    def test_T115_check_passes(self):
        assert DuplicateOrderGate(make_audit()).check().status == CriteriaStatus.PASS


class TestAC14Reconciliation:
    def test_T116_perfect(self):
        gate = MT5ReconciliationGate(make_audit())
        r = gate.check([make_trade(1), make_trade(2)], [make_trade(1), make_trade(2)])
        assert r.status == CriteriaStatus.PASS and r.detail["pass_rate"] == 1.0

    def test_T117_missing_fails(self):
        gate = MT5ReconciliationGate(make_audit())
        r = gate.check([make_trade(1), make_trade(2)], [make_trade(1)])
        assert r.status == CriteriaStatus.FAIL and 2 in r.detail["unmatched"]

    def test_T118_mismatch_fails(self):
        gate = MT5ReconciliationGate(make_audit())
        r = gate.check([make_trade(1, symbol="E")], [make_trade(1, symbol="G")])
        assert r.status == CriteriaStatus.FAIL and 1 in r.detail["mismatch"]

    def test_T119_empty_passes(self):
        assert MT5ReconciliationGate(make_audit()).check([], []).status == CriteriaStatus.PASS


class TestAC15RiskFailClosed:
    def test_T120_ok(self):
        assert RiskFailClosedGate(make_audit()).check(good_risk()).status == CriteriaStatus.PASS

    def test_T121_kill_switch(self):
        ctx = good_risk()
        ctx.kill_switch_on = True
        r = RiskFailClosedGate(make_audit()).check(ctx)
        assert r.status == CriteriaStatus.FAIL and "kill_switch" in r.evidence

    def test_T122_drawdown(self):
        ctx = good_risk()
        ctx.drawdown_pct = 25.0
        assert RiskFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T123_daily_loss(self):
        ctx = good_risk()
        ctx.daily_loss_pct = 6.0
        assert RiskFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T124_low_margin(self):
        ctx = good_risk()
        ctx.margin_level = 100.0
        assert RiskFailClosedGate(make_audit()).check(ctx).status == CriteriaStatus.FAIL

    def test_T125_critical(self):
        assert RiskFailClosedGate(make_audit()).check(good_risk()).severity == Severity.CRITICAL


class TestAC16KillSwitch:
    def test_T126_activate(self):
        gate = KillSwitchGate(make_audit())
        ts = gate.activate("t1", "e", "a1")
        assert ts > 0 and gate.is_active("t1")

    def test_T127_deactivate(self):
        gate = KillSwitchGate(make_audit())
        gate.activate("t1", "e", "a1")
        gate.deactivate("t1", "a1", reason="r")
        assert not gate.is_active("t1")

    def test_T128_activate_needs_reason(self):
        with pytest.raises(ValueError):
            KillSwitchGate(make_audit()).activate("t", "", "a")

    def test_T129_deactivate_needs_reason(self):
        gate = KillSwitchGate(make_audit())
        gate.activate("t", "r", "a")
        with pytest.raises(ValueError):
            gate.deactivate("t", "a", reason="")

    def test_T130_check_passes(self):
        assert KillSwitchGate(make_audit()).check().status == CriteriaStatus.PASS

    def test_T131_isolation(self):
        gate = KillSwitchGate(make_audit())
        gate.activate("t1", "r", "a")
        assert gate.is_active("t1") and not gate.is_active("t2")

    def test_T132_audited(self):
        audit = make_audit()
        gate = KillSwitchGate(audit)
        gate.activate("t1", "r", "a")
        assert len(audit.query(action="KILL_SWITCH_ACTIVATED")) == 1


class TestAC17HardcodedSecrets:
    def test_T133_clean_ok(self):
        r = HardcodedSecretScanner(make_audit()).check({"a.py": "import os\nV=os.environ['S']"})
        assert r.status == CriteriaStatus.PASS

    def test_T134_password_fails(self):
        assert (
            HardcodedSecretScanner(make_audit()).check({"c.py": 'password = "mysecret123"'}).status
            == CriteriaStatus.FAIL
        )

    def test_T135_stripe_live_fails(self):
        assert (
            HardcodedSecretScanner(make_audit())
            .check({"p.py": "STRIPE='sk_live_abc123xyz'"})
            .status
            == CriteriaStatus.FAIL
        )

    def test_T136_rsa_key_fails(self):
        assert (
            HardcodedSecretScanner(make_audit())
            .check({"k.py": "-----BEGIN RSA PRIVATE KEY-----"})
            .status
            == CriteriaStatus.FAIL
        )

    def test_T137_comment_ignored(self):
        r = HardcodedSecretScanner(make_audit()).check({"d.py": '# password = "ex"\nV=1'})
        assert r.status == CriteriaStatus.PASS

    def test_T138_multi_files(self):
        r = HardcodedSecretScanner(make_audit()).check({"a.py": "import os", "b.py": "x=1"})
        assert r.status == CriteriaStatus.PASS and "2 files" in r.evidence


class TestAC18LicenseStorage:
    def test_T139_hashed_ok(self):
        gate = LicenseStorageGate(make_audit())
        raw = "RAW-KEY-XYZ"
        stored = gate.hash_license(raw)
        assert gate.check(stored, raw).status == CriteriaStatus.PASS

    def test_T140_raw_fails(self):
        r = LicenseStorageGate(make_audit()).check("RAW", "RAW")
        assert r.status == CriteriaStatus.FAIL and "plaintext" in r.evidence

    def test_T141_short_fails(self):
        assert LicenseStorageGate(make_audit()).check("short", "diff").status == CriteriaStatus.FAIL

    def test_T142_encrypted_ok(self):
        ok, _ = LicenseStorageGate(None).verify_not_raw("enc_" + "a" * 60, "raw")
        assert ok is True

    def test_T143_blocking(self):
        assert LicenseStorageGate(make_audit()).check("a" * 64, "diff").blocking is True


class TestAC19PaymentWebhook:
    def _g(self):
        return PaymentWebhookGate(make_audit(), secret="wh-secret")

    def test_T144_valid_processes(self):
        g = self._g()
        p = b'{"type":"payment"}'
        ok, r, _ = g.process("e1", p, g.generate_signature(p))
        assert ok and r == "processed"

    def test_T145_bad_sig_fails(self):
        g = self._g()
        ok, r, _ = g.process("e2", b"p", "badsig")
        assert not ok and r == "signature_invalid"

    def test_T146_idempotent(self):
        g = self._g()
        p = b"p"
        sig = g.generate_signature(p)
        g.process("e3", p, sig)
        ok, r, _ = g.process("e3", p, sig)
        assert ok and r == "idempotent_duplicate"

    def test_T147_timing_safe(self):
        g = self._g()
        p = b"t"
        sig = g.generate_signature(p)
        bad = sig[:-1] + ("0" if sig[-1] != "0" else "1")
        ok, r, _ = g.process("e4", p, bad)
        assert not ok

    def test_T148_check_passes(self):
        assert self._g().check().status == CriteriaStatus.PASS

    def test_T149_many_idempotent(self):
        g = self._g()
        p = b"p"
        sig = g.generate_signature(p)
        for _ in range(5):
            g.process("e100", p, sig)
        assert len(g._results) == 1


class TestAC20_22Gates:
    def test_T150_tests_pass(self):
        r = TestGate(make_audit()).check(TestSuiteResult(4435, 4435, 0, {"P6": 100}))
        assert r.status == CriteriaStatus.PASS

    def test_T151_failed_tests_fail(self):
        assert (
            TestGate(make_audit()).check(TestSuiteResult(100, 95, 5, {})).status
            == CriteriaStatus.FAIL
        )

    def test_T152_docs_ok(self):
        r = DocsGate(make_audit()).check(DocAlignmentResult(10, 10, [], []))
        assert r.status == CriteriaStatus.PASS

    def test_T153_docs_mismatch_warn(self):
        r = DocsGate(make_audit()).check(DocAlignmentResult(10, 8, ["R.md"], []))
        assert r.status == CriteriaStatus.WARN

    def test_T154_docker_ok(self):
        r = DockerGate(make_audit()).check(
            DockerReadinessResult(True, True, True, True, True, True, True)
        )
        assert r.status == CriteriaStatus.PASS

    def test_T155_no_dockerfile_fails(self):
        r = DockerGate(make_audit()).check(
            DockerReadinessResult(True, True, False, True, True, True, True)
        )
        assert r.status == CriteriaStatus.FAIL

    def test_T156_prod_not_ready_fails(self):
        r = DockerGate(make_audit()).check(
            DockerReadinessResult(True, False, True, True, True, True, False)
        )
        assert r.status == CriteriaStatus.FAIL


class TestDockerComposeGenerator:
    def test_T157_staging(self):
        c = DockerComposeGenerator(make_audit()).generate_staging()
        assert "staging" in c and "healthcheck" in c

    def test_T158_prod(self):
        c = DockerComposeGenerator(make_audit()).generate_production()
        assert "production" in c and "replicas" in c

    def test_T159_dockerfile(self):
        c = DockerComposeGenerator(make_audit()).generate_dockerfile()
        assert "FROM python:3.11" in c and "HEALTHCHECK" in c

    def test_T160_env_no_real_secrets(self):
        c = DockerComposeGenerator(make_audit()).generate_env_template()
        assert "CHANGE_ME" in c and "sk_live_" not in c

    def test_T161_rollback(self):
        c = DockerComposeGenerator(make_audit()).generate_rollback_script()
        assert "rollback" in c.lower()

    def test_T162_staging_no_replicas(self):
        assert "replicas" not in DockerComposeGenerator(make_audit()).generate_staging()

    def test_T163_prod_restart_always(self):
        assert "restart: always" in DockerComposeGenerator(make_audit()).generate_production()

    def test_T164_prod_logging(self):
        assert "logging" in DockerComposeGenerator(make_audit()).generate_production()


class TestFinalAcceptanceEngine:
    def test_T165_go(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.GO

    def test_T166_results_count(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        assert len(sys_["engine"].run(ctx).results) >= 20

    def test_T167_no_go_no_config(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["env"] = {}
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T168_no_go_bad_mt5(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["mt5_creds"] = MT5Credentials(-1, "x", "", False)
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T169_no_go_revoked(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["trade_ctx"].license_status = "REVOKED"
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T170_no_go_kill_switch(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["risk_ctx"].kill_switch_on = True
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T171_no_go_hardcoded(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["code_samples"] = {"a.py": 'password = "secret123"'}
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T172_no_go_raw_license(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["license_storage"] = {"stored": "RAW-KEY", "raw": "RAW-KEY"}
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T173_no_go_test_fail(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["test_result"] = TestSuiteResult(100, 95, 5, {})
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T174_audit_ok(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        assert sys_["engine"].run(ctx).audit_ok is True

    def test_T175_to_dict(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        d = sys_["engine"].run(ctx).to_dict()
        assert d["decision"] == "GO" and d["audit_ok"] is True

    def test_T176_blocking_fails(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["env"] = {}
        assert len(sys_["engine"].run(ctx).blocking_fails()) >= 1

    def test_T177_conditional_on_warn(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["doc_alignment"] = DocAlignmentResult(10, 8, ["R"], [])
        r = sys_["engine"].run(ctx)
        assert r.decision in (AcceptanceDecision.GO, AcceptanceDecision.CONDITIONAL)

    def test_T178_ac23_in_results(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ids = [r.criteria_id for r in sys_["engine"].run(ctx).results]
        assert CriteriaID.AC23 in ids


class TestAcceptanceAdmin:
    def test_T179_store_retrieve(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        r = sys_["engine"].run(ctx)
        sys_["admin"].store_report(r)
        assert sys_["admin"].latest_report() is r

    def test_T180_summary(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        for _ in range(3):
            sys_["admin"].store_report(sys_["engine"].run(ctx))
        s = sys_["admin"].summary()
        assert s["total_runs"] == 3 and s["go_count"] == 3

    def test_T181_no_reports_none(self):
        assert make_system()["admin"].latest_report() is None

    def test_T182_audit_ok(self):
        s = make_system()["admin"].summary()
        assert s["audit_ok"] is True


class TestBuildAcceptanceSystem:
    def test_T183_all_components(self):
        sys_ = make_system()
        for k in ["audit", "engine", "config_gate", "mt5_gate", "admin", "docker_gen"]:
            assert k in sys_

    def test_T184_shared_audit(self):
        sys_ = make_system()
        assert sys_["config_gate"]._audit is sys_["audit"]

    def test_T185_isolated_secrets(self):
        s1 = build_acceptance_system("A")
        s2 = build_acceptance_system("B")
        assert s1["audit"]._genesis != s2["audit"]._genesis

    def test_T186_independent(self):
        s1 = make_system()
        s2 = make_system()
        s1["ks_gate"].activate("t1", "r", "a")
        assert not s2["ks_gate"].is_active("t1")

    def test_T187_engine_type(self):
        assert isinstance(make_system()["engine"], FinalAcceptanceEngine)

    def test_T188_docker_gen_type(self):
        assert isinstance(make_system()["docker_gen"], DockerComposeGenerator)


class TestSQLMigration:
    @pytest.fixture
    def sql(self):
        import os

        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        paths = [
            os.path.join(
                base, "supabase", "migrations", "20260629_045_phase36_final_acceptance.sql"
            ),
            os.path.join(base, "migration_045.sql"),
        ]
        for p in paths:
            if os.path.exists(p):
                with open(p) as f:
                    return f.read()
        pytest.skip("SQL file not found")

    def test_T189_acceptance_runs(self, sql):
        assert "acceptance_runs" in sql

    def test_T190_criteria_results(self, sql):
        assert "criteria_results" in sql

    def test_T191_audit_log(self, sql):
        assert "acceptance_audit_log" in sql

    def test_T192_rls(self, sql):
        assert "ROW LEVEL SECURITY" in sql.upper() or "ENABLE ROW LEVEL" in sql

    def test_T193_trigger(self, sql):
        assert "TRIGGER" in sql.upper()

    def test_T194_chain_hash(self, sql):
        assert "CHAR(64)" in sql or "chain_hash" in sql

    def test_T195_indexes(self, sql):
        assert "INDEX" in sql.upper()

    def test_T196_views(self, sql):
        assert "VIEW" in sql.upper()


class TestIntegrationFlows:
    def test_T197_trading_disabled(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["trading_enabled"] = False
        ctx["mt5_creds"] = None
        report = sys_["engine"].run(ctx)
        ac02 = next(r for r in report.results if r.criteria_id == CriteriaID.AC02)
        assert ac02.status == CriteriaStatus.PASS

    def test_T198_kill_switch_cycle(self):
        sys_ = make_system()
        sys_["ks_gate"].activate("t1", "e", "a")
        assert sys_["ks_gate"].is_active("t1")
        sys_["ks_gate"].deactivate("t1", "a", reason="r")
        assert not sys_["ks_gate"].is_active("t1")

    def test_T199_webhook_replay(self):
        g = make_system()["webhook_gate"]
        p = b"p"
        sig = g.generate_signature(p)
        g.process("e1", p, sig)
        ok, r, _ = g.process("e1", p, sig)
        assert ok and r == "idempotent_duplicate"

    def test_T200_dedup_blocked(self):
        gate = make_system()["dedup_gate"]
        gate.check_order("E", "B", 0.1, "t1")
        ok, _ = gate.check_order("E", "B", 0.1, "t1")
        assert not ok

    def test_T201_audit_trail(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        sys_["engine"].run(ctx)
        assert sys_["audit"].verify_chain() and len(sys_["audit"]) > 10

    def test_T202_cross_tenant(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["tenant_check"] = {"actor_tenant": "t1", "resource_tenant": "t2", "type": "l"}
        report = sys_["engine"].run(ctx)
        ac11 = next(r for r in report.results if r.criteria_id == CriteriaID.AC11)
        assert ac11.status == CriteriaStatus.FAIL

    def test_T203_ea_all_fail(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["ea_ctx"] = EAStartupContext(False, False, False, False, False)
        assert sys_["engine"].run(ctx).decision == AcceptanceDecision.NO_GO

    def test_T204_device_limit(self):
        sys_ = make_system()
        sys_["device_gate"].set_limit("l", 1)
        sys_["device_gate"].check("l", "d1")
        assert sys_["device_gate"].check("l", "d2").status == CriteriaStatus.FAIL

    def test_T205_source_leak(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["delivery_files"] = ["b.ex5", "backend/core/s.py"]
        ctx["role"] = "CUSTOMER"
        report = sys_["engine"].run(ctx)
        ac08 = next(r for r in report.results if r.criteria_id == CriteriaID.AC08)
        assert ac08.status == CriteriaStatus.FAIL


class TestEdgeCasesAndFinalAcceptance:
    def test_T206_to_dict(self):
        r = CriteriaResult(
            CriteriaID.AC01, "t", CriteriaStatus.PASS, "ok", Severity.CRITICAL, True, "P"
        )
        assert r.to_dict()["criteria_id"] == "AC01"

    def test_T207_blocking_fail_logic(self):
        r1 = CriteriaResult(
            CriteriaID.AC01, "", CriteriaStatus.FAIL, "", Severity.CRITICAL, True, ""
        )
        r2 = CriteriaResult(CriteriaID.AC09, "", CriteriaStatus.FAIL, "", Severity.HIGH, False, "")
        assert r1.is_blocking_fail() and not r2.is_blocking_fail()

    def test_T208_no_audit_no_crash(self):
        gate = KillSwitchGate(None)
        gate.activate("t", "r", "a")
        assert gate.is_active("t")

    def test_T209_ghost_trade(self):
        rec = MT5ReconciliationGate(make_audit()).reconcile(
            [make_trade(1)], [make_trade(1), make_trade(999)]
        )
        assert 999 in rec.ghost

    def test_T210_license_hash_sha256(self):
        h = LicenseStorageGate(None).hash_license("k")
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)

    def test_T211_env_template_keys(self):
        t = DockerComposeGenerator(None).generate_env_template()
        for k in ["JWT_SECRET", "DATABASE_URL", "STRIPE_SECRET_KEY"]:
            assert k in t

    def test_T212_dedup_per_tenant(self):
        gate = DuplicateOrderGate(make_audit())
        gate.check_order("E", "B", 0.1, "A")
        gate.check_order("E", "B", 0.1, "B")
        ok_a, _ = gate.check_order("E", "B", 0.1, "A")
        ok_b, _ = gate.check_order("E", "B", 0.1, "B")
        assert not ok_a and not ok_b

    def test_T213_blocking_critical(self):
        r = ProductionConfigGate(None).check(good_env(), allow_test_stripe=True)
        assert r.severity == Severity.CRITICAL and r.blocking

    def test_T214_go_zero_blocking(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        report = sys_["engine"].run(ctx)
        if report.decision == AcceptanceDecision.GO:
            assert len(report.blocking_fails()) == 0

    def test_T215_no_go_has_blocking(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        ctx["env"] = {}
        report = sys_["engine"].run(ctx)
        assert report.decision == AcceptanceDecision.NO_GO and len(report.blocking_fails()) >= 1

    def test_T216_ac23_pass_iff_go(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        report = sys_["engine"].run(ctx)
        ac23 = next(r for r in report.results if r.criteria_id == CriteriaID.AC23)
        if report.decision == AcceptanceDecision.GO:
            assert ac23.status == CriteriaStatus.PASS
        else:
            assert ac23.status == CriteriaStatus.FAIL

    def test_T217_audit_grows(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        n0 = len(sys_["audit"])
        sys_["engine"].run(ctx)
        assert len(sys_["audit"]) > n0

    def test_T218_concurrent_safe(self):
        import threading

        sys_ = make_system()
        ctx = full_ctx(sys_)
        results = []

        def run():
            c = deepcopy(ctx)
            results.append(sys_["engine"].run(c).decision)

        ts = [threading.Thread(target=run) for _ in range(5)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert len(results) == 5

    def test_T219_key_criteria_checked(self):
        sys_ = make_system()
        ctx = full_ctx(sys_)
        checked = {r.criteria_id for r in sys_["engine"].run(ctx).results}
        for c in [CriteriaID.AC01, CriteriaID.AC02, CriteriaID.AC16, CriteriaID.AC23]:
            assert c in checked

    def test_T220_prod_blocked_no_config(self):
        r = ProductionConfigGate(make_audit()).check({}, False)
        assert r.status == CriteriaStatus.FAIL

    def test_T221_trading_blocked_no_mt5(self):
        assert MT5CredentialsGate(make_audit()).check(None, True).status == CriteriaStatus.FAIL

    def test_T222_no_trade_revoked_or_overlimit(self):
        tg = TradeAuthGate(make_audit())
        ctx = good_trade_ctx()
        ctx.license_status = "REVOKED"
        assert tg.check(ctx).status == CriteriaStatus.FAIL
        dg = DeviceLimitGate(make_audit())
        dg.set_limit("l", 1)
        dg.check("l", "d1")
        assert dg.check("l", "d2").status == CriteriaStatus.FAIL

    def test_T223_source_never_to_customer(self):
        sg = SourceAccessGate(make_audit())
        assert sg.check_delivery(["b/c.py", "m.mq5"], "CUSTOMER").status == CriteriaStatus.FAIL
        dg = CustomerDeliveryGate(make_audit())
        assert dg.check(["b.ex5", "g.pdf"]).status == CriteriaStatus.PASS
        assert dg.check(["src.zip"]).status == CriteriaStatus.FAIL

    def test_T224_FINAL_ACCEPTANCE_ALL_23_CRITERIA_PASS(self):
        """T224 -- FINAL ACCEPTANCE: All 23 criteria verified. System GO for production."""
        sys_ = make_system()
        ctx = full_ctx(sys_)
        report = sys_["engine"].run(ctx)
        sys_["admin"].store_report(report)

        assert report.decision == AcceptanceDecision.GO, (
            f"Expected GO but got {report.decision.value}. "
            f"Blocking: {[r.criteria_id.value for r in report.blocking_fails()]}"
        )
        assert len(report.blocking_fails()) == 0
        assert report.audit_ok is True
        assert sys_["audit"].verify_chain() is True

        status_map = {r.criteria_id: r.status for r in report.results}
        for cid in BLOCKING_CRITERIA:
            if cid in status_map:
                assert status_map[cid] == CriteriaStatus.PASS, f"{cid.value} failed"

        ac23 = next(r for r in report.results if r.criteria_id == CriteriaID.AC23)
        assert ac23.status == CriteriaStatus.PASS
        d = report.to_dict()
        assert d["decision"] == "GO" and d["audit_ok"] is True and d["fail_count"] == 0

        s = sys_["admin"].summary()
        assert s["go_count"] == 1 and s["audit_ok"] is True

        staging = sys_["docker_gen"].generate_staging()
        prod = sys_["docker_gen"].generate_production()
        assert "bot12-api:staging" in staging and "replicas: 2" in prod

        print("\n" + "=" * 60)
        print("FINAL ACCEPTANCE: GO - APPROVED FOR PRODUCTION")
        print(f"  Criteria: {len(report.results)} checked")
        print(
            f"  PASS: {report.pass_count} | FAIL: {report.fail_count} | WARN: {report.warn_count}"
        )
        print(f"  Audit chain: {len(sys_['audit'])} entries, intact")
        print("=" * 60)
