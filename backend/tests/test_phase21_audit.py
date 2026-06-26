"""Phase 21   Tamper-Evident Audit Logging   172 tests"""
from __future__ import annotations
import csv, io, json, threading, time, uuid
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.core.audit_log_v21 import (
    AuditChain, AuditEvent, AuditLogger, AuditRecord,
    EVENT_META, MissingReasonError, REQUIRES_REASON, Severity,
)

@pytest.fixture
def chain(): return AuditChain(secret="test-secret-phase21")
@pytest.fixture
def logger(chain): return AuditLogger(chain=chain)

class TestAuditEventCoverage:
    def test_T001_at_least_64_events(self): assert len(AuditEvent) >= 64
    def test_T002_auth_events(self): assert len([e for e in AuditEvent if e.value.startswith("auth.")]) >= 8
    def test_T003_rbac_events(self): assert len([e for e in AuditEvent if e.value.startswith("rbac.")]) >= 6
    def test_T004_license_events(self): assert len([e for e in AuditEvent if e.value.startswith("license.")]) >= 8
    def test_T005_billing_events(self): assert len([e for e in AuditEvent if e.value.startswith("billing.")]) >= 8
    def test_T006_trading_events(self): assert len([e for e in AuditEvent if e.value.startswith(("trade.","signal.","reconciliation."))]) >= 8
    def test_T007_risk_events(self): assert len([e for e in AuditEvent if e.value.startswith("risk.")]) >= 8
    def test_T008_admin_events(self): assert len([e for e in AuditEvent if e.value.startswith("admin.")]) >= 8
    def test_T009_tenant_events(self): assert len([e for e in AuditEvent if e.value.startswith("tenant.")]) >= 6
    def test_T010_all_in_meta(self):
        for e in AuditEvent: assert e.value in EVENT_META, f"{e.value} missing"
    def test_T011_all_have_severity(self):
        for e in AuditEvent: assert "severity" in EVENT_META[e.value]
    def test_T012_all_have_category(self):
        for e in AuditEvent: assert "category" in EVENT_META[e.value]
    def test_T013_requires_reason_count(self): assert len(REQUIRES_REASON) >= 13
    def test_T014_kill_switch_requires_reason(self): assert AuditEvent.RISK_KILL_SWITCH_ON in REQUIRES_REASON
    def test_T015_license_revoke_requires_reason(self): assert AuditEvent.LICENSE_REVOKED in REQUIRES_REASON
    def test_T016_critical_events_severity(self):
        meta = EVENT_META[AuditEvent.RISK_KILL_SWITCH_ON.value]
        assert meta["severity"] in (Severity.CRITICAL, Severity.CRITICAL.value)

