"""
Phase 30 -- Compliance, Legal & User-Facing Disclosures
Test Suite: 212 tests T001-T212
"""

import hashlib
import os
import sys
import time
import uuid
from threading import Thread

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.compliance import (
    ACCEPTANCE_REQUIRED,
    GENESIS_CONST,
    REQUIRES_REASON,
    SAAS_REQUIRED_DOCS,
    AuditAction,
    CancellationError,
    CancellationPolicyConfig,
    CancellationPolicyEngine,
    ComplianceAdmin,
    ComplianceAuditChain,
    ComplianceError,
    ConsentRecord,
    ConsentRequiredError,
    ConsentStatus,
    ConsentStore,
    DisclosureEngine,
    DocumentNotFoundError,
    DocumentStatus,
    DocumentStore,
    DocumentType,
    DocumentVersion,
    JurisdictionCode,
    LegalDocumentFactory,
    MissingReasonError,
    RefundDeniedError,
    RefundPolicyConfig,
    RefundPolicyEngine,
    RetentionPolicyEngine,
    RetentionRule,
    SaaSReadinessChecker,
    SaaSReadinessReport,
    build_compliance_system,
)


def make_doc(
    doc_type=DocumentType.TOS,
    version="1.0.0",
    status=DocumentStatus.ACTIVE,
    jurisdiction=JurisdictionCode.GLOBAL,
    effective_date=None,
    content="Test legal content.",
    actor="admin",
) -> DocumentVersion:
    return DocumentVersion(
        doc_id=str(uuid.uuid4()),
        doc_type=doc_type,
        version=version,
        title=f"Test {doc_type.value} v{version}",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        status=status,
        effective_date=effective_date or time.time(),
        jurisdiction=jurisdiction,
        created_by=actor,
    )


def make_consent(
    user_id="user1",
    tenant_id="t1",
    doc_type=DocumentType.TOS,
    doc_id=None,
    status=ConsentStatus.ACCEPTED,
    expires_at=None,
) -> ConsentRecord:
    return ConsentRecord(
        consent_id=str(uuid.uuid4()),
        user_id=user_id,
        tenant_id=tenant_id,
        doc_id=doc_id or str(uuid.uuid4()),
        doc_type=doc_type,
        doc_version="1.0.0",
        status=status,
        ip_address="1.2.3.4",
        user_agent="TestAgent/1.0",
        accepted_at=time.time(),
        expires_at=expires_at,
    )


def full_doc_store():
    store = DocumentStore()
    for dt in SAAS_REQUIRED_DOCS:
        store.add(make_doc(doc_type=dt))
    return store


def full_consent_store(user_id="user1", tenant_id="t1"):
    store = ConsentStore()
    for dt in ACCEPTANCE_REQUIRED:
        store.record(make_consent(user_id=user_id, tenant_id=tenant_id, doc_type=dt))
    return store


class TestDocumentTypeEnums:
    def test_T001_all_10_doc_types_exist(self):
        types = {dt.value for dt in DocumentType}
        for t in [
            "tos",
            "privacy",
            "risk_disclaimer",
            "license_terms",
            "refund_policy",
            "retention_policy",
            "cancellation_policy",
            "data_processing_agreement",
            "cookie_policy",
            "aml_kyc_policy",
        ]:
            assert t in types
        assert len(types) == 10

    def test_T002_saas_required_docs_has_8_types(self):
        assert len(SAAS_REQUIRED_DOCS) == 8

    def test_T003_acceptance_required_has_4_types(self):
        assert len(ACCEPTANCE_REQUIRED) == 4
        for t in [DocumentType.TOS, DocumentType.PRIVACY, DocumentType.RISK, DocumentType.LICENSE]:
            assert t in ACCEPTANCE_REQUIRED

    def test_T004_requires_reason_actions(self):
        for a in [
            AuditAction.DOC_SUPERSEDED,
            AuditAction.DOC_ARCHIVED,
            AuditAction.CONSENT_WITHDRAWN,
            AuditAction.REFUND_DENIED,
        ]:
            assert a in REQUIRES_REASON

    def test_T005_document_status_values(self):
        assert DocumentStatus.DRAFT.value == "draft"
        assert DocumentStatus.ACTIVE.value == "active"
        assert DocumentStatus.SUPERSEDED.value == "superseded"
        assert DocumentStatus.ARCHIVED.value == "archived"

    def test_T006_consent_status_values(self):
        assert ConsentStatus.ACCEPTED.value == "accepted"
        assert ConsentStatus.DECLINED.value == "declined"
        assert ConsentStatus.EXPIRED.value == "expired"
        assert ConsentStatus.WITHDRAWN.value == "withdrawn"

    def test_T007_jurisdiction_codes(self):
        codes = {j.value for j in JurisdictionCode}
        for c in ["GLOBAL", "EU", "UK", "US"]:
            assert c in codes

    def test_T008_audit_action_values(self):
        assert AuditAction.DOC_PUBLISHED.value == "doc.published"
        assert AuditAction.CONSENT_RECORDED.value == "consent.recorded"
        assert AuditAction.SAAS_CHECK.value == "saas.readiness_check"

    def test_T009_genesis_const_format(self):
        assert GENESIS_CONST == "GENESIS:COMPLIANCE:CHAIN:V30"

    def test_T010_document_version_repr_safe(self):
        doc = make_doc()
        r = repr(doc)
        assert "DocumentVersion" in r and "tos" in r

    def test_T011_consent_record_is_valid_accepted(self):
        assert make_consent(status=ConsentStatus.ACCEPTED).is_valid() is True

    def test_T012_consent_record_invalid_if_declined(self):
        assert make_consent(status=ConsentStatus.DECLINED).is_valid() is False

    def test_T013_consent_record_invalid_if_expired(self):
        assert make_consent(expires_at=time.time() - 1).is_valid() is False

    def test_T014_consent_record_valid_before_expiry(self):
        assert make_consent(expires_at=time.time() + 3600).is_valid() is True

    def test_T015_consent_record_withdrawn_invalid(self):
        assert make_consent(status=ConsentStatus.WITHDRAWN).is_valid() is False

    def test_T016_document_type_str_enum(self):
        assert DocumentType.TOS.value == "tos"


