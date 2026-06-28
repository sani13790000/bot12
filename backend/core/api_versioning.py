"""
Phase 26 - API Versioning & Backward Compatibility
====================================================
Versioned routes, schema migration, deprecation policy,
graceful version mismatch handling, audit trail.
"""
from __future__ import annotations

import copy
import hashlib
import hmac as _hmac_mod
import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class APIVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, s: str) -> "APIVersion":
        s = s.strip().lower()
        for member in cls:
            if member.value == s:
                return member
        raise UnknownVersionError(f"Unknown API version: {s!r}")

    def as_int(self) -> int:
        return int(self.value[1:])


class VersionStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    EXPERIMENTAL = "experimental"


class CompatibilityLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    BREAKING = "breaking"


class DeprecationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MigrationStrategy(str, Enum):
    PASSTHROUGH = "passthrough"
    FIELD_RENAME = "field_rename"
    FIELD_ADD = "field_add"
    FIELD_REMOVE = "field_remove"
    TRANSFORM = "transform"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class VersionError(Exception):
    """Base version error."""


class UnknownVersionError(VersionError):
    """Unknown API version string."""


class SunsetVersionError(VersionError):
    """Requested version is sunset (410 Gone)."""
    def __init__(self, version: APIVersion, sunset_at: str):
        self.version = version
        self.sunset_at = sunset_at
        super().__init__(
            f"API {version} was sunset on {sunset_at}. "
            f"Please upgrade to a supported version."
        )


class VersionMismatchError(VersionError):
    """Client requested version incompatible with server."""
    def __init__(self, requested: str, supported: List[str]):
        self.requested = requested
        self.supported = supported
        super().__init__(
            f"Version {requested!r} is not supported. "
            f"Supported: {supported}"
        )


class BreakingChangeError(VersionError):
    """Attempted a breaking schema change without version bump."""


class MissingReasonError(VersionError):
    """Deprecation/sunset requires a reason."""


# ---------------------------------------------------------------------------
# Version Registry
# ---------------------------------------------------------------------------

VERSION_SUNSET_DATES: Dict[APIVersion, str] = {}
VERSION_DEPRECATION_DATES: Dict[APIVersion, str] = {}
CURRENT_VERSION = APIVersion.V3
SUPPORTED_VERSIONS: Set[APIVersion] = {APIVersion.V1, APIVersion.V2, APIVersion.V3}
DEPRECATED_VERSIONS: Set[APIVersion] = set()

