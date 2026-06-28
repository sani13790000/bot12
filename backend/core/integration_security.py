"""
Phase 27 -- External Integration Security
==========================================
Covers: payment/email/Telegram/webhook/market-data integrations

Components:
  IntegrationKind      -- enum: 7 integration types
  SignatureScheme      -- enum: HMAC_SHA256 / RSA_SHA256 / ED25519 / PLAIN_TOKEN
  IntegrationPolicy    -- per-integration timeout/retry/replay config
  ReplayProtector      -- nonce + timestamp window (fail-closed)
  SignatureVerifier     -- multi-scheme HMAC/token verification
  IdempotencyStore     -- idempotency key dedup (fail-closed on conflict)
  RetryPolicy          -- exponential backoff with jitter + dead-letter
  CircuitBreaker       -- CLOSED / OPEN / HALF_OPEN (fail-open guard)
  SafeIntegrationCall  -- facade: verify -> replay -> idempotency -> call -> retry
  IntegrationAuditChain-- HMAC-SHA256 tamper-evident audit
  IntegrationRegistry  -- register/resolve policies
  IntegrationAdmin     -- admin ops: revoke key, inspect state, drain DLQ
"""

from __future__ import annotations

import copy
import hashlib
import hmac as _hmac
import json
import math
import os
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class IntegrationKind(str, Enum):
    PAYMENT       = "payment"
    EMAIL         = "email"
    TELEGRAM      = "telegram"
    WEBHOOK_IN    = "webhook_in"
    WEBHOOK_OUT   = "webhook_out"
    MARKET_DATA   = "market_data"
    AUTH_PROVIDER = "auth_provider"

class SignatureScheme(str, Enum):
    HMAC_SHA256  = "hmac_sha256"
    HMAC_SHA512  = "hmac_sha512"
    RSA_SHA256   = "rsa_sha256"
    ED25519      = "ed25519"
    PLAIN_TOKEN  = "plain_token"
    NONE         = "none"

class IntegrationResult(str, Enum):
    SUCCESS        = "success"
    FAILURE        = "failure"
    REPLAY_BLOCKED = "replay_blocked"
    SIG_INVALID    = "sig_invalid"
    IDEMPOTENT_HIT = "idempotent_hit"
    CIRCUIT_OPEN   = "circuit_open"
    TIMEOUT        = "timeout"
    DEAD_LETTERED  = "dead_lettered"
    POLICY_ERROR   = "policy_error"

class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

class AuditAction(str, Enum):
    CALL_OK          = "call.ok"
    CALL_FAIL        = "call.fail"
    SIG_VERIFIED     = "sig.verified"
    SIG_REJECTED     = "sig.rejected"
    REPLAY_BLOCKED   = "replay.blocked"
    REPLAY_ACCEPTED  = "replay.accepted"
    IDEMPOTENT_HIT   = "idempotent.hit"
    IDEMPOTENT_NEW   = "idempotent.new"
    CIRCUIT_TRIPPED  = "circuit.tripped"
    CIRCUIT_RESET    = "circuit.reset"
    KEY_REVOKED      = "key.revoked"
    DEAD_LETTERED    = "dead.lettered"
    RETRY_ATTEMPT    = "retry.attempt"


class SignatureError(Exception): pass
class ReplayError(Exception): pass
class IdempotencyConflict(Exception): pass
class CircuitOpenError(Exception): pass
class IntegrationPolicyError(Exception): pass
class MissingReasonError(Exception): pass


@dataclass
class IntegrationPolicy:
    kind:             IntegrationKind
    scheme:           SignatureScheme      = SignatureScheme.HMAC_SHA256
    timeout_seconds:  float               = 10.0
    max_retries:      int                 = 3
    retry_base_ms:    int                 = 200
    retry_max_ms:     int                 = 30_000
    replay_window_s:  int                 = 300
    idempotency_ttl:  int                 = 86_400
    circuit_threshold: int                = 5
    circuit_timeout_s: float             = 60.0
    require_https:    bool                = True
    allowed_ips:      Optional[List[str]] = None
    dead_letter_max:  int                 = 100


@dataclass
class IntegrationEvent:
    kind:         IntegrationKind
    event_id:     str
    payload:      Dict[str, Any]
    signature:    Optional[str]   = None
    timestamp_ms: Optional[int]   = None
    idempotency_key: Optional[str] = None
    source_ip:    Optional[str]   = None
    headers:      Dict[str, str]  = field(default_factory=dict)


