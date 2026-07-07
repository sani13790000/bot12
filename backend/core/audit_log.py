from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.audit")


class AuditEvent(str, Enum):
    LOGIN_OK = "auth.login.ok"
    LOGIN_FAIL = "auth.login.fail"
    LOGIN_LOCKOUT = "auth.login.lockout"
    LOGOUT = "auth.logout"
    REGISTER = "auth.register"
    TOKEN_REFRESH = "token.refresh"
    TOKEN_REVOKE = "token.revoke"
    TOKEN_REUSE = "token.reuse_detected"
    PERM_DENIED = "rbac.permission_denied"
    ROLE_CHANGED = "rbac.role_changed"
    USER_BLOCKED = "rbac.user_blocked"
    USER_UNBLOCKED = "rbac.user_unblocked"
    LICENSE_ISSUED = "admin.license.issued"
    LICENSE_REVOKED = "admin.license.revoked"
    USER_DELETED = "admin.user.deleted"
    SETTINGS_CHANGED = "admin.settings.changed"
    DASHBOARD_ACCESS = "dashboard.access"


@dataclass
class AuditRecord:
    id: str
    ts: float
    event: str
    user_id: Optional[str]
    actor_id: Optional[str]
    ip: Optional[str]
    user_agent: Optional[str]
    detail: Dict[str, Any]
    seq: int
    chain_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "event": self.event,
            "user_id": self.user_id,
            "actor_id": self.actor_id,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "detail": self.detail,
            "seq": self.seq,
            "chain_hash": self.chain_hash,
        }


class AuditLogger:
    _MAX = 10_000

    def __init__(self) -> None:
        self._log: List[AuditRecord] = []
        self._seq: int = 0
        self._prev_hash: str = "GENESIS"
        self._db_writer = None

    def set_db_writer(self, fn) -> None:
        self._db_writer = fn

    def _compute_hash(self, prev: str, record_id: str, event: str, ts: float) -> str:
        payload = f"{prev}:{record_id}:{event}:{ts:.6f}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def record(
        self, event: str, *, user_id=None, actor_id=None, ip=None, user_agent=None, **detail
    ) -> AuditRecord:
        self._seq += 1
        rid = str(uuid.uuid4())
        ts = time.time()
        ch = self._compute_hash(self._prev_hash, rid, event, ts)
        self._prev_hash = ch
        r = AuditRecord(
            id=rid,
            ts=ts,
            event=event,
            user_id=user_id,
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            detail=dict(detail),
            seq=self._seq,
            chain_hash=ch,
        )
        self._log.append(r)
        if len(self._log) > self._MAX:
            self._log = self._log[-self._MAX :]
        logger.info(
            "[AUDIT] seq=%d event=%s user=%s ip=%s",
            self._seq,
            event,
            (user_id or "?")[:8],
            ip or "?",
        )
        return r

    def login_ok(self, user_id: str, ip: str, ua: str = "") -> None:
        self.record(AuditEvent.LOGIN_OK, user_id=user_id, ip=ip, user_agent=ua)

    def login_fail(self, email: str, ip: str, ua: str = "") -> None:
        self.record(AuditEvent.LOGIN_FAIL, ip=ip, user_agent=ua, email=email)

    def login_lockout(self, ip: str) -> None:
        self.record(AuditEvent.LOGIN_LOCKOUT, ip=ip)

    def logout(self, user_id: str, ip: str) -> None:
        self.record(AuditEvent.LOGOUT, user_id=user_id, ip=ip)

    def register(self, user_id: str, email: str, ip: str) -> None:
        self.record(AuditEvent.REGISTER, user_id=user_id, ip=ip, email=email)

    def perm_denied(self, user_id: str, perm: str, path: str, ip: str) -> None:
        self.record(AuditEvent.PERM_DENIED, user_id=user_id, ip=ip, perm=perm, path=path)

    def role_changed(self, target_id: str, old: str, new: str, actor_id: str) -> None:
        self.record(
            AuditEvent.ROLE_CHANGED,
            user_id=target_id,
            actor_id=actor_id,
            old_role=old,
            new_role=new,
        )

    def token_refresh(self, user_id: str, ip: str) -> None:
        self.record(AuditEvent.TOKEN_REFRESH, user_id=user_id, ip=ip)

    def token_reuse(self, user_id: str, ip: str) -> None:
        self.record(AuditEvent.TOKEN_REUSE, user_id=user_id, ip=ip)

    def user_blocked(self, target_id: str, actor_id: str, reason: str) -> None:
        self.record(AuditEvent.USER_BLOCKED, user_id=target_id, actor_id=actor_id, reason=reason)

    def dashboard_access(self, user_id: str, path: str, ip: str) -> None:
        self.record(AuditEvent.DASHBOARD_ACCESS, user_id=user_id, ip=ip, path=path)

    def query(self, *, user_id=None, event=None, since_ts=None, limit=200) -> List[Dict]:
        results = self._log
        if user_id:
            results = [r for r in results if r.user_id == user_id]
        if event:
            results = [r for r in results if r.event == event]
        if since_ts:
            results = [r for r in results if r.ts >= since_ts]
        return [r.to_dict() for r in results[-limit:]]

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for r in self._log:
            expected = self._compute_hash(prev, r.id, r.event, r.ts)
            if expected != r.chain_hash:
                logger.critical("[AUDIT] Chain broken at seq=%d", r.seq)
                return False
            prev = r.chain_hash
        return True

    def __len__(self) -> int:
        return len(self._log)


audit_logger = AuditLogger()
