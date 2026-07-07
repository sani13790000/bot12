"""
backend/core/secret_rotation.py
Galaxy Vast AI -- Phase 29: Secure Secrets Rotation & Key Lifecycle

P29-1: rotation policy for JWT/encryption/signing/webhook keys
P29-2: key versioning with grace period (old key still verifies during overlap)
P29-3: tamper-evident audit chain for every secret access / rotation
P29-4: compromise response plan (immediate revoke + emergency rotation)
P29-5: zero-downtime rotation (new key encrypts, old key still decrypts)
P29-6: HMAC-SHA256 key signatures -- keys are self-authenticating
P29-7: no plaintext secrets in logs, repr, or exceptions
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class KeyType(str, Enum):
    JWT_SIGNING = "jwt_signing"
    JWT_REFRESH = "jwt_refresh"
    ENCRYPTION_DEK = "encryption_dek"
    ENCRYPTION_KEK = "encryption_kek"
    SIGNING_ARTIFACT = "signing_artifact"
    WEBHOOK_HMAC = "webhook_hmac"
    AUDIT_CHAIN = "audit_chain"
    API_SECRET = "api_secret"
    BACKUP_ENCRYPT = "backup_encrypt"
    TENANT_ISOLATION = "tenant_isolation"


class KeyStatus(str, Enum):
    ACTIVE = "active"
    GRACE = "grace"
    REVOKED = "revoked"
    EXPIRED = "expired"
    PENDING = "pending"


class RotationTrigger(str, Enum):
    SCHEDULED = "scheduled"
    COMPROMISE = "compromise"
    MANUAL = "manual"
    POLICY_AGE = "policy_age"
    POLICY_USE = "policy_use"
    BOOTSTRAP = "bootstrap"


class AuditAction(str, Enum):
    KEY_GENERATED = "key.generated"
    KEY_ACTIVATED = "key.activated"
    KEY_ROTATED = "key.rotated"
    KEY_REVOKED = "key.revoked"
    KEY_EXPIRED = "key.expired"
    KEY_ACCESSED = "key.accessed"
    KEY_VERIFIED = "key.verified"
    COMPROMISE_ACK = "key.compromise_ack"
    GRACE_EXTENDED = "key.grace_extended"
    POLICY_UPDATED = "key.policy_updated"
    EMERGENCY_ROT = "key.emergency_rotation"


REQUIRES_REASON = {
    AuditAction.KEY_REVOKED,
    AuditAction.COMPROMISE_ACK,
    AuditAction.EMERGENCY_ROT,
    AuditAction.KEY_EXPIRED,
}

_POLICY_DEFAULTS: Dict[KeyType, Dict] = {
    KeyType.JWT_SIGNING: dict(max_age_days=30, grace_days=7, max_uses=0, auto_rotate=True),
    KeyType.JWT_REFRESH: dict(max_age_days=90, grace_days=14, max_uses=0, auto_rotate=True),
    KeyType.ENCRYPTION_DEK: dict(
        max_age_days=90, grace_days=30, max_uses=1_000_000, auto_rotate=True
    ),
    KeyType.ENCRYPTION_KEK: dict(max_age_days=365, grace_days=60, max_uses=0, auto_rotate=False),
    KeyType.SIGNING_ARTIFACT: dict(max_age_days=180, grace_days=30, max_uses=0, auto_rotate=True),
    KeyType.WEBHOOK_HMAC: dict(max_age_days=60, grace_days=14, max_uses=0, auto_rotate=True),
    KeyType.AUDIT_CHAIN: dict(max_age_days=365, grace_days=90, max_uses=0, auto_rotate=False),
    KeyType.API_SECRET: dict(max_age_days=90, grace_days=7, max_uses=0, auto_rotate=True),
    KeyType.BACKUP_ENCRYPT: dict(max_age_days=365, grace_days=60, max_uses=0, auto_rotate=False),
    KeyType.TENANT_ISOLATION: dict(max_age_days=180, grace_days=30, max_uses=0, auto_rotate=True),
}

COMPROMISE_RUNBOOK: List[str] = [
    "STEP-1: Immediately revoke compromised key (status=REVOKED)",
    "STEP-2: Generate emergency replacement key",
    "STEP-3: Activate new key (zero-downtime cutover)",
    "STEP-4: Reject all tokens/signatures from revoked key",
    "STEP-5: Notify security team via P1 alert",
    "STEP-6: Audit all recent accesses of compromised key",
    "STEP-7: Rotate all derived/dependent keys",
    "STEP-8: Verify new key works end-to-end",
    "STEP-9: Update key registry and downstream configs",
    "STEP-10: Post-mortem: root cause + timeline + remediation",
]


class SecretRotationError(Exception):
    pass


class KeyNotFoundError(SecretRotationError):
    pass


class KeyRevokedError(SecretRotationError):
    pass


class KeyExpiredError(SecretRotationError):
    pass


class MissingReasonError(SecretRotationError):
    pass


class PolicyViolationError(SecretRotationError):
    pass


class CompromiseResponseError(SecretRotationError):
    pass


@dataclass
class RotationPolicy:
    key_type: KeyType
    max_age_days: int = 90
    grace_days: int = 14
    max_uses: int = 0
    auto_rotate: bool = True
    tenant_id: Optional[str] = None

    @classmethod
    def default_for(cls, key_type: KeyType, tenant_id: Optional[str] = None) -> "RotationPolicy":
        d = _POLICY_DEFAULTS.get(key_type, {})
        return cls(key_type=key_type, tenant_id=tenant_id, **d)

    @property
    def max_age_seconds(self) -> float:
        return self.max_age_days * 86400.0

    @property
    def grace_seconds(self) -> float:
        return self.grace_days * 86400.0


@dataclass
class KeyVersion:
    key_id: str
    key_type: KeyType
    version: int
    status: KeyStatus
    created_at: float
    activated_at: Optional[float]
    expires_at: Optional[float]
    rotated_at: Optional[float]
    revoked_at: Optional[float]
    use_count: int
    tenant_id: Optional[str]
    _raw: bytes = field(repr=False, compare=False, default=b"")
    signature: str = ""
    rotation_trigger: RotationTrigger = RotationTrigger.BOOTSTRAP
    revoke_reason: Optional[str] = None

    def safe_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "key_type": self.key_type.value if hasattr(self.key_type, "value") else self.key_type,
            "version": self.version,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "expires_at": self.expires_at,
            "rotated_at": self.rotated_at,
            "revoked_at": self.revoked_at,
            "use_count": self.use_count,
            "tenant_id": self.tenant_id,
            "signature": self.signature,
            "rotation_trigger": self.rotation_trigger.value
            if hasattr(self.rotation_trigger, "value")
            else self.rotation_trigger,
        }

    @property
    def is_usable_for_new(self) -> bool:
        return self.status == KeyStatus.ACTIVE

    @property
    def is_usable_for_verify(self) -> bool:
        return self.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)


@dataclass
class AuditEntry:
    seq: int
    action: str
    key_id: str
    key_type: str
    version: int
    actor: str
    tenant_id: Optional[str]
    reason: Optional[str]
    detail: dict
    ts: float
    prev_hash: str
    chain_hash: str


@dataclass
class CompromiseReport:
    report_id: str
    key_id: str
    key_type: str
    version: int
    reported_by: str
    reported_at: float
    reason: str
    new_key_id: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    steps_taken: List[str] = field(default_factory=list)


class SecretAuditChain:
    GENESIS_CONST = "GENESIS:SECRET:CHAIN:V29"

    def __init__(self, secret: Optional[bytes] = None):
        self._secret = secret or os.urandom(32)
        self._entries: deque = deque(maxlen=10_000)
        self._lock = threading.Lock()
        self._seq = 0
        self._prev_hash = self._genesis()

    def _genesis(self) -> str:
        return hmac.new(self._secret, self.GENESIS_CONST.encode(), hashlib.sha256).hexdigest()

    def _hmac(self, data: str) -> str:
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()

    @property
    def genesis_hash(self) -> str:
        return self._genesis()

    def record(
        self,
        action: str | AuditAction,
        key_id: str,
        key_type: str,
        version: int,
        actor: str,
        tenant_id: Optional[str] = None,
        reason: Optional[str] = None,
        detail: Optional[dict] = None,
    ) -> AuditEntry:
        action_val = action.value if hasattr(action, "value") else action
        if action in REQUIRES_REASON or action_val in {a.value for a in REQUIRES_REASON}:
            if not reason or not reason.strip():
                raise MissingReasonError(f"reason required for action={action_val}")
        canonical = json.dumps(
            {
                "action": action_val,
                "key_id": key_id,
                "key_type": key_type,
                "version": version,
                "actor": actor,
                "tenant_id": tenant_id,
                "reason": reason,
                "detail": detail or {},
            },
            sort_keys=True,
        )
        with self._lock:
            self._seq += 1
            seq = self._seq
            chain_hash = self._hmac(self._prev_hash + ":" + canonical)
            entry = AuditEntry(
                seq=seq,
                action=action_val,
                key_id=key_id,
                key_type=key_type,
                version=version,
                actor=actor,
                tenant_id=tenant_id,
                reason=reason,
                detail=detail or {},
                ts=time.time(),
                prev_hash=self._prev_hash,
                chain_hash=chain_hash,
            )
            self._prev_hash = chain_hash
            self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return True
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps(
                {
                    "action": e.action,
                    "key_id": e.key_id,
                    "key_type": e.key_type,
                    "version": e.version,
                    "actor": e.actor,
                    "tenant_id": e.tenant_id,
                    "reason": e.reason,
                    "detail": e.detail,
                },
                sort_keys=True,
            )
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
            canonical = json.dumps(
                {
                    "action": e.action,
                    "key_id": e.key_id,
                    "key_type": e.key_type,
                    "version": e.version,
                    "actor": e.actor,
                    "tenant_id": e.tenant_id,
                    "reason": e.reason,
                    "detail": e.detail,
                },
                sort_keys=True,
            )
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                broken.append(e.seq)
            prev = e.chain_hash
        return broken

    def query(
        self,
        key_id: Optional[str] = None,
        action: Optional[str] = None,
        key_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        with self._lock:
            entries = list(self._entries)
        entries = list(reversed(entries))
        if key_id:
            entries = [e for e in entries if e.key_id == key_id]
        if action:
            entries = [e for e in entries if e.action == action]
        if key_type:
            entries = [e for e in entries if e.key_type == key_type]
        if limit and limit > 0:
            entries = entries[:limit]
        elif limit == 0:
            pass
        return entries

    @property
    def total(self) -> int:
        with self._lock:
            return self._seq


class KeyMaterialGenerator:
    KEY_SIZES: Dict[str, int] = {
        "jwt_signing": 64,
        "jwt_refresh": 64,
        "encryption_dek": 32,
        "encryption_kek": 32,
        "signing_artifact": 64,
        "webhook_hmac": 32,
        "audit_chain": 32,
        "api_secret": 32,
        "backup_encrypt": 32,
        "tenant_isolation": 32,
    }

    @classmethod
    def generate(cls, key_type: str) -> bytes:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        size = cls.KEY_SIZES.get(kt, 32)
        return secrets.token_bytes(size)

    @classmethod
    def key_id(cls) -> str:
        return str(uuid.uuid4())

    @classmethod
    def key_size(cls, key_type: str) -> int:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        return cls.KEY_SIZES.get(kt, 32)


class KeySelfAuth:
    def __init__(self, master: bytes):
        self._master = master

    def sign(self, kv: KeyVersion) -> str:
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        canonical = json.dumps(
            {
                "key_id": kv.key_id,
                "key_type": kt,
                "version": kv.version,
                "tenant_id": kv.tenant_id,
            },
            sort_keys=True,
        )
        return hmac.new(self._master, canonical.encode(), hashlib.sha256).hexdigest()

    def verify(self, kv: KeyVersion) -> bool:
        return hmac.compare_digest(self.sign(kv), kv.signature)


class KeyStore:
    def __init__(self):
        self._store: Dict[str, KeyVersion] = {}
        self._lock = threading.Lock()

    def add(self, kv: KeyVersion) -> None:
        with self._lock:
            self._store[kv.key_id] = kv

    def get(self, key_id: str) -> KeyVersion:
        with self._lock:
            kv = self._store.get(key_id)
        if kv is None:
            raise KeyNotFoundError(f"key_id={key_id}")
        return kv

    def active_key(self, key_type: str, tenant_id: Optional[str] = None) -> KeyVersion:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            candidates = [
                kv
                for kv in self._store.values()
                if (kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type) == kt
                and kv.status == KeyStatus.ACTIVE
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]
        if not candidates:
            raise KeyNotFoundError(f"no active key for type={kt}")
        return max(candidates, key=lambda k: k.version)

    def usable_keys(self, key_type: str, tenant_id: Optional[str] = None) -> List[KeyVersion]:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            return [
                kv
                for kv in self._store.values()
                if (kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type) == kt
                and kv.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]

    def list_by_type(self, key_type: str) -> List[KeyVersion]:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            return [
                kv
                for kv in self._store.values()
                if (kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type) == kt
            ]

    def all_keys(
        self, tenant_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[KeyVersion]:
        with self._lock:
            result = list(self._store.values())
        if tenant_id:
            result = [k for k in result if k.tenant_id == tenant_id]
        if status:
            st = status.value if hasattr(status, "value") else status
            result = [
                k
                for k in result
                if (k.status.value if hasattr(k.status, "value") else k.status) == st
            ]
        return result

    def update_status(
        self, key_id: str, status: KeyStatus, revoke_reason: Optional[str] = None
    ) -> None:
        with self._lock:
            kv = self._store.get(key_id)
            if kv is None:
                raise KeyNotFoundError(key_id)
            kv.status = status
            if revoke_reason:
                kv.revoke_reason = revoke_reason
            if status == KeyStatus.REVOKED:
                kv.revoked_at = time.time()

    def increment_use(self, key_id: str) -> int:
        with self._lock:
            kv = self._store.get(key_id)
            if kv:
                kv.use_count += 1
                return kv.use_count
            return 0


class RotationPolicyEngine:
    def __init__(self):
        self._policies: Dict[str, RotationPolicy] = {
            kt: RotationPolicy.default_for(kt) for kt in KeyType
        }
        self._lock = threading.Lock()

    def get_policy(
        self, key_type: KeyType | str, tenant_id: Optional[str] = None
    ) -> RotationPolicy:
        kt_val = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            tenant_key = f"{kt_val}:{tenant_id}" if tenant_id else None
            if tenant_key and tenant_key in self._policies:
                return self._policies[tenant_key]
            for kt in KeyType:
                if kt.value == kt_val and kt in self._policies:
                    return self._policies[kt]
            if kt_val in self._policies:
                return self._policies[kt_val]
        return RotationPolicy.default_for(
            key_type if isinstance(key_type, KeyType) else KeyType(kt_val)
        )

    def set_policy(
        self, key_type: KeyType | str, policy: RotationPolicy, tenant_id: Optional[str] = None
    ) -> None:
        kt_val = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            if tenant_id:
                self._policies[f"{kt_val}:{tenant_id}"] = policy
            else:
                for kt in KeyType:
                    if kt.value == kt_val:
                        self._policies[kt] = policy
                        return
                self._policies[kt_val] = policy

    def needs_rotation(self, kv: KeyVersion) -> bool:
        p = self.get_policy(kv.key_type, kv.tenant_id)
        if not p.auto_rotate or kv.status != KeyStatus.ACTIVE or kv.activated_at is None:
            return False
        age = time.time() - kv.activated_at
        if p.max_age_seconds > 0 and age >= p.max_age_seconds:
            return True
        if p.max_uses > 0 and kv.use_count >= p.max_uses:
            return True
        return False

    def is_grace_expired(self, kv: KeyVersion) -> bool:
        if kv.status != KeyStatus.GRACE or kv.expires_at is None:
            return False
        return time.time() >= kv.expires_at

    def due_soon(self, kv: KeyVersion, warn_seconds: float = 86400.0) -> bool:
        p = self.get_policy(kv.key_type, kv.tenant_id)
        if kv.status != KeyStatus.ACTIVE or kv.activated_at is None or p.max_age_seconds <= 0:
            return False
        return (p.max_age_seconds - (time.time() - kv.activated_at)) <= warn_seconds


class KeyLifecycleManager:
    """
    Central manager for zero-downtime key rotation.
    Flow: generate() -> activate() -> [rotate()] -> [revoke()/expire()]
    During rotation: old key moves to GRACE, new key is ACTIVE.
    Verifiers try ACTIVE first, then GRACE keys.
    """

    def __init__(
        self, master_secret: Optional[bytes] = None, audit: Optional[SecretAuditChain] = None
    ):
        self._master = master_secret or os.urandom(32)
        self._store = KeyStore()
        self._audit = audit if audit is not None else SecretAuditChain(self._master)
        self._policy_engine = RotationPolicyEngine()
        self._signer = KeySelfAuth(self._master)
        self._hooks: List[Callable] = []
        self._lock = threading.Lock()
        self._version_counters: Dict[str, int] = {}

    def _next_version(self, key_type: str, tenant_id: Optional[str] = None) -> int:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        counter_key = f"{kt}:{tenant_id}"
        with self._lock:
            v = self._version_counters.get(counter_key, 0) + 1
            self._version_counters[counter_key] = v
        return v

    def generate_key(
        self,
        key_type: KeyType | str,
        actor: str = "system",
        tenant_id: Optional[str] = None,
        activate: bool = False,
    ) -> KeyVersion:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        raw = KeyMaterialGenerator.generate(kt)
        version = self._next_version(kt, tenant_id)
        status = KeyStatus.ACTIVE if activate else KeyStatus.PENDING
        kv = KeyVersion(
            key_id=str(uuid.uuid4()),
            key_type=key_type,
            version=version,
            status=status,
            created_at=time.time(),
            activated_at=time.time() if activate else None,
            expires_at=None,
            rotated_at=None,
            revoked_at=None,
            use_count=0,
            tenant_id=tenant_id,
            _raw=raw,
        )
        kv.signature = self._signer.sign(kv)
        self._store.add(kv)
        self._audit.record(AuditAction.KEY_GENERATED, kv.key_id, kt, version, actor, tenant_id)
        if activate:
            self._audit.record(AuditAction.KEY_ACTIVATED, kv.key_id, kt, version, actor, tenant_id)
        self._fire_hooks("generate", kv)
        return kv

    def activate_key(self, key_id: str, actor: str) -> KeyVersion:
        kv = self._store.get(key_id)
        if kv.status != KeyStatus.PENDING:
            raise PolicyViolationError(f"key {key_id} is not PENDING")
        self._store.update_status(key_id, KeyStatus.ACTIVE)
        kv.activated_at = time.time()
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        self._audit.record(AuditAction.KEY_ACTIVATED, key_id, kt, kv.version, actor, kv.tenant_id)
        self._fire_hooks("activate", kv)
        return kv

    def active_key(self, key_type: KeyType | str, tenant_id: Optional[str] = None) -> KeyVersion:
        return self._store.active_key(key_type, tenant_id)

    def rotate_key(
        self,
        key_type: KeyType | str,
        actor: str,
        reason: str,
        trigger: RotationTrigger = RotationTrigger.MANUAL,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Optional[KeyVersion], KeyVersion]:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for rotation")
        kt = key_type.value if hasattr(key_type, "value") else key_type
        try:
            old = self._store.active_key(kt, tenant_id)
        except KeyNotFoundError:
            old = None
        policy = self._policy_engine.get_policy(key_type, tenant_id)
        raw = KeyMaterialGenerator.generate(kt)
        version = self._next_version(kt, tenant_id)
        new_kv = KeyVersion(
            key_id=str(uuid.uuid4()),
            key_type=key_type,
            version=version,
            status=KeyStatus.ACTIVE,
            created_at=time.time(),
            activated_at=time.time(),
            expires_at=None,
            rotated_at=None,
            revoked_at=None,
            use_count=0,
            tenant_id=tenant_id,
            _raw=raw,
            rotation_trigger=trigger,
        )
        new_kv.signature = self._signer.sign(new_kv)
        self._store.add(new_kv)
        if old:
            grace_exp = time.time() + policy.grace_seconds
            self._store.update_status(old.key_id, KeyStatus.GRACE)
            old.expires_at = grace_exp
            old.rotated_at = time.time()
        self._audit.record(
            AuditAction.KEY_ROTATED, new_kv.key_id, kt, version, actor, tenant_id, reason=reason
        )
        self._fire_hooks("rotate", new_kv)
        return old, new_kv

    def revoke_key(self, key_id: str, actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for revoke")
        kv = self._store.get(key_id)
        self._store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        self._audit.record(
            AuditAction.KEY_REVOKED, key_id, kt, kv.version, actor, kv.tenant_id, reason=reason
        )
        self._fire_hooks("revoke", kv)
        return kv

    def record_access(self, key_id: str, actor: str) -> None:
        kv = self._store.get(key_id)
        if kv.status == KeyStatus.REVOKED:
            raise KeyRevokedError(f"key {key_id} is REVOKED")
        if kv.status == KeyStatus.EXPIRED:
            raise KeyExpiredError(f"key {key_id} is EXPIRED")
        self._store.increment_use(key_id)
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        self._audit.record(AuditAction.KEY_ACCESSED, key_id, kt, kv.version, actor, kv.tenant_id)

    def get_key(self, key_id: str) -> KeyVersion:
        return self._store.get(key_id)

    def list_by_type(
        self, key_type: KeyType | str, tenant_id: Optional[str] = None
    ) -> List[KeyVersion]:
        kt = key_type.value if hasattr(key_type, "value") else key_type
        keys = self._store.list_by_type(kt)
        if tenant_id:
            keys = [k for k in keys if k.tenant_id == tenant_id]
        return keys

    def usable_keys(
        self, key_type: KeyType | str, tenant_id: Optional[str] = None
    ) -> List[KeyVersion]:
        return self._store.usable_keys(key_type, tenant_id)

    def expire_grace_keys(self, actor: str = "scheduler") -> List[str]:
        expired = []
        for kv in self._store.all_keys(status=KeyStatus.GRACE):
            if self._policy_engine.is_grace_expired(kv):
                self._store.update_status(kv.key_id, KeyStatus.EXPIRED)
                kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
                self._audit.record(
                    AuditAction.KEY_EXPIRED,
                    kv.key_id,
                    kt,
                    kv.version,
                    actor,
                    kv.tenant_id,
                    reason="grace period ended",
                )
                expired.append(kv.key_id)
        return expired

    def needs_rotation(self, kv: KeyVersion) -> bool:
        return self._policy_engine.needs_rotation(kv)

    def due_soon(self, kv: KeyVersion, warn_seconds: float = 86400.0) -> bool:
        return self._policy_engine.due_soon(kv, warn_seconds)

    def get_policy(
        self, key_type: KeyType | str, tenant_id: Optional[str] = None
    ) -> RotationPolicy:
        return self._policy_engine.get_policy(key_type, tenant_id)

    def set_policy(
        self, key_type: KeyType | str, policy: RotationPolicy, tenant_id: Optional[str] = None
    ) -> None:
        self._policy_engine.set_policy(key_type, policy, tenant_id)

    def self_auth_valid(self, kv: KeyVersion) -> bool:
        return self._signer.verify(kv)

    def sign_payload(self, payload: bytes, key_id: str) -> str:
        kv = self._store.get(key_id)
        if kv.status == KeyStatus.REVOKED:
            raise KeyRevokedError(f"key {key_id} is REVOKED")
        if not kv._raw:
            raise PolicyViolationError("no key material")
        return hmac.new(kv._raw, payload, hashlib.sha256).hexdigest()

    def verify_payload(
        self,
        payload: bytes,
        signature: str,
        key_type: KeyType | str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        usable = self._store.usable_keys(key_type, tenant_id)
        for kv in usable:
            if not kv._raw:
                continue
            expected = hmac.new(kv._raw, payload, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return True
        return False

    def add_rotation_hook(self, fn: Callable) -> None:
        self._hooks.append(fn)

    def _fire_hooks(self, event: str, kv: KeyVersion) -> None:
        for fn in self._hooks:
            try:
                fn(event, kv)
            except Exception:
                pass

    @property
    def store(self) -> KeyStore:
        return self._store

    @property
    def _audit_chain(self) -> SecretAuditChain:
        return self._audit


class CompromiseResponseManager:
    RUNBOOK = COMPROMISE_RUNBOOK

    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._reports: Dict[str, CompromiseReport] = {}
        self._lock = threading.Lock()

    def report_compromise(self, key_id: str, reported_by: str, reason: str) -> CompromiseReport:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required")
        kv = self._lc.get_key(key_id)
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        self._lc._store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        self._lc._audit.record(
            AuditAction.COMPROMISE_ACK,
            key_id,
            kt,
            kv.version,
            reported_by,
            kv.tenant_id,
            reason=reason,
        )
        _, new_kv = self._lc.rotate_key(
            kv.key_type,
            reported_by,
            reason=f"emergency rotation: {reason}",
            trigger=RotationTrigger.COMPROMISE,
            tenant_id=kv.tenant_id,
        )
        self._lc._audit.record(
            AuditAction.EMERGENCY_ROT,
            new_kv.key_id,
            kt,
            new_kv.version,
            reported_by,
            kv.tenant_id,
            reason=f"emergency: {reason}",
        )
        report = CompromiseReport(
            report_id=str(uuid.uuid4()),
            key_id=key_id,
            key_type=kt,
            version=kv.version,
            reported_by=reported_by,
            reported_at=time.time(),
            reason=reason,
            new_key_id=new_kv.key_id,
            resolved=False,
            steps_taken=self.RUNBOOK[:5],
        )
        with self._lock:
            self._reports[report.report_id] = report
        return report

    def resolve_report(self, report_id: str, resolved_by: str) -> CompromiseReport:
        with self._lock:
            r = self._reports.get(report_id)
            if r is None:
                raise KeyNotFoundError(report_id)
            r.resolved = True
            r.resolved_at = time.time()
            r.resolved_by = resolved_by
            r.steps_taken = self.RUNBOOK
        return r

    def list_reports(self, resolved: Optional[bool] = None) -> List[CompromiseReport]:
        with self._lock:
            reports = list(self._reports.values())
        if resolved is not None:
            reports = [r for r in reports if r.resolved == resolved]
        return reports

    def open_reports(self) -> List[CompromiseReport]:
        return self.list_reports(resolved=False)


class RotationScheduler:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def schedule(
        self,
        key_type: KeyType | str,
        at_ts: float,
        actor: str = "scheduler",
        tenant_id: Optional[str] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        kt = key_type.value if hasattr(key_type, "value") else key_type
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "key_type": kt,
                "at_ts": at_ts,
                "actor": actor,
                "tenant_id": tenant_id,
                "done": False,
                "created_at": time.time(),
            }
        return job_id

    def scan_due(self) -> List[str]:
        now = time.time()
        rotated = []
        with self._lock:
            due = [j for j in self._jobs.values() if not j["done"] and j["at_ts"] <= now]
        for job in due:
            try:
                self._lc.rotate_key(
                    job["key_type"],
                    job["actor"],
                    reason="scheduled rotation",
                    trigger=RotationTrigger.SCHEDULED,
                    tenant_id=job["tenant_id"],
                )
                with self._lock:
                    self._jobs[job["job_id"]]["done"] = True
                rotated.append(job["job_id"])
            except Exception:
                pass
        return rotated

    def scan_due_soon(self, warn_seconds: float = 86400.0) -> List[KeyVersion]:
        all_keys = self._lc.store.all_keys()
        return [kv for kv in all_keys if self._lc.due_soon(kv, warn_seconds)]

    def auto_rotate_all(self, actor: str = "scheduler") -> List[KeyVersion]:
        rotated = []
        for kv in self._lc.store.all_keys():
            if self._lc.needs_rotation(kv):
                try:
                    _, new_kv = self._lc.rotate_key(
                        kv.key_type,
                        actor,
                        reason="auto-rotation by policy",
                        trigger=RotationTrigger.POLICY_AGE,
                        tenant_id=kv.tenant_id,
                    )
                    rotated.append(new_kv)
                except Exception:
                    pass
        return rotated

    def expire_grace_pass(self, actor: str = "scheduler") -> List[str]:
        return self._lc.expire_grace_keys(actor)

    def pending_jobs(self) -> List[dict]:
        with self._lock:
            return [j for j in self._jobs.values() if not j["done"]]


class GracePeriodExtender:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle

    def extend(self, key_id: str, extra_seconds: float, actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for grace extension")
        kv = self._lc.get_key(key_id)
        if kv.status != KeyStatus.GRACE:
            raise PolicyViolationError(f"key {key_id} not in GRACE status")
        old_exp = kv.expires_at or time.time()
        kv.expires_at = old_exp + extra_seconds
        kt = kv.key_type.value if hasattr(kv.key_type, "value") else kv.key_type
        self._lc._audit.record(
            AuditAction.GRACE_EXTENDED, key_id, kt, kv.version, actor, kv.tenant_id, reason=reason
        )
        return kv


class SecretRotationAdmin:
    def __init__(
        self,
        lifecycle: KeyLifecycleManager,
        scheduler: Optional[RotationScheduler] = None,
        compromise: Optional[CompromiseResponseManager] = None,
    ):
        self._lc = lifecycle
        self._scheduler = scheduler or RotationScheduler(lifecycle)
        self._compromise = compromise or CompromiseResponseManager(lifecycle)
        self._extender = GracePeriodExtender(lifecycle)

    def summary(self, tenant_id: Optional[str] = None) -> dict:
        all_keys = self._lc.store.all_keys(tenant_id=tenant_id)
        by_status: Dict[str, int] = {}
        for kv in all_keys:
            st = kv.status.value if hasattr(kv.status, "value") else kv.status
            by_status[st] = by_status.get(st, 0) + 1
        return {
            "total_keys": len(all_keys),
            "by_status": by_status,
            "open_compromises": len(self._compromise.open_reports()),
            "pending_rotations": len(self._scheduler.scan_due_soon()),
            "audit_total": self._lc._audit.total,
            "chain_valid": self._lc._audit.verify_chain(),
        }

    def health_check(self) -> dict:
        issues = []
        for kv in self._lc.store.all_keys():
            if self._lc.needs_rotation(kv):
                issues.append(f"{kv.key_id}: needs rotation")
        return {"healthy": len(issues) == 0, "issues": issues}

    def bulk_rotate(
        self, key_types: List[KeyType], actor: str, reason: str, tenant_id: Optional[str] = None
    ) -> Dict[str, KeyVersion]:
        result = {}
        for kt in key_types:
            try:
                _, new_kv = self._lc.rotate_key(kt, actor, reason, tenant_id=tenant_id)
                result[kt.value if hasattr(kt, "value") else kt] = new_kv
            except Exception:
                pass
        return result

    def key_audit_trail(self, key_id: str) -> List[AuditEntry]:
        return self._lc._audit.query(key_id=key_id, limit=0)

    @property
    def lifecycle(self) -> KeyLifecycleManager:
        return self._lc

    @property
    def scheduler(self) -> RotationScheduler:
        return self._scheduler

    @property
    def compromise_mgr(self) -> CompromiseResponseManager:
        return self._compromise

    @property
    def extender(self) -> GracePeriodExtender:
        return self._extender


def build_secret_rotation_system(
    master_secret: Optional[bytes] = None,
) -> Tuple[
    KeyLifecycleManager,
    RotationScheduler,
    CompromiseResponseManager,
    GracePeriodExtender,
    SecretRotationAdmin,
]:
    audit = SecretAuditChain(master_secret or os.urandom(32))
    lifecycle = KeyLifecycleManager(master_secret=master_secret, audit=audit)
    scheduler = RotationScheduler(lifecycle)
    compromise = CompromiseResponseManager(lifecycle)
    extender = GracePeriodExtender(lifecycle)
    admin = SecretRotationAdmin(lifecycle, scheduler, compromise)
    return lifecycle, scheduler, compromise, extender, admin


__all__ = [
    "KeyType",
    "KeyStatus",
    "RotationTrigger",
    "AuditAction",
    "REQUIRES_REASON",
    "_POLICY_DEFAULTS",
    "COMPROMISE_RUNBOOK",
    "RotationPolicy",
    "KeyVersion",
    "AuditEntry",
    "CompromiseReport",
    "SecretAuditChain",
    "KeyMaterialGenerator",
    "KeySelfAuth",
    "KeyStore",
    "RotationPolicyEngine",
    "KeyLifecycleManager",
    "CompromiseResponseManager",
    "RotationScheduler",
    "GracePeriodExtender",
    "SecretRotationAdmin",
    "build_secret_rotation_system",
    "SecretRotationError",
    "KeyNotFoundError",
    "KeyRevokedError",
    "KeyExpiredError",
    "MissingReasonError",
    "PolicyViolationError",
    "CompromiseResponseError",
]