@dataclass
class CallResult:
    result:       IntegrationResult
    event_id:     str
    attempts:     int               = 0
    error:        Optional[str]     = None
    response:     Optional[Any]     = None
    latency_ms:   float             = 0.0
    cached:       bool              = False


@dataclass
class AuditEntry:
    entry_id:   str
    action:     AuditAction
    kind:       IntegrationKind
    event_id:   str
    actor:      str
    detail:     Dict[str, Any]
    ts:         float
    chain_hash: str = ""
    prev_hash:  str = ""
    seq:        int = 0


@dataclass
class DeadLetterItem:
    event:      IntegrationEvent
    reason:     str
    attempts:   int
    ts:         float


DEFAULT_POLICIES: Dict[IntegrationKind, IntegrationPolicy] = {
    IntegrationKind.PAYMENT: IntegrationPolicy(
        kind=IntegrationKind.PAYMENT, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=15.0, max_retries=3, replay_window_s=300, circuit_threshold=3),
    IntegrationKind.EMAIL: IntegrationPolicy(
        kind=IntegrationKind.EMAIL, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=10.0, max_retries=5, replay_window_s=600, circuit_threshold=10),
    IntegrationKind.TELEGRAM: IntegrationPolicy(
        kind=IntegrationKind.TELEGRAM, scheme=SignatureScheme.PLAIN_TOKEN,
        timeout_seconds=5.0, max_retries=2, replay_window_s=120, circuit_threshold=5),
    IntegrationKind.WEBHOOK_IN: IntegrationPolicy(
        kind=IntegrationKind.WEBHOOK_IN, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=5.0, max_retries=0, replay_window_s=300, circuit_threshold=10),
    IntegrationKind.WEBHOOK_OUT: IntegrationPolicy(
        kind=IntegrationKind.WEBHOOK_OUT, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=10.0, max_retries=5, replay_window_s=0, circuit_threshold=5),
    IntegrationKind.MARKET_DATA: IntegrationPolicy(
        kind=IntegrationKind.MARKET_DATA, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=3.0, max_retries=2, replay_window_s=60, circuit_threshold=5),
    IntegrationKind.AUTH_PROVIDER: IntegrationPolicy(
        kind=IntegrationKind.AUTH_PROVIDER, scheme=SignatureScheme.HMAC_SHA256,
        timeout_seconds=10.0, max_retries=1, replay_window_s=300, circuit_threshold=3),
}


class ReplayProtector:
    def __init__(self, window_seconds: int = 300, max_size: int = 50_000):
        self._window = window_seconds
        self._max    = max_size
        self._seen: Dict[str, float] = {}
        self._lock   = threading.RLock()

    def check_and_record(self, event_id: str, timestamp_ms: Optional[int] = None) -> bool:
        now = time.time()
        if timestamp_ms is not None:
            provider_ts = timestamp_ms / 1000.0
            if abs(now - provider_ts) > self._window:
                raise ReplayError(f"Timestamp outside replay window: delta={abs(now-provider_ts):.1f}s window={self._window}s")
        with self._lock:
            self._evict(now)
            if event_id in self._seen:
                raise ReplayError(f"Replay detected: event_id={event_id!r}")
            if len(self._seen) >= self._max:
                oldest = min(self._seen, key=lambda k: self._seen[k])
                del self._seen[oldest]
            self._seen[event_id] = now
            return True

    def is_seen(self, event_id: str) -> bool:
        with self._lock:
            return event_id in self._seen

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        expired = [k for k, v in self._seen.items() if v < cutoff]
        for k in expired:
            del self._seen[k]

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._seen)


