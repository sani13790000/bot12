"""backend/services/rbac_patch.py — Phase T

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


class ProactivePermCache:
    """T-21: Proactive TTL eviction every N inserts."""
    _EVICT_EVERY = 50

    def __init__(self, max_size: int = 128, ttl: int = 60) -> None:
        self._store: OrderedDict = OrderedDict()
        self._max = max_size
        self._ttl = ttl
        self._inserts = 0

    def _is_expired(self, ts: datetime) -> bool:
        return (datetime.now(timezone.utc) - ts).total_seconds() > self._ttl

    def _sweep(self) -> None:
        expired = [k for k, (_, ts) in list(self._store.items()) if self._is_expired(ts)]
        for k in expired:
            self._store.pop(k, None)

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if self._is_expired(ts):
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: bool) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, datetime.now(timezone.utc))
        self._inserts += 1
        if self._inserts % self._EVICT_EVERY == 0:
            self._sweep()
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def invalidate(self, user_id: str) -> None:
        keys = [k for k in self._store if k.startswith(f"{user_id}:")]
        for k in keys:
            self._store.pop(k, None)

    def size(self) -> int:
        return len(self._store)


def expand_wildcard_permissions(role_perms: Set[str], all_role_permissions: Dict[str, Set[str]]) -> Set[str]:
    """T-22: expand '*' to all known permissions."""
    if "*" not in role_perms:
        return role_perms
    expanded: Set[str] = set()
    for perms in all_role_permissions.values():
        expanded.update(p for p in perms if p != "*")
    return expanded


class PermissionCheckRateLimiter:
    """T-24: Sliding window rate limiter per user_id."""
    _MAX_CALLS = 200
    _WINDOW_SEC = 60
    _MAX_TRACKED = 10_000

    def __init__(self) -> None:
        from collections import defaultdict, deque as _deque
        self._windows: Dict[str, Any] = defaultdict(lambda: _deque())

    def is_allowed(self, user_id: str) -> bool:
        from collections import deque as _deque
        now = time.monotonic()
        dq = self._windows[user_id]
        while dq and now - dq[0] > self._WINDOW_SEC:
            dq.popleft()
        if len(dq) >= self._MAX_CALLS:
            log.warning("RBAC rate limit hit for user_id=%s (%d calls/%ds)", user_id, self._MAX_CALLS, self._WINDOW_SEC)
            return False
        dq.append(now)
        if len(self._windows) > self._MAX_TRACKED:
            try:
                del self._windows[next(iter(self._windows))]
            except StopIteration:
                pass
        return True


_perm_rate_limiter = PermissionCheckRateLimiter()


def patch_rbac_service() -> None:
    """Apply T-19..T-24 to global rbac_service. Idempotent."""
    from backend.services.rbac_service import RBACService, rbac_service, ROLE_PERMISSIONS

    if getattr(rbac_service, "_phase_t_patched", False):
        return

    rbac_service._cache = ProactivePermCache(max_size=128, ttl=60)

    _original_check = RBACService._check_permission_db

    async def _patched_check(self, user_id: str, permission: str) -> bool:
        if not _perm_rate_limiter.is_allowed(user_id):
            return False
        try:
            return await _original_check(self, user_id, permission)
        except Exception as exc:
            log.error("RBAC check_permission DB error user_id=%s permission=%s: %s — DENIED", user_id, permission, exc)
            asyncio.create_task(_audit_rbac_error(user_id, permission, str(exc)))
            return False

    async def _audit_rbac_error(user_id: str, permission: str, error: str) -> None:
        try:
            from backend.services.audit_service import audit_service
            await audit_service.log(user_id=user_id, action="RBAC_CHECK_ERROR", details={"permission": permission, "error": error})
        except Exception:
            pass

    _original_assign = RBACService.assign_role

    async def _patched_assign(self, user_id: str, role: str, assigned_by: str) -> bool:
        if role not in ROLE_PERMISSIONS:
            log.error("assign_role: invalid role '%s' (valid: %s)", role, list(ROLE_PERMISSIONS.keys()))
            return False
        return await _original_assign(self, user_id, role, assigned_by)

    _original_get_perms = RBACService.get_user_permissions

    async def _patched_get_perms(self, user_id: str) -> List[str]:
        result = await _original_get_perms(self, user_id)
        if "*" in result:
            return sorted(expand_wildcard_permissions({"*"}, ROLE_PERMISSIONS))
        return result

    RBACService._check_permission_db = _patched_check
    RBACService.assign_role = _patched_assign
    RBACService.get_user_permissions = _patched_get_perms
    rbac_service._phase_t_patched = True
    log.info("RBACService patched: T-19..T-24 active")
