"""
PHASE 24 - Feature Flags & Safe Rollout Control
Test Suite: 192 tests across 12 classes
"""
import sys, os, time, threading, hashlib, hmac, json
sys.path.insert(0, '/home/definable/phase24')

import pytest
from backend.core.feature_flags import (
    FlagKey, FlagScope, RolloutStrategy, ReleaseRing, PlanTier,
    FlagConfig, KillOverride, FlagAuditRecord, EvalContext, EvalResult,
    RolloutStep, FlagAuditChain, FlagEvaluator, AuditedFlagStore,
    GradualRolloutManager, PLAN_ORDER, RING_ORDER, FLAG_MIN_PLAN,
    MIGRATION_SQL, _stable_hash, get_store, get_rollout, is_enabled,
)


@pytest.fixture
def chain():
    return FlagAuditChain(secret="test-secret-p24")

@pytest.fixture
def store():
    c = FlagAuditChain(secret="test-secret-p24")
    return AuditedFlagStore(audit_chain=c)

@pytest.fixture
def rollout(store):
    return GradualRolloutManager(store)

@pytest.fixture
def evaluator():
    return FlagEvaluator()

@pytest.fixture
def basic_flag():
    return FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True, strategy=RolloutStrategy.NONE)

@pytest.fixture
def ctx():
    return EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.PRO, ring=ReleaseRing.BETA)


class TestFlagKeyEnum:
    def test_T001_total_32_flags(self):
        assert len(FlagKey) == 32
    def test_T002_risk_domain_8_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("risk.")]) == 8
    def test_T003_license_domain_6_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("license.")]) == 6
    def test_T004_billing_domain_6_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("billing.")]) == 6
    def test_T005_ea_domain_4_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("ea.")]) == 4
    def test_T006_dashboard_domain_4_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("dashboard.")]) == 4
    def test_T007_platform_domain_4_flags(self):
        assert len([k for k in FlagKey if k.value.startswith("platform.")]) == 4
    def test_T008_all_keys_have_dot_namespace(self):
        for k in FlagKey:
            assert "." in k.value
    def test_T009_kill_switch_v2_exists(self):
        assert FlagKey.RISK_KILL_SWITCH_V2.value == "risk.kill_switch_v2"
    def test_T010_billing_crypto_pay_exists(self):
        assert FlagKey.BILLING_CRYPTO_PAY.value == "billing.crypto_pay"
    def test_T011_platform_sso_exists(self):
        assert FlagKey.PLATFORM_SSO.value == "platform.sso"
    def test_T012_ea_remote_kill_exists(self):
        assert FlagKey.EA_REMOTE_KILL.value == "ea.remote_kill"
    def test_T013_all_values_unique(self):
        values = [k.value for k in FlagKey]
        assert len(values) == len(set(values))
    def test_T014_rollout_strategy_6_values(self):
        assert len(RolloutStrategy) == 6
    def test_T015_flag_scope_6_values(self):
        assert len(FlagScope) == 6
    def test_T016_release_ring_4_values(self):
        assert len(ReleaseRing) == 4


class TestPlanAndRingGates:
    def test_T017_plan_order_5_tiers(self):
        assert len(PLAN_ORDER) == 5
    def test_T018_trial_lowest_plan(self):
        assert PLAN_ORDER.index(PlanTier.TRIAL) == 0
    def test_T019_admin_highest_plan(self):
        assert PLAN_ORDER.index(PlanTier.ADMIN) == 4
    def test_T020_ring_order_4_rings(self):
        assert len(RING_ORDER) == 4
    def test_T021_internal_lowest_ring(self):
        assert RING_ORDER.index(ReleaseRing.INTERNAL) == 0
    def test_T022_ga_highest_ring(self):
        assert RING_ORDER.index(ReleaseRing.GA) == 3
    def test_T023_flag_min_plan_not_empty(self):
        assert len(FLAG_MIN_PLAN) >= 5
    def test_T024_crypto_pay_requires_pro(self, evaluator):
        cfg = FlagConfig(key=FlagKey.BILLING_CRYPTO_PAY, enabled=True)
        ctx = EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.BASIC)
        result = evaluator.evaluate(FlagKey.BILLING_CRYPTO_PAY, ctx, cfg, [])
        assert not result.enabled and "plan_gate" in result.reason
    def test_T025_crypto_pay_allowed_for_pro(self, evaluator):
        cfg = FlagConfig(key=FlagKey.BILLING_CRYPTO_PAY, enabled=True)
        ctx = EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.PRO)
        assert evaluator.evaluate(FlagKey.BILLING_CRYPTO_PAY, ctx, cfg, []).enabled
    def test_T026_sso_requires_vip(self, evaluator):
        cfg = FlagConfig(key=FlagKey.PLATFORM_SSO, enabled=True)
        ctx = EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.PRO)
        assert not evaluator.evaluate(FlagKey.PLATFORM_SSO, ctx, cfg, []).enabled
    def test_T027_sso_allowed_for_vip(self, evaluator):
        cfg = FlagConfig(key=FlagKey.PLATFORM_SSO, enabled=True)
        ctx = EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.VIP)
        assert evaluator.evaluate(FlagKey.PLATFORM_SSO, ctx, cfg, []).enabled
    def test_T028_ring_internal_sees_flag(self, evaluator):
        cfg = FlagConfig(key=FlagKey.EA_CLOUD_CONFIG, enabled=True, strategy=RolloutStrategy.RING, min_ring=ReleaseRing.INTERNAL)
        ctx = EvalContext(user_id="u1", tenant_id="t1", ring=ReleaseRing.INTERNAL)
        assert evaluator.evaluate(FlagKey.EA_CLOUD_CONFIG, ctx, cfg, []).enabled
    def test_T029_ring_ga_blocked_for_internal_only(self, evaluator):
        cfg = FlagConfig(key=FlagKey.EA_CLOUD_CONFIG, enabled=True, strategy=RolloutStrategy.RING, min_ring=ReleaseRing.INTERNAL)
        ctx = EvalContext(user_id="u1", tenant_id="t1", ring=ReleaseRing.GA)
        assert not evaluator.evaluate(FlagKey.EA_CLOUD_CONFIG, ctx, cfg, []).enabled
    def test_T030_ring_beta_sees_beta_flag(self, evaluator):
        cfg = FlagConfig(key=FlagKey.DASHBOARD_AI_INSIGHTS, enabled=True, strategy=RolloutStrategy.RING, min_ring=ReleaseRing.BETA)
        ctx = EvalContext(user_id="u1", tenant_id="t1", ring=ReleaseRing.BETA, plan=PlanTier.PRO)
        assert evaluator.evaluate(FlagKey.DASHBOARD_AI_INSIGHTS, ctx, cfg, []).enabled
    def test_T031_no_plan_in_ctx_skips_plan_gate(self, evaluator):
        cfg = FlagConfig(key=FlagKey.BILLING_CRYPTO_PAY, enabled=True)
        ctx = EvalContext(user_id="u1", tenant_id="t1", plan=None)
        assert evaluator.evaluate(FlagKey.BILLING_CRYPTO_PAY, ctx, cfg, []).enabled
    def test_T032_admin_plan_sees_all_flags(self, evaluator):
        for key in FLAG_MIN_PLAN:
            cfg = FlagConfig(key=key, enabled=True)
            ctx = EvalContext(user_id="u1", tenant_id="t1", plan=PlanTier.ADMIN)
            assert evaluator.evaluate(key, ctx, cfg, []).enabled