class TestHashChainIntegrity:
    def test_T017_hash_64_chars(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        assert len(r.chain_hash) == 64
    def test_T018_hash_is_hex(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        int(r.chain_hash, 16)
    def test_T019_genesis_64_chars(self, chain): assert len(chain._genesis) == 64
    def test_T020_sequential_hashes_differ(self, chain):
        r1 = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1")
        assert r1.chain_hash != r2.chain_hash
    def test_T021_verify_empty(self, chain): assert chain.verify_chain() is True
    def test_T022_verify_single(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        assert chain.verify_chain() is True
    def test_T023_verify_multi(self, chain):
        for i in range(10): chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
        assert chain.verify_chain() is True
    def test_T024_tamper_event_breaks_chain(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1")
        object.__setattr__(r2, "event", "auth.hacked")
        assert chain.verify_chain() is False
    def test_T025_tamper_detail_breaks_chain(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", detail={"k": "v"})
        object.__setattr__(r, "detail", {"k": "tampered"})
        assert chain.verify_chain() is False
    def test_T026_wrong_secret_fails_verify(self):
        c1 = AuditChain(secret="secret-A"); c2 = AuditChain(secret="secret-B")
        r = c1.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        object.__setattr__(c2, "_records", c1._records)
        object.__setattr__(c2, "_prev", c1._prev)
        assert c2.verify_chain() is False
    def test_T027_prev_hash_links(self, chain):
        r1 = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1")
        assert r2.prev_hash == r1.chain_hash
    def test_T028_genesis_is_prev_of_first(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        assert r.prev_hash == chain._genesis

class TestMandatoryReason:
    def test_T029_license_revoke_empty_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="")
    def test_T030_license_revoke_whitespace(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="   ")
    def test_T031_license_revoke_with_reason(self, chain):
        r = chain.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="Fraud")
        assert r.reason == "Fraud"
    def test_T032_kill_switch_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RISK_KILL_SWITCH_ON, user_id="u1")
    def test_T033_kill_switch_with_reason(self, chain):
        r = chain.record(AuditEvent.RISK_KILL_SWITCH_ON, user_id="u1", reason="D20%")
        assert r.severity == Severity.CRITICAL.value
    def test_T034_halt_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RISK_HALT, user_id="u1")
    def test_T035_role_changed_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RBAC_ROLE_CHANGED, user_id="u1")
    def test_T036_user_blocked_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RBAC_USER_BLOCKED, user_id="u1")
    def test_T037_refund_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.BILLING_REFUND, user_id="u1")
    def test_T038_impersonate_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.ADMIN_IMPERSONATE, user_id="u1")
    def test_T039_tenant_suspend_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.TENANT_SUSPEND, user_id="u1")
    def test_T040_tenant_purge_requires_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.TENANT_PURGE, user_id="u1")

