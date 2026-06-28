"""PHASE 35 - FINAL ACCEPTANCE CRITERIA - 224 tests T001-T224"""
import hashlib, hmac, sys, time, pytest
sys.path.insert(0, "/home/definable/phase35_final")
from backend.core.final_acceptance import (
    CriteriaID, CriteriaResult, Severity, ConfigGate, REQUIRED_ENV_VARS, FORBIDDEN_PLACEHOLDER_VALUES,
    MT5Credentials, MT5CredentialGate, LicenseStatus, LicenseContext, TradingAccessGate,
    EAFailClosedGate, HeartbeatRecord, HeartbeatMonitor, DeviceLimitEnforcer,
    DeliverableType, CUSTOMER_ALLOWED, CUSTOMER_BLOCKED, SourceProtectionGate,
    DashboardRole, CUSTOMER_VIEWS, ADMIN_VIEWS, DashboardSeparationGate, TenantDataGate,
    AdminControlPanel, DuplicateOrderGate, MT5Trade, MT5Reconciler, RiskContext, RiskFailClosedGate,
    KillSwitchState, KillSwitch, HardcodedSecretScanner, LicenseStorageChecker, WebhookSecurityGate,
    DockerDeploymentChecker, REQUIRED_DOCKER_FILES, REQUIRED_DEPLOYMENT_CONFIG,
    FinalAcceptanceAuditChain, FinalAcceptanceCriteria, AcceptanceReport, get_migration_sql,
)

def good_env(): return {k: f"prod-value-{i}" for i, k in enumerate(REQUIRED_ENV_VARS)}
def good_mt5_live(): return MT5Credentials(account_id=123456, password="Str0ngP@ss", server="broker.mt5.com", is_demo=False)
def good_license_ctx(expired=False, status=LicenseStatus.ACTIVE, device_id="dev1"):
    return LicenseContext("lic-001","user-001","tenant-001",status,device_id,["dev1"],2,time.time()+(100 if not expired else -100),True)
def full_scenario(**ov):
    base=dict(env=good_env(),mt5_creds=good_mt5_live(),live_mode=True,license_ctx=good_license_ctx(),ea_default_blocked=True,heartbeat_present=True,heartbeat_interval_seconds=300,license_revoke_supported=True,device_limit_server_side=True,source_protected=True,customer_deliverables=["dashboard","ex5_binary","documentation"],dashboard_separated=True,tenant_isolation=True,admin_full_control=True,dedup_active=True,mt5_reconciliation=True,risk_fail_closed=True,kill_switch_real=True,code_samples={"config.py":"jwt_secret = os.environ['JWT_SECRET']"},stored_licenses=["a"*64],webhook_verified=True,webhook_idempotent=True,core_tests_pass=True,test_count=4427,docs_synced=True,docker_files=REQUIRED_DOCKER_FILES,deploy_config={k:"set" for k in REQUIRED_DEPLOYMENT_CONFIG},staging_signoff=True,migration_verified=True,rollback_verified=True,tenant_id="system")
    base.update(ov); return base

class TestEnumsAndConstants:
    def test_T001_criteria_count(self): assert len(CriteriaID)==23
    def test_T002_criteria_c01_to_c23(self): [assert_in(f"C{i:02d}",[c.value for c in CriteriaID]) for i in range(1,24)]
    def test_T003_result_values(self): assert set(CriteriaResult)=={CriteriaResult.PASS,CriteriaResult.FAIL,CriteriaResult.WARNING}
    def test_T004_severity_critical(self): assert Severity.CRITICAL.value=="CRITICAL"
    def test_T005_required_env_vars(self): assert "JWT_SECRET" in REQUIRED_ENV_VARS and "DATABASE_URL" in REQUIRED_ENV_VARS
    def test_T006_forbidden_placeholders(self): assert "changeme" in FORBIDDEN_PLACEHOLDER_VALUES
    def test_T007_customer_allowed(self): assert DeliverableType.EX5_BINARY in CUSTOMER_ALLOWED and DeliverableType.DASHBOARD in CUSTOMER_ALLOWED
    def test_T008_customer_blocked(self): assert DeliverableType.MQL5_SOURCE in CUSTOMER_BLOCKED and DeliverableType.BACKEND_SRC in CUSTOMER_BLOCKED
    def test_T009_customer_views(self): assert "my_ea_status" in CUSTOMER_VIEWS and "download_ea" in CUSTOMER_VIEWS
    def test_T010_admin_views(self): assert "kill_switch_panel" in ADMIN_VIEWS and "all_users" in ADMIN_VIEWS
    def test_T011_no_view_overlap(self): assert len(ADMIN_VIEWS & CUSTOMER_VIEWS)==0
    def test_T012_docker_files(self): assert "Dockerfile" in REQUIRED_DOCKER_FILES and "docker-compose.yml" in REQUIRED_DOCKER_FILES
    def test_T013_deploy_config(self): assert "DOCKER_IMAGE_TAG" in REQUIRED_DEPLOYMENT_CONFIG
    def test_T014_license_statuses(self): assert LicenseStatus.ACTIVE.value=="active" and LicenseStatus.REVOKED.value=="revoked"
    def test_T015_dashboard_roles(self): assert set(DashboardRole)=={DashboardRole.CUSTOMER,DashboardRole.SUPPORT,DashboardRole.ADMIN}
    def test_T016_kill_switch_states(self): assert KillSwitchState.ACTIVE.value=="active" and KillSwitchState.TRIGGERED.value=="triggered"

def assert_in(a, b): assert a in b