class TestKillOverride:
    def test_T033_kill_requires_reason(self, store):
        with pytest.raises(ValueError, match="reason"):
            store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T034_kill_blocks_evaluation(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "emergency stop")
        result = store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx)
        assert not result.enabled and result.scope == FlagScope.KILL_OVERRIDE
    def test_T035_kill_reason_in_result(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "fraud detected")
        assert "fraud detected" in store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).reason
    def test_T036_kill_reset_re_enables(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "test kill")
        store.reset_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "resolved")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).enabled
    def test_T037_reset_kill_requires_reason(self, store):
        with pytest.raises(ValueError):
            store.reset_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T038_kill_ttl_expires(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "short", ttl_seconds=0.01)
        time.sleep(0.05)
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).enabled
    def test_T039_tenant_scoped_kill(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "block", tenant_id="t_bad")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1", tenant_id="t_good")).enabled
        assert not store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u2", tenant_id="t_bad")).enabled
    def test_T040_global_kill_blocks_all(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "global", tenant_id=None)
        for tid in ["t1","t2","t3"]:
            assert not store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1", tenant_id=tid)).enabled
    def test_T041_kill_override_scope(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.EA_REMOTE_KILL, enabled=True), "admin", "init")
        store.activate_kill(FlagKey.EA_REMOTE_KILL, "admin", "safety")
        assert store.evaluate(FlagKey.EA_REMOTE_KILL, ctx).scope == FlagScope.KILL_OVERRIDE
    def test_T042_kill_audited(self, store):
        store.activate_kill(FlagKey.BILLING_STRIPE_V2, "admin", "billing issue")
        assert any(r.flag_key == FlagKey.BILLING_STRIPE_V2.value for r in store.audit.query(action="kill"))
    def test_T043_kill_reset_audited(self, store):
        store.activate_kill(FlagKey.BILLING_STRIPE_V2, "admin", "test")
        store.reset_kill(FlagKey.BILLING_STRIPE_V2, "admin", "resolved")
        assert any(r.flag_key == FlagKey.BILLING_STRIPE_V2.value for r in store.audit.query(action="kill_reset"))
    def test_T044_active_kills_list(self, store):
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "k1")
        store.activate_kill(FlagKey.EA_REMOTE_KILL, "admin", "k2")
        keys = [k.flag_key for k in store.active_kills()]
        assert FlagKey.RISK_KILL_SWITCH_V2 in keys and FlagKey.EA_REMOTE_KILL in keys
    def test_T045_active_kills_filtered(self, store):
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "k1")
        store.activate_kill(FlagKey.EA_REMOTE_KILL, "admin", "k2")
        kills = store.active_kills(FlagKey.RISK_KILL_SWITCH_V2)
        assert len(kills) == 1 and kills[0].flag_key == FlagKey.RISK_KILL_SWITCH_V2
    def test_T046_kill_override_scope_constant(self):
        assert FlagScope.KILL_OVERRIDE in list(FlagScope)
    def test_T047_ko_not_expired_no_ttl(self):
        ko = KillOverride(flag_key=FlagKey.RISK_KILL_SWITCH_V2, reason="r", actor_id="a", tenant_id=None)
        assert not ko.is_expired()
    def test_T048_ko_expired_past_ttl(self):
        ko = KillOverride(flag_key=FlagKey.RISK_KILL_SWITCH_V2, reason="r", actor_id="a",
                          tenant_id=None, activated_at=time.time()-100, ttl_seconds=10)
        assert ko.is_expired()


