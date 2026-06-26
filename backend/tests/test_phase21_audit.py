"""Phase 21 - Tamper-Evident Audit Logging - 172 tests - FINAL"""
from __future__ import annotations
import csv, io, json, threading, time, uuid
import pytest, sys, os
sys.path.insert(0, '/home/definable/phase21')
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
        object.__setattr__(r2, "event", "auth.login.ok")
        assert chain.verify_chain() is False
    def test_T025_tamper_detail_breaks_chain(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1", detail={"k": "v"})
        object.__setattr__(r2, "detail", {"k": "TAMPERED"})
        assert chain.verify_chain() is False
    def test_T026_tamper_reason_breaks_chain(self, chain):
        r1 = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", reason="ok")
        object.__setattr__(r1, "reason", "TAMPERED")
        assert chain.verify_chain() is False
    def test_T027_wrong_secret(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        c2 = AuditChain(secret="wrong-secret")
        c2._records = chain._records; c2._seq = chain._seq
        assert c2.verify_chain() is False
    def test_T028_prev_hash_matches(self, chain):
        r1 = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
        r2 = chain.record(AuditEvent.AUTH_LOGOUT, user_id="u1")
        assert r2.prev_hash == r1.chain_hash

class TestMandatoryReason:
    def test_T029_license_revoke_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="")
    def test_T030_license_revoke_with_reason(self, chain):
        r = chain.record(AuditEvent.LICENSE_REVOKED, user_id="u1", reason="Fraud")
        assert r.reason == "Fraud"
    def test_T031_kill_switch_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RISK_KILL_SWITCH_ON, user_id="u1", reason="")
    def test_T032_kill_switch_with_reason(self, chain):
        assert chain.record(AuditEvent.RISK_KILL_SWITCH_ON, user_id="u1", reason="Drawdown exceeded") is not None
    def test_T033_whitespace_reason_raises(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RBAC_ROLE_CHANGED, user_id="u1", reason="   ")
    def test_T034_user_blocked_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RBAC_USER_BLOCKED, user_id="u1", reason="")
    def test_T035_refund_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.BILLING_REFUND, user_id="u1", reason="")
    def test_T036_impersonate_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.ADMIN_IMPERSONATE, actor_id="a1", reason="")
    def test_T037_tenant_suspend_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.TENANT_SUSPEND, actor_id="a1", reason="")
    def test_T038_tenant_purge_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.TENANT_PURGE, actor_id="a1", reason="")
    def test_T039_halt_no_reason(self, chain):
        with pytest.raises(MissingReasonError): chain.record(AuditEvent.RISK_HALT, user_id="u1", reason="")
    def test_T040_login_ok_no_reason_ok(self, chain):
        assert chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1") is not None