class TestAuditChain:
    def test_T017_genesis_ok(self): assert FinalAcceptanceAuditChain().verify_chain() is True
    def test_T018_single_record_ok(self): c=FinalAcceptanceAuditChain(); c.record("r1","C01","PASS"); assert c.verify_chain() is True
    def test_T019_23_records_ok(self):
        c=FinalAcceptanceAuditChain()
        for i in range(1,24): c.record("r1",f"C{i:02d}","PASS")
        assert c.verify_chain() is True and len(c)==23
    def test_T020_hash_64_hex(self): c=FinalAcceptanceAuditChain(); e=c.record("r1","C01","PASS"); assert len(e.chain_hash)==64 and all(x in "0123456789abcdef" for x in e.chain_hash)
    def test_T021_tamper_detected(self): c=FinalAcceptanceAuditChain(); c.record("r1","C01","PASS"); c.record("r1","C02","PASS"); c._entries[0].result="FAIL"; assert c.verify_chain() is False
    def test_T022_wrong_secret_fails(self):
        c1=FinalAcceptanceAuditChain("A"); c1.record("r1","C01","PASS")
        c2=FinalAcceptanceAuditChain("B"); c2._entries=c1._entries; c2._prev_hash=c1._prev_hash; assert c2.verify_chain() is False
    def test_T023_len_grows(self): c=FinalAcceptanceAuditChain(); assert len(c)==0; c.record("r1","C01","PASS"); assert len(c)==1
    def test_T024_seq_increments(self): c=FinalAcceptanceAuditChain(); e1=c.record("r1","C01","PASS"); e2=c.record("r1","C02","PASS"); assert e1.seq==1 and e2.seq==2

class TestC01ConfigGate:
    def test_T025_all_vars_pass(self): g=ConfigGate(); ok,_=g.check(good_env()); assert ok is True
    def test_T026_missing_fails(self): g=ConfigGate(); env=good_env(); del env["JWT_SECRET"]; ok,issues=g.check(env); assert ok is False and any("JWT_SECRET" in i for i in issues)
    def test_T027_placeholder_fails(self): g=ConfigGate(); env=good_env(); env["JWT_SECRET"]="changeme"; ok,issues=g.check(env); assert ok is False and any("PLACEHOLDER" in i for i in issues)
    def test_T028_empty_fails(self): g=ConfigGate(); env=good_env(); env["DATABASE_URL"]=""; ok,_=g.check(env); assert ok is False
    def test_T029_assert_raises_on_bad(self):
        with pytest.raises(RuntimeError,match="Config gate FAIL"): ConfigGate().assert_ready({})
    def test_T030_assert_passes_on_good(self): ConfigGate().assert_ready(good_env())
    def test_T031_custom_vars(self): g=ConfigGate(["MY_VAR"]); ok,_=g.check({"MY_VAR":"real"}); assert ok is True
    def test_T032_all_missing_reported(self): g=ConfigGate(); ok,issues=g.check({}); assert ok is False and len(issues)==len(REQUIRED_ENV_VARS)

class TestC02MT5Gate:
    def test_T033_demo_blocked_in_live(self): g=MT5CredentialGate(); c=MT5Credentials(123,"pass","a.com",True); ok,r=g.validate(c,True); assert ok is False and "demo" in r.lower()
    def test_T034_demo_allowed_in_demo(self): g=MT5CredentialGate(); ok,_=g.validate(MT5Credentials(123,"pass","a.com",True),False); assert ok is True
    def test_T035_live_in_live_ok(self): g=MT5CredentialGate(); ok,r=g.validate(good_mt5_live(),True); assert ok is True and r=="OK"
    def test_T036_zero_account_blocked(self): g=MT5CredentialGate(); ok,_=g.validate(MT5Credentials(0,"pass","a.com",False),False); assert ok is False
    def test_T037_short_pass_blocked(self): g=MT5CredentialGate(); ok,_=g.validate(MT5Credentials(123,"ab","a.com",False),False); assert ok is False
    def test_T038_invalid_server_blocked(self): g=MT5CredentialGate(); ok,_=g.validate(MT5Credentials(123,"pass","invalid",False),False); assert ok is False
    def test_T039_assert_raises_on_demo(self):
        with pytest.raises(PermissionError): MT5CredentialGate().assert_live_ready(MT5Credentials(123,"pass","a.com",True))
    def test_T040_assert_passes_on_live(self): MT5CredentialGate().assert_live_ready(good_mt5_live())

class TestC03TradingGate:
    def test_T041_active_allowed(self): g=TradingAccessGate(); ok,_=g.check(good_license_ctx()); assert ok is True
    def test_T042_expired_blocked(self): g=TradingAccessGate(); ok,r=g.check(good_license_ctx(expired=True)); assert ok is False and "expired" in r.lower()
    def test_T043_revoked_blocked(self): g=TradingAccessGate(); ok,r=g.check(good_license_ctx(status=LicenseStatus.REVOKED)); assert ok is False and "revoked" in r.lower()
    def test_T044_suspended_blocked(self): g=TradingAccessGate(); ok,_=g.check(good_license_ctx(status=LicenseStatus.SUSPENDED)); assert ok is False
    def test_T045_no_sub_blocked(self): g=TradingAccessGate(); ctx=good_license_ctx(); ctx.subscription_active=False; ok,r=g.check(ctx); assert ok is False and "subscription" in r.lower()
    def test_T046_unregistered_blocked(self): g=TradingAccessGate(); ok,r=g.check(good_license_ctx(device_id="unknown")); assert ok is False and "device" in r.lower()
    def test_T047_limit_exceeded_blocked(self): g=TradingAccessGate(); ctx=good_license_ctx(); ctx.registered_devices=["d1","d2","d3"]; ctx.max_devices=2; ok,r=g.check(ctx); assert ok is False and "limit" in r.lower()
    def test_T048_assert_raises(self):
        with pytest.raises(PermissionError): TradingAccessGate().assert_can_trade(good_license_ctx(status=LicenseStatus.REVOKED))