class TestFlagAuditChain:
    def test_T049_genesis_64_chars(self, chain):
        assert len(chain._genesis()) == 64
    def test_T050_record_64_char_hash(self, chain):
        assert len(chain.record("k","create","admin","init",{}).chain_hash) == 64
    def test_T051_reason_mandatory(self, chain):
        with pytest.raises(ValueError, match="reason"):
            chain.record("k","create","admin","",{})
    def test_T052_reason_whitespace_rejected(self, chain):
        with pytest.raises(ValueError):
            chain.record("k","create","admin","   ",{})
    def test_T053_verify_empty_chain(self, chain):
        assert chain.verify_chain()
    def test_T054_verify_after_records(self, chain):
        for i in range(10):
            chain.record("k","create",f"u{i}",f"r{i}",{"i":i})
        assert chain.verify_chain()
    def test_T055_tamper_detected(self, chain):
        chain.record("k","create","admin","init",{})
        chain.record("k","update","admin","change",{})
        recs = list(chain._records)
        recs[0].__dict__["chain_hash"] = "a"*64
        chain._records.clear(); chain._records.extend(recs)
        assert not chain.verify_chain()
    def test_T056_wrong_secret_fails(self):
        c1 = FlagAuditChain(secret="secret-A")
        c2 = FlagAuditChain(secret="secret-B")
        c1.record("k","create","admin","reason",{})
        rec = list(c1._records)[0]
        c2._records.append(rec)
        assert not c2.verify_chain()
    def test_T057_seq_starts_at_1(self, chain):
        assert chain.record("k","create","admin","first",{}).seq == 1
    def test_T058_seq_increments(self, chain):
        r1 = chain.record("k","create","admin","r1",{})
        r2 = chain.record("k","update","admin","r2",{})
        assert r2.seq == r1.seq + 1
    def test_T059_total_count(self, chain):
        for i in range(5): chain.record("k","create",f"u{i}",f"r{i}",{})
        assert chain.total == 5
    def test_T060_query_by_flag_key(self, chain):
        chain.record("risk.ks","create","admin","r1",{})
        chain.record("ea.kill","create","admin","r2",{})
        assert all(r.flag_key == "risk.ks" for r in chain.query(flag_key="risk.ks"))
    def test_T061_query_by_actor(self, chain):
        chain.record("k","create","alice","r1",{})
        chain.record("k","create","bob","r2",{})
        assert all(r.actor_id == "alice" for r in chain.query(actor_id="alice"))
    def test_T062_query_by_action(self, chain):
        chain.record("k","create","admin","r1",{})
        chain.record("k","kill","admin","r2",{})
        assert all(r.action == "kill" for r in chain.query(action="kill"))
    def test_T063_query_most_recent_first(self, chain):
        for i in range(5): chain.record("k","create","admin",f"r{i}",{"i":i})
        results = chain.query(limit=3)
        assert results[0].seq > results[-1].seq
    def test_T064_thread_safe_concurrent(self, chain):
        errors = []
        def writer(i):
            try: chain.record("k","create",f"u{i}",f"r {i}",{})
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors and len(set(r.seq for r in chain._records)) == 50


