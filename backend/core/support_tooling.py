"""
Phase 33 -- Support Tooling & Controlled Intervention
=======================================================
Support-only views and controlled action tools.
Every action: authenticated, reason-mandatory, audited, fail-closed.

Classes:
  SupportRole             -- VIEWER / AGENT / LEAD / ADMIN + permissions
  SupportAuditChain       -- HMAC-SHA256 tamper-evident chain
  SupportSessionManager   -- impersonation sessions (time-limited, audited)
  DeviceResetManager      -- controlled device reset/unlock
  SubscriptionExtender    -- extend subscription with approval gate
  ArtifactResender        -- resend download link (rate-limited)
  AccountRecoveryManager  -- step-by-step account recovery
  SupportTicketEngine     -- ticket lifecycle (open/claim/resolve/escalate)
  SupportViewEngine       -- read-only views (customer/license/device/billing)
  SupportAdmin            -- summary, active-sessions, force-close
  build_support_system    -- factory
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
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SupportRole(str, Enum):
    VIEWER = "viewer"        # read-only views
    AGENT  = "agent"         # actions: reset/resend/ticket
    LEAD   = "lead"          # + extend subscription / account recovery
    ADMIN  = "admin"         # + impersonation / force-close sessions

    @property
    def can_impersonate(self) -> bool:
        return self == SupportRole.ADMIN

    @property
    def can_extend(self) -> bool:
        return self in (SupportRole.LEAD, SupportRole.ADMIN)

    @property
    def can_recover_account(self) -> bool:
        return self in (SupportRole.LEAD, SupportRole.ADMIN)

    @property
    def can_reset_device(self) -> bool:
        return self in (SupportRole.AGENT, SupportRole.LEAD, SupportRole.ADMIN)

    @property
    def can_resend_artifact(self) -> bool:
        return self in (SupportRole.AGENT, SupportRole.LEAD, SupportRole.ADMIN)

    @property
    def can_view(self) -> bool:
        return True  # all roles can view


class SupportAction(str, Enum):
    # Impersonation
    IMPERSONATION_START   = "impersonation_start"
    IMPERSONATION_END     = "impersonation_end"
    IMPERSONATION_DENIED  = "impersonation_denied"
    # Device
    DEVICE_RESET          = "device_reset"
    DEVICE_UNLOCK         = "device_unlock"
    DEVICE_RESET_DENIED   = "device_reset_denied"
    # Subscription
    SUB_EXTENDED          = "subscription_extended"
    SUB_EXTEND_DENIED     = "subscription_extend_denied"
    # Artifact
    ARTIFACT_RESENT       = "artifact_resent"
    ARTIFACT_RESEND_DENIED = "artifact_resend_denied"
    # Account recovery
    ACCOUNT_RECOVERY_START    = "account_recovery_start"
    ACCOUNT_RECOVERY_STEP     = "account_recovery_step"
    ACCOUNT_RECOVERY_COMPLETE = "account_recovery_complete"
    ACCOUNT_RECOVERY_ABORTED  = "account_recovery_aborted"
    # Ticket
    TICKET_OPENED     = "ticket_opened"
    TICKET_CLAIMED    = "ticket_claimed"
    TICKET_RESOLVED   = "ticket_resolved"
    TICKET_ESCALATED  = "ticket_escalated"
    TICKET_CLOSED     = "ticket_closed"
    # View
    VIEW_ACCESSED     = "view_accessed"


REQUIRES_REASON: set = {
    SupportAction.DEVICE_RESET,
    SupportAction.DEVICE_UNLOCK,
    SupportAction.SUB_EXTENDED,
    SupportAction.ACCOUNT_RECOVERY_ABORTED,
    SupportAction.IMPERSONATION_START,
    SupportAction.TICKET_ESCALATED,
}


class TicketStatus(str, Enum):
    OPEN       = "open"
    CLAIMED    = "claimed"
    RESOLVED   = "resolved"
    ESCALATED  = "escalated"
    CLOSED     = "closed"


class TicketPriority(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    URGENT = "urgent"


class RecoveryStep(str, Enum):
    VERIFY_IDENTITY   = "verify_identity"
    DISABLE_2FA       = "disable_2fa"
    RESET_PASSWORD    = "reset_password"
    REVOKE_SESSIONS   = "revoke_sessions"
    RESTORE_ACCESS    = "restore_access"
    NOTIFY_USER       = "notify_user"
    COMPLETE          = "complete"


RECOVERY_ORDER = [
    RecoveryStep.VERIFY_IDENTITY,
    RecoveryStep.DISABLE_2FA,
    RecoveryStep.RESET_PASSWORD,
    RecoveryStep.REVOKE_SESSIONS,
    RecoveryStep.RESTORE_ACCESS,
    RecoveryStep.NOTIFY_USER,
    RecoveryStep.COMPLETE,
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SupportError(Exception):
    """Implementation required."""
    pass

class InsufficientRoleError(SupportError):
    """Implementation required."""
    pass

class MissingReasonError(SupportError):
    """Implementation required."""
    pass

class ImpersonationDeniedError(SupportError):
    """Implementation required."""
    pass

class DeviceResetDeniedError(SupportError):
    """Implementation required."""
    pass

class ArtifactResendDeniedError(SupportError):
    """Implementation required."""
    pass

class RecoveryStepError(SupportError):
    """Implementation required."""
    pass

class RateLimitError(SupportError):
    """Implementation required."""
    pass


# ---------------------------------------------------------------------------
# Audit Chain
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    entry_id:   str
    action:     str
    actor:      str
    tenant_id:  str
    target_id:  str
    reason:     Optional[str]
    detail:     Dict[str, Any]
    ts:         float
    seq:        int
    chain_hash: str


class SupportAuditChain:
    """HMAC-SHA256 tamper-evident append-only audit log."""

    _GENESIS_MSG = "GENESIS:SUPPORT:TOOLING:CHAIN:V33"

    def __init__(self, secret: str = "") -> None:
        self._secret  = (secret or secrets.token_hex(32)).encode()
        self._entries: List[AuditEntry] = []
        self._lock    = threading.Lock()
        self._prev    = self._hmac(self._GENESIS_MSG)

    def record(
        self,
        action:    SupportAction,
        actor:     str,
        tenant_id: str,
        target_id: str,
        reason:    Optional[str] = None,
        **detail:  Any,
    ) -> AuditEntry:
        if action in REQUIRES_REASON:
            if not reason or not reason.strip():
                raise MissingReasonError(
                    f"reason is mandatory for action={action.value}"
                )
        ts_now = time.time()
        with self._lock:
            seq      = len(self._entries)
            entry_id = str(uuid.uuid4())
            canonical = json.dumps({
                "entry_id":  entry_id,
                "action":    action.value,
                "actor":     actor,
                "tenant_id": tenant_id,
                "target_id": target_id,
                "reason":    reason,
                "detail":    detail,
                "ts":        ts_now,
                "seq":       seq,
            }, sort_keys=True)
            chain_hash = self._hmac(self._prev + ":" + canonical)
            entry = AuditEntry(
                entry_id   = entry_id,
                action     = action.value,
                actor      = actor,
                tenant_id  = tenant_id,
                target_id  = target_id,
                reason     = reason,
                detail     = dict(detail),
                ts         = ts_now,
                seq        = seq,
                chain_hash = chain_hash,
            )
            self._entries.append(entry)
            self._prev = chain_hash
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            prev = self._hmac(self._GENESIS_MSG)
            for e in self._entries:
                canonical = json.dumps({
                    "entry_id":  e.entry_id,
                    "action":    e.action,
                    "actor":     e.actor,
                    "tenant_id": e.tenant_id,
                    "target_id": e.target_id,
                    "reason":    e.reason,
                    "detail":    e.detail,
                    "ts":        e.ts,
                    "seq":       e.seq,
                }, sort_keys=True)
                expected = self._hmac(prev + ":" + canonical)
                if not hmac.compare_digest(expected, e.chain_hash):
                    return False
                prev = e.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        broken: List[int] = []
        with self._lock:
            prev = self._hmac(self._GENESIS_MSG)
            for e in self._entries:
                canonical = json.dumps({
                    "entry_id":  e.entry_id,
                    "action":    e.action,
                    "actor":     e.actor,
                    "tenant_id": e.tenant_id,
                    "target_id": e.target_id,
                    "reason":    e.reason,
                    "detail":    e.detail,
                    "ts":        e.ts,
                    "seq":       e.seq,
                }, sort_keys=True)
                expected = self._hmac(prev + ":" + canonical)
                if not hmac.compare_digest(expected, e.chain_hash):
                    broken.append(e.seq)
                prev = e.chain_hash
        return broken

    def query(
        self,
        *,
        actor:     Optional[str] = None,
        action:    Optional[SupportAction] = None,
        target_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit:     int = 100,
    ) -> List[AuditEntry]:
        with self._lock:
            results = []
            for e in reversed(self._entries):
                if actor     and e.actor     != actor:         continue
                if action    and e.action    != action.value:  continue
                if target_id and e.target_id != target_id:     continue
                if tenant_id and e.tenant_id != tenant_id:     continue
                results.append(e)
                if len(results) >= limit:
                    break
            return results

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _hmac(self, msg: str) -> str:
        return hmac.new(self._secret, msg.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Support Session (impersonation)
# ---------------------------------------------------------------------------

@dataclass
class SupportSession:
    session_id:       str
    actor:            str
    target_user_id:   str
    tenant_id:        str
    role:             SupportRole
    reason:           str
    started_at:       float
    ttl_seconds:      int
    ended_at:         Optional[float] = None
    ticket_ref:       Optional[str]   = None
    mfa_verified:     bool = False

    @property
    def is_active(self) -> bool:
        if self.ended_at is not None:
            return False
        return (time.time() - self.started_at) < self.ttl_seconds

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at


class SupportSessionManager:
    DEFAULT_TTL = 1800

    def __init__(
        self,
        audit:        SupportAuditChain,
        *,
        require_mfa:  bool = True,
        max_ttl:      int  = 3600,
        default_ttl:  int  = DEFAULT_TTL,
    ) -> None:
        self._audit       = audit
        self._require_mfa = require_mfa
        self._max_ttl     = max_ttl
        self._default_ttl = default_ttl
        self._sessions:   Dict[str, SupportSession] = {}
        self._lock        = threading.Lock()

    def start_session(
        self,
        actor:          str,
        role:           SupportRole,
        target_user_id: str,
        tenant_id:      str,
        reason:         str,
        *,
        ticket_ref:     Optional[str] = None,
        mfa_verified:   bool = False,
        ttl_seconds:    int  = DEFAULT_TTL,
    ) -> SupportSession:
        if not role.can_impersonate:
            if self._audit is not None:
                self._audit.record(
                    SupportAction.IMPERSONATION_DENIED,
                    actor, tenant_id, target_user_id,
                    reason=f"insufficient_role:{role.value}",
                )
            raise InsufficientRoleError(
                f"role={role.value} cannot impersonate; ADMIN required"
            )
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for impersonation")
        if self._require_mfa and not mfa_verified:
            raise ImpersonationDeniedError("MFA verification required")
        ttl = min(ttl_seconds, self._max_ttl)
        with self._lock:
            for s in self._sessions.values():
                if s.actor == actor and s.is_active:
                    raise ImpersonationDeniedError(
                        f"agent {actor} already has an active session"
                    )
            session = SupportSession(
                session_id     = str(uuid.uuid4()),
                actor          = actor,
                target_user_id = target_user_id,
                tenant_id      = tenant_id,
                role           = role,
                reason         = reason,
                started_at     = time.time(),
                ttl_seconds    = ttl,
                ticket_ref     = ticket_ref,
                mfa_verified   = mfa_verified,
            )
            self._sessions[session.session_id] = session
        if self._audit is not None:
            self._audit.record(
                SupportAction.IMPERSONATION_START,
                actor, tenant_id, target_user_id,
                reason=reason,
                session_id=session.session_id,
                ticket_ref=ticket_ref,
            )
        return session

    def end_session(self, session_id: str, actor: str) -> bool:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None or s.ended_at is not None:
                return False
            s.ended_at = time.time()
        if self._audit is not None:
            self._audit.record(
                SupportAction.IMPERSONATION_END,
                actor, s.tenant_id, s.target_user_id,
                reason="session_closed",
                session_id=session_id,
                elapsed=round(s.elapsed_seconds, 2),
            )
        return True

    def get_session(self, session_id: str) -> Optional[SupportSession]:
        with self._lock:
            s = self._sessions.get(session_id)
            if s and not s.is_active and s.ended_at is None:
                s.ended_at = time.time()
            return s

    def active_sessions(self) -> List[SupportSession]:
        with self._lock:
            return [s for s in self._sessions.values() if s.is_active]

    def force_close_all(self, admin_actor: str, reason: str) -> int:
        closed = 0
        with self._lock:
            for s in self._sessions.values():
                if s.is_active:
                    s.ended_at = time.time()
                    closed += 1
        if self._audit is not None and closed:
            self._audit.record(
                SupportAction.IMPERSONATION_END,
                admin_actor, "all_tenants", "all_users",
                reason=reason,
                force_closed=closed,
            )
        return closed


# ---------------------------------------------------------------------------
# Device Reset Manager
# ---------------------------------------------------------------------------

@dataclass
class DeviceResetRecord:
    reset_id:   str
    device_id:  str
    user_id:    str
    tenant_id:  str
    actor:      str
    reason:     str
    action:     str
    ts:         float
    slot_freed: bool = False


class DeviceResetManager:
    def __init__(self, audit: SupportAuditChain, *, max_resets_per_user_per_day: int = 3) -> None:
        self._audit    = audit
        self._max_day  = max_resets_per_user_per_day
        self._records:  List[DeviceResetRecord] = []
        self._lock      = threading.Lock()

    def reset_device(self, actor: str, role: SupportRole, device_id: str,
                     user_id: str, tenant_id: str, reason: str) -> DeviceResetRecord:
        if not role.can_reset_device:
            if self._audit is not None:
                self._audit.record(SupportAction.DEVICE_RESET_DENIED, actor, tenant_id,
                                   device_id, reason=f"insufficient_role:{role.value}")
            raise InsufficientRoleError(f"role={role.value} cannot reset devices")
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for device reset")
        self._check_daily_limit(user_id, tenant_id)
        rec = DeviceResetRecord(reset_id=str(uuid.uuid4()), device_id=device_id,
                                user_id=user_id, tenant_id=tenant_id, actor=actor,
                                reason=reason, action="reset", ts=time.time(), slot_freed=True)
        with self._lock:
            self._records.append(rec)
        if self._audit is not None:
            self._audit.record(SupportAction.DEVICE_RESET, actor, tenant_id, device_id,
                               reason=reason, user_id=user_id, reset_id=rec.reset_id)
        return rec

    def unlock_device(self, actor: str, role: SupportRole, device_id: str,
                      user_id: str, tenant_id: str, reason: str) -> DeviceResetRecord:
        if not role.can_reset_device:
            raise InsufficientRoleError(f"role={role.value} cannot unlock devices")
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for device unlock")
        rec = DeviceResetRecord(reset_id=str(uuid.uuid4()), device_id=device_id,
                                user_id=user_id, tenant_id=tenant_id, actor=actor,
                                reason=reason, action="unlock", ts=time.time(), slot_freed=False)
        with self._lock:
            self._records.append(rec)
        if self._audit is not None:
            self._audit.record(SupportAction.DEVICE_UNLOCK, actor, tenant_id, device_id,
                               reason=reason, user_id=user_id)
        return rec

    def history(self, *, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> List[DeviceResetRecord]:
        with self._lock:
            return [r for r in self._records
                    if (user_id is None or r.user_id == user_id)
                    and (tenant_id is None or r.tenant_id == tenant_id)]

    def _check_daily_limit(self, user_id: str, tenant_id: str) -> None:
        cutoff = time.time() - 86400
        with self._lock:
            count = sum(1 for r in self._records if r.user_id == user_id
                        and r.tenant_id == tenant_id and r.ts >= cutoff)
        if count >= self._max_day:
            raise DeviceResetDeniedError(f"daily reset limit ({self._max_day}) reached")


# ---------------------------------------------------------------------------
# Subscription Extender
# ---------------------------------------------------------------------------

@dataclass
class ExtensionRecord:
    ext_id:       str
    user_id:      str
    tenant_id:    str
    actor:        str
    reason:       str
    days_added:   int
    approved_by:  Optional[str]
    ts:           float
    auto_approved: bool = False


class SubscriptionExtender:
    AUTO_APPROVE_MAX_DAYS = 30
    HARD_MAX_DAYS         = 365

    def __init__(self, audit: SupportAuditChain, *, auto_approve_max: int = 30, hard_max: int = 365) -> None:
        self._audit    = audit
        self._auto_max = auto_approve_max
        self._hard_max = hard_max
        self._records:  List[ExtensionRecord] = []
        self._lock      = threading.Lock()

    def extend(self, actor: str, role: SupportRole, user_id: str, tenant_id: str,
               days: int, reason: str, *, approved_by: Optional[str] = None) -> ExtensionRecord:
        if not role.can_extend:
            if self._audit is not None:
                self._audit.record(SupportAction.SUB_EXTEND_DENIED, actor, tenant_id,
                                   user_id, reason=f"insufficient_role:{role.value}")
            raise InsufficientRoleError(f"role={role.value} cannot extend; LEAD+ required")
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory")
        if days <= 0:
            raise ValueError("days must be > 0")
        if days > self._hard_max:
            raise ValueError(f"days exceeds hard_max={self._hard_max}")
        if days > self._auto_max and approved_by is None:
            if self._audit is not None:
                self._audit.record(SupportAction.SUB_EXTEND_DENIED, actor, tenant_id,
                                   user_id, reason=f"approval_required_for_days>{self._auto_max}")
            raise SupportError(f"extensions > {self._auto_max} days require approved_by")
        auto = days <= self._auto_max
        rec  = ExtensionRecord(ext_id=str(uuid.uuid4()), user_id=user_id, tenant_id=tenant_id,
                               actor=actor, reason=reason, days_added=days,
                               approved_by=approved_by or (actor if auto else None),
                               ts=time.time(), auto_approved=auto)
        with self._lock:
            self._records.append(rec)
        if self._audit is not None:
            self._audit.record(SupportAction.SUB_EXTENDED, actor, tenant_id, user_id,
                               reason=reason, days_added=days, approved_by=rec.approved_by)
        return rec

    def history(self, *, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> List[ExtensionRecord]:
        with self._lock:
            return [r for r in self._records
                    if (user_id is None or r.user_id == user_id)
                    and (tenant_id is None or r.tenant_id == tenant_id)]


# ---------------------------------------------------------------------------
# Artifact Resender
# ---------------------------------------------------------------------------

@dataclass
class ResendRecord:
    resend_id:   str
    artifact_id: str
    user_id:     str
    tenant_id:   str
    actor:       str
    download_url: str
    ts:          float
    ttl_seconds: int = 3600


class ArtifactResender:
    MAX_RESENDS_PER_DAY = 5

    def __init__(self, audit: SupportAuditChain, *, max_per_day: int = 5,
                 download_base: str = "https://downloads.bot12.io/artifacts") -> None:
        self._audit       = audit
        self._max_per_day = max_per_day
        self._base        = download_base
        self._records:    List[ResendRecord] = []
        self._lock        = threading.Lock()

    def resend(self, actor: str, role: SupportRole, artifact_id: str,
               user_id: str, tenant_id: str) -> ResendRecord:
        if not role.can_resend_artifact:
            if self._audit is not None:
                self._audit.record(SupportAction.ARTIFACT_RESEND_DENIED, actor, tenant_id,
                                   artifact_id, reason=f"insufficient_role:{role.value}")
            raise InsufficientRoleError(f"role={role.value} cannot resend artifacts")
        self._check_rate_limit(artifact_id, user_id, tenant_id)
        token = secrets.token_urlsafe(32)
        url   = f"{self._base}/{artifact_id}?token={token}&user={user_id}"
        rec   = ResendRecord(resend_id=str(uuid.uuid4()), artifact_id=artifact_id,
                             user_id=user_id, tenant_id=tenant_id, actor=actor,
                             download_url=url, ts=time.time())
        with self._lock:
            self._records.append(rec)
        if self._audit is not None:
            self._audit.record(SupportAction.ARTIFACT_RESENT, actor, tenant_id, artifact_id,
                               reason="support_resend", user_id=user_id, resend_id=rec.resend_id)
        return rec

    def history(self, *, user_id: Optional[str] = None, artifact_id: Optional[str] = None) -> List[ResendRecord]:
        with self._lock:
            return [r for r in self._records
                    if (user_id is None or r.user_id == user_id)
                    and (artifact_id is None or r.artifact_id == artifact_id)]

    def _check_rate_limit(self, artifact_id: str, user_id: str, tenant_id: str) -> None:
        cutoff = time.time() - 86400
        with self._lock:
            count = sum(1 for r in self._records if r.artifact_id == artifact_id
                        and r.user_id == user_id and r.tenant_id == tenant_id and r.ts >= cutoff)
        if count >= self._max_per_day:
            raise RateLimitError(f"resend limit ({self._max_per_day}/day) reached")


# ---------------------------------------------------------------------------
# Account Recovery Manager
# ---------------------------------------------------------------------------

@dataclass
class RecoveryCase:
    case_id:        str
    user_id:        str
    tenant_id:      str
    actor:          str
    reason:         str
    steps_done:     List[RecoveryStep]
    current_step:   RecoveryStep
    completed:      bool
    aborted:        bool
    abort_reason:   Optional[str]
    started_at:     float
    completed_at:   Optional[float] = None


class AccountRecoveryManager:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit  = audit
        self._cases: Dict[str, RecoveryCase] = {}
        self._lock   = threading.Lock()

    def start_recovery(self, actor: str, role: SupportRole, user_id: str,
                       tenant_id: str, reason: str) -> RecoveryCase:
        if not role.can_recover_account:
            raise InsufficientRoleError(f"role={role.value} cannot perform account recovery")
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory")
        case = RecoveryCase(case_id=str(uuid.uuid4()), user_id=user_id, tenant_id=tenant_id,
                            actor=actor, reason=reason, steps_done=[], current_step=RECOVERY_ORDER[0],
                            completed=False, aborted=False, abort_reason=None, started_at=time.time())
        with self._lock:
            self._cases[case.case_id] = case
        if self._audit is not None:
            self._audit.record(SupportAction.ACCOUNT_RECOVERY_START, actor, tenant_id,
                               user_id, reason=reason, case_id=case.case_id)
        return case

    def advance_step(self, case_id: str, step: RecoveryStep, actor: str, *, note: str = "") -> RecoveryCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise RecoveryStepError(f"case_id={case_id} not found")
            if case.completed or case.aborted:
                raise RecoveryStepError("case is already closed")
            if case.current_step != step:
                raise RecoveryStepError(f"expected={case.current_step.value}, got={step.value}")
            case.steps_done.append(step)
            idx = RECOVERY_ORDER.index(step)
            if idx + 1 < len(RECOVERY_ORDER):
                case.current_step = RECOVERY_ORDER[idx + 1]
            if step == RecoveryStep.COMPLETE:
                case.completed    = True
                case.completed_at = time.time()
        if self._audit is not None:
            action = (SupportAction.ACCOUNT_RECOVERY_COMPLETE if step == RecoveryStep.COMPLETE
                      else SupportAction.ACCOUNT_RECOVERY_STEP)
            self._audit.record(action, actor, case.tenant_id, case.user_id,
                               reason=note or step.value, case_id=case_id, step=step.value)
        return case

    def abort_recovery(self, case_id: str, actor: str, abort_reason: str) -> RecoveryCase:
        if not abort_reason or not abort_reason.strip():
            raise MissingReasonError("abort_reason is mandatory")
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise RecoveryStepError(f"case_id={case_id} not found")
            if case.completed or case.aborted:
                raise RecoveryStepError("case is already closed")
            case.aborted      = True
            case.abort_reason = abort_reason
        if self._audit is not None:
            self._audit.record(SupportAction.ACCOUNT_RECOVERY_ABORTED, actor,
                               case.tenant_id, case.user_id, reason=abort_reason, case_id=case_id)
        return case

    def get_case(self, case_id: str) -> Optional[RecoveryCase]:
        with self._lock:
            return self._cases.get(case_id)

    def open_cases(self, tenant_id: Optional[str] = None) -> List[RecoveryCase]:
        with self._lock:
            return [c for c in self._cases.values()
                    if not c.completed and not c.aborted
                    and (tenant_id is None or c.tenant_id == tenant_id)]


# ---------------------------------------------------------------------------
# Support Ticket Engine
# ---------------------------------------------------------------------------

@dataclass
class SupportTicket:
    ticket_id:   str
    user_id:     str
    tenant_id:   str
    subject:     str
    description: str
    priority:    TicketPriority
    status:      TicketStatus
    claimed_by:  Optional[str]
    escalated_to: Optional[str]
    created_at:  float
    updated_at:  float
    resolved_at: Optional[float] = None
    tags:        List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ticket_id": self.ticket_id, "user_id": self.user_id,
                "tenant_id": self.tenant_id, "subject": self.subject,
                "priority": self.priority.value, "status": self.status.value,
                "claimed_by": self.claimed_by, "created_at": self.created_at}


VALID_TICKET_TRANSITIONS: Dict[TicketStatus, List[TicketStatus]] = {
    TicketStatus.OPEN:       [TicketStatus.CLAIMED, TicketStatus.ESCALATED],
    TicketStatus.CLAIMED:    [TicketStatus.RESOLVED, TicketStatus.ESCALATED],
    TicketStatus.ESCALATED:  [TicketStatus.CLAIMED, TicketStatus.RESOLVED],
    TicketStatus.RESOLVED:   [TicketStatus.CLOSED],
    TicketStatus.CLOSED:     [],
}


class SupportTicketEngine:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit   = audit
        self._tickets: Dict[str, SupportTicket] = {}
        self._lock    = threading.Lock()

    def open_ticket(self, actor: str, user_id: str, tenant_id: str, subject: str,
                    description: str, priority: TicketPriority = TicketPriority.MEDIUM,
                    tags: Optional[List[str]] = None) -> SupportTicket:
        now = time.time()
        t = SupportTicket(ticket_id=str(uuid.uuid4()), user_id=user_id, tenant_id=tenant_id,
                          subject=subject, description=description, priority=priority,
                          status=TicketStatus.OPEN, claimed_by=None, escalated_to=None,
                          created_at=now, updated_at=now, tags=tags or [])
        with self._lock:
            self._tickets[t.ticket_id] = t
        if self._audit is not None:
            self._audit.record(SupportAction.TICKET_OPENED, actor, tenant_id, t.ticket_id,
                               reason="user_request", subject=subject, priority=priority.value)
        return t

    def claim_ticket(self, ticket_id: str, actor: str, role: SupportRole) -> SupportTicket:
        t = self._get_and_transition(ticket_id, TicketStatus.CLAIMED)
        with self._lock:
            t.claimed_by = actor; t.updated_at = time.time()
        if self._audit is not None:
            self._audit.record(SupportAction.TICKET_CLAIMED, actor, t.tenant_id, ticket_id,
                               reason="agent_claim")
        return t

    def resolve_ticket(self, ticket_id: str, actor: str, resolution: str) -> SupportTicket:
        t = self._get_and_transition(ticket_id, TicketStatus.RESOLVED)
        with self._lock:
            t.resolved_at = time.time(); t.updated_at = time.time()
        if self._audit is not None:
            self._audit.record(SupportAction.TICKET_RESOLVED, actor, t.tenant_id, ticket_id,
                               reason=resolution)
        return t

    def escalate_ticket(self, ticket_id: str, actor: str, escalated_to: str, reason: str) -> SupportTicket:
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for escalation")
        t = self._get_and_transition(ticket_id, TicketStatus.ESCALATED)
        with self._lock:
            t.escalated_to = escalated_to; t.updated_at = time.time()
        if self._audit is not None:
            self._audit.record(SupportAction.TICKET_ESCALATED, actor, t.tenant_id, ticket_id,
                               reason=reason, escalated_to=escalated_to)
        return t

    def close_ticket(self, ticket_id: str, actor: str) -> SupportTicket:
        t = self._get_and_transition(ticket_id, TicketStatus.CLOSED)
        with self._lock:
            t.updated_at = time.time()
        if self._audit is not None:
            self._audit.record(SupportAction.TICKET_CLOSED, actor, t.tenant_id, ticket_id,
                               reason="closed")
        return t

    def list_tickets(self, *, tenant_id: Optional[str] = None,
                     status: Optional[TicketStatus] = None,
                     priority: Optional[TicketPriority] = None) -> List[SupportTicket]:
        with self._lock:
            return [t for t in self._tickets.values()
                    if (tenant_id is None or t.tenant_id == tenant_id)
                    and (status   is None or t.status    == status)
                    and (priority is None or t.priority  == priority)]

    def get_ticket(self, ticket_id: str) -> Optional[SupportTicket]:
        with self._lock:
            return self._tickets.get(ticket_id)

    def _get_and_transition(self, ticket_id: str, new_status: TicketStatus) -> SupportTicket:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                raise SupportError(f"ticket_id={ticket_id} not found")
            allowed = VALID_TICKET_TRANSITIONS.get(t.status, [])
            if new_status not in allowed:
                raise SupportError(f"invalid transition {t.status.value} -> {new_status.value}")
            t.status = new_status
        return t


# ---------------------------------------------------------------------------
# Support View Engine
# ---------------------------------------------------------------------------

@dataclass
class CustomerView:
    user_id:      str
    tenant_id:    str
    email:        str
    plan:         str
    status:       str
    created_at:   float
    expires_at:   Optional[float]
    device_count: int
    ticket_count: int
    last_heartbeat: Optional[float]


@dataclass
class LicenseView:
    license_id:  str
    user_id:     str
    tenant_id:   str
    plan:        str
    status:      str
    issued_at:   float
    expires_at:  Optional[float]
    device_slots: int
    devices_used: int


@dataclass
class BillingView:
    user_id:    str
    tenant_id:  str
    plan:       str
    mrr:        float
    last_payment_at:  Optional[float]
    last_payment_ok:  bool
    dunning_active:   bool
    invoices_count:   int


class SupportViewEngine:
    def __init__(self, audit: SupportAuditChain, *, data_store: Optional[Dict[str, Any]] = None) -> None:
        self._audit = audit
        self._store = data_store or {}
        self._lock  = threading.Lock()

    def get_customer_view(self, actor: str, role: SupportRole, user_id: str,
                          tenant_id: str) -> CustomerView:
        if not role.can_view:
            raise InsufficientRoleError("insufficient role")
        if self._audit is not None:
            self._audit.record(SupportAction.VIEW_ACCESSED, actor, tenant_id, user_id,
                               reason="customer_view", view_type="customer")
        key = f"customer:{tenant_id}:{user_id}"
        with self._lock:
            raw = self._store.get(key, {})
        return CustomerView(user_id=user_id, tenant_id=tenant_id, email=raw.get("email",""),
                            plan=raw.get("plan","trial"), status=raw.get("status","active"),
                            created_at=raw.get("created_at", time.time()),
                            expires_at=raw.get("expires_at"),
                            device_count=raw.get("device_count",0),
                            ticket_count=raw.get("ticket_count",0),
                            last_heartbeat=raw.get("last_heartbeat"))

    def get_license_view(self, actor: str, role: SupportRole, license_id: str,
                         tenant_id: str) -> LicenseView:
        if not role.can_view:
            raise InsufficientRoleError("insufficient role")
        if self._audit is not None:
            self._audit.record(SupportAction.VIEW_ACCESSED, actor, tenant_id, license_id,
                               reason="license_view", view_type="license")
        key = f"license:{tenant_id}:{license_id}"
        with self._lock:
            raw = self._store.get(key, {})
        return LicenseView(license_id=license_id, user_id=raw.get("user_id",""),
                           tenant_id=tenant_id, plan=raw.get("plan","basic"),
                           status=raw.get("status","active"),
                           issued_at=raw.get("issued_at", time.time()),
                           expires_at=raw.get("expires_at"),
                           device_slots=raw.get("device_slots",2),
                           devices_used=raw.get("devices_used",0))

    def get_billing_view(self, actor: str, role: SupportRole, user_id: str,
                         tenant_id: str) -> BillingView:
        if not role.can_view:
            raise InsufficientRoleError("insufficient role")
        if self._audit is not None:
            self._audit.record(SupportAction.VIEW_ACCESSED, actor, tenant_id, user_id,
                               reason="billing_view", view_type="billing")
        key = f"billing:{tenant_id}:{user_id}"
        with self._lock:
            raw = self._store.get(key, {})
        return BillingView(user_id=user_id, tenant_id=tenant_id, plan=raw.get("plan","basic"),
                           mrr=raw.get("mrr",0.0), last_payment_at=raw.get("last_payment_at"),
                           last_payment_ok=raw.get("last_payment_ok",True),
                           dunning_active=raw.get("dunning_active",False),
                           invoices_count=raw.get("invoices_count",0))

    def register(self, key: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._store[key] = data


# ---------------------------------------------------------------------------
# Support Admin
# ---------------------------------------------------------------------------

@dataclass
class SupportSystemSummary:
    active_sessions:    int
    open_tickets:       int
    urgent_tickets:     int
    open_recovery_cases: int
    audit_chain_ok:     bool
    total_audit_events: int


class SupportAdmin:
    def __init__(self, audit: SupportAuditChain, sessions: SupportSessionManager,
                 tickets: SupportTicketEngine, recovery: AccountRecoveryManager) -> None:
        self._audit    = audit
        self._sessions = sessions
        self._tickets  = tickets
        self._recovery = recovery

    def summary(self) -> SupportSystemSummary:
        return SupportSystemSummary(
            active_sessions      = len(self._sessions.active_sessions()),
            open_tickets         = len(self._tickets.list_tickets(status=TicketStatus.OPEN)),
            urgent_tickets       = len(self._tickets.list_tickets(priority=TicketPriority.URGENT)),
            open_recovery_cases  = len(self._recovery.open_cases()),
            audit_chain_ok       = self._audit.verify_chain() if self._audit is not None else True,
            total_audit_events   = len(self._audit) if self._audit is not None else 0,
        )

    def force_close_all_sessions(self, admin_actor: str, role: SupportRole, reason: str) -> int:
        if not role.can_impersonate:
            raise InsufficientRoleError("ADMIN required to force-close sessions")
        return self._sessions.force_close_all(admin_actor, reason)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_support_system(
    *,
    secret:           str = "",
    require_mfa:      bool = True,
    max_session_ttl:  int  = 3600,
    default_session_ttl: int = 1800,
    max_resets_day:   int  = 3,
    max_resends_day:  int  = 5,
    auto_approve_ext_max: int = 30,
    download_base:    str  = "https://downloads.bot12.io/artifacts",
    data_store:       Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    audit    = SupportAuditChain(secret=secret)
    sessions = SupportSessionManager(audit, require_mfa=require_mfa,
                                     max_ttl=max_session_ttl, default_ttl=default_session_ttl)
    device   = DeviceResetManager(audit, max_resets_per_user_per_day=max_resets_day)
    extender = SubscriptionExtender(audit, auto_approve_max=auto_approve_ext_max)
    resender = ArtifactResender(audit, max_per_day=max_resends_day, download_base=download_base)
    recovery = AccountRecoveryManager(audit)
    tickets  = SupportTicketEngine(audit)
    views    = SupportViewEngine(audit, data_store=data_store)
    admin    = SupportAdmin(audit, sessions, tickets, recovery)
    return {"audit": audit, "sessions": sessions, "device": device,
            "extender": extender, "resender": resender, "recovery": recovery,
            "tickets": tickets, "views": views, "admin": admin}