class TestC04EAFailClosed:
    def test_T049_starts_blocked(self): assert EAFailClosedGate().is_blocked is True
    def test_T050_blocked_raises(self):
        with pytest.raises(PermissionError,match="FAIL-CLOSED"): EAFailClosedGate().assert_can_execute()
    def test_T051_authorized_allows(self): g=EAFailClosedGate(); g.authorize("ok"); g.assert_can_execute()
    def test_T052_exception_reblocks(self): g=EAFailClosedGate(); g.authorize("ok"); g.handle_exception(ValueError("err")); assert g.is_blocked is True
    def test_T053_block_blocks(self): g=EAFailClosedGate(); g.authorize("ok"); g.block("reason"); assert g.is_blocked is True
    def test_T054_block_log_grows(self): g=EAFailClosedGate(); g.authorize("ok"); g.block("r1"); g.authorize("ok"); g.block("r2"); assert len(g.block_log)==2
    def test_T055_exc_type_logged(self): g=EAFailClosedGate(); g.authorize("ok"); g.handle_exception(RuntimeError("t")); assert "RuntimeError" in g.block_log[-1]["reason"]
    def test_T056_reauthorize_after_block(self): g=EAFailClosedGate(); g.authorize("ok"); g.block("r"); g.authorize("cleared"); assert g.is_blocked is False

class TestC05Heartbeat:
    def test_T057_alive_ok(self): m=HeartbeatMonitor(300); m.record(HeartbeatRecord("d1","t1",time.time(),"v2","EU",True)); assert m.is_alive("d1") is True
    def test_T058_old_miss(self): m=HeartbeatMonitor(5); m.record(HeartbeatRecord("d1","t1",time.time()-100,"v2","EU",True)); assert m.is_alive("d1") is False
    def test_T059_unknown_miss(self): m=HeartbeatMonitor(); alive,age=m.check_device("x"); assert alive is False and age==float("inf")
    def test_T060_callback_fires(self):
        called=[]; m=HeartbeatMonitor(1); m.on_miss(lambda d,a: called.append(d))
        m.record(HeartbeatRecord("d1","t1",time.time()-100,"v2","EU",True))
        assert "d1" in m.scan_all_misses() and "d1" in called
    def test_T061_multi_tracked(self): m=HeartbeatMonitor(300); [m.record(HeartbeatRecord(f"d{i}","t1",time.time(),"v2","EU",True)) for i in range(5)]; [assert_(m.is_alive(f"d{i}")) for i in range(5)]
    def test_T062_age_returned(self): m=HeartbeatMonitor(300); m.record(HeartbeatRecord("d1","t1",time.time()-10,"v2","EU",True)); alive,age=m.check_device("d1"); assert alive is True and 9<=age<=12
    def test_T063_no_miss_when_alive(self): m=HeartbeatMonitor(300); m.record(HeartbeatRecord("d1","t1",time.time(),"v2","EU",True)); assert m.scan_all_misses()==[]
    def test_T064_record_fields(self): r=HeartbeatRecord("d1","t1",time.time(),"v2","EURUSD",True); assert r.device_id=="d1" and r.symbol=="EURUSD"

def assert_(x): assert x

class TestC07DeviceLimit:
    def test_T065_within_limit(self): e=DeviceLimitEnforcer(); e.set_limit("l1",2); ok,_=e.register("l1","d1"); assert ok is True
    def test_T066_exceed_blocked(self): e=DeviceLimitEnforcer(); e.set_limit("l1",1); e.register("l1","d1"); ok,r=e.register("l1","d2"); assert ok is False and "limit" in r
    def test_T067_duplicate_ok(self): e=DeviceLimitEnforcer(); e.set_limit("l1",2); e.register("l1","d1"); ok,s=e.register("l1","d1"); assert ok is True and s=="already_registered" and e.count("l1")==1
    def test_T068_revoke_frees_slot(self): e=DeviceLimitEnforcer(); e.set_limit("l1",1); e.register("l1","d1"); e.revoke_device("l1","d1"); ok,_=e.register("l1","d2"); assert ok is True
    def test_T069_is_registered(self): e=DeviceLimitEnforcer(); e.set_limit("l1",2); e.register("l1","d1"); assert e.is_registered("l1","d1") is True and e.is_registered("l1","d2") is False
    def test_T070_count_accurate(self): e=DeviceLimitEnforcer(); e.set_limit("l1",5); [e.register("l1",f"d{i}") for i in range(3)]; assert e.count("l1")==3
    def test_T071_isolated_licenses(self): e=DeviceLimitEnforcer(); e.set_limit("l1",1); e.set_limit("l2",1); e.register("l1","dA"); e.register("l2","dB"); assert e.count("l1")==1 and e.count("l2")==1
    def test_T072_unknown_zero(self): assert DeviceLimitEnforcer().count("unknown")==0

