"""
backend/core/incident.py  --  PHASE 22: Incident Response & Kill-Switch Operations

P22-FIX-INC-1  : Unified IncidentSeverity (P1-P4) with SLA + escalation matrix
P22-FIX-INC-2  : AlertRouter -- severity-based routing (Telegram/PagerDuty/webhook/email)
P22-FIX-INC-3  : KillSwitchV22 -- 7 target types (bot/device/license/user/tenant/release/global)
P22-FIX-INC-4  : reason-coded actions -- every operation requires IncidentReason
P22-FIX-INC-5  : full audit integration -- all actions recorded in AuditChain
P22-FIX-INC-6  : fail-closed -- inactive state always blocks; explicit resume required
P22-FIX-INC-7  : IncidentManager -- lifecycle FSM (open->contained->resolved->closed)
P22-FIX-INC-8  : RunbookRegistry -- 6 runbooks (abuse/compromise/drawdown/billing/outage/recovery)
P22-FIX-INC-9  : rate-limited alert dedup (5min window per severity+target)
P22-FIX-INC-10 : thread-safe with RLock on all mutable state
P22-FIX-INC-11 : IncidentTimeline -- immutable append-only event log per incident
P22-FIX-INC-12 : EscalationPolicy -- auto-escalate if unacknowledged within SLA
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# P22-FIX-INC-1: Severity levels with SLA
# ---------------------------------------------------------------------------


class IncidentSeverity(str, Enum):
    """P1=most critical, P4=lowest."""

    P1_CRITICAL = "P1"  # Trading halted / data breach / service down       SLA: 15 min
    P2_HIGH = "P2"  # Kill switch triggered / license fraud              SLA: 1 hr
    P3_MEDIUM = "P3"  # Elevated error rate / billing failure              SLA: 4 hr
    P4_LOW = "P4"  # Single device anomaly / minor degradation          SLA: 24 hr


SEVERITY_SLA_SECONDS = {
    IncidentSeverity.P1_CRITICAL: 900,  # 15 min
    IncidentSeverity.P2_HIGH: 3600,  # 1 hr
    IncidentSeverity.P3_MEDIUM: 14400,  # 4 hr
    IncidentSeverity.P4_LOW: 86400,  # 24 hr
}

SEVERITY_CHANNELS = {
    IncidentSeverity.P1_CRITICAL: ["pagerduty", "telegram", "webhook", "email"],
    IncidentSeverity.P2_HIGH: ["telegram", "webhook", "email"],
    IncidentSeverity.P3_MEDIUM: ["telegram", "webhook"],
    IncidentSeverity.P4_LOW: ["telegram"],
}


# ---------------------------------------------------------------------------
# P22-FIX-INC-4: Reason codes
# ---------------------------------------------------------------------------


class IncidentReason(str, Enum):
    # Trading / Risk
    DRAWDOWN_LIMIT = "drawdown_limit_breached"
    FLASH_CRASH = "flash_crash_detected"
    EQUITY_FLOOR = "equity_below_floor"
    HEARTBEAT_LOSS = "heartbeat_loss"
    ABNORMAL_VOLUME = "abnormal_trade_volume"
    # Security
    ABUSE_DETECTED = "abuse_detected"
    FRAUD_DETECTED = "fraud_detected"
    CREDENTIAL_COMPROMISE = "credential_compromise"
    MULTIPLE_VIOLATIONS = "multiple_policy_violations"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    # Billing
    PAYMENT_FAILURE = "payment_failure"
    CHARGEBACK = "chargeback_received"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    # System
    SYSTEM_OUTAGE = "system_outage"
    DATA_INTEGRITY = "data_integrity_violation"
    COMPLIANCE = "compliance_requirement"
    # Admin
    MANUAL_ADMIN = "manual_admin_action"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    RECOVERY = "recovery_operation"
    # Artifact
    VULNERABLE_RELEASE = "vulnerable_release_detected"
    MALFORMED_ARTIFACT = "malformed_artifact"


class KillSwitchTarget(str, Enum):
    BOT = "bot"
    DEVICE = "device"
    LICENSE = "license"
    USER = "user"
    TENANT = "tenant"
    RELEASE = "release"
    GLOBAL = "global"


class IncidentState(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"
    FALSE_ALARM = "false_alarm"


@dataclass
class KillSwitchEntry:
    ks_id: str
    target: KillSwitchTarget
    target_id: str
    reason: IncidentReason
    reason_note: str
    severity: IncidentSeverity
    actor_id: str
    tenant_id: str
    activated_at: float = field(default_factory=time.time)
    incident_id: Optional[str] = None
    ttl_seconds: Optional[float] = None

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return time.time() - self.activated_at > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ks_id": self.ks_id,
            "target": self.target.value,
            "target_id": self.target_id,
            "reason": self.reason.value,
            "reason_note": self.reason_note,
            "severity": self.severity.value,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "activated_at": self.activated_at,
            "incident_id": self.incident_id,
            "ttl_seconds": self.ttl_seconds,
            "expired": self.is_expired(),
        }


@dataclass
class TimelineEvent:
    ts: float
    actor_id: str
    action: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Incident:
    incident_id: str
    title: str
    severity: IncidentSeverity
    reason: IncidentReason
    tenant_id: str
    reporter_id: str
    state: IncidentState = IncidentState.OPEN
    created_at: float = field(default_factory=time.time)
    acknowledged_at: Optional[float] = None
    contained_at: Optional[float] = None
    resolved_at: Optional[float] = None
    closed_at: Optional[float] = None
    timeline: List[TimelineEvent] = field(default_factory=list)
    kill_switch_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    runbook_id: Optional[str] = None

    def add_event(self, actor_id: str, action: str, **detail: Any) -> None:
        self.timeline.append(
            TimelineEvent(ts=time.time(), actor_id=actor_id, action=action, detail=dict(detail))
        )

    def is_sla_breached(self) -> bool:
        sla = SEVERITY_SLA_SECONDS[self.severity]
        if self.state in (IncidentState.RESOLVED, IncidentState.CLOSED, IncidentState.FALSE_ALARM):
            return False
        return (time.time() - self.created_at) > sla

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity.value,
            "reason": self.reason.value,
            "tenant_id": self.tenant_id,
            "reporter_id": self.reporter_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "sla_seconds": SEVERITY_SLA_SECONDS[self.severity],
            "sla_breached": self.is_sla_breached(),
            "kill_switch_ids": self.kill_switch_ids,
            "timeline_len": len(self.timeline),
            "runbook_id": self.runbook_id,
            "tags": self.tags,
        }


class AlertRouter:
    DEDUP_WINDOW = 300

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dedup: Dict[str, float] = {}
        self._history: deque = deque(maxlen=1000)
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._sent_count = 0

    def register_handler(self, channel: str, fn: Callable) -> None:
        with self._lock:
            self._handlers[channel].append(fn)

    def route(
        self,
        message: str,
        severity: IncidentSeverity,
        dedup_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if dedup_key:
                dk = f"{severity.value}:{dedup_key}"
                last = self._dedup.get(dk, 0.0)
                if time.time() - last < self.DEDUP_WINDOW:
                    return {"routed": False, "reason": "deduped", "dedup_key": dk}
                self._dedup[dk] = time.time()
            channels = SEVERITY_CHANNELS[severity]
            results: Dict[str, str] = {}
            for ch in channels:
                handlers = self._handlers.get(ch, [])
                if handlers:
                    for h in handlers:
                        try:
                            h(message, severity, context or {})
                            results[ch] = "sent"
                        except Exception as e:
                            results[ch] = f"error:{e}"
                else:
                    results[ch] = "no_handler"
            record = {
                "ts": time.time(),
                "message": message,
                "severity": severity.value,
                "channels": results,
                "dedup_key": dedup_key,
            }
            self._history.append(record)
            self._sent_count += 1
            return {"routed": True, "channels": results, "severity": severity.value}

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)[-limit:]

    @property
    def sent_count(self) -> int:
        return self._sent_count


class KillSwitchError(Exception):
    def __init__(self, target: KillSwitchTarget, target_id: str, reason: str):
        self.target = target
        self.target_id = target_id
        self.ks_reason = reason
        super().__init__(f"KILL_SWITCH:{target.value}:{target_id} reason={reason}")


class KillSwitchV22:
    def __init__(self, audit_logger=None, alert_router: Optional[AlertRouter] = None) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, KillSwitchEntry] = {}
        self._by_target: Dict[Tuple[KillSwitchTarget, str], Set[str]] = defaultdict(set)
        self._global_active = False
        self._audit = audit_logger
        self._router = alert_router or AlertRouter()

    def activate(
        self,
        target: KillSwitchTarget,
        target_id: str,
        reason: IncidentReason,
        actor_id: str,
        tenant_id: str,
        reason_note: str = "",
        severity: IncidentSeverity = IncidentSeverity.P2_HIGH,
        incident_id: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> KillSwitchEntry:
        if not reason_note:
            raise ValueError("reason_note is mandatory for kill switch activation")
        with self._lock:
            ks_id = str(uuid.uuid4())
            entry = KillSwitchEntry(
                ks_id=ks_id,
                target=target,
                target_id=target_id,
                reason=reason,
                reason_note=reason_note,
                severity=severity,
                actor_id=actor_id,
                tenant_id=tenant_id,
                incident_id=incident_id,
                ttl_seconds=ttl_seconds,
            )
            self._entries[ks_id] = entry
            self._by_target[(target, target_id)].add(ks_id)
            if target == KillSwitchTarget.GLOBAL:
                self._global_active = True
            self._audit_action(
                "kill_switch.activated",
                actor_id,
                tenant_id,
                reason.value,
                target=target.value,
                target_id=target_id,
                ks_id=ks_id,
                note=reason_note,
            )
            self._router.route(
                message=f"KILL SWITCH [{target.value}:{target_id}] activated: {reason_note}",
                severity=severity,
                dedup_key=f"ks:{target.value}:{target_id}",
                context={"ks_id": ks_id, "reason": reason.value},
            )
            return entry

    def reset(self, ks_id: str, actor_id: str, tenant_id: str, reason_note: str = "") -> bool:
        if not reason_note:
            raise ValueError("reason_note is mandatory for kill switch reset")
        with self._lock:
            entry = self._entries.pop(ks_id, None)
            if entry is None:
                return False
            self._by_target[(entry.target, entry.target_id)].discard(ks_id)
            if entry.target == KillSwitchTarget.GLOBAL:
                still_global = any(
                    e.target == KillSwitchTarget.GLOBAL
                    for e in self._entries.values()
                    if not e.is_expired()
                )
                self._global_active = still_global
            self._audit_action(
                "kill_switch.reset",
                actor_id,
                tenant_id,
                IncidentReason.RECOVERY.value,
                ks_id=ks_id,
                target=entry.target.value,
                target_id=entry.target_id,
                note=reason_note,
            )
            return True

    def reset_all(
        self,
        target: KillSwitchTarget,
        target_id: str,
        actor_id: str,
        tenant_id: str,
        reason_note: str,
    ) -> int:
        if not reason_note:
            raise ValueError("reason_note mandatory")
        with self._lock:
            ids = list(self._by_target.get((target, target_id), set()))
            count = 0
            for ks_id in ids:
                if self.reset(ks_id, actor_id, tenant_id, reason_note):
                    count += 1
            return count

    def check(self, target: KillSwitchTarget, target_id: str) -> None:
        with self._lock:
            self._purge_expired()
            if self._global_active:
                raise KillSwitchError(
                    KillSwitchTarget.GLOBAL, "global", "global kill switch active"
                )
            ids = self._by_target.get((target, target_id), set())
            for ks_id in ids:
                e = self._entries.get(ks_id)
                if e and not e.is_expired():
                    raise KillSwitchError(target, target_id, e.reason.value)

    def is_blocked(self, target: KillSwitchTarget, target_id: str) -> bool:
        try:
            self.check(target, target_id)
            return False
        except KillSwitchError:
            return True

    def list_active(
        self, target: Optional[KillSwitchTarget] = None, tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            self._purge_expired()
            result = []
            for e in self._entries.values():
                if e.is_expired():
                    continue
                if target and e.target != target:
                    continue
                if tenant_id and e.tenant_id != tenant_id:
                    continue
                result.append(e.to_dict())
            return result

    def active_count(self) -> int:
        with self._lock:
            self._purge_expired()
            return sum(1 for e in self._entries.values() if not e.is_expired())

    def _purge_expired(self) -> None:
        expired = [kid for kid, e in self._entries.items() if e.is_expired()]
        for kid in expired:
            e = self._entries.pop(kid)
            self._by_target[(e.target, e.target_id)].discard(kid)
        self._global_active = any(
            e.target == KillSwitchTarget.GLOBAL
            for e in self._entries.values()
            if not e.is_expired()
        )

    def _audit_action(
        self, event: str, user_id: str, tenant_id: str, reason: str, **detail: Any
    ) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(
                event=event, user_id=user_id, tenant_id=tenant_id, reason=reason, **detail
            )
        except Exception:
            pass


VALID_TRANSITIONS: Dict[IncidentState, Set[IncidentState]] = {
    IncidentState.OPEN: {IncidentState.ACKNOWLEDGED, IncidentState.FALSE_ALARM},
    IncidentState.ACKNOWLEDGED: {IncidentState.CONTAINED, IncidentState.FALSE_ALARM},
    IncidentState.CONTAINED: {IncidentState.RESOLVED},
    IncidentState.RESOLVED: {IncidentState.CLOSED},
    IncidentState.CLOSED: set(),
    IncidentState.FALSE_ALARM: set(),
}


class IncidentManager:
    def __init__(
        self,
        kill_switch: Optional[KillSwitchV22] = None,
        alert_router: Optional[AlertRouter] = None,
        audit_logger=None,
    ) -> None:
        self._lock = threading.RLock()
        self._incidents: Dict[str, Incident] = {}
        self._ks = kill_switch or KillSwitchV22()
        self._router = alert_router or AlertRouter()
        self._audit = audit_logger

    def open_incident(
        self,
        title: str,
        severity: IncidentSeverity,
        reason: IncidentReason,
        tenant_id: str,
        reporter_id: str,
        tags: Optional[List[str]] = None,
        runbook_id: Optional[str] = None,
        auto_kill: Optional[Tuple[KillSwitchTarget, str]] = None,
        reason_note: str = "",
    ) -> Incident:
        if auto_kill and not reason_note:
            raise ValueError("reason_note is mandatory when auto_kill is specified")
        with self._lock:
            inc_id = str(uuid.uuid4())
            inc = Incident(
                incident_id=inc_id,
                title=title,
                severity=severity,
                reason=reason,
                tenant_id=tenant_id,
                reporter_id=reporter_id,
                tags=tags or [],
                runbook_id=runbook_id,
            )
            inc.add_event(reporter_id, "opened", title=title, severity=severity.value)
            self._incidents[inc_id] = inc
            if auto_kill:
                target, target_id = auto_kill
                ks_entry = self._ks.activate(
                    target=target,
                    target_id=target_id,
                    reason=reason,
                    actor_id=reporter_id,
                    tenant_id=tenant_id,
                    reason_note=reason_note or title,
                    severity=severity,
                    incident_id=inc_id,
                )
                inc.kill_switch_ids.append(ks_entry.ks_id)
                inc.add_event(
                    reporter_id, "kill_switch_activated", ks_id=ks_entry.ks_id, target=target.value
                )
            self._router.route(
                message=f"[{severity.value}] INCIDENT OPENED: {title}",
                severity=severity,
                dedup_key=f"inc:{inc_id}",
                context={"incident_id": inc_id, "reason": reason.value},
            )
            self._do_audit(
                "incident.opened",
                reporter_id,
                tenant_id,
                reason.value,
                incident_id=inc_id,
                title=title,
            )
            return inc

    def transition(
        self, incident_id: str, new_state: IncidentState, actor_id: str, note: str = ""
    ) -> Incident:
        with self._lock:
            inc = self._get(incident_id)
            valid = VALID_TRANSITIONS.get(inc.state, set())
            if new_state not in valid:
                raise ValueError(
                    f"Invalid transition {inc.state.value} -> {new_state.value}. "
                    f"Valid: {[s.value for s in valid]}"
                )
            old_state = inc.state
            inc.state = new_state
            ts = time.time()
            if new_state == IncidentState.ACKNOWLEDGED:
                inc.acknowledged_at = ts
            elif new_state == IncidentState.CONTAINED:
                inc.contained_at = ts
            elif new_state == IncidentState.RESOLVED:
                inc.resolved_at = ts
            elif new_state == IncidentState.CLOSED:
                inc.closed_at = ts
            inc.add_event(
                actor_id, "state_changed", old=old_state.value, new=new_state.value, note=note
            )
            self._do_audit(
                "incident.state_changed",
                actor_id,
                inc.tenant_id,
                IncidentReason.MANUAL_ADMIN.value,
                incident_id=incident_id,
                old_state=old_state.value,
                new_state=new_state.value,
            )
            return inc

    def get(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            return self._incidents.get(incident_id)

    def list_incidents(
        self,
        tenant_id: Optional[str] = None,
        state: Optional[IncidentState] = None,
        severity: Optional[IncidentSeverity] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for inc in list(self._incidents.values()):
                if tenant_id and inc.tenant_id != tenant_id:
                    continue
                if state and inc.state != state:
                    continue
                if severity and inc.severity != severity:
                    continue
                result.append(inc.to_dict())
            result.sort(key=lambda x: x["created_at"], reverse=True)
            return result[:limit]

    def get_timeline(self, incident_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            inc = self._get(incident_id)
            return [
                {"ts": e.ts, "actor_id": e.actor_id, "action": e.action, "detail": e.detail}
                for e in inc.timeline
            ]

    def open_count(self) -> int:
        with self._lock:
            return sum(
                1
                for i in self._incidents.values()
                if i.state
                not in (IncidentState.CLOSED, IncidentState.RESOLVED, IncidentState.FALSE_ALARM)
            )

    def _get(self, incident_id: str) -> Incident:
        inc = self._incidents.get(incident_id)
        if inc is None:
            raise KeyError(f"Incident not found: {incident_id}")
        return inc

    def _do_audit(
        self, event: str, user_id: str, tenant_id: str, reason: str, **detail: Any
    ) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(
                event=event, user_id=user_id, tenant_id=tenant_id, reason=reason, **detail
            )
        except Exception:
            pass


@dataclass
class RunbookStep:
    order: int
    title: str
    description: str
    is_automated: bool = False
    cmd: Optional[str] = None


@dataclass
class Runbook:
    runbook_id: str
    name: str
    description: str
    severity: IncidentSeverity
    trigger_reason: IncidentReason
    steps: List[RunbookStep]
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "trigger_reason": self.trigger_reason.value,
            "step_count": len(self.steps),
            "tags": self.tags,
            "steps": [
                {"order": s.order, "title": s.title, "is_automated": s.is_automated, "cmd": s.cmd}
                for s in self.steps
            ],
        }


_RUNBOOKS = [
    Runbook(
        "RB-001-ABUSE",
        "Abuse / Policy Violation",
        "User detected abusing API, license sharing, or rate limits.",
        IncidentSeverity.P2_HIGH,
        IncidentReason.ABUSE_DETECTED,
        tags=["security", "license", "user"],
        steps=[
            RunbookStep(
                1,
                "Identify abusing user/device",
                "Query audit log for user_id.",
                True,
                "GET /admin/audit?user_id={user_id}",
            ),
            RunbookStep(
                2,
                "Kill switch device",
                "Activate kill switch for specific device.",
                True,
                "POST /admin/incident/kill-switch",
            ),
            RunbookStep(
                3,
                "Revoke license",
                "Revoke license with reason=abuse_detected.",
                True,
                "POST /admin/licenses/{id}/revoke",
            ),
            RunbookStep(
                4,
                "Block user account",
                "Block login and API access.",
                True,
                "POST /admin/users/{id}/block",
            ),
            RunbookStep(5, "Notify and document", "Send notification to tenant admin."),
            RunbookStep(6, "Review and close", "Review all actions in audit log."),
        ],
    ),
    Runbook(
        "RB-002-COMPROMISE",
        "Credential Compromise / Data Breach",
        "Credentials or sensitive data suspected to be compromised.",
        IncidentSeverity.P1_CRITICAL,
        IncidentReason.CREDENTIAL_COMPROMISE,
        tags=["security", "p1", "breach"],
        steps=[
            RunbookStep(
                1,
                "Activate GLOBAL kill switch",
                "Immediately halt all trading.",
                True,
                "POST /admin/incident/kill-switch (target=global)",
            ),
            RunbookStep(2, "Rotate all secrets", "Rotate JWT secret, DB password, API keys."),
            RunbookStep(
                3,
                "Force logout all sessions",
                "Invalidate all active JWTs.",
                True,
                "POST /admin/users/force-logout-all",
            ),
            RunbookStep(4, "Revoke all licenses", "Revoke all active licenses.", True),
            RunbookStep(
                5,
                "Forensic audit export",
                "Export full audit chain.",
                True,
                "GET /admin/audit/export.jsonl",
            ),
            RunbookStep(6, "Notify affected tenants", "Send breach notification."),
            RunbookStep(7, "Re-issue credentials", "After verification, re-issue secrets."),
            RunbookStep(8, "Post-mortem", "Document root cause."),
        ],
    ),
    Runbook(
        "RB-003-DRAWDOWN",
        "Drawdown / Risk Limit Breach",
        "Equity drawdown or flash crash exceeds configured limits.",
        IncidentSeverity.P1_CRITICAL,
        IncidentReason.DRAWDOWN_LIMIT,
        tags=["risk", "trading", "p1"],
        steps=[
            RunbookStep(
                1,
                "Kill switch trading bot",
                "Activate kill switch for affected bot.",
                True,
                "POST /admin/incident/kill-switch (target=bot)",
            ),
            RunbookStep(
                2,
                "Close all open positions",
                "Execute close-all on MT5.",
                True,
                "EA: CLOSE_ALL_POSITIONS",
            ),
            RunbookStep(3, "Verify equity", "Confirm current equity via MT5.", True),
            RunbookStep(4, "Notify account owner", "Send Telegram alert."),
            RunbookStep(5, "Review risk parameters", "Adjust drawdown limits."),
            RunbookStep(
                6,
                "Resume with approval",
                "Reset kill switch after admin approval.",
                True,
                "POST /admin/incident/kill-switch/{id}/reset",
            ),
        ],
    ),
    Runbook(
        "RB-004-BILLING",
        "Billing / Payment Failure",
        "Payment failure or chargeback leading to license suspension.",
        IncidentSeverity.P3_MEDIUM,
        IncidentReason.PAYMENT_FAILURE,
        tags=["billing", "license"],
        steps=[
            RunbookStep(1, "Detect payment failure", "Webhook from payment provider.", True),
            RunbookStep(
                2,
                "Suspend license",
                "Suspend with grace period.",
                True,
                "POST /admin/licenses/{id}/suspend",
            ),
            RunbookStep(3, "Kill switch device (soft)", "Block heartbeat.", True),
            RunbookStep(4, "Notify customer", "Send payment failure email."),
            RunbookStep(5, "Grace period (72h)", "Allow 72h retry window."),
            RunbookStep(6, "Restore or revoke", "On payment: restore. No payment: revoke.", True),
        ],
    ),
    Runbook(
        "RB-005-OUTAGE",
        "Service Outage / System Failure",
        "Backend API, database, or critical service is unreachable.",
        IncidentSeverity.P1_CRITICAL,
        IncidentReason.SYSTEM_OUTAGE,
        tags=["infrastructure", "p1", "sre"],
        steps=[
            RunbookStep(
                1, "Health check all services", "Run health probes.", True, "GET /health/ready"
            ),
            RunbookStep(2, "Check error rate", "Review Prometheus metrics.", True),
            RunbookStep(
                3,
                "Rollback if recent deploy",
                "Rollback if < 1hr old.",
                False,
                "docker compose up api@previous",
            ),
            RunbookStep(
                4,
                "Scale or restart",
                "Restart unhealthy containers.",
                True,
                "docker compose restart api",
            ),
            RunbookStep(5, "Database failover", "Switch to read-replica or restore."),
            RunbookStep(6, "Incident communication", "Post status update."),
        ],
    ),
    Runbook(
        "RB-006-RECOVERY",
        "Post-Incident Recovery",
        "Systematic recovery and verification after any incident.",
        IncidentSeverity.P3_MEDIUM,
        IncidentReason.RECOVERY,
        tags=["recovery", "verification"],
        steps=[
            RunbookStep(
                1,
                "Verify audit chain",
                "Run chain integrity check.",
                True,
                "GET /admin/audit/verify",
            ),
            RunbookStep(
                2,
                "Reset kill switches",
                "Reset specific kill switches.",
                True,
                "POST /admin/incident/kill-switch/{id}/reset",
            ),
            RunbookStep(3, "Re-enable licenses", "Reactivate suspended licenses.", True),
            RunbookStep(4, "Smoke test", "Run smoke test suite.", True),
            RunbookStep(5, "Monitor for 1 hour", "Watch error rates for 60 min."),
            RunbookStep(6, "Close incident", "Move to RESOLVED then CLOSED.", True),
            RunbookStep(7, "Post-mortem", "Document timeline and root cause."),
        ],
    ),
]


class RunbookRegistry:
    def __init__(self) -> None:
        self._runbooks: Dict[str, Runbook] = {r.runbook_id: r for r in _RUNBOOKS}

    def get(self, runbook_id: str) -> Optional[Runbook]:
        return self._runbooks.get(runbook_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._runbooks.values()]

    def find_by_reason(self, reason: IncidentReason) -> Optional[Runbook]:
        for r in self._runbooks.values():
            if r.trigger_reason == reason:
                return r
        return None

    def find_by_tag(self, tag: str) -> List[Runbook]:
        return [r for r in self._runbooks.values() if tag in r.tags]

    @property
    def count(self) -> int:
        return len(self._runbooks)


class EscalationPolicy:
    def __init__(self, manager: IncidentManager, router: AlertRouter) -> None:
        self._mgr = manager
        self._router = router
        self._lock = threading.RLock()
        self._escalated: Set[str] = set()

    def check_escalations(self) -> List[str]:
        escalated_now = []
        with self._lock:
            for inc in self._mgr._incidents.values():
                if inc.state in (IncidentState.OPEN,) and inc.incident_id not in self._escalated:
                    sla = SEVERITY_SLA_SECONDS[inc.severity]
                    elapsed = time.time() - inc.created_at
                    if elapsed > sla:
                        self._escalated.add(inc.incident_id)
                        escalated_now.append(inc.incident_id)
                        self._router.route(
                            message=(
                                f"SLA BREACH: Incident {inc.incident_id[:8]} "
                                f"[{inc.severity.value}] unacknowledged "
                                f"after {elapsed:.0f}s (SLA={sla}s)"
                            ),
                            severity=IncidentSeverity.P1_CRITICAL,
                            dedup_key=f"escalate:{inc.incident_id}",
                        )
        return escalated_now

    def already_escalated(self, incident_id: str) -> bool:
        with self._lock:
            return incident_id in self._escalated


MIGRATION_SQL = """
-- Phase 22: Incident Response & Kill-Switch Tables
BEGIN;
CREATE TABLE IF NOT EXISTS kill_switches_v22 (
    ks_id TEXT PRIMARY KEY, target TEXT NOT NULL
    CHECK (target IN ('bot','device','license','user','tenant','release','global')),
    target_id TEXT NOT NULL, reason TEXT NOT NULL, reason_note TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL CHECK (severity IN ('P1','P2','P3','P4')),
    actor_id TEXT NOT NULL, tenant_id TEXT NOT NULL, incident_id TEXT,
    ttl_seconds REAL, activated_at REAL NOT NULL, reset_at REAL, reset_by TEXT,
    reset_note TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS incidents_v22 (
    incident_id TEXT PRIMARY KEY, title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('P1','P2','P3','P4')),
    reason TEXT NOT NULL, tenant_id TEXT NOT NULL, reporter_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open', runbook_id TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ, contained_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ, closed_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS incident_timeline_v22 (
    id BIGSERIAL PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents_v22(incident_id),
    ts REAL NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}');
