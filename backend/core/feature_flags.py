"""
PHASE 24 - Feature Flags & Safe Rollout Control
================================================
P24-FLAG-1:  FlagKey enum - 32 flags across 6 domains
P24-FLAG-2:  FlagScope - tenant / user / plan / global
P24-FLAG-3:  RolloutStrategy - none/percentage/canary/ring/allowlist/blocklist
P24-FLAG-4:  KillOverride - instant flag disable, reason mandatory
P24-FLAG-5:  AuditedFlagStore - every change HMAC-chained, no silent mutation
P24-FLAG-6:  FlagEvaluator - deterministic % hash, scope precedence chain
P24-FLAG-7:  GradualRolloutManager - step-up/step-down/pause/resume
P24-FLAG-8:  FlagChangeAudit - forensic trail, tamper-evident
P24-FLAG-9:  FlagAdmin - CRUD + kill + rollout control
P24-FLAG-10: ReleaseRing - alpha/beta/ga/internal ring assignment
P24-FLAG-11: PlanGate - flag restricted by subscription plan
P24-FLAG-12: ConcurrencyGuard - thread-safe eval, no torn reads
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

_LOG = logging.getLogger(__name__)


class FlagKey(str, Enum):
    # RISK domain (8)
    RISK_KILL_SWITCH_V2        = "risk.kill_switch_v2"
    RISK_DYNAMIC_DRAWDOWN      = "risk.dynamic_drawdown"
    RISK_HEARTBEAT_MONITOR     = "risk.heartbeat_monitor"
    RISK_POSITION_HEDGE        = "risk.position_hedge"
    RISK_EQUITY_GUARD          = "risk.equity_guard"
    RISK_TRAILING_STOP_V2      = "risk.trailing_stop_v2"
    RISK_MULTI_SYMBOL_LIMIT    = "risk.multi_symbol_limit"
    RISK_NEWS_FILTER           = "risk.news_filter"
    # LICENSE domain (6)
    LICENSE_GRACE_PERIOD       = "license.grace_period"
    LICENSE_DEVICE_LIMIT_V2    = "license.device_limit_v2"
    LICENSE_OFFLINE_MODE       = "license.offline_mode"
    LICENSE_AUTO_RENEW         = "license.auto_renew"
    LICENSE_TRIAL_EXTENSION    = "license.trial_extension"
    LICENSE_BULK_ISSUANCE      = "license.bulk_issuance"
    # BILLING domain (6)
    BILLING_STRIPE_V2          = "billing.stripe_v2"
    BILLING_CRYPTO_PAY         = "billing.crypto_pay"
    BILLING_USAGE_METER        = "billing.usage_meter"
    BILLING_DUNNING_V2         = "billing.dunning_v2"
    BILLING_PRORATION          = "billing.proration"
    BILLING_INVOICE_PDF        = "billing.invoice_pdf"
    # EA / MQL5 domain (4)
    EA_CLOUD_CONFIG            = "ea.cloud_config"
    EA_REMOTE_KILL             = "ea.remote_kill"
    EA_TELEMETRY_V2            = "ea.telemetry_v2"
    EA_AUTO_UPDATE             = "ea.auto_update"
    # DASHBOARD domain (4)
    DASHBOARD_REALTIME_PNL     = "dashboard.realtime_pnl"
    DASHBOARD_ADVANCED_CHARTS  = "dashboard.advanced_charts"
    DASHBOARD_AI_INSIGHTS      = "dashboard.ai_insights"
    DASHBOARD_EXPORT_V2        = "dashboard.export_v2"
    # PLATFORM domain (4)
    PLATFORM_MULTI_TENANT      = "platform.multi_tenant"
    PLATFORM_SSO               = "platform.sso"
    PLATFORM_WEBHOOKS_V2       = "platform.webhooks_v2"
    PLATFORM_GRAPHQL           = "platform.graphql"


class FlagScope(str, Enum):
    KILL_OVERRIDE = "kill_override"
    USER          = "user"
    TENANT        = "tenant"
    PLAN          = "plan"
    RING          = "ring"
    GLOBAL        = "global"


class RolloutStrategy(str, Enum):
    NONE        = "none"
    PERCENTAGE  = "percentage"
    CANARY      = "canary"
    RING        = "ring"
    ALLOWLIST   = "allowlist"
    BLOCKLIST   = "blocklist"


class ReleaseRing(str, Enum):
    INTERNAL = "internal"
    ALPHA    = "alpha"
    BETA     = "beta"
    GA       = "ga"


class PlanTier(str, Enum):
    TRIAL   = "trial"
    BASIC   = "basic"
    PRO     = "pro"
    VIP     = "vip"
    ADMIN   = "admin"


RING_ORDER = [ReleaseRing.INTERNAL, ReleaseRing.ALPHA, ReleaseRing.BETA, ReleaseRing.GA]
PLAN_ORDER = [PlanTier.TRIAL, PlanTier.BASIC, PlanTier.PRO, PlanTier.VIP, PlanTier.ADMIN]

FLAG_MIN_PLAN: Dict[FlagKey, PlanTier] = {
    FlagKey.BILLING_CRYPTO_PAY:        PlanTier.PRO,
    FlagKey.BILLING_USAGE_METER:       PlanTier.PRO,
    FlagKey.DASHBOARD_AI_INSIGHTS:     PlanTier.PRO,
    FlagKey.DASHBOARD_ADVANCED_CHARTS: PlanTier.BASIC,
    FlagKey.LICENSE_BULK_ISSUANCE:     PlanTier.VIP,
    FlagKey.PLATFORM_SSO:              PlanTier.VIP,
    FlagKey.PLATFORM_GRAPHQL:          PlanTier.PRO,
    FlagKey.EA_REMOTE_KILL:            PlanTier.PRO,
    FlagKey.RISK_POSITION_HEDGE:       PlanTier.PRO,
}


@dataclass
class FlagConfig:
    key: FlagKey
    enabled: bool = False
    strategy: RolloutStrategy = RolloutStrategy.NONE
    rollout_pct: float = 0.0
    allowlist_users: Set[str] = field(default_factory=set)
    allowlist_tenants: Set[str] = field(default_factory=set)
    blocklist_users: Set[str] = field(default_factory=set)
    blocklist_tenants: Set[str] = field(default_factory=set)
    min_ring: Optional[ReleaseRing] = None
    min_plan: Optional[PlanTier] = None
    description: str = ""
    owner: str = "platform"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class KillOverride:
    flag_key: FlagKey
    reason: str
    actor_id: str
    tenant_id: Optional[str]
    activated_at: float = field(default_factory=time.time)
    ttl_seconds: Optional[float] = None

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return time.time() > self.activated_at + self.ttl_seconds


@dataclass
class FlagAuditRecord:
    id: str
    seq: int
    flag_key: str
    action: str
    actor_id: str
    tenant_id: Optional[str]
    reason: str
    payload: Dict[str, Any]
    ts: float
    chain_hash: str
    prev_hash: str


@dataclass
class EvalContext:
    user_id: str
    tenant_id: str
    plan: Optional[PlanTier] = None
    ring: Optional[ReleaseRing] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    enabled: bool
    reason: str
    scope: FlagScope
    flag_key: str


@dataclass
class RolloutStep:
    pct: float
    at: float = field(default_factory=time.time)


_DEFAULT_SECRET = os.environ.get("FLAG_AUDIT_SECRET", "flag-audit-secret-phase24")


class FlagAuditChain:
    def __init__(self, secret=_DEFAULT_SECRET):
        if isinstance(secret, str):
            secret = secret.encode()
        self._secret = secret
        self._records: deque[FlagAuditRecord] = deque(maxlen=10_000)
        self._seq = 0
        self._lock = threading.Lock()
        self._prev_hash = self._genesis()

    def _genesis(self) -> str:
        return hmac.new(self._secret, b"GENESIS:FLAG:AUDIT:CHAIN:V24", hashlib.sha256).hexdigest()

    def _compute_hash(self, prev: str, payload: Dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        msg = f"{prev}:{canonical}".encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def record(self, flag_key, action, actor_id, reason, payload, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError(f"reason is mandatory for flag action '{action}'")
        with self._lock:
            self._seq += 1
            rec_id = str(uuid.uuid4())
            ts = time.time()
            canonical = {"id": rec_id, "seq": self._seq, "flag_key": flag_key,
                         "action": action, "actor_id": actor_id, "tenant_id": tenant_id,
                         "reason": reason, "payload": payload, "ts": str(ts)}
            chain_hash = self._compute_hash(self._prev_hash, canonical)
            prev = self._prev_hash
            self._prev_hash = chain_hash
            rec = FlagAuditRecord(id=rec_id, seq=self._seq, flag_key=flag_key,
                                  action=action, actor_id=actor_id, tenant_id=tenant_id,
                                  reason=reason, payload=payload, ts=ts,
                                  chain_hash=chain_hash, prev_hash=prev)
            self._records.append(rec)
            return rec

    def verify_chain(self) -> bool:
        with self._lock:
            recs = list(self._records)
        prev = self._genesis()
        for r in recs:
            canonical = {"id": r.id, "seq": r.seq, "flag_key": r.flag_key,
                         "action": r.action, "actor_id": r.actor_id, "tenant_id": r.tenant_id,
                         "reason": r.reason, "payload": r.payload, "ts": str(r.ts)}
            expected = self._compute_hash(prev, canonical)
            if not hmac.compare_digest(expected, r.chain_hash):
                return False
            prev = r.chain_hash
        return True

    def query(self, flag_key=None, actor_id=None, action=None, limit=100):
        with self._lock:
            recs = list(self._records)
        recs = list(reversed(recs))
        if flag_key:
            recs = [r for r in recs if r.flag_key == flag_key]
        if actor_id:
            recs = [r for r in recs if r.actor_id == actor_id]
        if action:
            recs = [r for r in recs if r.action == action]
        return recs[:limit]

    @property
    def total(self) -> int:
        return len(self._records)


def _stable_hash(key: str, user_id: str, tenant_id: str) -> float:
    raw = hashlib.md5(f"{key}:{tenant_id}:{user_id}".encode()).hexdigest()
    return (int(raw[:8], 16) / 0xFFFFFFFF) * 100.0


class FlagEvaluator:
    def evaluate(self, flag_key, ctx, config, kills):
        key = flag_key.value
        for ko in kills:
            if ko.flag_key != flag_key:
                continue
            if ko.is_expired():
                continue
            if ko.tenant_id is None or ko.tenant_id == ctx.tenant_id:
                return EvalResult(enabled=False, reason=f"kill_override:{ko.reason}",
                                  scope=FlagScope.KILL_OVERRIDE, flag_key=key)
        if not config.enabled:
            return EvalResult(enabled=False, reason="flag_disabled", scope=FlagScope.GLOBAL, flag_key=key)
        effective_min = config.min_plan or FLAG_MIN_PLAN.get(flag_key)
        if effective_min and ctx.plan:
            plan_idx = PLAN_ORDER.index(ctx.plan) if ctx.plan in PLAN_ORDER else -1
            min_idx = PLAN_ORDER.index(effective_min)
            if plan_idx < min_idx:
                return EvalResult(enabled=False, reason=f"plan_gate:{effective_min.value}_required",
                                  scope=FlagScope.PLAN, flag_key=key)
        strategy = config.strategy
        if ctx.user_id in config.blocklist_users:
            return EvalResult(enabled=False, reason="blocklist:user", scope=FlagScope.USER, flag_key=key)
        if ctx.tenant_id in config.blocklist_tenants:
            return EvalResult(enabled=False, reason="blocklist:tenant", scope=FlagScope.TENANT, flag_key=key)
        if strategy == RolloutStrategy.ALLOWLIST:
            if ctx.user_id in config.allowlist_users:
                return EvalResult(enabled=True, reason="allowlist:user", scope=FlagScope.USER, flag_key=key)
            if ctx.tenant_id in config.allowlist_tenants:
                return EvalResult(enabled=True, reason="allowlist:tenant", scope=FlagScope.TENANT, flag_key=key)
            return EvalResult(enabled=False, reason="allowlist:not_in_list", scope=FlagScope.USER, flag_key=key)
        if ctx.user_id in config.allowlist_users:
            return EvalResult(enabled=True, reason="user_override:on", scope=FlagScope.USER, flag_key=key)
        if ctx.tenant_id in config.allowlist_tenants:
            return EvalResult(enabled=True, reason="tenant_override:on", scope=FlagScope.TENANT, flag_key=key)
        if strategy == RolloutStrategy.RING and config.min_ring and ctx.ring:
            min_idx = RING_ORDER.index(config.min_ring)
            ctx_idx = RING_ORDER.index(ctx.ring)
            if ctx_idx <= min_idx:
                return EvalResult(enabled=True, reason=f"ring:{ctx.ring.value}", scope=FlagScope.RING, flag_key=key)
            return EvalResult(enabled=False, reason=f"ring:{ctx.ring.value}_below_{config.min_ring.value}",
                              scope=FlagScope.RING, flag_key=key)
        if strategy == RolloutStrategy.PERCENTAGE:
            pct_hash = _stable_hash(key, ctx.user_id, ctx.tenant_id)
            if pct_hash < config.rollout_pct:
                return EvalResult(enabled=True, reason=f"pct:{config.rollout_pct:.1f}", scope=FlagScope.GLOBAL, flag_key=key)
            return EvalResult(enabled=False, reason=f"pct:{pct_hash:.1f}>={config.rollout_pct:.1f}",
                              scope=FlagScope.GLOBAL, flag_key=key)
        return EvalResult(enabled=True, reason="global:enabled", scope=FlagScope.GLOBAL, flag_key=key)


class AuditedFlagStore:
    def __init__(self, audit_chain=None):
        self._lock = threading.RLock()
        self._flags: Dict[FlagKey, FlagConfig] = {}
        self._kills: List[KillOverride] = []
        self._audit = audit_chain if audit_chain is not None else FlagAuditChain()
        self._evaluator = FlagEvaluator()
        self._hooks = []

    def set_flag(self, config, actor_id, reason, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for set_flag")
        with self._lock:
            action = "create" if config.key not in self._flags else "update"
            self._flags[config.key] = config
            return self._audit.record(flag_key=config.key.value, action=action,
                                      actor_id=actor_id, reason=reason,
                                      payload={"enabled": config.enabled,
                                               "strategy": config.strategy.value,
                                               "rollout_pct": config.rollout_pct},
                                      tenant_id=tenant_id)

    def get_flag(self, key):
        with self._lock:
            return self._flags.get(key)

    def remove_flag(self, key, actor_id, reason, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for remove_flag")
        with self._lock:
            self._flags.pop(key, None)
            return self._audit.record(flag_key=key.value, action="remove",
                                      actor_id=actor_id, reason=reason, payload={}, tenant_id=tenant_id)

    def list_flags(self):
        with self._lock:
            return list(self._flags.values())

    def activate_kill(self, key, actor_id, reason, tenant_id=None, ttl_seconds=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for kill override")
        with self._lock:
            ko = KillOverride(flag_key=key, reason=reason, actor_id=actor_id,
                              tenant_id=tenant_id, ttl_seconds=ttl_seconds)
            self._kills = [k for k in self._kills
                           if not (k.flag_key == key and k.tenant_id == tenant_id)]
            self._kills.append(ko)
            self._audit.record(flag_key=key.value, action="kill", actor_id=actor_id,
                               reason=reason, payload={"tenant_id": tenant_id, "ttl": ttl_seconds},
                               tenant_id=tenant_id)
            return ko

    def reset_kill(self, key, actor_id, reason, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for reset_kill")
        with self._lock:
            self._kills = [k for k in self._kills
                           if not (k.flag_key == key and k.tenant_id == tenant_id)]
            return self._audit.record(flag_key=key.value, action="kill_reset",
                                      actor_id=actor_id, reason=reason,
                                      payload={"tenant_id": tenant_id}, tenant_id=tenant_id)

    def active_kills(self, key=None):
        with self._lock:
            self._kills = [k for k in self._kills if not k.is_expired()]
            if key:
                return [k for k in self._kills if k.flag_key == key]
            return list(self._kills)

    def evaluate(self, key, ctx):
        with self._lock:
            config = self._flags.get(key)
            kills = [k for k in self._kills if not k.is_expired()]
        if config is None:
            result = EvalResult(enabled=False, reason="flag_not_found",
                                scope=FlagScope.GLOBAL, flag_key=key.value)
        else:
            result = self._evaluator.evaluate(key, ctx, config, kills)
        for hook in self._hooks:
            try:
                hook(key, result, ctx)
            except Exception as exc:
                _LOG.warning('feature flag hook error for %s: %s', key, exc)
        return result

    def is_enabled(self, key, ctx):
        return self.evaluate(key, ctx).enabled

    def add_hook(self, fn):
        self._hooks.append(fn)

    @property
    def audit(self):
        return self._audit


class GradualRolloutManager:
    DEFAULT_STEPS = [0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0]

    def __init__(self, store):
        self._store = store
        self._paused: Set[FlagKey] = set()
        self._step_history: Dict[FlagKey, List[RolloutStep]] = {}
        self._lock = threading.Lock()

    def start_rollout(self, key, actor_id, reason, initial_pct=1.0, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for start_rollout")
        with self._lock:
            cfg = self._store.get_flag(key) or FlagConfig(key=key)
            cfg.enabled = True
            cfg.strategy = RolloutStrategy.PERCENTAGE
            cfg.rollout_pct = max(0.0, min(100.0, initial_pct))
            cfg.updated_at = time.time()
            self._store.set_flag(cfg, actor_id, reason, tenant_id)
            self._step_history.setdefault(key, []).append(RolloutStep(pct=cfg.rollout_pct))
            self._paused.discard(key)
            return cfg

    def step_up(self, key, actor_id, reason, target_pct=None, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for step_up")
        with self._lock:
            if key in self._paused:
                raise RuntimeError(f"Rollout for {key.value} is paused - resume first")
            cfg = self._store.get_flag(key)
            if cfg is None:
                raise KeyError(f"Flag {key.value} not found")
            if target_pct is not None:
                new_pct = max(cfg.rollout_pct, min(100.0, target_pct))
            else:
                new_pct = cfg.rollout_pct
                for s in self.DEFAULT_STEPS:
                    if s > cfg.rollout_pct:
                        new_pct = s
                        break
                else:
                    new_pct = 100.0
            cfg.rollout_pct = new_pct
            cfg.updated_at = time.time()
            self._store.set_flag(cfg, actor_id, reason, tenant_id)
            self._step_history.setdefault(key, []).append(RolloutStep(pct=new_pct))
            return cfg

    def step_down(self, key, actor_id, reason, target_pct=None, tenant_id=None):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for step_down")
        with self._lock:
            cfg = self._store.get_flag(key)
            if cfg is None:
                raise KeyError(f"Flag {key.value} not found")
            if target_pct is not None:
                new_pct = max(0.0, min(cfg.rollout_pct, target_pct))
            else:
                new_pct = cfg.rollout_pct
                for s in reversed(self.DEFAULT_STEPS):
                    if s < cfg.rollout_pct:
                        new_pct = s
                        break
                else:
                    new_pct = 0.0
            cfg.rollout_pct = new_pct
            cfg.updated_at = time.time()
            self._store.set_flag(cfg, actor_id, reason, tenant_id)
            self._step_history.setdefault(key, []).append(RolloutStep(pct=new_pct))
            return cfg

    def pause(self, key, actor_id, reason):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for pause")
        with self._lock:
            self._paused.add(key)
            self._store.audit.record(flag_key=key.value, action="rollout_pause",
                                     actor_id=actor_id, reason=reason, payload={})

    def resume(self, key, actor_id, reason):
        if not reason or not reason.strip():
            raise ValueError("reason is mandatory for resume")
        with self._lock:
            self._paused.discard(key)
            self._store.audit.record(flag_key=key.value, action="rollout_resume",
                                     actor_id=actor_id, reason=reason, payload={})

    def is_paused(self, key):
        with self._lock:
            return key in self._paused

    def history(self, key):
        with self._lock:
            return list(self._step_history.get(key, []))


MIGRATION_SQL = """
BEGIN;
CREATE TABLE IF NOT EXISTS feature_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key TEXT NOT NULL UNIQUE, enabled BOOLEAN NOT NULL DEFAULT FALSE,
    strategy TEXT NOT NULL DEFAULT 'none',
    rollout_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
    allowlist_users JSONB NOT NULL DEFAULT '[]',
    allowlist_tenants JSONB NOT NULL DEFAULT '[]',
    blocklist_users JSONB NOT NULL DEFAULT '[]',
    blocklist_tenants JSONB NOT NULL DEFAULT '[]',
    min_ring TEXT, min_plan TEXT, description TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT 'platform', tenant_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_rollout_pct CHECK (rollout_pct BETWEEN 0 AND 100),
    CONSTRAINT valid_strategy CHECK (strategy IN ('none','percentage','canary','ring','allowlist','blocklist'))
);
CREATE TABLE IF NOT EXISTS flag_kill_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key TEXT NOT NULL, actor_id TEXT NOT NULL, tenant_id TEXT,
    reason TEXT NOT NULL, ttl_seconds NUMERIC,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reason_not_empty CHECK (char_length(trim(reason)) > 0)
);
CREATE TABLE IF NOT EXISTS flag_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq BIGINT NOT NULL, flag_key TEXT NOT NULL, action TEXT NOT NULL,
    actor_id TEXT NOT NULL, tenant_id TEXT, reason TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}', ts DOUBLE PRECISION NOT NULL,
    chain_hash CHAR(64) NOT NULL, prev_hash CHAR(64) NOT NULL,
    CONSTRAINT reason_not_empty CHECK (char_length(trim(reason)) > 0),
    CONSTRAINT chain_hash_length CHECK (char_length(chain_hash) = 64)
);
CREATE TABLE IF NOT EXISTS flag_rollout_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key TEXT NOT NULL, rollout_pct NUMERIC(5,2) NOT NULL,
    actor_id TEXT NOT NULL, tenant_id TEXT, reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE OR REPLACE FUNCTION prevent_flag_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION 'flag_audit_log is append-only: % denied', TG_OP;