class TestC08C09SourceProtection:
    def test_T073_ex5_allowed(self): g=SourceProtectionGate(); ok,_=g.can_deliver(DeliverableType.EX5_BINARY); assert ok is True
    def test_T074_dashboard_allowed(self): g=SourceProtectionGate(); ok,_=g.can_deliver(DeliverableType.DASHBOARD); assert ok is True
    def test_T075_mql5_blocked(self): g=SourceProtectionGate(); ok,r=g.can_deliver(DeliverableType.MQL5_SOURCE); assert ok is False and "BLOCKED" in r
    def test_T076_backend_blocked(self): ok,_=SourceProtectionGate().can_deliver(DeliverableType.BACKEND_SRC); assert ok is False
    def test_T077_frontend_blocked(self): ok,_=SourceProtectionGate().can_deliver(DeliverableType.FRONTEND_SRC); assert ok is False
    def test_T078_db_creds_blocked(self): ok,_=SourceProtectionGate().can_deliver(DeliverableType.DATABASE_CREDS); assert ok is False
    def test_T079_admin_all(self): g=SourceProtectionGate(); [assert_(g.can_deliver(d,True)[0]) for d in DeliverableType]
    def test_T080_assert_raises(self):
        with pytest.raises(PermissionError): SourceProtectionGate().assert_delivery(DeliverableType.MQL5_SOURCE)

class TestC10DashboardSeparation:
    def test_T081_customer_own_views(self): g=DashboardSeparationGate(); [assert_(g.can_access_view(DashboardRole.CUSTOMER,v)[0]) for v in ["my_ea_status","my_license","download_ea"]]
    def test_T082_customer_blocked_admin(self): g=DashboardSeparationGate(); [assert_(not g.can_access_view(DashboardRole.CUSTOMER,v)[0]) for v in ["kill_switch_panel","all_users"]]
    def test_T083_admin_all(self): g=DashboardSeparationGate(); [assert_(g.can_access_view(DashboardRole.ADMIN,v)[0]) for v in list(CUSTOMER_VIEWS)+list(ADMIN_VIEWS)]
    def test_T084_support_customer_views(self): g=DashboardSeparationGate(); ok,_=g.can_access_view(DashboardRole.SUPPORT,"my_ea_status"); assert ok is True
    def test_T085_customer_no_kill_switch(self): ok,_=DashboardSeparationGate().can_access_view(DashboardRole.CUSTOMER,"kill_switch_panel"); assert ok is False
    def test_T086_customer_no_impersonation(self): ok,_=DashboardSeparationGate().can_access_view(DashboardRole.CUSTOMER,"impersonation"); assert ok is False
    def test_T087_admin_impersonation(self): ok,_=DashboardSeparationGate().can_access_view(DashboardRole.ADMIN,"impersonation"); assert ok is True
    def test_T088_unknown_view_blocked(self): ok,_=DashboardSeparationGate().can_access_view(DashboardRole.CUSTOMER,"xyz"); assert ok is False

class TestC11TenantIsolation:
    def test_T089_same_tenant_ok(self): ok,_=TenantDataGate().check_access("t1","t1","trades"); assert ok is True
    def test_T090_cross_blocked(self): ok,r=TenantDataGate().check_access("t1","t2","trades"); assert ok is False and "IDOR" in r
    def test_T091_violation_logged(self): g=TenantDataGate(); g.check_access("t1","t2","lic"); assert len(g.violations)==1
    def test_T092_multi_violations(self): g=TenantDataGate(); [g.check_access("att",f"v{i}","d") for i in range(5)]; assert len(g.violations)==5
    def test_T093_assert_raises(self):
        with pytest.raises(PermissionError,match="IDOR"): TenantDataGate().assert_own_data("t1","t2","orders")
    def test_T094_no_violation_own(self): g=TenantDataGate(); g.assert_own_data("t1","t1","orders"); assert len(g.violations)==0
    def test_T095_resource_type_in_reason(self): ok,r=TenantDataGate().check_access("t1","t2","payment_records"); assert "payment_records" in r
    def test_T096_violation_fields(self): g=TenantDataGate(); g.check_access("t1","t2","x"); v=g.violations[0]; assert "actor_tenant" in v and "ts" in v

class TestC12AdminControl:
    def test_T097_admin_all_caps(self): p=AdminControlPanel(); [assert_(p.check_capability(DashboardRole.ADMIN,c)) for c in AdminControlPanel.ADMIN_CAPABILITIES]
    def test_T098_customer_no_caps(self): p=AdminControlPanel(); [assert_(not p.check_capability(DashboardRole.CUSTOMER,c)) for c in AdminControlPanel.ADMIN_CAPABILITIES]
    def test_T099_admin_kill_switch(self): assert AdminControlPanel().check_capability(DashboardRole.ADMIN,"kill_switch") is True
    def test_T100_admin_impersonation(self): assert AdminControlPanel().check_capability(DashboardRole.ADMIN,"impersonation") is True
    def test_T101_admin_bulk_revoke(self): assert AdminControlPanel().check_capability(DashboardRole.ADMIN,"bulk_revoke") is True
    def test_T102_assert_raises_customer(self):
        with pytest.raises(PermissionError): AdminControlPanel().assert_capability(DashboardRole.CUSTOMER,"manage_users")
    def test_T103_unknown_cap_blocked(self): assert AdminControlPanel().check_capability(DashboardRole.ADMIN,"xyz") is False
    def test_T104_at_least_15_caps(self): assert len(AdminControlPanel.ADMIN_CAPABILITIES)>=15

