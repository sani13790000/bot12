from __future__ import annotations
import hashlib, hmac, json, os, time, uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Tuple

class SupportRole(str, Enum):
    L1 = 'support.l1'
    L2 = 'support.l2'
    L3 = 'support.l3'
    ADMIN = 'support.admin'

class InterventionKind(str, Enum):
    DEVICE_RESET = 'device.reset'
    DEVICE_REVOKE = 'device.revoke'
    DEVICE_TRANSFER = 'device.transfer'
    SUBSCRIPTION_EXTEND = 'subscription.extend'
    SUBSCRIPTION_DOWNGRADE = 'subscription.downgrade'
    SUBSCRIPTION_UPGRADE = 'subscription.upgrade'
    ARTIFACT_RESEND = 'artifact.resend'
    ARTIFACT_REISSUE = 'artifact.reissue'
    ACCOUNT_RECOVER = 'account.recover'
    ACCOUNT_SUSPEND = 'account.suspend'
    ACCOUNT_UNSUSPEND = 'account.unsuspend'
    PASSWORD_RESET = 'password.reset'
    MFA_RESET = 'mfa.reset'
    IMPERSONATION_GRANT = 'impersonation.grant'
    IMPERSONATION_START = 'impersonation.start'
    IMPERSONATION_END = 'impersonation.end'
    IMPERSONATION_REVOKE = 'impersonation.revoke'
    REFUND_MANUAL = 'billing.refund_manual'
    CREDIT_MANUAL = 'billing.credit_manual'
    VIEW_CUSTOMER = 'view.customer'
    VIEW_AUDIT_TRAIL = 'view.audit_trail'
    VIEW_DEVICE_LIST = 'view.device_list'
    VIEW_LICENSE_STATUS = 'view.license_status'

class InterventionStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    EXECUTED = 'executed'
    DENIED = 'denied'
    REVERTED = 'reverted'

class ImpersonationStatus(str, Enum):
    ACTIVE = 'active'
    ENDED = 'ended'
    REVOKED = 'revoked'
    EXPIRED = 'expired'

_ROLE_RANK = {SupportRole.L1:0, SupportRole.L2:1, SupportRole.L3:2, SupportRole.ADMIN:3}

REQUIRED_ROLE: Dict[InterventionKind, SupportRole] = {
    InterventionKind.VIEW_CUSTOMER: SupportRole.L1,
    InterventionKind.VIEW_DEVICE_LIST: SupportRole.L1,
    InterventionKind.VIEW_LICENSE_STATUS: SupportRole.L1,
    InterventionKind.VIEW_AUDIT_TRAIL: SupportRole.L2,
    InterventionKind.DEVICE_RESET: SupportRole.L2,
    InterventionKind.DEVICE_REVOKE: SupportRole.L2,
    InterventionKind.DEVICE_TRANSFER: SupportRole.L2,
    InterventionKind.SUBSCRIPTION_EXTEND: SupportRole.L2,
    InterventionKind.SUBSCRIPTION_DOWNGRADE: SupportRole.L2,
    InterventionKind.SUBSCRIPTION_UPGRADE: SupportRole.L2,
    InterventionKind.ARTIFACT_RESEND: SupportRole.L2,
    InterventionKind.ARTIFACT_REISSUE: SupportRole.L3,
    InterventionKind.ACCOUNT_RECOVER: SupportRole.L3,
    InterventionKind.ACCOUNT_SUSPEND: SupportRole.L3,
    InterventionKind.ACCOUNT_UNSUSPEND: SupportRole.L3,
    InterventionKind.PASSWORD_RESET: SupportRole.L3,
    InterventionKind.MFA_RESET: SupportRole.L3,
    InterventionKind.IMPERSONATION_GRANT: SupportRole.ADMIN,
    InterventionKind.IMPERSONATION_START: SupportRole.L3,
    InterventionKind.IMPERSONATION_END: SupportRole.L3,
    InterventionKind.IMPERSONATION_REVOKE: SupportRole.ADMIN,
    InterventionKind.REFUND_MANUAL: SupportRole.L3,
    InterventionKind.CREDIT_MANUAL: SupportRole.L3,
}