VERSIONED_ENDPOINTS: Dict[str, Set[APIVersion]] = {
    "/api/signals":                {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/auth/login":             {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/auth/register":          {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/license/validate":       {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/license/issue":          {APIVersion.V2, APIVersion.V3},
    "/api/billing/checkout":       {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/billing/webhook":        {APIVersion.V2, APIVersion.V3},
    "/api/risk/halt":              {APIVersion.V1, APIVersion.V2, APIVersion.V3},
    "/api/risk/status":            {APIVersion.V2, APIVersion.V3},
    "/api/ea/config":              {APIVersion.V2, APIVersion.V3},
    "/api/ea/heartbeat":           {APIVersion.V2, APIVersion.V3},
    "/api/tenant/settings":        {APIVersion.V3},
    "/api/audit/trail":            {APIVersion.V3},
    "/api/feature-flags":          {APIVersion.V3},
    "/api/artifacts":              {APIVersion.V3},
}


# ---------------------------------------------------------------------------
# Version Policy
# ---------------------------------------------------------------------------

@dataclass
class VersionPolicy:
    version: APIVersion
    status: VersionStatus
    released_at: str
    deprecated_at: Optional[str] = None
    sunset_at: Optional[str] = None
    deprecation_reason: Optional[str] = None
    deprecation_severity: DeprecationSeverity = DeprecationSeverity.INFO
    successor: Optional[APIVersion] = None
    sunset_response_code: int = 410

    def is_active(self) -> bool:
        return self.status == VersionStatus.ACTIVE

    def is_deprecated(self) -> bool:
        return self.status == VersionStatus.DEPRECATED

    def is_sunset(self) -> bool:
        return self.status == VersionStatus.SUNSET

    def is_experimental(self) -> bool:
        return self.status == VersionStatus.EXPERIMENTAL

    def days_until_sunset(self) -> Optional[int]:
        if not self.sunset_at:
            return None
        try:
            sunset_dt = datetime.fromisoformat(self.sunset_at).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = (sunset_dt - now).days
            return max(0, delta)
        except ValueError:
            return None

    def deprecation_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.is_deprecated():
            headers["Deprecation"] = self.deprecated_at or "true"
            if self.sunset_at:
                headers["Sunset"] = self.sunset_at
            if self.successor:
                headers["Link"] = (
                    f'</api/{self.successor}/...>; rel="successor-version"'
                )
        return headers


DEFAULT_VERSION_POLICIES: Dict[APIVersion, VersionPolicy] = {
    APIVersion.V1: VersionPolicy(
        version=APIVersion.V1,
        status=VersionStatus.DEPRECATED,
        released_at="2024-01-01",
        deprecated_at="2026-01-01",
        sunset_at="2027-01-01",
        deprecation_reason="V1 lacks tenant isolation and audit support",
        deprecation_severity=DeprecationSeverity.WARNING,
        successor=APIVersion.V3,
    ),
    APIVersion.V2: VersionPolicy(
        version=APIVersion.V2,
        status=VersionStatus.ACTIVE,
        released_at="2025-01-01",
    ),
    APIVersion.V3: VersionPolicy(
        version=APIVersion.V3,
        status=VersionStatus.ACTIVE,
        released_at="2026-01-01",
    ),
}


# ---------------------------------------------------------------------------
# Schema Field Descriptors
# ---------------------------------------------------------------------------

@dataclass
class FieldDescriptor:
    name: str
    required: bool = True
    added_in: APIVersion = APIVersion.V1
    removed_in: Optional[APIVersion] = None
    renamed_from: Optional[str] = None
    default: Any = None

    def is_available_in(self, version: APIVersion) -> bool:
        if version.as_int() < self.added_in.as_int():
            return False
        if self.removed_in and version.as_int() >= self.removed_in.as_int():
            return False
        return True


# ---------------------------------------------------------------------------
# Schema Registry
# ---------------------------------------------------------------------------

@dataclass
class VersionedSchema:
    name: str
    fields: List[FieldDescriptor]
    compatibility: CompatibilityLevel = CompatibilityLevel.FULL
    changelog: str = ""

    def fields_for_version(self, version: APIVersion) -> List[FieldDescriptor]:
        return [f for f in self.fields if f.is_available_in(version)]

    def required_fields_for_version(self, version: APIVersion) -> List[str]:
        return [
            f.name for f in self.fields_for_version(version)
            if f.required
        ]

    def validate(self, data: Dict[str, Any], version: APIVersion) -> List[str]:
        errors: List[str] = []
        for f in self.fields_for_version(version):
            if f.required and f.name not in data:
                errors.append(f"Missing required field: {f.name!r}")
        return errors


VERSIONED_SCHEMAS: Dict[str, VersionedSchema] = {
    "signal": VersionedSchema(
        name="signal",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 adds tenant_id; V3 adds audit_token and feature_flags",
        fields=[
            FieldDescriptor("id", required=True, added_in=APIVersion.V1),
            FieldDescriptor("symbol", required=True, added_in=APIVersion.V1),
            FieldDescriptor("direction", required=True, added_in=APIVersion.V1),
            FieldDescriptor("entry_price", required=True, added_in=APIVersion.V1),
            FieldDescriptor("sl", required=True, added_in=APIVersion.V1),
            FieldDescriptor("tp", required=True, added_in=APIVersion.V1),
            FieldDescriptor("timestamp", required=True, added_in=APIVersion.V1),
            FieldDescriptor("tenant_id", required=True, added_in=APIVersion.V2),
            FieldDescriptor("audit_token", required=False, added_in=APIVersion.V3),
            FieldDescriptor("feature_flags", required=False, added_in=APIVersion.V3, default={}),
        ],
    ),
    "auth_response": VersionedSchema(
        name="auth_response",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 adds refresh_token; V3 adds tenant_id and roles",
        fields=[
            FieldDescriptor("access_token", required=True, added_in=APIVersion.V1),
            FieldDescriptor("expires_in", required=True, added_in=APIVersion.V1),
            FieldDescriptor("user_id", required=True, added_in=APIVersion.V1),
            FieldDescriptor("refresh_token", required=False, added_in=APIVersion.V2),
            FieldDescriptor("tenant_id", required=True, added_in=APIVersion.V3),
            FieldDescriptor("roles", required=False, added_in=APIVersion.V3, default=[]),
        ],
    ),
    "license": VersionedSchema(
        name="license",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 adds plan_tier; V3 adds feature_set and audit_chain",
        fields=[
            FieldDescriptor("license_key", required=True, added_in=APIVersion.V1),
            FieldDescriptor("user_id", required=True, added_in=APIVersion.V1),
            FieldDescriptor("valid_until", required=True, added_in=APIVersion.V1),
            FieldDescriptor("plan_tier", required=True, added_in=APIVersion.V2),
            FieldDescriptor("feature_set", required=False, added_in=APIVersion.V3, default=[]),
            FieldDescriptor("audit_chain", required=False, added_in=APIVersion.V3),
        ],
    ),
    "billing_checkout": VersionedSchema(
        name="billing_checkout",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 adds idempotency_key; V3 adds tenant_id and metadata",
        fields=[
            FieldDescriptor("plan_id", required=True, added_in=APIVersion.V1),
            FieldDescriptor("user_id", required=True, added_in=APIVersion.V1),
            FieldDescriptor("amount_cents", required=True, added_in=APIVersion.V1),
            FieldDescriptor("idempotency_key", required=True, added_in=APIVersion.V2),
            FieldDescriptor("tenant_id", required=True, added_in=APIVersion.V3),
            FieldDescriptor("metadata", required=False, added_in=APIVersion.V3, default={}),
        ],
    ),
    "risk_status": VersionedSchema(
        name="risk_status",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 adds kill_switch_active; V3 adds incident_id and audit",
        fields=[
            FieldDescriptor("equity", required=True, added_in=APIVersion.V1),
            FieldDescriptor("drawdown_pct", required=True, added_in=APIVersion.V1),
            FieldDescriptor("halted", required=True, added_in=APIVersion.V1),
            FieldDescriptor("kill_switch_active", required=True, added_in=APIVersion.V2),
            FieldDescriptor("incident_id", required=False, added_in=APIVersion.V3),
            FieldDescriptor("audit_token", required=False, added_in=APIVersion.V3),
        ],
    ),
    "ea_config": VersionedSchema(
        name="ea_config",
        compatibility=CompatibilityLevel.PARTIAL,
        changelog="V2 introduces ea_config; V3 adds feature_flags and kill_switch",
        fields=[
            FieldDescriptor("ea_id", required=True, added_in=APIVersion.V2),
            FieldDescriptor("params", required=True, added_in=APIVersion.V2),
            FieldDescriptor("version", required=True, added_in=APIVersion.V2),
            FieldDescriptor("feature_flags", required=False, added_in=APIVersion.V3, default={}),
            FieldDescriptor("kill_switch", required=False, added_in=APIVersion.V3, default=False),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Response Migrator
# ---------------------------------------------------------------------------

@dataclass
class MigrationRule:
    source_version: APIVersion
    target_version: APIVersion
    strategy: MigrationStrategy
    field_map: Dict[str, str] = field(default_factory=dict)
    add_defaults: Dict[str, Any] = field(default_factory=dict)
    remove_fields: List[str] = field(default_factory=list)
    transform_fn: Optional[Callable[[Dict], Dict]] = None


class ResponseMigrator:
    def __init__(self) -> None:
        self._rules: List[MigrationRule] = []
        self._lock = threading.Lock()
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        self.register(MigrationRule(
            source_version=APIVersion.V1,
            target_version=APIVersion.V2,
            strategy=MigrationStrategy.FIELD_ADD,
            add_defaults={"tenant_id": None, "refresh_token": None},
        ))
        self.register(MigrationRule(
            source_version=APIVersion.V2,
            target_version=APIVersion.V3,
            strategy=MigrationStrategy.FIELD_ADD,
            add_defaults={"audit_token": None, "feature_flags": {}, "roles": [], "incident_id": None},
        ))
        self.register(MigrationRule(
            source_version=APIVersion.V3,
            target_version=APIVersion.V2,
            strategy=MigrationStrategy.FIELD_REMOVE,
            remove_fields=["audit_token", "feature_flags", "roles", "incident_id", "audit_chain"],
        ))
        self.register(MigrationRule(
            source_version=APIVersion.V2,
            target_version=APIVersion.V1,
            strategy=MigrationStrategy.FIELD_REMOVE,
            remove_fields=["refresh_token", "tenant_id", "kill_switch_active",
                           "idempotency_key", "plan_tier"],
        ))

    def register(self, rule: MigrationRule) -> None:
        with self._lock:
            self._rules.append(rule)

    def migrate(self, data: Dict[str, Any], from_version: APIVersion,
                to_version: APIVersion) -> Dict[str, Any]:
        if from_version == to_version:
            return dict(data)
        result = dict(data)
        for rule in self._rules:
            if rule.source_version == from_version and rule.target_version == to_version:
                return self._apply_rule(result, rule)
        return self._step_migrate(result, from_version, to_version)

    def _step_migrate(self, data: Dict[str, Any], from_v: APIVersion,
                      to_v: APIVersion) -> Dict[str, Any]:
        versions = list(APIVersion)
        from_idx = versions.index(from_v)
        to_idx = versions.index(to_v)
        step = 1 if to_idx > from_idx else -1
        result = dict(data)
        for i in range(from_idx, to_idx, step):
            next_v = versions[i + step]
            result = self.migrate(result, versions[i], next_v)
        return result

    def _apply_rule(self, data: Dict[str, Any], rule: MigrationRule) -> Dict[str, Any]:
        result = dict(data)
        if rule.strategy == MigrationStrategy.PASSTHROUGH:
            pass
        elif rule.strategy == MigrationStrategy.FIELD_ADD:
            for k, v in rule.add_defaults.items():
                if k not in result:
                    result[k] = v
        elif rule.strategy == MigrationStrategy.FIELD_REMOVE:
            for k in rule.remove_fields:
                result.pop(k, None)
        elif rule.strategy == MigrationStrategy.FIELD_RENAME:
            for old, new in rule.field_map.items():
                if old in result:
                    result[new] = result.pop(old)
        elif rule.strategy == MigrationStrategy.TRANSFORM:
            if rule.transform_fn:
                result = rule.transform_fn(result)
        return result


# ---------------------------------------------------------------------------
# Deprecation Notice
# ---------------------------------------------------------------------------

@dataclass
class DeprecationNotice:
    version: APIVersion
    endpoint: str
    message: str
    severity: DeprecationSeverity
    deprecated_at: str
    sunset_at: Optional[str]
    successor_version: Optional[APIVersion]
    successor_endpoint: Optional[str]
    migration_guide_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warning": f"API {self.version} is deprecated",
            "message": self.message,
            "severity": self.severity.value,
            "deprecated_at": self.deprecated_at,
            "sunset_at": self.sunset_at,
            "successor_version": str(self.successor_version) if self.successor_version else None,
            "successor_endpoint": self.successor_endpoint,
            "migration_guide_url": self.migration_guide_url,
        }

    def headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Deprecation": self.deprecated_at,
            "X-API-Deprecation-Severity": self.severity.value,
            "X-API-Successor": str(self.successor_version) if self.successor_version else "",
        }
        if self.sunset_at:
            h["Sunset"] = self.sunset_at
        if self.migration_guide_url:
            h["X-API-Migration-Guide"] = self.migration_guide_url
        return h


# ---------------------------------------------------------------------------
# Version Negotiator
# ---------------------------------------------------------------------------

class VersionNegotiator:
    def __init__(self, policies: Optional[Dict[APIVersion, VersionPolicy]] = None) -> None:
        self._policies = (
            policies if policies is not None
            else copy.deepcopy(DEFAULT_VERSION_POLICIES)
        )
        self._lock = threading.Lock()

    def negotiate(self, requested: str, endpoint: str = "/") -> Tuple[APIVersion, Optional[DeprecationNotice]]:
        try:
            version = APIVersion.from_string(requested)
        except UnknownVersionError:
            supported = [v.value for v in self._policies.keys()]
            raise VersionMismatchError(requested, supported)

        policy = self._policies.get(version)
        if policy is None:
            supported = [v.value for v in self._policies.keys()]
            raise VersionMismatchError(requested, supported)

        if policy.is_sunset():
            raise SunsetVersionError(version, policy.sunset_at or "unknown")

        if endpoint != "/" and endpoint in VERSIONED_ENDPOINTS:
            if version not in VERSIONED_ENDPOINTS[endpoint]:
                supported = [v.value for v in VERSIONED_ENDPOINTS[endpoint]]
                raise VersionMismatchError(requested, supported)

        notice: Optional[DeprecationNotice] = None
        if policy.is_deprecated():
            notice = DeprecationNotice(
                version=version,
                endpoint=endpoint,
                message=policy.deprecation_reason or f"API {version} is deprecated.",
                severity=policy.deprecation_severity,
                deprecated_at=policy.deprecated_at or "",
                sunset_at=policy.sunset_at,
                successor_version=policy.successor,
                successor_endpoint=(
                    f"/api/{policy.successor}{endpoint}"
                    if policy.successor else None
                ),
            )
        return version, notice

    def sunset_version(self, version: APIVersion, reason: str,
                       sunset_at: str, actor: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("sunset requires a non-empty reason")
        with self._lock:
            policy = self._policies.get(version)
            if policy is None:
                raise VersionMismatchError(version.value, [])
            policy.status = VersionStatus.SUNSET
            policy.sunset_at = sunset_at
            policy.deprecation_reason = reason

    def deprecate_version(self, version: APIVersion, reason: str,
                          deprecated_at: str, sunset_at: Optional[str],
                          actor: str, successor: Optional[APIVersion] = None) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("deprecation requires a non-empty reason")
        with self._lock:
            policy = self._policies.get(version)
            if policy is None:
                raise VersionMismatchError(version.value, [])
            policy.status = VersionStatus.DEPRECATED
            policy.deprecated_at = deprecated_at
            policy.sunset_at = sunset_at
            policy.deprecation_reason = reason
            if successor:
                policy.successor = successor

    def supported_versions(self) -> List[APIVersion]:
        with self._lock:
            return [v for v, p in self._policies.items() if not p.is_sunset()]

    def active_versions(self) -> List[APIVersion]:
        with self._lock:
            return [v for v, p in self._policies.items() if p.is_active()]

    def deprecated_versions(self) -> List[APIVersion]:
        with self._lock:
            return [v for v, p in self._policies.items() if p.is_deprecated()]

    def get_policy(self, version: APIVersion) -> Optional[VersionPolicy]:
        return self._policies.get(version)


# ---------------------------------------------------------------------------
# Version Audit Chain
# ---------------------------------------------------------------------------

_DEFAULT_AUDIT_SECRET = os.getenv("VERSION_AUDIT_SECRET", "phase26-version-audit-secret").encode()


@dataclass
class VersionAuditEntry:
    entry_id: str
    action: str
    version: str
    endpoint: str
    actor: str
    tenant_id: Optional[str]
    detail: Dict[str, Any]
    ts: float
    seq: int
    chain_hash: str
    prev_hash: str


class VersionAuditChain:
    _GENESIS_CONST = b"GENESIS:API:VERSION:CHAIN:V26"
    _MAX_RECORDS = 50_000

    def __init__(self, secret: Optional[bytes] = None) -> None:
        self._secret = (
            secret if isinstance(secret, bytes)
            else (secret.encode() if secret else _DEFAULT_AUDIT_SECRET)
        )
        self._records: deque = deque(maxlen=self._MAX_RECORDS)
        self._lock = threading.Lock()
        self._seq = 1
        self._genesis = self._hmac(self._GENESIS_CONST)
        self._prev_hash = self._genesis

    def _hmac(self, data: bytes) -> str:
        return _hmac_mod.new(self._secret, data, digestmod="sha256").hexdigest()

    def record(self, action: str, version: str, endpoint: str,
               actor: str = "system", tenant_id: Optional[str] = None,
               detail: Optional[Dict[str, Any]] = None) -> VersionAuditEntry:
        with self._lock:
            entry_id = str(uuid.uuid4())
            ts = time.time()
            det = detail or {}
            canonical = json.dumps(
                {"entry_id": entry_id, "action": action, "version": version,
                 "endpoint": endpoint, "actor": actor, "tenant_id": tenant_id,
                 "detail": det, "ts": ts},
                sort_keys=True, separators=(",", ":")
            ).encode()
            chain_hash = self._hmac((self._prev_hash + ":").encode() + canonical)
            entry = VersionAuditEntry(
                entry_id=entry_id, action=action, version=version,
                endpoint=endpoint, actor=actor, tenant_id=tenant_id,
                detail=det, ts=ts, seq=self._seq,
                chain_hash=chain_hash, prev_hash=self._prev_hash,
            )
            self._records.append(entry)
            self._prev_hash = chain_hash
            self._seq += 1
            return entry

    def verify_chain(self) -> bool:
        with self._lock:
            records = list(self._records)
        if not records:
            return True
        prev = self._genesis
        for r in records:
            if r.prev_hash != prev:
                return False
            canonical = json.dumps(
                {"entry_id": r.entry_id, "action": r.action, "version": r.version,
                 "endpoint": r.endpoint, "actor": r.actor, "tenant_id": r.tenant_id,
                 "detail": r.detail, "ts": r.ts},
                sort_keys=True, separators=(",", ":")
            ).encode()
            expected = _hmac_mod.new(
                self._secret, (prev + ":").encode() + canonical, digestmod="sha256"
            ).hexdigest()
            if r.chain_hash != expected:
                return False
            prev = r.chain_hash
        return True

    def query(self, action: Optional[str] = None, version: Optional[str] = None,
              limit: int = 100) -> List[VersionAuditEntry]:
        with self._lock:
            records = list(self._records)
        results = []
        for r in reversed(records):
            if action and r.action != action:
                continue
            if version and r.version != version:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    def __len__(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# Version Router
# ---------------------------------------------------------------------------

@dataclass
class VersionedRequest:
    path: str
    version_str: str
    client_id: str = "anonymous"
    tenant_id: Optional[str] = None
    body: Optional[Dict[str, Any]] = None


@dataclass
class VersionedResponse:
    status_code: int
    version: APIVersion
    body: Dict[str, Any]
    headers: Dict[str, str]
    deprecation_notice: Optional[DeprecationNotice] = None

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_deprecated(self) -> bool:
        return self.deprecation_notice is not None


class VersionRouter:
    def __init__(self, negotiator: Optional[VersionNegotiator] = None,
                 migrator: Optional[ResponseMigrator] = None,
                 audit: Optional[VersionAuditChain] = None,
                 canonical_version: APIVersion = APIVersion.V3) -> None:
        self._negotiator = negotiator or VersionNegotiator()
        self._migrator = migrator or ResponseMigrator()
        self._audit = audit or VersionAuditChain()
        self._canonical = canonical_version
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()

    def route(self, request: VersionedRequest) -> VersionedResponse:
        try:
            version, notice = self._negotiator.negotiate(request.version_str, request.path)
        except SunsetVersionError as e:
            self._audit.record("sunset_blocked", request.version_str, request.path,
                               actor=request.client_id, tenant_id=request.tenant_id,
                               detail={"error": str(e)})
            return VersionedResponse(
                status_code=410, version=self._canonical,
                body={"error": "Gone", "message": str(e), "code": "SUNSET"},
                headers={"X-API-Version": request.version_str},
            )
        except VersionMismatchError as e:
            self._audit.record("mismatch", request.version_str, request.path,
                               actor=request.client_id, tenant_id=request.tenant_id,
                               detail={"supported": e.supported})
            return VersionedResponse(
                status_code=400, version=self._canonical,
                body={"error": "VersionMismatch", "message": str(e),
                      "supported_versions": e.supported, "code": "VERSION_MISMATCH"},
                headers={"X-API-Version": request.version_str,
                         "X-Supported-Versions": ",".join(e.supported)},
            )

        handler_body = self._call_handler(request.path, version, request)
        migrated = self._migrator.migrate(handler_body, from_version=self._canonical,
                                          to_version=version)
        headers: Dict[str, str] = {
            "X-API-Version": version.value,
            "X-API-Canonical-Version": self._canonical.value,
        }
        if notice:
            headers.update(notice.headers())

        self._audit.record("route", version.value, request.path,
                           actor=request.client_id, tenant_id=request.tenant_id,
                           detail={"deprecated": notice is not None,
                                   "migrated": version != self._canonical})
        return VersionedResponse(
            status_code=200, version=version, body=migrated,
            headers=headers, deprecation_notice=notice,
        )

    def register_handler(self, path: str, handler: Callable[[VersionedRequest], Dict[str, Any]]) -> None:
        with self._lock:
            self._handlers[path] = handler

    def _call_handler(self, path: str, version: APIVersion,
                      request: VersionedRequest) -> Dict[str, Any]:
        handler = self._handlers.get(path)
        if handler:
            return handler(request)
        return {
            "status": "ok", "version": version.value, "path": path,
            "tenant_id": request.tenant_id, "audit_token": str(uuid.uuid4()),
            "feature_flags": {}, "roles": [], "incident_id": None,
        }

    @property
    def audit(self) -> VersionAuditChain:
        return self._audit

    @property
    def negotiator(self) -> VersionNegotiator:
        return self._negotiator

    @property
    def migrator(self) -> ResponseMigrator:
        return self._migrator


# ---------------------------------------------------------------------------
# Breaking Change Detector
# ---------------------------------------------------------------------------

class BreakingChangeDetector:
    @staticmethod
    def compare(old_schema: VersionedSchema, new_schema: VersionedSchema,
                old_version: APIVersion, new_version: APIVersion) -> List[str]:
        issues: List[str] = []
        old_fields = {f.name: f for f in old_schema.fields_for_version(old_version)}
        new_fields = {f.name: f for f in new_schema.fields_for_version(new_version)}
        for name, old_f in old_fields.items():
            if name not in new_fields and old_f.required:
                issues.append(f"BREAKING: required field {name!r} removed in {new_version}")
        return issues

    @staticmethod
    def assert_compatible(old_schema: VersionedSchema, new_schema: VersionedSchema,
                          old_version: APIVersion, new_version: APIVersion) -> None:
        issues = BreakingChangeDetector.compare(old_schema, new_schema, old_version, new_version)
        if issues:
            raise BreakingChangeError(f"Breaking changes detected: {issues}")


# ---------------------------------------------------------------------------
# Version Registry Admin
# ---------------------------------------------------------------------------

class VersionRegistryAdmin:
    def __init__(self, negotiator: Optional[VersionNegotiator] = None,
                 audit: Optional[VersionAuditChain] = None) -> None:
        self._negotiator = negotiator or VersionNegotiator()
        self._audit = audit or VersionAuditChain()

    def summary(self) -> Dict[str, Any]:
        policies = self._negotiator._policies
        return {
            "versions": {
                v.value: {
                    "status": p.status.value,
                    "released_at": p.released_at,
                    "deprecated_at": p.deprecated_at,
                    "sunset_at": p.sunset_at,
                    "successor": str(p.successor) if p.successor else None,
                }
                for v, p in policies.items()
            },
            "current_version": CURRENT_VERSION.value,
            "supported_count": len(self._negotiator.supported_versions()),
            "deprecated_count": len(self._negotiator.deprecated_versions()),
            "audit_entries": len(self._audit),
            "audit_chain_valid": self._audit.verify_chain(),
        }

    def force_sunset(self, version: APIVersion, reason: str,
                     sunset_at: str, actor: str) -> None:
        self._negotiator.sunset_version(version, reason, sunset_at, actor)
        self._audit.record("force_sunset", version.value, "*",
                           actor=actor, detail={"reason": reason, "sunset_at": sunset_at})

    def endpoint_matrix(self) -> Dict[str, List[str]]:
        return {
            endpoint: sorted(v.value for v in versions)
            for endpoint, versions in VERSIONED_ENDPOINTS.items()
        }

    def schemas(self) -> Dict[str, Any]:
        result = {}
        for name, schema in VERSIONED_SCHEMAS.items():
            result[name] = {
                v.value: {
                    "fields": [f.name for f in schema.fields_for_version(v)],
                    "required": schema.required_fields_for_version(v),
                }
                for v in APIVersion
            }
        return result