class TestC13DuplicateOrders:
    def test_T105_first_allowed(self): ok,_=DuplicateOrderGate().check_and_record("EU","BUY",0.1,123); assert ok is True
    def test_T106_dup_blocked(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,123); ok,r=g.check_and_record("EU","BUY",0.1,123); assert ok is False and "DUPLICATE" in r
    def test_T107_diff_symbol_ok(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,123); ok,_=g.check_and_record("GB","BUY",0.1,123); assert ok is True
    def test_T108_diff_direction_ok(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,123); ok,_=g.check_and_record("EU","SELL",0.1,123); assert ok is True
    def test_T109_window_expiry(self): g=DuplicateOrderGate(0.01); g.check_and_record("EU","BUY",0.1,123); time.sleep(0.05); ok,_=g.check_and_record("EU","BUY",0.1,123); assert ok is True
    def test_T110_diff_account_ok(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,111); ok,_=g.check_and_record("EU","BUY",0.1,222); assert ok is True
    def test_T111_diff_volume_ok(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,123); ok,_=g.check_and_record("EU","BUY",0.2,123); assert ok is True
    def test_T112_reason_has_ago(self): g=DuplicateOrderGate(); g.check_and_record("EU","BUY",0.1,123); ok,r=g.check_and_record("EU","BUY",0.1,123); assert ok is False and "ago" in r

class TestC14Reconciliation:
    def mk(self, tickets): return [MT5Trade(t,"EU","BUY",0.1,1.1,time.time()) for t in tickets]
    def test_T113_clean(self): r=MT5Reconciler().reconcile(self.mk([1,2,3]),self.mk([1,2,3])); assert r.is_clean is True and r.matched==[1,2,3]
    def test_T114_missing_in_db(self): r=MT5Reconciler().reconcile(self.mk([1,2]),self.mk([1,2,3])); assert 3 in r.missing_in_db and r.is_clean is False
    def test_T115_missing_in_mt5(self): r=MT5Reconciler().reconcile(self.mk([1,2,3]),self.mk([1,2])); assert 3 in r.missing_in_mt5 and r.is_clean is False
    def test_T116_volume_discrepancy(self):
        r=MT5Reconciler().reconcile([MT5Trade(1,"EU","BUY",0.1,1.1,time.time())],[MT5Trade(1,"EU","BUY",0.5,1.1,time.time())])
        assert len(r.discrepancies)==1 and r.discrepancies[0]["field"]=="volume"
    def test_T117_empty_clean(self): assert MT5Reconciler().reconcile([],[]).is_clean is True
    def test_T118_100_match(self): trades=self.mk(range(100)); r=MT5Reconciler().reconcile(trades,trades); assert len(r.matched)==100 and r.is_clean is True

class TestC15RiskFailClosed:
    def gctx(self): return RiskContext(5.0,3,10000,9500)
    def test_T119_starts_blocked(self): assert RiskFailClosedGate().is_blocked is True
    def test_T120_safe_clears(self): g=RiskFailClosedGate(); ok,_=g.evaluate(self.gctx()); assert ok is True and g.is_blocked is False
    def test_T121_drawdown_blocks(self): ok,r=RiskFailClosedGate().evaluate(RiskContext(25,3,10000,7500)); assert ok is False and "DRAWDOWN" in r
    def test_T122_trades_blocks(self): ok,r=RiskFailClosedGate().evaluate(RiskContext(5,15,10000,9500)); assert ok is False and "TRADES" in r
    def test_T123_low_equity_blocks(self): ok,r=RiskFailClosedGate().evaluate(RiskContext(5,3,50,9500,min_equity=100)); assert ok is False and "EQUITY" in r
    def test_T124_zero_balance_blocks(self): ok,_=RiskFailClosedGate().evaluate(RiskContext(0,0,1000,0)); assert ok is False
    def test_T125_assert_raises(self):
        with pytest.raises(PermissionError,match="RISK FAIL-CLOSED"): RiskFailClosedGate().assert_safe(RiskContext(30,3,10000,7000))
    def test_T126_re_evaluate_updates(self): g=RiskFailClosedGate(); g.evaluate(self.gctx()); assert g.is_blocked is False; g.evaluate(RiskContext(25,3,10000,7500)); assert g.is_blocked is True

class TestC16KillSwitch:
    def test_T127_starts_active(self): ks=KillSwitch(); assert ks.state==KillSwitchState.ACTIVE and ks.is_triggered is False
    def test_T128_trigger_blocks(self): ks=KillSwitch(); ks.trigger("risk","drawdown");
        assert ks.is_triggered is True
    def test_T129_empty_reason_rejected(self):
        with pytest.raises(ValueError): KillSwitch().trigger("a","")
    def test_T130_callback_fires(self): fired=[]; ks=KillSwitch(); ks.on_trigger(lambda e: fired.append(e.reason)); ks.trigger("a","crash"); assert "crash" in fired
    def test_T131_reset_after_trigger(self): ks=KillSwitch(); ks.trigger("a","t"); ks.reset("a","ok"); assert ks.state==KillSwitchState.ACTIVE
    def test_T132_reset_needs_reason(self): ks=KillSwitch(); ks.trigger("a","t");
        with pytest.raises(ValueError): ks.reset("a","")
    def test_T133_reset_not_triggered_raises(self):
        with pytest.raises(RuntimeError): KillSwitch().reset("a","r")
    def test_T134_events_logged(self): ks=KillSwitch(); ks.trigger("a","r1"); assert len(ks.events)==1 and ks.events[0].reason=="r1"
    def test_T135_scope_recorded(self): ks=KillSwitch(); ks.trigger("a","t",scope="tenant:t1"); assert ks.events[0].scope=="tenant:t1"
    def test_T136_active_allows(self): KillSwitch().assert_ea_allowed()

