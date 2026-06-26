from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional, Set

from backend.core.tenant import (
    TenantContext, TenantPlan, TenantScope,
    _tenant_ctx, get_registry,
)

_log = logging.getLogger('middleware.tenant')

_PUBLIC_PREFIXES: Set[str] = {
    '/health', '/docs', '/redoc', '/openapi.json',
    '/metrics', '/favicon.ico',
}

_ADMIN_ROLES = frozenset({'admin', 'super_admin'})


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def _extract_tenant_id_from_jwt_sub(sub: Optional[str]) -> Optional[str]:
    if not sub:
        return None
    if ':' in sub:
        return sub.split(':')[0]
    return None


class TenantMiddleware:
    def __init__(self, app, registry=None, jwt_verify_fn=None,
                 public_prefixes=None):
        self.app = app
        self.registry = registry or get_registry()
        self.jwt_verify_fn = jwt_verify_fn
        if public_prefixes:
            _PUBLIC_PREFIXES.update(public_prefixes)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        path = scope.get('path', '/')
        if _is_public(path):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        raw_auth = headers.get(b'authorization', b'').decode('utf-8', 'replace')
        x_tenant = headers.get(b'x-tenant-id', b'').decode('utf-8', 'replace').strip()
        token_payload = None
        actor_role = 'customer'
        actor_id = ''
        actor_tenant_id = None
        if raw_auth.startswith('Bearer ') and self.jwt_verify_fn:
            try:
                token = raw_auth[7:]
                token_payload = self.jwt_verify_fn(token)
                actor_role = getattr(token_payload, 'role', 'customer')
                actor_id = getattr(token_payload, 'user_id', '')
                sub = getattr(token_payload, 'user_id', None)
                actor_tenant_id = _extract_tenant_id_from_jwt_sub(sub)
            except Exception:
                pass
        resolved_tenant_id = None
        if x_tenant and actor_role in _ADMIN_ROLES:
            resolved_tenant_id = x_tenant
            self.registry._audit.append({
                'type': 'admin_x_tenant_header', 'tenant_id': x_tenant,
                'actor_id': actor_id, 'actor_role': actor_role,
                'path': path, 'ts': time.time(),
            })
        elif actor_tenant_id:
            resolved_tenant_id = actor_tenant_id
        elif x_tenant and actor_role not in _ADMIN_ROLES:
            await self._send_403(send, 'X-Tenant-ID header forbidden for non-admin')
            return
        if not resolved_tenant_id:
            await self._send_403(send, 'Tenant context required')
            return
        tenant_ctx = self.registry.get(resolved_tenant_id)
        if tenant_ctx is None:
            await self._send_403(send, f'Unknown tenant: {resolved_tenant_id}')
            return
        if tenant_ctx.is_suspended():
            await self._send_403(send, f"Tenant '{resolved_tenant_id}' is suspended")
            return
        token = _tenant_ctx.set(tenant_ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            _tenant_ctx.reset(token)

    @staticmethod
    async def _send_403(send, detail: str):
        import json
        body = json.dumps({'detail': detail, 'error_code': 'TENANT_FORBIDDEN'}).encode()
        await send({'type': 'http.response.start', 'status': 403,
                    'headers': [(b'content-type', b'application/json'),
                                (b'content-length', str(len(body)).encode())]})
        await send({'type': 'http.response.body', 'body': body})