REQUIRES_REASON = {
    InterventionKind.DEVICE_REVOKE, InterventionKind.ACCOUNT_SUSPEND,
    InterventionKind.ACCOUNT_RECOVER, InterventionKind.MFA_RESET,
    InterventionKind.IMPERSONATION_GRANT, InterventionKind.IMPERSONATION_START,
    InterventionKind.REFUND_MANUAL, InterventionKind.CREDIT_MANUAL,
    InterventionKind.SUBSCRIPTION_DOWNGRADE, InterventionKind.ARTIFACT_REISSUE,
}

class SupportError(Exception): pass
class PermissionDeniedError(SupportError): pass
class MissingReasonError(SupportError): pass
class ImpersonationError(SupportError): pass
class InterventionDeniedError(SupportError): pass

@dataclass
class SupportAgent:
    agent_id: str
    name: str
    role: SupportRole
    tenant_id: str = 'system'
    active: bool = True

@dataclass
class CustomerView:
    user_id: str
    tenant_id: str
    email_masked: str
    plan: str
    status: str
    device_count: int
    device_limit: int
    license_expires_at: Optional[float]
    last_heartbeat_at: Optional[float]
    subscription_days_left: Optional[int]
    last_payment_status: str
    open_tickets: int
    notes: List[str] = field(default_factory=list)

@dataclass
class InterventionRecord:
    intervention_id: str
    kind: InterventionKind
    actor_id: str
    actor_role: SupportRole
    target_user_id: str
    tenant_id: str
    reason_note: str
    detail: Dict[str, Any]
    status: InterventionStatus
    created_at: float
    executed_at: Optional[float] = None
    reverted_at: Optional[float] = None
    revert_reason: Optional[str] = None

@dataclass
class ImpersonationSession:
    session_id: str
    agent_id: str
    target_user_id: str
    tenant_id: str
    granted_by: str
    reason: str
    status: ImpersonationStatus
    started_at: float
    ttl_seconds: int
    ended_at: Optional[float] = None
    actions_taken: List[str] = field(default_factory=list)
    @property
    def expires_at(self) -> float: return self.started_at + self.ttl_seconds
    def is_active(self) -> bool:
        return self.status == ImpersonationStatus.ACTIVE and time.time() < self.expires_at

@dataclass
class _AuditEntry:
    seq: int
    entry_id: str
    kind: str
    actor_id: str
    target_id: str
    tenant_id: str
    reason: str
    detail: Dict[str, Any]
    ts: float
    chain_hash: str

_AUDIT_SECRET = os.environ.get('SUPPORT_AUDIT_SECRET', 'support-audit-secret-v33')

class SupportAuditChain:
    GENESIS_MSG = 'GENESIS:SUPPORT:CHAIN:V33'
    def __init__(self, secret: str = _AUDIT_SECRET) -> None:
        self._secret = secret.encode()
        self._lock = RLock()
        self._entries: List[_AuditEntry] = []
        self._genesis = self._hmac(self.GENESIS_MSG)
    def _hmac(self, msg: str) -> str:
        return hmac.new(self._secret, msg.encode(), hashlib.sha256).hexdigest()
    def _prev_hash(self) -> str:
        return self._entries[-1].chain_hash if self._entries else self._genesis
    def record(self, kind: str, actor_id: str, target_id: str, tenant_id: str,
               reason: str = '', detail: Optional[Dict[str, Any]] = None) -> _AuditEntry:
        with self._lock:
            ts_now = time.time()
            canonical = json.dumps({'kind': kind, 'actor_id': actor_id,
                'target_id': target_id, 'tenant_id': tenant_id,
                'reason': reason, 'detail': detail or {}, 'ts': ts_now}, sort_keys=True)
            chain_hash = self._hmac(self._prev_hash() + ':' + canonical)
            entry = _AuditEntry(seq=len(self._entries), entry_id=str(uuid.uuid4()),
                kind=kind, actor_id=actor_id, target_id=target_id, tenant_id=tenant_id,
                reason=reason, detail=detail or {}, ts=ts_now, chain_hash=chain_hash)
            self._entries.append(entry)
            return entry
    def verify_chain(self) -> bool:
        with self._lock:
            prev = self._genesis
            for e in self._entries:
                canonical = json.dumps({'kind': e.kind, 'actor_id': e.actor_id,
                    'target_id': e.target_id, 'tenant_id': e.tenant_id,
                    'reason': e.reason, 'detail': e.detail, 'ts': e.ts}, sort_keys=True)
                expected = self._hmac(prev + ':' + canonical)
                if not hmac.compare_digest(expected, e.chain_hash): return False
                prev = e.chain_hash
            return True
    def detect_tampered(self) -> List[int]:
        with self._lock:
            bad: List[int] = []
            prev = self._genesis
            for e in self._entries:
                canonical = json.dumps({'kind': e.kind, 'actor_id': e.actor_id,
                    'target_id': e.target_id, 'tenant_id': e.tenant_id,
                    'reason': e.reason, 'detail': e.detail, 'ts': e.ts}, sort_keys=True)
                expected = self._hmac(prev + ':' + canonical)
                if not hmac.compare_digest(expected, e.chain_hash): bad.append(e.seq)
                prev = e.chain_hash
            return bad
    def query(self, target_id: Optional[str]=None, actor_id: Optional[str]=None,
              kind: Optional[str]=None, limit: int=50) -> List[_AuditEntry]:
        with self._lock:
            results = list(reversed(self._entries))
            if target_id: results = [e for e in results if e.target_id == target_id]
            if actor_id: results = [e for e in results if e.actor_id == actor_id]
            if kind: results = [e for e in results if e.kind == kind]
            return results[:limit] if limit > 0 else []
    def __len__(self) -> int: return len(self._entries)