class TestC17Secrets:
    def test_T137_env_var_safe(self): assert HardcodedSecretScanner().scan_text("jwt_secret = os.environ['JWT_SECRET']")==[]
    def test_T138_getenv_safe(self): assert HardcodedSecretScanner().scan_text("secret = os.getenv('X')")==[]
    def test_T139_hardcoded_detected(self): f=HardcodedSecretScanner().scan_text('password="supersecret123"'); assert len(f)==1 and f[0]["severity"]=="CRITICAL"
    def test_T140_comment_ignored(self): assert HardcodedSecretScanner().scan_text('# password="example"')==[]
    def test_T141_empty_not_flagged(self): assert HardcodedSecretScanner().scan_text('password=""')==[]
    def test_T142_settings_safe(self): assert HardcodedSecretScanner().scan_text("api_key = settings.KEY")==[]
    def test_T143_placeholder_env_detected(self): bad=HardcodedSecretScanner().scan_env({"K":"placeholder"}); assert len(bad)>=1
    def test_T144_clean_env_ok(self): assert HardcodedSecretScanner().scan_env({"K":"real-prod-abc123"})==[]

class TestC18LicenseStorage:
    def test_T145_sha256_recognized(self): assert LicenseStorageChecker().is_hashed("a"*64) is True
    def test_T146_sha512_recognized(self): assert LicenseStorageChecker().is_hashed("b"*128) is True
    def test_T147_raw_detected(self): assert LicenseStorageChecker().looks_like_raw_key("BOT12-ABCD-1234-EFGH") is True
    def test_T148_hash_not_raw(self): assert LicenseStorageChecker().looks_like_raw_key("a"*64) is False
    def test_T149_hash_returns_64hex(self): h=LicenseStorageChecker().hash_license("KEY"); assert len(h)==64 and all(c in "0123456789abcdef" for c in h)
    def test_T150_assert_raises_on_raw(self):
        with pytest.raises(ValueError,match="raw format"): LicenseStorageChecker().assert_not_raw("BOT12-ABCD-1234-EFGH")
    def test_T151_assert_passes_on_hash(self): LicenseStorageChecker().assert_not_raw("a"*64)
    def test_T152_deterministic(self): c=LicenseStorageChecker(); assert c.hash_license("KEY")==c.hash_license("KEY")

class TestC19Webhook:
    def _g(self): return WebhookSecurityGate("wh-secret")
    def _s(self, p, sec="wh-secret"): return hmac.new(sec.encode(),p,hashlib.sha256).hexdigest()
    def test_T153_valid_sig_accepted(self): g=self._g(); p=b'{"e":"ok"}'; ok,_=g.verify_signature(p,self._s(p)); assert ok is True
    def test_T154_invalid_sig_rejected(self): ok,r=self._g().verify_signature(b"p","bad"*16); assert ok is False and "INVALID_SIGNATURE" in r
    def test_T155_sha256_prefix_stripped(self): g=self._g(); p=b"test"; ok,_=g.verify_signature(p,"sha256="+self._s(p)); assert ok is True
    def test_T156_old_ts_replay_blocked(self): g=self._g(); p=b"t"; ok,r=g.verify_signature(p,self._s(p),str(time.time()-400)); assert ok is False and "REPLAY" in r
    def test_T157_fresh_ts_ok(self): g=self._g(); p=b"t"; ok,_=g.verify_signature(p,self._s(p),str(time.time())); assert ok is True
    def test_T158_idempotent_returns_cached(self): g=self._g(); g.record_processed("e1","h1",{"ok":1}); ok,r=g.check_idempotency("e1","h1"); assert ok is True and r=={"ok":1}
    def test_T159_conflict_detected(self): g=self._g(); g.record_processed("e1","h1",{}); ok,r=g.check_idempotency("e1","h2"); assert ok is False and "CONFLICT" in str(r)
    def test_T160_new_event_none(self): ok,r=self._g().check_idempotency("new","h"); assert ok is True and r is None

class TestC22Docker:
    def test_T161_all_files_pass(self): ok,_=DockerDeploymentChecker().check_files(REQUIRED_DOCKER_FILES); assert ok is True
    def test_T162_missing_fails(self): ok,m=DockerDeploymentChecker().check_files(["x"]); assert ok is False and "Dockerfile" in m
    def test_T163_all_config_pass(self): ok,_=DockerDeploymentChecker().check_config({k:"v" for k in REQUIRED_DEPLOYMENT_CONFIG}); assert ok is True
    def test_T164_dockerfile_valid(self): df=DockerDeploymentChecker().generate_dockerfile_template(); assert "FROM python:3.11-slim" in df and "HEALTHCHECK" in df and "USER nobody" in df
    def test_T165_compose_valid(self): dc=DockerDeploymentChecker().generate_compose_template(); assert "healthcheck" in dc and "restart: unless-stopped" in dc
    def test_T166_missing_config_reported(self): ok,m=DockerDeploymentChecker().check_config({}); assert ok is False and len(m)==len(REQUIRED_DEPLOYMENT_CONFIG)

