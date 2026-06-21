from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from ..database import db

logger = logging.getLogger("rbac_service")

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "guest":       {"VIEW_PUBLIC"},
    "user":        {"VIEW_PUBLIC", "VIEW_STATUS", "VIEW_SIGNALS", "CREATE_SIGNAL"},
    "trader":      {"VIEW_PUBLIC", "VIEW_STATUS", "VIEW_SIGNALS", "CREATE_SIGNAL",
                    "EXECUTE_TRADE", "VIEW_RISK", "VIEW_ANALYTICS"},
    "admin":       {"VIEW_PUBLIC", "VIEW_STATUS", "VIEW_SIGNALS", "CREATE_SIGNAL",
                    "EXECUTE_TRADE", "VIEW_RISK", "VIEW_ANALYTICS",
                    "MANAGE_USERS", "VIEW_AUDIT", "MANAGE_SETTINGS",
                    "PAUSE_TRADING", "CLOSE_ALL_TRADES"},
    "super_admin": {"*"},
}

_CACHE_TTL = 60
_CACHE_MAX = 128


class _PermCache:
    def __init__(self, max_size: int = _CACHE_MAX, ttl: int = _CACHE_TTL) -> None:
        self._store: OrderedDict[str, tuple] = OrderedDict()
        self._max = max_size
        self._ttl = ttl

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if datetime.now(timezone.utc) - ts > timedelta(seconds=self._ttl):
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: bool) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, datetime.now(timezone.utc))
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def invalidate(self, user_id: str) -> None:
        keys = [k for k in self._store if k.startswith(f"{user_id}:")]
        for k in keys:
            self._store.pop(k, None)


class RBACService:
    """
    G-16: single DB call for permissions
    G-17: TTL cache for check_permission
    G-18: upsert for role assignments
    """

    def __init__(self) -> None:
        self._cache = _PermCache()
        self._lock = asyncio.Lock()

    async def check_permission(self, user_id: str, permission: str) -> bool:
        cache_key = f"{user_id}:{permission}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = await self._check_permission_db(user_id, permission)
        self._cache.set(cache_key, result)
        return result

    async def _check_permission_db(self, user_id: str, permission: str) -> bool:
        try:
            user = await db.select_one("users", {"id": user_id}, columns="role,is_active,is_blocked")
            if not user or not user.get("is_active") or user.get("is_blocked"):
                return False
            role = user.get("role", "guest")
            role_perms = ROLE_PERMISSIONS.get(role, set())
            if "*" in role_perms or permission in role_perms:
                return True
            custom = await db.select_one(
                "user_permissions",
                {"user_id": user_id, "permission": permission, "is_active": True},
            )
            return custom is not None
        except Exception as exc:
            logger.error("check_permission DB error: %s", exc)
            return False

    async def get_user_role(self, user_id: str):
        try:
            user = await db.select_one("users", {"id": user_id}, columns="role")
            return user.get("role") if user else None
        except Exception as exc:
            logger.error("get_user_role error: %s", exc)
            return None

    async def assign_role(self, user_id: str, role: str, assigned_by: str) -> bool:
        if role not in ROLE_PERMISSIONS:
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            await db.update(
                "users",
                {"id": user_id},
                {"role": role, "role_assigned_by": assigned_by,
                 "role_assigned_at": now, "updated_at": now},
            )
            self._cache.invalidate(user_id)
            return True
        except Exception as exc:
            logger.error("assign_role error: %s", exc)
            return False

    async def get_user_permissions(self, user_id: str) -> List[str]:
        """G-16: single DB call."""
        try:
            user = await db.select_one("users", {"id": user_id}, columns="role")
            role = (user or {}).get("role", "guest")
            role_perms = set(ROLE_PERMISSIONS.get(role, set()))
            if "*" in role_perms:
                all_perms: Set[str] = set()
                for perms in ROLE_PERMISSIONS.values():
                    all_perms.update(p for p in perms if p != "*")
                return sorted(all_perms)
            custom_rows = await db.select_many(
                "user_permissions",
                filters={"user_id": user_id, "is_active": True},
                columns="permission",
            )
            custom_perms = {r["permission"] for r in custom_rows}
            return sorted(role_perms | custom_perms)
        except Exception as exc:
            logger.error("get_user_permissions error: %s", exc)
            return []

    async def block_user(self, user_id: str, blocked_by: str, reason: str = "") -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            await db.update(
                "users", {"id": user_id},
                {"is_blocked": True, "blocked_by": blocked_by,
                 "blocked_at": now, "block_reason": reason, "updated_at": now},
            )
            self._cache.invalidate(user_id)
            return True
        except Exception as exc:
            logger.error("block_user error: %s", exc)
            return False

    async def unblock_user(self, user_id: str, unblocked_by: str) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            await db.update(
                "users", {"id": user_id},
                {"is_blocked": False, "unblocked_by": unblocked_by,
                 "unblocked_at": now, "updated_at": now},
            )
            self._cache.invalidate(user_id)
            return True
        except Exception as exc:
            logger.error("unblock_user error: %s", exc)
            return False

    async def list_users(self, role=None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if role:
            filters["role"] = role
        try:
            return await db.select_many(
                "users", filters=filters,
                order_by="created_at", order_desc=True,
                limit=limit, offset=offset,
                columns="id,email,role,is_active,is_blocked,created_at",
            )
        except Exception as exc:
            logger.error("list_users error: %s", exc)
            return []


rbac_service = RBACService()
