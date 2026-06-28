"""
artifact_governance.py -- Phase 25: Release Artifact Governance
Artifact lifecycle: draft -> signed -> published -> deprecated -> revoked
Checksum, compatibility, access control, audit chain.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

_DEFAULT_SECRET = b"p25-artifact-hmac-secret-v25"


# == Enums ================================================================


class ArtifactStatus(str, Enum):
    DRAFT       = "draft"
    SIGNED      = "signed"
    PUBLISHED   = "published"
    DEPRECATED  = "deprecated"
    REVOKED     = "revoked"

    def __str__(self): return self.value


class ArtifactType(str, Enum):
    EA_BINARY   = "ea_binary"
    EA_SOURCE   = "ea_source"
    CONFIG      = "config"
    LICENSE_PKG = "license_pkg"
    MIGRATION   = "migration"
    DOCKER_IMG  = "docker_img"
    INSTALLER   = "installer"

    def __str__(self): return self.value


class ArtifactPlatform(str, Enum):
    MT5          = "mt5"
    MT4          = "mt4"
    WINDOWS_X64  = "windows_x64"
    DOCKER       = "docker"
    ANY          = "any"

    def __str__(self): return self.value


class CompatibilityStatus(str, Enum):
    COMPATIBLE   = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN      = "unknown"

    def __str__(self): return self.value


class ArtifactAction(str, Enum):
    CREATED     = "created"
    SIGNED      = "signed"
    PUBLISHED   = "published"
    DEPRECATED  = "deprecated"
    REVOKED     = "revoked"
    DOWNLOADED  = "downloaded"
    VERIFIED    = "verified"
    REJECTED    = "rejected"

    def __str__(self): return self.value


# == Constants =============================================================

BLOCKED_STATUSES = {
    ArtifactStatus.DRAFT,
    ArtifactStatus.REVOKED,
}

VALID_TRANSITIONS: Dict[ArtifactStatus, List[ArtifactStatus]] = {
    ArtifactStatus.DRAFT:       [ArtifactStatus.SIGNED, ArtifactStatus.REVOKED],
    ArtifactStatus.SIGNED:      [ArtifactStatus.PUBLISHED, ArtifactStatus.REVOKED],
    ArtifactStatus.PUBLISHED:   [ArtifactStatus.DEPRECATED, ArtifactStatus.REVOKED],
    ArtifactStatus.DEPRECATED:  [ArtifactStatus.REVOKED],
    ArtifactStatus.REVOKED:     [],
}

REQUIRES_REASON = {
    ArtifactAction.REVOKED,
    ArtifactAction.DEPRECATED,
    ArtifactAction.REJECTED,
}


# == Exceptions ============================================================

class ArtifactError(Exception): pass
class ArtifactNotFoundError(ArtifactError): pass
class ArtifactAccessDeniedError(ArtifactError): pass
class ArtifactTransitionError(ArtifactError): pass
class ArtifactChecksumError(ArtifactError): pass
class ArtifactCompatibilityError(ArtifactError): pass
class MissingReasonError(ArtifactError): pass


# == Helpers ===============================================================

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha512_bytes(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()

def verify_checksum(data: bytes, expected_hex: str) -> bool:
    actual = sha256_bytes(data)
    return hmac.compare_digest(actual, expected_hex)


# == Compatibility =========================================================

@dataclass
class CompatibilityRule:
    artifact_type: ArtifactType
    platform: ArtifactPlatform
    min_version: Optional[str] = None
    max_version: Optional[str] = None

    def _parse_version(self, v: str) -> tuple:
        try:
            return tuple(int(x) for x in v.split("."))
        except Exception:
            return (0,)

    def matches(self, artifact_type: ArtifactType, platform: ArtifactPlatform,
                version: Optional[str] = None) -> CompatibilityStatus:
        if self.artifact_type != artifact_type:
            return CompatibilityStatus.UNKNOWN
        if self.platform != ArtifactPlatform.ANY and self.platform != platform:
            return CompatibilityStatus.INCOMPATIBLE
        if version:
            ver = self._parse_version(version)
            if self.min_version and ver < self._parse_version(self.min_version):
                return CompatibilityStatus.INCOMPATIBLE
            if self.max_version and ver > self._parse_version(self.max_version):
                return CompatibilityStatus.INCOMPATIBLE
        return CompatibilityStatus.COMPATIBLE


DEFAULT_COMPATIBILITY_RULES: List[CompatibilityRule] = [
    CompatibilityRule(ArtifactType.EA_BINARY, ArtifactPlatform.MT5),
    CompatibilityRule(ArtifactType.EA_BINARY, ArtifactPlatform.MT4, min_version="1.0.0", max_version="2.9.9"),
    CompatibilityRule(ArtifactType.EA_SOURCE, ArtifactPlatform.MT5),
    CompatibilityRule(ArtifactType.CONFIG, ArtifactPlatform.ANY),
    CompatibilityRule(ArtifactType.LICENSE_PKG, ArtifactPlatform.ANY),
    CompatibilityRule(ArtifactType.MIGRATION, ArtifactPlatform.ANY),
    CompatibilityRule(ArtifactType.DOCKER_IMG, ArtifactPlatform.DOCKER),
    CompatibilityRule(ArtifactType.INSTALLER, ArtifactPlatform.WINDOWS_X64),
]


class CompatibilityChecker:
    def __init__(self, rules: Optional[List[CompatibilityRule]] = None):
        self._rules: List[CompatibilityRule] = list(rules or DEFAULT_COMPATIBILITY_RULES)
        self._lock = threading.RLock()

    def add_rule(self, rule: CompatibilityRule) -> None:
        with self._lock:
            self._rules.append(rule)

    def check(self, artifact_type: ArtifactType, platform: ArtifactPlatform,
              version: Optional[str] = None) -> CompatibilityStatus:
        with self._lock:
            for rule in self._rules:
                status = rule.matches(artifact_type, platform, version)
                if status != CompatibilityStatus.UNKNOWN:
                    return status
            return CompatibilityStatus.UNKNOWN

    def supported_platforms(self, artifact_type: ArtifactType) -> List[ArtifactPlatform]:
        with self._lock:
            seen = set()
            result = []
            for rule in self._rules:
                if rule.artifact_type == artifact_type:
                    p = rule.platform
                    if p not in seen:
                        seen.add(p)
                        result.append(p)
            return result


# == Data Models ===========================================================

@dataclass
class ArtifactRecord:
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    artifact_type: ArtifactType = ArtifactType.EA_BINARY
    platform: ArtifactPlatform = ArtifactPlatform.MT5
    status: ArtifactStatus = ArtifactStatus.DRAFT
    sha256: str = ""
    sha512: str = ""
    size_bytes: int = 0
    created_at: float = field(default_factory=time.time)
    created_by: str = ""
    tenant_id: str = ""
    signature: str = ""
    download_count: int = 0
    revoke_reason: Optional[str] = None

    def is_downloadable(self) -> bool:
        return self.status not in BLOCKED_STATUSES


@dataclass
class ArtifactAuditRecord:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    artifact_id: str = ""
    action: ArtifactAction = ArtifactAction.CREATED
    actor: str = ""
    tenant_id: str = ""
    reason: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    seq: int = 0
    chain_hash: str = ""
    prev_hash: str = ""


# == Audit Chain ===========================================================

class ArtifactAuditChain:
    _GENESIS_CONST = b"GENESIS:ARTIFACT:CHAIN:V25"
    MAX_RECORDS = 50_000

    def __init__(self, secret: bytes = _DEFAULT_SECRET):
        if isinstance(secret, str):
            secret = secret.encode()
        self._secret = secret
        self._records: deque = deque(maxlen=self.MAX_RECORDS)
        self._lock = threading.RLock()
        self._seq = 0
        self._genesis = self._hmac(self._GENESIS_CONST)
        self._prev_hash = self._genesis

    def _hmac(self, msg: bytes) -> str:
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def _canonical(self, r: ArtifactAuditRecord) -> bytes:
        payload = json.dumps({
            "entry_id": r.entry_id,
            "artifact_id": r.artifact_id,
            "action": str(r.action),
            "actor": r.actor,
            "tenant_id": r.tenant_id,
            "reason": r.reason,
            "detail": json.dumps(r.detail, sort_keys=True),
            "ts": f"{r.ts:.6f}",
        }, sort_keys=True)
        return payload.encode()

    def record(self, artifact_id: str, action: ArtifactAction, actor: str,
               reason: str = "", tenant_id: str = "",
               detail: Optional[Dict] = None) -> ArtifactAuditRecord:
        if action in REQUIRES_REASON and not reason.strip():
            raise MissingReasonError(f"{action} requires reason")
        with self._lock:
            self._seq += 1
            r = ArtifactAuditRecord(
                artifact_id=artifact_id,
                action=action,
                actor=actor,
                tenant_id=tenant_id,
                reason=reason,
                detail=detail or {},
                seq=self._seq,
                prev_hash=self._prev_hash,
            )
            msg = (self._prev_hash + ":" + self._canonical(r).decode()).encode()
            r.chain_hash = self._hmac(msg)
            self._prev_hash = r.chain_hash
            self._records.append(r)
            return r

    def verify_chain(self) -> bool:
        with self._lock:
            recs = list(self._records)
        if not recs:
            return True
        prev = self._genesis
        for r in recs:
            msg = (prev + ":" + self._canonical(r).decode()).encode()
            expected = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, r.chain_hash):
                return False
            prev = r.chain_hash
        return True

    def verify_entry(self, r: ArtifactAuditRecord) -> bool:
        msg = (r.prev_hash + ":" + self._canonical(r).decode()).encode()
        expected = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, r.chain_hash)

    def detect_tampered(self) -> List[int]:
        with self._lock:
            recs = list(self._records)
        broken = []
        prev = self._genesis
        for r in recs:
            msg = (prev + ":" + self._canonical(r).decode()).encode()
            expected = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, r.chain_hash):
                broken.append(r.seq)
            else:
                prev = r.chain_hash
        return broken

    def query(self, artifact_id: Optional[str] = None,
              actor: Optional[str] = None,
              action: Optional[ArtifactAction] = None,
              tenant_id: Optional[str] = None,
              limit: int = 100) -> List[ArtifactAuditRecord]:
        with self._lock:
            recs = list(self._records)
        result = []
        for r in reversed(recs):
            if artifact_id and r.artifact_id != artifact_id:
                continue
            if actor and r.actor != actor:
                continue
            if action and r.action != action:
                continue
            if tenant_id and r.tenant_id != tenant_id:
                continue
            result.append(r)
            if len(result) >= limit:
                break
        return result

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            recs = list(self._records)
        return {
            "total": len(recs),
            "genesis_hash": self._genesis,
            "last_hash": self._prev_hash,
            "seq_max": recs[-1].seq if recs else 0,
        }


# == Signer ================================================================

class ArtifactSigner:
    def __init__(self, secret: bytes = _DEFAULT_SECRET):
        if isinstance(secret, str):
            secret = secret.encode()
        self._secret = secret

    def _canonical(self, r: ArtifactRecord) -> str:
        return json.dumps({
            "artifact_id": r.artifact_id,
            "name": r.name,
            "version": r.version,
            "type": str(r.artifact_type),
            "platform": str(r.platform),
            "sha256": r.sha256,
            "size_bytes": r.size_bytes,
            "created_at": f"{r.created_at:.6f}",
            "created_by": r.created_by,
            "tenant_id": r.tenant_id,
        }, sort_keys=True)

    def sign(self, r: ArtifactRecord) -> str:
        msg = self._canonical(r).encode()
        sig = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        r.signature = sig
        return sig

    def verify_signature(self, r: ArtifactRecord) -> bool:
        msg = self._canonical(r).encode()
        expected = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        if not r.signature:
            return False
        return hmac.compare_digest(expected, r.signature)


# == Store =================================================================

class ArtifactStore:
    def __init__(self):
        self._store: Dict[str, ArtifactRecord] = {}
        self._lock = threading.RLock()

    def create(self, data: bytes, name: str, version: str,
               artifact_type: ArtifactType, platform: ArtifactPlatform,
               created_by: str = "", tenant_id: str = "") -> ArtifactRecord:
        r = ArtifactRecord(
            name=name,
            version=version,
            artifact_type=artifact_type,
            platform=platform,
            sha256=sha256_bytes(data),
            sha512=sha512_bytes(data),
            size_bytes=len(data),
            created_by=created_by,
            tenant_id=tenant_id,
        )
        with self._lock:
            self._store[r.artifact_id] = r
        return r

    def get(self, artifact_id: str) -> ArtifactRecord:
        with self._lock:
            r = self._store.get(artifact_id)
        if r is None:
            raise ArtifactNotFoundError(artifact_id)
        return r

    def transition(self, artifact_id: str, new_status: ArtifactStatus,
                   reason: str = "") -> ArtifactRecord:
        r = self.get(artifact_id)
        allowed = VALID_TRANSITIONS.get(r.status, [])
        if new_status not in allowed:
            raise ArtifactTransitionError(
                f"{r.status} -> {new_status} not allowed"
            )
        action = ArtifactAction(new_status.value)
        if action in REQUIRES_REASON and not reason.strip():
            raise MissingReasonError(f"{new_status} requires reason")
        with self._lock:
            r.status = new_status
            if new_status == ArtifactStatus.REVOKED:
                r.revoke_reason = reason
        return r

    def list_all(self, tenant_id: Optional[str] = None,
                 status: Optional[ArtifactStatus] = None,
                 artifact_type: Optional[ArtifactType] = None) -> List[ArtifactRecord]:
        with self._lock:
            recs = list(self._store.values())
        result = []
        for r in sorted(recs, key=lambda x: x.created_at):
            if tenant_id and r.tenant_id != tenant_id:
                continue
            if status and r.status != status:
                continue
            if artifact_type and r.artifact_type != artifact_type:
                continue
            result.append(r)
        return result


# == Governance (facade) ===================================================

class ArtifactGovernance:
    def __init__(self, secret: bytes = _DEFAULT_SECRET,
                 compat_rules: Optional[List[CompatibilityRule]] = None):
        if isinstance(secret, str):
            secret = secret.encode()
        self._secret = secret
        self._store = ArtifactStore()
        self._audit = ArtifactAuditChain(secret=secret)
        self._signer = ArtifactSigner(secret=secret)
        self._compat = CompatibilityChecker(rules=compat_rules)

    # -- lifecycle --

    def create_artifact(self, data: bytes, name: str, version: str,
                        artifact_type: ArtifactType, platform: ArtifactPlatform,
                        created_by: str = "", tenant_id: str = "") -> ArtifactRecord:
        r = self._store.create(data, name, version, artifact_type, platform,
                               created_by, tenant_id)
        self._audit.record(r.artifact_id, ArtifactAction.CREATED,
                           actor=created_by, tenant_id=tenant_id)
        return r

    def sign_artifact(self, artifact_id: str, actor: str = "") -> ArtifactRecord:
        r = self._store.get(artifact_id)
        if r.status != ArtifactStatus.DRAFT:
            raise ArtifactTransitionError("Can only sign DRAFT artifacts")
        self._signer.sign(r)
        self._store.transition(artifact_id, ArtifactStatus.SIGNED)
        self._audit.record(r.artifact_id, ArtifactAction.SIGNED,
                           actor=actor, tenant_id=r.tenant_id)
        return r

    def publish_artifact(self, artifact_id: str, actor: str = "") -> ArtifactRecord:
        r = self._store.get(artifact_id)
        if not self._signer.verify_signature(r):
            raise ArtifactTransitionError("Signature verification failed")
        self._store.transition(artifact_id, ArtifactStatus.PUBLISHED)
        self._audit.record(r.artifact_id, ArtifactAction.PUBLISHED,
                           actor=actor, tenant_id=r.tenant_id)
        return r

    def deprecate_artifact(self, artifact_id: str, reason: str,
                           actor: str = "") -> ArtifactRecord:
        if not reason or not reason.strip():
            raise MissingReasonError("deprecate requires reason")
        r = self._store.transition(artifact_id, ArtifactStatus.DEPRECATED, reason)
        self._audit.record(r.artifact_id, ArtifactAction.DEPRECATED,
                           actor=actor, reason=reason, tenant_id=r.tenant_id)
        return r

    def revoke_artifact(self, artifact_id: str, reason: str,
                        actor: str = "") -> ArtifactRecord:
        if not reason or not reason.strip():
            raise MissingReasonError("revoke requires reason")
        r = self._store.transition(artifact_id, ArtifactStatus.REVOKED, reason)
        self._audit.record(r.artifact_id, ArtifactAction.REVOKED,
                           actor=actor, reason=reason, tenant_id=r.tenant_id)
        return r

    # -- download control --

    def download_artifact(self, artifact_id: str, data: Optional[bytes] = None,
                          actor: str = "") -> ArtifactRecord:
        r = self._store.get(artifact_id)
        if not r.is_downloadable():
            self._audit.record(r.artifact_id, ArtifactAction.REJECTED,
                               actor=actor, tenant_id=r.tenant_id,
                               reason=f"blocked status: {r.status}")
            raise ArtifactAccessDeniedError(
                f"Artifact {artifact_id} is {r.status} - download denied"
            )
        if data is not None:
            if not verify_checksum(data, r.sha256):
                raise ArtifactChecksumError("Checksum mismatch")
        with self._store._lock:
            r.download_count += 1
        self._audit.record(r.artifact_id, ArtifactAction.DOWNLOADED,
                           actor=actor, tenant_id=r.tenant_id)
        return r

    # -- compatibility --

    def check_compatibility(self, artifact_id: str,
                            platform: ArtifactPlatform,
                            version: Optional[str] = None) -> CompatibilityStatus:
        r = self._store.get(artifact_id)
        return self._compat.check(r.artifact_type, platform, version)

    # -- audit --

    def verify_audit_chain(self) -> bool:
        return self._audit.verify_chain()

    def audit_trail(self, artifact_id: str) -> List[ArtifactAuditRecord]:
        return self._audit.query(artifact_id=artifact_id)

    def audit_summary(self) -> Dict[str, Any]:
        return self._audit.summary()

    # -- list --

    def list_artifacts(self, **kwargs) -> List[ArtifactRecord]:
        return self._store.list_all(**kwargs)


# == Admin Operations ======================================================

class AdminArtifactOps:
    def __init__(self, governance: ArtifactGovernance):
        self._gov = governance

    def bulk_revoke(self, artifact_ids: List[str], reason: str,
                   actor: str = "") -> Dict[str, bool]:
        if not reason or not reason.strip():
            raise MissingReasonError("bulk_revoke requires reason")
        results = {}
        for aid in artifact_ids:
            try:
                r = self._gov._store.get(aid)
                if r.status == ArtifactStatus.REVOKED:
                    results[aid] = False
                    continue
                self._gov.revoke_artifact(aid, reason=reason, actor=actor)
                results[aid] = True
            except Exception:
                results[aid] = False
        return results

    def revoke_by_type(self, artifact_type: ArtifactType, reason: str,
                       actor: str = "") -> int:
        if not reason or not reason.strip():
            raise MissingReasonError("revoke_by_type requires reason")
        recs = self._gov.list_artifacts(artifact_type=artifact_type)
        count = 0
        for r in recs:
            if r.status != ArtifactStatus.REVOKED:
                try:
                    self._gov.revoke_artifact(r.artifact_id, reason=reason, actor=actor)
                    count += 1
                except Exception:
                    pass
        return count

    def published_count(self) -> int:
        return len(self._gov.list_artifacts(status=ArtifactStatus.PUBLISHED))


# == SQL Migration =========================================================

MIGRATION_SQL = """
BEGIN;