class TestComplianceAuditChain:
    def test_T017_genesis_hash_64_chars(self):
        assert len(ComplianceAuditChain().last_hash) == 64

    def test_T018_record_returns_entry(self):
        e = ComplianceAuditChain().record(AuditAction.DOC_PUBLISHED, actor="admin")
        assert e.action == AuditAction.DOC_PUBLISHED and len(e.chain_hash) == 64

    def test_T019_verify_chain_empty_is_true(self):
        assert ComplianceAuditChain().verify_chain() is True

    def test_T020_verify_chain_single_entry(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="admin")
        assert c.verify_chain() is True

    def test_T021_verify_chain_multiple_entries(self):
        c = ComplianceAuditChain()
        for _ in range(10):
            c.record(AuditAction.CONSENT_RECORDED, actor="u")
        assert c.verify_chain() is True

    def test_T022_tamper_detected_on_hash_change(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="admin")
        list(c._entries)[0].chain_hash = "a" * 64
        assert c.verify_chain() is False

    def test_T023_detect_tampered_returns_seq(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="admin")
        e = list(c._entries)[0]
        e.chain_hash = "b" * 64
        assert e.seq in c.detect_tampered()

    def test_T024_no_tamper_detect_tampered_empty(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="admin")
        assert c.detect_tampered() == []

    def test_T025_requires_reason_missing_raises(self):
        with pytest.raises(MissingReasonError):
            ComplianceAuditChain().record(AuditAction.DOC_ARCHIVED, actor="admin")

    def test_T026_requires_reason_whitespace_raises(self):
        with pytest.raises(MissingReasonError):
            ComplianceAuditChain().record(AuditAction.DOC_ARCHIVED, actor="a", reason="   ")

    def test_T027_requires_reason_provided_ok(self):
        e = ComplianceAuditChain().record(AuditAction.DOC_ARCHIVED, actor="a", reason="expired")
        assert e.action == AuditAction.DOC_ARCHIVED

    def test_T028_sequential_seqs(self):
        c = ComplianceAuditChain()
        e1 = c.record(AuditAction.DOC_PUBLISHED, actor="a")
        e2 = c.record(AuditAction.DOC_PUBLISHED, actor="a")
        assert e2.seq == e1.seq + 1

    def test_T029_query_by_action(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="a")
        c.record(AuditAction.CONSENT_RECORDED, actor="u")
        assert all(
            e.action == AuditAction.DOC_PUBLISHED for e in c.query(action=AuditAction.DOC_PUBLISHED)
        )

    def test_T030_query_by_tenant(self):
        c = ComplianceAuditChain()
        c.record(AuditAction.DOC_PUBLISHED, actor="a", tenant_id="t1")
        c.record(AuditAction.DOC_PUBLISHED, actor="a", tenant_id="t2")
        assert len(c.query(tenant_id="t1")) == 1

    def test_T031_query_limit(self):
        c = ComplianceAuditChain()
        for _ in range(20):
            c.record(AuditAction.DOC_PUBLISHED, actor="a")
        assert len(c.query(limit=5)) == 5

    def test_T032_thread_safe_100_concurrent(self):
        c = ComplianceAuditChain()
        errors = []

        def w():
            try:
                c.record(AuditAction.CONSENT_RECORDED, actor="u")
            except Exception as e:
                errors.append(e)

        ts = [Thread(target=w) for _ in range(100)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == [] and len(c) == 100 and c.verify_chain() is True

    def test_T033_different_secrets_independent(self):
        c1 = ComplianceAuditChain(secret="s1")
        c2 = ComplianceAuditChain(secret="s2")
        c1.record(AuditAction.DOC_PUBLISHED, actor="a")
        c2.record(AuditAction.DOC_PUBLISHED, actor="a")
        assert c1.last_hash != c2.last_hash

    def test_T034_detail_kwargs_in_entry(self):
        e = ComplianceAuditChain().record(AuditAction.DOC_PUBLISHED, actor="a", doc_type="tos")
        assert e.detail.get("doc_type") == "tos"

    def test_T035_chain_length(self):
        c = ComplianceAuditChain()
        assert len(c) == 0
        c.record(AuditAction.DOC_PUBLISHED, actor="a")
        assert len(c) == 1

    def test_T036_last_hash_changes_on_each_record(self):
        c = ComplianceAuditChain()
        h0 = c.last_hash
        c.record(AuditAction.DOC_PUBLISHED, actor="a")
        h1 = c.last_hash
        c.record(AuditAction.DOC_PUBLISHED, actor="a")
        assert h0 != h1 != c.last_hash


class TestDocumentStore:
    def test_T037_add_and_get(self):
        s = DocumentStore()
        d = make_doc()
        s.add(d)
        assert s.get(d.doc_id).doc_id == d.doc_id

    def test_T038_get_missing_raises(self):
        with pytest.raises(DocumentNotFoundError):
            DocumentStore().get("x")

    def test_T039_active_for_type_returns_active(self):
        s = DocumentStore()
        d = make_doc(doc_type=DocumentType.PRIVACY)
        s.add(d)
        assert s.active_for_type(DocumentType.PRIVACY).doc_id == d.doc_id

    def test_T040_active_for_type_ignores_archived(self):
        s = DocumentStore()
        s.add(make_doc(status=DocumentStatus.ARCHIVED))
        assert s.active_for_type(DocumentType.TOS) is None

    def test_T041_active_for_type_returns_latest(self):
        s = DocumentStore()
        s.add(make_doc(version="1.0.0", effective_date=time.time() - 1000))
        s.add(make_doc(version="2.0.0", effective_date=time.time()))
        assert s.active_for_type(DocumentType.TOS).version == "2.0.0"

    def test_T042_list_active_returns_only_active(self):
        s = DocumentStore()
        s.add(make_doc(doc_type=DocumentType.TOS, status=DocumentStatus.ACTIVE))
        s.add(make_doc(doc_type=DocumentType.PRIVACY, status=DocumentStatus.ARCHIVED))
        assert len(s.list_active()) == 1

    def test_T043_all_types_covered_true(self):
        ok, missing = full_doc_store().all_types_covered(SAAS_REQUIRED_DOCS)
        assert ok is True and missing == []

    def test_T044_all_types_covered_false(self):
        ok, missing = DocumentStore().all_types_covered({DocumentType.TOS})
        assert ok is False and DocumentType.TOS in missing

    def test_T045_supersede_requires_reason(self):
        s = DocumentStore()
        o = make_doc()
        n = make_doc()
        s.add(o)
        s.add(n)
        with pytest.raises(MissingReasonError):
            s.supersede(o.doc_id, n.doc_id, "a", "")

    def test_T046_supersede_updates_status(self):
        s = DocumentStore()
        o = make_doc()
        n = make_doc()
        s.add(o)
        s.add(n)
        s.supersede(o.doc_id, n.doc_id, "a", "new version")
        assert s.get(o.doc_id).status == DocumentStatus.SUPERSEDED

    def test_T047_archive_requires_reason(self):
        s = DocumentStore()
        d = make_doc()
        s.add(d)
        with pytest.raises(MissingReasonError):
            s.archive(d.doc_id, "a", "")

    def test_T048_archive_updates_status(self):
        s = DocumentStore()
        d = make_doc()
        s.add(d)
        s.archive(d.doc_id, "a", "outdated")
        assert s.get(d.doc_id).status == DocumentStatus.ARCHIVED

    def test_T049_count(self):
        s = DocumentStore()
        assert s.count() == 0
        s.add(make_doc())
        assert s.count() == 1

    def test_T050_thread_safe_add(self):
        s = DocumentStore()
        docs = [make_doc() for _ in range(50)]
        ts = [Thread(target=s.add, args=(d,)) for d in docs]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert s.count() == 50

    def test_T051_jurisdiction_global_always_matches(self):
        s = DocumentStore()
        s.add(make_doc(jurisdiction=JurisdictionCode.GLOBAL))
        assert s.active_for_type(DocumentType.TOS, JurisdictionCode.EU) is not None

    def test_T052_jurisdiction_specific_matches(self):
        s = DocumentStore()
        s.add(make_doc(jurisdiction=JurisdictionCode.EU))
        assert s.active_for_type(DocumentType.TOS, JurisdictionCode.EU) is not None

    def test_T053_supersede_missing_doc_raises(self):
        with pytest.raises(DocumentNotFoundError):
            DocumentStore().supersede("x", "y", "a", "r")

    def test_T054_archive_missing_doc_raises(self):
        with pytest.raises(DocumentNotFoundError):
            DocumentStore().archive("x", "a", "r")

    def test_T055_active_for_type_none_if_no_active(self):
        assert DocumentStore().active_for_type(DocumentType.TOS) is None

    def test_T056_list_active_empty_store(self):
        assert DocumentStore().list_active() == []


class TestConsentStore:
    def test_T057_record_and_get(self):
        s = ConsentStore()
        c = make_consent()
        s.record(c)
        assert s.get(c.consent_id) is not None

    def test_T058_latest_for_returns_most_recent(self):
        s = ConsentStore()
        c1 = make_consent(user_id="u1")
        c1.accepted_at = time.time() - 100
        c2 = make_consent(user_id="u1")
        c2.accepted_at = time.time()
        s.record(c1)
        s.record(c2)
        assert s.latest_for("u1", DocumentType.TOS).consent_id == c2.consent_id

    def test_T059_user_has_accepted_true(self):
        s = ConsentStore()
        s.record(make_consent(user_id="u1", status=ConsentStatus.ACCEPTED))
        assert s.user_has_accepted("u1", DocumentType.TOS) is True

    def test_T060_user_has_accepted_false_no_record(self):
        assert ConsentStore().user_has_accepted("u1", DocumentType.TOS) is False

    def test_T061_user_has_accepted_false_if_declined(self):
        s = ConsentStore()
        s.record(make_consent(status=ConsentStatus.DECLINED))
        assert s.user_has_accepted("user1", DocumentType.TOS) is False

    def test_T062_withdraw_requires_reason(self):
        s = ConsentStore()
        c = make_consent()
        s.record(c)
        with pytest.raises(MissingReasonError):
            s.withdraw(c.consent_id, "", "a")

    def test_T063_withdraw_updates_status(self):
        s = ConsentStore()
        c = make_consent()
        s.record(c)
        s.withdraw(c.consent_id, "user request", "admin")
        assert s.get(c.consent_id).status == ConsentStatus.WITHDRAWN

    def test_T064_withdraw_missing_raises(self):
        with pytest.raises(ComplianceError):
            ConsentStore().withdraw("x", "r", "a")

    def test_T065_pending_for_user_all_accepted(self):
        assert (
            full_consent_store().pending_for_user(
                "user1", "t1", ACCEPTANCE_REQUIRED, full_doc_store()
            )
            == []
        )

    def test_T066_pending_for_user_missing_consent(self):
        assert len(
            ConsentStore().pending_for_user("u", "t", ACCEPTANCE_REQUIRED, full_doc_store())
        ) == len(ACCEPTANCE_REQUIRED)

    def test_T067_tenant_isolation(self):
        s = ConsentStore()
        s.record(make_consent(user_id="u1", tenant_id="t1"))
        assert s.user_has_accepted("u1", DocumentType.TOS, "t2") is False
        assert s.user_has_accepted("u1", DocumentType.TOS, "t1") is True

    def test_T068_count(self):
        s = ConsentStore()
        assert s.count() == 0
        s.record(make_consent())
        assert s.count() == 1

    def test_T069_thread_safe_record(self):
        s = ConsentStore()
        cs = [make_consent() for _ in range(50)]
        ts = [Thread(target=s.record, args=(c,)) for c in cs]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert s.count() == 50

    def test_T070_latest_for_none_if_no_records(self):
        assert ConsentStore().latest_for("u1", DocumentType.TOS) is None

    def test_T071_expired_consent_not_valid(self):
        s = ConsentStore()
        s.record(make_consent(expires_at=time.time() - 1))
        assert s.user_has_accepted("user1", DocumentType.TOS) is False

    def test_T072_withdraw_sets_withdrawn_at(self):
        s = ConsentStore()
        c = make_consent()
        s.record(c)
        s.withdraw(c.consent_id, "req", "admin")
        assert s.get(c.consent_id).withdrawn_at is not None

    def test_T073_multiple_doc_types_independent(self):
        s = ConsentStore()
        s.record(make_consent(doc_type=DocumentType.TOS))
        assert s.user_has_accepted("user1", DocumentType.TOS) is True
        assert s.user_has_accepted("user1", DocumentType.PRIVACY) is False

    def test_T074_pending_ignores_no_active_doc(self):
        ds = DocumentStore()
        ds.add(make_doc(doc_type=DocumentType.TOS))
        pending = ConsentStore().pending_for_user(
            "u", "t", {DocumentType.TOS, DocumentType.PRIVACY}, ds
        )
        assert DocumentType.TOS in pending and DocumentType.PRIVACY not in pending

    def test_T075_get_returns_none_if_missing(self):
        assert ConsentStore().get("x") is None

    def test_T076_withdraw_whitespace_reason_raises(self):
        s = ConsentStore()
        c = make_consent()
        s.record(c)
        with pytest.raises(MissingReasonError):
            s.withdraw(c.consent_id, "   ", "a")


class TestDisclosureEngine:
    def _setup(self, grace_days=7):
        audit = ComplianceAuditChain()
        ds = full_doc_store()
        cs = ConsentStore()
        return DisclosureEngine(ds, cs, audit, grace_days=grace_days), ds, cs, audit

    def test_T077_fully_accepted_user_allowed(self):
        e, ds, cs, _ = self._setup()
        for dt in ACCEPTANCE_REQUIRED:
            cs.record(make_consent(user_id="u1", doc_type=dt))
        allowed, missing = e.check_access("u1", "t1", time.time() - 86400)
        assert allowed is True and missing == []

    def test_T078_new_user_in_grace_period_allowed(self):
        e, ds, cs, _ = self._setup(grace_days=7)
        allowed, missing = e.check_access("new", "t1", time.time())
        assert allowed is True and len(missing) > 0

    def test_T079_old_user_missing_consent_blocked(self):
        e, ds, cs, _ = self._setup(grace_days=0)
        with pytest.raises(ConsentRequiredError):
            e.check_access("u", "t", time.time() - 9999)

    def test_T080_grace_period_expired_blocked(self):
        e, ds, cs, _ = self._setup(grace_days=0)
        with pytest.raises(ConsentRequiredError):
            e.check_access("u", "t", time.time() - 1)

    def test_T081_record_consent_creates_record(self):
        e, ds, cs, _ = self._setup()
        c = e.record_consent("u", "t", DocumentType.TOS, "1.2.3.4", "A")
        assert c.doc_type == DocumentType.TOS and c.status == ConsentStatus.ACCEPTED

    def test_T082_record_consent_with_ttl(self):
        e, ds, cs, _ = self._setup()
        c = e.record_consent("u", "t", DocumentType.TOS, "1.2.3.4", "A", ttl_days=30)
        assert c.expires_at is not None and c.expires_at > time.time()

    def test_T083_record_consent_no_active_doc_raises(self):
        e = DisclosureEngine(DocumentStore(), ConsentStore(), ComplianceAuditChain())
        with pytest.raises(DocumentNotFoundError):
            e.record_consent("u", "t", DocumentType.TOS, "1", "A")

    def test_T084_record_consent_audited(self):
        e, ds, cs, audit = self._setup()
        e.record_consent("u", "t", DocumentType.TOS, "1.2.3.4", "A")
        assert len(audit.query(action=AuditAction.CONSENT_RECORDED)) == 1

    def test_T085_block_audited(self):
        e, ds, cs, audit = self._setup(grace_days=0)
        try:
            e.check_access("u", "t", time.time() - 9999)
        except ConsentRequiredError:
            pass
        assert len(audit.query(action=AuditAction.DISCLOSURE_BLOCK)) == 1

    def test_T086_hook_called_on_block(self):
        e, ds, cs, _ = self._setup(grace_days=0)
        hooked = []
        e.add_hook(lambda u, t, m: hooked.append(u))
        try:
            e.check_access("u1", "t", time.time() - 9999)
        except ConsentRequiredError:
            pass
        assert "u1" in hooked

    def test_T087_hook_exception_does_not_propagate(self):
        e, ds, cs, _ = self._setup(grace_days=0)
        e.add_hook(lambda u, t, m: (_ for _ in ()).throw(RuntimeError("fail")))
        try:
            e.check_access("u", "t", time.time() - 9999)
        except ConsentRequiredError:
            pass

    def test_T088_fully_accepted_audited_as_allowed(self):
        e, ds, cs, audit = self._setup()
        for dt in ACCEPTANCE_REQUIRED:
            cs.record(make_consent(user_id="u", doc_type=dt))
        e.check_access("u", "t", time.time() - 86400)
        assert len(audit.query(action=AuditAction.DISCLOSURE_GATE)) >= 1

    def test_T089_check_access_missing_list_contains_types(self):
        e, ds, cs, _ = self._setup(grace_days=365)
        _, missing = e.check_access("u", "t", time.time())
        for m in missing:
            assert isinstance(m, DocumentType)

    def test_T090_multiple_users_isolated(self):
        e, ds, cs, _ = self._setup()
        for dt in ACCEPTANCE_REQUIRED:
            cs.record(make_consent(user_id="u1", tenant_id="t", doc_type=dt))
        allowed, _ = e.check_access("u1", "t", time.time() - 86400)
        assert allowed is True
        with pytest.raises(ConsentRequiredError):
            e.check_access("u2", "t", time.time() - 9999999)

    def test_T091_record_consent_stores_ip(self):
        e, ds, cs, _ = self._setup()
        c = e.record_consent("u", "t", DocumentType.TOS, "10.0.0.1", "A")
        assert c.ip_address == "10.0.0.1"

    def test_T092_record_consent_stores_user_agent(self):
        e, ds, cs, _ = self._setup()
        c = e.record_consent("u", "t", DocumentType.TOS, "1.2.3.4", "BotAgent/2")
        assert c.user_agent == "BotAgent/2"

    def test_T093_record_consent_version_matches_active_doc(self):
        e, ds, cs, _ = self._setup()
        active = ds.active_for_type(DocumentType.TOS)
        c = e.record_consent("u", "t", DocumentType.TOS, "1.2.3.4", "A")
        assert c.doc_version == active.version

    def test_T094_grace_period_exactly_at_boundary(self):
        e, ds, cs, _ = self._setup(grace_days=1)
        with pytest.raises(ConsentRequiredError):
            e.check_access("u", "t", time.time() - 86401)

    def test_T095_consent_required_error_lists_missing(self):
        e, ds, cs, _ = self._setup(grace_days=0)
        try:
            e.check_access("u1", "t", time.time() - 9999999)
        except ConsentRequiredError as ex:
            assert "u1" in str(ex)

    def test_T096_empty_required_set_always_allowed(self):
        e, ds, cs, _ = self._setup()
        allowed, missing = e.check_access("u", "t", time.time() - 9999, required=set())
        assert allowed is True and missing == []


class TestRetentionPolicyEngine:
    def test_T097_default_rules_loaded(self):
        e = RetentionPolicyEngine()
        for cat in ["user_pii", "trading_logs", "audit_logs"]:
            assert e.get(cat) is not None

    def test_T098_default_10_categories(self):
        assert len(RetentionPolicyEngine().all_rules()) == 10

    def test_T099_user_pii_730_days(self):
        assert RetentionPolicyEngine().get("user_pii").retain_days == 730

    def test_T100_trading_logs_7_years(self):
        assert RetentionPolicyEngine().get("trading_logs").retain_days == 2555

    def test_T101_is_expired_true(self):
        assert RetentionPolicyEngine().is_expired("user_pii", time.time() - 800 * 86400) is True

    def test_T102_is_expired_false(self):
        assert RetentionPolicyEngine().is_expired("user_pii", time.time() - 10 * 86400) is False

    def test_T103_is_expired_false_unknown_category(self):
        assert RetentionPolicyEngine().is_expired("unknown", time.time() - 99999) is False

    def test_T104_set_custom_rule(self):
        e = RetentionPolicyEngine(audit=ComplianceAuditChain())
        e.set(RetentionRule("custom", 365, "Ops", JurisdictionCode.GLOBAL), actor="a")
        assert e.get("custom") is not None

    def test_T105_set_rule_audited(self):
        audit = ComplianceAuditChain()
        e = RetentionPolicyEngine(audit=audit)
        e.set(RetentionRule("x", 30, "Ops", JurisdictionCode.GLOBAL), actor="a")
        assert len(audit.query(action=AuditAction.RETENTION_SET)) == 1

    def test_T106_categories_sorted(self):
        cats = RetentionPolicyEngine().categories()
        assert cats == sorted(cats)

    def test_T107_default_rules_immutable_on_init(self):
        e1 = RetentionPolicyEngine()
        e2 = RetentionPolicyEngine()
        e1.set(RetentionRule("test", 1, "x", JurisdictionCode.GLOBAL), actor="a")
        assert e2.get("test") is None

    def test_T108_all_rules_returns_dict(self):
        rules = RetentionPolicyEngine().all_rules()
        assert isinstance(rules, dict) and "user_pii" in rules

    def test_T109_kyc_5_years(self):
        assert RetentionPolicyEngine().get("kyc_documents").retain_days == 1825

    def test_T110_payment_records_7_years(self):
        assert RetentionPolicyEngine().get("payment_records").retain_days == 2555

    def test_T111_session_data_30_days(self):
        assert RetentionPolicyEngine().get("session_data").retain_days == 30

    def test_T112_backup_data_90_days(self):
        assert RetentionPolicyEngine().get("backup_data").retain_days == 90


class TestRefundPolicyEngine:
    def _e(self, **kw):
        audit = ComplianceAuditChain()
        return RefundPolicyEngine(
            config=RefundPolicyConfig(**kw) if kw else RefundPolicyConfig(), audit=audit
        ), audit

    def test_T113_request_refund_creates_record(self):
        e, _ = self._e()
        req = e.request_refund("u", "t", 5000, "USD", "reason", time.time())
        assert req.request_id != "" and req.status == "pending"

    def test_T114_request_refund_requires_reason(self):
        e, _ = self._e()
        with pytest.raises(MissingReasonError):
            e.request_refund("u", "t", 5000, "USD", "", time.time())

    def test_T115_evaluate_within_window_approved(self):
        e, _ = self._e(window_days=14)
        req = e.request_refund("u", "t", 5000, "USD", "r", time.time() - 5 * 86400)
        assert e.evaluate(req.request_id, "admin").status == "approved"

    def test_T116_evaluate_outside_window_denied(self):
        e, _ = self._e(window_days=14)
        req = e.request_refund("u", "t", 5000, "USD", "r", time.time() - 20 * 86400)
        with pytest.raises(RefundDeniedError):
            e.evaluate(req.request_id, "admin")

    def test_T117_evaluate_amount_exceeds_limit_denied(self):
        e, _ = self._e(max_amount_cents=1000)
        req = e.request_refund("u", "t", 5000, "USD", "r", time.time())
        with pytest.raises(RefundDeniedError):
            e.evaluate(req.request_id, "admin")

    def test_T118_approve_audited(self):
        e, audit = self._e()
        req = e.request_refund("u", "t", 500, "USD", "r", time.time())
        e.evaluate(req.request_id, "admin")
        assert len(audit.query(action=AuditAction.REFUND_ISSUED)) == 1

    def test_T119_deny_audited(self):
        e, audit = self._e(window_days=1)
        req = e.request_refund("u", "t", 500, "USD", "r", time.time() - 10 * 86400)
        try:
            e.evaluate(req.request_id, "admin")
        except RefundDeniedError:
            pass
        assert len(audit.query(action=AuditAction.REFUND_DENIED)) == 1

    def test_T120_get_returns_request(self):
        e, _ = self._e()
        req = e.request_refund("u", "t", 500, "USD", "r", time.time())
        assert e.get(req.request_id) is not None

    def test_T121_list_for_user(self):
        e, _ = self._e()
        e.request_refund("u1", "t", 500, "USD", "r", time.time())
        e.request_refund("u1", "t", 600, "USD", "r", time.time())
        e.request_refund("u2", "t", 700, "USD", "r", time.time())
        assert len(e.list_for_user("u1")) == 2

    def test_T122_missing_request_raises(self):
        e, _ = self._e()
        with pytest.raises(ComplianceError):
            e.evaluate("x", "admin")

    def test_T123_default_window_14_days(self):
        e, _ = self._e()
        assert e._config.window_days == 14

    def test_T124_denied_has_denial_reason(self):
        e, _ = self._e(window_days=1)
        req = e.request_refund("u", "t", 500, "USD", "r", time.time() - 10 * 86400)
        try:
            e.evaluate(req.request_id, "admin")
        except RefundDeniedError:
            pass
        updated = e.get(req.request_id)
        assert updated.denial_reason is not None and updated.status == "denied"

    def test_T125_approved_has_resolved_at(self):
        e, _ = self._e()
        req = e.request_refund("u", "t", 500, "USD", "r", time.time())
        result = e.evaluate(req.request_id, "admin")
        assert result.resolved_at is not None and result.resolved_by == "admin"

    def test_T126_whitespace_reason_raises(self):
        e, _ = self._e()
        with pytest.raises(MissingReasonError):
            e.request_refund("u", "t", 500, "USD", "   ", time.time())

    def test_T127_require_reason_false_allows_empty(self):
        e, _ = self._e(require_reason=False)
        assert e.request_refund("u", "t", 500, "USD", "", time.time()).status == "pending"

    def test_T128_get_missing_returns_none(self):
        assert RefundPolicyEngine().get("x") is None


class TestCancellationPolicyEngine:
    def _e(self, **kw):
        audit = ComplianceAuditChain()
        return CancellationPolicyEngine(
            config=CancellationPolicyConfig(**kw) if kw else CancellationPolicyConfig(), audit=audit
        ), audit

    def test_T129_request_cancellation_creates_record(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "switching")
        assert req.request_id != "" and req.status == "pending"

    def test_T130_request_requires_reason(self):
        e, _ = self._e()
        with pytest.raises(MissingReasonError):
            e.request_cancellation("u", "t", "")

    def test_T131_notice_period_sets_effective_date(self):
        e, _ = self._e(notice_days=30)
        req = e.request_cancellation("u", "t", "r")
        assert req.effective_at > time.time() + 29 * 86400

    def test_T132_immediate_cancellation_blocked_by_default(self):
        e, _ = self._e(immediate_allowed=False)
        with pytest.raises(CancellationError):
            e.request_cancellation("u", "t", "r", immediate=True)

    def test_T133_immediate_cancellation_allowed_when_configured(self):
        e, _ = self._e(immediate_allowed=True)
        assert e.request_cancellation("u", "t", "r", immediate=True).notice_days == 0

    def test_T134_confirm_cancellation(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r")
        assert e.confirm_cancellation(req.request_id, "admin").status == "confirmed"

    def test_T135_confirm_audited(self):
        e, audit = self._e()
        req = e.request_cancellation("u", "t", "r")
        e.confirm_cancellation(req.request_id, "admin")
        assert len(audit.query(action=AuditAction.CANCEL_CONFIRMED)) == 1

    def test_T136_double_confirm_raises(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r")
        e.confirm_cancellation(req.request_id, "admin")
        with pytest.raises(CancellationError):
            e.confirm_cancellation(req.request_id, "admin")

    def test_T137_abort_cancellation(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r")
        assert e.abort_cancellation(req.request_id).status == "cancelled"

    def test_T138_abort_confirmed_raises(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r")
        e.confirm_cancellation(req.request_id, "admin")
        with pytest.raises(CancellationError):
            e.abort_cancellation(req.request_id)

    def test_T139_confirm_missing_raises(self):
        e, _ = self._e()
        with pytest.raises(CancellationError):
            e.confirm_cancellation("x", "a")

    def test_T140_abort_missing_raises(self):
        e, _ = self._e()
        with pytest.raises(CancellationError):
            e.abort_cancellation("x")

    def test_T141_data_deletion_flag(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r", data_deletion=True)
        assert req.data_deletion is True

    def test_T142_request_audited(self):
        e, audit = self._e()
        e.request_cancellation("u", "t", "r")
        assert len(audit.query(action=AuditAction.CANCEL_REQUESTED)) == 1

    def test_T143_default_notice_30_days(self):
        e, _ = self._e()
        assert e._config.notice_days == 30

    def test_T144_get_request(self):
        e, _ = self._e()
        req = e.request_cancellation("u", "t", "r")
        assert e.get(req.request_id) is not None


class TestSaaSReadinessChecker:
    def test_T145_fully_configured_passes(self):
        r = build_compliance_system()["saas_checker"].check()
        assert r.passed is True and r.score >= 80

    def test_T146_missing_docs_fails(self):
        sys_ = build_compliance_system()
        sys_["doc_store"]._docs.clear()
        r = sys_["saas_checker"].check()
        assert r.passed is False and len(r.missing_docs) > 0

    def test_T147_score_100_when_perfect(self):
        assert build_compliance_system()["saas_checker"].check().score == 100

    def test_T148_report_has_checked_at(self):
        assert build_compliance_system()["saas_checker"].check().checked_at > 0

    def test_T149_to_dict_serializable(self):
        d = build_compliance_system()["saas_checker"].check().to_dict()
        for k in ["passed", "score", "missing_docs"]:
            assert k in d

    def test_T150_check_audited(self):
        sys_ = build_compliance_system()
        sys_["saas_checker"].check()
        assert len(sys_["audit"].query(action=AuditAction.SAAS_CHECK)) >= 1

    def test_T151_missing_retention_reduces_score(self):
        sys_ = build_compliance_system()
        for cat in SaaSReadinessChecker.REQUIRED_RETENTION_CATEGORIES:
            sys_["retention"]._rules.pop(cat, None)
        r = sys_["saas_checker"].check()
        assert r.score < 100 and len(r.gaps) > 0

    def test_T152_tampered_chain_fails(self):
        sys_ = build_compliance_system()
        entries = list(sys_["audit"]._entries)
        if entries:
            entries[0].chain_hash = "a" * 64
        assert sys_["saas_checker"].check().passed is False

    def test_T153_gaps_is_list(self):
        assert isinstance(build_compliance_system()["saas_checker"].check().gaps, list)

    def test_T154_recommendations_is_list(self):
        assert isinstance(build_compliance_system()["saas_checker"].check().recommendations, list)

    def test_T155_score_clamped_to_zero(self):
        sys_ = build_compliance_system()
        sys_["doc_store"]._docs.clear()
        for cat in SaaSReadinessChecker.REQUIRED_RETENTION_CATEGORIES:
            sys_["retention"]._rules.pop(cat, None)
        entries = list(sys_["audit"]._entries)
        if entries:
            entries[0].chain_hash = "a" * 64
        assert sys_["saas_checker"].check().score >= 0

    def test_T156_missing_docs_in_report(self):
        sys_ = build_compliance_system()
        sys_["doc_store"]._docs.clear()
        r = sys_["saas_checker"].check()
        assert all(isinstance(d, DocumentType) for d in r.missing_docs)

    def test_T157_required_retention_categories(self):
        cats = SaaSReadinessChecker.REQUIRED_RETENTION_CATEGORIES
        for c in ["user_pii", "trading_logs", "audit_logs", "financial_records", "payment_records"]:
            assert c in cats

    def test_T158_passed_false_when_score_below_80(self):
        sys_ = build_compliance_system()
        sys_["doc_store"]._docs.clear()
        assert sys_["saas_checker"].check().passed is False

    def test_T159_refund_window_zero_fails(self):
        r = build_compliance_system(refund_config=RefundPolicyConfig(window_days=0))[
            "saas_checker"
        ].check()
        assert r.score < 100

    def test_T160_all_saas_docs_in_active_store(self):
        sys_ = build_compliance_system()
        active_types = {d.doc_type for d in sys_["doc_store"].list_active()}
        for req in SAAS_REQUIRED_DOCS:
            assert req in active_types

    def test_T161_checker_fields(self):
        r = SaaSReadinessReport(
            passed=True, score=100, missing_docs=[], outdated_docs=[], gaps=[], recommendations=[]
        )
        assert r.passed is True and r.score == 100

    def test_T162_check_twice_consistent(self):
        checker = build_compliance_system()["saas_checker"]
        r1 = checker.check()
        r2 = checker.check()
        assert r1.passed == r2.passed and r1.score == r2.score

    def test_T163_cancellation_negative_notice_fails(self):
        r = build_compliance_system(cancellation_config=CancellationPolicyConfig(notice_days=-1))[
            "saas_checker"
        ].check()
        assert r.score < 100

    def test_T164_full_system_build_returns_all_components(self):
        sys_ = build_compliance_system()
        for k in [
            "audit",
            "doc_store",
            "consent_store",
            "retention",
            "refund",
            "cancellation",
            "disclosure",
            "admin",
            "saas_checker",
            "factory",
        ]:
            assert k in sys_


class TestComplianceAdmin:
    def _a(self):
        audit = ComplianceAuditChain()
        ds = DocumentStore()
        cs = ConsentStore()
        return ComplianceAdmin(ds, cs, audit), ds, cs, audit

    def test_T165_publish_document_active(self):
        a, ds, cs, _ = self._a()
        doc = a.publish_document(DocumentType.TOS, "1.0.0", "TOS", "content", time.time(), "admin")
        assert doc.status == DocumentStatus.ACTIVE

    def test_T166_publish_supersedes_old(self):
        a, ds, cs, _ = self._a()
        old = a.publish_document(DocumentType.TOS, "1.0.0", "TOS v1", "old", time.time(), "admin")
        new = a.publish_document(
            DocumentType.TOS,
            "2.0.0",
            "TOS v2",
            "new",
            time.time(),
            "admin",
            supersede_reason="update",
        )
        assert ds.get(old.doc_id).status == DocumentStatus.SUPERSEDED
        assert ds.get(new.doc_id).status == DocumentStatus.ACTIVE

    def test_T167_publish_audited(self):
        a, ds, cs, audit = self._a()
        a.publish_document(DocumentType.PRIVACY, "1.0", "P", "c", time.time(), "admin")
        assert len(audit.query(action=AuditAction.DOC_PUBLISHED)) == 1

    def test_T168_archive_document(self):
        a, ds, cs, _ = self._a()
        doc = a.publish_document(DocumentType.COOKIE, "1.0", "C", "c", time.time(), "admin")
        a.archive_document(doc.doc_id, "admin", "outdated")
        assert ds.get(doc.doc_id).status == DocumentStatus.ARCHIVED

    def test_T169_archive_requires_reason(self):
        a, ds, cs, _ = self._a()
        doc = a.publish_document(DocumentType.COOKIE, "1.0", "C", "c", time.time(), "admin")
        with pytest.raises(MissingReasonError):
            a.archive_document(doc.doc_id, "admin", "")

    def test_T170_archive_audited(self):
        a, ds, cs, audit = self._a()
        doc = a.publish_document(DocumentType.COOKIE, "1.0", "C", "c", time.time(), "admin")
        a.archive_document(doc.doc_id, "admin", "outdated")
        assert len(audit.query(action=AuditAction.DOC_ARCHIVED)) == 1

    def test_T171_bulk_consent_check_finds_missing(self):
        a, ds, cs, _ = self._a()
        a.publish_document(DocumentType.TOS, "1.0", "T", "c", time.time(), "admin")
        cs.record(make_consent(user_id="u1", doc_type=DocumentType.TOS))
        result = a.bulk_consent_check(["u1", "u2"], "t1", required={DocumentType.TOS})
        assert "u2" in result and "u1" not in result

    def test_T172_audit_summary_structure(self):
        a, ds, cs, _ = self._a()
        a.publish_document(DocumentType.TOS, "1.0", "T", "c", time.time(), "admin")
        s = a.audit_summary()
        for k in ["total_entries", "chain_valid", "docs_active", "consents_total"]:
            assert k in s
        assert s["chain_valid"] is True

    def test_T173_content_hash_sha256(self):
        c = "test"
        assert ComplianceAdmin._content_hash(c) == hashlib.sha256(c.encode()).hexdigest()

    def test_T174_publish_all_10_types(self):
        a, ds, cs, _ = self._a()
        for dt in DocumentType:
            a.publish_document(dt, "1.0", "T", "c", time.time(), "admin")
        assert len(ds.list_active()) == 10

    def test_T175_bulk_consent_empty_user_list(self):
        a, ds, cs, _ = self._a()
        assert a.bulk_consent_check([], "t") == {}

    def test_T176_supersede_audited(self):
        a, ds, cs, audit = self._a()
        a.publish_document(DocumentType.TOS, "1.0", "T", "old", time.time(), "admin")
        a.publish_document(
            DocumentType.TOS, "2.0", "T", "new", time.time(), "admin", supersede_reason="update"
        )
        assert len(audit.query(action=AuditAction.DOC_SUPERSEDED)) >= 1

    def test_T177_audit_summary_doc_count(self):
        a, ds, cs, _ = self._a()
        a.publish_document(DocumentType.TOS, "1.0", "T", "c", time.time(), "admin")
        assert a.audit_summary()["docs_active"] == 1

    def test_T178_audit_summary_consent_count(self):
        a, ds, cs, _ = self._a()
        cs.record(make_consent())
        assert a.audit_summary()["consents_total"] == 1

    def test_T179_bulk_check_multi_missing(self):
        a, ds, cs, _ = self._a()
        for dt in ACCEPTANCE_REQUIRED:
            a.publish_document(dt, "1.0", "T", "c", time.time(), "admin")
        result = a.bulk_consent_check(["u1"], "t", ACCEPTANCE_REQUIRED)
        assert "u1" in result and len(result["u1"]) == len(ACCEPTANCE_REQUIRED)

    def test_T180_audit_last_hash_truncated(self):
        a, ds, cs, _ = self._a()
        a.publish_document(DocumentType.TOS, "1.0", "T", "c", time.time(), "admin")
        assert a.audit_summary()["last_hash"].endswith("...")


class TestLegalDocumentFactory:
    def test_T181_generates_tos(self):
        t, c = LegalDocumentFactory().generate(DocumentType.TOS)
        assert "Terms of Service" in t and len(c) > 200

    def test_T182_generates_privacy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.PRIVACY)
        assert "Privacy Policy" in t and "GDPR" in c

    def test_T183_generates_risk_disclaimer(self):
        t, c = LegalDocumentFactory().generate(DocumentType.RISK)
        assert "Risk" in t and "INVESTMENT ADVICE" in c

    def test_T184_generates_license_terms(self):
        t, c = LegalDocumentFactory().generate(DocumentType.LICENSE)
        assert "License" in t and "TRIAL" in c and "PRO" in c

    def test_T185_generates_refund_policy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.REFUND)
        assert "Refund" in t and "14" in c

    def test_T186_generates_retention_policy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.RETENTION)
        assert "Retention" in t and "7 years" in c

    def test_T187_generates_cancellation_policy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.CANCELLATION)
        assert "Cancellation" in t and "30 days" in c

    def test_T188_generates_dpa(self):
        t, c = LegalDocumentFactory().generate(DocumentType.DPA)
        assert "Processing" in t and "GDPR" in c

    def test_T189_generates_cookie_policy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.COOKIE)
        assert "Cookie" in t and "session_id" in c

    def test_T190_generates_aml_policy(self):
        t, c = LegalDocumentFactory().generate(DocumentType.AML)
        assert "AML" in t and "KYC" in c and "PEP" in c

    def test_T191_company_name_in_content(self):
        _, c = LegalDocumentFactory(company_name="TestCorp").generate(DocumentType.TOS)
        assert "TestCorp" in c

    def test_T192_product_name_in_content(self):
        _, c = LegalDocumentFactory(product_name="MyApp").generate(DocumentType.TOS)
        assert "MyApp" in c

    def test_T193_support_email_in_content(self):
        _, c = LegalDocumentFactory(support_email="x@test.io").generate(DocumentType.TOS)
        assert "x@test.io" in c

    def test_T194_all_10_types_generate_without_error(self):
        f = LegalDocumentFactory()
        for dt in DocumentType:
            t, c = f.generate(dt)
            assert len(t) > 5 and len(c) > 100

    def test_T195_content_hash_stable(self):
        f = LegalDocumentFactory()
        _, c1 = f.generate(DocumentType.TOS)
        _, c2 = f.generate(DocumentType.TOS)
        assert hashlib.sha256(c1.encode()).hexdigest() == hashlib.sha256(c2.encode()).hexdigest()

    def test_T196_jurisdiction_in_tos(self):
        _, c = LegalDocumentFactory(jurisdiction="New South Wales").generate(DocumentType.TOS)
        assert "New South Wales" in c


class TestIntegrationFlows:
    def test_T197_full_saas_ready_system(self):
        r = build_compliance_system()["saas_checker"].check()
        assert r.passed is True and r.score == 100 and r.missing_docs == [] and r.gaps == []

    def test_T198_new_user_onboarding_flow(self):
        sys_ = build_compliance_system()
        engine = sys_["disclosure"]
        uid = "new_user_001"
        tid = "t1"
        created = time.time()
        allowed, missing = engine.check_access(uid, tid, created)
        assert allowed is True
        for dt in ACCEPTANCE_REQUIRED:
            engine.record_consent(uid, tid, dt, "1.2.3.4", "B")
        allowed2, missing2 = engine.check_access(uid, tid, created)
        assert allowed2 is True and missing2 == []

    def test_T199_refund_within_window_approved(self):
        r = build_compliance_system()["refund"]
        req = r.request_refund("u", "t", 4999, "USD", "not as described", time.time() - 3 * 86400)
        assert r.evaluate(req.request_id, "admin").status == "approved"

    def test_T200_cancellation_full_flow(self):
        c = build_compliance_system()["cancellation"]
        req = c.request_cancellation("u", "t", "switching", data_deletion=True)
        assert req.status == "pending"
        conf = c.confirm_cancellation(req.request_id, "admin")
        assert conf.status == "confirmed" and conf.data_deletion is True

    def test_T201_audit_chain_integrity_after_all_ops(self):
        sys_ = build_compliance_system()
        engine = sys_["disclosure"]
        for dt in ACCEPTANCE_REQUIRED:
            engine.record_consent("u", "t", dt, "1", "A")
        req = sys_["refund"].request_refund("u", "t", 100, "USD", "r", time.time())
        sys_["refund"].evaluate(req.request_id, "admin")
        assert sys_["audit"].verify_chain() is True

    def test_T202_100_users_concurrent_consent(self):
        sys_ = build_compliance_system()
        errors = []

        def accept(uid):
            try:
                for dt in ACCEPTANCE_REQUIRED:
                    sys_["disclosure"].record_consent(uid, "t", dt, "1", "A")
            except Exception as e:
                errors.append(e)

        ts = [Thread(target=accept, args=(f"u{i}",)) for i in range(100)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == [] and sys_["audit"].verify_chain() is True

    def test_T203_version_update_flow(self):
        sys_ = build_compliance_system()
        sys_["admin"].publish_document(
            DocumentType.TOS,
            "2.0.0",
            "TOS v2",
            "Updated terms",
            time.time(),
            "admin",
            supersede_reason="Annual review",
        )
        assert sys_["doc_store"].active_for_type(DocumentType.TOS).version == "2.0.0"

    def test_T204_document_content_hash_consistent(self):
        sys_ = build_compliance_system()
        for doc in sys_["doc_store"].list_active():
            assert doc.content_hash == hashlib.sha256(doc.content.encode()).hexdigest()

    def test_T205_all_audit_actions_used(self):
        sys_ = build_compliance_system()
        engine = sys_["disclosure"]
        for dt in ACCEPTANCE_REQUIRED:
            engine.record_consent("u", "t", dt, "1", "A")
        req = sys_["refund"].request_refund("u", "t", 100, "USD", "r", time.time())
        sys_["refund"].evaluate(req.request_id, "admin")
        sys_["cancellation"].request_cancellation("u", "t", "r")
        sys_["saas_checker"].check()
        actions = {e.action for e in sys_["audit"]._entries}
        for a in [
            AuditAction.DOC_PUBLISHED,
            AuditAction.CONSENT_RECORDED,
            AuditAction.REFUND_ISSUED,
            AuditAction.CANCEL_REQUESTED,
            AuditAction.SAAS_CHECK,
        ]:
            assert a in actions

    def test_T206_sql_migration_tables(self):
        sql_path = os.path.join(
            os.path.dirname(__file__),
            "../../supabase/migrations/20260628_039_phase30_compliance.sql",
        )
        if not os.path.exists(sql_path):
            pytest.skip("SQL file not found")
        sql = open(sql_path).read()
        for t in ["legal_documents", "consent_records", "compliance_audit_log"]:
            assert t in sql

    def test_T207_sql_migration_rls(self):
        sql_path = os.path.join(
            os.path.dirname(__file__),
            "../../supabase/migrations/20260628_039_phase30_compliance.sql",
        )
        if not os.path.exists(sql_path):
            pytest.skip("SQL file not found")
        sql = open(sql_path).read()
        assert "ROW LEVEL SECURITY" in sql or "ENABLE ROW LEVEL SECURITY" in sql

    def test_T208_sql_migration_immutable_audit(self):
        sql_path = os.path.join(
            os.path.dirname(__file__),
            "../../supabase/migrations/20260628_039_phase30_compliance.sql",
        )
        if not os.path.exists(sql_path):
            pytest.skip("SQL file not found")
        sql = open(sql_path).read()
        assert "immutable" in sql.lower() or "IMMUTABLE" in sql or "BEFORE DELETE" in sql

    def test_T209_build_system_isolation(self):
        s1 = build_compliance_system(secret="s1")
        s2 = build_compliance_system(secret="s2")
        s1["audit"].record(AuditAction.DOC_PUBLISHED, actor="a")
        assert s1["audit"].last_hash != s2["audit"].last_hash

    def test_T210_legal_factory_default_params(self):
        f = LegalDocumentFactory()
        assert f.company == "ACME Trading Technologies Ltd"
        assert f.product == "Bot12 Trading Platform"
        assert f.email == "legal@bot12.io"

    def test_T211_disclosure_engine_grace_0_blocks_immediately(self):
        sys_ = build_compliance_system()
        engine = DisclosureEngine(
            sys_["doc_store"], sys_["consent_store"], sys_["audit"], grace_days=0
        )
        with pytest.raises(ConsentRequiredError):
            engine.check_access("new", "t", time.time() - 1)

    def test_T212_saas_readiness_is_production_ready(self):
        """Final acceptance test: product is ready for commercial sale."""
        sys_ = build_compliance_system(
            company_name="Bot12 Technologies Ltd",
            product_name="Bot12 Pro Trading Platform",
            support_email="legal@bot12.io",
            jurisdiction="England and Wales",
        )
        report = sys_["saas_checker"].check(actor="compliance_officer")
        assert report.missing_docs == []
        assert report.gaps == []
        assert report.score == 100
        assert report.passed is True
        assert sys_["audit"].verify_chain() is True
        assert len(sys_["doc_store"].list_active()) == 10
        for cat in [
            "user_pii",
            "trading_logs",
            "audit_logs",
            "financial_records",
            "payment_records",
        ]:
            assert sys_["retention"].get(cat) is not None