class TestSQLMigration:
    def test_T167_not_empty(self): assert len(get_migration_sql())>100
    def test_T168_acceptance_runs(self): assert "acceptance_runs" in get_migration_sql()
    def test_T169_findings_table(self): assert "acceptance_findings" in get_migration_sql()
    def test_T170_gng_table(self): assert "go_nogo_decisions" in get_migration_sql()
    def test_T171_audit_log(self): assert "final_acceptance_audit_log" in get_migration_sql()
    def test_T172_remaining_risks(self): assert "remaining_risks" in get_migration_sql()
    def test_T173_deploy_checklist(self): assert "deployment_checklist" in get_migration_sql()
    def test_T174_rls(self): assert "ROW LEVEL SECURITY" in get_migration_sql()
    def test_T175_immutable_trigger(self): assert "immutable" in get_migration_sql().lower()
    def test_T176_chain_hash(self): assert "CHAR(64)" in get_migration_sql() or "chain_hash" in get_migration_sql()
    def test_T177_criteria_ids(self): sql=get_migration_sql(); [assert_in(f"'C{i:02d}'",sql) for i in range(1,24)]
    def test_T178_views(self): assert get_migration_sql().count("VIEW")>=2
    def test_T179_risks_seeded(self): sql=get_migration_sql(); assert "R00" in sql or "risk_id" in sql
    def test_T180_env_seeded(self): sql=get_migration_sql(); assert "staging" in sql and "production" in sql

