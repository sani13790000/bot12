from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

logger = logging.getLogger("core.refresh_rotation")

_MAX_SESSIONS = 5
_TTL_DAYS = 30


@dataclass
class _RTRecord:
    token_hash: str
    user_id: str
    family_id: str
    issued_at: float
    expires_at: float
    used: bool = False
    replaced_by: Optional[str] = None


@dataclass
class _AuditEntry:
    ts: float
    event: str
    user_id: str
    detail: str = ""


class RefreshTokenRotationStore:
    """P8-RT-1..7: Single-use refresh tokens with rotation, family tracking, session limit."""

    def __init__(self, max_sessions: int = _MAX_SESSIONS, ttl_days: int = _TTL_DAYS) -> None:
        self._store: Dict[str, _RTRecord] = {}
        self._families: Dict[str, Set[str]] = {}
        self._audit: List[_AuditEntry] = []
        self._max_sessions = max_sessions
        self._ttl_days = ttl_days
        self._max_audit = 5_000

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _log(self, event: str, user_id: str, detail: str = "") -> None:
        self._audit.append(_AuditEntry(ts=time.time(), event=event, user_id=user_id, detail=detail))
        if len(self._audit) > self._max_audit:
            self._audit = self._audit[-self._max_audit :]
        logger.info("[RT] %s user=%s %s", event, user_id[:8], detail)

    def _count_active_sessions(self, user_id: str) -> int:
        now = time.time()
        return sum(
            1
            for r in self._store.values()
            if r.user_id == user_id and not r.used and r.expires_at > now
        )

    def _oldest_session_hash(self, user_id: str) -> Optional[str]:
        now = time.time()
        active = [
            r
            for r in self._store.values()
            if r.user_id == user_id and not r.used and r.expires_at > now
        ]
        if not active:
            return None
        return min(active, key=lambda r: r.issued_at).token_hash

    def issue(self, user_id: str, family_id: Optional[str] = None) -> str:
        if self._count_active_sessions(user_id) >= self._max_sessions:
            oldest = self._oldest_session_hash(user_id)
            if oldest:
                self._store.pop(oldest, None)
                self._log("SESSION_EVICTED", user_id, f"oldest={oldest[:8]}")
        token = str(uuid.uuid4())
        th = self._hash(token)
        fid = family_id or str(uuid.uuid4())
        now = time.time()
        self._store[th] = _RTRecord(
            token_hash=th,
            user_id=user_id,
            family_id=fid,
            issued_at=now,
            expires_at=now + self._ttl_days * 86400,
        )
        self._families.setdefault(user_id, set()).add(fid)
        self._log("ISSUED", user_id, f"family={fid[:8]}")
        return token

    def rotate(self, old_token: str) -> Optional[str]:
        th = self._hash(old_token)
        record = self._store.get(th)
        if record is None:
            logger.warning("[RT] Unknown token presented")
            return None
        now = time.time()
        if now > record.expires_at:
            self._store.pop(th, None)
            self._log("EXPIRED", record.user_id)
            return None
        if record.used:
            self._log(
                "REUSE_DETECTED", record.user_id, f"family={record.family_id[:8]} -- revoking all"
            )
            self._revoke_family(record.user_id, record.family_id)
            return None
        record.used = True
        new_token = self.issue(record.user_id, family_id=record.family_id)
        record.replaced_by = self._hash(new_token)
        self._log("ROTATED", record.user_id, f"family={record.family_id[:8]}")
        return new_token

    def revoke_user(self, user_id: str) -> int:
        to_del = [th for th, r in self._store.items() if r.user_id == user_id]
        for th in to_del:
            del self._store[th]
        self._families.pop(user_id, None)
        self._log("REVOKE_ALL", user_id, f"removed={len(to_del)}")
        return len(to_del)

    def revoke_token(self, raw_token: str) -> bool:
        th = self._hash(raw_token)
        record = self._store.pop(th, None)
        if record:
            self._log("REVOKE_ONE", record.user_id, f"th={th[:8]}")
            return True
        return False

    def _revoke_family(self, user_id: str, family_id: str) -> None:
        to_del = [
            th for th, r in self._store.items() if r.user_id == user_id and r.family_id == family_id
        ]
        for th in to_del:
            del self._store[th]
        self._families.get(user_id, set()).discard(family_id)

    def validate(self, raw_token: str) -> Optional[_RTRecord]:
        th = self._hash(raw_token)
        record = self._store.get(th)
        if not record or record.used or time.time() > record.expires_at:
            return None
        return record

    def get_audit(self, user_id: Optional[str] = None, limit: int = 100) -> List[dict]:
        entries = self._audit
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        return [
            {"ts": e.ts, "event": e.event, "user_id": e.user_id, "detail": e.detail}
            for e in entries[-limit:]
        ]

    def active_session_count(self, user_id: str) -> int:
        return self._count_active_sessions(user_id)

    def purge_expired(self) -> int:
        now = time.time()
        to_del = [th for th, r in self._store.items() if r.expires_at < now]
        for th in to_del:
            del self._store[th]
        return len(to_del)


refresh_store = RefreshTokenRotationStore()