class TestThreadSafety:
    def test_T041_concurrent_unique_seqs(self, chain):
        results = []; lock = threading.Lock()
        def writer(i):
            r = chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
            with lock: results.append(r.seq)
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(results)) == 50
    def test_T042_concurrent_chain_valid(self, chain):
        def w(i): chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
        threads = [threading.Thread(target=w, args=(i,)) for i in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert chain.verify_chain() is True
    def test_T043_hook_error_isolated(self, chain):
        logger = AuditLogger(chain=chain)
        logger.add_write_hook(lambda r: (_ for _ in ()).throw(RuntimeError("bad")))
        assert logger.auth_login_ok("u1") is not None
    def test_T044_concurrent_hooks(self, chain):
        called = []; logger = AuditLogger(chain=chain)
        logger.add_write_hook(lambda r: called.append(1))
        threads = [threading.Thread(target=lambda: logger.auth_login_ok("u1")) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(called) == 20
    def test_T045_seq_monotonic(self, chain):
        seqs = [chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}").seq for i in range(20)]
        assert seqs == sorted(seqs) and len(set(seqs)) == 20
    def test_T046_concurrent_query_write(self, chain):
        stop = threading.Event(); errors = []
        def writer():
            while not stop.is_set():
                try: chain.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1")
                except Exception as e: errors.append(e)
        def reader():
            while not stop.is_set():
                try: chain.query(limit=10)
                except Exception as e: errors.append(e)
        threads = [threading.Thread(target=writer) for _ in range(3)] + [threading.Thread(target=reader) for _ in range(2)]
        for t in threads: t.start()
        time.sleep(0.1); stop.set()
        for t in threads: t.join()
        assert errors == []
    def test_T047_export_thread_safe(self, chain):
        for i in range(20): chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
        results = []
        def do(): results.append(chain.export_jsonl())
        threads = [threading.Thread(target=do) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(r == results[0] for r in results)
    def test_T048_summary_thread_safe(self, chain):
        for i in range(10): chain.record(AuditEvent.AUTH_LOGIN_OK, user_id=f"u{i}")
        results = []
        def do(): results.append(chain.summary())
        threads = [threading.Thread(target=do) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(results) == 5

class TestAuditLoggerConvenience:
    def test_T049_auth_login_ok(self, logger): assert logger.auth_login_ok("u1", tenant_id="t1").user_id == "u1"
    def test_T050_auth_login_fail(self, logger): assert logger.auth_login_fail("u1").event == AuditEvent.AUTH_LOGIN_FAIL.value
    def test_T051_auth_token_reuse_critical(self, logger): assert logger.auth_token_reuse("u1").severity == Severity.CRITICAL.value
    def test_T052_license_issued_detail(self, logger): assert logger.license_issued("u1", detail={"lic": "x"}).detail["lic"] == "x"
    def test_T053_license_revoked_requires(self, logger):
        with pytest.raises(MissingReasonError): logger.license_revoked("u1", reason="")
    def test_T054_license_revoked_ok(self, logger): assert logger.license_revoked("u1", reason="V").reason == "V"
    def test_T055_billing_checkout(self, logger): assert logger.billing_checkout("u1").event == AuditEvent.BILLING_CHECKOUT.value
    def test_T056_billing_refund_requires(self, logger):
        with pytest.raises(MissingReasonError): logger.billing_refund("u1", reason="")
    def test_T057_kill_switch_critical(self, logger): assert logger.risk_kill_switch_on("u1", reason="D").severity == Severity.CRITICAL.value
    def test_T058_risk_halt(self, logger): assert logger.risk_halt("u1", reason="E").event == AuditEvent.RISK_HALT.value
    def test_T059_admin_cross_tenant(self, logger): assert logger.admin_cross_tenant("a1").event == AuditEvent.ADMIN_CROSS_TENANT.value
    def test_T060_admin_impersonate(self, logger): assert logger.admin_impersonate("a1", reason="D").event == AuditEvent.ADMIN_IMPERSONATE.value
    def test_T061_trade_open(self, logger): assert logger.trade_open("u1", detail={"ticket": 1}).event == AuditEvent.TRADE_OPEN.value
    def test_T062_recon_mismatch(self, logger): assert logger.recon_mismatch().event == AuditEvent.RECON_MISMATCH.value
    def test_T063_rbac_role_changed(self, logger): assert logger.rbac_role_changed("u1", reason="P").event == AuditEvent.RBAC_ROLE_CHANGED.value
    def test_T064_rbac_user_blocked(self, logger): assert logger.rbac_user_blocked("u1", reason="T").event == AuditEvent.RBAC_USER_BLOCKED.value
    def test_T065_tenant_suspend(self, logger): assert logger.tenant_suspend("a1", reason="N").event == AuditEvent.TENANT_SUSPEND.value
    def test_T066_record_with_ip(self, logger): assert logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", ip="1.2.3.4").ip == "1.2.3.4"
    def test_T067_record_with_actor(self, logger): assert logger.record(AuditEvent.ADMIN_AUDIT_EXPORT, actor_id="a1").actor_id == "a1"
    def test_T068_record_kwargs_in_detail(self, logger): assert logger.record(AuditEvent.AUTH_LOGIN_OK, user_id="u1", foo="bar").detail.get("foo") == "bar"

class TestQueryAndFilter:
    def test_T069_by_user(self, logger):
        logger.auth_login_ok("alice"); logger.auth_login_ok("bob")
        assert all(r.user_id=="alice" for r in logger.query(user_id="alice"))
    def test_T070_by_tenant(self, logger):
        logger.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",tenant_id="ta")
        logger.record(AuditEvent.AUTH_LOGIN_OK,user_id="u2",tenant_id="tb")
        assert all(r.tenant_id=="ta" for r in logger.query(tenant_id="ta"))
    def test_T071_by_event(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_fail("u2")
        assert all(r.event==AuditEvent.AUTH_LOGIN_FAIL.value for r in logger.query(event=AuditEvent.AUTH_LOGIN_FAIL.value))
    def test_T072_by_severity(self, logger):
        logger.auth_login_ok("u1"); logger.auth_token_reuse("u2")
        assert all(r.severity==Severity.CRITICAL.value for r in logger.query(severity=Severity.CRITICAL.value))
    def test_T073_limit(self, logger):
        for i in range(20): logger.auth_login_ok(f"u{i}")
        assert len(logger.query(limit=5)) <= 5
    def test_T074_since_ts(self, logger):
        logger.auth_login_ok("u1"); ts=time.time(); time.sleep(0.01); logger.auth_login_ok("u2")
        assert all(r.ts>ts+0.005 for r in logger.query(since_ts=ts+0.005))
    def test_T075_until_ts(self, logger):
        logger.auth_login_ok("u1"); ts=time.time(); logger.auth_login_ok("u2")
        assert all(r.ts<=ts for r in logger.query(until_ts=ts))
    def test_T076_multi_filter(self, logger):
        logger.record(AuditEvent.AUTH_LOGIN_FAIL,user_id="alice",tenant_id="ta")
        logger.record(AuditEvent.AUTH_LOGIN_OK,user_id="alice",tenant_id="ta")
        logger.record(AuditEvent.AUTH_LOGIN_FAIL,user_id="bob",tenant_id="ta")
        res=logger.query(user_id="alice",event=AuditEvent.AUTH_LOGIN_FAIL.value)
        assert len(res)==1 and res[0].user_id=="alice"
    def test_T077_most_recent_first(self, logger):
        for i in range(5): logger.auth_login_ok(f"u{i}")
        seqs=[r.seq for r in logger.query(limit=5)]
        assert seqs==sorted(seqs,reverse=True)
    def test_T078_summary_total(self, logger):
        for i in range(5): logger.auth_login_ok(f"u{i}")
        assert logger.summary()["total"]==5
    def test_T079_summary_critical(self, logger):
        logger.auth_token_reuse("u1"); logger.auth_login_ok("u2")
        assert logger.summary()["critical_count"]>=1
    def test_T080_summary_last_hash(self, logger):
        r=logger.auth_login_ok("u1"); assert logger.summary()["last_hash"]==r.chain_hash
    def test_T081_summary_genesis(self, logger): assert len(logger.summary()["genesis_hash"])==64
    def test_T082_len_matches(self, logger):
        for i in range(7): logger.auth_login_ok(f"u{i}")
        assert len(logger)==7
    def test_T083_empty_result(self, logger): assert logger.query(user_id="nonexistent")==[]
    def test_T084_record_uuid(self, logger): r=logger.auth_login_ok("u1"); uuid.UUID(r.id)

class TestExportAndForensics:
    def test_T085_jsonl_format(self, logger):
        logger.auth_login_ok("u1"); logger.auth_login_fail("u2")
        lines=[l for l in logger.export_jsonl().split("\n") if l.strip()]
        assert len(lines)==2 and all("chain_hash" in json.loads(l) for l in lines)
    def test_T086_jsonl_hash_64(self, logger):
        logger.auth_login_ok("u1")
        assert len(json.loads(logger.export_jsonl().strip())["chain_hash"])==64
    def test_T087_csv_header(self, logger):
        logger.auth_login_ok("u1"); assert "chain_hash" in logger.export_csv().splitlines()[0]
    def test_T088_csv_data_row(self, logger):
        logger.auth_login_ok("u1")
        rows=list(csv.DictReader(io.StringIO(logger.export_csv())))
        assert len(rows)==1 and len(rows[0]["chain_hash"])==64
    def test_T089_export_no_mutate(self, logger):
        for i in range(5): logger.auth_login_ok(f"u{i}")
        logger.export_jsonl(); assert logger.verify_chain() is True
    def test_T090_detect_tamper_clean(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1")
        chain.record(AuditEvent.AUTH_LOGOUT,user_id="u1")
        assert chain.detect_tamper()==[]
    def test_T091_detect_tamper_mutated(self, chain):
        chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1")
        r2=chain.record(AuditEvent.AUTH_LOGOUT,user_id="u1")
        object.__setattr__(r2,"event","TAMPERED")
        assert r2.seq in chain.detect_tamper()
    def test_T092_export_jsonl_empty(self, logger): assert logger.export_jsonl()==""
    def test_T093_csv_empty_header_only(self, logger):
        lines=logger.export_csv().strip().splitlines()
        assert len(lines)==1 and "chain_hash" in lines[0]
    def test_T094_verify_50_records(self, chain):
        for i in range(50): chain.record(AuditEvent.AUTH_LOGIN_OK,user_id=f"u{i}")
        assert chain.verify_chain() is True
    def test_T095_to_dict_fields(self, chain):
        r=chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",tenant_id="t1",ip="x",reason="ok")
        for f in ["id","seq","event","severity","ts","user_id","tenant_id","actor_id","ip","reason","detail","chain_hash","prev_hash"]:
            assert f in r.to_dict()
    def test_T096_severity_is_string(self, chain):
        r=chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1")
        assert isinstance(r.severity,str)

class TestSQLMigration:
    @pytest.fixture
    def sql(self):
        candidates=[
            "/home/definable/phase21/supabase/migrations/20260626_029_phase21_audit_chain.sql",
            "/home/definable/bot12/supabase/migrations/20260626_029_phase21_audit_chain.sql",
        ]
        for p in candidates:
            if os.path.exists(p): return open(p).read()
        pytest.skip("SQL file not found")
    def test_T097_begin_commit(self,sql): assert "BEGIN" in sql and "COMMIT" in sql
    def test_T098_table_name(self,sql): assert "audit_log_v21" in sql
    def test_T099_chain_hash_col(self,sql): assert "chain_hash" in sql
    def test_T100_length_64(self,sql): assert "64" in sql
    def test_T101_rls(self,sql): assert "ROW LEVEL SECURITY" in sql
    def test_T102_immutability(self,sql): assert "immutable" in sql.lower()
    def test_T103_reason(self,sql): assert "reason" in sql.lower()
    def test_T104_severity(self,sql): assert "severity" in sql
    def test_T105_tenant_id(self,sql): assert "tenant_id" in sql
    def test_T106_if_not_exists(self,sql): assert "IF NOT EXISTS" in sql
    def test_T107_verify_fn(self,sql): assert "verify_audit_chain_v21" in sql
    def test_T108_indexes(self,sql): assert sql.count("CREATE INDEX")>=4

class TestForensicTrailQuality:
    def test_T109_ip(self,logger): assert logger.record(AuditEvent.AUTH_LOGIN_FAIL,user_id="u1",ip="1.2.3.4").ip=="1.2.3.4"
    def test_T110_actor(self,logger): assert logger.admin_impersonate("a1",reason="S").actor_id=="a1"
    def test_T111_detail(self,logger): assert logger.billing_checkout("u1",detail={"plan":"pro"}).detail["plan"]=="pro"
    def test_T112_timestamp(self,logger): r=logger.auth_login_ok("u1"); assert isinstance(r.ts,float) and r.ts>0
    def test_T113_tenant(self,logger): assert logger.record(AuditEvent.TRADE_OPEN,user_id="u1",tenant_id="t_a").tenant_id=="t_a"
    def test_T114_reason(self,logger): assert logger.license_revoked("u1",reason="P").reason=="P"
    def test_T115_info_severity(self,logger): assert logger.auth_login_ok("u1").severity==Severity.INFO.value
    def test_T116_warning_severity(self,logger): assert logger.auth_login_fail("u1").severity==Severity.WARNING.value
    def test_T117_critical_severity(self,logger): assert logger.risk_kill_switch_on("u1",reason="E").severity==Severity.CRITICAL.value
    def test_T118_seq_starts_1(self,chain): assert chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1").seq==1
    def test_T119_seq_increments(self,chain):
        r1=chain.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1")
        r2=chain.record(AuditEvent.AUTH_LOGOUT,user_id="u1")
        assert r2.seq==r1.seq+1
    def test_T120_500_records(self,chain):
        for i in range(500): chain.record(AuditEvent.AUTH_LOGIN_OK,user_id=f"u{i%10}")
        assert chain.verify_chain() is True and len(chain)==500
    def test_T121_empty_detail_default(self,logger): assert logger.auth_login_ok("u1").detail=={}
    def test_T122_uuid_id(self,logger): r=logger.auth_login_ok("u1"); assert str(uuid.UUID(r.id))==r.id
    def test_T123_different_secrets_genesis(self):
        assert AuditChain(secret="a")._genesis != AuditChain(secret="b")._genesis
    def test_T124_genesis_not_plain_string(self):
        c=AuditChain(secret="t"); assert c._genesis!="GENESIS" and len(c._genesis)==64

class TestAdminRoutes:
    @pytest.fixture
    def src(self):
        p="/home/definable/phase21/backend/api/routes/audit_routes_v21.py"
        if not os.path.exists(p): pytest.skip("routes file not found")
        return open(p).read()
    def test_T125_audit_in_src(self,src): assert "audit" in src.lower()
    def test_T126_verify(self,src): assert "verify" in src
    def test_T127_jsonl(self,src): assert "jsonl" in src or "export" in src
    def test_T128_csv(self,src): assert "csv" in src
    def test_T129_events(self,src): assert "events" in src
    def test_T130_user(self,src): assert "user" in src
    def test_T131_summary(self,src): assert "summary" in src
    def test_T132_tamper(self,src): assert "tamper" in src
    def test_T133_admin(self,src): assert "admin" in src.lower()
    def test_T134_logger(self,src): assert "AuditLogger" in src or "audit_logger" in src

class TestAuditLoggerChainIsolation:
    def test_T137_two_loggers_independent(self):
        l1=AuditLogger(chain=AuditChain(secret="s1")); l2=AuditLogger(chain=AuditChain(secret="s2"))
        l1.auth_login_ok("u1"); l2.auth_login_ok("u2")
        assert len(l1)==1 and len(l2)==1
    def test_T138_none_chain_fresh(self):
        assert AuditLogger(chain=None).auth_login_ok("u1") is not None
    def test_T139_uses_provided_chain(self):
        c=AuditChain(secret="s"); l=AuditLogger(chain=c); l.auth_login_ok("u1"); assert len(c)==1
    def test_T140_hook_called(self):
        called=[]; l=AuditLogger(chain=AuditChain(secret="s"))
        l.add_write_hook(lambda r: called.append(r.event)); l.auth_login_ok("u1"); assert len(called)==1
    def test_T141_multiple_hooks(self):
        counts=[0,0]; l=AuditLogger(chain=AuditChain(secret="s"))
        l.add_write_hook(lambda r: counts.__setitem__(0,counts[0]+1))
        l.add_write_hook(lambda r: counts.__setitem__(1,counts[1]+1))
        l.auth_login_ok("u1"); assert counts==[1,1]
    def test_T142_empty_chain_not_replaced(self):
        c=AuditChain(secret="specific"); assert len(c)==0; l=AuditLogger(chain=c); assert l._chain is c
    def test_T143_verify_via_logger(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for i in range(5): l.auth_login_ok(f"u{i}")
        assert l.verify_chain() is True
    def test_T144_detect_tamper_via_logger(self):
        l=AuditLogger(chain=AuditChain(secret="s")); r=l.auth_login_ok("u1")
        object.__setattr__(r,"event","tampered"); assert r.seq in l.detect_tamper()

class TestIntegrationFlows:
    def test_T145_auth_lifecycle(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.auth_login_fail("alice"); l.auth_login_fail("alice"); l.auth_login_lockout("alice")
        assert len(l)==3 and l.verify_chain() is True
    def test_T146_license_lifecycle(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.license_issued("u1",tenant_id="t1"); l.license_expired("u1",tenant_id="t1")
        l.license_revoked("u1",reason="Non",tenant_id="t1")
        assert l.verify_chain() is True and len(l.query(event=AuditEvent.LICENSE_REVOKED.value))==1
    def test_T147_kill_switch_flow(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.risk_drawdown_alert("u1"); l.risk_kill_switch_on("u1",reason="D15%")
        l.risk_kill_switch_off("u1",reason="Reset")
        assert l.verify_chain() is True and len(l.query(severity=Severity.CRITICAL.value))>=1
    def test_T148_cross_tenant_isolation(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.record(AuditEvent.TRADE_OPEN,user_id="u1",tenant_id="ta")
        l.record(AuditEvent.TRADE_OPEN,user_id="u2",tenant_id="tb")
        assert len(l.query(tenant_id="ta"))==1 and len(l.query(tenant_id="tb"))==1
    def test_T149_billing_with_webhook(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.billing_checkout("u1"); l.billing_payment_ok("u1"); l.billing_webhook_fail()
        assert l.verify_chain() is True
    def test_T150_admin_cross_tenant_audited(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.admin_cross_tenant("admin1",reason="Ticket #1",detail={"target":"tx"})
        res=l.query(event=AuditEvent.ADMIN_CROSS_TENANT.value)
        assert len(res)==1 and res[0].reason=="Ticket #1"
    def test_T151_500_records_export(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for i in range(500): l.auth_login_ok(f"u{i%20}",tenant_id=f"t{i%5}")
        assert l.verify_chain() is True
        assert len([ln for ln in l.export_jsonl().split("\n") if ln.strip()])==500
    def test_T152_concurrent_multi_tenant(self):
        l=AuditLogger(chain=AuditChain(secret="s")); errors=[]
        def w(tn,un):
            try: l.record(AuditEvent.AUTH_LOGIN_OK,user_id=un,tenant_id=tn)
            except Exception as e: errors.append(e)
        threads=[threading.Thread(target=w,args=(f"t{i}",f"u{j}")) for i in range(5) for j in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors==[] and l.verify_chain() is True and len(l)==50
    def test_T153_missing_reason_no_write(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        try: l.license_revoked("u1",reason="")
        except MissingReasonError: pass
        assert len(l)==0
    def test_T154_csv_row_count(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for i in range(10): l.auth_login_ok(f"u{i}")
        assert len(list(csv.DictReader(io.StringIO(l.export_csv()))))==10
    def test_T155_recon_mismatch_critical(self):
        l=AuditLogger(chain=AuditChain(secret="s")); l.recon_mismatch(detail={"e":5,"a":4})
        res=l.query(severity=Severity.CRITICAL.value)
        assert len(res)==1 and res[0].event==AuditEvent.RECON_MISMATCH.value
    def test_T156_signal_dedup_info(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.record(AuditEvent.SIGNAL_DEDUP_BLOCKED,user_id="u1")
        assert l.query(event=AuditEvent.SIGNAL_DEDUP_BLOCKED.value)[0].severity==Severity.INFO.value
    def test_T157_hash_differs_by_detail(self):
        c1=AuditChain(secret="s"); c2=AuditChain(secret="s")
        r1=c1.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",detail={"a":1})
        r2=c2.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",detail={"a":2})
        assert r1.chain_hash!=r2.chain_hash
    def test_T158_hash_differs_by_reason(self):
        c1=AuditChain(secret="s"); c2=AuditChain(secret="s")
        r1=c1.record(AuditEvent.LICENSE_REVOKED,user_id="u1",reason="A")
        r2=c2.record(AuditEvent.LICENSE_REVOKED,user_id="u1",reason="B")
        assert r1.chain_hash!=r2.chain_hash
    def test_T159_hash_differs_by_tenant(self):
        c1=AuditChain(secret="s"); c2=AuditChain(secret="s")
        r1=c1.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",tenant_id="ta")
        r2=c2.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",tenant_id="tb")
        assert r1.chain_hash!=r2.chain_hash
    def test_T160_hook_full_record(self):
        received=[]; l=AuditLogger(chain=AuditChain(secret="s"))
        l.add_write_hook(lambda r: received.append(r))
        l.trade_open("u1",tenant_id="t1",detail={"ticket":99})
        assert received[0].user_id=="u1" and received[0].detail["ticket"]==99
    def test_T161_summary_seq_max(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for i in range(5): l.auth_login_ok(f"u{i}")
        assert l.summary()["seq_max"]==5
    def test_T162_jsonl_sorted_keys(self):
        l=AuditLogger(chain=AuditChain(secret="s")); l.auth_login_ok("u1")
        obj=json.loads(l.export_jsonl().strip())
        assert list(obj.keys())==sorted(obj.keys())
    def test_T163_export_recorded(self):
        l=AuditLogger(chain=AuditChain(secret="s")); l.admin_audit_export("a1")
        assert len(l.query(event=AuditEvent.ADMIN_AUDIT_EXPORT.value))==1
    def test_T164_verify_recorded(self):
        l=AuditLogger(chain=AuditChain(secret="s")); l.admin_chain_verify("a1")
        assert len(l.query(event=AuditEvent.ADMIN_CHAIN_VERIFY.value))==1
    def test_T165_user_deleted_requires_reason(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        with pytest.raises(MissingReasonError): l.rbac_user_deleted("u1",reason="")
    def test_T166_purge_requires_reason(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        with pytest.raises(MissingReasonError): l.tenant_purge("a1",reason="")
    def test_T167_tenant_isolation_query(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for _ in range(5): l.record(AuditEvent.AUTH_LOGIN_OK,user_id="u1",tenant_id="ta")
        for _ in range(3): l.record(AuditEvent.AUTH_LOGIN_OK,user_id="u2",tenant_id="tb")
        assert len(l.query(tenant_id="ta"))==5 and len(l.query(tenant_id="tb"))==3
    def test_T168_csv_no_mutate(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        for i in range(10): l.auth_login_ok(f"u{i}")
        l.export_csv(); assert l.verify_chain() is True
    def test_T169_signal_detail(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        l.signal_emit("u1",tenant_id="t1",detail={"symbol":"EURUSD"})
        assert l.query(event=AuditEvent.SIGNAL_EMIT.value)[0].detail["symbol"]=="EURUSD"
    def test_T170_drawdown_warning(self):
        l=AuditLogger(chain=AuditChain(secret="s"))
        assert l.risk_drawdown_alert("u1").severity==Severity.WARNING.value
    def test_T171_full_compliance_trail(self):
        l=AuditLogger(chain=AuditChain(secret="compliance-isolated"))
        l.billing_checkout("u1",tenant_id="t1",detail={"plan":"pro"})
        l.billing_payment_ok("u1",tenant_id="t1")
        l.license_issued("u1",tenant_id="t1")
        l.trade_open("u1",tenant_id="t1",detail={"ticket":1001})
        l.risk_drawdown_alert("u1",tenant_id="t1")
        l.risk_kill_switch_on("u1",tenant_id="t1",reason="D20%")
        assert len(l)==6 and l.verify_chain() is True
        assert len(l.query(severity=Severity.CRITICAL.value))>=1
        assert len(l.query(tenant_id="t1"))==6
    def test_T172_tamper_middle_of_chain(self):
        l=AuditLogger(chain=AuditChain(secret="tamper"))
        recs=[l.auth_login_ok(f"u{i}") for i in range(5)]
        assert l.verify_chain() is True
        object.__setattr__(recs[2],"event","auth.hacked")
        assert l.verify_chain() is False and recs[2].seq in l.detect_tamper()