class TestAuditedFlagStore:
    def test_T065_set_flag_requires_reason(self, store, basic_flag):
        with pytest.raises(ValueError):
            store.set_flag(basic_flag, "admin", "")
    def test_T066_set_flag_stores_config(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "init")
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2) is not None
    def test_T067_set_flag_creates_audit(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "init test")
        assert len(store.audit.query(flag_key=FlagKey.RISK_KILL_SWITCH_V2.value)) >= 1
    def test_T068_update_action(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "create")
        basic_flag.rollout_pct = 50.0
        store.set_flag(basic_flag, "admin", "update pct")
        assert len(store.audit.query(flag_key=FlagKey.RISK_KILL_SWITCH_V2.value, action="update")) >= 1
    def test_T069_remove_requires_reason(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "init")
        with pytest.raises(ValueError):
            store.remove_flag(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T070_remove_deletes_config(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "init")
        store.remove_flag(FlagKey.RISK_KILL_SWITCH_V2, "admin", "cleanup")
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2) is None
    def test_T071_remove_audited(self, store, basic_flag):
        store.set_flag(basic_flag, "admin", "init")
        store.remove_flag(FlagKey.RISK_KILL_SWITCH_V2, "admin", "teardown")
        assert len(store.audit.query(action="remove")) >= 1
    def test_T072_list_flags_empty(self, store):
        assert store.list_flags() == []
    def test_T073_list_flags_returns_all(self, store):
        for key in [FlagKey.RISK_KILL_SWITCH_V2, FlagKey.EA_REMOTE_KILL, FlagKey.BILLING_STRIPE_V2]:
            store.set_flag(FlagConfig(key=key, enabled=True), "admin", "init")
        assert len(store.list_flags()) == 3
    def test_T074_get_nonexistent_none(self, store):
        assert store.get_flag(FlagKey.PLATFORM_GRAPHQL) is None
    def test_T075_evaluate_not_found(self, store, ctx):
        result = store.evaluate(FlagKey.PLATFORM_GRAPHQL, ctx)
        assert not result.enabled and result.reason == "flag_not_found"
    def test_T076_evaluate_disabled(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.PLATFORM_GRAPHQL, enabled=False), "admin", "disabled")
        assert not store.evaluate(FlagKey.PLATFORM_GRAPHQL, ctx).enabled
    def test_T077_is_enabled_convenience(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        assert store.is_enabled(FlagKey.RISK_KILL_SWITCH_V2, ctx)
    def test_T078_hook_called(self, store, ctx):
        called = []
        store.add_hook(lambda k,r,c: called.append((k,r.enabled)))
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx)
        assert len(called) == 1
    def test_T079_hook_exception_no_crash(self, store, ctx):
        store.add_hook(lambda k,r,c: (_ for _ in ()).throw(RuntimeError("err")))
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).enabled
    def test_T080_concurrent_eval(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        errors = []
        def worker():
            try: store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1"))
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


class TestRolloutStrategies:
    def test_T081_percentage_0_blocks_all(self, store):
        cfg = FlagConfig(key=FlagKey.DASHBOARD_REALTIME_PNL, enabled=True,
                         strategy=RolloutStrategy.PERCENTAGE, rollout_pct=0.0)
        store.set_flag(cfg, "admin", "0pct")
        hits = sum(1 for i in range(100)
                   if store.is_enabled(FlagKey.DASHBOARD_REALTIME_PNL, EvalContext(user_id=f"u{i}",tenant_id="t1")))
        assert hits == 0
    def test_T082_percentage_100_allows_all(self, store):
        cfg = FlagConfig(key=FlagKey.DASHBOARD_REALTIME_PNL, enabled=True,
                         strategy=RolloutStrategy.PERCENTAGE, rollout_pct=100.0)
        store.set_flag(cfg, "admin", "100pct")
        hits = sum(1 for i in range(100)
                   if store.is_enabled(FlagKey.DASHBOARD_REALTIME_PNL, EvalContext(user_id=f"u{i}",tenant_id="t1")))
        assert hits == 100
    def test_T083_percentage_50_roughly_half(self, store):
        cfg = FlagConfig(key=FlagKey.DASHBOARD_REALTIME_PNL, enabled=True,
                         strategy=RolloutStrategy.PERCENTAGE, rollout_pct=50.0)
        store.set_flag(cfg, "admin", "50pct")
        hits = sum(1 for i in range(1000)
                   if store.is_enabled(FlagKey.DASHBOARD_REALTIME_PNL, EvalContext(user_id=f"u{i}",tenant_id="t1")))
        assert 350 <= hits <= 650
    def test_T084_stable_hash_deterministic(self):
        h1 = _stable_hash("risk.kill_switch_v2","u42","t1")
        h2 = _stable_hash("risk.kill_switch_v2","u42","t1")
        assert h1 == h2
    def test_T085_stable_hash_different_users(self):
        assert _stable_hash("k","u1","t1") != _stable_hash("k","u2","t1")
    def test_T086_stable_hash_range(self):
        for i in range(50):
            h = _stable_hash(f"key{i}",f"u{i}",f"t{i}")
            assert 0.0 <= h <= 100.0
    def test_T087_allowlist_user(self, store):
        cfg = FlagConfig(key=FlagKey.EA_TELEMETRY_V2, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_users={"u_vip"})
        store.set_flag(cfg, "admin", "allowlist")
        assert store.is_enabled(FlagKey.EA_TELEMETRY_V2, EvalContext(user_id="u_vip",tenant_id="t1"))
        assert not store.is_enabled(FlagKey.EA_TELEMETRY_V2, EvalContext(user_id="u_other",tenant_id="t1"))
    def test_T088_allowlist_tenant(self, store):
        cfg = FlagConfig(key=FlagKey.EA_TELEMETRY_V2, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_tenants={"t_beta"})
        store.set_flag(cfg, "admin", "tenant allowlist")
        assert store.is_enabled(FlagKey.EA_TELEMETRY_V2, EvalContext(user_id="any",tenant_id="t_beta"))
        assert not store.is_enabled(FlagKey.EA_TELEMETRY_V2, EvalContext(user_id="any",tenant_id="t_other"))
    def test_T089_blocklist_user(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_DYNAMIC_DRAWDOWN, enabled=True, blocklist_users={"u_bad"})
        store.set_flag(cfg, "admin", "blocklist")
        assert not store.is_enabled(FlagKey.RISK_DYNAMIC_DRAWDOWN, EvalContext(user_id="u_bad",tenant_id="t1"))
        assert store.is_enabled(FlagKey.RISK_DYNAMIC_DRAWDOWN, EvalContext(user_id="u_good",tenant_id="t1"))
    def test_T090_blocklist_tenant(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_DYNAMIC_DRAWDOWN, enabled=True, blocklist_tenants={"t_suspended"})
        store.set_flag(cfg, "admin", "tenant block")
        assert not store.is_enabled(FlagKey.RISK_DYNAMIC_DRAWDOWN, EvalContext(user_id="u1",tenant_id="t_suspended"))
        assert store.is_enabled(FlagKey.RISK_DYNAMIC_DRAWDOWN, EvalContext(user_id="u1",tenant_id="t_good"))
    def test_T091_blocklist_priority_over_allowlist(self, store):
        cfg = FlagConfig(key=FlagKey.LICENSE_GRACE_PERIOD, enabled=True,
                         blocklist_users={"u1"}, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "conflict")
        assert not store.evaluate(FlagKey.LICENSE_GRACE_PERIOD, EvalContext(user_id="u1",tenant_id="t1")).enabled
    def test_T092_kill_overrides_allowlist(self, store):
        cfg = FlagConfig(key=FlagKey.LICENSE_GRACE_PERIOD, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "init")
        store.activate_kill(FlagKey.LICENSE_GRACE_PERIOD, "admin", "emergency")
        result = store.evaluate(FlagKey.LICENSE_GRACE_PERIOD, EvalContext(user_id="u1",tenant_id="t1"))
        assert not result.enabled and result.scope == FlagScope.KILL_OVERRIDE
    def test_T093_eval_result_has_flag_key(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).flag_key == FlagKey.RISK_KILL_SWITCH_V2.value
    def test_T094_eval_global_scope(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True), "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx).scope == FlagScope.GLOBAL
    def test_T095_allowlist_scope_user(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1")).scope == FlagScope.USER
    def test_T096_tenant_allowlist_scope(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_tenants={"t1"})
        store.set_flag(cfg, "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u_other",tenant_id="t1")).scope == FlagScope.TENANT


class TestGradualRolloutManager:
    def test_T097_start_requires_reason(self, rollout):
        with pytest.raises(ValueError):
            rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T098_start_creates_flag(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "begin", initial_pct=1.0)
        cfg = store.get_flag(FlagKey.RISK_KILL_SWITCH_V2)
        assert cfg and cfg.enabled and cfg.strategy == RolloutStrategy.PERCENTAGE and cfg.rollout_pct == 1.0
    def test_T099_step_up_increases(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=1.0)
        rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "step1")
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct > 1.0
    def test_T100_step_up_to_target(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=5.0)
        rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "jump", target_pct=50.0)
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct == 50.0
    def test_T101_step_down_decreases(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=50.0)
        rollout.step_down(FlagKey.RISK_KILL_SWITCH_V2, "admin", "rollback")
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct < 50.0
    def test_T102_step_down_to_target(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=75.0)
        rollout.step_down(FlagKey.RISK_KILL_SWITCH_V2, "admin", "drop", target_pct=10.0)
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct == 10.0
    def test_T103_pause_blocks_step_up(self, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=5.0)
        rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "incident")
        with pytest.raises(RuntimeError, match="paused"):
            rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "blocked")
    def test_T104_resume_unblocks(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=5.0)
        rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "pause")
        rollout.resume(FlagKey.RISK_KILL_SWITCH_V2, "admin", "resumed")
        rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "step")
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct > 5.0
    def test_T105_is_paused(self, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start")
        assert not rollout.is_paused(FlagKey.RISK_KILL_SWITCH_V2)
        rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "pause")
        assert rollout.is_paused(FlagKey.RISK_KILL_SWITCH_V2)
    def test_T106_history_tracked(self, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=1.0)
        rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "s1")
        rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "s2")
        assert len(rollout.history(FlagKey.RISK_KILL_SWITCH_V2)) == 3
    def test_T107_history_empty_unknown(self, rollout):
        assert rollout.history(FlagKey.PLATFORM_GRAPHQL) == []
    def test_T108_step_up_requires_reason(self, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start")
        with pytest.raises(ValueError): rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T109_step_down_requires_reason(self, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start")
        with pytest.raises(ValueError): rollout.step_down(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T110_pause_requires_reason(self, rollout):
        with pytest.raises(ValueError): rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T111_resume_requires_reason(self, rollout):
        with pytest.raises(ValueError): rollout.resume(FlagKey.RISK_KILL_SWITCH_V2, "admin", "")
    def test_T112_pct_capped_100(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=200.0)
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct <= 100.0


class TestAuditIntegrity:
    def test_T113_chain_valid_many_ops(self, store):
        for i in range(20):
            store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=(i%2==0)), f"u{i}", f"r{i}")
        assert store.audit.verify_chain()
    def test_T114_kill_audit_record(self, store):
        store.activate_kill(FlagKey.EA_REMOTE_KILL, "admin", "security")
        recs = store.audit.query(action="kill")
        assert len(recs)==1 and recs[0].reason=="security"
    def test_T115_audit_has_tenant_id(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "op", tenant_id="t_acme")
        assert store.audit.query(flag_key=FlagKey.RISK_KILL_SWITCH_V2.value)[0].tenant_id == "t_acme"
    def test_T116_audit_has_payload(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True, rollout_pct=42.0)
        store.set_flag(cfg, "admin", "pct")
        assert store.audit.query(flag_key=FlagKey.RISK_KILL_SWITCH_V2.value)[0].payload.get("rollout_pct") == 42.0
    def test_T117_every_change_audited(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True)
        before = store.audit.total
        store.set_flag(cfg, "admin", "change")
        assert store.audit.total == before + 1
    def test_T118_unique_ids(self, chain):
        for i in range(20): chain.record("k","create",f"u{i}",f"r{i}",{})
        ids = [r.id for r in chain._records]
        assert len(ids) == len(set(ids))
    def test_T119_prev_hash_linked(self, chain):
        chain.record("k","c1","admin","r1",{})
        chain.record("k","c2","admin","r2",{})
        recs = list(chain._records)
        assert recs[1].prev_hash == recs[0].chain_hash
    def test_T120_eval_no_audit(self, store, ctx):
        before = store.audit.total
        store.evaluate(FlagKey.PLATFORM_GRAPHQL, ctx)
        assert store.audit.total == before
    def test_T121_remove_action_audited(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "init")
        store.remove_flag(FlagKey.RISK_KILL_SWITCH_V2, "admin", "cleanup")
        assert any(r.flag_key==FlagKey.RISK_KILL_SWITCH_V2.value for r in store.audit.query(action="remove"))
    def test_T122_all_mutations_need_reason(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True)
        store.set_flag(cfg, "admin", "init")
        for fn, args in [
            (store.set_flag, (cfg,"admin","")),
            (store.remove_flag, (FlagKey.RISK_KILL_SWITCH_V2,"admin","")),
            (store.activate_kill, (FlagKey.RISK_KILL_SWITCH_V2,"admin","")),
            (store.reset_kill, (FlagKey.RISK_KILL_SWITCH_V2,"admin","")),
        ]:
            with pytest.raises(ValueError): fn(*args)
    def test_T123_concurrent_chain_valid(self, store):
        def worker(i):
            store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), f"u{i}", f"op {i}")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert store.audit.verify_chain()
    def test_T124_record_fields_complete(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "full check")
        r = store.audit.query(flag_key=FlagKey.RISK_KILL_SWITCH_V2.value)[0]
        assert r.id and r.seq>=1 and r.flag_key and r.action and r.actor_id=="admin"
        assert r.reason=="full check" and r.ts>0 and len(r.chain_hash)==64 and len(r.prev_hash)==64
    def test_T125_different_secrets_different_genesis(self):
        assert FlagAuditChain(secret="s1")._genesis() != FlagAuditChain(secret="s2")._genesis()
    def test_T126_query_limit(self, chain):
        for i in range(20): chain.record("k","c",f"u{i}",f"r{i}",{})
        assert len(chain.query(limit=5)) == 5
    def test_T127_pause_creates_audit(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start")
        rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "incident")
        assert len(store.audit.query(action="rollout_pause")) >= 1
    def test_T128_resume_creates_audit(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start")
        rollout.pause(FlagKey.RISK_KILL_SWITCH_V2, "admin", "p")
        rollout.resume(FlagKey.RISK_KILL_SWITCH_V2, "admin", "resolved")
        assert len(store.audit.query(action="rollout_resume")) >= 1


class TestSQLMigration:
    def test_T129_sql_exists(self): assert len(MIGRATION_SQL) > 100
    def test_T130_begin_commit(self): assert "BEGIN;" in MIGRATION_SQL and "COMMIT;" in MIGRATION_SQL
    def test_T131_feature_flags_table(self): assert "CREATE TABLE IF NOT EXISTS feature_flags" in MIGRATION_SQL
    def test_T132_kill_overrides_table(self): assert "CREATE TABLE IF NOT EXISTS flag_kill_overrides" in MIGRATION_SQL
    def test_T133_audit_log_table(self): assert "CREATE TABLE IF NOT EXISTS flag_audit_log" in MIGRATION_SQL
    def test_T134_rollout_history_table(self): assert "CREATE TABLE IF NOT EXISTS flag_rollout_history" in MIGRATION_SQL
    def test_T135_immutable_trigger(self): assert "prevent_flag_audit_mutation" in MIGRATION_SQL
    def test_T136_rls_enabled(self): assert "ENABLE ROW LEVEL SECURITY" in MIGRATION_SQL
    def test_T137_rls_policies(self): assert all(p in MIGRATION_SQL for p in ["flag_tenant_isolation","kill_tenant_isolation","audit_tenant_isolation"])
    def test_T138_indexes(self): assert "idx_feature_flags_key" in MIGRATION_SQL and "idx_flag_audit_seq" in MIGRATION_SQL
    def test_T139_cleanup_fn(self): assert "cleanup_expired_kills" in MIGRATION_SQL
    def test_T140_active_kills_view(self): assert "vw_active_flag_kills" in MIGRATION_SQL
    def test_T141_tenant_id_in_tables(self): assert MIGRATION_SQL.count("tenant_id") >= 4
    def test_T142_rollout_pct_constraint(self): assert "rollout_pct BETWEEN 0 AND 100" in MIGRATION_SQL
    def test_T143_reason_not_empty(self): assert "reason_not_empty" in MIGRATION_SQL
    def test_T144_chain_hash_length(self): assert "char_length(chain_hash) = 64" in MIGRATION_SQL


class TestScopeAndPrecedence:
    def test_T145_kill_beats_all(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_users={"u1"}, allowlist_tenants={"t1"})
        store.set_flag(cfg, "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "emergency")
        result = store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1"))
        assert not result.enabled and result.scope == FlagScope.KILL_OVERRIDE
    def test_T146_blocklist_scope(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=True, blocklist_tenants={"t1"}, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "init")
        result = store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1"))
        assert not result.enabled
    def test_T147_plan_gate_before_pct(self, store):
        cfg = FlagConfig(key=FlagKey.BILLING_CRYPTO_PAY, enabled=True,
                         strategy=RolloutStrategy.PERCENTAGE, rollout_pct=100.0)
        store.set_flag(cfg, "admin", "init")
        result = store.evaluate(FlagKey.BILLING_CRYPTO_PAY, EvalContext(user_id="u1",tenant_id="t1",plan=PlanTier.TRIAL))
        assert not result.enabled and "plan_gate" in result.reason
    def test_T148_disabled_beats_all(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, enabled=False,
                         strategy=RolloutStrategy.ALLOWLIST, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "disabled")
        result = store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1"))
        assert not result.enabled and result.reason == "flag_disabled"
    def test_T149_reason_is_string(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "init")
        r = store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx)
        assert isinstance(r.reason, str) and len(r.reason) > 0
    def test_T150_all_32_flags_evaluatable(self, store):
        ctx2 = EvalContext(user_id="u1",tenant_id="t1",plan=PlanTier.ADMIN)
        for key in FlagKey:
            store.set_flag(FlagConfig(key=key,enabled=True), "admin", f"init {key.value}")
        for key in FlagKey:
            assert isinstance(store.evaluate(key, ctx2), EvalResult)
    def test_T151_not_found_scope_global(self, store, ctx):
        assert store.evaluate(FlagKey.PLATFORM_GRAPHQL, ctx).scope == FlagScope.GLOBAL
    def test_T152_disabled_scope_global(self, store, ctx):
        store.set_flag(FlagConfig(key=FlagKey.PLATFORM_GRAPHQL,enabled=False), "admin", "init")
        assert store.evaluate(FlagKey.PLATFORM_GRAPHQL, ctx).scope == FlagScope.GLOBAL
    def test_T153_ring_scope(self, store):
        cfg = FlagConfig(key=FlagKey.EA_CLOUD_CONFIG, enabled=True,
                         strategy=RolloutStrategy.RING, min_ring=ReleaseRing.BETA)
        store.set_flag(cfg, "admin", "ring")
        assert store.evaluate(FlagKey.EA_CLOUD_CONFIG, EvalContext(user_id="u1",tenant_id="t1",ring=ReleaseRing.BETA)).scope == FlagScope.RING
    def test_T154_plan_scope(self, store):
        store.set_flag(FlagConfig(key=FlagKey.BILLING_CRYPTO_PAY,enabled=True), "admin", "init")
        assert store.evaluate(FlagKey.BILLING_CRYPTO_PAY, EvalContext(user_id="u1",tenant_id="t1",plan=PlanTier.BASIC)).scope == FlagScope.PLAN
    def test_T155_pct_scope_global(self, store):
        cfg = FlagConfig(key=FlagKey.DASHBOARD_REALTIME_PNL, enabled=True,
                         strategy=RolloutStrategy.PERCENTAGE, rollout_pct=100.0)
        store.set_flag(cfg, "admin", "init")
        assert store.evaluate(FlagKey.DASHBOARD_REALTIME_PNL, EvalContext(user_id="u1",tenant_id="t1")).scope == FlagScope.GLOBAL
    def test_T156_tenant_scope(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True, allowlist_tenants={"t1"})
        store.set_flag(cfg, "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u_new",tenant_id="t1")).scope == FlagScope.TENANT
    def test_T157_user_scope(self, store):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True, allowlist_users={"u1"})
        store.set_flag(cfg, "admin", "init")
        assert store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, EvalContext(user_id="u1",tenant_id="t1")).scope == FlagScope.USER
    def test_T158_kill_blocks_admin_plan(self, store):
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "init")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "global")
        assert not store.evaluate(FlagKey.RISK_KILL_SWITCH_V2,
                                  EvalContext(user_id="root",tenant_id="t1",plan=PlanTier.ADMIN,ring=ReleaseRing.INTERNAL)).enabled
    def test_T159_flag_config_defaults(self):
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2)
        assert not cfg.enabled and cfg.strategy==RolloutStrategy.NONE and cfg.rollout_pct==0.0
        assert cfg.allowlist_users==set() and cfg.min_plan is None and cfg.min_ring is None
    def test_T160_flag_config_timestamps(self):
        before = time.time()
        cfg = FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2)
        after = time.time()
        assert before <= cfg.created_at <= after and before <= cfg.updated_at <= after


