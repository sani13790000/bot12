from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

log = logging.getLogger(__name__)


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    TRADER = "trader"


class RBACService:
    """
    RBAC Service

    FIX: datetime.utcnow() x6 replaced with datetime.now(timezone.utc)
    """

    _table = "users"

    @property
    def _client(self):
        from backend.database.connection import get_db_client
        return get_db_client()

    async def _run(self, func):
        import asyncio
        from functools import partial
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)

    async def create_user(
        self,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER,
        full_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        try:
            now = datetime.now(timezone.utc).isoformat()
            data = {
                "email": email,
                "password_hash": password_hash,
                "role": role.value,
                "full_name": full_name,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            result = await self._run(
                lambda: self._client.table(self._table).insert(data).execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            log.exception("create_user failed email=%s", email)
            return None

    async def deactivate_user(self, user_id: str) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._run(
                lambda: self._client.table(self._table)
                .update({"is_active": False, "deactivated_at": now, "updated_at": now})
                .eq("id", user_id)
                .execute()
            )
            return True
        except Exception:
            log.exception("deactivate_user failed user_id=%s", user_id)
            return False

    async def change_role(self, user_id: str, new_role: UserRole) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._run(
                lambda: self._client.table(self._table)
                .update({"role": new_role.value, "role_changed_at": now, "updated_at": now})
                .eq("id", user_id)
                .execute()
            )
            log.info("role_changed user_id=%s new_role=%s", user_id, new_role.value)
            return True
        except Exception:
            log.exception("change_role failed user_id=%s", user_id)
            return False

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self._run(
                lambda: self._client.table(self._table)
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return result.data if result.data else None
        except Exception:
            log.exception("get_user failed user_id=%s", user_id)
            return None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self._run(
                lambda: self._client.table(self._table)
                .select("*")
                .eq("email", email)
                .single()
                .execute()
            )
            return result.data if result.data else None
        except Exception:
            log.exception("get_user_by_email failed email=%s", email)
            return None

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = await self._run(
                lambda: self._client.table(self._table)
                .select("*")
                .eq("telegram_id", telegram_id)
                .single()
                .execute()
            )
            return result.data if result.data else None
        except Exception:
            log.exception("get_user_by_telegram_id failed tid=%s", telegram_id)
            return None

    async def get_all_users(self) -> List[Dict[str, Any]]:
        try:
            result = await self._run(
                lambda: self._client.table(self._table)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return result.data or []
        except Exception:
            log.exception("get_all_users failed")
            return []

    async def get_users_by_role(self, role: UserRole) -> List[Dict[str, Any]]:
        try:
            result = await self._run(
                lambda: self._client.table(self._table)
                .select("*")
                .eq("role", role.value)
                .execute()
            )
            return result.data or []
        except Exception:
            log.exception("get_users_by_role failed role=%s", role)
            return []

    def has_permission(self, user_role: str, required_role: str) -> bool:
        hierarchy = {"viewer": 0, "user": 1, "trader": 2, "admin": 3}
        return hierarchy.get(user_role, 0) >= hierarchy.get(required_role, 0)


rbac_service = RBACService()
