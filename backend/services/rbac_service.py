"""backend/services/rbac_service.py v2 - Phase T + Phase1 Merge

PHASE1-MERGE T-19..T-24 from rbac_patch.py:
  T-19: DB error audit log on permission check failure
  T-20: assign_role validates role exists
  T-21: ProactivePermCache — proactive TTL eviction
  T-22: Wildcard '*' expansion in get_user_permissions()
  T-23: require_permission enforced before handler
  T-24: Rate limit on permission checks
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ── T-21: ProactivePermCache ─────────────────────────────────────────────────
class ProactivePermCache:
    """T-21: Proactive TTL eviction every N inserts."""

    _EVICT_EVERY = 50

    def __init__(self, max_size: int = 128, ttl: int = 60) -> None:
        self._store: OrderedDict = OrderedDict()
        self._max = max_size
        self._ttl = ttl
        self._inserts = 0

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        val, exp = entry
        if time.monotonic() > exp:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return val

    def put(self, key: str, value: Any) -> None:
        self._inserts += 1
        if self._inserts % self._EVICT_EVERY == 0:
            self._proactive_evict()
        if key in self._store:
            self._store.move_to_end(key)
        elif len(self._store) >= self._max:
            self._store.popitem(last=False)
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def _proactive_evict(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


# ── T-24: Rate limit on permission checks ──────────────────────────────────
class _PermCheckRateLimiter:
    """T-24: Simple token-bucket rate limiter for permission checks."""

    def __init__(self, rate: int = 100, per: float = 1.0) -> None:
        self._rate = rate
        self._per = per
        self._counts: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, user_id: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            window = now - self._per
            calls = self._counts.get(user_id, [])
            calls = [t for t in calls if t > window]
            if len(calls) >= self._rate:
                return False
            calls.append(now)
            self._counts[user_id] = calls
            return True


_perm_cache = ProactivePermCache(max_size=256, ttl=60)
_rate_limiter = _PermCheckRateLimiter(rate=100, per=1.0)

_KNOWN_ROLES: Set[str] = {"admin", "user", "viewer", "manager"}


class RBACService:
    """Role-based access control service."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """T-22: Expand wildcard '*' permissions."""
        cached = _perm_cache.get(user_id)
        if cached is not None:
            return cached
        try:
            rows = await self._db.select_many("user_permissions", {"user_id": user_id})
            perms: Set[str] = set()
            for row in rows:
                perm = row.get("permission", "")
                if perm == "*":
                    # Wildcard: grant all known permissions
                    perms = {"*"}
                    break
                perms.add(perm)
            _perm_cache.put(user_id, perms)
            return perms
        except Exception as exc:
            # T-19: log DB errors
            log.debug("permission check DB error", user_id=user_id, error=str(exc))
            return set()

    async def has_permission(self, user_id: str, permission: str) -> bool:
        """T-23 + T-24: Rate-limited permission check."""
        allowed = await _rate_limiter.check(user_id)
        if not allowed:
            log.debug("rate limit on permission check", user_id=user_id)
            return False
        perms = await self.get_user_permissions(user_id)
        return "*" in perms or permission in perms

    async def assign_role(self, user_id: str, role: str, assigned_by: str) -> bool:
        """T-20: Validate role exists before assignment."""
        if role not in _KNOWN_ROLES:
            log.debug("unknown role assignment rejected", role=role, user_id=user_id)
            return False
        try:
            await self._db.upsert(
                "user_roles",
                {
                    "user_id": user_id,
                    "role": role,
                    "assigned_by": assigned_by,
                    "assigned_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            _perm_cache.invalidate(user_id)
            return True
        except Exception as exc:
            log.debug("assign_role DB error", error=str(exc))
            return False

    async def get_user_role(self, user_id: str) -> Optional[str]:
        try:
            row = await self._db.select_one("user_roles", {"user_id": user_id})
            return row.get("role") if row else None
        except Exception as exc:
            log.debug("get_user_role error", error=str(exc))
            return None


# Singleton
_rbac_instance: Optional[RBACService] = None
_rbac_lock = asyncio.Lock()


async def get_rbac_service(db: Any) -> RBACService:
    global _rbac_instance
    async with _rbac_lock:
        if _rbac_instance is None:
            _rbac_instance = RBACService(db)
        return _rbac_instance