class TestIntegrationFlows:
    def test_T161_full_release_lifecycle(self, store, rollout):
        key = FlagKey.DASHBOARD_REALTIME_PNL
        rollout.start_rollout(key, "admin", "release starts", initial_pct=1.0)
        assert store.get_flag(key).rollout_pct == 1.0
        rollout.step_up(key, "admin", "metrics good")
        rollout.step_up(key, "admin", "all clear", target_pct=100.0)
        assert store.get_flag(key).rollout_pct == 100.0
        ctx = EvalContext(user_id="u1",tenant_id="t1")
        store.activate_kill(key, "admin", "P1 incident")
        assert not store.is_enabled(key, ctx)
        store.reset_kill(key, "admin", "resolved")
        assert store.is_enabled(key, ctx)
        store.remove_flag(key, "admin", "stable")
        assert store.get_flag(key) is None
        assert store.audit.verify_chain()
    def test_T162_canary_to_ga_flow(self, store):
        key = FlagKey.BILLING_INVOICE_PDF
        cfg = FlagConfig(key=key,enabled=True,strategy=RolloutStrategy.RING,min_ring=ReleaseRing.INTERNAL)
        store.set_flag(cfg, "admin", "canary")
        assert store.is_enabled(key, EvalContext(user_id="u1",tenant_id="t1",ring=ReleaseRing.INTERNAL))
        assert not store.is_enabled(key, EvalContext(user_id="u2",tenant_id="t2",ring=ReleaseRing.GA))
        cfg.min_ring = ReleaseRing.GA
        store.set_flag(cfg, "admin", "expand GA")
        assert store.is_enabled(key, EvalContext(user_id="u2",tenant_id="t2",ring=ReleaseRing.GA))
    def test_T163_multi_flag_isolation(self, store):
        k1,k2 = FlagKey.RISK_KILL_SWITCH_V2, FlagKey.EA_REMOTE_KILL
        store.set_flag(FlagConfig(key=k1,enabled=True), "admin", "init k1")
        store.set_flag(FlagConfig(key=k2,enabled=False), "admin", "init k2")
        ctx = EvalContext(user_id="u1",tenant_id="t1")
        store.activate_kill(k1, "admin", "kill k1")
        assert not store.is_enabled(k1, ctx)
        assert len(store.active_kills(k2)) == 0
    def test_T164_chain_survives_200_ops(self, store):
        for i in range(100):
            store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=(i%2==0)), f"u{i}", f"op {i}")
        for i in range(50):
            store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, f"admin{i}", f"kill {i}")
            store.reset_kill(FlagKey.RISK_KILL_SWITCH_V2, f"admin{i}", f"reset {i}")
        assert store.audit.verify_chain() and store.audit.total == 200
    def test_T165_concurrent_rollout_safe(self, store, rollout):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=0.0)
        errors = []
        def worker():
            try: rollout.step_up(FlagKey.RISK_KILL_SWITCH_V2, "admin", "concurrent step")
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert store.audit.verify_chain()
    def test_T166_ea_kill_flow(self, store):
        key = FlagKey.EA_REMOTE_KILL
        store.set_flag(FlagConfig(key=key,enabled=True), "devops", "deploy ea v2.1")
        ctx = EvalContext(user_id="mt4_001",tenant_id="broker_acme",plan=PlanTier.PRO)
        assert store.is_enabled(key, ctx)
        store.activate_kill(key, "oncall", "runaway trades", tenant_id="broker_acme")
        assert not store.is_enabled(key, ctx)
        assert store.is_enabled(key, EvalContext(user_id="mt4_002",tenant_id="broker_beta",plan=PlanTier.PRO))
        store.reset_kill(key, "oncall", "patched", tenant_id="broker_acme")
        assert store.is_enabled(key, ctx)
    def test_T167_billing_plan_gate_flow(self, store):
        key = FlagKey.BILLING_CRYPTO_PAY
        store.set_flag(FlagConfig(key=key,enabled=True), "admin", "enable crypto pay")
        assert not store.is_enabled(key, EvalContext(user_id="trial",tenant_id="t1",plan=PlanTier.TRIAL))
        assert store.is_enabled(key, EvalContext(user_id="pro",tenant_id="t1",plan=PlanTier.PRO))
        assert store.is_enabled(key, EvalContext(user_id="vip",tenant_id="t1",plan=PlanTier.VIP))
    def test_T168_global_singleton(self):
        assert get_store() is not None and get_rollout() is not None
    def test_T169_is_enabled_helper(self):
        get_store().set_flag(FlagConfig(key=FlagKey.RISK_NEWS_FILTER,enabled=True), "admin", "test")
        assert isinstance(is_enabled(FlagKey.RISK_NEWS_FILTER, EvalContext(user_id="u",tenant_id="t")), bool)
    def test_T170_risk_kill_switch_full_flow(self, store):
        key = FlagKey.RISK_KILL_SWITCH_V2
        store.set_flag(FlagConfig(key=key,enabled=True), "risk", "enable")
        users = [EvalContext(user_id=f"u{i}",tenant_id=f"t{i}") for i in range(10)]
        for ctx in users: assert store.is_enabled(key, ctx)
        store.activate_kill(key, "cto", "drawdown emergency")
        for ctx in users: assert not store.is_enabled(key, ctx)
        store.reset_kill(key, "cto", "resolved")
        for ctx in users: assert store.is_enabled(key, ctx)
        assert store.audit.verify_chain()
    def test_T171_rollout_history_ordered(self, store, rollout):
        key = FlagKey.DASHBOARD_ADVANCED_CHARTS
        rollout.start_rollout(key, "admin", "begin", initial_pct=1.0)
        rollout.step_up(key, "admin", "s1")
        rollout.step_up(key, "admin", "s2")
        hist = rollout.history(key)
        assert len(hist)==3 and hist[0].pct <= hist[-1].pct
    def test_T172_flag_owner(self):
        assert FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, owner="risk_team").owner == "risk_team"
    def test_T173_flag_description(self):
        assert "kill switch" in FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2, description="enables new kill switch logic").description
    def test_T174_eval_context_extra(self):
        assert EvalContext(user_id="u1",tenant_id="t1",extra={"ab":"B"}).extra["ab"] == "B"
    def test_T175_rollout_step_dataclass(self):
        s = RolloutStep(pct=50.0)
        assert s.pct == 50.0 and s.at > 0
    def test_T176_audit_record_fields(self, chain):
        r = chain.record("k","create","admin","test",{"x":1})
        assert isinstance(r, FlagAuditRecord) and r.action=="create" and r.payload=={"x":1}


