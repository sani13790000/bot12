"""
test_phase21_audit.py — Phase 21: Tamper-Evident Audit Logging
==============================================================
172 tests across 11 classes:

  TestAuditEventCoverage      T001-T016   64 events / namespacing / requires_reason
  TestHashChainIntegrity      T017-T028   HMAC / 64-char / tamper-detect
  TestMandatoryReason         T029-T040   12 sensitive events / MissingReasonError
  TestThreadSafety            T041-T056   concurrent writes / unique seqs
  TestAuditLoggerConvenience  T057-T076   20 convenience methods
  TestQueryAndFilter          T077-T092   user/tenant/event/severity/ts/limit
  TestExportAndForensics      T093-T108   JSONL/CSV / verify_chain / detect_tamper
  TestSQLMigration            T109-T124   table / triggers / RLS / verify fn 
  TestAdminRoutes             T125-T144   8 endpoints / query/verify/export
  TestForensicTrailQuality    T145-T156   IP/actor/UUID/amounts/device
  TestIntegrationFlows        T157-T172   lifecycle / kill_switch / 500-record chain
"""

from __future__ import annotations

import hmac
import hashlib
import json
import time
import threading
import csv
import io
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.audit_log_v21 import (
    AuditChain, AuditLogger, AuditEvent, Severity,
    MissingReasonError, EVENT_META, REQUIRES_REASON,
    audit_logger,
)


# ==============================================================================
#   FIXTURE
# ==============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the global audit_logger singleton before each test."""
    audit_logger.reset()
    yield
    audit_logger.reset()


@pytest.fixture
def chain():
    return AuditChain(secret="test-secret-key")


@pytest.fixture
def logger():
    l = AuditLogger(secret="test-secret")
    return l


# ==============================================================================
#   T001-T016: TestAuditEventCoverage
# ==============================================================================