class PermissionGuard:
    def check(self, agent: SupportAgent, kind: InterventionKind, reason: str = '') -> None:
        if not agent.active:
            raise PermissionDeniedError(f'Agent {agent.agent_id} is inactive.')
        required = REQUIRED_ROLE.get(kind)
        if required is None:
            raise PermissionDeniedError(f'Unknown intervention kind: {kind}')
        if _ROLE_RANK[agent.role] < _ROLE_RANK[required]:
            raise PermissionDeniedError(f'{agent.role} cannot perform {kind}; requires {required}')
        if kind in REQUIRES_REASON:
            if not reason or not reason.strip():
                raise MissingReasonError(f'reason_note is mandatory for {kind}')

class InterventionStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: Dict[str, InterventionRecord] = {}
        self._by_user: Dict[str, List[str]] = defaultdict(list)
    def save(self, rec: InterventionRecord) -> None:
        with self._lock:
            self._records[rec.intervention_id] = rec
            self._by_user[rec.target_user_id].append(rec.intervention_id)
    def get(self, intervention_id: str) -> Optional[InterventionRecord]:
        with self._lock: return self._records.get(intervention_id)
    def list_for_user(self, user_id: str, limit: int=50) -> List[InterventionRecord]:
        with self._lock:
            ids = list(reversed(self._by_user[user_id]))[:limit]
            return [self._records[i] for i in ids if i in self._records]
    def list_by_kind(self, kind: InterventionKind) -> List[InterventionRecord]:
        with self._lock: return [r for r in self._records.values() if r.kind == kind]
    def __len__(self) -> int: return len(self._records)

class CustomerViewBuilder:
    def _mask_email(self, email: str) -> str:
        if '@' not in email: return '***'
        local, domain = email.split('@', 1)
        if len(local) <= 1: return f'*@{domain}'
        return f'{local[0]}***@{domain}'
    def build(self, raw: Dict[str, Any]) -> CustomerView:
        return CustomerView(
            user_id=raw.get('user_id',''), tenant_id=raw.get('tenant_id',''),
            email_masked=self._mask_email(raw.get('email','')),
            plan=raw.get('plan','unknown'), status=raw.get('status','unknown'),
            device_count=raw.get('device_count',0), device_limit=raw.get('device_limit',3),
            license_expires_at=raw.get('license_expires_at'),
            last_heartbeat_at=raw.get('last_heartbeat_at'),
            subscription_days_left=raw.get('subscription_days_left'),
            last_payment_status=raw.get('last_payment_status','unknown'),
            open_tickets=raw.get('open_tickets',0), notes=raw.get('notes',[]))
    def mask_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        masked = dict(data)
        for key in ('password_hash','mfa_secret','raw_token','payment_card','bank_account'):
            masked.pop(key, None)
        if 'email' in masked: masked['email'] = self._mask_email(masked['email'])
        return masked

