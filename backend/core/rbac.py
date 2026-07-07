from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, FrozenSet, List, Optional, Set

from .ttl_cache import TTLPermissionCache

logger = logging.getLogger("core.rbac")


class Role(str, Enum):
    READONLY = "readonly"
    CUSTOMER = "customer"
    SUPPORT = "support"
    ADMIN = "admin"
    SUPER = "super_admin"


_ROLE_RANK: Dict[str, int] = {
    Role.READONLY: 0,
    Role.CUSTOMER: 1,
    Role.SUPPORT: 2,
    Role.ADMIN: 3,
    Role.SUPER: 4,
}

_ROLE_ALIASES: Dict[str, str] = {
    "user": Role.CUSTOMER,
    "trader": Role.CUSTOMER,
    "read_only": Role.READONLY,
    "superadmin": Role.SUPER,
}


def normalize_role(raw: str) -> str:
    r = (raw or "").lower().strip()
    return _ROLE_ALIASES.get(r, r)


class Perm(str, Enum):
    READ_OWN_TRADES = "read:own:trades"
    READ_OWN_SIGNALS = "read:own:signals"
    READ_OWN_PROFILE = "read:own:profile"
    READ_OWN_LICENSE = "read:own:license"
    READ_OWN_BALANCE = "read:own:balance"
    WRITE_OWN_SETTINGS = "write:own:settings"
    WRITE_OWN_PROFILE = "write:own:profile"
    READ_ANY_TRADES = "read:any:trades"
    READ_ANY_SIGNALS = "read:any:signals"
    READ_ANY_PROFILE = "read:any:profile"
    READ_ANY_LICENSE = "read:any:license"
    READ_AUDIT_LOG = "read:audit:log"
    WRITE_ANY_PROFILE = "write:any:profile"
    MANAGE_USERS = "manage:users"
    MANAGE_LICENSES = "manage:licenses"
    MANAGE_SETTINGS = "manage:settings"
    PAUSE_TRADING = "manage:trading:pause"
    CLOSE_ALL = "manage:trading:close_all"
    VIEW_RISK_REPORT = "read:risk:report"
    ALL = "*"


ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    Role.READONLY: frozenset(
        {
            Perm.READ_OWN_TRADES,
            Perm.READ_OWN_SIGNALS,
            Perm.READ_OWN_PROFILE,
            Perm.READ_OWN_LICENSE,
            Perm.READ_OWN_BALANCE,
        }
    ),
    Role.CUSTOMER: frozenset(
        {
            Perm.READ_OWN_TRADES,
            Perm.READ_OWN_SIGNALS,
            Perm.READ_OWN_PROFILE,
            Perm.READ_OWN_LICENSE,
            Perm.READ_OWN_BALANCE,
            Perm.WRITE_OWN_SETTINGS,
            Perm.WRITE_OWN_PROFILE,
        }
    ),
    Role.SUPPORT: frozenset(
        {
            Perm.READ_OWN_TRADES,
            Perm.READ_ANY_TRADES,
            Perm.READ_OWN_SIGNALS,
            Perm.READ_ANY_SIGNALS,
            Perm.READ_OWN_PROFILE,
            Perm.READ_ANY_PROFILE,
            Perm.READ_OWN_LICENSE,
            Perm.READ_ANY_LICENSE,
            Perm.READ_OWN_BALANCE,
            Perm.WRITE_OWN_SETTINGS,
            Perm.WRITE_OWN_PROFILE,
            Perm.READ_AUDIT_LOG,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Perm.READ_OWN_TRADES,
            Perm.READ_ANY_TRADES,
            Perm.READ_OWN_SIGNALS,
            Perm.READ_ANY_SIGNALS,
            Perm.READ_OWN_PROFILE,
            Perm.READ_ANY_PROFILE,
            Perm.READ_OWN_LICENSE,
            Perm.READ_ANY_LICENSE,
            Perm.READ_OWN_BALANCE,
            Perm.WRITE_OWN_SETTINGS,
            Perm.WRITE_ANY_PROFILE,
            Perm.WRITE_OWN_PROFILE,
            Perm.READ_AUDIT_LOG,
            Perm.MANAGE_USERS,
            Perm.MANAGE_LICENSES,
            Perm.MANAGE_SETTINGS,
            Perm.PAUSE_TRADING,
            Perm.CLOSE_ALL,
            Perm.VIEW_RISK_REPORT,
        }
    ),
    Role.SUPER: frozenset({Perm.ALL}),
}


