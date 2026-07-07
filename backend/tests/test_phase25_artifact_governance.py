"""
test_phase25_artifact_governance.py -- Phase 25: Release Artifact Governance
196 tests: lifecycle FSM, checksum, compatibility, audit chain, access control, admin ops.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest

from backend.core.artifact_governance import (
    BLOCKED_STATUSES,
    DEFAULT_COMPATIBILITY_RULES,
    MIGRATION_SQL,
    REQUIRES_REASON,
    VALID_TRANSITIONS,
    AdminArtifactOps,
    ArtifactAccessDeniedError,
    ArtifactAction,
    ArtifactAuditChain,
    ArtifactChecksumError,
    ArtifactError,
    ArtifactGovernance,
    ArtifactNotFoundError,
    ArtifactPlatform,
    ArtifactRecord,
    ArtifactSigner,
    ArtifactStatus,
    ArtifactStore,
    ArtifactTransitionError,
    ArtifactType,
    CompatibilityChecker,
    CompatibilityRule,
    CompatibilityStatus,
    MissingReasonError,
    sha256_bytes,
    sha512_bytes,
    verify_checksum,
)


@pytest.fixture
def gov():
    return ArtifactGovernance(secret=b"test-secret-phase25")


@pytest.fixture
def data():
    return b"EA binary payload v1.0.0" * 100


@pytest.fixture
def artifact(gov, data):
    return gov.create_artifact(
        "MT5TradingEA",
        "1.0.0",
        ArtifactType.EA_BINARY,
        ArtifactPlatform.MT5,
        data,
        "builder-01",
        "tenant-acme",
    )


@pytest.fixture
def signed_artifact(gov, artifact):
    return gov.sign_artifact(artifact.artifact_id, "signer-01", "tenant-acme")


@pytest.fixture
def published_artifact(gov, signed_artifact):
    return gov.publish_artifact(signed_artifact.artifact_id, "admin-01", "tenant-acme")


@pytest.fixture
def chain():
    return ArtifactAuditChain(secret=b"chain-secret-phase25")


@pytest.fixture
def compat():
    c = CompatibilityChecker()
    for rule in DEFAULT_COMPATIBILITY_RULES:
        c.add_rule(rule)
    return c


class TestArtifactEnums:
    def test_T001_status_values(self):
        assert ArtifactStatus.DRAFT.value == "draft"
        assert ArtifactStatus.SIGNED.value == "signed"
        assert ArtifactStatus.PUBLISHED.value == "published"
        assert ArtifactStatus.DEPRECATED.value == "deprecated"
        assert ArtifactStatus.REVOKED.value == "revoked"

    def test_T002_type_count(self):
        assert len(ArtifactType) >= 7

    def test_T003_platform_values(self):
        assert ArtifactPlatform.MT4 in ArtifactPlatform
        assert ArtifactPlatform.MT5 in ArtifactPlatform
        assert ArtifactPlatform.ANY in ArtifactPlatform

    def test_T004_compat_status(self):
        assert CompatibilityStatus.COMPATIBLE.value == "compatible"
        assert CompatibilityStatus.INCOMPATIBLE.value == "incompatible"

    def test_T005_action_count(self):
        assert len(ArtifactAction) >= 7

    def test_T006_blocked_statuses(self):
        assert ArtifactStatus.REVOKED in BLOCKED_STATUSES
        assert ArtifactStatus.DRAFT in BLOCKED_STATUSES
        assert ArtifactStatus.PUBLISHED not in BLOCKED_STATUSES

    def test_T007_requires_reason(self):
        assert ArtifactAction.REVOKED in REQUIRES_REASON
        assert ArtifactAction.DEPRECATED in REQUIRES_REASON
        assert ArtifactAction.CREATED not in REQUIRES_REASON

    def test_T008_transitions_draft(self):
        allowed = VALID_TRANSITIONS[ArtifactStatus.DRAFT]
        assert ArtifactStatus.SIGNED in allowed
        assert ArtifactStatus.REVOKED in allowed

    def test_T009_transitions_signed(self):
        allowed = VALID_TRANSITIONS[ArtifactStatus.SIGNED]
        assert ArtifactStatus.PUBLISHED in allowed

    def test_T010_transitions_published(self):
        allowed = VALID_TRANSITIONS[ArtifactStatus.PUBLISHED]
        assert ArtifactStatus.DEPRECATED in allowed
        assert ArtifactStatus.REVOKED in allowed

    def test_T011_transitions_deprecated(self):
        assert ArtifactStatus.REVOKED in VALID_TRANSITIONS[ArtifactStatus.DEPRECATED]

    def test_T012_transitions_revoked_terminal(self):
        assert VALID_TRANSITIONS[ArtifactStatus.REVOKED] == set()

    def test_T013_default_rules_count(self):
        assert len(DEFAULT_COMPATIBILITY_RULES) >= 6

    def test_T014_ea_binary_in_rules(self):
        types = [r.artifact_type for r in DEFAULT_COMPATIBILITY_RULES]
        assert ArtifactType.EA_BINARY in types

    def test_T015_migration_has_tables(self):
        sql = MIGRATION_SQL.upper()
        assert "ARTIFACT_RECORDS" in sql
        assert "ARTIFACT_AUDIT_LOG" in sql

    def test_T016_migration_has_rls(self):
        assert "ROW LEVEL SECURITY" in MIGRATION_SQL.upper()


class TestChecksumHelpers:
    def test_T017_sha256_length(self):
        assert len(sha256_bytes(b"test")) == 64

    def test_T018_sha256_hex(self):
        assert all(c in "0123456789abcdef" for c in sha256_bytes(b"test"))

    def test_T019_sha512_length(self):
        assert len(sha512_bytes(b"test")) == 128

    def test_T020_sha256_deterministic(self):
        assert sha256_bytes(b"same") == sha256_bytes(b"same")

    def test_T021_sha256_different(self):
        assert sha256_bytes(b"a") != sha256_bytes(b"b")

    def test_T022_verify_ok(self):
        data = b"hello world"
        assert verify_checksum(data, sha256_bytes(data)) is True

    def test_T023_verify_wrong_hash(self):
        assert verify_checksum(b"hello", "a" * 64) is False

    def test_T024_verify_tampered_data(self):
        h = sha256_bytes(b"original")
        assert verify_checksum(b"tampered", h) is False

    def test_T025_verify_empty(self):
        h = sha256_bytes(b"")
        assert verify_checksum(b"", h) is True

    def test_T026_verify_large(self):
        data = b"x" * (1024 * 1024)
        assert verify_checksum(data, sha256_bytes(data)) is True

    def test_T027_sha256_known(self):
        assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()

    def test_T028_sha512_different(self):
        assert sha256_bytes(b"t") != sha512_bytes(b"t")

    def test_T029_verify_short_hash_false(self):
        assert verify_checksum(b"d", "short") is False

    def test_T030_checksum_thread_safe(self):
        results = []
        data = b"concurrent"
        expected = sha256_bytes(data)

        def check():
            results.append(verify_checksum(data, expected))

        ts = [threading.Thread(target=check) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert all(results)

    def test_T031_sha256_empty_known(self):
        assert sha256_bytes(b"") == hashlib.sha256(b"").hexdigest()

    def test_T032_sha512_known(self):
        assert sha512_bytes(b"test") == hashlib.sha512(b"test").hexdigest()


class TestCompatibilityChecker:
    def test_T033_ea_mt5_compatible(self, compat):
        assert (
            compat.check(ArtifactType.EA_BINARY, "1.0.0", ArtifactPlatform.MT5)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T034_ea_linux_incompatible(self, compat):
        assert (
            compat.check(ArtifactType.EA_BINARY, "1.0.0", ArtifactPlatform.LINUX_X64)
            == CompatibilityStatus.INCOMPATIBLE
        )

    def test_T035_config_any(self, compat):
        assert (
            compat.check(ArtifactType.CONFIG, "1.0.0", ArtifactPlatform.ANY)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T036_no_rules_unknown(self):
        assert (
            CompatibilityChecker().check(ArtifactType.EA_BINARY, "1.0.0", ArtifactPlatform.MT5)
            == CompatibilityStatus.UNKNOWN
        )

    def test_T037_version_below_min(self, compat):
        assert (
            compat.check(ArtifactType.EA_BINARY, "0.9.0", ArtifactPlatform.MT5)
            == CompatibilityStatus.INCOMPATIBLE
        )

    def test_T038_mt4_version_too_high(self, compat):
        assert (
            compat.check(ArtifactType.EA_BINARY, "3.0.0", ArtifactPlatform.MT4)
            == CompatibilityStatus.INCOMPATIBLE
        )

    def test_T039_mt4_within_range(self, compat):
        assert (
            compat.check(ArtifactType.EA_BINARY, "2.0.0", ArtifactPlatform.MT4)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T040_supported_platforms(self, compat):
        p = compat.get_supported_platforms(ArtifactType.EA_BINARY)
        assert ArtifactPlatform.MT5 in p
        assert ArtifactPlatform.MT4 in p

    def test_T041_custom_rule(self):
        c = CompatibilityChecker()
        c.add_rule(
            CompatibilityRule(ArtifactType.DOCKER_IMG, "2.0.0", None, ArtifactPlatform.DOCKER)
        )
        assert (
            c.check(ArtifactType.DOCKER_IMG, "2.0.0", ArtifactPlatform.DOCKER)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T042_custom_rule_below_min(self):
        c = CompatibilityChecker()
        c.add_rule(
            CompatibilityRule(ArtifactType.DOCKER_IMG, "2.0.0", None, ArtifactPlatform.DOCKER)
        )
        assert (
            c.check(ArtifactType.DOCKER_IMG, "1.9.9", ArtifactPlatform.DOCKER)
            == CompatibilityStatus.INCOMPATIBLE
        )

    def test_T043_rule_version_range(self):
        rule = CompatibilityRule(ArtifactType.CONFIG, "1.2.3", "2.0.0", ArtifactPlatform.ANY)
        assert rule.check("1.5.0", ArtifactPlatform.ANY) == CompatibilityStatus.COMPATIBLE
        assert rule.check("2.1.0", ArtifactPlatform.ANY) == CompatibilityStatus.INCOMPATIBLE

    def test_T044_thread_safe(self, compat):
        results = []

        def check():
            results.append(compat.check(ArtifactType.EA_BINARY, "1.0.0", ArtifactPlatform.MT5))

        ts = [threading.Thread(target=check) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert all(r == CompatibilityStatus.COMPATIBLE for r in results)

    def test_T045_docker_compatible(self, compat):
        assert (
            compat.check(ArtifactType.DOCKER_IMG, "1.0.0", ArtifactPlatform.DOCKER)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T046_installer_windows(self, compat):
        assert (
            compat.check(ArtifactType.INSTALLER, "1.0.0", ArtifactPlatform.WINDOWS_X64)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T047_migration_any(self, compat):
        assert (
            compat.check(ArtifactType.MIGRATION, "1.0.0", ArtifactPlatform.ANY)
            == CompatibilityStatus.COMPATIBLE
        )

    def test_T048_license_any(self, compat):
        assert (
            compat.check(ArtifactType.LICENSE_PKG, "1.0.0", ArtifactPlatform.ANY)
            == CompatibilityStatus.COMPATIBLE
        )


class TestArtifactLifecycleFSM:
    def test_T049_create_draft(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        assert a.status == ArtifactStatus.DRAFT

    def test_T050_checksums_set(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        assert a.sha256 == sha256_bytes(data)
        assert a.sha512 == sha512_bytes(data)
        assert a.size_bytes == len(data)

    def test_T051_sign_draft_to_signed(self, gov, artifact):
        s = gov.sign_artifact(artifact.artifact_id, "signer", "t-acme")
        assert s.status == ArtifactStatus.SIGNED
        assert s.signed_by == "signer"
        assert s.signature != ""

    def test_T052_publish_signed_to_published(self, gov, signed_artifact):
        p = gov.publish_artifact(signed_artifact.artifact_id, "admin", "t-acme")
        assert p.status == ArtifactStatus.PUBLISHED
        assert p.published_at is not None

    def test_T053_deprecate_published(self, gov, published_artifact):
        d = gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "New version")
        assert d.status == ArtifactStatus.DEPRECATED

    def test_T054_revoke_published(self, gov, published_artifact):
        r = gov.revoke_artifact(published_artifact.artifact_id, "admin", "t-acme", "Security issue")
        assert r.status == ArtifactStatus.REVOKED
        assert r.revoke_reason == "Security issue"

    def test_T055_revoke_draft(self, gov, artifact):
        r = gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "Draft rejected")
        assert r.status == ArtifactStatus.REVOKED

    def test_T056_revoke_deprecated(self, gov, published_artifact):
        gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "old")
        r = gov.revoke_artifact(published_artifact.artifact_id, "admin", "t-acme", "revoked")
        assert r.status == ArtifactStatus.REVOKED

    def test_T057_cannot_publish_draft(self, gov, artifact):
        with pytest.raises(ArtifactTransitionError):
            gov.publish_artifact(artifact.artifact_id, "admin", "t-acme")

    def test_T058_cannot_sign_published(self, gov, published_artifact):
        with pytest.raises(ArtifactTransitionError):
            gov.sign_artifact(published_artifact.artifact_id, "s", "t-acme")

    def test_T059_cannot_revoke_twice(self, gov, artifact):
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "r1")
        with pytest.raises(ArtifactTransitionError):
            gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "r2")

    def test_T060_cannot_deprecate_draft(self, gov, artifact):
        with pytest.raises(ArtifactTransitionError):
            gov.deprecate_artifact(artifact.artifact_id, "admin", "t-acme", "too early")

    def test_T061_deprecate_requires_reason(self, gov, published_artifact):
        with pytest.raises(MissingReasonError):
            gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "")

    def test_T062_revoke_requires_reason(self, gov, artifact):
        with pytest.raises(MissingReasonError):
            gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "")

    def test_T063_revoke_whitespace_rejected(self, gov, artifact):
        with pytest.raises(MissingReasonError):
            gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "   ")

    def test_T064_deprecate_whitespace_rejected(self, gov, published_artifact):
        with pytest.raises(MissingReasonError):
            gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "  ")


class TestArtifactDownloadControl:
    def test_T065_published_downloadable(self, published_artifact):
        assert published_artifact.is_downloadable() is True

    def test_T066_draft_not_downloadable(self, artifact):
        assert artifact.is_downloadable() is False

    def test_T067_revoked_not_downloadable(self, gov, artifact):
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "reason")
        assert gov.get_artifact(artifact.artifact_id).is_downloadable() is False

    def test_T068_download_published_ok(self, gov, data, published_artifact):
        a = gov.download_artifact(published_artifact.artifact_id, "user", "t-acme", data)
        assert a.download_count == 1

    def test_T069_download_draft_raises(self, gov, artifact):
        with pytest.raises(ArtifactAccessDeniedError):
            gov.download_artifact(artifact.artifact_id, "user", "t-acme")

    def test_T070_download_revoked_raises(self, gov, artifact):
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "reason")
        with pytest.raises(ArtifactAccessDeniedError):
            gov.download_artifact(artifact.artifact_id, "user", "t-acme")

    def test_T071_wrong_checksum_raises(self, gov, published_artifact):
        with pytest.raises(ArtifactChecksumError):
            gov.download_artifact(published_artifact.artifact_id, "user", "t-acme", b"tampered")

    def test_T072_counter_increments(self, gov, data, published_artifact):
        for _ in range(5):
            gov.download_artifact(published_artifact.artifact_id, "u", "t-acme", data)
        assert gov.get_artifact(published_artifact.artifact_id).download_count == 5

    def test_T073_download_deprecated_ok(self, gov, data, published_artifact):
        gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "old")
        a = gov.download_artifact(published_artifact.artifact_id, "user", "t-acme", data)
        assert a.download_count == 1

    def test_T074_no_data_no_checksum(self, gov, published_artifact):
        assert (
            gov.download_artifact(published_artifact.artifact_id, "user", "t-acme").download_count
            == 1
        )

    def test_T075_rejected_audited(self, gov, artifact):
        try:
            gov.download_artifact(artifact.artifact_id, "user", "t-acme")
        except ArtifactAccessDeniedError:
            pass
        assert ArtifactAction.REJECTED in [
            r.action for r in gov.audit_log(artifact_id=artifact.artifact_id)
        ]

    def test_T076_checksum_fail_audited(self, gov, published_artifact):
        try:
            gov.download_artifact(published_artifact.artifact_id, "user", "t-acme", b"bad")
        except ArtifactChecksumError:
            pass
        assert (
            len(
                gov.audit_log(
                    artifact_id=published_artifact.artifact_id, action=ArtifactAction.REJECTED
                )
            )
            >= 1
        )

    def test_T077_download_records_requester(self, gov, data, published_artifact):
        gov.download_artifact(published_artifact.artifact_id, "user-xyz", "t-acme", data)
        logs = gov.audit_log(
            artifact_id=published_artifact.artifact_id, action=ArtifactAction.DOWNLOADED
        )
        assert any(r.actor == "user-xyz" for r in logs)

    def test_T078_signed_downloadable(self, signed_artifact):
        assert signed_artifact.is_downloadable() is True

    def test_T079_deprecated_downloadable(self, gov, published_artifact):
        gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "old")
        assert gov.get_artifact(published_artifact.artifact_id).is_downloadable() is True

    def test_T080_concurrent_downloads(self, gov, data, published_artifact):
        results = []

        def dl():
            results.append(
                gov.download_artifact(
                    published_artifact.artifact_id, "u", "t-acme", data
                ).download_count
            )

        ts = [threading.Thread(target=dl) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert gov.get_artifact(published_artifact.artifact_id).download_count == 10


class TestArtifactSigner:
    def test_T081_sign_64chars(self, gov, artifact):
        assert len(gov.sign_artifact(artifact.artifact_id, "s", "t-acme").signature) == 64

    def test_T082_sign_hex(self, gov, artifact):
        s = gov.sign_artifact(artifact.artifact_id, "s", "t-acme")
        assert all(c in "0123456789abcdef" for c in s.signature)

    def test_T083_verify_sig_ok(self, gov, signed_artifact):
        assert (
            ArtifactSigner(secret=b"test-secret-phase25").verify_signature(signed_artifact) is True
        )

    def test_T084_verify_sig_tampered(self, gov, signed_artifact):
        signed_artifact.signature = "a" * 64
        assert (
            ArtifactSigner(secret=b"test-secret-phase25").verify_signature(signed_artifact) is False
        )

    def test_T085_publish_without_sig_fails(self, gov, artifact):
        artifact.status = ArtifactStatus.SIGNED
        gov._store.save(artifact)
        with pytest.raises(ArtifactError):
            gov.publish_artifact(artifact.artifact_id, "admin", "t-acme")

    def test_T086_different_secrets_different_sigs(self):
        import time as t
        import uuid

        a = ArtifactRecord(
            artifact_id=str(uuid.uuid4()),
            name="EA",
            version="1.0.0",
            artifact_type=ArtifactType.EA_BINARY,
            platform=ArtifactPlatform.MT5,
            status=ArtifactStatus.DRAFT,
            sha256="a" * 64,
            sha512="b" * 128,
            size_bytes=100,
            created_at=t.time(),
            created_by="b",
            tenant_id="t",
        )
        assert ArtifactSigner(b"s1").sign(a, "s1") != ArtifactSigner(b"s2").sign(a, "s2")

    def test_T087_verify_empty_sig_false(self, gov, artifact):
        assert ArtifactSigner(b"test-secret-phase25").verify_signature(artifact) is False

    def test_T088_sign_deterministic(self, gov, artifact):
        s = ArtifactSigner(b"test-secret-phase25")
        assert s.sign(artifact, "s1") == s.sign(artifact, "s2")

    def test_T089_signed_at_set(self, gov, artifact):
        before = time.time()
        s = gov.sign_artifact(artifact.artifact_id, "signer", "t-acme")
        assert before <= s.signed_at <= time.time()

    def test_T090_signed_by_set(self, gov, artifact):
        assert (
            gov.sign_artifact(artifact.artifact_id, "signer-007", "t-acme").signed_by
            == "signer-007"
        )

    def test_T091_canonical_includes_fields(self, gov, artifact):
        c = artifact.canonical()
        assert artifact.artifact_id in c
        assert artifact.sha256 in c

    def test_T092_canonical_is_json(self, gov, artifact):
        parsed = json.loads(artifact.canonical())
        assert "artifact_id" in parsed

    def test_T093_wrong_secret_verify_fails(self, gov, artifact):
        gov.sign_artifact(artifact.artifact_id, "s", "t-acme")
        a = gov.get_artifact(artifact.artifact_id)
        assert ArtifactSigner(b"wrong").verify_signature(a) is False

    def test_T094_str_secret(self):
        assert ArtifactSigner(secret="string") is not None

    def test_T095_gov_str_secret(self):
        g = ArtifactGovernance(secret="string-secret")
        a = g.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, b"data", "b", "t"
        )
        assert g.sign_artifact(a.artifact_id, "s", "t").signature != ""

    def test_T096_published_at_set(self, gov, signed_artifact):
        before = time.time()
        p = gov.publish_artifact(signed_artifact.artifact_id, "admin", "t-acme")
        assert before <= p.published_at <= time.time()


class TestAuditChainIntegrity:
    def test_T097_genesis_64chars(self, chain):
        assert len(chain._genesis) == 64

    def test_T098_genesis_hex(self, chain):
        assert all(c in "0123456789abcdef" for c in chain._genesis)

    def test_T099_record_64char_hash(self, chain):
        assert len(chain.record("a", ArtifactAction.CREATED, "actor", "t").chain_hash) == 64

    def test_T100_seq_starts_1(self, chain):
        assert chain.record("a", ArtifactAction.CREATED, "actor", "t").seq == 1

    def test_T101_seq_increments(self, chain):
        r1 = chain.record("a", ArtifactAction.CREATED, "actor", "t")
        r2 = chain.record("a", ArtifactAction.SIGNED, "actor", "t")
        assert r2.seq == r1.seq + 1

    def test_T102_prev_hash_chaining(self, chain):
        r1 = chain.record("a", ArtifactAction.CREATED, "actor", "t")
        r2 = chain.record("a", ArtifactAction.SIGNED, "actor", "t")
        assert r2.prev_hash == r1.chain_hash

    def test_T103_verify_empty(self, chain):
        assert chain.verify_chain() is True

    def test_T104_verify_after_records(self, chain):
        for i in range(10):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        assert chain.verify_chain() is True

    def test_T105_tamper_event_breaks(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        list(chain._records)[0].action = ArtifactAction.REVOKED
        assert chain.verify_chain() is False

    def test_T106_tamper_actor_breaks(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        list(chain._records)[0].actor = "hacker"
        assert chain.verify_chain() is False

    def test_T107_tamper_reason_breaks(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        list(chain._records)[0].reason = "injected"
        assert chain.verify_chain() is False

    def test_T108_tamper_tenant_breaks(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        list(chain._records)[0].tenant_id = "evil"
        assert chain.verify_chain() is False

    def test_T109_wrong_secret_breaks(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        wc = ArtifactAuditChain(b"wrong")
        wc._records = chain._records
        assert wc.verify_chain() is False

    def test_T110_detect_tampered_seq(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        chain.record("a", ArtifactAction.SIGNED, "actor", "t")
        list(chain._records)[0].actor = "tampered"
        assert 1 in chain.detect_tampered()

    def test_T111_detect_tampered_clean(self, chain):
        for i in range(5):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        assert chain.detect_tampered() == []

    def test_T112_requires_reason_enforced(self, chain):
        with pytest.raises(MissingReasonError):
            chain.record("a", ArtifactAction.REVOKED, "actor", "t", reason="")


class TestAuditChainQuery:
    def test_T113_query_by_artifact(self, chain):
        chain.record("art-1", ArtifactAction.CREATED, "actor", "t")
        chain.record("art-2", ArtifactAction.CREATED, "actor", "t")
        assert all(r.artifact_id == "art-1" for r in chain.query(artifact_id="art-1"))

    def test_T114_query_by_action(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        chain.record("a", ArtifactAction.SIGNED, "actor", "t")
        assert all(
            r.action == ArtifactAction.CREATED for r in chain.query(action=ArtifactAction.CREATED)
        )

    def test_T115_query_by_actor(self, chain):
        chain.record("a", ArtifactAction.CREATED, "alice", "t")
        chain.record("a", ArtifactAction.SIGNED, "bob", "t")
        assert all(r.actor == "alice" for r in chain.query(actor="alice"))

    def test_T116_query_by_tenant(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t1")
        chain.record("b", ArtifactAction.CREATED, "actor", "t2")
        assert all(r.tenant_id == "t1" for r in chain.query(tenant_id="t1"))

    def test_T117_query_limit(self, chain):
        for i in range(20):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        assert len(chain.query(limit=5)) == 5

    def test_T118_most_recent_first(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        time.sleep(0.01)
        chain.record("b", ArtifactAction.CREATED, "actor", "t")
        results = chain.query(limit=10)
        assert results[0].ts >= results[1].ts

    def test_T119_no_filter(self, chain):
        for i in range(5):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        assert len(chain.query()) == 5

    def test_T120_len(self, chain):
        for i in range(7):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        assert len(chain) == 7

    def test_T121_records_property(self, chain):
        chain.record("a", ArtifactAction.CREATED, "actor", "t")
        assert len(chain.records) == 1

    def test_T122_concurrent_records(self, chain):
        errors = []

        def write(i):
            try:
                chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=write, args=(i,)) for i in range(50)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors and len(chain) == 50

    def test_T123_unique_seqs(self, chain):
        def write(i):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")

        ts = [threading.Thread(target=write, args=(i,)) for i in range(30)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        seqs = [r.seq for r in chain.records]
        assert len(seqs) == len(set(seqs))

    def test_T124_unique_entry_ids(self, chain):
        for i in range(10):
            chain.record(f"a{i}", ArtifactAction.CREATED, "actor", "t")
        ids = [r.entry_id for r in chain.records]
        assert len(ids) == len(set(ids))

    def test_T125_audit_via_governance(self, gov, artifact):
        logs = gov.audit_log(artifact_id=artifact.artifact_id)
        assert len(logs) >= 1

    def test_T126_verify_chain_gov(self, gov, artifact):
        assert gov.verify_audit_chain() is True

    def test_T127_detect_tamper_clean(self, gov, artifact):
        assert gov.detect_audit_tamper() == []

    def test_T128_query_by_action_gov(self, gov, artifact):
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "sec")
        assert len(gov.audit_log(action=ArtifactAction.REVOKED)) >= 1


class TestArtifactStore:
    def test_T129_save_get(self):
        import time as t
        import uuid

        store = ArtifactStore()
        a = ArtifactRecord(
            artifact_id=str(uuid.uuid4()),
            name="EA",
            version="1.0.0",
            artifact_type=ArtifactType.EA_BINARY,
            platform=ArtifactPlatform.MT5,
            status=ArtifactStatus.DRAFT,
            sha256="a" * 64,
            sha512="b" * 128,
            size_bytes=100,
            created_at=t.time(),
            created_by="b",
            tenant_id="t",
        )
        store.save(a)
        assert store.get(a.artifact_id).artifact_id == a.artifact_id

    def test_T130_not_found_raises(self):
        with pytest.raises(ArtifactNotFoundError):
            ArtifactStore().get("bad")

    def test_T131_list_by_status(self, gov, data):
        a1 = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        a2 = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        gov.sign_artifact(a2.artifact_id, "s", "t1")
        assert any(
            a.artifact_id == a1.artifact_id for a in gov.list_artifacts(status=ArtifactStatus.DRAFT)
        )

    def test_T132_list_by_type(self, gov, data):
        gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        gov.create_artifact(
            "C", "1.0.0", ArtifactType.CONFIG, ArtifactPlatform.ANY, data, "b", "t1"
        )
        assert all(
            a.artifact_type == ArtifactType.EA_BINARY
            for a in gov.list_artifacts(artifact_type=ArtifactType.EA_BINARY)
        )

    def test_T133_list_by_tenant(self, gov, data):
        gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "tA"
        )
        gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "tB"
        )
        assert all(a.tenant_id == "tA" for a in gov.list_artifacts(tenant_id="tA"))

    def test_T134_list_by_platform(self, gov, data):
        gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
        )
        gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT4, data, "b", "t1"
        )
        assert all(
            a.platform == ArtifactPlatform.MT5
            for a in gov.list_artifacts(platform=ArtifactPlatform.MT5)
        )

    def test_T135_store_len(self, gov, data):
        for _ in range(5):
            gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t1"
            )
        assert len(gov._store) >= 5

    def test_T136_store_thread_safe(self):
        import time as t
        import uuid

        store = ArtifactStore()
        errors = []

        def write():
            try:
                a = ArtifactRecord(
                    artifact_id=str(uuid.uuid4()),
                    name="EA",
                    version="1.0.0",
                    artifact_type=ArtifactType.EA_BINARY,
                    platform=ArtifactPlatform.MT5,
                    status=ArtifactStatus.DRAFT,
                    sha256="a" * 64,
                    sha512="b" * 128,
                    size_bytes=100,
                    created_at=t.time(),
                    created_by="b",
                    tenant_id="t",
                )
                store.save(a)
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=write) for _ in range(30)]
        for t_ in ts:
            t_.start()
        for t_ in ts:
            t_.join()
        assert not errors and len(store) == 30

    def test_T137_sorted_desc(self, gov, data):
        for _ in range(3):
            gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-sort"
            )
            time.sleep(0.01)
        ts = [a.created_at for a in gov.list_artifacts(tenant_id="t-sort")]
        assert ts == sorted(ts, reverse=True)

    def test_T138_delete(self):
        import time as t
        import uuid

        store = ArtifactStore()
        aid = str(uuid.uuid4())
        a = ArtifactRecord(
            artifact_id=aid,
            name="EA",
            version="1.0.0",
            artifact_type=ArtifactType.EA_BINARY,
            platform=ArtifactPlatform.MT5,
            status=ArtifactStatus.DRAFT,
            sha256="a" * 64,
            sha512="b" * 128,
            size_bytes=100,
            created_at=t.time(),
            created_by="b",
            tenant_id="t",
        )
        store.save(a)
        store.delete(aid)
        with pytest.raises(ArtifactNotFoundError):
            store.get(aid)

    def test_T139_get_via_gov(self, gov, artifact):
        assert gov.get_artifact(artifact.artifact_id).artifact_id == artifact.artifact_id

    def test_T140_artifact_id_is_uuid(self, gov, data):
        import uuid

        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        assert str(uuid.UUID(a.artifact_id)) == a.artifact_id

    def test_T141_metadata_stored(self, gov, data):
        meta = {"build": "123"}
        a = gov.create_artifact(
            "EA",
            "1.0.0",
            ArtifactType.EA_BINARY,
            ArtifactPlatform.MT5,
            data,
            "b",
            "t",
            metadata=meta,
        )
        assert gov.get_artifact(a.artifact_id).metadata == meta

    def test_T142_compatible_platforms_list(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        assert isinstance(a.compatible_platforms, list)

    def test_T143_not_found_message(self):
        with pytest.raises(ArtifactNotFoundError, match="not found"):
            ArtifactStore().get("x")

    def test_T144_check_compat_via_gov(self, gov, artifact):
        assert (
            gov.check_compatibility(artifact.artifact_id, ArtifactPlatform.MT5)
            == CompatibilityStatus.COMPATIBLE
        )


class TestAdminArtifactOps:
    def test_T145_bulk_revoke(self, gov, data):
        admin = AdminArtifactOps(gov)
        ids = [
            gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-b"
            ).artifact_id
            for _ in range(3)
        ]
        assert all(
            v == "revoked" for v in admin.bulk_revoke(ids, "admin", "t-b", "emergency").values()
        )

    def test_T146_bulk_requires_reason(self, gov):
        with pytest.raises(MissingReasonError):
            AdminArtifactOps(gov).bulk_revoke(["x"], "admin", "t", "")

    def test_T147_bulk_partial_fail(self, gov, data):
        admin = AdminArtifactOps(gov)
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        r = admin.bulk_revoke([a.artifact_id, "bad"], "admin", "t", "bulk")
        assert r[a.artifact_id] == "revoked" and "error" in r["bad"]

    def test_T148_revoke_by_type(self, gov, data):
        admin = AdminArtifactOps(gov)
        for _ in range(4):
            gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-type"
            )
        assert admin.revoke_by_type(ArtifactType.EA_BINARY, "admin", "t-type", "all") == 4

    def test_T149_skips_already_revoked(self, gov, data):
        admin = AdminArtifactOps(gov)
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-skip"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t-skip", "first")
        assert admin.revoke_by_type(ArtifactType.EA_BINARY, "admin", "t-skip", "second") == 0

    def test_T150_revoke_by_type_requires_reason(self, gov):
        with pytest.raises(MissingReasonError):
            AdminArtifactOps(gov).revoke_by_type(ArtifactType.EA_BINARY, "admin", "t", "")

    def test_T151_published_count(self, gov, data):
        admin = AdminArtifactOps(gov)
        for _ in range(3):
            a = gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-cnt"
            )
            gov.publish_artifact(
                gov.sign_artifact(a.artifact_id, "s", "t-cnt").artifact_id, "admin", "t-cnt"
            )
        assert admin.published_count("t-cnt") == 3

    def test_T152_whitespace_reason(self, gov):
        with pytest.raises(MissingReasonError):
            AdminArtifactOps(gov).bulk_revoke(["x"], "admin", "t", "   ")

    def test_T153_revoke_all_published(self, gov, data):
        admin = AdminArtifactOps(gov)
        for _ in range(2):
            a = gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-pub"
            )
            gov.publish_artifact(
                gov.sign_artifact(a.artifact_id, "s", "t-pub").artifact_id, "admin", "t-pub"
            )
        assert admin.revoke_by_type(ArtifactType.EA_BINARY, "admin", "t-pub", "emergency") == 2
        assert admin.published_count("t-pub") == 0

    def test_T154_bulk_audited(self, gov, data):
        admin = AdminArtifactOps(gov)
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-ab"
        )
        admin.bulk_revoke([a.artifact_id], "admin-007", "t-ab", "security")
        assert any(
            r.actor == "admin-007"
            for r in gov.audit_log(artifact_id=a.artifact_id, action=ArtifactAction.REVOKED)
        )

    def test_T155_revoke_reason_stored(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t", "Malware detected")
        assert gov.get_artifact(a.artifact_id).revoke_reason == "Malware detected"

    def test_T156_deprecated_reason_stored(self, gov, published_artifact):
        gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "Superseded")
        assert gov.get_artifact(published_artifact.artifact_id).deprecated_reason == "Superseded"

    def test_T157_revoked_at_ts(self, gov, artifact):
        before = time.time()
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "r")
        assert before <= gov.get_artifact(artifact.artifact_id).revoked_at <= time.time()

    def test_T158_deprecated_at_ts(self, gov, published_artifact):
        before = time.time()
        gov.deprecate_artifact(published_artifact.artifact_id, "admin", "t-acme", "old")
        assert (
            before <= gov.get_artifact(published_artifact.artifact_id).deprecated_at <= time.time()
        )

    def test_T159_summary(self, gov, published_artifact):
        s = gov.summary()
        assert (
            "total_artifacts" in s and "audit_chain_valid" in s and s["audit_chain_valid"] is True
        )

    def test_T160_verify_artifact(self, gov, data, signed_artifact):
        assert gov.verify_artifact(signed_artifact.artifact_id, data, "verifier", "t-acme") is True


class TestSQLMigration:
    def test_T161_begin_commit(self):
        assert "BEGIN;" in MIGRATION_SQL and "COMMIT;" in MIGRATION_SQL

    def test_T162_artifact_records(self):
        assert "CREATE TABLE IF NOT EXISTS artifact_records" in MIGRATION_SQL

    def test_T163_audit_log(self):
        assert "CREATE TABLE IF NOT EXISTS artifact_audit_log" in MIGRATION_SQL

    def test_T164_compat_rules(self):
        assert "CREATE TABLE IF NOT EXISTS artifact_compatibility_rules" in MIGRATION_SQL

    def test_T165_download_tokens(self):
        assert "CREATE TABLE IF NOT EXISTS artifact_download_tokens" in MIGRATION_SQL

    def test_T166_immutable_trigger(self):
        assert "artifact_audit_immutable" in MIGRATION_SQL

    def test_T167_revoke_reason_trigger(self):
        assert "artifact_revoke_reason_check" in MIGRATION_SQL

    def test_T168_rls(self):
        assert "ENABLE ROW LEVEL SECURITY" in MIGRATION_SQL

    def test_T169_tenant_isolation(self):
        assert "artifact_tenant_isolation" in MIGRATION_SQL

    def test_T170_service_role(self):
        assert "service_role" in MIGRATION_SQL

    def test_T171_indexes(self):
        assert (
            "CREATE INDEX IF NOT EXISTS" in MIGRATION_SQL and "idx_artifact_sha256" in MIGRATION_SQL
        )

    def test_T172_chain_hash_char64(self):
        assert "CHAR(64)" in MIGRATION_SQL

    def test_T173_cleanup_fn(self):
        assert "cleanup_expired_tokens" in MIGRATION_SQL

    def test_T174_view(self):
        assert "vw_downloadable_artifacts" in MIGRATION_SQL

    def test_T175_verify_fn(self):
        assert "verify_artifact_audit_chain" in MIGRATION_SQL

    def test_T176_status_constraint(self):
        assert "artifact_status_valid" in MIGRATION_SQL


class TestIntegrationFlows:
    def test_T177_full_to_published(self, gov, data):
        a = gov.create_artifact(
            "EA", "2.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.sign_artifact(a.artifact_id, "s", "t")
        a = gov.publish_artifact(a.artifact_id, "admin", "t")
        assert a.status == ArtifactStatus.PUBLISHED

    def test_T178_to_deprecated(self, gov, data):
        a = gov.create_artifact(
            "EA", "2.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        assert (
            gov.deprecate_artifact(a.artifact_id, "admin", "t", "v3").status
            == ArtifactStatus.DEPRECATED
        )

    def test_T179_to_revoked(self, gov, data):
        a = gov.create_artifact(
            "EA", "2.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        r = gov.revoke_artifact(a.artifact_id, "admin", "t", "CVE-2026")
        assert r.status == ArtifactStatus.REVOKED and "CVE-2026" in r.revoke_reason

    def test_T180_revoked_no_download(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t", "revoked")
        with pytest.raises(ArtifactAccessDeniedError):
            gov.download_artifact(a.artifact_id, "user", "t", data)

    def test_T181_full_audit_trail(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t", "reason")
        actions = {r.action for r in gov.audit_log(artifact_id=a.artifact_id)}
        assert {
            ArtifactAction.CREATED,
            ArtifactAction.SIGNED,
            ArtifactAction.PUBLISHED,
            ArtifactAction.REVOKED,
        }.issubset(actions)

    def test_T182_chain_valid_after_lifecycle(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t", "reason")
        assert gov.verify_audit_chain() is True

    def test_T183_hook_called(self, gov, data):
        events = []
        gov.add_hook(lambda r: events.append(r.action))
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        gov.revoke_artifact(a.artifact_id, "admin", "t", "reason")
        assert ArtifactAction.CREATED in events and ArtifactAction.REVOKED in events

    def test_T184_hook_exception_safe(self, gov, data):
        gov.add_hook(lambda r: (_ for _ in ()).throw(RuntimeError("fail")))
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        assert a.status == ArtifactStatus.DRAFT

    def test_T185_tenant_isolation(self, gov, data):
        a1 = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "tX"
        )
        a2 = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "tY"
        )
        xids = {a.artifact_id for a in gov.list_artifacts(tenant_id="tX")}
        assert a1.artifact_id in xids and a2.artifact_id not in xids

    def test_T186_concurrent_lifecycle(self, gov, data):
        artifacts = [
            gov.create_artifact(
                f"EA{i}", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-cc"
            )
            for i in range(10)
        ]
        errors = []

        def sp(a):
            try:
                s = gov.sign_artifact(a.artifact_id, "s", "t-cc")
                gov.publish_artifact(s.artifact_id, "admin", "t-cc")
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=sp, args=(a,)) for a in artifacts]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert (
            not errors
            and len(gov.list_artifacts(status=ArtifactStatus.PUBLISHED, tenant_id="t-cc")) == 10
        )

    def test_T187_emergency_bulk_revoke(self, gov, data):
        admin = AdminArtifactOps(gov)
        ids = []
        for _ in range(5):
            a = gov.create_artifact(
                "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t-em"
            )
            a = gov.publish_artifact(
                gov.sign_artifact(a.artifact_id, "s", "t-em").artifact_id, "admin", "t-em"
            )
            ids.append(a.artifact_id)
        assert all(
            v == "revoked" for v in admin.bulk_revoke(ids, "ciso", "t-em", "Zero-day").values()
        )
        assert admin.published_count("t-em") == 0 and gov.verify_audit_chain() is True

    def test_T188_verify_tampered_fails(self, gov, data, signed_artifact):
        assert (
            gov.verify_artifact(signed_artifact.artifact_id, data + b"INJECTED", "v", "t-acme")
            is False
        )

    def test_T189_download_count_persists(self, gov, data, published_artifact):
        for _ in range(3):
            gov.download_artifact(published_artifact.artifact_id, "u", "t-acme", data)
        assert gov.get_artifact(published_artifact.artifact_id).download_count == 3

    def test_T190_compat_check_gov(self, gov, artifact):
        assert (
            gov.check_compatibility(artifact.artifact_id, ArtifactPlatform.MT5)
            == CompatibilityStatus.COMPATIBLE
        )
        assert (
            gov.check_compatibility(artifact.artifact_id, ArtifactPlatform.LINUX_X64)
            == CompatibilityStatus.INCOMPATIBLE
        )

    def test_T191_100_artifacts_chain(self, gov, data):
        for i in range(100):
            gov.create_artifact(
                f"EA{i}", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t100"
            )
        assert gov.verify_audit_chain() is True

    def test_T192_revoke_reason_in_audit(self, gov, artifact):
        gov.revoke_artifact(artifact.artifact_id, "admin", "t-acme", "CVE-999")
        logs = gov.audit_log(artifact_id=artifact.artifact_id, action=ArtifactAction.REVOKED)
        assert len(logs) == 1 and logs[0].reason == "CVE-999"

    def test_T193_multi_type(self, gov, data):
        for t in [
            ArtifactType.EA_BINARY,
            ArtifactType.CONFIG,
            ArtifactType.LICENSE_PKG,
            ArtifactType.MIGRATION,
        ]:
            gov.create_artifact("a", "1.0.0", t, ArtifactPlatform.ANY, data, "b", "t-mt")
            assert len(gov.list_artifacts(artifact_type=t, tenant_id="t-mt")) >= 1

    def test_T194_signed_downloadable(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.sign_artifact(a.artifact_id, "s", "t")
        assert gov.download_artifact(a.artifact_id, "u", "t", data).download_count == 1

    def test_T195_summary_by_status(self, gov, published_artifact):
        gov.revoke_artifact(published_artifact.artifact_id, "admin", "t-acme", "test")
        assert gov.summary()["by_status"].get("revoked", 0) >= 1

    def test_T196_full_download_lifecycle(self, gov, data):
        a = gov.create_artifact(
            "EA", "1.0.0", ArtifactType.EA_BINARY, ArtifactPlatform.MT5, data, "b", "t"
        )
        a = gov.publish_artifact(
            gov.sign_artifact(a.artifact_id, "s", "t").artifact_id, "admin", "t"
        )
        gov.download_artifact(a.artifact_id, "user", "t", data)
        gov.revoke_artifact(a.artifact_id, "admin", "t", "EOL")
        with pytest.raises(ArtifactAccessDeniedError):
            gov.download_artifact(a.artifact_id, "user", "t", data)
        assert gov.verify_audit_chain() is True
        actions = {r.action for r in gov.audit_log(artifact_id=a.artifact_id)}
        assert ArtifactAction.DOWNLOADED in actions
        assert ArtifactAction.REJECTED in actions
