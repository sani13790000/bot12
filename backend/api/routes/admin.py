from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from backend.core.deps_v2 import get_auth_context, AuthContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/admin', tags=['admin'])


def AdminCtx(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not getattr(ctx, 'is_admin', False):
        raise HTTPException(403, 'Admin access required')
    return ctx


@router.get('/users')
async def list_users(ctx: AuthContext = Depends(AdminCtx)):
    return {'users': [], 'note': 'implement via database query'}


@router.post('/users/{user_id}/block', status_code=204)
async def block_user(user_id: str, ctx: AuthContext = Depends(AdminCtx)):
    pass


@router.post('/devices/revoke', status_code=204)
async def revoke_device(body: dict, ctx: AuthContext = Depends(AdminCtx)):
    device_id = body.get('device_id', '').strip()
    if not device_id:
        raise HTTPException(400, 'device_id is required')
