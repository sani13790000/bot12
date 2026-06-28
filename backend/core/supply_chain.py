from __future__ import annotations

import copy
import hashlib
import hmac as _hmac_mod
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class VulnSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class PinStatus(str, Enum):
    PINNED    = "pinned"
    UNPINNED  = "unpinned"
    MISSING   = "missing"
    CONFLICT  = "conflict"


class BuildStatus(str, Enum):
    UNSIGNED    = "unsigned"
    SIGNED      = "signed"
    VERIFIED    = "verified"
    TAMPERED    = "tampered"
    REPRODUCING = "reproducing"


class DriftKind(str, Enum):
    ADDED   = "added"
    REMOVED = "removed"
    VERSION = "version"
    HASH    = "hash"


class ScanPattern(str, Enum):
    EXEC          = "exec("
    EVAL          = "eval("
    COMPILE       = "compile("
    IMPORTLIB     = "importlib.import_module"
    DYNAMIC_ATTR  = "__import__"
    PICKLE_LOAD   = "pickle.loads"
    MARSHAL_LOAD  = "marshal.loads"
    SUBPROCESS    = "subprocess.Popen"
    OS_SYSTEM     = "os.system("
    CTYPES        = "ctypes.CDLL"


UNSAFE_PATTERNS: List[str] = [p.value for p in ScanPattern]

BANNED_PACKAGES: List[str] = [
    "debug-toolbar", "django-debug-toolbar",
    "pdb++", "ipdb", "pudb",
    "test-pypi-upload-example",
    "malicious-package",
]

_SEV_RANK: Dict[VulnSeverity, int] = {
    VulnSeverity.CRITICAL: 4,
    VulnSeverity.HIGH:     3,
    VulnSeverity.MEDIUM:   2,
    VulnSeverity.LOW:      1,
    VulnSeverity.INFO:     0,
}

_DEFAULT_SECRET = b"phase28-supply-chain-secret-v1"


@dataclass
class DepSpec:
    name:        str
    version:     str
    pin_op:      str = "=="
    extras:      List[str] = field(default_factory=list)
    source:      str = "pypi"
    is_dev:      bool = False

    @property
    def pinned(self) -> bool:
        return self.pin_op == "=="

    @property
    def req_string(self) -> str:
        ext = f"[{','.join(self.extras)}]" if self.extras else ""
        return f"{self.name}{ext}{self.pin_op}{self.version}"


@dataclass
class LockfileEntry:
    name:       str
    version:    str
    sha256:     str
    source_url: str = ""
    is_direct:  bool = True

    def verify_hash(self, actual_sha256: str) -> bool:
        return _hmac_mod.compare_digest(self.sha256, actual_sha256)


@dataclass
class VulnRecord:
    cve_id:      str
    package:     str
    affected_versions: List[str]
    severity:    VulnSeverity
    description: str = ""
    fix_version: Optional[str] = None
    published:   float = field(default_factory=time.time)

    def affects(self, version: str) -> bool:
        return version in self.affected_versions


@dataclass
class BuildRecord:
    build_id:     str = field(default_factory=lambda: str(uuid.uuid4()))
    commit_sha:   str = ""
    branch:       str = ""
    python_ver:   str = ""
    lockfile_hash: str = ""
    deps_count:   int = 0
    built_at:     float = field(default_factory=time.time)
    built_by:     str = ""
    artifact_ids: List[str] = field(default_factory=list)
    status:       BuildStatus = BuildStatus.UNSIGNED
    signature:    str = ""
    env_vars_hash: str = ""


@dataclass
class DynamicLoadViolation:
    file_path:   str
    line_no:     int
    pattern:     str
    line_content: str
    severity:    VulnSeverity = VulnSeverity.HIGH


@dataclass
class DriftItem:
    kind:     DriftKind
    package:  str
    expected: str = ""
    actual:   str = ""


