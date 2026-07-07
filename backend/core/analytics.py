"""
Phase 31 -- Operational Analytics & Business KPIs
==================================================
KPI collection: MRR / ARR / churn / subscription / heartbeat /
                payment-failure / risk-block / LTV / NRR / CAC
Admin dashboard: real-time business health snapshot
Anomaly detection: fraud / abuse / billing / trading spikes
Audit chain: every KPI write is HMAC-chained and tamper-evident
Fail-closed: degraded data raises AnalyticsError, never silently wrong
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)

class KPICategory(str, Enum):
    SUBSCRIPTION  = "subscription"
    REVENUE       = "revenue"
    CHURN         = "churn"
    PAYMENT       = "payment"
    RISK          = "risk"
    HEARTBEAT     = "heartbeat"
    FRAUD         = "fraud"
    LICENSE       = "license"
    SYSTEM        = "system"
    TENANT        = "tenant"

class KPIKey(str, Enum):
    MRR                  = "revenue.mrr"
    ARR                  = "revenue.arr"
    NRR                  = "revenue.nrr"
    LTV                  = "revenue.ltv"
    ARPU                 = "revenue.arpu"
    CAC                  = "revenue.cac"
    ACTIVE_SUBS          = "subscription.active"
    NEW_SUBS             = "subscription.new"
    CANCELLED_SUBS       = "subscription.cancelled"
    TRIAL_CONVERSIONS    = "subscription.trial_conversions"
    PLAN_UPGRADES        = "subscription.plan_upgrades"
    PLAN_DOWNGRADES      = "subscription.plan_downgrades"
    CHURN_RATE           = "churn.rate"
    REVENUE_CHURN        = "churn.revenue"
    GROSS_CHURN          = "churn.gross"
    PAYMENT_SUCCESS_RATE = "payment.success_rate"
    PAYMENT_FAILURES     = "payment.failures"
    PAYMENT_RECOVERY     = "payment.recovery"
    DUNNING_ACTIVE       = "payment.dunning_active"
    RISK_BLOCKS          = "risk.blocks"
    KILL_SWITCH_EVENTS   = "risk.kill_switch"
    DRAWDOWN_BREACHES    = "risk.drawdown"
    HEARTBEAT_MISS       = "heartbeat.miss"
    HEARTBEAT_OK         = "heartbeat.ok"
    FRAUD_FLAGS          = "fraud.flags"
    ABUSE_BANS           = "fraud.bans"
    REPLAY_ATTACKS       = "fraud.replay"
    AUTH_FAILURES        = "fraud.auth_failures"
    LICENSE_ISSUED       = "license.issued"
    LICENSE_REVOKED      = "license.revoked"
    LICENSE_ACTIVE       = "license.active"
    LICENSE_EXPIRED      = "license.expired"
    API_ERROR_RATE       = "system.api_error_rate"
    P95_LATENCY_MS       = "system.p95_latency_ms"
    ACTIVE_TENANTS       = "system.active_tenants"

class AnomalyKind(str, Enum):
    SPIKE      = "spike"
    DROP       = "drop"
    FLATLINE   = "flatline"
    THRESHOLD  = "threshold"
    ZSCORE     = "zscore"

class AlertSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"

class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    CRITICAL  = "critical"
    UNKNOWN   = "unknown"

class AuditAction(str, Enum):
    KPI_RECORDED    = "kpi.recorded"
    KPI_SNAPSHOT    = "kpi.snapshot"
    ANOMALY_RAISED  = "anomaly.raised"
    ALERT_FIRED     = "alert.fired"
    DASHBOARD_READ  = "dashboard.read"
    THRESHOLD_SET   = "threshold.set"
    BASELINE_RESET  = "baseline.reset"

REQUIRES_REASON = {AuditAction.BASELINE_RESET, AuditAction.THRESHOLD_SET}

class AnalyticsError(Exception): pass
class MissingReasonError(AnalyticsError): pass
class AuditChainTampered(AnalyticsError): pass

@dataclass
class _AuditEntry:
    seq: int
    action: str
    actor: str
    kpi_key: str
    detail: dict
    reason: str
    ts: float
    chain_hash: str = ""

class AnalyticsAuditChain:
    _GENESIS_MSG = "GENESIS:ANALYTICS:CHAIN:V31"
    def __init__(self, secret: str = ""):
        self._secret = secret or os.urandom(32).hex()
        self._entries: List[_AuditEntry] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._prev_hash = self._hmac(self._GENESIS_MSG)
    def _hmac(self, msg: str) -> str:
        return hmac.new(self._secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    def record(self, action: AuditAction, actor: str = "system", kpi_key: str = "", reason: str = "", **detail) -> _AuditEntry:
        if action in REQUIRES_REASON:
            if not reason or not reason.strip():
                raise MissingReasonError(f"{action} requires reason")
        with self._lock:
            self._seq += 1
            ts_now = time.time()
            canonical = json.dumps({"seq": self._seq, "action": str(action), "actor": actor, "kpi_key": kpi_key, "reason": reason, "detail": detail, "ts": ts_now}, sort_keys=True)
            ch = self._hmac(self._prev_hash + ":" + canonical)
            entry = _AuditEntry(seq=self._seq, action=str(action), actor=actor, kpi_key=kpi_key, detail=detail, reason=reason, ts=ts_now, chain_hash=ch)
            self._prev_hash = ch
            self._entries.append(entry)
            return entry
    def verify_chain(self) -> bool:
        prev = self._hmac(self._GENESIS_MSG)
        for e in self._entries:
            canonical = json.dumps({"seq": e.seq, "action": e.action, "actor": e.actor, "kpi_key": e.kpi_key, "reason": e.reason, "detail": e.detail, "ts": e.ts}, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash): return False
            prev = e.chain_hash
        return True
    def detect_tampered(self) -> List[int]:
        broken = []
        prev = self._hmac(self._GENESIS_MSG)
        for e in self._entries:
            canonical = json.dumps({"seq": e.seq, "action": e.action, "actor": e.actor, "kpi_key": e.kpi_key, "reason": e.reason, "detail": e.detail, "ts": e.ts}, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash): broken.append(e.seq)
            prev = e.chain_hash
        return broken
    def query(self, action=None, kpi_key: str = "", limit: int = 50) -> List[_AuditEntry]:
        with self._lock: res = list(self._entries)
        if action is not None: res = [e for e in res if e.action == str(action)]
        if kpi_key: res = [e for e in res if e.kpi_key == kpi_key]
        return list(reversed(res))[:max(0, limit)]
    def __len__(self) -> int: return len(self._entries)

@dataclass
class KPIDataPoint:
    id: str
    kpi_key: str
    category: str
    value: float
    tenant_id: str
    period: str
    recorded_at: float
    meta: dict = field(default_factory=dict)

class KPIStore:
    def __init__(self, maxlen: int = 10_000):
        self._data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=maxlen))
        self._lock = threading.Lock()
    def record(self, point: KPIDataPoint) -> None:
        with self._lock: self._data[f"{point.tenant_id}:{point.kpi_key}"].append(point)
    def latest(self, kpi_key: str, tenant_id: str = "global", n: int = 1) -> List[KPIDataPoint]:
        with self._lock: data = list(self._data[f"{tenant_id}:{kpi_key}"])
        data.sort(key=lambda p: p.recorded_at, reverse=True)
        return data[:n]
    def series(self, kpi_key: str, tenant_id: str = "global", since: float = 0.0, limit: int = 100) -> List[KPIDataPoint]:
        with self._lock: data = list(self._data[f"{tenant_id}:{kpi_key}"])
        data = [p for p in data if p.recorded_at >= since]
        data.sort(key=lambda p: p.recorded_at)
        return data[-limit:]
    def sum_period(self, kpi_key: str, period: str, tenant_id: str = "global") -> float:
        with self._lock: data = list(self._data[f"{tenant_id}:{kpi_key}"])
        return sum(p.value for p in data if p.period == period)
    def all_tenants(self) -> List[str]:
        with self._lock: keys = list(self._data.keys())
        return list({k.split(":")[0] for k in keys})
    def total_records(self) -> int:
        with self._lock: return sum(len(v) for v in self._data.values())

class KPIEngine:
    def __init__(self, store: KPIStore, audit=None):
        self._store = store; self._audit = audit; self._lock = threading.Lock()
    def _period(self, ts=None) -> str:
        import datetime as _dt
        d = _dt.datetime.utcfromtimestamp(ts or time.time())
        return f"{d.year}-{d.month:02d}"
    def _record(self, kpi_key, value, tenant_id, meta):
        cat_map = {"revenue": KPICategory.REVENUE,"subscription": KPICategory.SUBSCRIPTION,"churn": KPICategory.CHURN,"payment": KPICategory.PAYMENT,"risk": KPICategory.RISK,"heartbeat": KPICategory.HEARTBEAT,"fraud": KPICategory.FRAUD,"license": KPICategory.LICENSE,"system": KPICategory.SYSTEM}
        category = cat_map.get(kpi_key.value.split(".")[0], KPICategory.SYSTEM)
        pt = KPIDataPoint(id=str(uuid.uuid4()), kpi_key=kpi_key.value, category=category.value, value=value, tenant_id=tenant_id, period=self._period(), recorded_at=time.time(), meta=meta)
        self._store.record(pt)
        if self._audit is not None: self._audit.record(AuditAction.KPI_RECORDED, kpi_key=kpi_key.value, value=value, tenant_id=tenant_id)
        return pt
    def record_mrr(self, amount, tenant_id="global", **meta): return self._record(KPIKey.MRR, amount, tenant_id, meta)
    def record_arr(self, amount, tenant_id="global", **meta): return self._record(KPIKey.ARR, amount, tenant_id, meta)
    def compute_arr_from_mrr(self, tenant_id="global"):
        pts = self._store.latest(KPIKey.MRR.value, tenant_id, n=1)
        return pts[0].value * 12 if pts else 0.0
    def record_nrr(self, rate, tenant_id="global", **meta): return self._record(KPIKey.NRR, rate, tenant_id, meta)
    def record_arpu(self, amount, tenant_id="global", **meta): return self._record(KPIKey.ARPU, amount, tenant_id, meta)
    def record_ltv(self, amount, tenant_id="global", **meta): return self._record(KPIKey.LTV, amount, tenant_id, meta)
    def record_cac(self, amount, tenant_id="global", **meta): return self._record(KPIKey.CAC, amount, tenant_id, meta)
    def compute_ltv_cac_ratio(self, tenant_id="global"):
        ltv = self._store.latest(KPIKey.LTV.value, tenant_id, 1)
        cac = self._store.latest(KPIKey.CAC.value, tenant_id, 1)
        if not ltv or not cac or cac[0].value == 0: return None
        return round(ltv[0].value / cac[0].value, 2)
    def record_active_subs(self, count, tenant_id="global", **meta): return self._record(KPIKey.ACTIVE_SUBS, float(count), tenant_id, meta)
    def record_new_subs(self, count, tenant_id="global", **meta): return self._record(KPIKey.NEW_SUBS, float(count), tenant_id, meta)
    def record_cancelled_subs(self, count, tenant_id="global", **meta): return self._record(KPIKey.CANCELLED_SUBS, float(count), tenant_id, meta)
    def record_trial_conversion(self, count, tenant_id="global", **meta): return self._record(KPIKey.TRIAL_CONVERSIONS, float(count), tenant_id, meta)
    def record_plan_upgrade(self, count, tenant_id="global", **meta): return self._record(KPIKey.PLAN_UPGRADES, float(count), tenant_id, meta)
    def record_plan_downgrade(self, count, tenant_id="global", **meta): return self._record(KPIKey.PLAN_DOWNGRADES, float(count), tenant_id, meta)
    def record_churn_rate(self, rate, tenant_id="global", **meta): return self._record(KPIKey.CHURN_RATE, rate, tenant_id, meta)
    def record_revenue_churn(self, amount, tenant_id="global", **meta): return self._record(KPIKey.REVENUE_CHURN, amount, tenant_id, meta)
    def compute_churn_rate(self, lost, start):
        if start == 0: return 0.0
        return round(lost / start * 100, 4)
    def record_payment_success_rate(self, rate, tenant_id="global", **meta): return self._record(KPIKey.PAYMENT_SUCCESS_RATE, rate, tenant_id, meta)
    def record_payment_failure(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.PAYMENT_FAILURES, float(count), tenant_id, meta)
    def record_payment_recovery(self, amount, tenant_id="global", **meta): return self._record(KPIKey.PAYMENT_RECOVERY, amount, tenant_id, meta)
    def record_dunning_active(self, count, tenant_id="global", **meta): return self._record(KPIKey.DUNNING_ACTIVE, float(count), tenant_id, meta)
    def record_risk_block(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.RISK_BLOCKS, float(count), tenant_id, meta)
    def record_kill_switch_event(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.KILL_SWITCH_EVENTS, float(count), tenant_id, meta)
    def record_drawdown_breach(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.DRAWDOWN_BREACHES, float(count), tenant_id, meta)
    def record_heartbeat_miss(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.HEARTBEAT_MISS, float(count), tenant_id, meta)
    def record_heartbeat_ok(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.HEARTBEAT_OK, float(count), tenant_id, meta)
    def record_fraud_flag(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.FRAUD_FLAGS, float(count), tenant_id, meta)
    def record_abuse_ban(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.ABUSE_BANS, float(count), tenant_id, meta)
    def record_replay_attack(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.REPLAY_ATTACKS, float(count), tenant_id, meta)
    def record_auth_failure(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.AUTH_FAILURES, float(count), tenant_id, meta)
    def record_license_issued(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.LICENSE_ISSUED, float(count), tenant_id, meta)
    def record_license_revoked(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.LICENSE_REVOKED, float(count), tenant_id, meta)
    def record_license_active(self, count, tenant_id="global", **meta): return self._record(KPIKey.LICENSE_ACTIVE, float(count), tenant_id, meta)
    def record_license_expired(self, count=1, tenant_id="global", **meta): return self._record(KPIKey.LICENSE_EXPIRED, float(count), tenant_id, meta)
    def record_api_error_rate(self, rate, tenant_id="global", **meta): return self._record(KPIKey.API_ERROR_RATE, rate, tenant_id, meta)
    def record_p95_latency(self, ms, tenant_id="global", **meta): return self._record(KPIKey.P95_LATENCY_MS, ms, tenant_id, meta)
    def record_active_tenants(self, count, tenant_id="global", **meta): return self._record(KPIKey.ACTIVE_TENANTS, float(count), tenant_id, meta)

@dataclass
class AnomalyEvent:
    id: str; kpi_key: str; kind: AnomalyKind; severity: AlertSeverity
    value: float; expected: float; zscore: float; tenant_id: str
    detected_at: float; message: str

class AnomalyDetector:
    DEFAULT_THRESHOLDS = {
        KPIKey.CHURN_RATE.value: {"warn": 5.0, "crit": 10.0},
        KPIKey.PAYMENT_FAILURES.value: {"warn": 5.0, "crit": 20.0},
        KPIKey.RISK_BLOCKS.value: {"warn": 3.0, "crit": 10.0},
        KPIKey.KILL_SWITCH_EVENTS.value: {"warn": 1.0, "crit": 3.0},
        KPIKey.FRAUD_FLAGS.value: {"warn": 5.0, "crit": 15.0},
        KPIKey.ABUSE_BANS.value: {"warn": 3.0, "crit": 10.0},
        KPIKey.REPLAY_ATTACKS.value: {"warn": 2.0, "crit": 5.0},
        KPIKey.AUTH_FAILURES.value: {"warn": 10.0, "crit": 50.0},
        KPIKey.API_ERROR_RATE.value: {"warn": 1.0, "crit": 5.0},
        KPIKey.P95_LATENCY_MS.value: {"warn": 500.0, "crit": 2000.0},
        KPIKey.HEARTBEAT_MISS.value: {"warn": 1.0, "crit": 3.0},
        KPIKey.DRAWDOWN_BREACHES.value: {"warn": 1.0, "crit": 3.0},
    }
    def __init__(self, zscore_threshold=3.0, window=30, thresholds=None, audit=None):
        self._zscore_threshold = zscore_threshold; self._window = window
        self._thresholds = copy.deepcopy(thresholds or self.DEFAULT_THRESHOLDS)
        self._audit = audit; self._history = defaultdict(lambda: deque(maxlen=window))
        self._events: deque = deque(maxlen=1000); self._hooks = []; self._lock = threading.Lock()
    def add_hook(self, fn): self._hooks.append(fn)
    def set_threshold(self, kpi_key, warn, crit, actor="admin", reason=""):
        with self._lock: self._thresholds[kpi_key] = {"warn": warn, "crit": crit}
        if self._audit is not None: self._audit.record(AuditAction.THRESHOLD_SET, actor=actor, kpi_key=kpi_key, reason=reason, warn=warn, crit=crit)
    def feed(self, kpi_key, value, tenant_id="global"):
        tk = f"{tenant_id}:{kpi_key}"
        with self._lock: hist = list(self._history[tk]); self._history[tk].append(value)
        anomaly = self._check_zscore(kpi_key, value, hist, tenant_id)
        if anomaly is None: anomaly = self._check_threshold(kpi_key, value, tenant_id)
        if anomaly is not None:
            with self._lock: self._events.append(anomaly)
            if self._audit is not None: self._audit.record(AuditAction.ANOMALY_RAISED, kpi_key=kpi_key, kind=anomaly.kind.value, severity=anomaly.severity.value, value=value, tenant_id=tenant_id)
            for hook in self._hooks:
                try: hook(anomaly)
                except Exception as exc:
                    _LOG.warning('anomaly hook error: %s', exc)
        return anomaly
    def _check_zscore(self, kpi_key, value, hist, tenant_id):
        if len(hist) < 5: return None
        mean = sum(hist) / len(hist)
        variance = sum((x - mean)**2 for x in hist) / len(hist)
        std = math.sqrt(variance)
        if std == 0:
            if value != mean: z = self._zscore_threshold + 1.0
            else: return None
        else: z = abs(value - mean) / std
        if z < self._zscore_threshold: return None
        sev = AlertSeverity.CRITICAL if z > self._zscore_threshold * 1.5 else AlertSeverity.WARNING
        kind = AnomalyKind.SPIKE if value > mean else AnomalyKind.DROP
        return AnomalyEvent(id=str(uuid.uuid4()), kpi_key=kpi_key, kind=kind, severity=sev, value=value, expected=round(mean,4), zscore=round(z,4), tenant_id=tenant_id, detected_at=time.time(), message=f"Z-score {z:.2f} on {kpi_key}")
    def _check_threshold(self, kpi_key, value, tenant_id):
        th = self._thresholds.get(kpi_key)
        if th is None: return None
        crit = th.get("crit", float("inf")); warn = th.get("warn", float("inf"))
        if value >= crit: sev = AlertSeverity.CRITICAL
        elif value >= warn: sev = AlertSeverity.WARNING
        else: return None
        return AnomalyEvent(id=str(uuid.uuid4()), kpi_key=kpi_key, kind=AnomalyKind.THRESHOLD, severity=sev, value=value, expected=warn, zscore=0.0, tenant_id=tenant_id, detected_at=time.time(), message=f"Threshold breach on {kpi_key}: {value}")
    def check_flatline(self, kpi_key, last_seen_ts, expected_interval_s, tenant_id="global"):
        age = time.time() - last_seen_ts
        if age <= expected_interval_s: return None
        sev = AlertSeverity.CRITICAL if age > expected_interval_s * 3 else AlertSeverity.WARNING
        ev = AnomalyEvent(id=str(uuid.uuid4()), kpi_key=kpi_key, kind=AnomalyKind.FLATLINE, severity=sev, value=0.0, expected=expected_interval_s, zscore=0.0, tenant_id=tenant_id, detected_at=time.time(), message=f"Flatline on {kpi_key}: no data for {age:.0f}s")
        with self._lock: self._events.append(ev)
        return ev
    def recent_anomalies(self, limit=20, severity=None, kpi_key=""):
        with self._lock: events = list(self._events)
        if severity is not None: events = [e for e in events if e.severity == severity]
        if kpi_key: events = [e for e in events if e.kpi_key == kpi_key]
        return list(reversed(events))[:limit]
    def reset_baseline(self, kpi_key, tenant_id="global", actor="admin", reason=""):
        tk = f"{tenant_id}:{kpi_key}"
        with self._lock: self._history[tk].clear()
        if self._audit is not None: self._audit.record(AuditAction.BASELINE_RESET, actor=actor, kpi_key=kpi_key, reason=reason, tenant_id=tenant_id)
    def anomaly_count(self):
        with self._lock: return len(self._events)

@dataclass
class HealthGate:
    name: str; status: HealthStatus; value: float; threshold: float; message: str

@dataclass
class BusinessHealthReport:
    status: HealthStatus; score: int; gates: List[HealthGate]
    critical_count: int; warning_count: int; snapshot_at: float
    tenant_id: str; anomalies: List[AnomalyEvent]

class BusinessHealthChecker:
    GATES = [
        {"name": "payment_success_rate", "kpi": KPIKey.PAYMENT_SUCCESS_RATE, "warn": 95.0, "crit": 85.0, "higher_is_better": True},
        {"name": "churn_rate",           "kpi": KPIKey.CHURN_RATE,           "warn": 5.0,  "crit": 10.0, "higher_is_better": False},
        {"name": "risk_blocks",          "kpi": KPIKey.RISK_BLOCKS,          "warn": 3.0,  "crit": 10.0, "higher_is_better": False},
        {"name": "heartbeat_miss",       "kpi": KPIKey.HEARTBEAT_MISS,       "warn": 1.0,  "crit": 3.0,  "higher_is_better": False},
        {"name": "fraud_flags",          "kpi": KPIKey.FRAUD_FLAGS,          "warn": 5.0,  "crit": 15.0, "higher_is_better": False},
        {"name": "api_error_rate",       "kpi": KPIKey.API_ERROR_RATE,       "warn": 1.0,  "crit": 5.0,  "higher_is_better": False},
        {"name": "nrr",                  "kpi": KPIKey.NRR,                  "warn": 100.0,"crit": 90.0, "higher_is_better": True},
        {"name": "kill_switch_events",   "kpi": KPIKey.KILL_SWITCH_EVENTS,   "warn": 1.0,  "crit": 3.0,  "higher_is_better": False},
    ]
    def __init__(self, store, detector, audit=None):
        self._store = store; self._detector = detector; self._audit = audit
    def check(self, tenant_id="global", actor="admin"):
        gates = []; critical = 0; warning = 0
        for g in self.GATES:
            kpi = g["kpi"]; pts = self._store.latest(kpi.value, tenant_id, n=1)
            if not pts:
                gates.append(HealthGate(name=g["name"], status=HealthStatus.UNKNOWN, value=0.0, threshold=g["crit"], message=f"No data"))
                continue
            val = pts[0].value; higher = g["higher_is_better"]
            if higher:
                if val < g["crit"]: s = HealthStatus.CRITICAL; critical += 1
                elif val < g["warn"]: s = HealthStatus.DEGRADED; warning += 1
                else: s = HealthStatus.HEALTHY
            else:
                if val >= g["crit"]: s = HealthStatus.CRITICAL; critical += 1
                elif val >= g["warn"]: s = HealthStatus.DEGRADED; warning += 1
                else: s = HealthStatus.HEALTHY
            gates.append(HealthGate(name=g["name"], status=s, value=val, threshold=g["crit"], message=f"{g['name']}={val}"))
        score = max(0, 100 - critical * 20 - warning * 5)
        overall = HealthStatus.CRITICAL if critical > 0 else (HealthStatus.DEGRADED if warning > 0 else HealthStatus.HEALTHY)
        report = BusinessHealthReport(status=overall, score=score, gates=gates, critical_count=critical, warning_count=warning, snapshot_at=time.time(), tenant_id=tenant_id, anomalies=self._detector.recent_anomalies(limit=10))
        if self._audit is not None: self._audit.record(AuditAction.DASHBOARD_READ, actor=actor, kpi_key="health_check", status=overall.value, score=score, tenant_id=tenant_id)
        return report

@dataclass
class DashboardSnapshot:
    tenant_id: str; period: str; mrr: float; arr: float; nrr: float
    active_subs: int; new_subs: int; churn_rate: float
    payment_success_rate: float; payment_failures: int
    risk_blocks: int; kill_switch_events: int; heartbeat_miss: int
    fraud_flags: int; abuse_bans: int; license_active: int
    api_error_rate: float; p95_latency_ms: float
    ltv_cac_ratio: Optional[float]; health: BusinessHealthReport
    top_anomalies: List[AnomalyEvent]; snapshot_at: float
    def to_dict(self):
        return {"tenant_id": self.tenant_id, "period": self.period,
            "revenue": {"mrr": self.mrr, "arr": self.arr, "nrr": self.nrr, "ltv_cac_ratio": self.ltv_cac_ratio},
            "subscriptions": {"active": self.active_subs, "new": self.new_subs, "churn_rate": self.churn_rate},
            "payments": {"success_rate": self.payment_success_rate, "failures": self.payment_failures},
            "risk": {"blocks": self.risk_blocks, "kill_switch_events": self.kill_switch_events, "heartbeat_miss": self.heartbeat_miss},
            "fraud": {"flags": self.fraud_flags, "bans": self.abuse_bans},
            "license": {"active": self.license_active},
            "system": {"api_error_rate": self.api_error_rate, "p95_latency_ms": self.p95_latency_ms},
            "health": {"status": self.health.status.value, "score": self.health.score, "critical_count": self.health.critical_count, "warning_count": self.health.warning_count},
            "anomalies": [{"kpi_key": a.kpi_key, "kind": a.kind.value, "severity": a.severity.value, "value": a.value} for a in self.top_anomalies],
            "snapshot_at": self.snapshot_at}

class AdminDashboard:
    def __init__(self, store, engine, detector, health_checker, audit=None):
        self._store = store; self._engine = engine; self._detector = detector
        self._health = health_checker; self._audit = audit
    def _get(self, kpi_key, tenant_id):
        pts = self._store.latest(kpi_key.value, tenant_id, n=1)
        return pts[0].value if pts else 0.0
    def snapshot(self, tenant_id="global", actor="admin"):
        import datetime; d = datetime.datetime.utcnow(); period = f"{d.year}-{d.month:02d}"
        health = self._health.check(tenant_id=tenant_id, actor=actor)
        anomalies = self._detector.recent_anomalies(limit=5)
        ltv_cac = self._engine.compute_ltv_cac_ratio(tenant_id)
        snap = DashboardSnapshot(tenant_id=tenant_id, period=period,
            mrr=self._get(KPIKey.MRR, tenant_id), arr=self._get(KPIKey.ARR, tenant_id),
            nrr=self._get(KPIKey.NRR, tenant_id), active_subs=int(self._get(KPIKey.ACTIVE_SUBS, tenant_id)),
            new_subs=int(self._get(KPIKey.NEW_SUBS, tenant_id)), churn_rate=self._get(KPIKey.CHURN_RATE, tenant_id),
            payment_success_rate=self._get(KPIKey.PAYMENT_SUCCESS_RATE, tenant_id),
            payment_failures=int(self._get(KPIKey.PAYMENT_FAILURES, tenant_id)),
            risk_blocks=int(self._get(KPIKey.RISK_BLOCKS, tenant_id)),
            kill_switch_events=int(self._get(KPIKey.KILL_SWITCH_EVENTS, tenant_id)),
            heartbeat_miss=int(self._get(KPIKey.HEARTBEAT_MISS, tenant_id)),
            fraud_flags=int(self._get(KPIKey.FRAUD_FLAGS, tenant_id)),
            abuse_bans=int(self._get(KPIKey.ABUSE_BANS, tenant_id)),
            license_active=int(self._get(KPIKey.LICENSE_ACTIVE, tenant_id)),
            api_error_rate=self._get(KPIKey.API_ERROR_RATE, tenant_id),
            p95_latency_ms=self._get(KPIKey.P95_LATENCY_MS, tenant_id),
            ltv_cac_ratio=ltv_cac, health=health, top_anomalies=anomalies, snapshot_at=time.time())
        if self._audit is not None: self._audit.record(AuditAction.KPI_SNAPSHOT, actor=actor, kpi_key="dashboard_snapshot", tenant_id=tenant_id, mrr=snap.mrr, health_status=health.status.value)
        return snap
    def mrr_trend(self, tenant_id="global", periods=6):
        return [{"period": p.period, "mrr": p.value, "ts": p.recorded_at} for p in self._store.series(KPIKey.MRR.value, tenant_id, limit=periods)]
    def churn_trend(self, tenant_id="global", periods=6):
        return [{"period": p.period, "churn_rate": p.value, "ts": p.recorded_at} for p in self._store.series(KPIKey.CHURN_RATE.value, tenant_id, limit=periods)]
    def fraud_summary(self, tenant_id="global"):
        return {"fraud_flags": int(self._get(KPIKey.FRAUD_FLAGS, tenant_id)), "abuse_bans": int(self._get(KPIKey.ABUSE_BANS, tenant_id)), "replay_attacks": int(self._get(KPIKey.REPLAY_ATTACKS, tenant_id)), "auth_failures": int(self._get(KPIKey.AUTH_FAILURES, tenant_id)), "anomalies": [e for e in self._detector.recent_anomalies(limit=20) if e.kpi_key in (KPIKey.FRAUD_FLAGS.value, KPIKey.ABUSE_BANS.value, KPIKey.REPLAY_ATTACKS.value, KPIKey.AUTH_FAILURES.value)]}
    def risk_summary(self, tenant_id="global"):
        return {"risk_blocks": int(self._get(KPIKey.RISK_BLOCKS, tenant_id)), "kill_switch_events": int(self._get(KPIKey.KILL_SWITCH_EVENTS, tenant_id)), "drawdown_breaches": int(self._get(KPIKey.DRAWDOWN_BREACHES, tenant_id)), "heartbeat_miss": int(self._get(KPIKey.HEARTBEAT_MISS, tenant_id))}
    def payment_summary(self, tenant_id="global"):
        return {"payment_success_rate": self._get(KPIKey.PAYMENT_SUCCESS_RATE, tenant_id), "payment_failures": int(self._get(KPIKey.PAYMENT_FAILURES, tenant_id)), "dunning_active": int(self._get(KPIKey.DUNNING_ACTIVE, tenant_id)), "payment_recovery": self._get(KPIKey.PAYMENT_RECOVERY, tenant_id)}
    def multi_tenant_summary(self):
        return [{"tenant_id": t, "mrr": self._get(KPIKey.MRR, t), "active_subs": int(self._get(KPIKey.ACTIVE_SUBS, t)), "churn_rate": self._get(KPIKey.CHURN_RATE, t)} for t in self._store.all_tenants() if t != "global"]

def build_analytics_system(secret="", zscore_threshold=3.0, thresholds=None):
    audit = AnalyticsAuditChain(secret=secret)
    store = KPIStore()
    engine = KPIEngine(store=store, audit=audit)
    detector = AnomalyDetector(zscore_threshold=zscore_threshold, thresholds=thresholds, audit=audit)
    health_checker = BusinessHealthChecker(store=store, detector=detector, audit=audit)
    dashboard = AdminDashboard(store=store, engine=engine, detector=detector, health_checker=health_checker, audit=audit)
    return {"audit": audit, "store": store, "engine": engine, "detector": detector, "health_checker": health_checker, "dashboard": dashboard}