class TestEngine:
    def test_T181_builds(self): assert FinalAcceptanceCriteria() is not None
    def test_T182_full_pass_go(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert r.go_nogo=="GO" and r.overall==CriteriaResult.PASS
    def test_T183_23_findings(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert len(r.findings)==23
    def test_T184_pass_23(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert r.pass_count==23 and r.fail_count==0
    def test_T185_chain_ok(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert r.audit_chain_ok is True
    def test_T186_23_audit_entries(self): e=FinalAcceptanceCriteria(); e.run(full_scenario()); assert len(e.audit)==23
    def test_T187_bad_env_c01_fail(self): r=FinalAcceptanceCriteria().run(full_scenario(env={})); c01=next(f for f in r.findings if f.criteria_id==CriteriaID.C01_NO_START_WITHOUT_CONFIG); assert c01.result==CriteriaResult.FAIL
    def test_T188_demo_live_c02_fail(self): r=FinalAcceptanceCriteria().run(full_scenario(mt5_creds=MT5Credentials(123,"pass","a.com",True),live_mode=True)); c02=next(f for f in r.findings if f.criteria_id==CriteriaID.C02_NO_LIVE_WITHOUT_MT5_CREDS); assert c02.result==CriteriaResult.FAIL
    def test_T189_no_fail_closed_nogo(self): r=FinalAcceptanceCriteria().run(full_scenario(ea_default_blocked=False)); assert r.go_nogo=="NO_GO"
    def test_T190_source_exposed_nogo(self): r=FinalAcceptanceCriteria().run(full_scenario(source_protected=False)); assert r.go_nogo=="NO_GO"
    def test_T191_hardcoded_nogo(self): r=FinalAcceptanceCriteria().run(full_scenario(code_samples={"c.py":'secret="hardcoded"'})); assert r.go_nogo=="NO_GO"
    def test_T192_raw_license_fail(self): r=FinalAcceptanceCriteria().run(full_scenario(stored_licenses=["BOT12-ABCD-1234-EFGH"])); c18=next(f for f in r.findings if f.criteria_id==CriteriaID.C18_LICENSE_NOT_RAW_STORED); assert c18.result==CriteriaResult.FAIL
    def test_T193_webhook_not_secure_nogo(self): r=FinalAcceptanceCriteria().run(full_scenario(webhook_verified=False)); assert r.go_nogo=="NO_GO"
    def test_T194_tests_fail_c20_fail(self): r=FinalAcceptanceCriteria().run(full_scenario(core_tests_pass=False)); c20=next(f for f in r.findings if f.criteria_id==CriteriaID.C20_CORE_TESTS_PASS); assert c20.result==CriteriaResult.FAIL
    def test_T195_docs_unsync_warning(self): r=FinalAcceptanceCriteria().run(full_scenario(docs_synced=False)); c21=next(f for f in r.findings if f.criteria_id==CriteriaID.C21_DOCS_SYNC_WITH_CODE); assert c21.severity in (Severity.MEDIUM,Severity.INFO) or c21.result==CriteriaResult.WARNING
    def test_T196_to_dict_serializable(self):
        import json; d=FinalAcceptanceCriteria().run(full_scenario()).to_dict(); json.dumps(d); assert d["go_nogo"]=="GO" and d["pass_count"]==23
    def test_T197_two_runs_independent(self): e=FinalAcceptanceCriteria(); r1=e.run(full_scenario()); r2=e.run(full_scenario()); assert r1.run_id!=r2.run_id and r1.go_nogo==r2.go_nogo=="GO"
    def test_T198_run_id_uuid(self): import uuid; uuid.UUID(FinalAcceptanceCriteria().run(full_scenario()).run_id)
    def test_T199_all_ids_covered(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert {f.criteria_id for f in r.findings}==set(CriteriaID)
    def test_T200_recommendation_nonempty(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert len(r.recommendation)>10

class TestIntegrationFlows:
    def test_T201_revoked_no_trade(self): g=TradingAccessGate(); ok,_=g.check(good_license_ctx(status=LicenseStatus.REVOKED)); assert ok is False
    def test_T202_ea_exception_failclosed(self): ea=EAFailClosedGate(); ea.authorize("ok"); ea.handle_exception(ConnectionError("lost")); assert ea.is_blocked is True
    def test_T203_ks_plus_ea(self): ks=KillSwitch(); ea=EAFailClosedGate(); ea.authorize("ok"); ks.trigger("risk","drawdown"); ea.block(f"ks:{ks.events[0].reason}"); assert ks.is_triggered and ea.is_blocked
    def test_T204_dup_order_blocked(self): g=DuplicateOrderGate(30); g.check_and_record("EU","BUY",0.1,123); ok,r=g.check_and_record("EU","BUY",0.1,123); assert ok is False and "DUPLICATE" in r
    def test_T205_webhook_replay_blocked(self): g=WebhookSecurityGate("s"); p=b"t"; sig=hmac.new(b"s",p,hashlib.sha256).hexdigest(); ok2,r=g.verify_signature(p,sig,str(time.time()-400)); assert ok2 is False and "REPLAY" in r
    def test_T206_idor_blocked(self): ok,r=TenantDataGate().check_access("att","vic","trades"); assert ok is False and "IDOR" in r
    def test_T207_device_limit_bypass_blocked(self): e=DeviceLimitEnforcer(); e.set_limit("l",2); e.register("l","d1"); e.register("l","d2"); ok,r=e.register("l","d3"); assert ok is False and "limit" in r
    def test_T208_phantom_trade_detected(self): r=MT5Reconciler().reconcile([MT5Trade(1,"EU","BUY",0.1,1.1,time.time()),MT5Trade(999,"GB","SELL",0.5,1.3,time.time())],[MT5Trade(1,"EU","BUY",0.1,1.1,time.time())]); assert 999 in r.missing_in_mt5 and r.is_clean is False

class TestFinalGate:
    def test_T209_all_23_for_go(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert r.pass_count==23 and r.fail_count==0 and r.go_nogo=="GO"
    def test_T210_critical_fail_nogo(self): r=FinalAcceptanceCriteria().run(full_scenario(ea_default_blocked=False)); assert r.go_nogo=="NO_GO" and any(f.severity==Severity.CRITICAL and f.result==CriteriaResult.FAIL for f in r.findings)
    def test_T211_evidence_in_findings(self): [assert_(isinstance(f.evidence,dict)) for f in FinalAcceptanceCriteria().run(full_scenario()).findings]
    def test_T212_chain_survives_two_runs(self): e=FinalAcceptanceCriteria(); e.run(full_scenario()); e.run(full_scenario()); assert e.audit.verify_chain() is True and len(e.audit)==46
    def test_T213_run_id_unique(self): e=FinalAcceptanceCriteria(); ids={e.run(full_scenario()).run_id for _ in range(5)}; assert len(ids)==5
    def test_T214_ts_present(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert r.ts>0 and abs(r.ts-time.time())<5
    def test_T215_all_components_init(self): e=FinalAcceptanceCriteria(); assert all(hasattr(e,x) for x in ["config_gate","mt5_gate","trading_gate","ea_gate","heartbeat","device_enforcer","source_gate","dashboard_gate","data_gate","admin_panel","dedup_gate","reconciler","risk_gate","kill_switch","secret_scanner","license_checker","docker_checker"])
    def test_T216_to_dict_keys(self): d=FinalAcceptanceCriteria().run(full_scenario()).to_dict(); [assert_in(k,d) for k in ["run_id","tenant_id","ts","overall","go_nogo","pass_count","fail_count","warn_count","audit_chain_ok","recommendation","findings"]]
    def test_T217_all_criteria_in_findings(self): r=FinalAcceptanceCriteria().run(full_scenario()); assert {f.criteria_id for f in r.findings}==set(CriteriaID)
    def test_T218_nogo_mentions_criteria(self): r=FinalAcceptanceCriteria().run(full_scenario(ea_default_blocked=False,risk_fail_closed=False)); assert "C04" in r.recommendation or "C15" in r.recommendation
    def test_T219_webhook_idempotent(self): g=WebhookSecurityGate("k"); g.record_processed("e","h",{"charged":True}); ok,c=g.check_idempotency("e","h"); assert ok is True and c=={"charged":True}
    def test_T220_license_never_raw(self):
        c=LicenseStorageChecker(); raw=["BOT12-AAAA-BBBB-CCCC","BOT12-1234-5678-XXXX"]
        hashed=[c.hash_license(k) for k in raw]
        [assert_(c.is_hashed(h) and not c.looks_like_raw_key(h)) for h in hashed]
        [pytest.raises(ValueError, c.assert_not_raw, r) for r in raw]
    def test_T221_placeholder_jwt_blocked(self): g=ConfigGate(); env=good_env(); env["JWT_SECRET"]="changeme"; ok,issues=g.check(env); assert ok is False and any("JWT_SECRET" in i for i in issues)
    def test_T222_any_exception_failclosed(self):
        for exc in [ValueError,RuntimeError,ConnectionError,KeyError,PermissionError]:
            ea=EAFailClosedGate(); ea.authorize("ok"); ea.handle_exception(exc("t")); assert ea.is_blocked is True
    def test_T223_risk_blocked_on_init(self): g=RiskFailClosedGate(); assert g.is_blocked is True
    def test_T224_final_go_nogo_production_ready(self):
        """T224 - FINAL ACCEPTANCE TEST - All 23 criteria must PASS for GO decision."""
        engine=FinalAcceptanceCriteria(secret="bot12-production-acceptance-v35")
        report=engine.run(full_scenario(tenant_id="bot12-production",test_count=4427))
        assert report.pass_count==23, f"Expected 23 PASS, got {report.pass_count}"
        assert report.fail_count==0, f"Expected 0 FAIL, got {report.fail_count}"
        assert report.overall==CriteriaResult.PASS
        assert report.go_nogo=="GO", f"Expected GO, got {report.go_nogo}"
        assert report.audit_chain_ok is True, "Audit chain FAIL"
        assert engine.audit.verify_chain() is True
        assert {f.criteria_id for f in report.findings}==set(CriteriaID)
        d=report.to_dict(); assert d["go_nogo"]=="GO" and d["pass_count"]==23 and d["audit_chain_ok"] is True
        assert "Approved" in report.recommendation or "PASS" in report.recommendation
