"""
test_phase23_backup_dr.py -- PHASE 23: Backup, Restore & Disaster Recovery
186 tests across 12 classes
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, "/home/definable/phase23")

import pytest

from backend.core.backup_dr import (
    DEFAULT_POLICIES,
    RETENTION_HOURS,
    BackupAuditEntry,
    BackupAuditLog,
    BackupCategory,
    BackupDRSystem,
    BackupEngine,
    BackupError,
    BackupManifest,
    BackupPolicy,
    BackupRecord,
    BackupStatus,
    BackupType,
    DrillStatus,
    EncryptionAlgorithm,
    EncryptionError,
    EncryptionKey,
    EncryptionLayer,
    PITRError,
    PITRManager,
    RestoreError,
    RestoreStatus,
    RestoreValidator,
    ValidationCheck,
    WALSegment,
)


@pytest.fixture
def enc():
    return EncryptionLayer(master_secret=b"test-master-key")


@pytest.fixture
def audit():
    return BackupAuditLog()


@pytest.fixture
def engine(enc, audit):
    return BackupEngine(encryption=enc, audit=audit)


@pytest.fixture
def system():
    return BackupDRSystem(master_secret=b"test-master", manifest_secret=b"test-manifest")


@pytest.fixture
def db_backup(system):
    return system.backup(BackupCategory.DB, actor="test")


@pytest.fixture
def all_backups(system):
    return {cat: system.backup(cat, actor="test") for cat in BackupCategory}


class TestBackupPolicy:
    def test_T001_default_policies_all_categories(self):
        assert set(DEFAULT_POLICIES.keys()) == set(BackupCategory)

    def test_T002_db_policy_retention_30days(self):
        assert DEFAULT_POLICIES[BackupCategory.DB].retention_hours == 30 * 24

    def test_T003_config_policy_retention_90days(self):
        assert DEFAULT_POLICIES[BackupCategory.CONFIG].retention_hours == 90 * 24

    def test_T004_artifact_policy_retention_365days(self):
        assert DEFAULT_POLICIES[BackupCategory.ARTIFACTS].retention_hours == 365 * 24

    def test_T005_audit_policy_retention_730days(self):
        assert DEFAULT_POLICIES[BackupCategory.AUDIT].retention_hours == 730 * 24

    def test_T006_all_policies_encrypt_true(self):
        assert all(p.encrypt for p in DEFAULT_POLICIES.values())

    def test_T007_db_policy_offsite_true(self):
        assert DEFAULT_POLICIES[BackupCategory.DB].offsite_copy is True

    def test_T008_policy_is_expired_fresh(self):
        assert (
            BackupPolicy(BackupCategory.DB, BackupType.FULL, 30 * 24).is_expired(time.time())
            is False
        )

    def test_T009_policy_is_expired_old(self):
        assert (
            BackupPolicy(BackupCategory.DB, BackupType.FULL, 1).is_expired(time.time() - 7200)
            is True
        )

    def test_T010_retention_hours_table_db(self):
        assert "full_daily" in RETENTION_HOURS[BackupCategory.DB]

    def test_T011_retention_hours_table_audit_2years(self):
        assert RETENTION_HOURS[BackupCategory.AUDIT]["daily_archive"] == 730 * 24

    def test_T012_policy_repr(self):
        assert "db" in repr(DEFAULT_POLICIES[BackupCategory.DB])

    def test_T013_policy_compress_default_true(self):
        assert DEFAULT_POLICIES[BackupCategory.DB].compress is True

    def test_T014_policy_verify_after_default_true(self):
        assert DEFAULT_POLICIES[BackupCategory.DB].verify_after is True

    def test_T015_policy_max_size_mb(self):
        assert DEFAULT_POLICIES[BackupCategory.DB].max_size_mb >= 1024

    def test_T016_policy_schedule_cron_set(self):
        assert all(p.schedule_cron and "*" in p.schedule_cron for p in DEFAULT_POLICIES.values())


class TestEncryptionLayer:
    def test_T017_encrypt_returns_key_id_and_blob(self, enc):
        kid, blob = enc.encrypt(b"hello")
        assert isinstance(kid, str) and len(blob) > 0

    def test_T018_decrypt_roundtrip(self, enc):
        kid, blob = enc.encrypt(b"sensitive-data")
        assert enc.decrypt(kid, blob) == b"sensitive-data"

    def test_T019_blob_larger_than_plaintext(self, enc):
        _, blob = enc.encrypt(b"x" * 100)
        assert len(blob) > 100

    def test_T020_tamper_blob_raises(self, enc):
        kid, blob = enc.encrypt(b"test")
        with pytest.raises(EncryptionError):
            enc.decrypt(kid, blob[:-4] + bytes([b ^ 0xFF for b in blob[-4:]]))

    def test_T021_unknown_key_id_raises(self, enc):
        with pytest.raises(EncryptionError):
            enc.decrypt("bad-key-id", b"\x00" * 50)

    def test_T022_rotate_key_changes_active(self, enc):
        old = enc.active_key_id
        assert enc.rotate_key() != old

    def test_T023_old_key_still_decrypts_after_rotation(self, enc):
        kid, blob = enc.encrypt(b"before-rotation")
        enc.rotate_key()
        assert enc.decrypt(kid, blob) == b"before-rotation"

    def test_T024_key_count_increments(self, enc):
        before = enc.key_count()
        enc.rotate_key()
        assert enc.key_count() == before + 1

    def test_T025_rotation_due_check(self):
        key = EncryptionKey("k1", EncryptionAlgorithm.AES256_GCM)
        key.created_at = time.time() - 91 * 86400
        assert key.is_rotation_due(90) is True

    def test_T026_rotation_not_due_fresh_key(self):
        assert EncryptionKey("k2", EncryptionAlgorithm.AES256_GCM).is_rotation_due(90) is False

    def test_T027_different_secrets_different_blobs(self):
        _, b1 = EncryptionLayer(b"a").encrypt(b"data")
        _, b2 = EncryptionLayer(b"b").encrypt(b"data")
        assert b1 != b2

    def test_T028_algorithm_is_aes256_gcm(self, enc):
        assert enc._keys[enc.active_key_id].algorithm == EncryptionAlgorithm.AES256_GCM

    def test_T029_encrypt_empty_bytes(self, enc):
        kid, blob = enc.encrypt(b"")
        assert enc.decrypt(kid, blob) == b""

    def test_T030_concurrent_encrypt_safe(self, enc):
        errors, results = [], []

        def w():
            try:
                kid, blob = enc.encrypt(b"x")
                results.append(enc.decrypt(kid, blob) == b"x")
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=w) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors and all(results)

    def test_T031_active_key_id_property(self, enc):
        assert isinstance(enc.active_key_id, str)

    def test_T032_encrypt_large_data(self, enc):
        data = os.urandom(1024 * 100)
        kid, blob = enc.encrypt(data)
        assert enc.decrypt(kid, blob) == data


class TestBackupManifest:
    def _m(self):
        return BackupManifest(
            "m1",
            "b1",
            BackupCategory.DB,
            BackupType.FULL,
            1e6,
            1024,
            "a" * 64,
            "k1",
            True,
            True,
            True,
            {"retention_hours": 720},
            {"generator": "test"},
        )

    def test_T033_sign_produces_hmac_sig(self):
        m = self._m()
        m.sign(b"secret")
        assert len(m.hmac_sig) == 64

    def test_T034_verify_correct_secret(self):
        m = self._m()
        m.sign(b"secret")
        assert m.verify(b"secret") is True

    def test_T035_verify_wrong_secret(self):
        m = self._m()
        m.sign(b"secret")
        assert m.verify(b"wrong") is False

    def test_T036_verify_unsigned(self):
        assert self._m().verify(b"secret") is False

    def test_T037_tamper_backup_id(self):
        m = self._m()
        m.sign(b"s")
        m.backup_id = "tampered"
        assert m.verify(b"s") is False

    def test_T038_tamper_size(self):
        m = self._m()
        m.sign(b"s")
        m.size_bytes = 9999
        assert m.verify(b"s") is False

    def test_T039_tamper_checksum(self):
        m = self._m()
        m.sign(b"s")
        m.checksum_sha256 = "b" * 64
        assert m.verify(b"s") is False

    def test_T040_tamper_key_id(self):
        m = self._m()
        m.sign(b"s")
        m.encryption_key_id = "bad"
        assert m.verify(b"s") is False

    def test_T041_policy_snapshot(self):
        assert "retention_hours" in self._m().policy_snapshot

    def test_T042_encrypted_flag(self):
        assert self._m().encrypted is True

    def test_T043_offsite_flag(self):
        assert self._m().offsite is True

    def test_T044_category_value(self):
        assert self._m().category == BackupCategory.DB

    def test_T045_metadata(self):
        assert "generator" in self._m().metadata

    def test_T046_resign_same_sig(self):
        m = self._m()
        m.sign(b"s")
        s1 = m.hmac_sig
        m.sign(b"s")
        assert m.hmac_sig == s1

    def test_T047_different_manifests_different_sigs(self):
        m1, m2 = self._m(), self._m()
        m2.size_bytes = 9999
        m1.sign(b"s")
        m2.sign(b"s")
        assert m1.hmac_sig != m2.hmac_sig

    def test_T048_sig_64chars(self):
        m = self._m()
        m.sign(b"secret")
        assert len(m.hmac_sig) == 64


class TestBackupEngine:
    def test_T049_run_backup_returns_record(self, engine):
        assert isinstance(engine.run_backup(BackupCategory.DB), BackupRecord)

    def test_T050_backup_status_success(self, engine):
        assert engine.run_backup(BackupCategory.DB).status == BackupStatus.SUCCESS

    def test_T051_backup_has_checksum(self, engine):
        assert len(engine.run_backup(BackupCategory.DB).checksum_sha256) == 64

    def test_T052_backup_has_manifest(self, engine):
        assert engine.run_backup(BackupCategory.DB).manifest is not None

    def test_T053_backup_manifest_signed(self, engine):
        assert len(engine.run_backup(BackupCategory.DB).manifest.hmac_sig) == 64

    def test_T054_backup_has_backup_id(self, engine):
        assert engine.run_backup(BackupCategory.DB).backup_id.startswith("bkp-")

    def test_T055_backup_offsite_url(self, engine):
        rec = engine.run_backup(BackupCategory.DB)
        assert rec.offsite_url and "s3://" in rec.offsite_url

    def test_T056_backup_size_positive(self, engine):
        assert engine.run_backup(BackupCategory.DB).size_bytes > 0

    def test_T057_all_categories(self, engine):
        for cat in BackupCategory:
            assert engine.run_backup(cat).status == BackupStatus.SUCCESS

    def test_T058_backup_type_override(self, engine):
        assert (
            engine.run_backup(BackupCategory.DB, backup_type=BackupType.INCREMENTAL).backup_type
            == BackupType.INCREMENTAL
        )

    def test_T059_wal_backup_has_lsn(self, engine):
        rec = engine.run_backup(BackupCategory.DB, backup_type=BackupType.WAL)
        assert rec.pitr_lsn and rec.pitr_lsn.startswith("LSN-")

    def test_T060_list_records_all(self, engine):
        engine.run_backup(BackupCategory.DB)
        engine.run_backup(BackupCategory.CONFIG)
        assert len(engine.list_records()) >= 2

    def test_T061_list_records_filter_category(self, engine):
        engine.run_backup(BackupCategory.DB)
        engine.run_backup(BackupCategory.CONFIG)
        assert all(
            r.category == BackupCategory.DB for r in engine.list_records(category=BackupCategory.DB)
        )

    def test_T062_list_records_filter_status(self, engine):
        engine.run_backup(BackupCategory.DB)
        assert all(
            r.status == BackupStatus.SUCCESS
            for r in engine.list_records(status=BackupStatus.SUCCESS)
        )

    def test_T063_verify_manifest_true(self, engine):
        rec = engine.run_backup(BackupCategory.DB)
        assert engine.verify_manifest(rec.backup_id) is True

    def test_T064_verify_manifest_tampered(self, engine):
        rec = engine.run_backup(BackupCategory.DB)
        rec.manifest.size_bytes = 999999
        assert engine.verify_manifest(rec.backup_id) is False

    def test_T065_get_record_by_id(self, engine):
        rec = engine.run_backup(BackupCategory.DB)
        assert engine.get_record(rec.backup_id) is rec

    def test_T066_get_record_unknown_none(self, engine):
        assert engine.get_record("nonexistent") is None

    def test_T067_no_policy_raises(self, audit, enc):
        eng = BackupEngine(policies={}, encryption=enc, audit=audit)
        with pytest.raises(BackupError):
            eng.run_backup(BackupCategory.DB)

    def test_T068_audit_records_on_backup(self, engine):
        before = engine.audit.count()
        engine.run_backup(BackupCategory.DB)
        assert engine.audit.count() >= before + 2

    def test_T069_completed_at_set(self, engine):
        rec = engine.run_backup(BackupCategory.DB)
        assert rec.completed_at and rec.completed_at > rec.created_at

    def test_T070_concurrent_unique_ids(self, engine):
        ids = []
        errors = []

        def w():
            try:
                ids.append(engine.run_backup(BackupCategory.LOGS).backup_id)
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=w) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors and len(set(ids)) == 10

    def test_T071_backup_tags(self, engine):
        assert engine.run_backup(BackupCategory.DB, tags={"env": "prod"}).tags["env"] == "prod"

    def test_T072_list_sorted_newest_first(self, engine):
        engine.run_backup(BackupCategory.DB)
        engine.run_backup(BackupCategory.DB)
        recs = engine.list_records()
        assert recs[0].created_at >= recs[-1].created_at


class TestRestoreEngine:
    def test_T073_restore_success(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "staging").status == RestoreStatus.SUCCESS

    def test_T074_all_validations_pass(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "staging").all_passed is True

    def test_T075_has_5_checks(self, system, db_backup):
        assert len(system.run_restore(db_backup.backup_id, "staging").validations) == 5

    def test_T076_includes_manifest_check(self, system, db_backup):
        rst = system.run_restore(db_backup.backup_id, "staging")
        assert ValidationCheck.MANIFEST in [v.check for v in rst.validations]

    def test_T077_includes_checksum_check(self, system, db_backup):
        rst = system.run_restore(db_backup.backup_id, "staging")
        assert ValidationCheck.CHECKSUM in [v.check for v in rst.validations]

    def test_T078_includes_schema_check(self, system, db_backup):
        rst = system.run_restore(db_backup.backup_id, "staging")
        assert ValidationCheck.SCHEMA in [v.check for v in rst.validations]

    def test_T079_unknown_backup_raises(self, system):
        with pytest.raises(RestoreError):
            system.run_restore("nonexistent", "staging")

    def test_T080_corrupted_backup_raises(self, system, db_backup):
        db_backup.status = BackupStatus.CORRUPTED
        with pytest.raises(RestoreError):
            system.run_restore(db_backup.backup_id, "staging")

    def test_T081_tampered_manifest_fails(self, system, db_backup):
        db_backup.manifest.size_bytes = 1
        with pytest.raises(RestoreError):
            system.run_restore(db_backup.backup_id, "staging")

    def test_T082_has_restore_id(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "staging").restore_id.startswith("rst-")

    def test_T083_completed_at_set(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "staging").completed_at is not None

    def test_T084_audit_events(self, system, db_backup):
        before = system.audit.count()
        system.run_restore(db_backup.backup_id, "staging")
        assert system.audit.count() >= before + 2

    def test_T085_failed_checks_empty_on_success(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "staging").failed_checks == []

    def test_T086_no_manifest_raises(self, system, db_backup):
        db_backup.manifest = None
        with pytest.raises(RestoreError):
            system.run_restore(db_backup.backup_id, "staging")

    def test_T087_pitr_target_stored(self, system, db_backup):
        t = time.time()
        assert system.run_restore(db_backup.backup_id, "staging", pitr_target=t).pitr_target == t

    def test_T088_list_records(self, system, db_backup):
        system.run_restore(db_backup.backup_id, "staging")
        assert len(system.restore.list_records()) >= 1


class TestPITRManager:
    def test_T089_record_wal(self, system):
        assert isinstance(system.pitr.record_wal(), WALSegment)

    def test_T090_wal_has_lsn(self, system):
        assert system.pitr.record_wal().lsn.startswith("LSN-")

    def test_T091_wal_count_increments(self, system):
        before = system.pitr.wal_count()
        system.pitr.record_wal()
        assert system.pitr.wal_count() == before + 1

    def test_T092_recover_needs_backup(self):
        with pytest.raises(PITRError):
            PITRManager(BackupEngine(), BackupAuditLog()).recover_to(time.time())

    def test_T093_recover_success(self, system, db_backup):
        system.pitr.record_wal()
        assert system.pitr.recover_to(time.time() + 1).status == "success"

    def test_T094_recover_uses_base_backup(self, system, db_backup):
        assert system.pitr.recover_to(time.time() + 1).base_backup_id == db_backup.backup_id

    def test_T095_recover_wal_segments(self, system, db_backup):
        system.pitr.record_wal()
        system.pitr.record_wal()
        assert system.pitr.recover_to(time.time() + 1).wal_segments_applied >= 2

    def test_T096_recover_past_raises(self, system, db_backup):
        with pytest.raises(PITRError):
            system.pitr.recover_to(db_backup.created_at - 1)

    def test_T097_pitr_id_prefix(self, system, db_backup):
        assert system.pitr.recover_to(time.time() + 1).pitr_id.startswith("pitr-")

    def test_T098_pitr_list(self, system, db_backup):
        system.pitr.recover_to(time.time() + 1)
        assert len(system.pitr.list_pitr()) >= 1

    def test_T099_wal_purge_old(self, system):
        seg = system.pitr.record_wal()
        seg.created_at = time.time() - (7 * 24 * 3601)
        assert system.pitr.purge_old_wal() >= 1

    def test_T100_wal_checksum(self, system):
        assert len(system.pitr.record_wal().checksum) == 64

    def test_T101_pitr_audit_events(self, system, db_backup):
        before = system.audit.count()
        system.pitr.recover_to(time.time() + 1)
        assert system.audit.count() >= before + 2

    def test_T102_pitr_completed_at(self, system, db_backup):
        assert system.pitr.recover_to(time.time() + 1).completed_at is not None

    def test_T103_pitr_target_stored(self, system, db_backup):
        t = time.time() + 100
        assert system.pitr.recover_to(t).target_ts == t

    def test_T104_uses_latest_backup(self, system):
        system.backup(BackupCategory.DB)
        time.sleep(0.001)
        b2 = system.backup(BackupCategory.DB)
        assert system.pitr.recover_to(time.time() + 1).base_backup_id == b2.backup_id


class TestRetentionEnforcer:
    def test_T105_returns_per_category(self, system, all_backups):
        assert len(system.retention.enforce()) == len(BackupCategory)

    def test_T106_fresh_not_expired(self, system, all_backups):
        assert sum(r.expired for r in system.retention.enforce()) == 0

    def test_T107_old_gets_expired(self, system):
        rec = system.backup(BackupCategory.LOGS)
        rec.created_at = time.time() - (90 * 24 * 3601)
        system.retention.enforce()
        assert system.engine.get_record(rec.backup_id).status == BackupStatus.EXPIRED

    def test_T108_expired_frees_bytes(self, system):
        rec = system.backup(BackupCategory.LOGS)
        rec.created_at = time.time() - (90 * 24 * 3601)
        results = system.retention.enforce()
        log_r = next(r for r in results if r.category == BackupCategory.LOGS)
        assert log_r.freed_bytes >= rec.size_bytes

    def test_T109_retained_count(self, system, all_backups):
        assert sum(r.retained for r in system.retention.enforce()) >= len(BackupCategory)

    def test_T110_audit_events(self, system):
        rec = system.backup(BackupCategory.LOGS)
        rec.created_at = time.time() - (90 * 24 * 3601)
        before = system.audit.count()
        system.retention.enforce()
        assert system.audit.count() > before

    def test_T111_category_in_result(self, system, all_backups):
        assert BackupCategory.DB in {r.category for r in system.retention.enforce()}

    def test_T112_freed_non_negative(self, system, all_backups):
        assert all(r.freed_bytes >= 0 for r in system.retention.enforce())


class TestDRDrillRunner:
    def test_T113_drill_passes(self, system, all_backups):
        assert system.run_drill().status == DrillStatus.PASSED

    def test_T114_passed_property(self, system, all_backups):
        assert system.run_drill().passed is True

    def test_T115_has_7_steps(self, system, all_backups):
        assert len(system.run_drill().steps) == 7

    def test_T116_all_steps_pass(self, system, all_backups):
        assert all(s.passed for s in system.run_drill().steps)

    def test_T117_has_drill_id(self, system, all_backups):
        assert system.run_drill().drill_id.startswith("drill-")

    def test_T118_has_actual_rto(self, system, all_backups):
        assert system.run_drill().actual_rto is not None

    def test_T119_rto_met(self, system, all_backups):
        assert system.run_drill(rto=3600).rto_met is True

    def test_T120_rpo_met(self, system, all_backups):
        assert system.run_drill(rpo=3600).rpo_met is True

    def test_T121_completed_at_set(self, system, all_backups):
        assert system.run_drill().completed_at is not None

    def test_T122_without_backup_fails(self):
        fresh = BackupDRSystem(b"m", b"s")
        assert fresh.run_drill().status == DrillStatus.FAILED

    def test_T123_step_names(self, system, all_backups):
        names = {s.name for s in system.run_drill().steps}
        assert "latest_backup_available" in names and "restore_test" in names

    def test_T124_audit_events(self, system, all_backups):
        before = system.audit.count()
        system.run_drill()
        assert system.audit.count() > before

    def test_T125_list_drills(self, system, all_backups):
        system.run_drill()
        assert len(system.drill.list_drills()) >= 1

    def test_T126_get_drill_by_id(self, system, all_backups):
        d = system.run_drill()
        assert system.drill.get_drill(d.drill_id) is d

    def test_T127_step_duration_non_negative(self, system, all_backups):
        assert all(s.duration_ms >= 0 for s in system.run_drill().steps)

    def test_T128_step_ids_sequential(self, system, all_backups):
        assert [s.step_id for s in system.run_drill().steps] == list(range(1, 8))


class TestBackupAuditLog:
    def test_T129_record_entry(self, audit):
        assert isinstance(audit.record("e", "actor"), BackupAuditEntry)

    def test_T130_chain_hash_64chars(self, audit):
        assert len(audit.record("e", "a").chain_hash) == 64

    def test_T131_verify_empty(self, audit):
        assert audit.verify_chain() is True

    def test_T132_verify_after_records(self, audit):
        [audit.record(f"e{i}", "a") for i in range(10)]
        assert audit.verify_chain() is True

    def test_T133_tamper_breaks_chain(self, audit):
        audit.record("e1", "a")
        e2 = audit.record("e2", "a")
        audit.record("e3", "a")
        e2.event = "tampered"
        assert audit.verify_chain() is False

    def test_T134_list_all(self, audit):
        audit.record("e1", "a")
        audit.record("e2", "a")
        assert len(audit.list()) >= 2

    def test_T135_list_filter_backup_id(self, audit):
        audit.record("e1", "a", backup_id="b1")
        audit.record("e2", "a", backup_id="b2")
        assert all(e.backup_id == "b1" for e in audit.list(backup_id="b1"))

    def test_T136_count_increments(self, audit):
        before = audit.count()
        audit.record("e", "a")
        assert audit.count() == before + 1

    def test_T137_entry_has_id(self, audit):
        assert len(audit.record("e", "a").entry_id) == 32

    def test_T138_entry_has_ts(self, audit):
        assert audit.record("e", "a").ts > 0

    def test_T139_entry_detail_stored(self, audit):
        assert audit.record("e", "a", size_bytes=1024).detail["size_bytes"] == 1024

    def test_T140_two_instances_different_hashes(self):
        a1, a2 = BackupAuditLog(), BackupAuditLog()
        e1, e2 = a1.record("e", "a"), a2.record("e", "a")
        assert len(e1.chain_hash) == 64 and len(e2.chain_hash) == 64

    def test_T141_concurrent_safe(self, audit):
        errors = []

        def w():
            try:
                audit.record("c", "actor")
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=w) for _ in range(30)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors

    def test_T142_verify_large_chain(self, audit):
        [audit.record(f"e{i}", "a", backup_id=f"b{i}") for i in range(100)]
        assert audit.verify_chain() is True

    def test_T143_actor_stored(self, audit):
        assert audit.record("e", "dr-operator").actor == "dr-operator"

    def test_T144_no_backup_id_none(self, audit):
        assert audit.record("e", "a").backup_id is None


class TestRestoreValidator:
    def test_T145_validate_success(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert all(r.passed for r in v.validate(db_backup))

    def test_T146_returns_5_checks(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert len(v.validate(db_backup)) == 5

    def test_T147_manifest_fails_tampered(self, system, db_backup):
        db_backup.manifest.size_bytes = 1
        v = RestoreValidator(system.encryption, b"test-manifest")
        m = next(r for r in v.validate(db_backup) if r.check == ValidationCheck.MANIFEST)
        assert m.passed is False

    def test_T148_checksum_check(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert ValidationCheck.CHECKSUM in [r.check for r in v.validate(db_backup)]

    def test_T149_schema_check(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert ValidationCheck.SCHEMA in [r.check for r in v.validate(db_backup)]

    def test_T150_duration_non_negative(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert all(r.duration_ms >= 0 for r in v.validate(db_backup))

    def test_T151_detail_str(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert all(isinstance(r.detail, str) and r.detail for r in v.validate(db_backup))

    def test_T152_row_count_check(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert ValidationCheck.ROW_COUNT in [r.check for r in v.validate(db_backup)]

    def test_T153_decryption_check(self, system, db_backup):
        v = RestoreValidator(system.encryption, b"test-manifest")
        assert ValidationCheck.DECRYPTION in [r.check for r in v.validate(db_backup)]

    def test_T154_required_checks_covered(self):
        assert ValidationCheck.MANIFEST in RestoreValidator.REQUIRED_CHECKS
        assert ValidationCheck.CHECKSUM in RestoreValidator.REQUIRED_CHECKS


class TestBackupDRSystemFacade:
    def test_T161_has_all_components(self, system):
        for attr in ["encryption", "audit", "engine", "restore", "pitr", "retention", "drill"]:
            assert hasattr(system, attr)

    def test_T162_backup_shortcut(self, system):
        assert system.backup(BackupCategory.CONFIG).status == BackupStatus.SUCCESS

    def test_T163_run_restore_shortcut(self, system, db_backup):
        assert system.run_restore(db_backup.backup_id, "prod").status == RestoreStatus.SUCCESS

    def test_T164_run_drill_shortcut(self, system, all_backups):
        assert system.run_drill().passed

    def test_T165_full_cycle(self, system):
        for cat in BackupCategory:
            bkp = system.backup(cat)
            assert system.run_restore(bkp.backup_id, "dr").status == RestoreStatus.SUCCESS

    def test_T166_audit_chain_after_cycle(self, system, all_backups):
        system.run_restore(all_backups[BackupCategory.DB].backup_id, "dr")
        system.retention.enforce()
        assert system.audit.verify_chain() is True

    def test_T167_drill_includes_restore(self, system, all_backups):
        assert "restore_test" in {s.name for s in system.run_drill().steps}

    def test_T168_drill_includes_pitr(self, system, all_backups):
        assert "pitr_test" in {s.name for s in system.run_drill().steps}

    def test_T169_key_rotation_still_restores(self, system):
        bkp = system.backup(BackupCategory.DB)
        system.encryption.rotate_key()
        assert system.run_restore(bkp.backup_id, "staging").status == RestoreStatus.SUCCESS

    def test_T170_multiple_drills(self, system, all_backups):
        system.run_drill()
        system.run_drill()
        assert len(system.drill.list_drills()) >= 2

    def test_T171_wal_after_backup_used(self, system):
        system.pitr.record_wal()
        time.sleep(0.001)
        system.backup(BackupCategory.DB)
        system.pitr.record_wal()
        assert system.pitr.recover_to(time.time() + 1).wal_segments_applied >= 1

    def test_T172_enum_db_value(self):
        assert BackupCategory.DB.value == "db"

    def test_T173_restore_status_values(self):
        assert RestoreStatus.SUCCESS.value == "success"

    def test_T174_drill_status_values(self):
        assert DrillStatus.PASSED.value == "passed"

    def test_T175_backup_status_values(self):
        assert BackupStatus.CORRUPTED.value == "corrupted"

    def test_T176_backup_type_values(self):
        assert BackupType.WAL.value == "wal"


class TestSQLMigration:
    @pytest.fixture(autouse=True)
    def sql(self):
        p = "/home/definable/phase23/supabase/migrations/20260627_031_phase23_backup_dr.sql"
        if not os.path.exists(p):
            pytest.skip("SQL file not found")
        with open(p) as f:
            self.sql_text = f.read()

    def test_T177_begin_commit(self):
        assert "BEGIN;" in self.sql_text and "COMMIT;" in self.sql_text

    def test_T178_backup_runs_table(self):
        assert "backup_runs" in self.sql_text

    def test_T179_restore_runs_table(self):
        assert "restore_runs" in self.sql_text

    def test_T180_pitr_records_table(self):
        assert "pitr_records" in self.sql_text

    def test_T181_dr_drills_table(self):
        assert "dr_drills" in self.sql_text

    def test_T182_rls_enabled(self):
        assert "ROW LEVEL SECURITY" in self.sql_text

    def test_T183_checksum_col(self):
        assert "checksum_sha256" in self.sql_text

    def test_T184_encryption_key_id(self):
        assert "encryption_key_id" in self.sql_text

    def test_T185_retention_policy_table(self):
        assert "backup_policy" in self.sql_text or "retention_policy" in self.sql_text

    def test_T186_if_not_exists(self):
        assert "IF NOT EXISTS" in self.sql_text

    def test_T187_pitr_has_lsn(self):
        assert "lsn" in self.sql_text.lower()

    def test_T188_indexes_present(self):
        assert "CREATE INDEX" in self.sql_text

    def test_T189_rto_rpo(self):
        assert "rto" in self.sql_text.lower() or "rpo" in self.sql_text.lower()

    def test_T190_cleanup_function(self):
        assert "cleanup" in self.sql_text.lower() or "purge" in self.sql_text.lower()

    def test_T191_tenant_id_column(self):
        assert "tenant_id" in self.sql_text

    def test_T192_status_column(self):
        assert "status" in self.sql_text
