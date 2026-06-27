"""
backend/core/rate_limit_v22.py - Phase 22: API Rate Limiting & Abuse Prevention
================================================================================
P22-RL-1:  Sliding window algorithm (not fixed window - no boundary burst)
P22-RL-2:  Per-endpoint, per-role, per-plan rate limits
P22-RL-3:  IP-based + User-based + Tenant-based limiting
P22-RL-4:  Burst allowance with token bucket
P22-RL-5:  Exponential backoff for repeat offenders
P22-RL-6:  Abuse detection: credential stuffing, scraping, enumeration
P22-RL-7:  Automatic IP ban with TTL
P22-RL-8:  429 with Retry-After header
P22-RL-9:  Whitelist for health/metrics/internal
P22-RL-10: Thread-safe in-memory store (Redis-compatible interface)
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class RateLimitTier(str, Enum):
    ANONYMOUS = "anonymous"
    READONLY  = "readonly"
    TRIAL     = "trial"
    BASIC     = "basic"
    PRO       = "pro"
    VIP       = "vip"
    ADMIN     = "admin"
    INTERNAL  = "internal"


class AbuseType(str, Enum):
    CREDENTIAL_STUFFING = "credential_stuffing"
    ENUMERATION         = "enumeration"
    SCRAPING            = "scraping"
    BRUTE_FORCE         = "brute_force"
    WEBHOOK_REPLAY      = "webhook_replay"
    EXCESSIVE_ERRORS    = "excessive_errors"


@dataclass
class EndpointLimit:
    requests: int
    window:   int
    burst:    int = 0
    reason:   str = ""


@dataclass
class TierLimits:
    tier:          RateLimitTier
    rpm:           int
    burst:         int
    ban_threshold: int = 10


TIER_LIMITS: Dict[RateLimitTier, TierLimits] = {
    RateLimitTier.ANONYMOUS: TierLimits(RateLimitTier.ANONYMOUS,  rpm=20,    burst=5,   ban_threshold=5),
    RateLimitTier.READONLY:  TierLimits(RateLimitTier.READONLY,   rpm=60,    burst=10,  ban_threshold=10),
    RateLimitTier.TRIAL:     TierLimits(RateLimitTier.TRIAL,      rpm=60,    burst=10,  ban_threshold=10),
    RateLimitTier.BASIC:     TierLimits(RateLimitTier.BASIC,      rpm=120,   burst=20,  ban_threshold=15),
    RateLimitTier.PRO:       TierLimits(RateLimitTier.PRO,        rpm=300,   burst=50,  ban_threshold=20),
    RateLimitTier.VIP:       TierLimits(RateLimitTier.VIP,        rpm=600,   burst=100, ban_threshold=30),
    RateLimitTier.ADMIN:     TierLimits(RateLimitTier.ADMIN,      rpm=1200,  burst=200, ban_threshold=50),
    RateLimitTier.INTERNAL:  TierLimits(RateLimitTier.INTERNAL,   rpm=99999, burst=999, ban_threshold=9999),
}

ENDPOINT_LIMITS: Dict[str, EndpointLimit] = {
    "/api/auth/login":       EndpointLimit(5,     60, burst=2,  reason="auth - brute force prevention"),
    "/api/auth/register":    EndpointLimit(3,     60, burst=0,  reason="registration throttle"),
    "/api/auth/refresh":     EndpointLimit(10,    60, burst=2,  reason="token refresh"),
    "/api/auth/logout":      EndpointLimit(10,    60, burst=0,  reason="logout"),
    "/api/billing/checkout": EndpointLimit(5,     60, burst=1,  reason="checkout throttle"),
    "/api/billing/webhook":  EndpointLimit(60,    60, burst=10, reason="webhook ingestion"),
    "/api/license/issue":    EndpointLimit(10,    60, burst=2,  reason="license issuance"),
    "/api/license/verify":   EndpointLimit(30,    60, burst=5,  reason="license verify"),
    "/api/signals":          EndpointLimit(120,   60, burst=20, reason="signal fetch"),
    "/api/trade":            EndpointLimit(60,    60, burst=10, reason="trade execution"),
    "/api/admin":            EndpointLimit(120,   60, burst=30, reason="admin operations"),
    "/api/risk/halt":        EndpointLimit(5,     60, burst=0,  reason="risk halt - rare"),
    "/api/risk/resume":      EndpointLimit(5,     60, burst=0,  reason="risk resume - rare"),
    "/health":               EndpointLimit(99999, 60, burst=999, reason="health - no limit"),
    "/metrics":              EndpointLimit(99999, 60, burst=999, reason="metrics - no limit"),
}

WHITELIST_PREFIXES: Set[str] = {
    "/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
}

ABUSE_THRESHOLDS = {
    AbuseType.CREDENTIAL_STUFFING: {"endpoint": "/api/auth/login", "fails": 5,  "window": 60},
    AbuseType.BRUTE_FORCE:         {"endpoint": "/api/auth/",      "fails": 10, "window": 60},
    AbuseType.SCRAPING:            {"rpm": 200,  "window": 60},
    AbuseType.EXCESSIVE_ERRORS:    {"errors": 20, "window": 60},
}

BAN_TTL_SECONDS  = 3600
MAX_BACKOFF_SECS = 3600
VIOLATION_DECAY  = 300


@dataclass
class RateLimitRecord:
    key:        str
    timestamps: deque = field(default_factory=deque)
    violations: int   = 0
    last_violation: float = 0.0
    backoff_until:  float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)

    def prune(self, cutoff: float) -> None:
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def count(self, window: int) -> int:
        self.prune(time.monotonic() - window)
        return len(self.timestamps)


@dataclass
class BanRecord:
    ip:         str
    reason:     str
    banned_at:  float
    expires_at: float
    abuse_type: Optional[AbuseType] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class AbuseRecord:
    ip:           str
    fail_count:   int   = 0
    error_count:  int   = 0
    last_fail_ts: float = 0.0
    fail_window:  deque = field(default_factory=deque)
    error_window: deque = field(default_factory=deque)
    detected:     List[AbuseType] = field(default_factory=list)


@dataclass
class RateLimitResult:
    allowed:      bool
    key:          str
    limit:        int
    remaining:    int
    reset_after:  float
    retry_after:  float
    reason:       str      = ""
    banned:       bool     = False
    abuse_types:  List[AbuseType] = field(default_factory=list)
    request_id:   str      = field(default_factory=lambda: str(uuid.uuid4())[:8])


class RateLimitStore:
    def __init__(self) -> None:
        self._records: Dict[str, RateLimitRecord] = {}
        self._bans:    Dict[str, BanRecord]        = {}
        self._abuse:   Dict[str, AbuseRecord]      = {}
        self._lock     = threading.RLock()

    def get_record(self, key: str) -> RateLimitRecord:
        with self._lock:
            if key not in self._records:
                self._records[key] = RateLimitRecord(key=key)
            return self._records[key]

    def reset(self, key: str) -> None:
        with self._lock:
            self._records.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._records.clear()
            self._bans.clear()
            self._abuse.clear()

    def ban(self, ip: str, reason: str, ttl: float = BAN_TTL_SECONDS,
            abuse_type: Optional[AbuseType] = None) -> BanRecord:
        with self._lock:
            now = time.monotonic()
            rec = BanRecord(ip=ip, reason=reason, banned_at=now,
                            expires_at=now + ttl, abuse_type=abuse_type)
            self._bans[ip] = rec
            return rec

    def unban(self, ip: str) -> bool:
        with self._lock:
            return self._bans.pop(ip, None) is not None

    def is_banned(self, ip: str) -> Optional[BanRecord]:
        with self._lock:
            rec = self._bans.get(ip)
            if rec and time.monotonic() > rec.expires_at:
                del self._bans[ip]
                return None
            return rec

    def list_bans(self) -> List[BanRecord]:
        with self._lock:
            now = time.monotonic()
            expired = [ip for ip, r in self._bans.items() if now > r.expires_at]
            for ip in expired:
                del self._bans[ip]
            return list(self._bans.values())

    def get_abuse(self, ip: str) -> AbuseRecord:
        with self._lock:
            if ip not in self._abuse:
                self._abuse[ip] = AbuseRecord(ip=ip)
            return self._abuse[ip]

    def record_fail(self, ip: str, endpoint: str) -> AbuseRecord:
        with self._lock:
            rec = self.get_abuse(ip)
            now = time.monotonic()
            rec.fail_count += 1
            rec.last_fail_ts = now
            rec.fail_window.append((now, endpoint))
            cutoff = now - 60
            while rec.fail_window and rec.fail_window[0][0] < cutoff:
                rec.fail_window.popleft()
            return rec

    def record_error(self, ip: str) -> AbuseRecord:
        with self._lock:
            rec = self.get_abuse(ip)
            now = time.monotonic()
            rec.error_count += 1
            rec.error_window.append(now)
            cutoff = now - 60
            while rec.error_window and rec.error_window[0] < cutoff:
                rec.error_window.popleft()
            return rec

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tracked_keys":  len(self._records),
                "active_bans":   len([r for r in self._bans.values()
                                      if time.monotonic() < r.expires_at]),
                "abuse_tracked": len(self._abuse),
            }


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float) -> None:
        self._capacity    = capacity
        self._refill_rate = refill_rate
        self._tokens      = float(capacity)
        self._last_refill = time.monotonic()
        self._lock        = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(float(self._capacity),
                               self._tokens + elapsed * self._refill_rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available(self) -> float:
        with self._lock:
            now = time.monotonic()
            return min(float(self._capacity),
                       self._tokens + (now - self._last_refill) * self._refill_rate)

    def reset(self) -> None:
        with self._lock:
            self._tokens = float(self._capacity)
            self._last_refill = time.monotonic()


class SlidingWindowChecker:
    def __init__(self, store: RateLimitStore) -> None:
        self._store = store

    def check(self, key: str, limit: int, window: int,
              burst: int = 0, consume: bool = True) -> Tuple[bool, int, float]:
        rec = self._store.get_record(key)
        now = time.monotonic()
        with rec.lock:
            cutoff = now - window
            rec.prune(cutoff)
            count = len(rec.timestamps)
            effective_limit = limit + burst
            if count >= effective_limit:
                oldest = rec.timestamps[0] if rec.timestamps else now
                retry_after = max(0.0, (oldest + window) - now)
                return False, 0, retry_after
            if consume:
                rec.add(now)
                count += 1
            remaining = max(0, effective_limit - count)
            return True, remaining, 0.0


class BackoffTracker:
    def __init__(self, store: RateLimitStore) -> None:
        self._store = store

    def record_violation(self, key: str) -> float:
        rec = self._store.get_record(key)
        with rec.lock:
            now = time.monotonic()
            if now - rec.last_violation > VIOLATION_DECAY and rec.violations > 0:
                rec.violations = max(0, rec.violations - 1)
            rec.violations    += 1
            rec.last_violation = now
            backoff = min(MAX_BACKOFF_SECS, 2 ** rec.violations)
            rec.backoff_until  = now + backoff
            return backoff

    def is_in_backoff(self, key: str) -> Tuple[bool, float]:
        rec = self._store.get_record(key)
        with rec.lock:
            now = time.monotonic()
            if rec.backoff_until > now:
                return True, rec.backoff_until - now
            return False, 0.0

    def clear(self, key: str) -> None:
        rec = self._store.get_record(key)
        with rec.lock:
            rec.violations    = 0
            rec.backoff_until = 0.0


class AbuseDetector:
    def __init__(self, store: RateLimitStore) -> None:
        self._store = store
        self._hooks: List[Callable] = []

    def add_hook(self, fn: Callable) -> None:
        self._hooks.append(fn)

    def _fire(self, ip: str, abuse: AbuseType, ban: BanRecord) -> None:
        for h in self._hooks:
            try:
                h(ip, abuse, ban)
            except Exception:
                pass

    def record_auth_fail(self, ip: str, endpoint: str = "/api/auth/login") -> Optional[BanRecord]:
        rec = self._store.record_fail(ip, endpoint)
        now    = time.monotonic()
        cutoff = now - 60
        recent = sum(1 for ts, _ in rec.fail_window if ts >= cutoff)
        threshold = ABUSE_THRESHOLDS[AbuseType.CREDENTIAL_STUFFING]["fails"]
        if recent >= threshold:
            ban = self._store.ban(ip=ip,
                reason=f"Credential stuffing: {recent} fails in 60s",
                ttl=BAN_TTL_SECONDS, abuse_type=AbuseType.CREDENTIAL_STUFFING)
            self._fire(ip, AbuseType.CREDENTIAL_STUFFING, ban)
            return ban
        return None

    def record_error(self, ip: str) -> Optional[BanRecord]:
        rec    = self._store.record_error(ip)
        recent = len(rec.error_window)
        threshold = ABUSE_THRESHOLDS[AbuseType.EXCESSIVE_ERRORS]["errors"]
        if recent >= threshold:
            ban = self._store.ban(ip=ip,
                reason=f"Excessive errors: {recent} in 60s",
                ttl=BAN_TTL_SECONDS // 2,
                abuse_type=AbuseType.EXCESSIVE_ERRORS)
            self._fire(ip, AbuseType.EXCESSIVE_ERRORS, ban)
            return ban
        return None

    def detect_scraping(self, ip: str, rpm: int) -> Optional[BanRecord]:
        threshold = ABUSE_THRESHOLDS[AbuseType.SCRAPING]["rpm"]
        if rpm >= threshold:
            ban = self._store.ban(ip=ip, reason=f"Scraping: {rpm} RPM",
                ttl=BAN_TTL_SECONDS, abuse_type=AbuseType.SCRAPING)
            self._fire(ip, AbuseType.SCRAPING, ban)
            return ban
        return None

    def detect_enumeration(self, ip: str, sequential_count: int) -> Optional[BanRecord]:
        if sequential_count >= 5:
            ban = self._store.ban(ip=ip,
                reason=f"Enumeration: {sequential_count} sequential IDs",
                ttl=BAN_TTL_SECONDS, abuse_type=AbuseType.ENUMERATION)
            self._fire(ip, AbuseType.ENUMERATION, ban)
            return ban
        return None

    def is_banned(self, ip: str) -> Optional[BanRecord]:
        return self._store.is_banned(ip)


class RateLimiter:
    def __init__(self, store=None, backoff=None, abuse=None,
                 tier_limits=None, endpoint_limits=None) -> None:
        self._store   = store   or RateLimitStore()
        self._checker = SlidingWindowChecker(self._store)
        self._backoff = backoff or BackoffTracker(self._store)
        self._abuse   = abuse   or AbuseDetector(self._store)
        self._tiers   = tier_limits     or TIER_LIMITS
        self._eps     = endpoint_limits or ENDPOINT_LIMITS
        self._buckets: Dict[str, TokenBucket] = {}
        self._bk_lock = threading.Lock()

    def check(self, ip: str, endpoint: str = "/", user_id=None,
              tenant_id=None, tier: RateLimitTier = RateLimitTier.ANONYMOUS) -> RateLimitResult:
        req_id = str(uuid.uuid4())[:8]
        for prefix in WHITELIST_PREFIXES:
            if endpoint.startswith(prefix):
                return RateLimitResult(allowed=True, key=ip, limit=99999,
                    remaining=99999, reset_after=0.0, retry_after=0.0,
                    reason="whitelisted", request_id=req_id)
        ban = self._store.is_banned(ip)
        if ban:
            ttl = ban.expires_at - time.monotonic()
            return RateLimitResult(allowed=False, key=ip, limit=0, remaining=0,
                reset_after=ttl, retry_after=ttl,
                reason=f"IP banned: {ban.reason}", banned=True, request_id=req_id)
        in_bo, bo_secs = self._backoff.is_in_backoff(f"bo:{ip}")
        if in_bo:
            return RateLimitResult(allowed=False, key=ip, limit=0, remaining=0,
                reset_after=bo_secs, retry_after=bo_secs,
                reason=f"Backoff: {bo_secs:.1f}s remaining", request_id=req_id)
        if tier == RateLimitTier.INTERNAL:
            return RateLimitResult(allowed=True, key=ip, limit=99999,
                remaining=99999, reset_after=0.0, retry_after=0.0,
                reason="internal tier", request_id=req_id)
        tier_cfg = self._tiers.get(tier, self._tiers[RateLimitTier.ANONYMOUS])
        ep_limit = self._get_endpoint_limit(endpoint)
        if ep_limit:
            ep_key = f"ep:{ip}:{endpoint}"
            allowed, remaining, retry = self._checker.check(
                key=ep_key, limit=ep_limit.requests,
                window=ep_limit.window, burst=ep_limit.burst)
            if not allowed:
                self._backoff.record_violation(f"bo:{ip}")
                return RateLimitResult(allowed=False, key=ep_key,
                    limit=ep_limit.requests + ep_limit.burst, remaining=0,
                    reset_after=retry, retry_after=retry,
                    reason=f"Endpoint limit: {ep_limit.reason}", request_id=req_id)
        ip_key = f"ip:{ip}"
        allowed_ip, rem_ip, retry_ip = self._checker.check(
            key=ip_key, limit=tier_cfg.rpm, window=60, burst=tier_cfg.burst)
        if not allowed_ip:
            self._backoff.record_violation(f"bo:{ip}")
            return RateLimitResult(allowed=False, key=ip_key,
                limit=tier_cfg.rpm + tier_cfg.burst, remaining=0,
                reset_after=retry_ip, retry_after=retry_ip,
                reason=f"IP RPM limit for tier {tier.value}", request_id=req_id)
        if user_id:
            u_key = f"user:{user_id}"
            allowed_u, rem_u, retry_u = self._checker.check(
                key=u_key, limit=tier_cfg.rpm, window=60, burst=tier_cfg.burst)
            if not allowed_u:
                return RateLimitResult(allowed=False, key=u_key,
                    limit=tier_cfg.rpm + tier_cfg.burst, remaining=0,
                    reset_after=retry_u, retry_after=retry_u,
                    reason=f"User RPM limit for tier {tier.value}", request_id=req_id)
        if tenant_id:
            t_key = f"tenant:{tenant_id}"
            allowed_t, rem_t, retry_t = self._checker.check(
                key=t_key, limit=tier_cfg.rpm * 5, window=60, burst=tier_cfg.burst * 5)
            if not allowed_t:
                return RateLimitResult(allowed=False, key=t_key,
                    limit=tier_cfg.rpm * 5, remaining=0,
                    reset_after=retry_t, retry_after=retry_t,
                    reason="Tenant RPM limit", request_id=req_id)
        remaining = min(rem_ip, tier_cfg.rpm + tier_cfg.burst - 1)
        return RateLimitResult(allowed=True, key=ip_key,
            limit=tier_cfg.rpm + tier_cfg.burst, remaining=remaining,
            reset_after=60.0, retry_after=0.0, reason="ok", request_id=req_id)

    def record_auth_fail(self, ip: str): return self._abuse.record_auth_fail(ip)
    def record_error(self, ip: str):     return self._abuse.record_error(ip)
    def ban(self, ip, reason, ttl=BAN_TTL_SECONDS): return self._store.ban(ip, reason, ttl)
    def unban(self, ip: str): return self._store.unban(ip)
    def is_banned(self, ip: str): return self._store.is_banned(ip)
    def reset(self, key: str): self._store.reset(key)
    def reset_all(self): self._store.reset_all()
    def stats(self): return self._store.stats()
    def add_abuse_hook(self, fn): self._abuse.add_hook(fn)

    def _get_endpoint_limit(self, endpoint: str) -> Optional[EndpointLimit]:
        if endpoint in self._eps:
            return self._eps[endpoint]
        for pat in sorted(self._eps.keys(), key=len, reverse=True):
            if endpoint.startswith(pat):
                return self._eps[pat]
        return None


def make_rate_limit_headers(result: RateLimitResult, limit: int) -> Dict[str, str]:
    h = {
        "X-RateLimit-Limit":     str(limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset":     str(int(time.time() + result.reset_after)),
        "X-RateLimit-RequestId": result.request_id,
    }
    if not result.allowed:
        h["Retry-After"]         = str(int(result.retry_after) + 1)
        h["X-RateLimit-Reason"]  = result.reason
    return h


_global_limiter: Optional[RateLimiter] = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _global_limiter
    if _global_limiter is None:
        with _limiter_lock:
            if _global_limiter is None:
                _global_limiter = RateLimiter()
    return _global_limiter


def reset_global_limiter() -> None:
    global _global_limiter
    with _limiter_lock:
        _global_limiter = None