class TestThreadSafety:
    def test_T041_concurrent_writes_unique_seq(self):
        c = AuditChain(secret="s"); results = []
        def w(): results.append(c.record(AuditEvent.AUTH_LOGIN_OK, user_id="u").seq)
        threads = [threading.Thread(target=w) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(results)) == 50
    def test_T042_concurrent_verify_safe(self):
        c = AuditChain(secret="s")
        for i in range(20): c.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
        results = []
        def v(): results.append(c.verify_chain())
        threads = [threading.Thread(target=v) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(results)
    def test_T043_hook_error_isolated(self):
        c = AuditChain(secret="s"); l = AuditLogger(chain=c)
        l.add_write_hook(lambda r: 1/0)
        r = l.auth_login_ok("u1")
        assert r.user_id == "u1"
    def test_T044_concurrent_hooks(self):
        c = AuditChain(secret="s"); l = AuditLogger(chain=c); calls = []
        l.add_write_hook(lambda r: calls.append(r.seq))
        threads = [threading.Thread(target=lambda: l.auth_login_ok("u")) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(calls) == 20
    def test_T045_seq_monotonic(self):
        c = AuditChain(secret="s")
        seqs = [c.record(AuditEvent.AUTH_LOGIN_OK, user_id="u").seq for _ in range(10)]
        assert seqs == sorted(seqs) and len(set(seqs)) == 10
    def test_T046_chain_intact_after_concurrent(self):
        c = AuditChain(secret="s")
        def w():
            for _ in range(10): c.record(AuditEvent.AUTH_LOGIN_OK, user_id="u")
        threads = [threading.Thread(target=w) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(c) == 50 and c.verify_chain() is True
    def test_T047_lock_released_on_exception(self):
        c = AuditChain(secret="s")
        try: c.record(AuditEvent.LICENSE_REVOKED, user_id="u1")
        except MissingReasonError: pass
        r = c.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        assert r.seq == 1
    def test_T048_multi_logger_isolated(self):
        l1 = AuditLogger(chain=AuditChain(secret="s1"))
        l2 = AuditLogger(chain=AuditChain(secret="s2"))
        l1.auth_login_ok("u1"); l2.auth_login_ok("u2")
        assert len(l1) == 1 and len(l2) == 1

class TestAuditLoggerConvenience:
    def test_T049_auth_login_ok(self, logger):
        r = logger.auth_login_ok("u1"); assert r.event == AuditEvent.AUTH_LOGIN_OK.value
    def test_T050_auth_login_fail(self, logger):
        r = logger.auth_login_fail("u1"); assert r.severity == Severity.WARNING.value
    def test_T051_auth_lockout_critical(self, logger):
        r = logger.auth_login_lockout("u1"); assert r.severity == Severity.CRITICAL.value
    def test_T052_auth_token_reuse(self, logger):
        r = logger.auth_token_reuse("u1"); assert r.event == AuditEvent.AUTH_TOKEN_REUSE.value
    def test_T053_license_issued(self, logger):
        r = logger.license_issued("u1"); assert r.event == AuditEvent.LICENSE_ISSUED.value
    def test_T054_license_revoked_with_reason(self, logger):
        r = logger.license_revoked("u1", reason="Violation")
        assert r.event == AuditEvent.LICENSE_REVOKED.value and r.reason == "Violation"
    def test_T055_license_suspended(self, logger):
        r = logger.license_suspended("u1", reason="Abuse"); assert r.reason == "Abuse"
    def test_T056_license_expired(self, logger):
        r = logger.license_expired("u1"); assert r.event == AuditEvent.LICENSE_EXPIRED.value
    def test_T057_billing_checkout(self, logger):
        r = logger.billing_checkout("u1"); assert r.event == AuditEvent.BILLING_CHECKOUT.value
    def test_T058_billing_refund(self, logger):
        r = logger.billing_refund("u1", reason="Customer request")
        assert r.severity == Severity.CRITICAL.value
    def test_T059_trade_open(self, logger):
        r = logger.trade_open("u1", detail={"ticket": 42}); assert r.detail["ticket"] == 42
    def test_T060_trade_close(self, logger):
        r = logger.trade_close("u1"); assert r.event == AuditEvent.TRADE_CLOSE.value
    def test_T061_trade_duplicate(self, logger):
        r = logger.trade_duplicate_blocked("u1"); assert r.event == AuditEvent.TRADE_DUPLICATE_BLOCKED.value
    def test_T062_signal_emit(self, logger):
        r = logger.signal_emit("u1"); assert r.event == AuditEvent.SIGNAL_EMIT.value
    def test_T063_signal_dedup(self, logger):
        r = logger.signal_dedup_blocked("u1"); assert r.event == AuditEvent.SIGNAL_DEDUP_BLOCKED.value
    def test_T064_kill_switch_on(self, logger):
        r = logger.risk_kill_switch_on("u1", reason="MaxDD"); assert r.severity == Severity.CRITICAL.value
    def test_T065_kill_switch_off(self, logger):
        r = logger.risk_kill_switch_off("u1", reason="Manual reset"); assert r.reason == "Manual reset"
    def test_T066_risk_halt(self, logger):
        r = logger.risk_halt("u1", reason="Emergency"); assert r.severity == Severity.CRITICAL.value
    def test_T067_drawdown_alert(self, logger):
        r = logger.risk_drawdown_alert("u1"); assert r.severity == Severity.WARNING.value
    def test_T068_drawdown_critical(self, logger):
        r = logger.risk_drawdown_critical("u1"); assert r.severity == Severity.CRITICAL.value
    def test_T069_admin_export(self, logger):
        r = logger.admin_audit_export("admin1"); assert r.event == AuditEvent.ADMIN_AUDIT_EXPORT.value
    def test_T070_admin_verify(self, logger):
        r = logger.admin_chain_verify("admin1"); assert r.event == AuditEvent.ADMIN_CHAIN_VERIFY.value
    def test_T071_recon_mismatch(self, logger):
        r = logger.recon_mismatch(detail={"expected": 10, "actual": 9})
        assert r.severity == Severity.CRITICAL.value
    def test_T072_billing_payment_ok(self, logger):
        r = logger.billing_payment_ok("u1"); assert r.event == AuditEvent.BILLING_PAYMENT_OK.value

class TestQueryAndFilter:
    def test_T073_query_by_user(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_ok("u2")
        assert len(logger.query(user_id="u1")) == 1
    def test_T074_query_by_tenant(self, logger):
        logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="ta")
        logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u2", tenant_id="tb")
        assert len(logger.query(tenant_id="ta")) == 1
    def test_T075_query_by_event(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_fail("u2")
        assert len(logger.query(event=AuditEvent.AUTH_LOGIN_OK.value)) == 1
    def test_T076_query_by_severity(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_lockout("u2")
        res = logger.query(severity=Severity.CRITICAL.value)
        assert len(res) >= 1 and all(r.severity == Severity.CRITICAL.value for r in res)
    def test_T077_query_since_ts(self, logger):
        t0 = time.time(); logger.auth_login_ok("u1")
        assert len(logger.query(since_ts=t0)) == 1
    def test_T078_query_until_ts(self, logger):
        logger.auth_login_ok("u1"); t1 = time.time()
        assert len(logger.query(until_ts=t1)) == 1
    def test_T079_query_limit(self, logger):
        for i in range(20): logger.auth_login_ok(f"u{i}")
        assert len(logger.query(limit=5)) == 5
    def test_T080_query_empty(self, logger):
        assert logger.query(user_id="nobody") == []
    def test_T081_query_multi_filter(self, logger):
        logger.record(AuditEvent.AUTH_LOGIN_FAIL, user_id="u1", tenant_id="ta")
        logger.record(AuditEvent.AUTH_LOGIN_FAIL, user_id="u2", tenant_id="tb")
        res = logger.query(user_id="u1", tenant_id="ta")
        assert len(res) == 1 and res[0].user_id == "u1"
    def test_T082_query_returns_newest_first(self, logger):
        for i in range(3): logger.auth_login_ok(f"u{i}")
        res = logger.query()
        assert res[0].seq > res[-1].seq
    def test_T083_query_until_before_since(self, logger):
        logger.auth_login_ok("u1")
        assert logger.query(since_ts=time.time()+1) == []
    def test_T084_summary_counts_critical(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_lockout("u2")
        s = logger.summary(); assert s["total"] == 2 and s["critical_count"] >= 1

class TestExportAndForensics:
    def test_T085_jsonl_nonempty(self, logger):
        logger.auth_login_ok("u1"); assert len(logger.export_jsonl()) > 0
    def test_T086_jsonl_valid_json(self, logger):
        logger.auth_login_ok("u1")
        for ln in logger.export_jsonl().split("\n"):
            if ln.strip(): json.loads(ln)
    def test_T087_jsonl_has_chain_hash(self, logger):
        logger.auth_login_ok("u1")
        obj = json.loads(logger.export_jsonl().strip())
        assert "chain_hash" in obj and len(obj["chain_hash"]) == 64
    def test_T088_csv_has_header(self, logger):
        logger.auth_login_ok("u1")
        assert logger.export_csv().startswith("seq,")
    def test_T089_csv_chain_hash_col(self, logger):
        logger.auth_login_ok("u1")
        rows = list(csv.DictReader(io.StringIO(logger.export_csv())))
        assert "chain_hash" in rows[0] and len(rows[0]["chain_hash"]) == 64
    def test_T090_verify_then_export(self, logger):
        for i in range(5): logger.auth_login_ok(f"u{i}")
        assert logger.verify_chain() is True
        logger.export_jsonl()
        assert logger.verify_chain() is True
    def test_T091_detect_tamper_empty(self, logger):
        assert logger.detect_tamper() == []
    def test_T092_detect_tamper_after_mutate(self, chain):
        recs = [chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}") for i in range(5)]
        object.__setattr__(recs[1], "event", "auth.hacked")
        broken = chain.detect_tamper()
        assert recs[1].seq in broken
    def test_T093_export_csv_row_count(self, logger):
        for i in range(7): logger.auth_login_ok(f"u{i}")
        rows = list(csv.DictReader(io.StringIO(logger.export_csv())))
        assert len(rows) == 7
    def test_T094_jsonl_line_count(self, logger):
        for i in range(4): logger.auth_login_ok(f"u{i}")
        lines = [l for l in logger.export_jsonl().split("\n") if l.strip()]
        assert len(lines) == 4
    def test_T095_summary_last_hash(self, logger):
        r = logger.auth_login_ok("u1")
        assert logger.summary()["last_hash"] == r.chain_hash
    def test_T096_summary_genesis(self, chain):
        assert chain.summary()["genesis_hash"] == chain._genesis

class TestSQLMigration:
    def _sql(self):
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        paths = [
            os.path.join(base, "supabase", "migrations", "20260626_029_phase21_audit_chain.sql"),
            os.path.join(base, "..", "supabase", "migrations", "20260626_029_phase21_audit_chain.sql"),
        ]
        for p in paths:
            if os.path.exists(p):
                with open(p) as f: return f.read()
        return ""
    def test_T097_sql_has_begin_commit(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "BEGIN" in s and "COMMIT" in s
    def test_T098_sql_has_chain_hash_col(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "chain_hash" in s
    def test_T099_sql_rls_enabled(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "ROW LEVEL SECURITY" in s
    def test_T100_sql_immutable_trigger(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "trg_audit_v21_no_update" in s or "immutable" in s.lower()
    def test_T101_sql_reason_trigger(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "require_reason" in s or "reason" in s
    def test_T102_sql_severity_col(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "severity" in s
    def test_T103_sql_tenant_id_col(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "tenant_id" in s
    def test_T104_sql_verify_fn(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "verify_audit_chain_v21" in s
    def test_T105_sql_if_not_exists(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "IF NOT EXISTS" in s
    def test_T106_sql_seq_col(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "seq" in s
    def test_T107_sql_64_char_constraint(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "64" in s or "length(chain_hash)" in s
    def test_T108_sql_gin_index(self):
        s = self._sql()
        if not s: pytest.skip("SQL file not found")
        assert "gin" in s.lower() or "jsonb" in s.lower()

class TestAdminRoutes:
    def _routes(self):
        from backend.api.routes.audit_routes_v21 import (
            get_admin_audit_list, get_admin_audit_summary, get_admin_audit_verify,
            get_admin_audit_tamper, get_admin_audit_export_jsonl, get_admin_audit_export_csv,
            get_admin_audit_events, get_admin_audit_user_trail, post_admin_audit_test,
            ADMIN_AUDIT_ROUTES, audit_logger,
        )
        return locals()
    def test_T109_route_list_exists(self): assert callable(self._routes()["get_admin_audit_list"])
    def test_T110_route_summary_exists(self): assert callable(self._routes()["get_admin_audit_summary"])
    def test_T111_route_verify_exists(self): assert callable(self._routes()["get_admin_audit_verify"])
    def test_T112_route_tamper_exists(self): assert callable(self._routes()["get_admin_audit_tamper"])
    def test_T113_route_jsonl_exists(self): assert callable(self._routes()["get_admin_audit_export_jsonl"])
    def test_T114_route_csv_exists(self): assert callable(self._routes()["get_admin_audit_export_csv"])
    def test_T115_route_events_exists(self): assert callable(self._routes()["get_admin_audit_events"])
    def test_T116_route_user_trail_exists(self): assert callable(self._routes()["get_admin_audit_user_trail"])
    def test_T117_route_test_exists(self): assert callable(self._routes()["post_admin_audit_test"])
    def test_T118_admin_routes_count(self):
        r = self._routes(); assert len(r["ADMIN_AUDIT_ROUTES"]) >= 9
    def test_T119_verify_returns_valid(self):
        r = self._routes(); res = r["get_admin_audit_verify"]()
        assert "valid" in res and "genesis_hash" in res
    def test_T120_events_returns_64_plus(self):
        r = self._routes(); res = r["get_admin_audit_events"]()
        assert res["total"] >= 64

class TestForensicTrailQuality:
    def test_T121_ip_recorded(self, logger):
        r = logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", ip="1.2.3.4")
        assert r.ip == "1.2.3.4"
    def test_T122_actor_id_recorded(self, logger):
        r = logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", actor_id="admin1")
        assert r.actor_id == "admin1"
    def test_T123_uuid_format(self, logger):
        r = logger.auth_login_ok("u1"); uuid.UUID(r.id)
    def test_T124_timestamp_recent(self, logger):
        t0 = time.time(); r = logger.auth_login_ok("u1")
        assert abs(r.ts - t0) < 1.0
    def test_T125_detail_preserved(self, logger):
        r = logger.trade_open("u1", detail={"ticket": 999, "symbol": "EURUSD"})
        assert r.detail["ticket"] == 999 and r.detail["symbol"] == "EURUSD"
    def test_T126_severity_info(self, logger):
        r = logger.auth_login_ok("u1"); assert r.severity == Severity.INFO.value
    def test_T127_severity_warning(self, logger):
        r = logger.auth_login_fail("u1"); assert r.severity == Severity.WARNING.value
    def test_T128_severity_critical(self, logger):
        r = logger.auth_login_lockout("u1"); assert r.severity == Severity.CRITICAL.value
    def test_T129_tenant_id_recorded(self, logger):
        r = logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="t_acme")
        assert r.tenant_id == "t_acme"
    def test_T130_default_tenant(self, logger):
        r = logger.auth_login_ok("u1"); assert r.tenant_id == "default"
    def test_T131_reason_recorded(self, logger):
        r = logger.license_revoked("u1", reason="TOS violation")
        assert r.reason == "TOS violation"
    def test_T132_500_record_chain_valid(self):
        c = AuditChain(secret="perf")
        for i in range(500): c.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i%10}")
        assert c.verify_chain() is True and len(c) == 500
    def test_T133_kill_switch_detail(self, logger):
        r = logger.risk_kill_switch_on("u1", reason="MaxDD", detail={"equity": 9500})
        assert r.detail["equity"] == 9500
    def test_T134_trade_ticket_detail(self, logger):
        r = logger.trade_open("u1", detail={"ticket": 12345})
        assert r.detail["ticket"] == 12345
    def test_T135_billing_amount_detail(self, logger):
        r = logger.billing_checkout("u1", detail={"amount": 99.99, "currency": "USD"})
        assert r.detail["amount"] == 99.99
    def test_T136_license_id_detail(self, logger):
        r = logger.license_issued("u1", detail={"license_id": "lic-001"})
        assert r.detail["license_id"] == "lic-001"
    def test_T137_seq_starts_at_1(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1"); assert r.seq == 1
    def test_T138_seq_increments(self, chain):
        r1 = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1")
        assert r2.seq == r1.seq + 1
    def test_T139_to_dict_all_fields(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        d = r.to_dict()
        for key in ["id","seq","event","severity","ts","user_id","tenant_id",
                    "actor_id","ip","reason","detail","chain_hash","prev_hash"]:
            assert key in d, f"missing {key}"
    def test_T140_to_dict_json_serializable(self, chain):
        r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        json.dumps(r.to_dict())

class TestIntegrationFlows:
    def test_T141_full_auth_flow(self):
        l = AuditLogger(chain=AuditChain(secret="auth"))
        l.auth_login_fail("u1"); l.auth_login_fail("u1"); l.auth_login_lockout("u1")
        assert l.verify_chain() is True and len(l) == 3
        assert len(l.query(severity=Severity.CRITICAL.value)) == 1
    def test_T142_full_license_flow(self):
        l = AuditLogger(chain=AuditChain(secret="lic"))
        l.license_issued("u1", tenant_id="t1")
        l.record(AuditEvent.LICENSE_ACTIVATED, user_id="u1", tenant_id="t1")
        l.license_revoked("u1", reason="Fraud", tenant_id="t1")
        assert l.verify_chain() is True and len(l.query(tenant_id="t1")) == 3
    def test_T143_full_billing_flow(self):
        l = AuditLogger(chain=AuditChain(secret="bill"))
        l.billing_checkout("u1"); l.billing_payment_ok("u1")
        l.billing_refund("u1", reason="Customer request")
        assert l.verify_chain() is True
    def test_T144_full_risk_flow(self):
        l = AuditLogger(chain=AuditChain(secret="risk"))
        l.risk_drawdown_alert("u1"); l.risk_drawdown_critical("u1")
        l.risk_kill_switch_on("u1", reason="MaxDD20%")
        assert l.verify_chain() is True
        assert len(l.query(severity=Severity.CRITICAL.value)) == 2
    def test_T145_cross_tenant_isolation(self):
        l = AuditLogger(chain=AuditChain(secret="iso"))
        for i in range(5): l.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="ta")
        for i in range(3): l.record(AuditEvent.AUTH_LOGIN_OK, user_id="u2", tenant_id="tb")
        assert len(l.query(tenant_id="ta")) == 5
        assert len(l.query(tenant_id="tb")) == 3
    def test_T146_admin_export_audit_trail(self):
        l = AuditLogger(chain=AuditChain(secret="adm"))
        for i in range(5): l.auth_login_ok(f"u{i}")
        l.admin_audit_export("admin1")
        assert l.query(event=AuditEvent.ADMIN_AUDIT_EXPORT.value)[0].user_id == "admin1"
    def test_T147_verify_then_export_then_verify(self):
        l = AuditLogger(chain=AuditChain(secret="v"))
        for i in range(10): l.auth_login_ok(f"u{i}")
        assert l.verify_chain() is True
        l.export_jsonl(); l.export_csv()
        assert l.verify_chain() is True
    def test_T148_tamper_breaks_verify(self):
        c = AuditChain(secret="t")
        recs = [c.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}") for i in range(5)]
        assert c.verify_chain() is True
        object.__setattr__(recs[0], "event", "auth.hacked")
        assert c.verify_chain() is False
    def test_T149_trading_full_flow(self):
        l = AuditLogger(chain=AuditChain(secret="trade"))
        l.signal_emit("u1", detail={"symbol": "EURUSD"})
        l.trade_open("u1", detail={"ticket": 1001})
        l.trade_duplicate_blocked("u1")
        l.trade_close("u1", detail={"ticket": 1001})
        l.recon_mismatch(detail={"expected": 10, "actual": 9})
        assert l.verify_chain() is True and len(l) == 5
    def test_T150_summary_seq_max_matches(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        for i in range(5): l.auth_login_ok(f"u{i}")
        assert l.summary()["seq_max"] == 5
    def test_T151_500_records_export(self):
        l = AuditLogger(chain=AuditChain(secret="perf"))
        for i in range(500): l.auth_login_ok(f"u{i%10}")
        assert len([ln for ln in l.export_jsonl().split("\n") if ln.strip()]) == 500
    def test_T152_concurrent_multi_tenant(self):
        l = AuditLogger(chain=AuditChain(secret="s")); errors = []
        def w(tn, un):
            try: l.record(AuditEvent.AUTH_LOGIN_OK, user_id=un, tenant_id=tn)
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=w, args=(f"t{i}", f"u{j}")) for i in range(5) for j in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == [] and l.verify_chain() is True and len(l) == 50
    def test_T153_missing_reason_no_write(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        try: l.license_revoked("u1", reason="")
        except MissingReasonError: pass
        assert len(l) == 0
    def test_T154_csv_row_count(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        for i in range(10): l.auth_login_ok(f"u{i}")
        assert len(list(csv.DictReader(io.StringIO(l.export_csv())))) == 10
    def test_T155_recon_mismatch_critical(self):
        l = AuditLogger(chain=AuditChain(secret="s")); l.recon_mismatch(detail={"e": 5, "a": 4})
        res = l.query(severity=Severity.CRITICAL.value)
        assert len(res) == 1 and res[0].event == AuditEvent.RECON_MISMATCH.value
    def test_T156_signal_dedup_info(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        l.record(AuditEvent.SIGNAL_DEDUP_BLOCKED, user_id="u1")
        assert l.query(event=AuditEvent.SIGNAL_DEDUP_BLOCKED.value)[0].severity == Severity.INFO.value
    def test_T157_hash_differs_by_detail(self):
        c1 = AuditChain(secret="s"); c2 = AuditChain(secret="s")
        r1 = c1.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", detail={"a": 1})
        r2 = c2.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", detail={"a": 2})
        assert r1.chain_hash != r2.chain_hash
    def test_T158_hash_differs_by_reason(self):
        c1 = AuditChain(secret="s"); c2 = AuditChain(secret="s")
        r1 = c1.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="A")
        r2 = c2.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="B")
        assert r1.chain_hash != r2.chain_hash
    def test_T159_hash_differs_by_tenant(self):
        c1 = AuditChain(secret="s"); c2 = AuditChain(secret="s")
        r1 = c1.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="ta")
        r2 = c2.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="tb")
        assert r1.chain_hash != r2.chain_hash
    def test_T160_hook_full_record(self):
        received = []; l = AuditLogger(chain=AuditChain(secret="s"))
        l.add_write_hook(lambda r: received.append(r))
        l.trade_open("u1", tenant_id="t1", detail={"ticket": 99})
        assert received[0].user_id == "u1" and received[0].detail["ticket"] == 99
    def test_T161_summary_seq_max(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        for i in range(5): l.auth_login_ok(f"u{i}")
        assert l.summary()["seq_max"] == 5
    def test_T162_jsonl_sorted_keys(self):
        l = AuditLogger(chain=AuditChain(secret="s")); l.auth_login_ok("u1")
        obj = json.loads(l.export_jsonl().strip())
        assert list(obj.keys()) == sorted(obj.keys())
    def test_T163_export_recorded(self):
        l = AuditLogger(chain=AuditChain(secret="s")); l.admin_audit_export("a1")
        assert len(l.query(event=AuditEvent.ADMIN_AUDIT_EXPORT.value)) == 1
    def test_T164_verify_recorded(self):
        l = AuditLogger(chain=AuditChain(secret="s")); l.admin_chain_verify("a1")
        assert len(l.query(event=AuditEvent.ADMIN_CHAIN_VERIFY.value)) == 1
    def test_T165_user_deleted_requires_reason(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        with pytest.raises(MissingReasonError): l.rbac_user_deleted("u1", reason="")
    def test_T166_purge_requires_reason(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        with pytest.raises(MissingReasonError): l.tenant_purge("a1", reason="")
    def test_T167_tenant_isolation_query(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        for _ in range(5): l.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", tenant_id="ta")
        for _ in range(3): l.record(AuditEvent.AUTH_LOGIN_OK, user_id="u2", tenant_id="tb")
        assert len(l.query(tenant_id="ta")) == 5 and len(l.query(tenant_id="tb")) == 3
    def test_T168_csv_no_mutate(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        for i in range(10): l.auth_login_ok(f"u{i}")
        l.export_csv(); assert l.verify_chain() is True
    def test_T169_signal_detail(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        l.signal_emit("u1", tenant_id="t1", detail={"symbol": "EURUSD"})
        assert l.query(event=AuditEvent.SIGNAL_EMIT.value)[0].detail["symbol"] == "EURUSD"
    def test_T170_drawdown_warning(self):
        l = AuditLogger(chain=AuditChain(secret="s"))
        assert l.risk_drawdown_alert("u1").severity == Severity.WARNING.value
    def test_T171_full_compliance_trail(self):
        l = AuditLogger(chain=AuditChain(secret="compliance"))
        l.billing_checkout("u1", tenant_id="t1", detail={"plan": "pro"})
        l.billing_payment_ok("u1", tenant_id="t1")
        l.license_issued("u1", tenant_id="t1")
        l.trade_open("u1", tenant_id="t1", detail={"ticket": 1001})
        l.risk_drawdown_alert("u1", tenant_id="t1")
        l.risk_kill_switch_on("u1", tenant_id="t1", reason="D20%")
        assert len(l) == 6 and l.verify_chain() is True
        assert len(l.query(severity=Severity.CRITICAL.value)) >= 1
        assert len(l.query(tenant_id="t1")) == 6
    def test_T172_tamper_middle_of_chain(self):
        l = AuditLogger(chain=AuditChain(secret="tamper"))
        recs = [l.auth_login_ok(f"u{i}") for i in range(5)]
        assert l.verify_chain() is True
        object.__setattr__(recs[2], "event", "auth.hacked")
        assert l.verify_chain() is False and recs[2].seq in l.detect_tamper()