class LockfileIntegrity:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stored: Optional[str] = None
        self._entries: Dict[str, LockfileEntry] = {}

    def compute_hash(self, entries: List[LockfileEntry]) -> str:
        canonical = json.dumps(
            sorted(
                [{"n": e.name, "v": e.version, "h": e.sha256} for e in entries],
                key=lambda x: x["n"],
            ),
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def record(self, entries: List[LockfileEntry]) -> str:
        h = self.compute_hash(entries)
        with self._lock:
            self._stored = h
            self._entries = {e.name: e for e in entries}
        return h

    def verify(self, entries: List[LockfileEntry]) -> bool:
        h = self.compute_hash(entries)
        with self._lock:
            if self._stored is None:
                return False
            return _hmac_mod.compare_digest(self._stored, h)

    def get_entry(self, name: str) -> Optional[LockfileEntry]:
        with self._lock:
            return self._entries.get(name)

    @property
    def stored_hash(self) -> Optional[str]:
        with self._lock:
            return self._stored


class UnpinnedDependencyError(Exception):
    pass


class BannedPackageError(Exception):
    pass


class DependencyPinner:
    _REQ_RE = re.compile(
        r"^([A-Za-z0-9_\-]+)"
        r"(\[[^\]]*\])?"
        r"([><=!~^]+)?"
        r"([\w.\-+]+)?"
    )

    def parse_line(self, line: str) -> Optional[DepSpec]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            return None
        m = self._REQ_RE.match(line)
        if not m:
            return None
        name    = m.group(1)
        extras  = [x.strip() for x in m.group(2)[1:-1].split(",")] if m.group(2) else []
        pin_op  = m.group(3) or ""
        version = m.group(4) or ""
        return DepSpec(name=name, version=version, pin_op=pin_op, extras=extras)

    def parse_requirements(self, content: str) -> List[DepSpec]:
        specs = []
        for line in content.splitlines():
            s = self.parse_line(line)
            if s:
                specs.append(s)
        return specs

    def check_pinned(self, specs: List[DepSpec]) -> List[DepSpec]:
        return [s for s in specs if not s.pinned]

    def check_banned(self, specs: List[DepSpec]) -> List[DepSpec]:
        banned_lower = [b.lower() for b in BANNED_PACKAGES]
        return [s for s in specs if s.name.lower() in banned_lower]

    def enforce(self, content: str) -> Tuple[List[DepSpec], List[DepSpec]]:
        specs    = self.parse_requirements(content)
        unpinned = self.check_pinned(specs)
        banned   = self.check_banned(specs)
        return unpinned, banned

    def pin_all(self, specs: List[DepSpec]) -> List[DepSpec]:
        result = []
        for s in specs:
            fixed = copy.copy(s)
            fixed.pin_op = "=="
            result.append(fixed)
        return result

    def generate_requirements(self, specs: List[DepSpec]) -> str:
        return "\n".join(s.req_string for s in specs if s.version)


class VulnerabilityScanner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db:   List[VulnRecord] = []
        self._hooks: List[Any] = []

    def load_db(self, records: List[VulnRecord]) -> None:
        with self._lock:
            self._db = list(records)

    def add_vuln(self, record: VulnRecord) -> None:
        with self._lock:
            self._db.append(record)

    def add_hook(self, fn: Any) -> None:
        self._hooks.append(fn)

    def scan(self, specs: List[DepSpec]) -> List[VulnRecord]:
        found: List[VulnRecord] = []
        with self._lock:
            db_snapshot = list(self._db)
        for spec in specs:
            for vuln in db_snapshot:
                if (vuln.package.lower() == spec.name.lower()
                        and vuln.affects(spec.version)):
                    found.append(vuln)
        found.sort(key=lambda v: _SEV_RANK[v.severity], reverse=True)
        for fn in self._hooks:
            try:
                fn(found)
            except Exception:
                pass
        return found

    def has_critical(self, specs: List[DepSpec]) -> bool:
        vulns = self.scan(specs)
        return any(v.severity == VulnSeverity.CRITICAL for v in vulns)

    def summary(self, specs: List[DepSpec]) -> Dict[str, int]:
        vulns = self.scan(specs)
        result: Dict[str, int] = {s.value: 0 for s in VulnSeverity}
        for v in vulns:
            result[v.severity.value] += 1
        return result


class DriftDetector:
    def detect(
        self,
        lockfile: Dict[str, str],
        current:  Dict[str, str],
    ) -> List[DriftItem]:
        items: List[DriftItem] = []
        lock_lower  = {k.lower(): v for k, v in lockfile.items()}
        curr_lower  = {k.lower(): v for k, v in current.items()}
        for name, ver in lock_lower.items():
            if name not in curr_lower:
                items.append(DriftItem(DriftKind.REMOVED, name, expected=ver))
            elif curr_lower[name] != ver:
                items.append(DriftItem(DriftKind.VERSION, name,
                                       expected=ver, actual=curr_lower[name]))
        for name, ver in curr_lower.items():
            if name not in lock_lower:
                items.append(DriftItem(DriftKind.ADDED, name, actual=ver))
        return items

    def detect_hash_drift(
        self,
        lockfile_entries: List[LockfileEntry],
        actual_hashes: Dict[str, str],
    ) -> List[DriftItem]:
        items: List[DriftItem] = []
        for entry in lockfile_entries:
            actual = actual_hashes.get(entry.name.lower(), "")
            if actual and not _hmac_mod.compare_digest(entry.sha256, actual):
                items.append(DriftItem(
                    DriftKind.HASH, entry.name,
                    expected=entry.sha256, actual=actual,
                ))
        return items

    def is_clean(self, drift: List[DriftItem]) -> bool:
        return len(drift) == 0


class DynamicLoadScanner:
    def __init__(self, patterns: Optional[List[str]] = None) -> None:
        self._patterns = patterns or UNSAFE_PATTERNS

    def scan_source(self, source: str, file_path: str = "<string>") -> List[DynamicLoadViolation]:
        violations: List[DynamicLoadViolation] = []
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in self._patterns:
                if pat in line:
                    sev = (VulnSeverity.CRITICAL
                           if pat in ("exec(", "eval(", "pickle.loads", "marshal.loads")
                           else VulnSeverity.HIGH)
                    violations.append(DynamicLoadViolation(
                        file_path=file_path,
                        line_no=i,
                        pattern=pat,
                        line_content=stripped[:200],
                        severity=sev,
                    ))
        return violations

    def scan_files(self, sources: Dict[str, str]) -> List[DynamicLoadViolation]:
        all_violations: List[DynamicLoadViolation] = []
        for path, src in sources.items():
            all_violations.extend(self.scan_source(src, path))
        return all_violations

    def has_critical_violation(self, sources: Dict[str, str]) -> bool:
        viols = self.scan_files(sources)
        return any(v.severity == VulnSeverity.CRITICAL for v in viols)

    def summary(self, sources: Dict[str, str]) -> Dict[str, int]:
        viols = self.scan_files(sources)
        result: Dict[str, int] = {s.value: 0 for s in VulnSeverity}
        for v in viols:
            result[v.severity.value] += 1
        return result


class BuildSignatureError(Exception):
    pass


class BuildSigner:
    def __init__(self, secret: bytes = _DEFAULT_SECRET) -> None:
        self._secret = secret if isinstance(secret, bytes) else secret.encode()

    def _canonical(self, record: BuildRecord) -> str:
        return json.dumps({
            "build_id":     record.build_id,
            "commit_sha":   record.commit_sha,
            "branch":       record.branch,
            "python_ver":   record.python_ver,
            "lockfile_hash": record.lockfile_hash,
            "deps_count":   record.deps_count,
            "built_at":     record.built_at,
            "built_by":     record.built_by,
            "artifact_ids": sorted(record.artifact_ids),
            "env_vars_hash": record.env_vars_hash,
        }, sort_keys=True, separators=(",", ":"))

    def sign(self, record: BuildRecord) -> BuildRecord:
        canonical = self._canonical(record)
        sig = _hmac_mod.new(self._secret, canonical.encode(), "sha256").hexdigest()
        record.signature = sig
        record.status    = BuildStatus.SIGNED
        return record

    def verify(self, record: BuildRecord) -> bool:
        if not record.signature:
            return False
        canonical = self._canonical(record)
        expected = _hmac_mod.new(self._secret, canonical.encode(), "sha256").hexdigest()
        return _hmac_mod.compare_digest(expected, record.signature)

    def verify_or_raise(self, record: BuildRecord) -> None:
        if not self.verify(record):
            raise BuildSignatureError(f"Build {record.build_id} signature invalid")


class BuildReproducer:
    def __init__(self, signer: Optional[BuildSigner] = None) -> None:
        self._signer   = signer or BuildSigner()
        self._lock     = threading.Lock()
        self._builds:  Dict[str, BuildRecord] = {}

    def _hash_env(self, env: Dict[str, str]) -> str:
        canonical = json.dumps(
            {k: v for k, v in sorted(env.items())},
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def create_build(
        self,
        commit_sha: str,
        branch:     str,
        python_ver: str,
        lockfile_entries: List[LockfileEntry],
        artifact_ids: List[str],
        built_by:   str,
        env:        Optional[Dict[str, str]] = None,
    ) -> BuildRecord:
        lf_hash = hashlib.sha256(
            json.dumps(
                sorted([{"n": e.name, "v": e.version, "h": e.sha256}
                        for e in lockfile_entries], key=lambda x: x["n"]),
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        record = BuildRecord(
            commit_sha=commit_sha,
            branch=branch,
            python_ver=python_ver,
            lockfile_hash=lf_hash,
            deps_count=len(lockfile_entries),
            built_by=built_by,
            artifact_ids=list(artifact_ids),
            env_vars_hash=self._hash_env(env or {}),
        )
        self._signer.sign(record)
        record.status = BuildStatus.VERIFIED
        with self._lock:
            self._builds[record.build_id] = record
        return record

    def verify_build(self, build_id: str) -> Tuple[bool, str]:
        with self._lock:
            record = self._builds.get(build_id)
        if record is None:
            return False, "build_not_found"
        if not self._signer.verify(record):
            return False, "signature_invalid"
        return True, "ok"

    def is_reproducible(
        self,
        build_id: str,
        lockfile_entries: List[LockfileEntry],
        commit_sha: str,
        python_ver: str,
    ) -> bool:
        with self._lock:
            record = self._builds.get(build_id)
        if record is None:
            return False
        expected_hash = hashlib.sha256(
            json.dumps(
                sorted([{"n": e.name, "v": e.version, "h": e.sha256}
                        for e in lockfile_entries], key=lambda x: x["n"]),
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return (
            _hmac_mod.compare_digest(record.lockfile_hash, expected_hash)
            and _hmac_mod.compare_digest(record.commit_sha, commit_sha)
            and record.python_ver == python_ver
        )

    def get(self, build_id: str) -> Optional[BuildRecord]:
        with self._lock:
            return self._builds.get(build_id)

    def list_builds(self) -> List[BuildRecord]:
        with self._lock:
            return sorted(self._builds.values(), key=lambda b: b.built_at, reverse=True)


@dataclass
class _AuditEntry:
    entry_id:   str
    seq:        int
    action:     str
    actor:      str
    detail:     Dict[str, Any]
    ts:         float
    chain_hash: str
    prev_hash:  str


class SupplyChainAuditChain:
    _GENESIS_CONST = "GENESIS:SUPPLY:CHAIN:V28"

    def __init__(self, secret: bytes = _DEFAULT_SECRET) -> None:
        self._secret = secret if isinstance(secret, bytes) else secret.encode()
        self._lock   = threading.Lock()
        self._records: deque = deque(maxlen=50_000)
        self._seq    = 1
        genesis_sig  = _hmac_mod.new(self._secret, self._GENESIS_CONST.encode(), "sha256").hexdigest()
        self._prev_hash: str = genesis_sig
        self._genesis:   str = genesis_sig

    def _make_hash(self, prev: str, payload: str) -> str:
        return _hmac_mod.new(self._secret, (prev + ":" + payload).encode(), "sha256").hexdigest()

    def record(self, action: str, actor: str, detail: Optional[Dict] = None) -> _AuditEntry:
        with self._lock:
            seq = self._seq
            self._seq += 1
            ts  = time.time()
            d   = detail or {}
            canonical = json.dumps({"seq": seq, "action": action, "actor": actor, "detail": d, "ts": ts}, sort_keys=True, separators=(",", ":"))
            chain_hash = self._make_hash(self._prev_hash, canonical)
            entry = _AuditEntry(
                entry_id=str(uuid.uuid4()), seq=seq, action=action, actor=actor,
                detail=d, ts=ts, chain_hash=chain_hash, prev_hash=self._prev_hash,
            )
            self._prev_hash = chain_hash
            self._records.append(entry)
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            recs = list(self._records)
        prev = self._genesis
        for r in recs:
            canonical = json.dumps({"seq": r.seq, "action": r.action, "actor": r.actor, "detail": r.detail, "ts": r.ts}, sort_keys=True, separators=(",", ":"))
            expected = self._make_hash(prev, canonical)
            if not _hmac_mod.compare_digest(expected, r.chain_hash):
                return False
            prev = r.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            recs = list(self._records)
        broken: List[int] = []
        prev = self._genesis
        for r in recs:
            canonical = json.dumps({"seq": r.seq, "action": r.action, "actor": r.actor, "detail": r.detail, "ts": r.ts}, sort_keys=True, separators=(",", ":"))
            expected = self._make_hash(prev, canonical)
            if not _hmac_mod.compare_digest(expected, r.chain_hash):
                broken.append(r.seq)
            prev = r.chain_hash
        return broken

    def query(self, action: Optional[str] = None, actor: Optional[str] = None, limit: int = 100) -> List[_AuditEntry]:
        with self._lock:
            recs = list(self._records)
        recs.reverse()
        result = []
        if limit <= 0:
            return result
        for r in recs:
            if action and r.action != action:
                continue
            if actor and r.actor != actor:
                continue
            result.append(r)
            if len(result) >= limit:
                break
        return result

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._records)


class SupplyChainAdmin:
    def __init__(self, pinner, scanner, drift, dyn, builds, audit) -> None:
        self._pinner  = pinner
        self._scanner = scanner
        self._drift   = drift
        self._dyn     = dyn
        self._builds  = builds
        self._audit   = audit

    def full_scan(self, req_content, lockfile_entries, current_env, source_files, actor="admin"):
        specs    = self._pinner.parse_requirements(req_content)
        unpinned, banned = self._pinner.enforce(req_content)
        vulns    = self._scanner.scan(specs)
        drift    = self._drift.detect({e.name: e.version for e in lockfile_entries}, current_env)
        dyn_viols = self._dyn.scan_files(source_files)
        report = {
            "total_deps":         len(specs),
            "unpinned_count":     len(unpinned),
            "banned_count":       len(banned),
            "vuln_count":         len(vulns),
            "critical_vulns":     sum(1 for v in vulns if v.severity == VulnSeverity.CRITICAL),
            "drift_count":        len(drift),
            "dynamic_load_count": len(dyn_viols),
            "pass":               (len(unpinned) == 0 and len(banned) == 0 and not any(v.severity == VulnSeverity.CRITICAL for v in vulns) and len(dyn_viols) == 0),
        }
        self._audit.record("full_scan", actor, {"report": report})
        return report

    def generate_sbom(self, specs, lockfile_entries, build_id="", actor="admin"):
        entry_map = {e.name.lower(): e for e in lockfile_entries}
        components = []
        for s in specs:
            entry = entry_map.get(s.name.lower())
            components.append({"name": s.name, "version": s.version, "pinned": s.pinned, "source": s.source, "sha256": entry.sha256 if entry else "", "is_dev": s.is_dev})
        sbom = {"sbom_version": "1.0", "build_id": build_id, "generated_at": time.time(), "total": len(components), "components": components}
        self._audit.record("sbom_generated", actor, {"build_id": build_id, "count": len(components)})
        return sbom

    def policy_gate(self, req_content, vuln_records, source_files, block_on_critical_vuln=True, block_on_unpinned=True, block_on_dynamic_load=True, block_on_banned=True, actor="ci"):
        reasons = []
        specs    = self._pinner.parse_requirements(req_content)
        unpinned, banned = self._pinner.enforce(req_content)
        self._scanner.load_db(vuln_records)
        vulns     = self._scanner.scan(specs)
        dyn_viols = self._dyn.scan_files(source_files)
        if block_on_unpinned and unpinned:
            reasons.append(f"unpinned_deps:{[s.name for s in unpinned]}")
        if block_on_banned and banned:
            reasons.append(f"banned_packages:{[s.name for s in banned]}")
        if block_on_critical_vuln and any(v.severity == VulnSeverity.CRITICAL for v in vulns):
            reasons.append(f"critical_vulns:{[v.cve_id for v in vulns if v.severity == VulnSeverity.CRITICAL]}")
        if block_on_dynamic_load and dyn_viols:
            reasons.append(f"dynamic_load:{[(v.file_path, v.line_no) for v in dyn_viols]}")
        passed = len(reasons) == 0
        self._audit.record("policy_gate", actor, {"passed": passed, "reasons": reasons})
        return passed, reasons


class SupplyChainSystem:
    def __init__(self, secret: bytes = _DEFAULT_SECRET) -> None:
        self.pinner   = DependencyPinner()
        self.scanner  = VulnerabilityScanner()
        self.drift    = DriftDetector()
        self.dyn      = DynamicLoadScanner()
        self.lockfile = LockfileIntegrity()
        self.signer   = BuildSigner(secret)
        self.builds   = BuildReproducer(self.signer)
        self.audit    = SupplyChainAuditChain(secret)
        self.admin    = SupplyChainAdmin(self.pinner, self.scanner, self.drift, self.dyn, self.builds, self.audit)

    def parse_requirements(self, content: str):
        return self.pinner.parse_requirements(content)

    def record_lockfile(self, entries):
        return self.lockfile.record(entries)

    def create_build(self, **kwargs):
        return self.builds.create_build(**kwargs)