class TestEdgeCasesAndCoverage:
    def test_T177_no_spaces_in_keys(self):
        for k in FlagKey: assert " " not in k.value
    def test_T178_plan_tier_5(self): assert len(PlanTier) == 5
    def test_T179_ring_order(self):
        assert RING_ORDER == [ReleaseRing.INTERNAL,ReleaseRing.ALPHA,ReleaseRing.BETA,ReleaseRing.GA]
    def test_T180_plan_order(self):
        assert PLAN_ORDER == [PlanTier.TRIAL,PlanTier.BASIC,PlanTier.PRO,PlanTier.VIP,PlanTier.ADMIN]
    def test_T181_stable_hash_nonzero(self):
        assert not all(_stable_hash("k",f"u{i}","t1")==0 for i in range(100))
    def test_T182_default_strategy_none(self):
        assert FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2).strategy == RolloutStrategy.NONE
    def test_T183_ring_optional(self):
        assert EvalContext(user_id="u1",tenant_id="t1").ring is None
    def test_T184_plan_optional(self):
        assert EvalContext(user_id="u1",tenant_id="t1").plan is None
    def test_T185_kill_global_tenant_none(self):
        assert KillOverride(flag_key=FlagKey.RISK_KILL_SWITCH_V2,reason="r",actor_id="a",tenant_id=None).tenant_id is None
    def test_T186_multiple_hooks(self, store, ctx):
        calls = []
        store.add_hook(lambda k,r,c: calls.append("h1"))
        store.add_hook(lambda k,r,c: calls.append("h2"))
        store.set_flag(FlagConfig(key=FlagKey.RISK_KILL_SWITCH_V2,enabled=True), "admin", "init")
        store.evaluate(FlagKey.RISK_KILL_SWITCH_V2, ctx)
        assert "h1" in calls and "h2" in calls
    def test_T187_string_secret(self):
        assert len(FlagAuditChain(secret="plain").record("k","create","admin","test",{}).chain_hash) == 64
    def test_T188_bytes_secret(self):
        assert len(FlagAuditChain(secret=b"bytes").record("k","create","admin","test",{}).chain_hash) == 64
    def test_T189_pct_min_0(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=-10.0)
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct >= 0.0
    def test_T190_step_down_min_0(self, rollout, store):
        rollout.start_rollout(FlagKey.RISK_KILL_SWITCH_V2, "admin", "start", initial_pct=1.0)
        rollout.step_down(FlagKey.RISK_KILL_SWITCH_V2, "admin", "rollback", target_pct=-50.0)
        assert store.get_flag(FlagKey.RISK_KILL_SWITCH_V2).rollout_pct >= 0.0
    def test_T191_kill_dedup(self, store):
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "first", tenant_id="t1")
        store.activate_kill(FlagKey.RISK_KILL_SWITCH_V2, "admin", "second", tenant_id="t1")
        kills = [k for k in store.active_kills(FlagKey.RISK_KILL_SWITCH_V2) if k.tenant_id=="t1"]
        assert len(kills)==1 and kills[0].reason=="second"
    def test_T192_all_domains_covered(self):
        domains = {k.value.split(".")[0] for k in FlagKey}
        assert domains == {"risk","license","billing","ea","dashboard","platform"}
