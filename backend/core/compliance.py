"""
Phase 30 -- Compliance, Legal & User-Facing Disclosures
"""
from __future__ import annotations
import copy, hashlib, hmac, json, logging, os, time, uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Callable, Dict, List, Optional, Set, Tuple

_LOG = logging.getLogger(__name__)

class DocumentType(str, Enum):
    TOS           = "tos"
    PRIVACY       = "privacy"
    RISK          = "risk_disclaimer"
    LICENSE       = "license_terms"
    REFUND        = "refund_policy"
    RETENTION     = "retention_policy"
    CANCELLATION  = "cancellation_policy"
    DPA           = "data_processing_agreement"
    COOKIE        = "cookie_policy"
    AML           = "aml_kyc_policy"

class DocumentStatus(str, Enum):
    DRAFT      = "draft"
    ACTIVE     = "active"
    SUPERSEDED = "superseded"
    ARCHIVED   = "archived"

class ConsentStatus(str, Enum):
    PENDING    = "pending"
    ACCEPTED   = "accepted"
    DECLINED   = "declined"
    EXPIRED    = "expired"
    WITHDRAWN  = "withdrawn"

class JurisdictionCode(str, Enum):
    GLOBAL = "GLOBAL"
    EU     = "EU"
    UK     = "UK"
    US     = "US"
    UAE    = "UAE"
    AU     = "AU"

class AuditAction(str, Enum):
    DOC_PUBLISHED    = "doc.published"
    DOC_SUPERSEDED   = "doc.superseded"
    DOC_ARCHIVED     = "doc.archived"
    CONSENT_RECORDED = "consent.recorded"
    CONSENT_WITHDRAWN= "consent.withdrawn"
    CONSENT_EXPIRED  = "consent.expired"
    DISCLOSURE_GATE  = "disclosure.gate_checked"
    DISCLOSURE_BLOCK = "disclosure.blocked"
    RETENTION_SET    = "retention.policy_set"
    REFUND_ISSUED    = "refund.issued"
    REFUND_DENIED    = "refund.denied"
    CANCEL_REQUESTED = "cancellation.requested"
    CANCEL_CONFIRMED = "cancellation.confirmed"
    SAAS_CHECK       = "saas.readiness_check"
    COMPROMISE_RESP  = "compliance.compromise_response"

SAAS_REQUIRED_DOCS: Set[DocumentType] = {
    DocumentType.TOS, DocumentType.PRIVACY, DocumentType.RISK,
    DocumentType.LICENSE, DocumentType.REFUND, DocumentType.RETENTION,
    DocumentType.CANCELLATION, DocumentType.COOKIE,
}
ACCEPTANCE_REQUIRED: Set[DocumentType] = {
    DocumentType.TOS, DocumentType.PRIVACY,
    DocumentType.RISK, DocumentType.LICENSE,
}
REQUIRES_REASON: Set[AuditAction] = {
    AuditAction.DOC_SUPERSEDED, AuditAction.DOC_ARCHIVED,
    AuditAction.CONSENT_WITHDRAWN, AuditAction.REFUND_DENIED,
}
GENESIS_CONST = "GENESIS:COMPLIANCE:CHAIN:V30"

class ComplianceError(Exception): pass
class MissingReasonError(ComplianceError): pass
class DocumentNotFoundError(ComplianceError): pass
class ConsentRequiredError(ComplianceError): pass
class ConsentDeclinedError(ComplianceError): pass
class RefundDeniedError(ComplianceError): pass
class CancellationError(ComplianceError): pass

@dataclass
class DocumentVersion:
    doc_id: str
    doc_type: DocumentType
    version: str
    title: str
    content: str
    content_hash: str
    status: DocumentStatus
    effective_date: float
    jurisdiction: JurisdictionCode
    created_by: str
    created_at: float = field(default_factory=time.time)
    superseded_by: Optional[str] = None
    min_version_required: Optional[str] = None
    language: str = "en"
    def __repr__(self):
        return f"DocumentVersion(type={self.doc_type.value}, v={self.version}, status={self.status.value})"

@dataclass
class ConsentRecord:
    consent_id: str
    user_id: str
    tenant_id: str
    doc_id: str
    doc_type: DocumentType
    doc_version: str
    status: ConsentStatus
    ip_address: str
    user_agent: str
    accepted_at: float
    expires_at: Optional[float] = None
    withdrawn_at: Optional[float] = None
    reason: Optional[str] = None
    def is_valid(self) -> bool:
        if self.status != ConsentStatus.ACCEPTED:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

@dataclass
class RetentionRule:
    category: str
    retain_days: int
    legal_basis: str
    jurisdiction: JurisdictionCode
    auto_delete: bool = True
    description: str = ""

@dataclass
class RefundRequest:
    request_id: str
    user_id: str
    tenant_id: str
    amount_cents: int
    currency: str
    reason: str
    requested_at: float
    purchase_at: float
    status: str = "pending"
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    denial_reason: Optional[str] = None