CREATE TABLE IF NOT EXISTS artifact_records (
    artifact_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    platform      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft'
                  CONSTRAINT status_valid CHECK (status IN
                  ('draft','signed','published','deprecated','revoked')),
    sha256        CHAR(64) NOT NULL,
    sha512        CHAR(128) NOT NULL,
    size_bytes    BIGINT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    TEXT NOT NULL DEFAULT '',
    tenant_id     UUID NOT NULL,
    signature     CHAR(64) NOT NULL DEFAULT '',
    download_count INT NOT NULL DEFAULT 0,
    revoke_reason TEXT
);

CREATE TABLE IF NOT EXISTS artifact_audit_log (
    entry_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifact_records(artifact_id),
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT '',
    tenant_id   UUID NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    detail      JSONB NOT NULL DEFAULT '{}',
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq         BIGINT NOT NULL,
    chain_hash  CHAR(64) NOT NULL,
    prev_hash   CHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_compatibility_rules (
    rule_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_type TEXT NOT NULL,
    platform      TEXT NOT NULL,
    min_version   TEXT,
    max_version   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifact_download_tokens (
    token_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifact_records(artifact_id),
    tenant_id   UUID NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE artifact_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_compatibility_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_download_tokens ENABLE ROW LEVEL SECURITY;

-- Immutable audit log trigger
CREATE OR REPLACE FUNCTION prevent_artifact_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'artifact_audit_log is immutable';
END;
$$;

CREATE TRIGGER artifact_audit_immutable
BEFORE UPDATE OR DELETE ON artifact_audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_artifact_audit_mutation();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_artifacts_tenant_status
    ON artifact_records(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_artifacts_type_status
    ON artifact_records(artifact_type, status);
CREATE INDEX IF NOT EXISTS idx_audit_artifact_id
    ON artifact_audit_log(artifact_id);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts
    ON artifact_audit_log(tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_seq
    ON artifact_audit_log(seq);

-- Cleanup function
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM artifact_download_tokens
    WHERE expires_at < now() AND used = FALSE;
END;
$$;

-- View
CREATE OR REPLACE VIEW vw_downloadable_artifacts AS
SELECT * FROM artifact_records
WHERE status IN ('signed', 'published', 'deprecated');

COMMIT;
"""


__all__ = [
    # Enums
    "ArtifactStatus", "ArtifactType", "ArtifactPlatform",
    "CompatibilityStatus", "ArtifactAction",
    # Exceptions
    "ArtifactError", "ArtifactNotFoundError", "ArtifactAccessDeniedError",
    "ArtifactTransitionError", "ArtifactChecksumError",
    "ArtifactCompatibilityError", "MissingReasonError",
    # Models
    "ArtifactRecord", "ArtifactAuditRecord",
    # Core classes
    "ArtifactAuditChain", "ArtifactSigner", "ArtifactStore",
    "ArtifactGovernance", "CompatibilityChecker", "CompatibilityRule",
    "AdminArtifactOps",
    # Constants
    "VALID_TRANSITIONS", "BLOCKED_STATUSES", "REQUIRES_REASON",
    "DEFAULT_COMPATIBILITY_RULES", "MIGRATION_SQL",
    # Helpers
    "sha256_bytes", "sha512_bytes", "verify_checksum",
]