def _expand(role: str) -> FrozenSet[str]:
    perms = ROLE_PERMISSIONS.get(role, frozenset())
    if Perm.ALL in perms:
        all_perms: Set[str] = set()
        for p in ROLE_PERMISSIONS.values():
            all_perms.update(x for x in p if x != Perm.ALL)
        all_perms.add(Perm.ALL)
        return frozenset(all_perms)
    return perms


_CACHE_TTL_SEC = 60
_CACHE_MAX = 2048


@dataclass
class AuthContext:
    user_id: str
    role: str
    is_active: bool = True
    is_blocked: bool = False
    extra_perms: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def rank(self) -> int:
        return _ROLE_RANK.get(self.role, 0)

    @property
    def effective_perms(self) -> FrozenSet[str]:
        return _expand(self.role) | self.extra_perms

    def has_perm(self, perm: str) -> bool:
        if not self.is_active or self.is_blocked:
            return False
        ep = self.effective_perms
        return Perm.ALL in ep or perm in ep

    def can_access_resource(self, perm: str, owner_id: Optional[str]) -> bool:
        if not self.has_perm(perm):
            return False
        own_perms = {
            Perm.READ_OWN_TRADES,
            Perm.READ_OWN_SIGNALS,
            Perm.READ_OWN_PROFILE,
            Perm.READ_OWN_LICENSE,
            Perm.READ_OWN_BALANCE,
            Perm.WRITE_OWN_SETTINGS,
            Perm.WRITE_OWN_PROFILE,
        }
        if perm in own_perms and owner_id is not None:
            return str(owner_id) == str(self.user_id)
        return True


class RBACEngine:
    def __init__(self) -> None:
        self._cache = TTLPermissionCache(max_size=_CACHE_MAX, ttl=_CACHE_TTL_SEC)
        self._lock = asyncio.Lock()
        self._audit_hooks: List[Callable] = []

    def check(self, ctx: AuthContext, perm: str) -> bool:
        cache_key = f"{ctx.user_id}:{ctx.role}:{perm}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = ctx.has_perm(perm)
        self._cache.set(cache_key, result)
        if not result:
            logger.warning("RBAC deny: user=%s role=%s perm=%s", ctx.user_id[:8], ctx.role, perm)
        return result

    def check_resource(self, ctx: AuthContext, perm: str, owner_id: Optional[str]) -> bool:
        result = ctx.can_access_resource(perm, owner_id)
        if not result:
            logger.warning(
                "RBAC owner-deny: user=%s role=%s perm=%s owner=%s",
                ctx.user_id[:8],
                ctx.role,
                perm,
                str(owner_id)[:8] if owner_id else "None",
            )
        return result

    def require(self, ctx: AuthContext, perm: str) -> None:
        if not self.check(ctx, perm):
            raise PermissionDeniedError(f"Role '{ctx.role}' lacks permission '{perm}'")

    def require_resource(self, ctx: AuthContext, perm: str, owner_id: Optional[str]) -> None:
        if not self.check_resource(ctx, perm, owner_id):
            raise PermissionDeniedError(
                f"Access to resource denied: user={ctx.user_id[:8]} "
                f"owner={str(owner_id)[:8] if owner_id else '?'}"
            )

    def invalidate(self, user_id: str) -> None:
        self._cache.invalidate_user(user_id)

    def get_role_permissions(self, role: str) -> List[str]:
        return sorted(_expand(role))

    def is_admin_or_above(self, ctx: AuthContext) -> bool:
        return ctx.rank >= _ROLE_RANK[Role.ADMIN]

    def is_support_or_above(self, ctx: AuthContext) -> bool:
        return ctx.rank >= _ROLE_RANK[Role.SUPPORT]

    def can_escalate_to(self, actor: AuthContext, target_role: str) -> bool:
        """
        P8-RBAC: Can actor assign target_role?
        Requires:
          1. actor has MANAGE_USERS permission
          2. target_role rank strictly below actor rank
        Support cannot assign roles (no MANAGE_USERS).
        """
        if not actor.has_perm(Perm.MANAGE_USERS):
            return False
        target_rank = _ROLE_RANK.get(target_role, -1)
        return actor.rank > target_rank


class PermissionDeniedError(Exception):
    pass


rbac_engine = RBACEngine()