@dataclass
class CancellationRequest:
    request_id: str
    user_id: str
    tenant_id: str
    reason: str
    requested_at: float
    effective_at: float
    notice_days: int
    status: str = "pending"
    confirmed_at: Optional[float] = None
    data_deletion: bool = False

@dataclass
class _AuditEntry:
    entry_id: str
    action: AuditAction
    actor: str
    tenant_id: str
    detail: dict
    reason: Optional[str]
    ts: float
    seq: int
    chain_hash: str = ""

class ComplianceAuditChain:
    def __init__(self, secret: Optional[str] = None) -> None:
        self._secret = (secret or os.urandom(32).hex()).encode()
        self._entries: deque = deque(maxlen=100_000)
        self._prev_hash = self._genesis()
        self._seq = 0
        self._lock = RLock()

    def _genesis(self) -> str:
        return hmac.new(self._secret, GENESIS_CONST.encode(), hashlib.sha256).hexdigest()

    def _hmac(self, data: str) -> str:
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()

    def record(self, action: AuditAction, actor: str, tenant_id: str = "system",
               reason: Optional[str] = None, **detail) -> _AuditEntry:
        if action in REQUIRES_REASON:
            if not reason or not reason.strip():
                raise MissingReasonError(f"reason required for action {action.value}")
        ts_now = time.time()
        with self._lock:
            self._seq += 1
            seq = self._seq
            entry_id = str(uuid.uuid4())
            canonical = json.dumps({"entry_id": entry_id, "action": action.value,
                "actor": actor, "tenant_id": tenant_id, "reason": reason,
                "detail": detail, "ts": ts_now, "seq": seq}, sort_keys=True)
            chain_hash = self._hmac(self._prev_hash + ":" + canonical)
            self._prev_hash = chain_hash
            entry = _AuditEntry(entry_id=entry_id, action=action, actor=actor,
                tenant_id=tenant_id, detail=detail, reason=reason,
                ts=ts_now, seq=seq, chain_hash=chain_hash)
            self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return True
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps({"entry_id": e.entry_id, "action": e.action.value,
                "actor": e.actor, "tenant_id": e.tenant_id, "reason": e.reason,
                "detail": e.detail, "ts": e.ts, "seq": e.seq}, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                return False
            prev = e.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            entries = list(self._entries)
        broken = []
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps({"entry_id": e.entry_id, "action": e.action.value,
                "actor": e.actor, "tenant_id": e.tenant_id, "reason": e.reason,
                "detail": e.detail, "ts": e.ts, "seq": e.seq}, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                broken.append(e.seq)
            prev = e.chain_hash
        return broken

    def query(self, action: Optional[AuditAction] = None,
              tenant_id: Optional[str] = None, limit: int = 50) -> List[_AuditEntry]:
        with self._lock:
            entries = list(self._entries)
        results = []
        for e in reversed(entries):
            if action and e.action != action:
                continue
            if tenant_id and e.tenant_id != tenant_id:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    @property
    def last_hash(self) -> str:
        with self._lock:
            return self._prev_hash

    def __len__(self) -> int:
        return len(self._entries)


class DocumentStore:
    def __init__(self) -> None:
        self._docs: Dict[str, DocumentVersion] = {}
        self._lock = RLock()

    def add(self, doc: DocumentVersion) -> None:
        with self._lock:
            self._docs[doc.doc_id] = doc

    def get(self, doc_id: str) -> DocumentVersion:
        with self._lock:
            d = self._docs.get(doc_id)
        if d is None:
            raise DocumentNotFoundError(doc_id)
        return d

    def active_for_type(self, doc_type: DocumentType,
                        jurisdiction: JurisdictionCode = JurisdictionCode.GLOBAL) -> Optional[DocumentVersion]:
        with self._lock:
            docs = list(self._docs.values())
        candidates = [d for d in docs if d.doc_type == doc_type
                      and d.status == DocumentStatus.ACTIVE
                      and d.jurisdiction in (jurisdiction, JurisdictionCode.GLOBAL)]
        if not candidates:
            return None
        return max(candidates, key=lambda d: d.effective_date)

    def list_active(self) -> List[DocumentVersion]:
        with self._lock:
            return [d for d in self._docs.values() if d.status == DocumentStatus.ACTIVE]

    def all_types_covered(self, required: Set[DocumentType]) -> Tuple[bool, List[DocumentType]]:
        active_types = {d.doc_type for d in self.list_active()}
        missing = [t for t in required if t not in active_types]
        return len(missing) == 0, missing

    def supersede(self, old_doc_id: str, new_doc_id: str, actor: str, reason: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for supersede")
        with self._lock:
            old = self._docs.get(old_doc_id)
            if old is None:
                raise DocumentNotFoundError(old_doc_id)
            old.status = DocumentStatus.SUPERSEDED
            old.superseded_by = new_doc_id

    def archive(self, doc_id: str, actor: str, reason: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for archive")
        with self._lock:
            doc = self._docs.get(doc_id)
            if doc is None:
                raise DocumentNotFoundError(doc_id)
            doc.status = DocumentStatus.ARCHIVED

    def count(self) -> int:
        with self._lock:
            return len(self._docs)


class ConsentStore:
    def __init__(self) -> None:
        self._records: Dict[str, ConsentRecord] = {}
        self._lock = RLock()

    def record(self, consent: ConsentRecord) -> None:
        with self._lock:
            self._records[consent.consent_id] = consent

    def get(self, consent_id: str) -> Optional[ConsentRecord]:
        with self._lock:
            return self._records.get(consent_id)

    def latest_for(self, user_id: str, doc_type: DocumentType,
                   tenant_id: Optional[str] = None) -> Optional[ConsentRecord]:
        with self._lock:
            records = list(self._records.values())
        candidates = [r for r in records if r.user_id == user_id
                      and r.doc_type == doc_type
                      and (tenant_id is None or r.tenant_id == tenant_id)]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.accepted_at)

    def user_has_accepted(self, user_id: str, doc_type: DocumentType,
                          tenant_id: Optional[str] = None) -> bool:
        r = self.latest_for(user_id, doc_type, tenant_id)
        return r is not None and r.is_valid()

    def withdraw(self, consent_id: str, reason: str, actor: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for consent withdrawal")
        with self._lock:
            r = self._records.get(consent_id)
            if r is None:
                raise ComplianceError(f"consent {consent_id} not found")
            r.status = ConsentStatus.WITHDRAWN
            r.withdrawn_at = time.time()
            r.reason = reason

    def pending_for_user(self, user_id: str, tenant_id: str,
                         required_types: Set[DocumentType],
                         doc_store: DocumentStore) -> List[DocumentType]:
        missing = []
        for doc_type in required_types:
            active = doc_store.active_for_type(doc_type)
            if active is None:
                continue
            if not self.user_has_accepted(user_id, doc_type, tenant_id):
                missing.append(doc_type)
        return missing

    def count(self) -> int:
        with self._lock:
            return len(self._records)


class DisclosureEngine:
    def __init__(self, doc_store: DocumentStore, consent_store: ConsentStore,
                 audit: ComplianceAuditChain, grace_days: int = 7) -> None:
        self._docs = doc_store
        self._consents = consent_store
        self._audit = audit
        self._grace_seconds = grace_days * 86400
        self._hooks: List[Callable] = []

    def add_hook(self, fn: Callable) -> None:
        self._hooks.append(fn)

    def check_access(self, user_id: str, tenant_id: str, user_created_at: float,
                     required: Set[DocumentType] = ACCEPTANCE_REQUIRED) -> Tuple[bool, List[DocumentType]]:
        missing = self._consents.pending_for_user(user_id, tenant_id, required, self._docs)
        if not missing:
            self._audit.record(AuditAction.DISCLOSURE_GATE, actor=user_id,
                               tenant_id=tenant_id, result="allowed")
            return True, []
        in_grace = (time.time() - user_created_at) < self._grace_seconds
        if in_grace:
            self._audit.record(AuditAction.DISCLOSURE_GATE, actor=user_id,
                               tenant_id=tenant_id, result="grace_period",
                               missing=[t.value for t in missing])
            return True, missing
        self._audit.record(AuditAction.DISCLOSURE_BLOCK, actor=user_id,
                           tenant_id=tenant_id, missing=[t.value for t in missing])
        for hook in self._hooks:
            try:
                hook(user_id, tenant_id, missing)
            except Exception as exc:
                _LOG.warning('compliance hook error: %s', exc)
        raise ConsentRequiredError(f"User {user_id} must accept: {[t.value for t in missing]}")

    def record_consent(self, user_id: str, tenant_id: str, doc_type: DocumentType,
                       ip_address: str, user_agent: str,
                       ttl_days: Optional[int] = None) -> ConsentRecord:
        active = self._docs.active_for_type(doc_type)
        if active is None:
            raise DocumentNotFoundError(f"No active document for type {doc_type.value}")
        now = time.time()
        consent = ConsentRecord(
            consent_id=str(uuid.uuid4()), user_id=user_id, tenant_id=tenant_id,
            doc_id=active.doc_id, doc_type=doc_type, doc_version=active.version,
            status=ConsentStatus.ACCEPTED, ip_address=ip_address, user_agent=user_agent,
            accepted_at=now, expires_at=now + ttl_days * 86400 if ttl_days else None)
        self._consents.record(consent)
        self._audit.record(AuditAction.CONSENT_RECORDED, actor=user_id,
                           tenant_id=tenant_id, doc_type=doc_type.value,
                           doc_version=active.version, ip_address=ip_address)
        return consent


DEFAULT_RETENTION_RULES: Dict[str, RetentionRule] = {
    "user_pii": RetentionRule("user_pii", 730, "GDPR Art.5", JurisdictionCode.EU, True,
        "Personal identifiable information retained for 2 years post-account closure"),
    "trading_logs": RetentionRule("trading_logs", 2555, "MiFID II", JurisdictionCode.EU, False,
        "Trade logs retained for 7 years per MiFID II"),
    "audit_logs": RetentionRule("audit_logs", 2555, "SOC2/ISO27001", JurisdictionCode.GLOBAL, False,
        "Security audit logs retained for 7 years"),
    "financial_records": RetentionRule("financial_records", 2555, "Companies Act", JurisdictionCode.UK, False,
        "Financial records retained for 7 years"),
    "support_tickets": RetentionRule("support_tickets", 1095, "Operational", JurisdictionCode.GLOBAL, True,
        "Support tickets retained for 3 years"),
    "marketing_consent": RetentionRule("marketing_consent", 1825, "GDPR Art.7", JurisdictionCode.EU, True,
        "Marketing consent records retained for 5 years"),
    "backup_data": RetentionRule("backup_data", 90, "Operational", JurisdictionCode.GLOBAL, True,
        "Backup snapshots retained for 90 days"),
    "session_data": RetentionRule("session_data", 30, "Security", JurisdictionCode.GLOBAL, True,
        "Session tokens and refresh records for 30 days"),
    "kyc_documents": RetentionRule("kyc_documents", 1825, "AML Directive", JurisdictionCode.EU, False,
        "KYC/AML documents retained 5 years post-relationship"),
    "payment_records": RetentionRule("payment_records", 2555, "PCI-DSS", JurisdictionCode.GLOBAL, False,
        "Payment transaction records for 7 years"),
}


class RetentionPolicyEngine:
    def __init__(self, rules: Optional[Dict[str, RetentionRule]] = None,
                 audit: Optional[ComplianceAuditChain] = None) -> None:
        self._rules: Dict[str, RetentionRule] = (
            copy.deepcopy(DEFAULT_RETENTION_RULES) if rules is None else copy.deepcopy(rules))
        self._audit = audit
        self._lock = RLock()

    def get(self, category: str) -> Optional[RetentionRule]:
        with self._lock:
            return self._rules.get(category)

    def set(self, rule: RetentionRule, actor: str, tenant_id: str = "system") -> None:
        with self._lock:
            self._rules[rule.category] = rule
        if self._audit is not None:
            self._audit.record(AuditAction.RETENTION_SET, actor=actor,
                               tenant_id=tenant_id, category=rule.category,
                               retain_days=rule.retain_days)

    def is_expired(self, category: str, created_at: float) -> bool:
        rule = self.get(category)
        if rule is None:
            return False
        return (time.time() - created_at) / 86400 > rule.retain_days

    def all_rules(self) -> Dict[str, RetentionRule]:
        with self._lock:
            return dict(self._rules)

    def categories(self) -> List[str]:
        with self._lock:
            return sorted(self._rules.keys())


@dataclass
class RefundPolicyConfig:
    window_days: int = 14
    max_amount_cents: int = 100_000
    currency: str = "USD"
    partial_allowed: bool = True
    require_reason: bool = True
    auto_approve_days: int = 7


class RefundPolicyEngine:
    def __init__(self, config: Optional[RefundPolicyConfig] = None,
                 audit: Optional[ComplianceAuditChain] = None) -> None:
        self._config = config or RefundPolicyConfig()
        self._requests: Dict[str, RefundRequest] = {}
        self._audit = audit
        self._lock = RLock()

    def request_refund(self, user_id: str, tenant_id: str, amount_cents: int,
                       currency: str, reason: str, purchase_at: float) -> RefundRequest:
        if self._config.require_reason and (not reason or not reason.strip()):
            raise MissingReasonError("reason required for refund request")
        req = RefundRequest(request_id=str(uuid.uuid4()), user_id=user_id,
            tenant_id=tenant_id, amount_cents=amount_cents, currency=currency,
            reason=reason, requested_at=time.time(), purchase_at=purchase_at)
        with self._lock:
            self._requests[req.request_id] = req
        return req

    def evaluate(self, request_id: str, actor: str) -> RefundRequest:
        with self._lock:
            req = self._requests.get(request_id)
        if req is None:
            raise ComplianceError(f"refund {request_id} not found")
        now = time.time()
        age_days = (now - req.purchase_at) / 86400
        if age_days > self._config.window_days:
            req.status = "denied"
            req.denial_reason = f"Outside refund window ({self._config.window_days} days)"
            req.resolved_at = now
            req.resolved_by = actor
            if self._audit is not None:
                self._audit.record(AuditAction.REFUND_DENIED, actor=actor,
                    tenant_id=req.tenant_id, request_id=request_id,
                    reason=req.denial_reason)
            raise RefundDeniedError(req.denial_reason)
        if req.amount_cents > self._config.max_amount_cents:
            req.status = "denied"
            req.denial_reason = "Amount exceeds maximum refund limit"
            req.resolved_at = now
            req.resolved_by = actor
            if self._audit is not None:
                self._audit.record(AuditAction.REFUND_DENIED, actor=actor,
                    tenant_id=req.tenant_id, request_id=request_id,
                    reason=req.denial_reason)
            raise RefundDeniedError(req.denial_reason)
        req.status = "approved"
        req.resolved_at = now
        req.resolved_by = actor
        if self._audit is not None:
            self._audit.record(AuditAction.REFUND_ISSUED, actor=actor,
                tenant_id=req.tenant_id, request_id=request_id,
                amount_cents=req.amount_cents)
        return req

    def get(self, request_id: str) -> Optional[RefundRequest]:
        with self._lock:
            return self._requests.get(request_id)

    def list_for_user(self, user_id: str) -> List[RefundRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.user_id == user_id]


@dataclass
class CancellationPolicyConfig:
    notice_days: int = 30
    immediate_allowed: bool = False
    data_deletion_days: int = 30
    allow_reactivation: bool = True
    pro_rata_refund: bool = True


class CancellationPolicyEngine:
    def __init__(self, config: Optional[CancellationPolicyConfig] = None,
                 audit: Optional[ComplianceAuditChain] = None) -> None:
        self._config = config or CancellationPolicyConfig()
        self._requests: Dict[str, CancellationRequest] = {}
        self._audit = audit
        self._lock = RLock()

    def request_cancellation(self, user_id: str, tenant_id: str, reason: str,
                              immediate: bool = False,
                              data_deletion: bool = False) -> CancellationRequest:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for cancellation")
        if immediate and not self._config.immediate_allowed:
            raise CancellationError(
                f"Immediate cancellation not allowed; notice period is {self._config.notice_days} days")
        now = time.time()
        notice_days = 0 if immediate else self._config.notice_days
        req = CancellationRequest(request_id=str(uuid.uuid4()), user_id=user_id,
            tenant_id=tenant_id, reason=reason, requested_at=now,
            effective_at=now + notice_days * 86400, notice_days=notice_days,
            data_deletion=data_deletion)
        with self._lock:
            self._requests[req.request_id] = req
        if self._audit is not None:
            self._audit.record(AuditAction.CANCEL_REQUESTED, actor=user_id,
                tenant_id=tenant_id, request_id=req.request_id, notice_days=notice_days)
        return req

    def confirm_cancellation(self, request_id: str, actor: str) -> CancellationRequest:
        with self._lock:
            req = self._requests.get(request_id)
        if req is None:
            raise CancellationError(f"cancellation {request_id} not found")
        if req.status == "confirmed":
            raise CancellationError("already confirmed")
        req.status = "confirmed"
        req.confirmed_at = time.time()
        if self._audit is not None:
            self._audit.record(AuditAction.CANCEL_CONFIRMED, actor=actor,
                tenant_id=req.tenant_id, request_id=request_id)
        return req

    def abort_cancellation(self, request_id: str) -> CancellationRequest:
        with self._lock:
            req = self._requests.get(request_id)
        if req is None:
            raise CancellationError(f"cancellation {request_id} not found")
        if req.status == "confirmed":
            raise CancellationError("cannot abort confirmed cancellation")
        req.status = "cancelled"
        return req

    def get(self, request_id: str) -> Optional[CancellationRequest]:
        with self._lock:
            return self._requests.get(request_id)


@dataclass
class SaaSReadinessReport:
    passed: bool
    score: int
    missing_docs: List[DocumentType]
    outdated_docs: List[DocumentType]
    gaps: List[str]
    recommendations: List[str]
    checked_at: float = field(default_factory=time.time)
    def to_dict(self) -> dict:
        return {"passed": self.passed, "score": self.score,
                "missing_docs": [d.value for d in self.missing_docs],
                "outdated_docs": [d.value for d in self.outdated_docs],
                "gaps": self.gaps, "recommendations": self.recommendations,
                "checked_at": self.checked_at}


class SaaSReadinessChecker:
    REQUIRED_RETENTION_CATEGORIES = {
        "user_pii", "trading_logs", "audit_logs", "financial_records", "payment_records",
    }

    def __init__(self, doc_store: DocumentStore, consent_store: ConsentStore,
                 retention: RetentionPolicyEngine, refund: RefundPolicyEngine,
                 cancellation: CancellationPolicyEngine, audit: ComplianceAuditChain) -> None:
        self._docs = doc_store
        self._consents = consent_store
        self._retention = retention
        self._refund = refund
        self._cancellation = cancellation
        self._audit = audit

    def check(self, actor: str = "system") -> SaaSReadinessReport:
        gaps: List[str] = []
        recommendations: List[str] = []
        score = 100
        ok, missing_docs = self._docs.all_types_covered(SAAS_REQUIRED_DOCS)
        if not ok:
            for d in missing_docs:
                gaps.append(f"Missing required document: {d.value}")
                score -= 10
        outdated_docs: List[DocumentType] = []
        for dt in ACCEPTANCE_REQUIRED:
            active = self._docs.active_for_type(dt)
            if active is None:
                outdated_docs.append(dt)
                gaps.append(f"No active version for acceptance-required doc: {dt.value}")
                score -= 8
        for cat in self.REQUIRED_RETENTION_CATEGORIES:
            if self._retention.get(cat) is None:
                gaps.append(f"Missing retention rule for category: {cat}")
                recommendations.append(f"Define retention policy for '{cat}'")
                score -= 5
        if self._refund._config.window_days < 1:
            gaps.append("Refund window must be >= 1 day")
            score -= 5
        if self._cancellation._config.notice_days < 0:
            gaps.append("Cancellation notice_days cannot be negative")
            score -= 5
        if not self._audit.verify_chain():
            gaps.append("Compliance audit chain TAMPERED -- integrity failure")
            score -= 20
        if len(self._audit) == 0:
            recommendations.append("No audit entries yet -- publish first doc to initiate chain")
        score = max(0, score)
        passed = score >= 80 and len(gaps) == 0
        report = SaaSReadinessReport(passed=passed, score=score, missing_docs=missing_docs,
            outdated_docs=outdated_docs, gaps=gaps, recommendations=recommendations)
        self._audit.record(AuditAction.SAAS_CHECK, actor=actor, tenant_id="system",
                           passed=passed, score=score, gaps=len(gaps))
        return report


class ComplianceAdmin:
    def __init__(self, doc_store: DocumentStore, consent_store: ConsentStore,
                 audit: ComplianceAuditChain) -> None:
        self._docs = doc_store
        self._consents = consent_store
        self._audit = audit

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def publish_document(self, doc_type: DocumentType, version: str, title: str,
                         content: str, effective_date: float, actor: str,
                         jurisdiction: JurisdictionCode = JurisdictionCode.GLOBAL,
                         language: str = "en",
                         supersede_reason: Optional[str] = None) -> DocumentVersion:
        doc_id = str(uuid.uuid4())
        doc = DocumentVersion(doc_id=doc_id, doc_type=doc_type, version=version,
            title=title, content=content, content_hash=self._content_hash(content),
            status=DocumentStatus.ACTIVE, effective_date=effective_date,
            jurisdiction=jurisdiction, created_by=actor, language=language)
        for old in self._docs.list_active():
            if old.doc_type == doc_type and old.doc_id != doc_id:
                reason = supersede_reason or f"Superseded by version {version}"
                self._docs.supersede(old.doc_id, doc_id, actor, reason)
                self._audit.record(AuditAction.DOC_SUPERSEDED, actor=actor,
                    tenant_id="system", old_doc_id=old.doc_id, new_doc_id=doc_id,
                    reason=reason)
        self._docs.add(doc)
        self._audit.record(AuditAction.DOC_PUBLISHED, actor=actor, tenant_id="system",
                           doc_id=doc_id, doc_type=doc_type.value, version=version)
        return doc

    def archive_document(self, doc_id: str, actor: str, reason: str) -> None:
        self._docs.archive(doc_id, actor, reason)
        self._audit.record(AuditAction.DOC_ARCHIVED, actor=actor, tenant_id="system",
                           doc_id=doc_id, reason=reason)

    def bulk_consent_check(self, user_ids: List[str], tenant_id: str,
                            required: Set[DocumentType] = ACCEPTANCE_REQUIRED) -> Dict[str, List[DocumentType]]:
        result = {}
        for uid in user_ids:
            missing = self._consents.pending_for_user(uid, tenant_id, required, self._docs)
            if missing:
                result[uid] = missing
        return result

    def audit_summary(self) -> dict:
        with self._audit._lock:
            entries = list(self._audit._entries)
        action_counts: Dict[str, int] = {}
        for e in entries:
            action_counts[e.action.value] = action_counts.get(e.action.value, 0) + 1
        return {"total_entries": len(entries), "action_counts": action_counts,
                "chain_valid": self._audit.verify_chain(),
                "last_hash": self._audit.last_hash[:16] + "...",
                "docs_active": len(self._docs.list_active()),
                "consents_total": self._consents.count()}


class LegalDocumentFactory:
    def __init__(self, company_name: str = "ACME Trading Technologies Ltd",
                 product_name: str = "Bot12 Trading Platform",
                 support_email: str = "legal@bot12.io",
                 jurisdiction: str = "England and Wales",
                 effective_date: str = "1 January 2026") -> None:
        self.company = company_name
        self.product = product_name
        self.email = support_email
        self.juris = jurisdiction
        self.eff_date = effective_date

    def generate(self, doc_type: DocumentType) -> Tuple[str, str]:
        generators = {
            DocumentType.TOS: self._tos, DocumentType.PRIVACY: self._privacy,
            DocumentType.RISK: self._risk, DocumentType.LICENSE: self._license,
            DocumentType.REFUND: self._refund, DocumentType.RETENTION: self._retention,
            DocumentType.CANCELLATION: self._cancellation, DocumentType.DPA: self._dpa,
            DocumentType.COOKIE: self._cookie, DocumentType.AML: self._aml,
        }
        return generators[doc_type]()

    def _tos(self):
        title = f"{self.product} -- Terms of Service"
        content = f"""TERMS OF SERVICE\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. ACCEPTANCE\nBy accessing {self.product} you agree to these Terms.\n2. SERVICE\n{self.product} provides automated trading infrastructure, EA deployment, license management, risk controls.\n3. ELIGIBILITY\nMust be 18+ and legally capable.\n4. TRADING DISCLAIMER\nTECHNOLOGY PLATFORM ONLY. NO INVESTMENT ADVICE. ALL TRADING DECISIONS ARE YOURS ALONE.\n5. LIMITATION OF LIABILITY\n{self.company.upper()} NOT LIABLE FOR INDIRECT, INCIDENTAL, CONSEQUENTIAL DAMAGES.\nAGGREGATE LIABILITY CAPPED AT FEES PAID IN PRIOR 12 MONTHS.\n6. GOVERNING LAW\nGoverned by {self.juris}. Disputes resolved by courts of {self.juris}.\n7. CONTACT\n{self.email}\n"""
        return title, content

    def _privacy(self):
        title = f"{self.product} -- Privacy Policy"
        content = f"""PRIVACY POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. CONTROLLER\n{self.company} is the data controller. Contact: {self.email}\n2. DATA WE COLLECT\nAccount Data, Trading Data, Technical Data, Financial Data, KYC Data, Usage Data.\n3. LEGAL BASIS (GDPR)\nContract performance, legitimate interests, legal obligation, consent.\n4. YOUR RIGHTS (GDPR/UK GDPR)\nAccess, rectification, erasure (right to be forgotten), restriction, portability, objection.\nEmail {self.email} to exercise rights. Response within 30 days.\n5. SECURITY\nAES-256 encryption at rest, TLS 1.3 in transit, HMAC audit chains, RBAC.\n6. CONTACT\n{self.email}\n"""
        return title, content

    def _risk(self):
        title = f"{self.product} -- Risk Disclaimer"
        content = f"""RISK DISCLAIMER\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. HIGH-RISK ACTIVITY\nAutomated trading carries HIGH RISK OF LOSS. You may lose all invested capital.\n2. NO INVESTMENT ADVICE\n{self.product} is a TECHNOLOGY PLATFORM ONLY. Nothing constitutes investment advice.\n3. PAST PERFORMANCE\nPast performance is NOT indicative of future results.\n4. AUTOMATED TRADING RISKS\nSoftware bugs, connectivity failures, and parameter misconfiguration may amplify losses.\n5. REGULATORY STATUS\n{self.company} is a SOFTWARE PROVIDER, not a regulated investment firm.\n6. ACKNOWLEDGEMENT\nBy using {self.product} trading features you accept this Risk Disclaimer in full.\nContact: {self.email}\n"""
        return title, content

    def _license(self):
        title = f"{self.product} -- Software License Terms"
        content = f"""SOFTWARE LICENSE TERMS\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. LICENSE GRANT\nLimited, non-exclusive, non-transferable, revocable license to use the Service.\n2. LICENSE TYPES\nTRIAL: 14-day evaluation. BASIC: 1 live account. PRO: up to 5 accounts. VIP: unlimited. ENTERPRISE: custom.\n3. DEVICE BINDING\nEA licenses are bound to specific device IDs. Keys must not be shared.\n4. RESTRICTIONS\nNo copying, reverse-engineering, sublicensing, or exceeding device limits.\n5. WARRANTY DISCLAIMER\nSOFTWARE PROVIDED AS IS WITHOUT WARRANTY. NO FITNESS FOR PARTICULAR PURPOSE.\n6. CONTACT\n{self.email}\n"""
        return title, content

    def _refund(self):
        title = f"{self.product} -- Refund Policy"
        content = f"""REFUND POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. SUBSCRIPTION REFUNDS\nFull refund within 14 days if Service does not function as described.\n2. NON-REFUNDABLE\nUsage-based charges, setup fees, subscriptions cancelled after 14-day window.\n3. REFUND PROCESS\nSubmit to {self.email}. Response in 5 business days. Payment in 10 business days.\n4. CONTACT\n{self.email}\n"""
        return title, content

    def _retention(self):
        title = f"{self.product} -- Data Retention Policy"
        content = f"""DATA RETENTION POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. RETENTION SCHEDULE\nUser PII: 2 years. Trading Logs: 7 years (MiFID II). Financial Records: 7 years.\nAudit Logs: 7 years (SOC2). KYC Docs: 5 years (AML). Payment Records: 7 years (PCI-DSS).\nSession Data: 30 days. Backup Snapshots: 90 days.\n2. DELETION\nSecure deletion per NIST 800-88 at end of retention period.\n3. LEGAL HOLDS\nData may be retained beyond standard period if required by law.\n4. CONTACT\n{self.email}\n"""
        return title, content

    def _cancellation(self):
        title = f"{self.product} -- Cancellation Policy"
        content = f"""CANCELLATION POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. HOW TO CANCEL\nCancel via Account Settings or email {self.email}.\n2. NOTICE PERIOD\nCancellations require 30 days notice. Service active during notice period.\n3. EFFECTIVE DATE\nCancellation effective at end of billing period or 30 days from request.\n4. DATA EXPORT\nData export available within 30 days of effective date.\n5. EU/UK COOLING-OFF\nEU/UK consumers have 14-day cooling-off period from subscription date.\n6. CONTACT\n{self.email}\n"""
        return title, content

    def _dpa(self):
        title = f"{self.product} -- Data Processing Agreement"
        content = f"""DATA PROCESSING AGREEMENT\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. PROCESSOR OBLIGATIONS\nProcess data only on Controller instructions. Implement Art.32 GDPR security.\nAssist with data subject rights. Delete/return data on termination.\n2. SUB-PROCESSORS\nAWS, Stripe, SendGrid, Sentry. 30 days notice for new sub-processors.\n3. DATA BREACH\nNotify within 72 hours of becoming aware, per Art.33 GDPR.\n4. INTERNATIONAL TRANSFERS\nConducted under Standard Contractual Clauses (SCCs).\n5. CONTACT\n{self.email}\n"""
        return title, content

    def _cookie(self):
        title = f"{self.product} -- Cookie Policy"
        content = f"""COOKIE POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. COOKIES WE USE\nsession_id: Authentication (Session). csrf_token: Security (Session).\nconsent_status: Consent record (1 year). ui_preferences: Layout (1 year).\n_ga (Google): Analytics (2 years). amplitude_id: Features (1 year).\n_fbp (Meta): Retargeting (90 days).\n2. STRICTLY NECESSARY\nsession_id and csrf_token cannot be disabled.\n3. YOUR CHOICES\nManage via consent banner or browser settings.\n4. CONTACT\n{self.email}\n"""
        return title, content

    def _aml(self):
        title = f"{self.product} -- AML/KYC Policy"
        content = f"""AML/KYC POLICY\n{self.product} -- {self.company}\nEffective: {self.eff_date}\n\n1. COMMITMENT\nCompliance with UK POCA 2002, EU AML Directives, and FATF Recommendations.\n2. CDD\nStandard: name, email, country, DOB. Enhanced (EDD): ID + proof of address for high-risk or >EUR 15,000.\n3. HIGH-RISK INDICATORS\nPEPs, FATF grey/black list jurisdictions, unusual transaction patterns.\n4. PROHIBITED\nSanctioned persons (OFAC, EU, UN, HMT lists) and embargoed countries not permitted.\n5. RECORD KEEPING\nKYC records retained 5 years post-relationship per EU AML Directive and UK MLR 2017.\n6. CONTACT\n{self.email}\n"""
        return title, content


def build_compliance_system(
    secret: Optional[str] = None,
    company_name: str = "ACME Trading Technologies Ltd",
    product_name: str = "Bot12 Trading Platform",
    support_email: str = "legal@bot12.io",
    jurisdiction: str = "England and Wales",
    effective_date: str = "1 January 2026",
    refund_config: Optional[RefundPolicyConfig] = None,
    cancellation_config: Optional[CancellationPolicyConfig] = None,
) -> dict:
    audit = ComplianceAuditChain(secret=secret)
    doc_store = DocumentStore()
    consent_store = ConsentStore()
    retention = RetentionPolicyEngine(audit=audit)
    refund = RefundPolicyEngine(config=refund_config, audit=audit)
    cancellation = CancellationPolicyEngine(config=cancellation_config, audit=audit)
    disclosure = DisclosureEngine(doc_store, consent_store, audit)
    admin = ComplianceAdmin(doc_store, consent_store, audit)
    saas_checker = SaaSReadinessChecker(
        doc_store, consent_store, retention, refund, cancellation, audit)
    factory = LegalDocumentFactory(
        company_name=company_name, product_name=product_name,
        support_email=support_email, jurisdiction=jurisdiction,
        effective_date=effective_date)
    now = time.time()
    for doc_type in DocumentType:
        title, content = factory.generate(doc_type)
        admin.publish_document(doc_type=doc_type, version="1.0.0", title=title,
            content=content, effective_date=now, actor="system")
    return {"audit": audit, "doc_store": doc_store, "consent_store": consent_store,
            "retention": retention, "refund": refund, "cancellation": cancellation,
            "disclosure": disclosure, "admin": admin, "saas_checker": saas_checker,
            "factory": factory}