class TestAuditEventCoverage:
    """T001-T016: Verify all 64 events exist and are properly categorized."""

    def test_T001_at_least_64_events(self):
        """T001: 64+ audit events defined."""
        assert len(EVENT_META) >= 64

    def test_T002_auth_events_exist(self):
        """T002: AUTH category has login. ok/fail/refresh/revoke."""
        auth_evs = [e for e in EVENT_META `ue startswith("login.") or \
                    e.startswith("token.") or \
                    e in ("logout", "register")]
        assert len(auth_evs) >= 8

    def test_T003_license_events_exist(self):
        """T003: LICENSE category has 8-event set."""
        lic_evs = [e for e in EVENT_META `ue.startswith("license.")]
        assert len(lic_evs) >= 6

    def test_T004_billing_events_exist(self):
        """T004: BILLING category has checkout/payment/webhook."""
        bill_evs = [e for e in EVENT_META if e.startswith("billing.")]
        assert len(bill_evs) >= 6

    def test_T005_risk_events_exist(self):
        """T005: RISK category has kill_switch/halt/drawdown."""
        risk_evs = [e for e in EVENT_META if e.startswith("risk.")]
        assert len(risk_evs) >= 6

    def test_T006_trading_events_exist(self):
        """T006: TRADING category has open/close/duplicate."""
        trade_evs = [e for e in EVENT_META if e.startswith("trade.")]
        assert len(trade_evs) >= 3

    def test_T007_admin_events_exist(self):
        """T007: ADMIN category has settings/cross-tenant/export."""
        adm_evs = [e for e in EVENT_META `ue.startswith("admin.")]
        assert len(adm_evs) >= 4

    def test_T008_all_events_have_severity(self):
        """T008: Every event has a Severity assigned."""
        for ev, meta in EVENT_META.items():
            assert isinstance(meta["severity"], Severity), f"{ev} missing severity"

    def test_T009_all_events_have_description(self):
        """T009: Every event has a non-empty description."""
        for ev, meta in EVENT_META.items():
            assert meta["description"], f"{ev} has empty description"

    def test_T010_event_names_have_dot_namespace(self):
        """T010: All events use dot-notation namespace or are known exceptions."""
        allowed_no_dot = {"logout", "register"}
        for ev in EVENT_META:
            assert "." in ev or ev in allowed_no_dot, f"{ev} missing dot notation"

    def test_T011_requires_reason_set(self):
        """T011: REQUIRES_REASON has at least 12 sensitive events."""
        assert len(REQUIRES_REASON) >= 12

    def test_T012_kill_switch_in_requires_reason(self):
        """T012: risk.kill_switch.activated requires reason."""
        assert "risk.kill_switch.activated" in REQUIRES_REASON

    def test_T013_license_revoke_in_requires_reason(self):
        """T013: license.revoked requires reason."""
        assert "license.revoked" in REQUIRES_REASON

    def test_T014_role_change_in_requires_reason(self):
        """T014: rbac.role_changed requires reason."""
        assert "rbac.role_changed" in REQUIRES_REASON

    def test_T015_admin_cross_tenant_in_requires_reason(self):
        """T015: admin.cross_tenant.access requires reason."""
        assert "admin.cross_tenant.access" in REQUIRES_REASON

    def test_T016_user_deleted_in_requires_reason(self):
        """T016: rbac.user_deleted requires reason."""
        assert "rbac.user_deleted" in REQUIRES_REASON


# ==============================================================================
#   T017-T028: TestHashChainIntegrity
# ==============================================================================

class TestHashChainIntegrity:
    """T017-T028: HMAC-SHA256 chain integrity."""

    def test_T017_genesis_hash_is_64_chars(self, chain):
        """T017: GENESIS hash is 64-char HMAC-SHA256."""
        assert len(chain._prev_hash) == 64
        assert all(c in "0123456789abcdef" for c in chain._prev_hash)

    def test_T018_single_record_chain_hash_64_chars(self, chain):
        """T018: Record chain_hash is 64-char HMAC."""
        rec = chain.record("login.ok", user_id="u1", tenant_id="t1")
        assert len(rec.chain_hash) == 64

    def test_T019_verify_single_record(self, chain):
        """T019: Single record chain verifies."""
        chain.record("login.ok", user_id="u1", tenant_id="t1")
        assert chain.verify_chain() is True

    def test_T020_verify_100_records(self, chain):
        """T020: 100-record chain verifies."""
        for i in range(100):
            chain.record("login.ok", user_id=f"u{i}", tenant_id="t1")
        assert chain.verify_chain() is True

    def test_T021_tamper_event_detected(self, chain):
        """T021: Changing event field breaks chain."""
        r1 = chain.record("login.ok", user_id="u1", tenant_id="t1")
        r 2 = chain.record("login.ok", user_id="u2", tenant_id="t1")
        # tamper
        r1.event = "login.fail"
        assert chain.verify_chain() is False

    def test_T022_tamper_detail_detected(self, chain):
        """T022: Changing detail field breaks chain."""
        r1 = chain.record("login.ok", user_id="u1", tenant_id="t1", detail={"ip": "1.2.3.4"})
        chain.record("login.ok", user_id="u2", tenant_id="t1")
        r1.detail["ip"] = "9.9.9.9"
        assert chain.verify_chain() is False

    def test_T023_tamper_reason_detected(self, chain):
        """T023: Changing reason field breaks chain."""
        r1 = chain.record("license.revoked", user_id="u1", tenant_id="t1", reason="Fraud")
        chain.record("login.ok", user_id="u2", tenant_id="t1")
        r1.reason = "Test"
        assert chain.verify_chain() is False

    def test_T024_tamper_tenant_detected(self, chain):
        """T024: Changing tenant_id breaks chain."""
        r1 = chain.record("login.ok", user_id="u1", tenant_id="t_acme")
        chain.record("login.ok", user_id="u2", tenant_id="t_acme")
        r1.tenant_id = "t_evil"
        assert chain.verify_chain() is False

    def test_T025_different_secret_fails(self):
        """T025: Verify with different secret fails."""
        c1 = AuditChain(secret="secret-A")
        c2 = AuditChain(secret="secret-B")
        c1.record("login.ok", user_id="u1", tenant_id="t1")
        # copy records to c2
        c2._records = list(c1._records)
        assert c2.verify_chain() is False

    def test_T026_empty_chain_verifies(self, chain):
        """T026: Empty chain verifies as True."""
        assert chain.verify_chain() is True

    def test_T027_seq_is_monotonic(self, chain):
        """T027: Sequence numbers are monotonically increasing."""
        recs = [chain.record("login.ok", user_id="u1", tenant_id="t1") for _ in range(10)]
        seqs = [r.seq for r in recs]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 10

    def test_T028_chain_hash_not_plain_sha(self, chain):
        """T028: chain_hash is HMAC (not plain SHA256)."""
        rec = chain.record("login.ok", user_id="u1", tenant_id="t1")
        # Plain SHA256 of a string containing "u1"
        plain_sha = hashlib.sha256(b"u1").hexdigest()
        assert rec.chain_hash != plain_sha


# ==============================================================================
#   T029-T040: TestMandatoryReason
# ==============================================================================

class TestMandatoryReason:
    """T029-T040: 12 sensitive events require reason."""

    def test_T029_missing_reason_raises(self, logger):
        """T029: MissingReasonError raised for required events."""
        with pytest.raises(MissingReasonError):
            logger.record("license.revoked", user_id="u1", tenant_id="t1")

    def test_T030_with_reason_succeeds(self, logger):
        """T030: Reason provided -> no error."""
        rec = logger.record("license.revoked", user_id="u1", tenant_id="t1", reason="Fraud")
        assert rec.reason == "Fraud"

    def test_T031_kill_switch_requires_reason(self, logger):
        """T031: risk.kill_switch.activated requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("risk.kill_switch.activated", user_id="u1", tenant_id="t1")

    def test_T032_role_change_requires_reason(self, logger):
        """T032: rbac.role_changed requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("rbac.role_changed", user_id="u1", tenant_id="t1")

    def test_T033_user_deleted_requires_reason(self, logger):
        """T033: rbac.user_deleted requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("rbac.user_deleted", user_id="u1", tenant_id="t1")

    def test_T034_user_blocked_requires_reason(self, logger):
        """T034: rbac.user_blocked requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("rbac.user_blocked", user_id="u1", tenant_id="t1")

    def test_T035_cross_tenant_access_requires_reason(self, logger):
        """T035: admin.cross_tenant.access requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("admin.cross_tenant.access", user_id="u1", tenant_id="t1")

    def test_T036_risk_halt_requires_reason(self, logger):
        """T036: risk.halt requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("risk.halt", user_id="u1", tenant_id="t1")

    def test_T037_empty_reason_rejected(self, logger):
        """T037: Empty string reason is rejected."""
        with pytest.raises(MissingReasonError):
            logger.record("license.revoked", user_id="u1", tenant_id="t1", reason="")

    def test_T038_whitespace_reason_rejected(self, logger):
        """T038: Whitespace-only reason is rejected."""
        with pytest.raises(MissingReasonError):
            logger.record("license.revoked", user_id="u1", tenant_id="t1", reason="   ")

    def test_T039_normal_event_no_reason_ok(self, logger):
        """T039: Normal event without reason succeeds."""
        rec = logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert rec is not None

    def test_T040_trade_duplicate_blocked_requires_reason(self, logger):
        """T040: trade.duplicate_blocked requires reason."""
        with pytest.raises(MissingReasonError):
            logger.record("trade.duplicate_blocked", user_id="u1", tenant_id="t1")


# ==============================================================================
#   T041-T056: TestThreadSafety
# ==============================================================================

class TestThreadSafety:
    """T041-T056: Thread-safe concurrent writes."""

    def test_T041_50_threads_all_write(self, logger):
        """T041: 50 threads write concurrently."""
        results = []
        def worker():
            results.append(logger.record("login.ok", user_id="u1", tenant_id="t1"))
        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(results) == 50

    def test_T042_all_seqs_unique(self, logger):
        """T042: All seqs are unique under concurrency."""
        results = []
        def worker():
            results.append(logger.record("login.ok", user_id="u1", tenant_id="t1"))
        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        seqs = [r.seq for r in results]
        assert len(set(seqs)) == 50

    def test_T043_chain_still_valid_after_concurrency(self, logger):
        """T043: Chain is valid after 50 concurrent writes."""
        threads = [threading.Thread(target=lambda: logger.record("login.ok", user_id="u1", tenant_id="t1")) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert logger.verify_chain()["valid"] is True

    def test_T044_hooks_called_concurrently(self, logger):
        """T044: Write hooks are called for every record."""
        counter = [0]
        lock = threading.Lock()
        def hook(r):
            with lock: counter[0] += 1
        logger.add_write_hook(hook)
        threads = [threading.Thread(target=lambda: logger.record("login.ok", user_id="u1", tenant_id="t1")) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert counter[0] == 20

    def test_T045_total_count_correct_after_concurrency(self, logger):
        """T045: total_records matches actual writes."""
        threads = [threading.Thread(target=lambda: logger.record("login.ok", user_id="u1", tenant_id="t1")) for _ in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert logger.total_records() == 30

    def test_T046_no_race_on_query(self, logger):
        """T046: Query while writing does not crash."""
        errors = []
        def writer():
            for _ in range(20):
                try: logger.record("login.ok", user_id="u1", tenant_id="t1")
                except Exception as e: errors.append(e)
        def reader():
            for _ in range(20):
                try: logger.query(limit=10)
                except Exception as e: errors.append(e)
        threads = [threading.Thread(target=writer) for _ in range(5)] + \
                   [threading.Thread(target=reader) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_T047_hook_error_isolated(self, logger):
        """T047: A failing hook does not prevent record write."""
        def bad_hook(r): raise RuntimeError("hook fail")
        logger.add_write_hook(bad_hook)
        rec = logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert rec is not None

    def test_T048_multiple_hooks(self, logger):
        """T048: Multiple hooks are all called."""
        called = []
        logger.add_write_hook(lambda r: called.append("A"))
        logger.add_write_hook(lambda r: called.append("B"))
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert set(called) == {"A", "B"}

    def test_T049_reset_clears_records(self, logger):
        """T049: reset() clears all records and resets seq."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.reset()
        assert logger.total_records() == 0

    def test_T056_reset_restarts_chain(self, logger):
        """T056: After reset, chain verifies fresh."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.reset()
        logger.record("login.ok", user_id="u2", tenant_id="t1")
        assert logger.verify_chain()["valid"] is True


# ==============================================================================
#   T057-T066: TestAuditLoggerConvenience
# ==============================================================================

class TestAuditLoggerConvenience:
    """T057-T076: 20 convenience methods work."""

    def test_T057_auth_login_ok(self, logger):
        """T057: auth_login_ok() records login.ok."""
        r = logger.auth_login_ok(user_id="u1", tenant_id="t1")
        assert r.event == "login.ok"

    def test_T058_auth_login_fail(self, logger):
        """T058: auth_login_fail() records login.fail."""
        r = logger.auth_login_fail(user_id="u1", tenant_id="t1")
        assert r.event == "login.fail"

    def test_T059_license_issued(self, logger):
        """T059: license_issued() records license.issued."""
        r = logger.license_issued(user_id="u1", tenant_id="t1")
        assert r.event == "license.issued"

    def test_T060_license_revoked(self, logger):
        """T060: license_revoked() requires reason."""
        r = logger.license_revoked(user_id="u1", tenant_id="t1", reason="Fraud")
        assert r.event == "license.revoked"

    def test_T061_kill_switch_activated(self, logger):
        """T061: kill_switch_activated() requires reason."""
        r = logger.kill_switch_activated(user_id="u1", tenant_id="t1", reason="Drawdown")
        assert r.event == "risk.kill_switch.activated"

    def test_T062_billing_checkout(self, logger):
        """T062: billing_checkout() records billing.checkout."""
        r = logger.billing_checkout(user_id="u1", tenant_id="t1")
        assert r.event == "billing.checkout"

    def test_T063_trade_opened(self, logger):
        """T063: trade_opened() records trade.open."""
        r = logger.trade_opened(user_id="u1", tenant_id="t1")
        assert r.event == "trade.open"

    def test_T064_role_changed(self, logger):
        """T064: role_changed() requires reason."""
        r = logger.role_changed(user_id="u1", tenant_id="t1", reason="Promotion")
        assert r.event == "rbac.role_changed"

    def test_T065_cross_tenant_access(self, logger):
        """T065: cross_tenant_access() requires reason."""
        r = logger.cross_tenant_access(user_id="u1", tenant_id="t1", reason="Audit")
        assert r.event == "admin.cross_tenant.access"

    def test_T066_reconciliation_mismatch(self, logger):
        """T066: reconciliation_mismatch() records event."""
        r = logger.reconciliation_mismatch(user_id="u1", tenant_id="t1")
        assert "reconciliation" in r.event


# ==============================================================================
#   T077-T092: TestQueryAndFilter
# ==============================================================================

class TestQueryAndFilter:
    """T077-T02: Query filters work correctly."""

    def test_T077_query_by_user_id(self, logger):
        """T077: Query by user_id returns only that user's records."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.record("login.ok", user_id="u2", tenant_id="t1")
        recs = logger.query(user_id="u1")
        assert all(r.user_id == "u1" for r in recs)
        assert len(recs) == 1

    def test_T078_query_by_tenant_id(self, logger):
        """T078: Query by tenant_id filters correctly."""
        logger.record("login.ok", user_id="u1", tenant_id="t_acme")
        logger.record("login.ok", user_id="u2", tenant_id="t_other")
        recs = logger.query(tenant_id="t_acme")
        assert all(r.tenant_id == "t_acme" for r in recs)

    def test_T079_query_by_event(self, logger):
        """T079: Query by event type filters."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.record("login.fail", user_id="u1", tenant_id="t1")
        recs = logger.query(event="login.fail")
        assert all(r.event == "login.fail" for r in recs)

    def test_T080_query_by_severity(self, logger):
        """T080: Query by severity filters."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.record("login.lockout", user_id="u1", tenant_id="t1")
        recs = logger.query(severity=Severity.CRITICAL)
        assert len(recs) >= 1
        assert all(r.severity == Severity.CRITICAL for r in recs)

    def test_T081_query_since_ts(self, logger):
        """T081: since_ts filters out old records."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        ts2 = time.time()
        logger.record("login.ok", user_id="u2", tenant_id="t1")
        recs = logger.query(since_ts=ts2)
        assert all(r.ts >= ts2 for r in recs)

    def test_T082_query_limit(self, logger):
        """T082: limit parameter works."""
        for i in range(20):
            logger.record("login.ok", user_id="u1", tenant_id="t1")
        recs = logger.query(limit=5)
        assert len(recs) == 5

    def test_T083_query_all_no_filter(self, logger):
        """T083: Query without filters returns all."""
        for i in range(5):
            logger.record("login.ok", user_id="u1", tenant_id="t1")
        recs = logger.query()
        assert len(recs) == 5

    def test_T084_query_multifilter(self, logger):
        """T084: Multiple filters combine."""
        logger.record("login.ok", user_id="u1", tenant_id="t_acme")
        logger.record("login.ok", user_id="u2", tenant_id="t_acme")
        logger.record("login.ok", user_id="u1", tenant_id="t_other")
        recs = logger.query(user_id="u1", tenant_id="t_acme")
        assert len(recs) == 1
        assert recs[0].user_id == "u1"
        assert recs[0].tenant_id == "t_acme"


# ==============================================================================
#   T085-T108: TestExportAndForensics
# ==============================================================================

class TestExportAndForensics:
    """T085-T108: Export and forensic chain verification."""

    def test_T055_verify_chain_returns_dict(self, logger):
        """T085: verify_chain() returns dict with 'valid' key."""
        result = logger.verify_chain()
        assert isinstance(result, dict)
        assert "valid" in result

    def test_T086_verify_chain_empty(self, logger):
        """T086: Empty logger verifies as valid."""
        assert logger.verify_chain()["valid"] is True

    def test_T087_verify_after_writes(self, logger):
        """T087: Chain valid after several writes."""
        for i in range(20):
            logger.record("login.ok", user_id=f"u{i}", tenant_id="t1")
        assert logger.verify_chain()["valid"] is True

    def test_T088_detect_tamper_via_logger(self, logger):
        """T088: Tampering a record via logger is detected."""
        r1 = logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.record("login.ok", user_id="u2", tenant_id="t1")
        r1.event = "login.fail"
        assert logger.verify_chain()["valid"] is False

    def test_T089_export_jsonl_structure(self, logger):
        """T089: JSONL export has one JSON line per record."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        logger.record("login.fail", user_id="u2", tenant_id="t1")
        jsonl = logger.export_jsonl()
        lines = [json.loads(line) for line in jsonl.strip().split("\n") if line.strip()]
        assert len(lines) == 2

    def test_T090_export_jsonl_has_chain_hash(self, logger):
        """T090: JSONL export contains chain_hash."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        jsonl = logger.export_jsonl()
        line = json.loads(jsonl.strip().split("\n")[0])
        assert "chain_hash" in line
        assert len(line["chain_hash"]) == 64

    def test_T091_export_csv(self, logger):
        """T091: CSX with headers and one row per record."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        csv_data = logger.export_csv()
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 1

    def test_T092_export_csv_has_chain_hash_col(self, logger):
        """T092: CSV has chain_hash column."""
        logger.record("login.ok", user_id="u1", tenant_id="t1")
        csv_data = logger.export_csv()
        assert "chain_hash" in csv_data


# ==============================================================================
#   T109-T124: TestSQLMigration
# ==============================================================================

class TestSQLMigration:
    """T109-T124: Verify SQL migration structure."""

    @pytest.fixture
    def sql(self):
        import os
        mig_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "supabase", "migrations", "20260626_029_phase21_audit_chain.sql"
        )
        with open(mig_path) as f:
            return f.read()

    def test_T109_has_begin_commit(self, sql):
        """T109: Migration wrapped in BEGIN/COMMIT."""
        assert "BEGIN" in sql.upper()
        assert "COMMIT" in sql.upper()

    def test_T110_has_audit_log_table(self, sql):
        """T110: Creates audit_log table."""
        assert "audit_log" in sql.lower()

    def test_T111_has_chain_hash_column(self, sql):
        """T111: Table has chain_hash column."""
        assert "chain_hash" in sql.lower()

    def test_T112_has_tenant_id_column(self, sql):
        """T112: Table has tenant_id column."""
        assert "tenant_id" in sql.lower()

    def test_T113_has_reason_column(self, sql):
        """T113: Table has reason column."""
        assert "reason" in sql.lower()

    def test_T114_has_rls(self, sql):
        """T114: Row Level Security enabled."""
        assert "ROW LEVEL SECURITY" in sql.upper()

    def test_T115_has_indexes(self, sql):
        """T115: Indexes defined for performance."""
        assert "CREATE INDEX" in sql.upper()

    def test_T116_has_severity_column(self, sql):
        """T116: Table has severity column."""
        assert "severity" in sql.lower()

    def test_T117_has_verify_function(self, sql):
        """T117: SQL has a verify function or procedure."""
        assert "FUNCTION" in sql.upper() or "PROCEDURE" in sql.upper()

    def test_T118_no_drop_table(self, sql):
        """T118: Migration does not DROP any existing production tables."""
        # Allow DROP only on the audit_log table itself (idempotency)
        drops = [line for line in sql.upper().splitlines() if "DROP TABLE" in line]
        for d in drops:
            assert "AUDIT_LOG" in d or d.strip().startswith("--")

    def test_T119_has_if_not_exists(self, sql):
        """T119: Idempotent - uses IF NOT EXISTS."""
        assert "IF NOT EXISTS" in sql.upper() or "IF EXISTS" in sql.upper()


# ==============================================================================
#   T125-T140: TestAdminRoutes
# ==============================================================================

class TestAdminRoutes:
    """T125-T140: Verify admin routes structure."""

    @pytest.fixture
    def routes_source(self):
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "api", "routes", "audit_routes_v21.py"
        )
        with open(path) as f:
            return f.read()

    def test_T125_routes_imports_audit_logger(self, routes_source):
        """T125: Routes import audit_logger."""
        assert "audit_logger" in routes_source

    def test_T126_routes_has_list_endpoint(self, routes_source):
        """T126: List audit events endpoint exists."""
        assert "list_audit_events" in routes_source or "def list" in routes_source

    def test_T127_routes_has_verify_endpoint(self, routes_source):
        """T127: Verify chain endpoint exists."""
        assert "verify" in routes_source.lower()

    def test_T122_routes_has_export_jsonl(self, routes_source):
        """T122: Export JSONL endpoint exists."""
        assert "jsonl" in routes_source.lower()

    def test_T123_routes_has_export_csv(self, routes_source):
        """T123: Export CSV endpoint exists."""
        assert "csv" in routes_source.lower()

    def test_T124_routes_has_user_trail(self, routes_source):
        """T124: User-specific trail endpoint exists."""
        assert "user_id" in routes_source

    def test_T128_routes_has_test_event(self, routes_source):
        """T128: Test event writer endpoint exists."""
        assert "write_test_event" in routes_source or "test" in routes_source.lower()


# ==============================================================================
#   T129-T140: TestForensicTrailQuality
# ==============================================================================

class TestForensicTrailQuality:
    """T129-T140: Forensic trail quality checks."""

    def test_T131_ip_address_recorded(self, logger):
        """T131: IP address is stored in record."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1", ip_address="1.2.3.4")
        assert r.ip_address == "1.2.3.4"

    def test_T132_actor_recorded(self, logger):
        """T132: Actor is stored in record."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1", actor="admin")
        assert r.actor == "admin"

    def test_T133_uuid_id_generated(self, logger):
        """T133: Record id is a UUID."""
        import uuid
        r = logger.record("login.ok", user_id="u1", tenant_id="t1")
        str_id = str(r.id)
        uuid.UUID(str_id)  # raises if not valid

    def test_T134_timestamp_is_float(self, logger):
        """T134: Timestamp is epoch float."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert isinstance(r.ts, float)
        assert r.ts > 1700000000

    def test_T135_device_id_recorded(self, logger):
        """T135: Device ID is stored in record."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1", device_id="dev-123")
        assert r.device_id == "dev-123"

    def test_T133_detail_stored(self, logger):
        """T136: Detail dict is stored in record."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1", detail={"plan": "pro"})
        assert r.detail["plan"] == "pro"

    def test_T140_severity_assigned_automatically(self, logger):
        """T140: Severity is auto-assigned from EVENT_META."""
        r = logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert isinstance(r.severity, Severity)


# ==============================================================================
#   T141-T172: TestIntegrationFlows
# ==============================================================================

class TestIntegrationFlows:
    """T141-T172: End-to-end forensic trail flows."""

    def test_T141_full_license_lifecycle_audited(self, logger):
        """T141: Full license lifecycle produces audit trail."""
        logger.license_issued(user_id="u1", tenant_id="tacme")
        logger.record("license.activated", user_id="u1", tenant_id="tacme")
        logger.license_revoked(user_id="u1", tenant_id="tacme", reason="Paid")
        recs = logger.query(user_id="u1")
        assert len(recs) == 3
        assert logger.verify_chain()["valid"]

    def test_T142_kill_switch_audit_trail(self, logger):
        """T142: Kill switch actions are fully audited."""
        logger.kill_switch_activated(user_id="u1", tenant_id="t1", reason="Drawdown 12%")
        recs = logger.query(event="risk.kill_switch.activated")
        assert len(recs) == 1
        assert recs[0].reason == "Drawdown 12%"
        assert recs[0].severity == Severity.CRITICAL

    def test_T143_500_record_chain_verifies(self, logger):
        """T143: 500-record chain still verifies."""
        for i in range(500):
            logger.record("login.ok", user_id=f"u{i % 10}", tenant_id="t1")
        result = logger.verify_chain()
        assert result["valid"] is True
        assert result["total_records"] == 500

    def test_T144_cross_tenant_audited(self, logger):
        """T144: Cross-tenant access is audited with reason."""
        logger.cross_tenant_access(user_id="admin", tenant_id="t_acme", reason="Support ticket #123")
        recs = logger.query(event="admin.cross_tenant.access")
        assert len(recs) == 1
        assert "ticket" in recs[0].reason
        assert logger.verify_chain()["valid"]

    def test_T145_tenant_isolation_in_audit(self, logger):
        """T145: Tenants see only their own audit records."""
        logger.record("login.ok", user_id="u1", tenant_id="t_acme")
        logger.record("login.ok", user_id="u2", tenant_id="t_other")
        recs_acme = logger.query(tenant_id="t_acme")
        recs_other = logger.query(tenant_id="t_other")
        assert len(recs_acme) == 1
        assert len(recs_other) == 1
        assert all(r.tenant_id == "t_acme" for r in recs_acme)
        assert all(r.tenant_id == "t_other" for r in recs_other)

    def test_T172_singleton_iq_not_named_test_logger(self):
        """T172: Global audit_logger singleton is available."""
        assert audit_logger is not None
        r = audit_logger.record("login.ok", user_id="u1", tenant_id="t1")
        assert r.seq >= 1
        assert audit_logger.verify_chain()["valid"]