class DeviceResetHandler:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._devices: Dict[str, Dict[str, Any]] = {}
    def register(self, device_id: str, user_id: str, tenant_id: str) -> None:
        with self._lock:
            self._devices[device_id] = {'user_id':user_id,'tenant_id':tenant_id,'active':True,'reset_count':0}
    def reset(self, agent: SupportAgent, device_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None: raise InterventionDeniedError(f'Device {device_id} not found')
            dev['reset_count'] += 1; dev['active'] = True
            result = {'device_id':device_id,'reset_count':dev['reset_count'],'status':'reset'}
            self._audit.record(kind=InterventionKind.DEVICE_RESET, actor_id=agent.agent_id,
                target_id=device_id, tenant_id=dev['tenant_id'], reason=reason, detail=result)
            return result
    def revoke(self, agent: SupportAgent, device_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None: raise InterventionDeniedError(f'Device {device_id} not found')
            dev['active'] = False
            result = {'device_id':device_id,'status':'revoked'}
            self._audit.record(kind=InterventionKind.DEVICE_REVOKE, actor_id=agent.agent_id,
                target_id=device_id, tenant_id=dev['tenant_id'], reason=reason, detail=result)
            return result
    def list_devices(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [{'device_id':did,**info} for did,info in self._devices.items() if info['user_id']==user_id]

class SubscriptionExtender:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._subs: Dict[str, Dict[str, Any]] = {}
    def register(self, user_id: str, tenant_id: str, plan: str, expires_at: float) -> None:
        with self._lock:
            self._subs[user_id] = {'tenant_id':tenant_id,'plan':plan,'expires_at':expires_at,'extensions':0}
    def extend(self, agent: SupportAgent, user_id: str, days: int, reason: str) -> Dict[str, Any]:
        with self._lock:
            sub = self._subs.get(user_id)
            if sub is None: raise InterventionDeniedError(f'No subscription for {user_id}')
            if days <= 0: raise ValueError('days must be positive')
            old_exp = sub['expires_at']; sub['expires_at'] += days * 86400; sub['extensions'] += 1
            result = {'user_id':user_id,'days_added':days,'old_expires':old_exp,'new_expires':sub['expires_at'],'extensions':sub['extensions']}
            self._audit.record(kind=InterventionKind.SUBSCRIPTION_EXTEND, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=sub['tenant_id'], reason=reason, detail=result)
            return result
    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock: return dict(self._subs[user_id]) if user_id in self._subs else None

class ArtifactResendHandler:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._sends: List[Dict[str,Any]] = []; self._reissues: List[Dict[str,Any]] = []
    def resend(self, agent: SupportAgent, user_id: str, tenant_id: str,
               artifact_id: str, channel: str='email', reason: str='') -> Dict[str, Any]:
        with self._lock:
            result = {'artifact_id':artifact_id,'user_id':user_id,'channel':channel,'status':'resent','ts':time.time()}
            self._sends.append(result)
            self._audit.record(kind=InterventionKind.ARTIFACT_RESEND, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=tenant_id, reason=reason, detail=result)
            return result
    def reissue(self, agent: SupportAgent, user_id: str, tenant_id: str,
                artifact_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            new_id = str(uuid.uuid4())
            result = {'original_artifact_id':artifact_id,'new_artifact_id':new_id,'user_id':user_id,'status':'reissued','ts':time.time()}
            self._reissues.append(result)
            self._audit.record(kind=InterventionKind.ARTIFACT_REISSUE, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=tenant_id, reason=reason, detail=result)
            return result
    def send_history(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock: return [s for s in self._sends if s['user_id']==user_id]

class AccountRecoveryHandler:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._accounts: Dict[str, Dict[str, Any]] = {}
    def register(self, user_id: str, tenant_id: str, status: str='active') -> None:
        with self._lock:
            self._accounts[user_id] = {'tenant_id':tenant_id,'status':status,'suspended_reason':None}
    def recover(self, agent: SupportAgent, user_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            acc = self._accounts.get(user_id)
            if acc is None: raise InterventionDeniedError(f'Account {user_id} not found')
            acc['status'] = 'active'; acc['suspended_reason'] = None
            result = {'user_id':user_id,'status':'recovered'}
            self._audit.record(kind=InterventionKind.ACCOUNT_RECOVER, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=acc['tenant_id'], reason=reason, detail=result)
            return result
    def suspend(self, agent: SupportAgent, user_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            acc = self._accounts.get(user_id)
            if acc is None: raise InterventionDeniedError(f'Account {user_id} not found')
            acc['status'] = 'suspended'; acc['suspended_reason'] = reason
            result = {'user_id':user_id,'status':'suspended'}
            self._audit.record(kind=InterventionKind.ACCOUNT_SUSPEND, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=acc['tenant_id'], reason=reason, detail=result)
            return result
    def unsuspend(self, agent: SupportAgent, user_id: str, reason: str='') -> Dict[str, Any]:
        with self._lock:
            acc = self._accounts.get(user_id)
            if acc is None: raise InterventionDeniedError(f'Account {user_id} not found')
            acc['status'] = 'active'; acc['suspended_reason'] = None
            result = {'user_id':user_id,'status':'unsuspended'}
            self._audit.record(kind=InterventionKind.ACCOUNT_UNSUSPEND, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=acc['tenant_id'], reason=reason, detail=result)
            return result
    def reset_password(self, agent: SupportAgent, user_id: str, reason: str='') -> Dict[str, Any]:
        with self._lock:
            acc = self._accounts.get(user_id)
            if acc is None: raise InterventionDeniedError(f'Account {user_id} not found')
            token = str(uuid.uuid4())
            result = {'user_id':user_id,'reset_token':token,'status':'password_reset'}
            self._audit.record(kind=InterventionKind.PASSWORD_RESET, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=acc['tenant_id'], reason=reason,
                detail={'user_id':user_id,'status':'password_reset'})
            return result
    def reset_mfa(self, agent: SupportAgent, user_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            acc = self._accounts.get(user_id)
            if acc is None: raise InterventionDeniedError(f'Account {user_id} not found')
            result = {'user_id':user_id,'status':'mfa_reset'}
            self._audit.record(kind=InterventionKind.MFA_RESET, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=acc['tenant_id'], reason=reason, detail=result)
            return result
    def get_status(self, user_id: str) -> Optional[str]:
        with self._lock:
            acc = self._accounts.get(user_id)
            return acc['status'] if acc else None

class ImpersonationManager:
    DEFAULT_TTL = 1800
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._sessions: Dict[str, ImpersonationSession] = {}
        self._grants: Dict[Tuple[str,str], str] = {}
    def grant(self, admin: SupportAgent, agent_id: str, target_user_id: str,
              tenant_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            self._grants[(agent_id, target_user_id)] = admin.agent_id
            result = {'agent_id':agent_id,'target_user_id':target_user_id,'granted_by':admin.agent_id}
            self._audit.record(kind=InterventionKind.IMPERSONATION_GRANT, actor_id=admin.agent_id,
                target_id=target_user_id, tenant_id=tenant_id, reason=reason, detail=result)
            return result
    def start(self, agent: SupportAgent, target_user_id: str, tenant_id: str,
              reason: str, ttl_seconds: int=DEFAULT_TTL) -> ImpersonationSession:
        with self._lock:
            key = (agent.agent_id, target_user_id)
            if key not in self._grants:
                raise ImpersonationError(f'No grant for {agent.agent_id} -> {target_user_id}')
            session = ImpersonationSession(session_id=str(uuid.uuid4()), agent_id=agent.agent_id,
                target_user_id=target_user_id, tenant_id=tenant_id,
                granted_by=self._grants[key], reason=reason,
                status=ImpersonationStatus.ACTIVE, started_at=time.time(), ttl_seconds=ttl_seconds)
            self._sessions[session.session_id] = session
            self._audit.record(kind=InterventionKind.IMPERSONATION_START, actor_id=agent.agent_id,
                target_id=target_user_id, tenant_id=tenant_id, reason=reason,
                detail={'session_id':session.session_id,'ttl_seconds':ttl_seconds})
            return session
    def log_action(self, session_id: str, action: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None: raise ImpersonationError(f'Session {session_id} not found')
            if not session.is_active(): raise ImpersonationError(f'Session {session_id} is not active')
            session.actions_taken.append(action)
    def end(self, agent: SupportAgent, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None: raise ImpersonationError(f'Session {session_id} not found')
            if session.agent_id != agent.agent_id: raise PermissionDeniedError('Only the owning agent can end a session')
            session.status = ImpersonationStatus.ENDED; session.ended_at = time.time()
            result = {'session_id':session_id,'status':'ended','actions_taken':len(session.actions_taken)}
            self._audit.record(kind=InterventionKind.IMPERSONATION_END, actor_id=agent.agent_id,
                target_id=session.target_user_id, tenant_id=session.tenant_id,
                reason='session_ended', detail=result)
            return result
    def revoke(self, admin: SupportAgent, session_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None: raise ImpersonationError(f'Session {session_id} not found')
            session.status = ImpersonationStatus.REVOKED; session.ended_at = time.time()
            result = {'session_id':session_id,'status':'revoked','revoked_by':admin.agent_id}
            self._audit.record(kind=InterventionKind.IMPERSONATION_REVOKE, actor_id=admin.agent_id,
                target_id=session.target_user_id, tenant_id=session.tenant_id, reason=reason, detail=result)
            return result
    def get_session(self, session_id: str) -> Optional[ImpersonationSession]:
        with self._lock:
            s = self._sessions.get(session_id)
            if s and not s.is_active() and s.status == ImpersonationStatus.ACTIVE:
                s.status = ImpersonationStatus.EXPIRED
            return s
    def active_sessions(self) -> List[ImpersonationSession]:
        with self._lock:
            now = time.time(); result = []
            for s in self._sessions.values():
                if s.status == ImpersonationStatus.ACTIVE:
                    if now > s.expires_at: s.status = ImpersonationStatus.EXPIRED
                    else: result.append(s)
            return result

class BillingInterventionHandler:
    def __init__(self, audit: SupportAuditChain) -> None:
        self._audit = audit; self._lock = RLock()
        self._refunds: List[Dict[str,Any]] = []; self._credits: List[Dict[str,Any]] = []
    def issue_refund(self, agent: SupportAgent, user_id: str, tenant_id: str,
                    amount_cents: int, reason: str) -> Dict[str, Any]:
        with self._lock:
            if amount_cents <= 0: raise ValueError('amount_cents must be positive')
            record = {'refund_id':str(uuid.uuid4()),'user_id':user_id,'amount_cents':amount_cents,'status':'issued','ts':time.time()}
            self._refunds.append(record)
            self._audit.record(kind=InterventionKind.REFUND_MANUAL, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=tenant_id, reason=reason, detail=record)
            return record
    def issue_credit(self, agent: SupportAgent, user_id: str, tenant_id: str,
                     amount_cents: int, reason: str) -> Dict[str, Any]:
        with self._lock:
            if amount_cents <= 0: raise ValueError('amount_cents must be positive')
            record = {'credit_id':str(uuid.uuid4()),'user_id':user_id,'amount_cents':amount_cents,'status':'issued','ts':time.time()}
            self._credits.append(record)
            self._audit.record(kind=InterventionKind.CREDIT_MANUAL, actor_id=agent.agent_id,
                target_id=user_id, tenant_id=tenant_id, reason=reason, detail=record)
            return record
    def total_refunded(self, user_id: str) -> int:
        with self._lock: return sum(r['amount_cents'] for r in self._refunds if r['user_id']==user_id)

class SupportViewEngine:
    def __init__(self, audit: SupportAuditChain, guard: PermissionGuard, builder: CustomerViewBuilder) -> None:
        self._audit = audit; self._guard = guard; self._builder = builder
    def view_customer(self, agent: SupportAgent, raw: Dict[str, Any]) -> CustomerView:
        self._guard.check(agent, InterventionKind.VIEW_CUSTOMER)
        view = self._builder.build(raw)
        self._audit.record(kind=InterventionKind.VIEW_CUSTOMER, actor_id=agent.agent_id,
            target_id=raw.get('user_id',''), tenant_id=raw.get('tenant_id',''), reason='support_view')
        return view
    def view_audit_trail(self, agent: SupportAgent, target_id: str, tenant_id: str, limit: int=50) -> List[_AuditEntry]:
        self._guard.check(agent, InterventionKind.VIEW_AUDIT_TRAIL)
        self._audit.record(kind=InterventionKind.VIEW_AUDIT_TRAIL, actor_id=agent.agent_id,
            target_id=target_id, tenant_id=tenant_id, reason='support_audit_view')
        return self._audit.query(target_id=target_id, limit=limit)
    def view_device_list(self, agent: SupportAgent, user_id: str, tenant_id: str,
                         device_handler) -> List[Dict[str, Any]]:
        self._guard.check(agent, InterventionKind.VIEW_DEVICE_LIST)
        self._audit.record(kind=InterventionKind.VIEW_DEVICE_LIST, actor_id=agent.agent_id,
            target_id=user_id, tenant_id=tenant_id, reason='support_device_view')
        return device_handler.list_devices(user_id)
    def view_license_status(self, agent: SupportAgent, user_id: str, tenant_id: str,
                             info: Dict[str, Any]) -> Dict[str, Any]:
        self._guard.check(agent, InterventionKind.VIEW_LICENSE_STATUS)
        self._audit.record(kind=InterventionKind.VIEW_LICENSE_STATUS, actor_id=agent.agent_id,
            target_id=user_id, tenant_id=tenant_id, reason='support_license_view')
        return self._builder.mask_sensitive(info)

class ControlledInterventionEngine:
    def __init__(self, audit, guard, store, devices, subscriptions, artifacts, accounts, impersonation, billing):
        self._audit=audit; self._guard=guard; self._store=store; self._devices=devices
        self._subs=subscriptions; self._artifacts=artifacts; self._accounts=accounts
        self._impersonation=impersonation; self._billing=billing
        self._hooks: List[Callable[[InterventionRecord], None]] = []
    def add_hook(self, fn): self._hooks.append(fn)
    def _make_record(self, kind, agent, user_id, tenant_id, reason, detail, status=InterventionStatus.EXECUTED):
        rec = InterventionRecord(intervention_id=str(uuid.uuid4()), kind=kind,
            actor_id=agent.agent_id, actor_role=agent.role, target_user_id=user_id,
            tenant_id=tenant_id, reason_note=reason, detail=detail, status=status,
            created_at=time.time(), executed_at=time.time())
        self._store.save(rec)
        for h in self._hooks:
            try: h(rec)
            except Exception: pass
        return rec
    def reset_device(self, agent, device_id, reason=''):
        self._guard.check(agent, InterventionKind.DEVICE_RESET, reason)
        detail = self._devices.reset(agent, device_id, reason)
        return self._make_record(InterventionKind.DEVICE_RESET, agent, detail.get('user_id', device_id), agent.tenant_id, reason, detail)
    def revoke_device(self, agent, device_id, reason):
        self._guard.check(agent, InterventionKind.DEVICE_REVOKE, reason)
        detail = self._devices.revoke(agent, device_id, reason)
        return self._make_record(InterventionKind.DEVICE_REVOKE, agent, device_id, agent.tenant_id, reason, detail)
    def extend_subscription(self, agent, user_id, days, reason=''):
        self._guard.check(agent, InterventionKind.SUBSCRIPTION_EXTEND, reason)
        detail = self._subs.extend(agent, user_id, days, reason)
        return self._make_record(InterventionKind.SUBSCRIPTION_EXTEND, agent, user_id, agent.tenant_id, reason, detail)
    def resend_artifact(self, agent, user_id, tenant_id, artifact_id, channel='email', reason=''):
        self._guard.check(agent, InterventionKind.ARTIFACT_RESEND, reason)
        detail = self._artifacts.resend(agent, user_id, tenant_id, artifact_id, channel, reason)
        return self._make_record(InterventionKind.ARTIFACT_RESEND, agent, user_id, tenant_id, reason, detail)
    def reissue_artifact(self, agent, user_id, tenant_id, artifact_id, reason):
        self._guard.check(agent, InterventionKind.ARTIFACT_REISSUE, reason)
        detail = self._artifacts.reissue(agent, user_id, tenant_id, artifact_id, reason)
        return self._make_record(InterventionKind.ARTIFACT_REISSUE, agent, user_id, tenant_id, reason, detail)
    def recover_account(self, agent, user_id, reason):
        self._guard.check(agent, InterventionKind.ACCOUNT_RECOVER, reason)
        detail = self._accounts.recover(agent, user_id, reason)
        return self._make_record(InterventionKind.ACCOUNT_RECOVER, agent, user_id, agent.tenant_id, reason, detail)
    def suspend_account(self, agent, user_id, reason):
        self._guard.check(agent, InterventionKind.ACCOUNT_SUSPEND, reason)
        detail = self._accounts.suspend(agent, user_id, reason)
        return self._make_record(InterventionKind.ACCOUNT_SUSPEND, agent, user_id, agent.tenant_id, reason, detail)
    def reset_password(self, agent, user_id, reason=''):
        self._guard.check(agent, InterventionKind.PASSWORD_RESET, reason)
        detail = self._accounts.reset_password(agent, user_id, reason)
        return self._make_record(InterventionKind.PASSWORD_RESET, agent, user_id, agent.tenant_id, reason, detail)
    def reset_mfa(self, agent, user_id, reason):
        self._guard.check(agent, InterventionKind.MFA_RESET, reason)
        detail = self._accounts.reset_mfa(agent, user_id, reason)
        return self._make_record(InterventionKind.MFA_RESET, agent, user_id, agent.tenant_id, reason, detail)
    def issue_refund(self, agent, user_id, tenant_id, amount_cents, reason):
        self._guard.check(agent, InterventionKind.REFUND_MANUAL, reason)
        detail = self._billing.issue_refund(agent, user_id, tenant_id, amount_cents, reason)
        return self._make_record(InterventionKind.REFUND_MANUAL, agent, user_id, tenant_id, reason, detail)
    def issue_credit(self, agent, user_id, tenant_id, amount_cents, reason):
        self._guard.check(agent, InterventionKind.CREDIT_MANUAL, reason)
        detail = self._billing.issue_credit(agent, user_id, tenant_id, amount_cents, reason)
        return self._make_record(InterventionKind.CREDIT_MANUAL, agent, user_id, tenant_id, reason, detail)
    def revert_intervention(self, agent, intervention_id, reason):
        rec = self._store.get(intervention_id)
        if rec is None: raise InterventionDeniedError(f'Intervention {intervention_id} not found')
        if rec.status != InterventionStatus.EXECUTED:
            raise InterventionDeniedError(f'Cannot revert intervention in state {rec.status}')
        rec.status = InterventionStatus.REVERTED; rec.reverted_at = time.time(); rec.revert_reason = reason
        self._audit.record(kind=f'{rec.kind}.reverted', actor_id=agent.agent_id,
            target_id=rec.target_user_id, tenant_id=rec.tenant_id, reason=reason,
            detail={'original_intervention_id': intervention_id})
        return rec

class SupportAdminDashboard:
    def __init__(self, audit, store, impersonation):
        self._audit=audit; self._store=store; self._impersonation=impersonation
    def summary(self) -> Dict[str, Any]:
        all_records = list(self._store._records.values())
        by_kind: Dict[str,int] = defaultdict(int); by_status: Dict[str,int] = defaultdict(int)
        for r in all_records: by_kind[r.kind]+=1; by_status[r.status]+=1
        return {'total_interventions':len(all_records),'by_kind':dict(by_kind),
                'by_status':dict(by_status),'active_impersonations':len(self._impersonation.active_sessions()),
                'audit_chain_ok':self._audit.verify_chain(),'audit_entries':len(self._audit)}
    def user_history(self, user_id: str, limit: int=20) -> List[Dict[str, Any]]:
        records = self._store.list_for_user(user_id, limit=limit)
        return [{'intervention_id':r.intervention_id,'kind':r.kind,'actor_id':r.actor_id,
                 'actor_role':r.actor_role,'reason_note':r.reason_note,'status':r.status,
                 'created_at':r.created_at} for r in records]
    def active_impersonations(self) -> List[Dict[str, Any]]:
        return [{'session_id':s.session_id,'agent_id':s.agent_id,'target_user_id':s.target_user_id,
                 'started_at':s.started_at,'expires_at':s.expires_at,'actions_taken':len(s.actions_taken)}
                for s in self._impersonation.active_sessions()]

def build_support_system(secret: str = _AUDIT_SECRET) -> Dict[str, Any]:
    audit=SupportAuditChain(secret=secret); guard=PermissionGuard(); store=InterventionStore()
    builder=CustomerViewBuilder(); devices=DeviceResetHandler(audit)
    subs=SubscriptionExtender(audit); artifacts=ArtifactResendHandler(audit)
    accounts=AccountRecoveryHandler(audit); imperso=ImpersonationManager(audit)
    billing=BillingInterventionHandler(audit)
    engine=ControlledInterventionEngine(audit=audit, guard=guard, store=store,
        devices=devices, subscriptions=subs, artifacts=artifacts, accounts=accounts,
        impersonation=imperso, billing=billing)
    views=SupportViewEngine(audit=audit, guard=guard, builder=builder)
    admin=SupportAdminDashboard(audit=audit, store=store, impersonation=imperso)
    return {'audit':audit,'guard':guard,'store':store,'builder':builder,'devices':devices,
            'subscriptions':subs,'artifacts':artifacts,'accounts':accounts,'impersonation':imperso,
            'billing':billing,'engine':engine,'views':views,'admin':admin}