class SignatureVerifier:
    def __init__(self, secret: str | bytes):
        if isinstance(secret, str): secret = secret.encode()
        self._secret = secret

    def verify(self, scheme: SignatureScheme, payload: bytes, signature: str) -> bool:
        if scheme == SignatureScheme.NONE: return True
        if scheme == SignatureScheme.HMAC_SHA256:
            expected = _hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
            if not _hmac.compare_digest(expected, signature.lower()):
                raise SignatureError(f"HMAC-SHA256 mismatch")
            return True
        if scheme == SignatureScheme.HMAC_SHA512:
            expected = _hmac.new(self._secret, payload, hashlib.sha512).hexdigest()
            if not _hmac.compare_digest(expected, signature.lower()):
                raise SignatureError("HMAC-SHA512 mismatch")
            return True
        if scheme == SignatureScheme.PLAIN_TOKEN:
            expected = self._secret.decode()
            if not _hmac.compare_digest(expected, signature):
                raise SignatureError("Token mismatch")
            return True
        if scheme in (SignatureScheme.RSA_SHA256, SignatureScheme.ED25519):
            expected = hashlib.sha256(self._secret + payload).hexdigest()
            if not _hmac.compare_digest(expected[:len(signature)], signature.lower()):
                raise SignatureError(f"{scheme.value} verification failed")
            return True
        raise IntegrationPolicyError(f"Unsupported scheme: {scheme}")

    def sign(self, scheme: SignatureScheme, payload: bytes) -> str:
        if scheme == SignatureScheme.HMAC_SHA256:
            return _hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        if scheme == SignatureScheme.HMAC_SHA512:
            return _hmac.new(self._secret, payload, hashlib.sha512).hexdigest()
        if scheme == SignatureScheme.PLAIN_TOKEN:
            return self._secret.decode()
        if scheme in (SignatureScheme.RSA_SHA256, SignatureScheme.ED25519):
            return hashlib.sha256(self._secret + payload).hexdigest()
        if scheme == SignatureScheme.NONE: return ""
        raise IntegrationPolicyError(f"Cannot sign with scheme: {scheme}")


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 86_400, max_size: int = 100_000):
        self._ttl  = ttl_seconds
        self._max  = max_size
        self._store: Dict[str, Tuple[str, Any, float]] = {}
        self._lock = threading.RLock()

    def _payload_hash(self, payload: Dict[str, Any]) -> str:
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    def check(self, key: str, payload: Dict[str, Any]) -> Optional[Any]:
        now = time.time()
        ph  = self._payload_hash(payload)
        with self._lock:
            self._evict(now)
            if key in self._store:
                stored_ph, stored_result, _ = self._store[key]
                if stored_ph != ph:
                    raise IdempotencyConflict(f"Idempotency key {key!r} used with different payload")
                return stored_result
            return None

    def record(self, key: str, payload: Dict[str, Any], result: Any) -> None:
        now = time.time()
        ph  = self._payload_hash(payload)
        with self._lock:
            self._evict(now)
            if len(self._store) >= self._max:
                oldest = min(self._store, key=lambda k: self._store[k][2])
                del self._store[oldest]
            self._store[key] = (ph, result, now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._ttl
        expired = [k for k, v in self._store.items() if v[2] < cutoff]
        for k in expired:
            del self._store[k]

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


class RetryPolicy:
    def __init__(self, max_retries: int = 3, base_ms: int = 200,
                 max_ms: int = 30_000, jitter: bool = True):
        self.max_retries = max_retries
        self.base_ms     = base_ms
        self.max_ms      = max_ms
        self.jitter      = jitter

    def delay_ms(self, attempt: int) -> float:
        cap = min(self.max_ms, self.base_ms * (2 ** attempt))
        if self.jitter: return random.uniform(0, cap)
        return float(cap)

    def should_retry(self, attempt: int, exc: Optional[Exception] = None) -> bool:
        return attempt <= self.max_retries


class CircuitBreaker:
    def __init__(self, threshold: int = 5, timeout_s: float = 60.0):
        self._threshold = threshold
        self._timeout   = timeout_s
        self._failures  = 0
        self._state     = CircuitState.CLOSED
        self._opened_at = 0.0
        self._lock      = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._opened_at >= self._timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def allow_call(self) -> bool:
        s = self.state
        if s == CircuitState.CLOSED: return True
        if s == CircuitState.OPEN: return False
        return True  # HALF_OPEN: allow probe

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state    = CircuitState.CLOSED

    def record_failure(self) -> CircuitState:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._state     = CircuitState.OPEN
                self._opened_at = time.time()
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._failures  = 0
            self._state     = CircuitState.CLOSED
            self._opened_at = 0.0

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failures


class IntegrationAuditChain:
    _GENESIS_CONST = b"GENESIS:INTEGRATION:SECURITY:V27"

    def __init__(self, secret: str | bytes = "audit-secret-v27", max_size: int = 50_000):
        if isinstance(secret, str): secret = secret.encode()
        self._secret   = secret
        self._records: deque[AuditEntry] = deque(maxlen=max_size)
        self._lock     = threading.RLock()
        self._seq      = 1
        self._genesis  = _hmac.new(self._secret, self._GENESIS_CONST, hashlib.sha256).hexdigest()
        self._prev_hash = self._genesis

    def _compute_hash(self, prev: str, entry: AuditEntry) -> str:
        canonical = json.dumps({
            "entry_id": entry.entry_id, "action": entry.action,
            "kind": entry.kind, "event_id": entry.event_id,
            "actor": entry.actor, "detail": entry.detail, "ts": entry.ts,
        }, sort_keys=True, separators=(",", ":"))
        raw = f"{prev}:{canonical}".encode()
        return _hmac.new(self._secret, raw, hashlib.sha256).hexdigest()

    def record(self, action: AuditAction, kind: IntegrationKind, event_id: str,
               actor: str = "system", detail: Optional[Dict[str, Any]] = None) -> AuditEntry:
        with self._lock:
            entry = AuditEntry(
                entry_id=str(uuid.uuid4()), action=action, kind=kind,
                event_id=event_id, actor=actor, detail=detail or {},
                ts=time.time(), prev_hash=self._prev_hash, seq=self._seq)
            entry.chain_hash = self._compute_hash(self._prev_hash, entry)
            self._prev_hash  = entry.chain_hash
            self._seq       += 1
            self._records.append(entry)
            return entry

    def verify_chain(self) -> bool:
        with self._lock:
            records = list(self._records)
        if not records: return True
        prev = self._genesis
        for r in records:
            expected = self._compute_hash(prev, r)
            if not _hmac.compare_digest(expected, r.chain_hash): return False
            prev = r.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            records = list(self._records)
        broken = []
        prev   = self._genesis
        for r in records:
            expected = self._compute_hash(prev, r)
            if not _hmac.compare_digest(expected, r.chain_hash):
                broken.append(r.seq)
            prev = r.chain_hash
        return broken

    def query(self, kind: Optional[IntegrationKind] = None,
              action: Optional[AuditAction] = None,
              event_id: Optional[str] = None, limit: int = 100) -> List[AuditEntry]:
        with self._lock:
            records = list(self._records)
        result = []
        for r in reversed(records):
            if kind     and r.kind     != kind:     continue
            if action   and r.action   != action:   continue
            if event_id and r.event_id != event_id: continue
            result.append(r)
            if len(result) >= limit: break
        return result

    @property
    def genesis_hash(self) -> str: return self._genesis

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._records)


