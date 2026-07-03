from __future__ import annotations
import logging
import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from ..rbac import require_admin

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command('admin_stats'))
@require_admin
async def admin_stats(message: Message) -> None:
    """Show system health stats."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get('http://localhost:8000/health')
        if resp.status_code == 200:
            data   = resp.json()
            status = data.get('status', 'unknown')
            db     = data.get('db', False)
            routes = data.get('routes', 0)
            db_icon = '✅' if db else '❌'
            text = (
                f'📊 *API Stats*\n\n'
                f'Status:   `{status}`\n'
                f'DB:       `{db_icon}`\n'
                f'Routes:   `{routes}`\n'
            )
            await message.answer(text)
        else:
            await message.answer(f'⚠️ Health check failed: {resp.status_code}')
    except Exception as exc:
        logger.error('Admin stats error: %s', exc)
        await message.answer(f'❌ Error: {exc}')


@router.message(Command('admin_kill'))
@require_admin
async def admin_kill(message: Message) -> None:
    """Activate kill switch."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post('http://localhost:8000/risk/kill-switch', json={'active': True})
        if resp.status_code in (200, 204):
            await message.answer('🛑 Kill switch ACTIVATED')
        else:
            await message.answer(f'❌ Failed: {resp.status_code}')
    except Exception as exc:
        await message.answer(f'❌ Error: {exc}')
