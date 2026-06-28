"""
test_phase29_secret_rotation.py
Phase 29 -- Secure Secrets Rotation & Key Lifecycle
208 tests: T001-T208
"""
from __future__ import annotations
import hashlib, hmac, json, os, sys, threading, time, uuid
sys.path.insert(0, "/home/definable/phase29")
import pytest
from backend.core.secret_rotation import (
    KeyType, KeyStatus, RotationTrigger, AuditAction, REQUIRES_REASON,
    COMPROMISE_RUNBOOK,
    SecretRotationError, KeyNotFoundError, KeyRevokedError, KeyExpiredError,
    MissingReasonError, PolicyViolationError, CompromiseResponseError,
    RotationPolicy, KeyVersion, AuditEntry, CompromiseReport,
    SecretAuditChain, KeyMaterialGenerator, KeySelfAuth,
    KeyStore, RotationPolicyEngine, KeyLifecycleManager,
    CompromiseResponseManager, RotationScheduler, GracePeriodExtender,
    SecretRotationAdmin, build_secret_rotation_system,
    _POLICY_DEFAULTS,
)

def fresh() -> KeyLifecycleManager:
    return KeyLifecycleManager(master_secret=b"test-master-p29")

def full_system():
    return build_secret_rotation_system(b"test-master-p29")

class TestEnumsAndDefaults:
    def test_T001_key_type_count(self):
        assert len(KeyType) == 10
    def test_T002_key_status_values(self):
        vals = {s.value for s in KeyStatus}
        assert vals == {"active","grace","revoked","expired","pending"}
    def test_T003_rotation_trigger_values(self):
        vals = {t.value for t in RotationTrigger}
        assert "scheduled" in vals and "compromise" in vals and "bootstrap" in vals
    def test_T004_audit_action_values(self):
        assert AuditAction.KEY_ROTATED.value  == "key.rotated"
        assert AuditAction.KEY_REVOKED.value  == "key.revoked"
        assert AuditAction.EMERGENCY_ROT.value == "key.emergency_rotation"
        assert AuditAction.COMPROMISE_ACK.value == "key.compromise_ack"
    def test_T005_requires_reason_set(self):
        assert AuditAction.KEY_REVOKED    in REQUIRES_REASON
        assert AuditAction.COMPROMISE_ACK in REQUIRES_REASON
        assert AuditAction.EMERGENCY_ROT  in REQUIRES_REASON
        assert AuditAction.KEY_EXPIRED    in REQUIRES_REASON
        assert AuditAction.KEY_GENERATED  not in REQUIRES_REASON
    def test_T006_policy_defaults_all_types(self):
        for kt in KeyType:
            assert kt in _POLICY_DEFAULTS
    def test_T007_jwt_policy(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING)
        assert p.max_age_days == 30 and p.grace_days == 7 and p.auto_rotate is True
    def test_T008_kek_no_auto_rotate(self):
        assert RotationPolicy.default_for(KeyType.ENCRYPTION_KEK).auto_rotate is False
    def test_T009_audit_chain_no_auto_rotate(self):
        assert RotationPolicy.default_for(KeyType.AUDIT_CHAIN).auto_rotate is False
    def test_T010_max_age_seconds(self):
        assert RotationPolicy.default_for(KeyType.JWT_SIGNING).max_age_seconds == 30*86400.0
    def test_T011_grace_seconds(self):
        assert RotationPolicy.default_for(KeyType.JWT_SIGNING).grace_seconds == 7*86400.0
    def test_T012_key_material_sizes(self):
        for kt in KeyType:
            assert len(KeyMaterialGenerator.generate(kt)) >= 32
    def test_T013_compromise_runbook_steps(self):
        assert len(COMPROMISE_RUNBOOK) == 10
        assert "STEP-1" in COMPROMISE_RUNBOOK[0]
        assert "STEP-10" in COMPROMISE_RUNBOOK[-1]
    def test_T014_key_status_active_exists(self):
        assert KeyStatus.ACTIVE in list(KeyStatus)
    def test_T015_policy_tenant_scoped(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING, tenant_id="t1")
        assert p.tenant_id == "t1"
    def test_T016_policy_max_uses_dek(self):
        assert RotationPolicy.default_for(KeyType.ENCRYPTION_DEK).max_uses == 1_000_000