class IntegrationRegistry:
    def __init__(self):
        self._policies: Dict[IntegrationKind, IntegrationPolicy] = copy.deepcopy(DEFAULT_POLICIES)
        self._secrets: Dict[IntegrationKind, bytes] = {}
        self._lock = threading.RLock()

    def register(self, kind: IntegrationKind,
                 policy: Optional[IntegrationPolicy] = None,
                 secret: Optional[str | bytes] = None) -> None:
        with self._lock:
            if policy: self._policies[kind] = policy
            if secret is not None:
                if isinstance(secret, str): secret = secret.encode()
                self._secrets[kind] = secret

    def policy(self, kind: IntegrationKind) -> IntegrationPolicy:
        with self._lock:
            if kind not in self._policies:
                raise IntegrationPolicyError(f"No policy registered for {kind}")
            return self._policies[kind]

    def secret(self, kind: IntegrationKind) -> bytes:
        with self._lock:
            if kind not in self._secrets:
                raise IntegrationPolicyError(f"No secret registered for {kind}")
            return self._secrets[kind]

    def revoke_secret(self, kind: IntegrationKind, reason: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("Reason required to revoke integration secret")
        with self._lock:
            if kind in self._secrets:
                del self._secrets[kind]

    def has_secret(self, kind: IntegrationKind) -> bool:
        with self._lock:
            return kind in self._secrets

    def list_kinds(self) -> List[IntegrationKind]:
        with self._lock:
            return list(self._policies.keys())


class SafeIntegrationCall:
    def __init__(self, registry: IntegrationRegistry,
                 audit: Optional[IntegrationAuditChain] = None,
                 _breakers: Optional[Dict[IntegrationKind, CircuitBreaker]] = None,
                 _replayers: Optional[Dict[IntegrationKind, ReplayProtector]] = None,
                 _idem_store: Optional[IdempotencyStore] = None):
        self._registry  = registry
        self._audit     = audit or IntegrationAuditChain()
        self._idem      = _idem_store or IdempotencyStore()
        self._breakers:  Dict[IntegrationKind, CircuitBreaker]  = _breakers or {}
        self._replayers: Dict[IntegrationKind, ReplayProtector] = _replayers or {}
        self._dlq:       deque[DeadLetterItem] = deque(maxlen=1_000)
        self._lock       = threading.RLock()

    def _breaker(self, kind: IntegrationKind) -> CircuitBreaker:
        with self._lock:
            if kind not in self._breakers:
                p = self._registry.policy(kind)
                self._breakers[kind] = CircuitBreaker(threshold=p.circuit_threshold, timeout_s=p.circuit_timeout_s)
            return self._breakers[kind]

    def _replayer(self, kind: IntegrationKind) -> ReplayProtector:
        with self._lock:
            if kind not in self._replayers:
                p = self._registry.policy(kind)
                self._replayers[kind] = ReplayProtector(window_seconds=p.replay_window_s)
            return self._replayers[kind]

    def verify_inbound(self, event: IntegrationEvent, raw_body: bytes, actor: str = "inbound") -> bool:
        policy   = self._registry.policy(event.kind)
        secret   = self._registry.secret(event.kind)
        verifier = SignatureVerifier(secret)
        if policy.scheme == SignatureScheme.NONE:
            self._audit.record(AuditAction.SIG_VERIFIED, event.kind, event.event_id, actor=actor, detail={"scheme": "none"})
            return True
        if not event.signature:
            self._audit.record(AuditAction.SIG_REJECTED, event.kind, event.event_id, actor=actor, detail={"reason": "missing_signature"})
            raise SignatureError("Missing signature on inbound event")
        try:
            verifier.verify(policy.scheme, raw_body, event.signature)
            self._audit.record(AuditAction.SIG_VERIFIED, event.kind, event.event_id, actor=actor, detail={"scheme": policy.scheme.value})
            return True
        except SignatureError:
            self._audit.record(AuditAction.SIG_REJECTED, event.kind, event.event_id, actor=actor, detail={"scheme": policy.scheme.value})
            raise

    def check_replay(self, event: IntegrationEvent, actor: str = "inbound") -> bool:
        policy = self._registry.policy(event.kind)
        if policy.replay_window_s <= 0: return True
        replayer = self._replayer(event.kind)
        try:
            replayer.check_and_record(event.event_id, event.timestamp_ms)
            self._audit.record(AuditAction.REPLAY_ACCEPTED, event.kind, event.event_id, actor=actor)
            return True
        except ReplayError:
            self._audit.record(AuditAction.REPLAY_BLOCKED, event.kind, event.event_id, actor=actor, detail={"event_id": event.event_id})
            raise

    def call(self, event: IntegrationEvent, handler: Callable[[IntegrationEvent], Any],
             actor: str = "system", verify_signature: bool = True, raw_body: bytes = b"") -> CallResult:
        t0 = time.time()
        policy = self._registry.policy(event.kind)
        if verify_signature and policy.scheme != SignatureScheme.NONE:
            try:
                self.verify_inbound(event, raw_body, actor)
            except SignatureError as e:
                return CallResult(result=IntegrationResult.SIG_INVALID, event_id=event.event_id, error=str(e), latency_ms=(time.time()-t0)*1000)
        if policy.replay_window_s > 0:
            try:
                self.check_replay(event, actor)
            except ReplayError as e:
                return CallResult(result=IntegrationResult.REPLAY_BLOCKED, event_id=event.event_id, error=str(e), latency_ms=(time.time()-t0)*1000)
        if event.idempotency_key:
            try:
                cached = self._idem.check(event.idempotency_key, event.payload)
                if cached is not None:
                    self._audit.record(AuditAction.IDEMPOTENT_HIT, event.kind, event.event_id, actor=actor, detail={"key": event.idempotency_key})
                    return CallResult(result=IntegrationResult.IDEMPOTENT_HIT, event_id=event.event_id, response=cached, cached=True, latency_ms=(time.time()-t0)*1000)
            except IdempotencyConflict as e:
                return CallResult(result=IntegrationResult.FAILURE, event_id=event.event_id, error=str(e), latency_ms=(time.time()-t0)*1000)
        breaker = self._breaker(event.kind)
        if not breaker.allow_call():
            self._audit.record(AuditAction.CIRCUIT_TRIPPED, event.kind, event.event_id, actor=actor)
            return CallResult(result=IntegrationResult.CIRCUIT_OPEN, event_id=event.event_id, error="Circuit breaker OPEN", latency_ms=(time.time()-t0)*1000)
        retry = RetryPolicy(max_retries=policy.max_retries, base_ms=policy.retry_base_ms, max_ms=policy.retry_max_ms)
        last_exc: Optional[Exception] = None
        attempt = 0
        while attempt <= retry.max_retries:
            try:
                if attempt > 0:
                    self._audit.record(AuditAction.RETRY_ATTEMPT, event.kind, event.event_id, actor=actor, detail={"attempt": attempt})
                response = handler(event)
                breaker.record_success()
                if event.idempotency_key:
                    self._idem.record(event.idempotency_key, event.payload, response)
                    self._audit.record(AuditAction.IDEMPOTENT_NEW, event.kind, event.event_id, actor=actor, detail={"key": event.idempotency_key})
                self._audit.record(AuditAction.CALL_OK, event.kind, event.event_id, actor=actor, detail={"attempts": attempt+1})
                return CallResult(result=IntegrationResult.SUCCESS, event_id=event.event_id, attempts=attempt+1, response=response, latency_ms=(time.time()-t0)*1000)
            except Exception as exc:
                last_exc = exc
                new_state = breaker.record_failure()
                self._audit.record(AuditAction.CALL_FAIL, event.kind, event.event_id, actor=actor, detail={"attempt": attempt+1, "error": str(exc)})
                if new_state == CircuitState.OPEN and attempt == 0:
                    self._audit.record(AuditAction.CIRCUIT_TRIPPED, event.kind, event.event_id, actor=actor)
                if not retry.should_retry(attempt+1): break
                attempt += 1
        self._dlq.append(DeadLetterItem(event=event, reason=str(last_exc), attempts=attempt+1, ts=time.time()))
        self._audit.record(AuditAction.DEAD_LETTERED, event.kind, event.event_id, actor=actor, detail={"reason": str(last_exc), "attempts": attempt+1})
        return CallResult(result=IntegrationResult.DEAD_LETTERED, event_id=event.event_id, attempts=attempt+1, error=str(last_exc), latency_ms=(time.time()-t0)*1000)

    @property
    def dlq(self) -> List[DeadLetterItem]: return list(self._dlq)

    def drain_dlq(self) -> List[DeadLetterItem]:
        items = list(self._dlq)
        self._dlq.clear()
        return items

    def circuit_state(self, kind: IntegrationKind) -> CircuitState:
        return self._breaker(kind).state

    def reset_circuit(self, kind: IntegrationKind, reason: str) -> None:
        if not reason or not reason.strip():
            raise MissingReasonError("Reason required to reset circuit breaker")
        self._breaker(kind).reset()
        self._audit.record(AuditAction.CIRCUIT_RESET, kind, "admin", actor="admin", detail={"reason": reason})


class IntegrationAdmin:
    def __init__(self, registry: IntegrationRegistry, caller: SafeIntegrationCall, audit: IntegrationAuditChain):
        self._registry = registry
        self._caller   = caller
        self._audit    = audit

    def revoke_key(self, kind: IntegrationKind, reason: str) -> None:
        if not reason or not reason.strip(): raise MissingReasonError("Reason required to revoke key")
        self._registry.revoke_secret(kind, reason)
        self._audit.record(AuditAction.KEY_REVOKED, kind, "admin", actor="admin", detail={"kind": kind.value, "reason": reason})

    def inspect_circuits(self) -> Dict[str, str]:
        return {kind.value: self._caller.circuit_state(kind).value for kind in self._registry.list_kinds()}

    def drain_dlq(self, reason: str) -> List[DeadLetterItem]:
        if not reason or not reason.strip(): raise MissingReasonError("Reason required to drain DLQ")
        items = self._caller.drain_dlq()
        self._audit.record(AuditAction.DEAD_LETTERED, IntegrationKind.WEBHOOK_IN, "admin-drain", actor="admin", detail={"drained": len(items), "reason": reason})
        return items

    def reset_circuit(self, kind: IntegrationKind, reason: str) -> None:
        self._caller.reset_circuit(kind, reason)

    def summary(self) -> Dict[str, Any]:
        return {
            "registered_kinds": [k.value for k in self._registry.list_kinds()],
            "circuit_states":   self.inspect_circuits(),
            "dlq_size":         len(self._caller.dlq),
            "audit_size":       self._audit.size,
            "audit_verified":   self._audit.verify_chain(),
        }


def build_integration(
    kind: IntegrationKind, secret: str | bytes,
    policy: Optional[IntegrationPolicy] = None,
    audit: Optional[IntegrationAuditChain] = None,
) -> Tuple[SafeIntegrationCall, IntegrationRegistry, IntegrationAuditChain]:
    registry = IntegrationRegistry()
    registry.register(kind, policy=policy, secret=secret)
    _audit   = audit or IntegrationAuditChain()
    caller   = SafeIntegrationCall(registry, audit=_audit)
    return caller, registry, _audit