END; $$;
DROP TRIGGER IF EXISTS flag_audit_immutable ON flag_audit_log;
CREATE TRIGGER flag_audit_immutable BEFORE UPDATE OR DELETE ON flag_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_flag_audit_mutation();
ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_kill_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_rollout_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY flag_tenant_isolation ON feature_flags
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY kill_tenant_isolation ON flag_kill_overrides
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY audit_tenant_isolation ON flag_audit_log
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE POLICY rollout_tenant_isolation ON flag_rollout_history
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', TRUE));
CREATE INDEX IF NOT EXISTS idx_feature_flags_key ON feature_flags(flag_key);
CREATE INDEX IF NOT EXISTS idx_feature_flags_tenant ON feature_flags(tenant_id);
CREATE INDEX IF NOT EXISTS idx_flag_audit_flag_key ON flag_audit_log(flag_key, ts DESC);
CREATE INDEX IF NOT EXISTS idx_flag_audit_actor ON flag_audit_log(actor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_flag_audit_seq ON flag_audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_flag_kill_key ON flag_kill_overrides(flag_key);
CREATE INDEX IF NOT EXISTS idx_flag_rollout_key ON flag_rollout_history(flag_key, created_at DESC);
CREATE OR REPLACE FUNCTION cleanup_expired_kills() RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE deleted INTEGER; BEGIN
    DELETE FROM flag_kill_overrides WHERE ttl_seconds IS NOT NULL
      AND activated_at + (ttl_seconds * INTERVAL '1 second') < NOW();
    GET DIAGNOSTICS deleted = ROW_COUNT; RETURN deleted;
END; $$;
CREATE OR REPLACE VIEW vw_active_flag_kills AS
SELECT k.*, f.description, f.enabled FROM flag_kill_overrides k
LEFT JOIN feature_flags f ON f.flag_key = k.flag_key
WHERE k.ttl_seconds IS NULL OR k.activated_at + (k.ttl_seconds * INTERVAL '1 second') > NOW();
COMMIT;
"""

_global_audit = FlagAuditChain()
_global_store = AuditedFlagStore(audit_chain=_global_audit)
_global_rollout = GradualRolloutManager(_global_store)

def get_store(): return _global_store
def get_rollout(): return _global_rollout
def is_enabled(key, ctx): return _global_store.is_enabled(key, ctx)
