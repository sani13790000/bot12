from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

_log = logging.getLogger('core.tenant')

_tenant_ctx: ContextVar[Optional['TenantContext']] = ContextVar(
    '_tenant_ctx', default=None
)


class TenantPlan(str, Enum):
    TRIAL   = 'trial'
    BASIC   = 'basic'
    PRO     = 'pro'
    VIP     = 'vip'
    ANNUAL  = 'annual'


@dataclass
class TenantLimits:
    max_devices:      int = 1
    max_signals_day:  int = 100
    max_bots:         int = 1
    max_users:        int = 1
    api_rate_per_min: int = 30

    @staticmethod
    def for_plan(plan) -> 'TenantLimits':
        _MAP = {
            TenantPlan.TRIAL:  TenantLimits(1,   50,  1, 1, 20),
            TenantPlan.BASIC:  TenantLimits(2,  200,  1, 3, 60),
            TenantPlan.PRO:    TenantLimits(5,  500,  3, 5, 120),
            TenantPlan.VIP:    TenantLimits(10, 2000, 5, 10, 300),
            TenantPlan.ANNUAL: TenantLimits(10, 2000, 5, 10, 300),
        }
        return _MAP.get(plan, TenantLimits())


@dataclass
class TenantContext:
    tenant_id:  str
    plan:       TenantPlan = TenantPlan.TRIAL
    is_active:  bool = True
    created_at: float = field(default_factory=time.time)

    @property
    def limits(self) -> TenantLimits:
        return TenantLimits.for_plan(self.plan)

    def is_suspended(self) -> bool:
        return not self.is_active


class TenantScope:
    def __init__(self, tenant_id: str, plan: TenantPlan = TenantPlan.TRIAL,
                 is_active: bool = True):
        self._ctx = TenantContext(tenant_id=tenant_id, plan=plan, is_active=is_active)
        self._token: Optional[Token] = None

    def __enter__(self) -> TenantContext:
        self._token = _tenant_ctx.set(self._ctx)
        return self._ctx

    def __exit__(self, *_):
        if self._token is not None:
            _tenant_ctx.reset(self._token)

    async def __aenter__(self) -> TenantContext:
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)


def get_current_tenant() -> Optional[TenantContext]:
    return _tenant_ctx.get()


def require_tenant() -> TenantContext:
    t = _tenant_ctx.get()
    if t is None:
        raise RuntimeError('No tenant context — TenantMiddleware not applied')
    return t


class TenantRegistry:
    def __init__(self):
        self._tenants: Dict[str, TenantContext] = {}
        self._audit:   List[Dict[str, Any]] = []

    def register(self, tenant_id: str, plan: TenantPlan = TenantPlan.TRIAL,
                 is_active: bool = True) -> TenantContext:
        ctx = TenantContext(tenant_id=tenant_id, plan=plan, is_active=is_active)
        self._tenants[tenant_id] = ctx
        return ctx

    def get(self, tenant_id: str) -> Optional[TenantContext]:
        return self._tenants.get(tenant_id)

    def suspend(self, tenant_id: str, actor: str) -> bool:
        t = self._tenants.get(tenant_id)
        if not t:
            return False
        self._tenants[tenant_id] = TenantContext(
            tenant_id=t.tenant_id, plan=t.plan, is_active=False,
            created_at=t.created_at,
        )
        self._audit.append({'action': 'suspend', 'tenant_id': tenant_id,
                            'actor': actor, 'ts': time.time()})
        return True

    def reactivate(self, tenant_id: str, actor: str) -> bool:
        t = self._tenants.get(tenant_id)
        if not t:
            return False
        self._tenants[tenant_id] = TenantContext(
            tenant_id=t.tenant_id, plan=t.plan, is_active=True,
            created_at=t.created_at,
        )
        self._audit.append({'action': 'reactivate', 'tenant_id': tenant_id,
                            'actor': actor, 'ts': time.time()})
        return True

    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    def all_tenants(self) -> List[TenantContext]:
        return list(self._tenants.values())

    def reset(self):
        self._tenants.clear()
        self._audit.clear()


_registry = TenantRegistry()


def get_registry() -> TenantRegistry:
    return _registry


class CrossTenantAccessError(Exception):
    pass


def assert_tenant_access(
    resource_tenant_id: str,
    actor_tenant_id: str,
    actor_role: str,
    actor_id: str,
    resource_label: str = 'resource',
    audit_callbacks: Optional[List[Callable]] = None,
) -> bool:
    if resource_tenant_id == actor_tenant_id:
        return True
    admin_roles = {'admin', 'super_admin'}
    if actor_role in admin_roles:
        entry = {
            'type':            'cross_tenant_access',
            'resource_tenant': resource_tenant_id,
            'actor_tenant':    actor_tenant_id,
            'actor_id':        actor_id,
            'actor_role':      actor_role,
            'resource':        resource_label,
            'ts':              time.time(),
        }
        _log.warning('cross-tenant access granted', extra=entry)
        _registry._audit.append(entry)
        if audit_callbacks:
            for cb in audit_callbacks:
                try:
                    cb(entry)
                except Exception:
                    pass
        return True
    _log.error('cross-tenant boundary violation',
               extra={'actor_tenant': actor_tenant_id,
                      'resource_tenant': resource_tenant_id,
                      'actor_id': actor_id})
    raise CrossTenantAccessError(
        f"Tenant '{actor_tenant_id}' cannot access {resource_label} "
        f"belonging to tenant '{resource_tenant_id}'"
    )