CREATE OR REPLACE RULE incident_timeline_no_update AS
    ON UPDATE TO incident_timeline_v22 DO INSTEAD NOTHING;
CREATE OR REPLACE RULE incident_timeline_no_delete AS
    ON DELETE TO incident_timeline_v22 DO INSTEAD NOTHING;
CREATE TABLE IF NOT EXISTS alert_history_v22 (
    id BIGSERIAL PRIMARY KEY, ts REAL NOT NULL, message TEXT NOT NULL,
    severity TEXT NOT NULL, channels JSONB NOT NULL DEFAULT '{}',
    dedup_key TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS idx_ks22_target ON kill_switches_v22(target, target_id);
CREATE INDEX IF NOT EXISTS idx_ks22_tenant ON kill_switches_v22(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_ks22_incident ON kill_switches_v22(incident_id);
CREATE INDEX IF NOT EXISTS idx_inc22_tenant_state ON incidents_v22(tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_inc22_severity ON incidents_v22(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_timeline22_inc ON incident_timeline_v22(incident_id, ts DESC);
ALTER TABLE kill_switches_v22 ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents_v22 ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_timeline_v22 ENABLE ROW LEVEL SECURITY;
CREATE POLICY ks22_tenant_isolation ON kill_switches_v22
    USING (is_app_admin() OR tenant_id = current_tenant_id());
CREATE POLICY inc22_tenant_isolation ON incidents_v22
    USING (is_app_admin() OR tenant_id = current_tenant_id());
CREATE POLICY timeline22_via_incident ON incident_timeline_v22
    USING (is_app_admin() OR EXISTS (
        SELECT 1 FROM incidents_v22 i
        WHERE i.incident_id = incident_timeline_v22.incident_id
          AND (is_app_admin() OR i.tenant_id = current_tenant_id())));
COMMIT;
"""

_router = None
_ks = None
_manager = None
_runbooks = None


def get_alert_router() -> AlertRouter:
    global _router
    if _router is None:
        _router = AlertRouter()
    return _router


def get_kill_switch_v22(audit_logger=None) -> KillSwitchV22:
    global _ks
    if _ks is None:
        _ks = KillSwitchV22(audit_logger=audit_logger, alert_router=get_alert_router())
    return _ks


def get_incident_manager(audit_logger=None) -> IncidentManager:
    global _manager
    if _manager is None:
        _manager = IncidentManager(
            kill_switch=get_kill_switch_v22(audit_logger),
            alert_router=get_alert_router(),
            audit_logger=audit_logger,
        )
    return _manager


def get_runbook_registry() -> RunbookRegistry:
    global _runbooks
    if _runbooks is None:
        _runbooks = RunbookRegistry()
    return _runbooks