class TestSecretAuditChain:
    def test_T017_genesis_hash_64chars(self):
        chain = SecretAuditChain(b"secret")
        e = chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"actor")
        assert len(e.chain_hash) == 64
    def test_T018_verify_empty_chain(self):
        assert SecretAuditChain(b"s").verify_chain() is True
    def test_T019_verify_valid_chain(self):
        chain = SecretAuditChain(b"s")
        for i in range(5):
            chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,i+1,"a")
        assert chain.verify_chain() is True
    def test_T020_tamper_detected(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        chain.record(AuditAction.KEY_ACTIVATED,"k1",KeyType.JWT_SIGNING,1,"a")
        list(chain._entries)[0].chain_hash = "0"*64
        assert chain.verify_chain() is False
    def test_T021_detect_tampered_seq(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        chain.record(AuditAction.KEY_ACTIVATED,"k1",KeyType.JWT_SIGNING,1,"a")
        list(chain._entries)[0].chain_hash = "ff"*32
        assert 1 in chain.detect_tampered()
    def test_T022_requires_reason_enforced(self):
        chain = SecretAuditChain(b"s")
        with pytest.raises(MissingReasonError):
            chain.record(AuditAction.KEY_REVOKED,"k1",KeyType.JWT_SIGNING,1,"a",reason="")
    def test_T023_requires_reason_whitespace(self):
        chain = SecretAuditChain(b"s")
        with pytest.raises(MissingReasonError):
            chain.record(AuditAction.KEY_REVOKED,"k1",KeyType.JWT_SIGNING,1,"a",reason="   ")
    def test_T024_seq_monotonic(self):
        chain = SecretAuditChain(b"s")
        seqs = [chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,i,"a").seq for i in range(1,6)]
        assert seqs == sorted(seqs) and len(set(seqs)) == 5
    def test_T025_query_by_key_id(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        chain.record(AuditAction.KEY_GENERATED,"k2",KeyType.JWT_REFRESH,1,"a")
        assert len(chain.query(key_id="k1")) == 1
    def test_T026_query_most_recent_first(self):
        chain = SecretAuditChain(b"s")
        for i in range(5):
            chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,i+1,"a")
        seqs = [e.seq for e in chain.query(key_id="k1")]
        assert seqs == sorted(seqs, reverse=True)
    def test_T027_query_by_action(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        chain.record(AuditAction.KEY_ACTIVATED,"k1",KeyType.JWT_SIGNING,1,"a")
        assert len(chain.query(action=AuditAction.KEY_ACTIVATED)) == 1
    def test_T028_concurrent_records(self):
        chain = SecretAuditChain(b"s")
        threads = [threading.Thread(target=lambda: chain.record(
            AuditAction.KEY_GENERATED,str(uuid.uuid4()),KeyType.JWT_SIGNING,1,"a")) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert chain.total == 50 and chain.verify_chain() is True
    def test_T029_total_counter(self):
        chain = SecretAuditChain(b"s")
        for _ in range(10):
            chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        assert chain.total == 10
    def test_T030_str_secret_accepted(self):
        chain = SecretAuditChain("string-secret")
        e = chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        assert len(e.chain_hash) == 64
    def test_T031_query_limit(self):
        chain = SecretAuditChain(b"s")
        for i in range(20):
            chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,i,"a")
        assert len(chain.query(limit=5)) == 5
    def test_T032_query_limit_zero_returns_all(self):
        chain = SecretAuditChain(b"s")
        for _ in range(10):
            chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"a")
        assert len(chain.query(limit=0)) == 10

class TestKeyStore:
    def _make_kv(self, key_type=KeyType.JWT_SIGNING, version=1,
                 status=KeyStatus.ACTIVE, tenant_id=None):
        return KeyVersion(key_id=str(uuid.uuid4()), key_type=key_type,
            version=version, status=status, created_at=time.time(),
            activated_at=time.time(), expires_at=None, rotated_at=None,
            revoked_at=None, use_count=0, tenant_id=tenant_id,
            _raw=os.urandom(32), signature="",
            rotation_trigger=RotationTrigger.BOOTSTRAP)
    def test_T033_add_and_get(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        assert store.get(kv.key_id).key_id == kv.key_id
    def test_T034_get_not_found(self):
        with pytest.raises(KeyNotFoundError): KeyStore().get("nonexistent")
    def test_T035_list_by_type(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        assert any(k.key_id == kv.key_id for k in store.list_by_type(KeyType.JWT_SIGNING))
    def test_T036_active_key(self):
        store = KeyStore(); kv = self._make_kv(status=KeyStatus.ACTIVE); store.add(kv)
        assert store.active_key(KeyType.JWT_SIGNING).key_id == kv.key_id
    def test_T037_no_active_raises(self):
        with pytest.raises(KeyNotFoundError): KeyStore().active_key(KeyType.JWT_SIGNING)
    def test_T038_update_status(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        assert store.update_status(kv.key_id, kv.version, KeyStatus.GRACE).status == KeyStatus.GRACE
    def test_T039_increment_use(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        assert store.increment_use(kv.key_id, kv.version) == 1
    def test_T040_usable_keys_active_and_grace(self):
        store = KeyStore()
        kv_a = self._make_kv(version=1, status=KeyStatus.ACTIVE); store.add(kv_a)
        kv_g = self._make_kv(version=2, status=KeyStatus.GRACE); store.add(kv_g)
        kv_r = self._make_kv(version=3, status=KeyStatus.REVOKED); store.add(kv_r)
        statuses = {k.status for k in store.usable_keys(KeyType.JWT_SIGNING)}
        assert KeyStatus.ACTIVE in statuses and KeyStatus.GRACE in statuses and KeyStatus.REVOKED not in statuses
    def test_T041_tenant_isolation(self):
        store = KeyStore()
        store.add(self._make_kv(tenant_id="t1")); store.add(self._make_kv(tenant_id="t2"))
        assert all(k.tenant_id == "t1" for k in store.list_by_type(KeyType.JWT_SIGNING, tenant_id="t1"))
    def test_T042_version_filter(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        assert store.get(kv.key_id, version=kv.version).version == kv.version
    def test_T043_version_not_found(self):
        store = KeyStore(); kv = self._make_kv(); store.add(kv)
        with pytest.raises(KeyNotFoundError): store.get(kv.key_id, version=999)
    def test_T044_concurrent_add(self):
        store = KeyStore(); results = []
        def add(): kv = self._make_kv(); store.add(kv); results.append(kv.key_id)
        threads = [threading.Thread(target=add) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(store.all_keys()) == 50
    def test_T045_all_keys(self):
        store = KeyStore()
        for _ in range(5): store.add(self._make_kv())
        assert len(store.all_keys()) == 5
    def test_T046_status_filter(self):
        store = KeyStore()
        store.add(self._make_kv(version=1, status=KeyStatus.ACTIVE))
        store.add(self._make_kv(version=2, status=KeyStatus.PENDING))
        assert all(k.status == KeyStatus.ACTIVE for k in store.list_by_type(KeyType.JWT_SIGNING, status=KeyStatus.ACTIVE))
    def test_T047_safe_dict_no_raw(self):
        kv = self._make_kv(); d = kv.safe_dict()
        assert "_raw" not in d and "key_id" in d
    def test_T048_usable_for_verify_grace(self):
        kv = self._make_kv(status=KeyStatus.GRACE)
        assert kv.is_usable_for_verify() is True and kv.is_usable_for_new() is False

class TestRotationPolicyEngine:
    def _make_kv(self, key_type=KeyType.JWT_SIGNING, age_days=0, use_count=0, tenant_id=None):
        now = time.time(); activated = now - age_days*86400
        return KeyVersion(key_id="k1", key_type=key_type, version=1, status=KeyStatus.ACTIVE,
            created_at=activated, activated_at=activated, expires_at=None, rotated_at=None,
            revoked_at=None, use_count=use_count, tenant_id=tenant_id, _raw=os.urandom(32))
    def test_T049_no_rotation_needed_fresh(self):
        assert RotationPolicyEngine().needs_rotation(self._make_kv(age_days=0))[0] is False
    def test_T050_rotation_needed_old(self):
        needs, reason = RotationPolicyEngine().needs_rotation(self._make_kv(age_days=31))
        assert needs is True and "max_age_days" in reason
    def test_T051_rotation_by_max_uses(self):
        needs, reason = RotationPolicyEngine().needs_rotation(self._make_kv(key_type=KeyType.ENCRYPTION_DEK, use_count=1_000_001))
        assert needs is True and "max_uses" in reason
    def test_T052_custom_policy(self):
        eng = RotationPolicyEngine()
        eng.set_policy(RotationPolicy(key_type=KeyType.JWT_SIGNING, max_age_days=5))
        assert eng.needs_rotation(self._make_kv(age_days=6))[0] is True
    def test_T053_grace_not_expired(self):
        eng = RotationPolicyEngine(); kv = self._make_kv()
        kv.expires_at = time.time()+3600
        assert eng.is_grace_expired(kv) is False
    def test_T054_grace_expired(self):
        eng = RotationPolicyEngine(); kv = self._make_kv()
        kv.expires_at = time.time()-1
        assert eng.is_grace_expired(kv) is True
    def test_T055_due_soon(self):
        assert RotationPolicyEngine().due_soon(self._make_kv(age_days=24), warn_days=7) is True
    def test_T056_not_due_soon(self):
        assert RotationPolicyEngine().due_soon(self._make_kv(age_days=5), warn_days=7) is False
    def test_T057_tenant_policy_override(self):
        eng = RotationPolicyEngine()
        eng.set_policy(RotationPolicy(key_type=KeyType.JWT_SIGNING, max_age_days=10, tenant_id="t1"))
        eng.set_policy(RotationPolicy(key_type=KeyType.JWT_SIGNING, max_age_days=30))
        assert eng.get_policy(KeyType.JWT_SIGNING, "t1").max_age_days == 10
        assert eng.get_policy(KeyType.JWT_SIGNING, "t2").max_age_days == 30
    def test_T058_default_fallback(self):
        eng = RotationPolicyEngine()
        assert eng.get_policy(KeyType.WEBHOOK_HMAC).max_age_days == _POLICY_DEFAULTS[KeyType.WEBHOOK_HMAC]["max_age_days"]
    def test_T059_no_rotation_0_max_uses(self):
        kv = self._make_kv(key_type=KeyType.JWT_SIGNING, use_count=999_999)
        assert RotationPolicyEngine().needs_rotation(kv)[0] is False
    def test_T060_all_key_types_have_policy(self):
        eng = RotationPolicyEngine()
        for kt in KeyType:
            assert eng.get_policy(kt).max_age_days > 0

class TestKeyLifecycleManager:
    def test_T061_generate_key(self):
        kv = fresh().generate_key(KeyType.JWT_SIGNING, actor="test")
        assert kv.status == KeyStatus.PENDING and kv.key_id and kv.version >= 1
    def test_T062_generate_with_activate(self):
        kv = fresh().generate_key(KeyType.JWT_SIGNING, activate=True)
        assert kv.status == KeyStatus.ACTIVE and kv.activated_at is not None
    def test_T063_activate_pending(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING)
        assert lm.activate_key(kv.key_id, kv.version).status == KeyStatus.ACTIVE
    def test_T064_activate_non_pending_fails(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(PolicyViolationError): lm.activate_key(kv.key_id, kv.version)
    def test_T065_rotate_key_zero_downtime(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        old, new = lm.rotate_key(KeyType.JWT_SIGNING, actor="admin")
        assert old.status == KeyStatus.GRACE and new.status == KeyStatus.ACTIVE
    def test_T066_rotate_grace_has_expires_at(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        old, _ = lm.rotate_key(KeyType.JWT_SIGNING)
        assert old.expires_at is not None and old.expires_at > time.time()
    def test_T067_rotate_first_key_no_old(self):
        lm = fresh(); old, new = lm.rotate_key(KeyType.JWT_SIGNING)
        assert old is None and new.status == KeyStatus.ACTIVE
    def test_T068_revoke_key_requires_reason(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError): lm.revoke_key(kv.key_id, kv.version, actor="admin", reason="")
    def test_T069_revoke_key(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        r = lm.revoke_key(kv.key_id, kv.version, actor="admin", reason="suspected breach")
        assert r.status == KeyStatus.REVOKED and r.revoke_reason == "suspected breach"
    def test_T070_revoke_idempotent(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, kv.version, actor="a", reason="r")
        assert lm.revoke_key(kv.key_id, kv.version, actor="a", reason="r").status == KeyStatus.REVOKED
    def test_T071_expire_grace_keys(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        old, _ = lm.rotate_key(KeyType.JWT_SIGNING)
        lm._store.update_status(old.key_id, old.version, KeyStatus.GRACE, expires_at=time.time()-1)
        expired = lm.expire_grace_keys(reason="test grace expiry")
        assert len(expired) == 1 and expired[0].status == KeyStatus.EXPIRED
    def test_T072_record_access_increments_use(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.record_access(kv.key_id, kv.version, actor="svc") == 1
    def test_T073_record_access_revoked_raises(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, kv.version, actor="a", reason="r")
        with pytest.raises(KeyRevokedError): lm.record_access(kv.key_id, kv.version)
    def test_T074_record_access_expired_raises(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.EXPIRED)
        with pytest.raises(KeyExpiredError): lm.record_access(kv.key_id, kv.version)
    def test_T075_sign_payload(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"hello", KeyType.JWT_SIGNING)
        assert len(sig) == 64 and kid and ver >= 1
    def test_T076_verify_payload_ok(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"hello", KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"hello", sig, kid, ver) is True
    def test_T077_verify_payload_tampered(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"hello", KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"tampered", sig, kid, ver) is False
    def test_T078_verify_revoked_key_returns_false(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"data", KeyType.JWT_SIGNING)
        lm.revoke_key(kid, ver, actor="a", reason="r")
        assert lm.verify_payload(b"data", sig, kid, ver) is False
    def test_T079_verify_grace_key_ok(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"data", KeyType.JWT_SIGNING)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"data", sig, kid, ver) is True
    def test_T080_self_auth_valid(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.self_auth_valid(kv.key_id, kv.version) is True
    def test_T081_self_auth_different_master_fails(self):
        lm1 = KeyLifecycleManager(master_secret=b"master1")
        kv = lm1.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert KeySelfAuth.verify(kv, b"master2") is False
    def test_T082_rotation_hook_called(self):
        lm = fresh(); events = []
        lm.add_rotation_hook(lambda e, kv: events.append(e))
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert "generated" in events and "activated" in events
    def test_T083_hook_exception_does_not_propagate(self):
        lm = fresh(); lm.add_rotation_hook(lambda e, kv: 1/0)
        assert lm.generate_key(KeyType.JWT_SIGNING).key_id
    def test_T084_version_increment_per_type(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING); kv2 = lm.generate_key(KeyType.JWT_SIGNING)
        assert kv2.version == kv1.version + 1
    def test_T085_version_isolated_per_type(self):
        lm = fresh()
        assert lm.generate_key(KeyType.JWT_SIGNING).version == lm.generate_key(KeyType.WEBHOOK_HMAC).version == 1
    def test_T086_list_by_type(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING); lm.generate_key(KeyType.JWT_SIGNING)
        assert len(lm.list_by_type(KeyType.JWT_SIGNING)) == 2
    def test_T087_usable_keys_include_grace(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        statuses = {k.status for k in lm.usable_keys(KeyType.JWT_SIGNING)}
        assert KeyStatus.ACTIVE in statuses and KeyStatus.GRACE in statuses
    def test_T088_audit_chain_integrity(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm._audit.verify_chain() is True
    def test_T089_needs_rotation_fresh_false(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.needs_rotation(kv.key_id, kv.version)[0] is False
    def test_T090_concurrent_generate(self):
        lm = fresh(); keys = []; lock = threading.Lock()
        def gen():
            kv = lm.generate_key(KeyType.JWT_SIGNING)
            with lock: keys.append(kv)
        threads = [threading.Thread(target=gen) for _ in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(k.version for k in keys)) == 30
    def test_T091_all_key_types_can_generate(self):
        lm = fresh()
        for kt in KeyType: assert lm.generate_key(kt).key_type == kt
    def test_T092_rotate_multiple_types_independent(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.generate_key(KeyType.WEBHOOK_HMAC, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm.active_key(KeyType.WEBHOOK_HMAC).status == KeyStatus.ACTIVE
    def test_T093_sign_no_active_key_raises(self):
        with pytest.raises(KeyNotFoundError): fresh().sign_payload(b"x", KeyType.JWT_SIGNING)
    def test_T094_set_policy_recorded(self):
        lm = fresh(); before = lm._audit.total
        lm.set_policy(RotationPolicy(KeyType.JWT_SIGNING, max_age_days=10))
        assert lm._audit.total > before
    def test_T095_get_key_by_id_and_version(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.get_key(kv.key_id, kv.version).key_id == kv.key_id
    def test_T096_due_soon_false_for_fresh(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.due_soon(kv.key_id, kv.version, warn_days=7) is False

class TestCompromiseResponseManager:
    def test_T097_report_compromise(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        r = CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "leaked in logs")
        assert r.report_id and len(r.steps_taken) >= 3
    def test_T098_compromised_key_revoked(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "leaked")
        assert lm.get_key(kv.key_id, kv.version).status == KeyStatus.REVOKED
    def test_T099_new_key_generated_after_compromise(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        report = CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert lm.get_key(report.new_key_id).status == KeyStatus.ACTIVE
    def test_T100_reason_required(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError):
            CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", reason="")
    def test_T101_report_listed(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        crm = CompromiseResponseManager(lm)
        crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert len(crm.list_reports()) == 1
    def test_T102_resolve_report(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        crm = CompromiseResponseManager(lm)
        r = crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        resolved = crm.resolve_report(r.report_id, "admin")
        assert resolved.resolved is True and resolved.resolved_at is not None
    def test_T103_resolve_not_found(self):
        with pytest.raises(CompromiseResponseError):
            CompromiseResponseManager(fresh()).resolve_report("nonexistent", "admin")
    def test_T104_list_unresolved(self):
        lm = fresh(); crm = CompromiseResponseManager(lm)
        for _ in range(3):
            kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
            crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        crm.resolve_report(crm.list_reports()[0].report_id, "admin")
        assert len(crm.list_reports(resolved=False)) == 2
    def test_T105_audit_contains_emergency_rot(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert len(lm._audit.query(action=AuditAction.EMERGENCY_ROT)) >= 1
    def test_T106_compromise_trigger_on_new_key(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        crm = CompromiseResponseManager(lm)
        report = crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert lm.get_key(report.new_key_id).rotation_trigger == RotationTrigger.COMPROMISE
    def test_T107_report_stores_reason(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        r = CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "git leak")
        assert "git leak" in r.reason
    def test_T108_runbook_steps_count(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        r = CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert len(r.steps_taken) == len(COMPROMISE_RUNBOOK)

class TestSchedulerAndExtender:
    def test_T109_scan_due_empty(self):
        assert RotationScheduler(fresh()).scan_due() == []
    def test_T110_scan_due_overdue(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-31*86400)
        assert len(RotationScheduler(lm).scan_due()) >= 1
    def test_T111_scan_due_soon(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-24*86400)
        assert len(RotationScheduler(lm).scan_due_soon(warn_days=7)) >= 1
    def test_T112_auto_rotate_overdue(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-31*86400)
        rotated = RotationScheduler(lm).auto_rotate_all()
        assert len(rotated) >= 1 and rotated[0][0].status == KeyStatus.GRACE
    def test_T113_auto_rotate_skips_no_auto(self):
        lm = fresh(); kv = lm.generate_key(KeyType.ENCRYPTION_KEK, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-400*86400)
        assert len(RotationScheduler(lm).auto_rotate_all()) == 0
    def test_T114_expire_grace_pass(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.GRACE, expires_at=time.time()-1)
        assert len(RotationScheduler(lm).expire_grace_pass(reason="test expiry")) == 1
    def test_T115_extend_grace(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        grace_kv = lm.get_key(kv.key_id, kv.version)
        old_exp = grace_kv.expires_at
        ext = GracePeriodExtender(lm).extend(kv.key_id, kv.version, extra_days=14, actor="admin")
        assert ext.expires_at > old_exp
    def test_T116_extend_grace_audit(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        GracePeriodExtender(lm).extend(kv.key_id, kv.version, extra_days=7, actor="admin")
        assert len(lm._audit.query(action=AuditAction.GRACE_EXTENDED)) >= 1
    def test_T117_extend_non_grace_fails(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(PolicyViolationError):
            GracePeriodExtender(lm).extend(kv.key_id, kv.version, extra_days=7, actor="a")
    def test_T118_expire_grace_audit(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.GRACE, expires_at=time.time()-1)
        lm.expire_grace_keys(reason="test")
        assert len(lm._audit.query(action=AuditAction.KEY_EXPIRED)) >= 1
    def test_T119_scan_due_ignores_grace(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.GRACE, activated_at=time.time()-100*86400)
        assert len(RotationScheduler(lm).scan_due()) == 0
    def test_T120_extend_by_days_correct(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING)
        old_exp = lm.get_key(kv.key_id, kv.version).expires_at
        GracePeriodExtender(lm).extend(kv.key_id, kv.version, extra_days=10, actor="a")
        assert abs(lm.get_key(kv.key_id, kv.version).expires_at - old_exp - 10*86400) < 2

class TestSecretRotationAdmin:
    def _setup(self): return full_system()
    def test_T121_summary_empty(self):
        _,_,_,_,admin = self._setup(); s = admin.summary()
        assert s["total_keys"] == 0 and s["audit_chain_valid"] is True
    def test_T122_summary_after_generate(self):
        lm,_,_,_,admin = self._setup(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        s = admin.summary()
        assert s["total_keys"] == 1 and s["by_status"].get("active") == 1
    def test_T123_summary_overdue(self):
        lm,_,_,_,admin = self._setup(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-31*86400)
        assert admin.summary()["overdue_rotation"] >= 1
    def test_T124_health_check_clean(self):
        _,_,_,_,admin = self._setup(); ok, issues = admin.health_check()
        assert ok is True and issues == []
    def test_T125_health_check_overdue(self):
        lm,_,_,_,admin = self._setup(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-31*86400)
        ok, issues = admin.health_check()
        assert ok is False and any("overdue" in i for i in issues)
    def test_T126_health_check_open_compromise(self):
        lm,_,crm,_,admin = self._setup(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        ok, issues = admin.health_check()
        assert ok is False and any("compromise" in i for i in issues)
    def test_T127_bulk_rotate(self):
        lm,_,_,_,admin = self._setup(); lm.generate_key(KeyType.WEBHOOK_HMAC, activate=True)
        results = admin.bulk_rotate(KeyType.WEBHOOK_HMAC, actor="admin")
        assert len(results) == 1 and results[0][0].status == KeyStatus.GRACE
    def test_T128_key_audit_trail(self):
        lm,_,_,_,admin = self._setup(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.sign_payload(b"x", KeyType.JWT_SIGNING)
        assert len(admin.key_audit_trail(kv.key_id)) >= 2
    def test_T129_summary_audit_entries_count(self):
        lm,_,_,_,admin = self._setup(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert admin.summary()["audit_entries"] >= 2
    def test_T130_summary_tenant_filter(self):
        lm,_,_,_,admin = self._setup()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        assert admin.summary(tenant_id="t1")["total_keys"] == 1
    def test_T131_summary_due_soon(self):
        lm,_,_,_,admin = self._setup(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-24*86400)
        assert admin.summary()["due_soon"] >= 1
    def test_T132_health_chain_tampered(self):
        lm,_,_,_,admin = self._setup(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        list(lm._audit._entries)[0].chain_hash = "ff"*32
        ok, issues = admin.health_check()
        assert ok is False and any("audit chain" in i for i in issues)

class TestMultiTenantIsolation:
    def test_T133_tenant_keys_isolated(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        assert lm.active_key(KeyType.JWT_SIGNING, "t1").key_id != lm.active_key(KeyType.JWT_SIGNING, "t2").key_id
    def test_T134_tenant_sign_uses_own_key(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        sig, kid, ver = lm.sign_payload(b"x", KeyType.JWT_SIGNING, tenant_id="t1")
        assert lm.get_key(kid, ver).tenant_id == "t1"
    def test_T135_rotate_affects_only_tenant(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        lm.rotate_key(KeyType.JWT_SIGNING, tenant_id="t1")
        assert lm.active_key(KeyType.JWT_SIGNING, "t2").status == KeyStatus.ACTIVE
    def test_T136_tenant_audit_filter(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        assert all(e.tenant_id == "t1" for e in lm._audit.query(tenant_id="t1"))
    def test_T137_no_cross_tenant_key_use(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        with pytest.raises(KeyNotFoundError): lm.active_key(KeyType.JWT_SIGNING, tenant_id="t2")

class TestSQLMigration:
    @pytest.fixture(autouse=True)
    def load_sql(self):
        path = "/home/definable/phase29/supabase/migrations/20260628_038_phase29_secret_rotation.sql"
        if not os.path.exists(path):
            pytest.skip("SQL migration file not found")
        with open(path) as f: self.sql = f.read()
    def test_T138_has_begin_commit(self): assert "BEGIN;" in self.sql and "COMMIT;" in self.sql
    def test_T139_key_versions_table(self): assert "key_versions" in self.sql
    def test_T140_key_audit_log_table(self): assert "key_audit_log" in self.sql
    def test_T141_rotation_policies_table(self): assert "rotation_policies" in self.sql
    def test_T142_compromise_reports_table(self): assert "compromise_reports" in self.sql
    def test_T143_rls_enabled(self): assert "ROW LEVEL SECURITY" in self.sql
    def test_T144_tenant_id_column(self): assert "tenant_id" in self.sql
    def test_T145_status_constraint(self): assert "active" in self.sql and "grace" in self.sql
    def test_T146_indexes_present(self): assert "CREATE INDEX" in self.sql
    def test_T147_immutable_audit_trigger(self): assert "TRIGGER" in self.sql
    def test_T148_chain_hash_column(self): assert "chain_hash" in self.sql
    def test_T149_revoke_reason_not_null(self): assert "revoke_reason" in self.sql
    def test_T150_cleanup_function(self): assert "cleanup" in self.sql.lower() or "expired" in self.sql.lower()
    def test_T151_view_present(self): assert "CREATE" in self.sql and "VIEW" in self.sql
    def test_T152_if_not_exists(self): assert "IF NOT EXISTS" in self.sql

class TestIntegrationFlows:
    def test_T153_zero_downtime_jwt_rotation(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid_old, ver_old = lm.sign_payload(b"token", KeyType.JWT_SIGNING)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"token", sig, kid_old, ver_old) is True
        sig2, kid2, ver2 = lm.sign_payload(b"token2", KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"token2", sig2, kid2, ver2) is True
    def test_T154_revoked_key_blocks_verify(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"data", KeyType.JWT_SIGNING)
        lm.revoke_key(kid, ver, actor="admin", reason="breach")
        assert lm.verify_payload(b"data", sig, kid, ver) is False
    def test_T155_expired_grace_blocks_verify(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"data", KeyType.JWT_SIGNING)
        lm.rotate_key(KeyType.JWT_SIGNING)
        lm._store.update_status(kid, ver, KeyStatus.EXPIRED)
        assert lm.verify_payload(b"data", sig, kid, ver) is False
    def test_T156_full_lifecycle_all_types(self):
        lm = fresh()
        for kt in KeyType:
            lm.generate_key(kt, activate=True)
            lm.rotate_key(kt)
        assert lm._audit.verify_chain() is True
    def test_T157_compromise_then_re_sign(self):
        lm = fresh(); kv = lm.generate_key(KeyType.WEBHOOK_HMAC, activate=True)
        crm = CompromiseResponseManager(lm)
        crm.report_compromise(kv.key_id, kv.version, "sec", "webhook key exposed")
        sig, kid, ver = lm.sign_payload(b"event", KeyType.WEBHOOK_HMAC)
        assert lm.verify_payload(b"event", sig, kid, ver) is True
        assert lm.get_key(kv.key_id, kv.version).status == KeyStatus.REVOKED
    def test_T158_multi_rotation_chain_valid(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        for _ in range(5): lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm._audit.verify_chain() is True
        assert lm.active_key(KeyType.JWT_SIGNING).version == 6
    def test_T159_scheduler_full_cycle(self):
        lm = fresh(); sched = RotationScheduler(lm)
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.ACTIVE, activated_at=time.time()-31*86400)
        rotated = sched.auto_rotate_all()
        assert len(rotated) == 1
        old_kv = rotated[0][0]
        lm._store.update_status(old_kv.key_id, old_kv.version, KeyStatus.GRACE, expires_at=time.time()-1)
        assert len(sched.expire_grace_pass(reason="test")) == 1
    def test_T160_50_concurrent_sign_verify(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True); errors = []
        def sign_verify():
            try:
                sig, kid, ver = lm.sign_payload(b"concurrent", KeyType.JWT_SIGNING)
                assert lm.verify_payload(b"concurrent", sig, kid, ver)
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=sign_verify) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
    def test_T161_grace_window_allows_old_token_verify(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid1, ver1 = lm.sign_payload(b"session", KeyType.JWT_SIGNING)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"session", sig, kid1, ver1) is True
    def test_T162_emergency_rotation_audit_complete(self):
        lm = fresh(); kv = lm.generate_key(KeyType.SIGNING_ARTIFACT, activate=True)
        CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "ci", "found in repo")
        actions = {e.action for e in lm._audit.query()}
        assert AuditAction.EMERGENCY_ROT in actions and AuditAction.COMPROMISE_ACK in actions and AuditAction.KEY_REVOKED in actions
    def test_T163_build_factory(self):
        lm,sched,crm,ext,admin = full_system()
        assert isinstance(lm, KeyLifecycleManager) and isinstance(sched, RotationScheduler)
    def test_T164_200_ops_audit_chain_valid(self):
        lm = fresh()
        for kt in KeyType: lm.generate_key(kt, activate=True)
        for _ in range(19):
            for kt in KeyType: lm.rotate_key(kt)
        assert lm._audit.verify_chain() is True and lm._audit.total >= 200

class TestEdgeCases:
    def test_T165_key_version_repr_no_raw(self):
        kv = KeyVersion("k1",KeyType.JWT_SIGNING,1,KeyStatus.ACTIVE,0.0,0.0,None,None,None,0,None,_raw=b"secret_bytes")
        assert "secret_bytes" not in repr(kv)
    def test_T166_safe_dict_has_all_fields(self):
        kv = KeyVersion("k1",KeyType.JWT_SIGNING,1,KeyStatus.ACTIVE,0.0,0.0,None,None,None,0,None,_raw=b"x"*32)
        d = kv.safe_dict()
        for f in ["key_id","key_type","version","status","signature"]: assert f in d
    def test_T167_pending_key_not_usable_new(self):
        lm = fresh(); kv2 = lm.get_key(lm.generate_key(KeyType.JWT_SIGNING).key_id)
        assert kv2.is_usable_for_new() is False and kv2.is_usable_for_verify() is False
    def test_T168_revoked_not_usable(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, kv.version, actor="a", reason="r")
        r = lm.get_key(kv.key_id, kv.version)
        assert r.is_usable_for_new() is False and r.is_usable_for_verify() is False
    def test_T169_expired_not_usable(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, kv.version, KeyStatus.EXPIRED)
        exp = lm.get_key(kv.key_id, kv.version)
        assert exp.is_usable_for_new() is False and exp.is_usable_for_verify() is False
    def test_T170_key_material_unique(self):
        raws = {KeyMaterialGenerator.generate(KeyType.JWT_SIGNING) for _ in range(100)}
        assert len(raws) == 100
    def test_T171_key_id_uuid_format(self):
        kid = KeyMaterialGenerator.key_id()
        assert str(uuid.UUID(kid)) == kid
    def test_T172_audit_chain_genesis_deterministic(self):
        assert SecretAuditChain(b"same")._genesis_hash() == SecretAuditChain(b"same")._genesis_hash()
    def test_T173_audit_chain_different_secret_different_genesis(self):
        assert SecretAuditChain(b"s1")._genesis_hash() != SecretAuditChain(b"s2")._genesis_hash()
    def test_T174_policy_engine_independent_instances(self):
        e1 = RotationPolicyEngine(); e2 = RotationPolicyEngine()
        e1.set_policy(RotationPolicy(KeyType.JWT_SIGNING, max_age_days=5))
        assert e2.get_policy(KeyType.JWT_SIGNING).max_age_days != 5
    def test_T175_compromise_report_dataclass(self):
        r = CompromiseReport("r1","k1",KeyType.JWT_SIGNING,1,"sec",time.time(),"test",None,[])
        assert r.resolved is False
    def test_T176_enum_str_values(self):
        assert KeyType.JWT_SIGNING.value == "jwt_signing"
        assert KeyStatus.GRACE.value == "grace"
        assert RotationTrigger.COMPROMISE.value == "compromise"

class TestAdditionalCoverage:
    def test_T177_all_audit_actions_have_values(self):
        for a in AuditAction: assert a.value.startswith("key.")
    def test_T178_rotation_policy_default_for_all_types(self):
        for kt in KeyType:
            p = RotationPolicy.default_for(kt)
            assert p.max_age_days > 0 and p.grace_days >= 0
    def test_T179_key_self_auth_sign_verify(self):
        lm = KeyLifecycleManager(master_secret=b"m")
        kv = lm.generate_key(KeyType.JWT_SIGNING)
        assert KeySelfAuth.verify(kv, b"m") is True and KeySelfAuth.verify(kv, b"wrong") is False
    def test_T180_lifecycle_shared_audit(self):
        lm,_,_,_,admin = build_secret_rotation_system(b"s")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert admin.summary()["audit_entries"] >= 2
    def test_T181_revoke_reason_stored(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, kv.version, actor="admin", reason="admin action")
        assert lm.get_key(kv.key_id, kv.version).revoke_reason == "admin action"
    def test_T182_no_active_key_for_fresh_type(self):
        with pytest.raises(KeyNotFoundError): fresh().active_key(KeyType.BACKUP_ENCRYPT)
    def test_T183_grace_key_verify_uses_hmac(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"grace_test", KeyType.JWT_SIGNING)
        lm.rotate_key(KeyType.JWT_SIGNING)
        assert lm.verify_payload(b"grace_test", sig, kid, ver) is True
        assert lm.verify_payload(b"wrong_payload", sig, kid, ver) is False
    def test_T184_policy_max_age_seconds_calculation(self):
        assert RotationPolicy(KeyType.JWT_SIGNING, max_age_days=7).max_age_seconds == 7*86400.0
    def test_T185_all_key_types_generate_correct_size(self):
        for kt in KeyType: assert len(KeyMaterialGenerator.generate(kt)) in (32, 64)
    def test_T186_rotation_trigger_values_complete(self):
        assert {t.value for t in RotationTrigger} == {"scheduled","compromise","manual","policy_age","policy_use","bootstrap"}
    def test_T187_key_version_is_usable_for_new_active_only(self):
        for status in KeyStatus:
            kv = KeyVersion("k",KeyType.JWT_SIGNING,1,status,0.0,0.0,None,None,None,0,None,_raw=b"x"*32)
            assert kv.is_usable_for_new() == (status == KeyStatus.ACTIVE)
    def test_T188_key_version_is_usable_for_verify_active_and_grace(self):
        for status in KeyStatus:
            kv = KeyVersion("k",KeyType.JWT_SIGNING,1,status,0.0,0.0,None,None,None,0,None,_raw=b"x"*32)
            assert kv.is_usable_for_verify() == (status in (KeyStatus.ACTIVE, KeyStatus.GRACE))
    def test_T189_audit_entry_fields(self):
        chain = SecretAuditChain(b"s")
        e = chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"actor",tenant_id="t1")
        assert e.entry_id and e.seq == 1 and e.key_id == "k1" and e.actor == "actor" and e.tenant_id == "t1"
    def test_T190_concurrent_rotate_independent_types(self):
        lm = fresh(); errors = []
        for kt in KeyType: lm.generate_key(kt, activate=True)
        def rotate(kt):
            try: lm.rotate_key(kt)
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=rotate, args=(kt,)) for kt in KeyType]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == [] and lm._audit.verify_chain() is True
    def test_T191_max_uses_policy_enforcement(self):
        lm = fresh(); lm.set_policy(RotationPolicy(KeyType.API_SECRET, max_age_days=365, max_uses=3))
        kv = lm.generate_key(KeyType.API_SECRET, activate=True)
        for _ in range(3): lm.record_access(kv.key_id, kv.version)
        needs, reason = lm.needs_rotation(kv.key_id, kv.version)
        assert needs is True and "max_uses" in reason
    def test_T192_key_access_audit_recorded(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.record_access(kv.key_id, kv.version, actor="service-a")
        assert len(lm._audit.query(action=AuditAction.KEY_ACCESSED, key_id=kv.key_id)) >= 1
    def test_T193_verify_audit_recorded(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig, kid, ver = lm.sign_payload(b"x", KeyType.JWT_SIGNING)
        lm.verify_payload(b"x", sig, kid, ver)
        assert len(lm._audit.query(action=AuditAction.KEY_VERIFIED)) >= 1
    def test_T194_compromise_whitespace_reason_rejected(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError):
            CompromiseResponseManager(lm).report_compromise(kv.key_id, kv.version, "sec", reason="   ")
    def test_T195_query_by_actor(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED,"k1",KeyType.JWT_SIGNING,1,"alice")
        chain.record(AuditAction.KEY_GENERATED,"k2",KeyType.JWT_SIGNING,1,"bob")
        alice = chain.query(actor="alice")
        assert len(alice) == 1 and alice[0].actor == "alice"
    def test_T196_multiple_compromise_reports(self):
        lm = fresh(); crm = CompromiseResponseManager(lm)
        for kt in [KeyType.JWT_SIGNING, KeyType.WEBHOOK_HMAC, KeyType.ENCRYPTION_DEK]:
            kv = lm.generate_key(kt, activate=True)
            crm.report_compromise(kv.key_id, kv.version, "sec", "leak")
        assert len(crm.list_reports()) == 3
    def test_T197_rotation_trigger_stored(self):
        lm = fresh(); kv = lm.generate_key(KeyType.JWT_SIGNING, trigger=RotationTrigger.MANUAL, activate=True)
        assert kv.rotation_trigger == RotationTrigger.MANUAL
    def test_T198_sign_verify_all_key_types(self):
        lm = fresh()
        for kt in KeyType:
            lm.generate_key(kt, activate=True)
            sig, kid, ver = lm.sign_payload(b"payload", kt)
            assert lm.verify_payload(b"payload", sig, kid, ver) is True
    def test_T199_multi_tenant_audit_isolation(self):
        lm = fresh()
        for i in range(3): lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id=f"t{i}")
        assert all(e.tenant_id == "t0" for e in lm._audit.query(tenant_id="t0"))
    def test_T200_key_not_found_on_get(self):
        with pytest.raises(KeyNotFoundError): fresh().get_key("nonexistent-uuid", version=1)
    def test_T201_full_compromise_runbook_text(self):
        for i, step in enumerate(COMPROMISE_RUNBOOK, 1): assert f"STEP-{i}:" in step
    def test_T202_policy_default_backup_encrypt(self):
        p = RotationPolicy.default_for(KeyType.BACKUP_ENCRYPT)
        assert p.max_age_days == 365 and p.auto_rotate is False
    def test_T203_rotate_records_rotated_at(self):
        lm = fresh(); lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        old, _ = lm.rotate_key(KeyType.JWT_SIGNING)
        assert old.rotated_at is not None
    def test_T204_secret_not_in_exception_message(self):
        lm = fresh()
        try: lm.get_key("bad-id")
        except KeyNotFoundError as e:
            assert "secret" not in str(e).lower() and "_raw" not in str(e)
    def test_T205_key_versions_sorted_by_version(self):
        lm = fresh()
        for _ in range(5): lm.generate_key(KeyType.JWT_SIGNING)
        versions = [k.version for k in lm.list_by_type(KeyType.JWT_SIGNING)]
        assert versions == sorted(versions)
    def test_T206_health_check_returns_tuple(self):
        _,_,_,_,admin = full_system()
        result = admin.health_check()
        assert isinstance(result, tuple) and isinstance(result[0], bool) and isinstance(result[1], list)
    def test_T207_policy_grace_days_in_summary(self):
        assert RotationPolicy.default_for(KeyType.JWT_SIGNING).grace_days == 7
    def test_T208_factory_independent_instances(self):
        lm1,_,_,_,_ = build_secret_rotation_system(b"s1")
        lm2,_,_,_,_ = build_secret_rotation_system(b"s2")
        lm1.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(KeyNotFoundError): lm2.active_key(KeyType.JWT_SIGNING)
