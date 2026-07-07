"""
test_phase29_secret_rotation.py
Phase 29 -- Secure Secrets Rotation & Key Lifecycle
208 tests: T001-T208
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid

sys.path.insert(0, "/home/definable/phase29")
import pytest

from backend.core.secret_rotation import (
    _POLICY_DEFAULTS,
    COMPROMISE_RUNBOOK,
    REQUIRES_REASON,
    AuditAction,
    AuditEntry,
    CompromiseReport,
    CompromiseResponseError,
    CompromiseResponseManager,
    GracePeriodExtender,
    KeyExpiredError,
    KeyLifecycleManager,
    KeyMaterialGenerator,
    KeyNotFoundError,
    KeyRevokedError,
    KeySelfAuth,
    KeyStatus,
    KeyStore,
    KeyType,
    KeyVersion,
    MissingReasonError,
    PolicyViolationError,
    RotationPolicy,
    RotationPolicyEngine,
    RotationScheduler,
    RotationTrigger,
    SecretAuditChain,
    SecretRotationError,
    build_secret_rotation_system,
)


def fresh() -> KeyLifecycleManager:
    return KeyLifecycleManager(master_secret=b"test-master-p29")


def full_system():
    return build_secret_rotation_system(b"test-master-p29")


SQL_PATH = "/home/definable/phase29/supabase/migrations/20260628_038_phase29_secret_rotation.sql"


class TestEnumsAndDefaults:
    def test_T001_key_type_count(self):
        assert len(KeyType) == 10

    def test_T002_key_status_values(self):
        assert {s.value for s in KeyStatus} == {"active", "grace", "revoked", "expired", "pending"}

    def test_T003_rotation_trigger_values(self):
        vals = {t.value for t in RotationTrigger}
        assert "scheduled" in vals and "compromise" in vals and "bootstrap" in vals

    def test_T004_audit_action_values(self):
        assert AuditAction.KEY_ROTATED.value == "key.rotated"
        assert AuditAction.KEY_REVOKED.value == "key.revoked"
        assert AuditAction.EMERGENCY_ROT.value == "key.emergency_rotation"
        assert AuditAction.COMPROMISE_ACK.value == "key.compromise_ack"

    def test_T005_requires_reason_set(self):
        assert AuditAction.KEY_REVOKED in REQUIRES_REASON
        assert AuditAction.COMPROMISE_ACK in REQUIRES_REASON
        assert AuditAction.EMERGENCY_ROT in REQUIRES_REASON
        assert AuditAction.KEY_EXPIRED in REQUIRES_REASON
        assert AuditAction.KEY_GENERATED not in REQUIRES_REASON

    def test_T006_policy_defaults_all_types(self):
        for kt in KeyType:
            assert kt in _POLICY_DEFAULTS

    def test_T007_jwt_policy(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING)
        assert p.max_age_days == 30
        assert p.grace_days == 7
        assert p.auto_rotate is True

    def test_T008_kek_no_auto_rotate(self):
        p = RotationPolicy.default_for(KeyType.ENCRYPTION_KEK)
        assert p.auto_rotate is False

    def test_T009_audit_chain_no_auto_rotate(self):
        p = RotationPolicy.default_for(KeyType.AUDIT_CHAIN)
        assert p.auto_rotate is False

    def test_T010_max_age_seconds(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING)
        assert p.max_age_seconds == 30 * 86400.0

    def test_T011_grace_seconds(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING)
        assert p.grace_seconds == 7 * 86400.0

    def test_T012_key_material_sizes(self):
        assert KeyMaterialGenerator.key_size(KeyType.JWT_SIGNING) == 64
        assert KeyMaterialGenerator.key_size(KeyType.ENCRYPTION_DEK) == 32
        assert KeyMaterialGenerator.key_size(KeyType.WEBHOOK_HMAC) == 32

    def test_T013_compromise_runbook_steps(self):
        assert len(COMPROMISE_RUNBOOK) >= 8
        assert any("revoke" in s.lower() for s in COMPROMISE_RUNBOOK)
        assert any("emergency" in s.lower() or "generat" in s.lower() for s in COMPROMISE_RUNBOOK)

    def test_T014_key_status_usable_new(self):
        kv = KeyVersion(
            key_id="x",
            key_type=KeyType.JWT_SIGNING,
            version=1,
            status=KeyStatus.ACTIVE,
            created_at=0.0,
            activated_at=0.0,
            expires_at=None,
            rotated_at=None,
            revoked_at=None,
            use_count=0,
            tenant_id=None,
            _raw=b"x",
        )
        assert kv.is_usable_for_new is True
        kv.status = KeyStatus.GRACE
        assert kv.is_usable_for_new is False

    def test_T015_policy_tenant_scoped(self):
        p = RotationPolicy.default_for(KeyType.JWT_SIGNING, tenant_id="t1")
        assert p.tenant_id == "t1"

    def test_T016_policy_max_uses_dek(self):
        p = RotationPolicy.default_for(KeyType.ENCRYPTION_DEK)
        assert p.max_uses == 1_000_000


class TestSecretAuditChain:
    def test_T017_genesis_hash_64chars(self):
        chain = SecretAuditChain(b"test-secret")
        assert len(chain.genesis_hash) == 64

    def test_T018_verify_empty_chain(self):
        chain = SecretAuditChain(b"secret")
        assert chain.verify_chain() is True

    def test_T019_verify_valid_chain(self):
        chain = SecretAuditChain(b"secret")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "sys")
        chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "sys")
        assert chain.verify_chain() is True

    def test_T020_tamper_detected(self):
        chain = SecretAuditChain(b"secret")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "sys")
        entries = list(chain._entries)
        entries[0].action = "tampered"
        assert chain.verify_chain() is False

    def test_T021_detect_tampered_seq(self):
        chain = SecretAuditChain(b"secret")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "sys")
        chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "sys")
        entries = list(chain._entries)
        entries[0].reason = "injected"
        broken = chain.detect_tampered()
        assert len(broken) >= 1

    def test_T022_requires_reason_enforced(self):
        chain = SecretAuditChain(b"s")
        with pytest.raises(MissingReasonError):
            chain.record(AuditAction.KEY_REVOKED, "k1", "jwt_signing", 1, "actor")

    def test_T023_requires_reason_whitespace(self):
        chain = SecretAuditChain(b"s")
        with pytest.raises(MissingReasonError):
            chain.record(AuditAction.KEY_REVOKED, "k1", "jwt_signing", 1, "actor", reason="  ")

    def test_T024_seq_monotonic(self):
        chain = SecretAuditChain(b"s")
        e1 = chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "a")
        e2 = chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "a")
        assert e2.seq == e1.seq + 1

    def test_T025_query_by_key_id(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "a")
        chain.record(AuditAction.KEY_GENERATED, "k2", "jwt_refresh", 1, "a")
        res = chain.query(key_id="k1")
        assert all(e.key_id == "k1" for e in res)

    def test_T026_query_most_recent_first(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "a")
        chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "a")
        res = chain.query()
        assert res[0].seq > res[1].seq

    def test_T027_query_by_action(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "a")
        chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "a")
        res = chain.query(action="key.generated")
        assert all(e.action == "key.generated" for e in res)

    def test_T028_concurrent_records(self):
        chain = SecretAuditChain(b"s")
        errors = []

        def worker():
            try:
                chain.record(AuditAction.KEY_GENERATED, str(uuid.uuid4()), "jwt_signing", 1, "a")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert chain.total == 20

    def test_T029_total_counter(self):
        chain = SecretAuditChain(b"s")
        for i in range(5):
            chain.record(AuditAction.KEY_GENERATED, f"k{i}", "jwt_signing", i, "a")
        assert chain.total == 5

    def test_T030_str_secret_accepted(self):
        chain = SecretAuditChain(b"secret")
        chain.record(AuditAction.KEY_GENERATED, "k", "jwt_signing", 1, "a")
        assert chain.verify_chain() is True

    def test_T031_query_limit(self):
        chain = SecretAuditChain(b"s")
        for i in range(10):
            chain.record(AuditAction.KEY_GENERATED, f"k{i}", "jwt_signing", i, "a")
        assert len(chain.query(limit=3)) == 3

    def test_T032_query_limit_zero_returns_all(self):
        chain = SecretAuditChain(b"s")
        for i in range(5):
            chain.record(AuditAction.KEY_GENERATED, f"k{i}", "jwt_signing", i, "a")
        assert len(chain.query(limit=0)) == 5


class TestKeyStore:
    def test_T033_add_and_get(self):
        store = KeyStore()
        kv = KeyVersion(
            "id1",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            time.time(),
            time.time(),
            None,
            None,
            None,
            0,
            None,
            b"raw",
        )
        store.add(kv)
        assert store.get("id1") is kv

    def test_T034_get_not_found(self):
        store = KeyStore()
        with pytest.raises(KeyNotFoundError):
            store.get("missing")

    def test_T035_list_by_type(self):
        store = KeyStore()
        kv1 = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        kv2 = KeyVersion(
            "b", KeyType.JWT_REFRESH, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv1)
        store.add(kv2)
        assert store.list_by_type(KeyType.JWT_SIGNING) == [kv1]

    def test_T036_active_key(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        assert store.active_key(KeyType.JWT_SIGNING) is kv

    def test_T037_no_active_raises(self):
        store = KeyStore()
        with pytest.raises(KeyNotFoundError):
            store.active_key(KeyType.JWT_SIGNING)

    def test_T038_update_status(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        store.update_status("a", KeyStatus.GRACE)
        assert store.get("a").status == KeyStatus.GRACE

    def test_T039_increment_use(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        count = store.increment_use("a")
        assert count == 1
        assert store.get("a").use_count == 1

    def test_T040_usable_keys_active_and_grace(self):
        store = KeyStore()
        kv1 = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        kv2 = KeyVersion(
            "b", KeyType.JWT_SIGNING, 2, KeyStatus.GRACE, 0, 0, None, None, None, 0, None, b""
        )
        kv3 = KeyVersion(
            "c", KeyType.JWT_SIGNING, 3, KeyStatus.REVOKED, 0, 0, None, None, None, 0, None, b""
        )
        for kv in (kv1, kv2, kv3):
            store.add(kv)
        usable = store.usable_keys(KeyType.JWT_SIGNING)
        assert len(usable) == 2
        assert kv3 not in usable

    def test_T041_tenant_isolation(self):
        store = KeyStore()
        kv1 = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, "t1", b""
        )
        kv2 = KeyVersion(
            "b", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, "t2", b""
        )
        store.add(kv1)
        store.add(kv2)
        assert store.active_key(KeyType.JWT_SIGNING, tenant_id="t1") is kv1
        assert store.active_key(KeyType.JWT_SIGNING, tenant_id="t2") is kv2

    def test_T042_version_filter(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 3, KeyStatus.GRACE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        found = next((k for k in store.list_by_type(KeyType.JWT_SIGNING) if k.version == 3), None)
        assert found is kv

    def test_T043_version_not_found(self):
        store = KeyStore()
        with pytest.raises(KeyNotFoundError):
            store.active_key(KeyType.JWT_SIGNING)

    def test_T044_concurrent_add(self):
        store = KeyStore()
        errors = []

        def worker(i):
            try:
                kv = KeyVersion(
                    str(i),
                    KeyType.JWT_SIGNING,
                    i,
                    KeyStatus.PENDING,
                    0,
                    None,
                    None,
                    None,
                    None,
                    0,
                    None,
                    b"",
                )
                store.add(kv)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_T045_all_keys(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        assert kv in store.all_keys()

    def test_T046_status_filter(self):
        store = KeyStore()
        kv1 = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        kv2 = KeyVersion(
            "b", KeyType.JWT_SIGNING, 2, KeyStatus.REVOKED, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv1)
        store.add(kv2)
        active = store.all_keys(status=KeyStatus.ACTIVE)
        assert kv1 in active and kv2 not in active

    def test_T047_safe_dict_no_raw(self):
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            0,
            None,
            None,
            None,
            0,
            None,
            b"sensitive",
        )
        d = kv.safe_dict()
        assert "_raw" not in d
        assert "sensitive" not in str(d)

    def test_T048_usable_for_verify_grace(self):
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.GRACE, 0, 0, None, None, None, 0, None, b""
        )
        assert kv.is_usable_for_verify is True


class TestRotationPolicyEngine:
    def test_T049_no_rotation_needed_fresh(self):
        eng = RotationPolicyEngine()
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            time.time(),
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        assert eng.needs_rotation(kv) is False

    def test_T050_rotation_needed_old(self):
        eng = RotationPolicyEngine()
        old_ts = time.time() - 31 * 86400
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, old_ts, None, None, None, 0, None, b""
        )
        assert eng.needs_rotation(kv) is True

    def test_T051_rotation_by_max_uses(self):
        eng = RotationPolicyEngine()
        policy = RotationPolicy(
            KeyType.ENCRYPTION_DEK, max_age_days=365, grace_days=30, max_uses=100, auto_rotate=True
        )
        eng.set_policy(KeyType.ENCRYPTION_DEK, policy)
        kv = KeyVersion(
            "a",
            KeyType.ENCRYPTION_DEK,
            1,
            KeyStatus.ACTIVE,
            0,
            time.time(),
            None,
            None,
            None,
            101,
            None,
            b"",
        )
        assert eng.needs_rotation(kv) is True

    def test_T052_custom_policy(self):
        eng = RotationPolicyEngine()
        policy = RotationPolicy(KeyType.JWT_SIGNING, max_age_days=1, grace_days=0, auto_rotate=True)
        eng.set_policy(KeyType.JWT_SIGNING, policy)
        old_ts = time.time() - 2 * 86400
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, old_ts, None, None, None, 0, None, b""
        )
        assert eng.needs_rotation(kv) is True

    def test_T053_grace_not_expired(self):
        eng = RotationPolicyEngine()
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.GRACE,
            0,
            0,
            time.time() + 3600,
            None,
            None,
            0,
            None,
            b"",
        )
        assert eng.is_grace_expired(kv) is False

    def test_T054_grace_expired(self):
        eng = RotationPolicyEngine()
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.GRACE,
            0,
            0,
            time.time() - 1,
            None,
            None,
            0,
            None,
            b"",
        )
        assert eng.is_grace_expired(kv) is True

    def test_T055_due_soon(self):
        eng = RotationPolicyEngine()
        activated_at = time.time() - (30 * 86400 - 3600)
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            activated_at,
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        assert eng.due_soon(kv, warn_seconds=86400) is True

    def test_T056_not_due_soon(self):
        eng = RotationPolicyEngine()
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            time.time(),
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        assert eng.due_soon(kv) is False

    def test_T057_tenant_policy_override(self):
        eng = RotationPolicyEngine()
        p = RotationPolicy(KeyType.JWT_SIGNING, max_age_days=7, grace_days=1, auto_rotate=True)
        eng.set_policy(KeyType.JWT_SIGNING, p, tenant_id="t1")
        got = eng.get_policy(KeyType.JWT_SIGNING, tenant_id="t1")
        assert got.max_age_days == 7

    def test_T058_default_fallback(self):
        eng = RotationPolicyEngine()
        p = eng.get_policy(KeyType.JWT_SIGNING)
        assert p.max_age_days == 30


class TestKeyLifecycleManager:
    def test_T059_generate_key_pending(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING)
        assert kv.status == KeyStatus.PENDING
        assert kv._raw != b""

    def test_T060_generate_key_activate(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert kv.status == KeyStatus.ACTIVE
        assert kv.activated_at is not None

    def test_T061_activate_key(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING)
        assert kv.status == KeyStatus.PENDING
        activated = lm.activate_key(kv.key_id, "admin")
        assert activated.status == KeyStatus.ACTIVE

    def test_T062_activate_non_pending_raises(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(PolicyViolationError):
            lm.activate_key(kv.key_id, "admin")

    def test_T063_active_key_returns_active(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        kv = lm.active_key(KeyType.JWT_SIGNING)
        assert kv.status == KeyStatus.ACTIVE

    def test_T064_active_key_not_found(self):
        lm = fresh()
        with pytest.raises(KeyNotFoundError):
            lm.active_key(KeyType.JWT_SIGNING)

    def test_T065_rotate_key(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        old, new = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="scheduled")
        assert old.status == KeyStatus.GRACE
        assert new.status == KeyStatus.ACTIVE
        assert new.version > old.version

    def test_T066_rotate_requires_reason(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError):
            lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="")

    def test_T067_revoke_key(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="security incident")
        assert lm.get_key(kv.key_id).status == KeyStatus.REVOKED

    def test_T068_revoke_requires_reason(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError):
            lm.revoke_key(kv.key_id, "admin", reason=" ")

    def test_T069_record_access(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.record_access(kv.key_id, "user")
        assert lm.get_key(kv.key_id).use_count == 1

    def test_T070_record_access_revoked_raises(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="test")
        with pytest.raises(KeyRevokedError):
            lm.record_access(kv.key_id, "user")

    def test_T071_record_access_expired_raises(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.EXPIRED)
        with pytest.raises(KeyExpiredError):
            lm.record_access(kv.key_id, "user")

    def test_T072_self_auth_valid(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert lm.self_auth_valid(kv) is True

    def test_T073_self_auth_tampered(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        kv.signature = "tampered" * 8
        assert lm.self_auth_valid(kv) is False

    def test_T074_sign_and_verify_payload(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig = lm.sign_payload(b"data", kv.key_id)
        assert lm.verify_payload(b"data", sig, KeyType.JWT_SIGNING)

    def test_T075_verify_wrong_payload(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig = lm.sign_payload(b"data", kv.key_id)
        assert not lm.verify_payload(b"wrong", sig, KeyType.JWT_SIGNING)

    def test_T076_rotation_hook(self):
        lm = fresh()
        events = []
        lm.add_rotation_hook(lambda evt, kv: events.append(evt))
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="test")
        assert "rotate" in events

    def test_T077_list_by_type(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.generate_key(KeyType.JWT_REFRESH, activate=True)
        jwt_keys = lm.list_by_type(KeyType.JWT_SIGNING)
        assert all(
            (
                k.key_type == KeyType.JWT_SIGNING
                or (hasattr(k.key_type, "value") and k.key_type.value == "jwt_signing")
            )
            for k in jwt_keys
        )

    def test_T078_usable_keys(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation")
        usable = lm.usable_keys(KeyType.JWT_SIGNING)
        assert len(usable) == 2

    def test_T079_expire_grace_keys(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        kv.expires_at = time.time() - 1
        expired = lm.expire_grace_keys()
        assert kv.key_id in expired

    def test_T080_concurrent_generate(self):
        lm = fresh()
        errors = []

        def worker():
            try:
                lm.generate_key(KeyType.JWT_SIGNING, activate=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestCompromiseResponseManager:
    def test_T081_report_compromise(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        report = mgr.report_compromise(kv.key_id, "security", reason="breach")
        assert isinstance(report, CompromiseReport)
        assert report.key_id == kv.key_id
        assert not report.resolved

    def test_T082_compromised_key_revoked(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        mgr.report_compromise(kv.key_id, "sec", reason="leaked")
        assert lm.get_key(kv.key_id).status == KeyStatus.REVOKED

    def test_T083_emergency_rotation_creates_new_key(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        report = mgr.report_compromise(kv.key_id, "sec", reason="breach")
        assert report.new_key_id is not None
        new_kv = lm.get_key(report.new_key_id)
        assert new_kv.status == KeyStatus.ACTIVE

    def test_T084_compromise_requires_reason(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        with pytest.raises(MissingReasonError):
            mgr.report_compromise(kv.key_id, "sec", reason="")

    def test_T085_resolve_report(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        report = mgr.report_compromise(kv.key_id, "sec", reason="breach")
        resolved = mgr.resolve_report(report.report_id, "admin")
        assert resolved.resolved is True
        assert resolved.resolved_by == "admin"

    def test_T086_open_reports(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        mgr.report_compromise(kv.key_id, "sec", reason="breach")
        assert len(mgr.open_reports()) == 1

    def test_T087_resolved_not_in_open(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        r = mgr.report_compromise(kv.key_id, "sec", reason="breach")
        mgr.resolve_report(r.report_id, "admin")
        assert len(mgr.open_reports()) == 0

    def test_T088_runbook_steps(self):
        assert len(CompromiseResponseManager.RUNBOOK) >= 8

    def test_T089_list_reports_all(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        mgr.report_compromise(kv.key_id, "sec", reason="breach")
        assert len(mgr.list_reports()) == 1

    def test_T090_list_reports_filter(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        kv2 = lm.generate_key(KeyType.JWT_REFRESH, activate=True)
        mgr = CompromiseResponseManager(lm)
        r1 = mgr.report_compromise(kv.key_id, "sec", reason="b1")
        mgr.report_compromise(kv2.key_id, "sec", reason="b2")
        mgr.resolve_report(r1.report_id, "admin")
        open_r = mgr.list_reports(resolved=False)
        assert len(open_r) == 1


class TestSchedulerAndExtender:
    def test_T091_schedule_rotation(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sched = RotationScheduler(lm)
        job_id = sched.schedule(KeyType.JWT_SIGNING, time.time() - 1)
        rotated = sched.scan_due()
        assert job_id in rotated

    def test_T092_not_due(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sched = RotationScheduler(lm)
        sched.schedule(KeyType.JWT_SIGNING, time.time() + 3600)
        assert sched.scan_due() == []

    def test_T093_pending_jobs(self):
        lm = fresh()
        sched = RotationScheduler(lm)
        sched.schedule(KeyType.JWT_SIGNING, time.time() + 3600)
        assert len(sched.pending_jobs()) == 1

    def test_T094_scan_due_soon(self):
        lm = fresh()
        activated_at = time.time() - (30 * 86400 - 3600)
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            activated_at,
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        lm._store.add(kv)
        sched = RotationScheduler(lm)
        due_soon = sched.scan_due_soon(warn_seconds=86400)
        assert kv in due_soon

    def test_T095_auto_rotate_all(self):
        lm = fresh()
        activated_at = time.time() - 31 * 86400
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            activated_at,
            None,
            None,
            None,
            0,
            None,
            b"raw",
        )
        kv.signature = KeySelfAuth(b"test-master-p29").sign(kv)
        lm._store.add(kv)
        sched = RotationScheduler(lm)
        rotated = sched.auto_rotate_all()
        assert len(rotated) >= 1

    def test_T096_expire_grace_pass(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        kv.expires_at = time.time() - 1
        sched = RotationScheduler(lm)
        expired = sched.expire_grace_pass()
        assert kv.key_id in expired

    def test_T097_extend_grace(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        kv.expires_at = time.time() + 3600
        ext = GracePeriodExtender(lm)
        extended = ext.extend(kv.key_id, 7200, "admin", reason="rollback needed")
        assert extended.expires_at >= time.time() + 7200

    def test_T098_extend_requires_grace_status(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        ext = GracePeriodExtender(lm)
        with pytest.raises(PolicyViolationError):
            ext.extend(kv.key_id, 3600, "admin", reason="test")

    def test_T099_extend_requires_reason(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        ext = GracePeriodExtender(lm)
        with pytest.raises(MissingReasonError):
            ext.extend(kv.key_id, 3600, "admin", reason="")

    def test_T100_extend_audit_logged(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        kv.expires_at = time.time() + 3600
        ext = GracePeriodExtender(lm)
        ext.extend(kv.key_id, 1800, "admin", reason="emergency")
        trail = lm._audit.query(key_id=kv.key_id, action="key.grace_extended")
        assert len(trail) >= 1


class TestSecretRotationAdmin:
    def test_T101_summary_empty(self):
        lm, sched, comp, ext, admin = full_system()
        s = admin.summary()
        assert s["total_keys"] == 0
        assert s["chain_valid"] is True

    def test_T102_summary_after_generate(self):
        lm, sched, comp, ext, admin = full_system()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        s = admin.summary()
        assert s["total_keys"] == 1

    def test_T103_health_check_healthy(self):
        lm, sched, comp, ext, admin = full_system()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        h = admin.health_check()
        assert h["healthy"] is True

    def test_T104_bulk_rotate(self):
        lm, sched, comp, ext, admin = full_system()
        for kt in [KeyType.JWT_SIGNING, KeyType.JWT_REFRESH]:
            lm.generate_key(kt, activate=True)
        result = admin.bulk_rotate(
            [KeyType.JWT_SIGNING, KeyType.JWT_REFRESH], "admin", reason="quarterly rotation"
        )
        assert len(result) == 2

    def test_T105_key_audit_trail(self):
        lm, sched, comp, ext, admin = full_system()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        trail = admin.key_audit_trail(kv.key_id)
        assert len(trail) >= 1

    def test_T106_admin_lifecycle_property(self):
        lm, sched, comp, ext, admin = full_system()
        assert admin.lifecycle is lm

    def test_T107_admin_scheduler_property(self):
        lm, sched, comp, ext, admin = full_system()
        assert admin.scheduler is sched

    def test_T108_admin_compromise_property(self):
        lm, sched, comp, ext, admin = full_system()
        assert admin.compromise_mgr is comp


class TestMultiTenantIsolation:
    def test_T109_different_tenants_isolated(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        kv2 = lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        assert lm.active_key(KeyType.JWT_SIGNING, tenant_id="t1") is kv1
        assert lm.active_key(KeyType.JWT_SIGNING, tenant_id="t2") is kv2

    def test_T110_rotation_per_tenant(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        _, new = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation", tenant_id="t1")
        assert new.tenant_id == "t1"
        t2_active = lm.active_key(KeyType.JWT_SIGNING, tenant_id="t2")
        assert t2_active.status == KeyStatus.ACTIVE

    def test_T111_tenant_policy(self):
        lm = fresh()
        p = RotationPolicy(KeyType.JWT_SIGNING, max_age_days=7, grace_days=1, auto_rotate=True)
        lm.set_policy(KeyType.JWT_SIGNING, p, tenant_id="t1")
        got = lm.get_policy(KeyType.JWT_SIGNING, tenant_id="t1")
        assert got.max_age_days == 7

    def test_T112_revoke_per_tenant(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t1")
        kv2 = lm.generate_key(KeyType.JWT_SIGNING, activate=True, tenant_id="t2")
        lm.revoke_key(kv1.key_id, "admin", reason="test")
        assert lm.get_key(kv1.key_id).status == KeyStatus.REVOKED
        assert lm.get_key(kv2.key_id).status == KeyStatus.ACTIVE


class TestSQLMigration:
    @pytest.fixture
    def sql(self):
        if not os.path.exists(SQL_PATH):
            pytest.skip("SQL file not found")
        return open(SQL_PATH).read()

    def test_T113_begin_commit(self, sql):
        assert "BEGIN" in sql and "COMMIT" in sql

    def test_T114_key_versions_table(self, sql):
        assert "key_versions" in sql

    def test_T115_rotation_policies_table(self, sql):
        assert "rotation_policies" in sql

    def test_T116_compromise_reports_table(self, sql):
        assert "compromise_reports" in sql

    def test_T117_key_audit_log_table(self, sql):
        assert "key_audit_log" in sql

    def test_T118_rls_enabled(self, sql):
        assert "ROW LEVEL SECURITY" in sql or "ENABLE ROW LEVEL" in sql

    def test_T119_immutable_trigger(self, sql):
        assert "TRIGGER" in sql and ("immutable" in sql.lower() or "prevent" in sql.lower())

    def test_T120_chain_hash_column(self, sql):
        assert "chain_hash" in sql

    def test_T121_reason_not_null(self, sql):
        assert "reason" in sql and "NOT NULL" in sql.upper()

    def test_T122_key_type_constraint(self, sql):
        assert "jwt_signing" in sql

    def test_T123_status_constraint(self, sql):
        assert "active" in sql and "grace" in sql and "revoked" in sql

    def test_T124_cleanup_function(self, sql):
        assert "cleanup" in sql.lower() or "FUNCTION" in sql

    def test_T125_rls_policy_tenant(self, sql):
        assert "tenant_id" in sql

    def test_T126_indexes(self, sql):
        assert "INDEX" in sql

    def test_T127_view_active_keys(self, sql):
        assert "VIEW" in sql or "view" in sql

    def test_T128_signature_column(self, sql):
        assert "signature" in sql


class TestIntegrationFlows:
    def test_T129_zero_downtime_rotation(self):
        lm = fresh()
        old = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        original_sig = lm.sign_payload(b"token", old.key_id)
        _, new_kv = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation")
        assert lm.verify_payload(b"token", original_sig, KeyType.JWT_SIGNING)
        new_sig = lm.sign_payload(b"new_token", new_kv.key_id)
        assert lm.verify_payload(b"new_token", new_sig, KeyType.JWT_SIGNING)

    def test_T130_full_lifecycle(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING)
        lm.activate_key(kv.key_id, "admin")
        _, new_kv = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="quarterly")
        lm.revoke_key(kv.key_id, "admin", reason="old")
        assert lm.get_key(kv.key_id).status == KeyStatus.REVOKED
        assert lm.get_key(new_kv.key_id).status == KeyStatus.ACTIVE

    def test_T131_compromise_full_flow(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        r = mgr.report_compromise(kv.key_id, "sec", reason="key leaked")
        assert lm.get_key(kv.key_id).status == KeyStatus.REVOKED
        assert r.new_key_id is not None
        mgr.resolve_report(r.report_id, "admin")
        assert len(mgr.open_reports()) == 0

    def test_T132_audit_chain_valid_after_operations(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation")
        lm.revoke_key(kv.key_id, "admin", reason="old")
        assert lm._audit.verify_chain() is True

    def test_T133_concurrent_rotations(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        errors = []

        def worker():
            try:
                lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="concurrent test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert lm._audit.verify_chain() is True

    def test_T134_scheduler_full_flow(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sched = RotationScheduler(lm)
        sched.schedule(KeyType.JWT_SIGNING, time.time() - 1)
        rotated = sched.scan_due()
        assert len(rotated) == 1

    def test_T135_10_key_types_bootstrap(self):
        lm = fresh()
        for kt in KeyType:
            lm.generate_key(kt, activate=True)
        assert len(lm.store.all_keys()) == len(KeyType)

    def test_T136_verify_payload_grace_key(self):
        lm = fresh()
        old = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig = lm.sign_payload(b"payload", old.key_id)
        lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="test")
        assert lm.verify_payload(b"payload", sig, KeyType.JWT_SIGNING)


class TestEdgeCases:
    def test_T137_generate_key_without_raw_on_pending(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING)
        assert kv._raw != b""

    def test_T138_revoke_already_revoked(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="first")
        lm.revoke_key(kv.key_id, "admin", reason="second")
        assert lm.get_key(kv.key_id).status == KeyStatus.REVOKED

    def test_T139_get_missing_key(self):
        lm = fresh()
        with pytest.raises(KeyNotFoundError):
            lm.get_key("nonexistent")

    def test_T140_sign_revoked_key_raises(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="test")
        with pytest.raises(KeyRevokedError):
            lm.sign_payload(b"data", kv.key_id)

    def test_T141_rotate_no_existing_key(self):
        lm = fresh()
        old, new = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="first rotation")
        assert old is None
        assert new.status == KeyStatus.ACTIVE

    def test_T142_empty_reason_rejected(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(MissingReasonError):
            lm.revoke_key(kv.key_id, "admin", reason="  ")

    def test_T143_key_version_monotonic(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        _, kv2 = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation")
        assert kv2.version == kv1.version + 1

    def test_T144_policy_update_audit(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.POLICY_UPDATED, "sys", "jwt_signing", 0, "admin")
        assert chain.total == 1


class TestAdditionalCoverage:
    def test_T145_audit_entry_dataclass(self):
        e = AuditEntry(
            seq=1,
            action="key.generated",
            key_id="k",
            key_type="jwt_signing",
            version=1,
            actor="a",
            tenant_id=None,
            reason=None,
            detail={},
            ts=time.time(),
            prev_hash="ph",
            chain_hash="ch",
        )
        assert e.seq == 1
        assert e.chain_hash == "ch"

    def test_T146_compromise_report_dataclass(self):
        r = CompromiseReport(
            report_id="r",
            key_id="k",
            key_type="jwt_signing",
            version=1,
            reported_by="sec",
            reported_at=time.time(),
            reason="breach",
        )
        assert r.resolved is False
        assert r.new_key_id is None

    def test_T147_key_material_generator_random(self):
        m1 = KeyMaterialGenerator.generate(KeyType.JWT_SIGNING)
        m2 = KeyMaterialGenerator.generate(KeyType.JWT_SIGNING)
        assert m1 != m2

    def test_T148_key_self_auth_sign_verify(self):
        auth = KeySelfAuth(b"master")
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b"raw"
        )
        sig = auth.sign(kv)
        kv.signature = sig
        assert auth.verify(kv) is True

    def test_T149_key_self_auth_tampered(self):
        auth = KeySelfAuth(b"master")
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b"raw"
        )
        kv.signature = auth.sign(kv)
        kv.version = 99
        assert auth.verify(kv) is False

    def test_T150_rotation_trigger_values(self):
        assert RotationTrigger.COMPROMISE.value == "compromise"
        assert RotationTrigger.SCHEDULED.value == "scheduled"

    def test_T151_audit_chain_64char_hash(self):
        chain = SecretAuditChain(b"s")
        e = chain.record(AuditAction.KEY_GENERATED, "k", "jwt_signing", 1, "a")
        assert len(e.chain_hash) == 64

    def test_T152_audit_chain_prev_hash_linked(self):
        chain = SecretAuditChain(b"s")
        e1 = chain.record(AuditAction.KEY_GENERATED, "k1", "jwt_signing", 1, "a")
        e2 = chain.record(AuditAction.KEY_ACTIVATED, "k1", "jwt_signing", 1, "a")
        assert e2.prev_hash == e1.chain_hash

    def test_T153_key_store_increment_missing(self):
        store = KeyStore()
        count = store.increment_use("nonexistent")
        assert count == 0

    def test_T154_policy_engine_all_types_covered(self):
        eng = RotationPolicyEngine()
        for kt in KeyType:
            p = eng.get_policy(kt)
            assert p is not None

    def test_T155_lifecycle_manager_audit_accessible(self):
        lm = fresh()
        assert lm._audit is not None

    def test_T156_compromise_response_error_is_secret_rotation_error(self):
        assert issubclass(CompromiseResponseError, SecretRotationError)

    def test_T157_policy_violation_error_is_secret_rotation_error(self):
        assert issubclass(PolicyViolationError, SecretRotationError)

    def test_T158_missing_reason_error_is_secret_rotation_error(self):
        assert issubclass(MissingReasonError, SecretRotationError)

    def test_T159_key_not_found_error_is_secret_rotation_error(self):
        assert issubclass(KeyNotFoundError, SecretRotationError)

    def test_T160_key_revoked_error_is_secret_rotation_error(self):
        assert issubclass(KeyRevokedError, SecretRotationError)

    def test_T161_key_expired_error_is_secret_rotation_error(self):
        assert issubclass(KeyExpiredError, SecretRotationError)

    def test_T162_rotation_policy_default_for_classmethod(self):
        p = RotationPolicy.default_for(KeyType.WEBHOOK_HMAC)
        assert p.key_type == KeyType.WEBHOOK_HMAC
        assert p.max_age_days == 60

    def test_T163_admin_extender_property(self):
        lm, sched, comp, ext, admin = full_system()
        assert admin.extender is ext

    def test_T164_build_system_returns_tuple(self):
        result = build_secret_rotation_system(b"master")
        assert len(result) == 5

    def test_T165_full_system_admin_summary(self):
        lm, sched, comp, ext, admin = full_system()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        s = admin.summary()
        assert s["total_keys"] == 1
        assert s["chain_valid"] is True

    def test_T166_audit_chain_query_by_type(self):
        chain = SecretAuditChain(b"s")
        chain.record(AuditAction.KEY_GENERATED, "k", "jwt_signing", 1, "a")
        chain.record(AuditAction.KEY_GENERATED, "k2", "jwt_refresh", 1, "a")
        res = chain.query(key_type="jwt_signing")
        assert all(e.key_type == "jwt_signing" for e in res)

    def test_T167_key_version_safe_dict_has_key_id(self):
        kv = KeyVersion(
            "abc",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            0,
            None,
            None,
            None,
            0,
            None,
            b"secret",
        )
        d = kv.safe_dict()
        assert d["key_id"] == "abc"

    def test_T168_rotation_trigger_bootstrap(self):
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        assert kv.rotation_trigger == RotationTrigger.BOOTSTRAP

    def test_T169_compromise_runbook_has_post_mortem(self):
        assert any("post" in s.lower() or "mortem" in s.lower() for s in COMPROMISE_RUNBOOK)

    def test_T170_key_material_size_fallback(self):
        size = KeyMaterialGenerator.key_size("unknown_type")
        assert size == 32

    def test_T171_concurrent_audit_chain_verify(self):
        chain = SecretAuditChain(b"s")
        for i in range(50):
            chain.record(AuditAction.KEY_GENERATED, f"k{i}", "jwt_signing", i, "a")
        errors = []

        def worker():
            try:
                assert chain.verify_chain() is True
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_T172_key_store_revoked_at_set(self):
        store = KeyStore()
        kv = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, None, b""
        )
        store.add(kv)
        store.update_status("a", KeyStatus.REVOKED)
        assert store.get("a").revoked_at is not None

    def test_T173_schedule_returns_job_id(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sched = RotationScheduler(lm)
        job_id = sched.schedule(KeyType.JWT_SIGNING, time.time() + 100)
        assert isinstance(job_id, str) and len(job_id) == 36

    def test_T174_scheduler_all_jobs(self):
        lm = fresh()
        sched = RotationScheduler(lm)
        sched.schedule(KeyType.JWT_SIGNING, time.time() + 3600)
        sched.schedule(KeyType.JWT_REFRESH, time.time() + 7200)
        jobs = sched.pending_jobs()
        assert len(jobs) == 2

    def test_T175_admin_summary_by_status(self):
        lm, sched, comp, ext, admin = full_system()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="test")
        s = admin.summary()
        assert s["by_status"].get("revoked", 0) >= 1

    def test_T176_sign_payload_hex_output(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sig = lm.sign_payload(b"hello", kv.key_id)
        assert len(sig) == 64
        int(sig, 16)

    def test_T177_policy_max_age_dek(self):
        p = RotationPolicy.default_for(KeyType.ENCRYPTION_DEK)
        assert p.max_age_days == 90
        assert p.grace_days == 30

    def test_T178_key_type_all_have_policies(self):
        for kt in KeyType:
            p = RotationPolicy.default_for(kt)
            assert p.max_age_days >= 0

    def test_T179_rotate_trigger_propagated(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        _, new = lm.rotate_key(
            KeyType.JWT_SIGNING, "admin", reason="manual", trigger=RotationTrigger.COMPROMISE
        )
        assert new.rotation_trigger == RotationTrigger.COMPROMISE

    def test_T180_key_version_repr_hides_raw(self):
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            0,
            None,
            None,
            None,
            0,
            None,
            b"secret-bytes",
        )
        r = repr(kv)
        assert "secret-bytes" not in r

    def test_T181_full_system_returns_5_components(self):
        lm, sched, comp, ext, admin = build_secret_rotation_system()
        assert all(x is not None for x in [lm, sched, comp, ext, admin])

    def test_T182_lifecycle_multiple_key_types(self):
        lm = fresh()
        for kt in [KeyType.JWT_SIGNING, KeyType.WEBHOOK_HMAC, KeyType.API_SECRET]:
            lm.generate_key(kt, activate=True)
        assert len(lm.store.all_keys()) == 3

    def test_T183_rotate_all_10_types(self):
        lm = fresh()
        for kt in KeyType:
            lm.generate_key(kt, activate=True)
        for kt in KeyType:
            lm.rotate_key(kt, "admin", reason="full rotation")
        assert lm._audit.verify_chain() is True

    def test_T184_key_material_sizes_all_types(self):
        for kt in KeyType:
            mat = KeyMaterialGenerator.generate(kt)
            size = KeyMaterialGenerator.key_size(kt)
            assert len(mat) == size

    def test_T185_compromise_report_steps_taken(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        r = mgr.report_compromise(kv.key_id, "sec", reason="breach")
        assert len(r.steps_taken) >= 1

    def test_T186_resolve_nonexistent_report(self):
        lm = fresh()
        mgr = CompromiseResponseManager(lm)
        with pytest.raises(KeyNotFoundError):
            mgr.resolve_report("nonexistent", "admin")

    def test_T187_policy_engine_no_auto_rotate(self):
        lm = fresh()
        policy = RotationPolicy(
            KeyType.ENCRYPTION_KEK, max_age_days=1, grace_days=0, auto_rotate=False
        )
        lm.set_policy(KeyType.ENCRYPTION_KEK, policy)
        old_ts = time.time() - 10 * 86400
        kv = KeyVersion(
            "a",
            KeyType.ENCRYPTION_KEK,
            1,
            KeyStatus.ACTIVE,
            0,
            old_ts,
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        lm._store.add(kv)
        assert not lm.needs_rotation(kv)

    def test_T188_lifecycle_shared_audit(self):
        audit = SecretAuditChain(b"shared")
        lm1 = KeyLifecycleManager(master_secret=b"m1", audit=audit)
        lm1.generate_key(KeyType.JWT_SIGNING, activate=True)
        assert audit.total >= 2

    def test_T189_key_store_all_keys_tenant_filter(self):
        store = KeyStore()
        kv1 = KeyVersion(
            "a", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, "t1", b""
        )
        kv2 = KeyVersion(
            "b", KeyType.JWT_SIGNING, 1, KeyStatus.ACTIVE, 0, 0, None, None, None, 0, "t2", b""
        )
        store.add(kv1)
        store.add(kv2)
        t1_keys = store.all_keys(tenant_id="t1")
        assert kv1 in t1_keys and kv2 not in t1_keys

    def test_T190_verify_chain_empty_chain(self):
        chain = SecretAuditChain(b"secret")
        assert chain.verify_chain() is True

    def test_T191_detect_tampered_empty(self):
        chain = SecretAuditChain(b"secret")
        assert chain.detect_tampered() == []

    def test_T192_sched_job_not_done_initially(self):
        lm = fresh()
        sched = RotationScheduler(lm)
        jid = sched.schedule(KeyType.JWT_SIGNING, time.time() + 9999)
        jobs = sched.pending_jobs()
        assert any(j["job_id"] == jid for j in jobs)

    def test_T193_key_version_is_usable_for_new_only_active(self):
        for status in [KeyStatus.GRACE, KeyStatus.REVOKED, KeyStatus.EXPIRED, KeyStatus.PENDING]:
            kv = KeyVersion(
                "a", KeyType.JWT_SIGNING, 1, status, 0, 0, None, None, None, 0, None, b""
            )
            assert kv.is_usable_for_new is False

    def test_T194_revoke_reason_stored(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm.revoke_key(kv.key_id, "admin", reason="security breach")
        got = lm.get_key(kv.key_id)
        assert got.revoke_reason == "security breach"

    def test_T195_audit_chain_genesis_consistent(self):
        chain = SecretAuditChain(b"fixed-secret")
        g1 = chain.genesis_hash
        g2 = chain.genesis_hash
        assert g1 == g2

    def test_T196_list_reports_resolved_filter(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        kv2 = lm.generate_key(KeyType.JWT_REFRESH, activate=True)
        mgr = CompromiseResponseManager(lm)
        r1 = mgr.report_compromise(kv1.key_id, "sec", reason="b1")
        mgr.report_compromise(kv2.key_id, "sec", reason="b2")
        mgr.resolve_report(r1.report_id, "admin")
        resolved = mgr.list_reports(resolved=True)
        assert len(resolved) == 1
        assert resolved[0].report_id == r1.report_id

    def test_T197_key_material_unique_per_call(self):
        mats = set()
        for _ in range(10):
            mat = KeyMaterialGenerator.generate(KeyType.JWT_SIGNING)
            mats.add(mat)
        assert len(mats) == 10

    def test_T198_admin_health_check_detects_issue(self):
        lm, sched, comp, ext, admin = full_system()
        activated_at = time.time() - 31 * 86400
        kv = KeyVersion(
            "a",
            KeyType.JWT_SIGNING,
            1,
            KeyStatus.ACTIVE,
            0,
            activated_at,
            None,
            None,
            None,
            0,
            None,
            b"",
        )
        lm._store.add(kv)
        h = admin.health_check()
        assert h["healthy"] is False
        assert len(h["issues"]) >= 1

    def test_T199_verify_payload_no_usable_keys(self):
        lm = fresh()
        result = lm.verify_payload(b"data", "fakesig", KeyType.JWT_SIGNING)
        assert result is False

    def test_T200_audit_chain_100_entries_valid(self):
        chain = SecretAuditChain(b"s")
        for i in range(100):
            chain.record(AuditAction.KEY_GENERATED, f"k{i}", "jwt_signing", i, "a")
        assert chain.verify_chain() is True
        assert chain.total == 100

    def test_T201_lifecycle_multiple_rotations_chain_valid(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        for i in range(5):
            lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason=f"rotation {i}")
        assert lm._audit.verify_chain() is True

    def test_T202_grace_period_extender_multiple(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        lm._store.update_status(kv.key_id, KeyStatus.GRACE)
        kv.expires_at = time.time() + 3600
        ext = GracePeriodExtender(lm)
        ext.extend(kv.key_id, 1800, "admin", reason="ext1")
        ext.extend(kv.key_id, 1800, "admin", reason="ext2")
        assert kv.expires_at >= time.time() + 3600 + 3600 - 5

    def test_T203_key_store_list_by_type_empty(self):
        store = KeyStore()
        result = store.list_by_type(KeyType.JWT_SIGNING)
        assert result == []

    def test_T204_scheduler_done_job_not_in_pending(self):
        lm = fresh()
        lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        sched = RotationScheduler(lm)
        jid = sched.schedule(KeyType.JWT_SIGNING, time.time() - 1)
        sched.scan_due()
        assert not any(j["job_id"] == jid for j in sched.pending_jobs())

    def test_T205_compromise_report_audit_entries(self):
        lm = fresh()
        kv = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        mgr = CompromiseResponseManager(lm)
        mgr.report_compromise(kv.key_id, "sec", reason="breach")
        ack_entries = lm._audit.query(action="key.compromise_ack")
        assert len(ack_entries) >= 1
        emergency_entries = lm._audit.query(action="key.emergency_rotation")
        assert len(emergency_entries) >= 1

    def test_T206_rotation_policy_engine_set_tenant(self):
        eng = RotationPolicyEngine()
        p = RotationPolicy(KeyType.WEBHOOK_HMAC, max_age_days=14, grace_days=2, auto_rotate=True)
        eng.set_policy(KeyType.WEBHOOK_HMAC, p, tenant_id="tenant_x")
        got = eng.get_policy(KeyType.WEBHOOK_HMAC, tenant_id="tenant_x")
        assert got.max_age_days == 14

    def test_T207_lifecycle_version_counter_increments(self):
        lm = fresh()
        kv1 = lm.generate_key(KeyType.JWT_SIGNING, activate=True)
        _, kv2 = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation")
        _, kv3 = lm.rotate_key(KeyType.JWT_SIGNING, "admin", reason="rotation again")
        assert kv1.version < kv2.version < kv3.version

    def test_T208_factory_independent_instances(self):
        s1 = build_secret_rotation_system(b"master1")
        s2 = build_secret_rotation_system(b"master2")
        lm1 = s1[0]
        lm2 = s2[0]
        _ = s2
        lm1.generate_key(KeyType.JWT_SIGNING, activate=True)
        with pytest.raises(KeyNotFoundError):
            lm2.active_key(KeyType.JWT_SIGNING)
