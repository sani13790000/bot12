"""
========================================================
Control Handler - Galaxy Vast AI Trading Platform
Bot control commands: stop, status, close all trades
========================================================
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from aiogram import Router, types
from aiogram.filters import Command

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()

_API_BASE = "http://localhost:8000/api/v1"


def _get_headers(user_id: int) -> dict:
    """Build auth headers for API calls."""
    return {"X-Telegram-User-Id": str(user_id), "Content-Type": "application/json"}


async def _api_post(path: str, headers: dict, json_body: dict = None) -> Dict[str, Any]:
    """POST to internal API."""
    import aiohttp
    url = f"{_API_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=json_body or {}) as resp:
                return await resp.json()
    except Exception as exc:
        logger.error("[Control] API call failed %s: %s", path, exc)
        return {"error": str(exc)}


async def _api_get(path: str, headers: dict) -> Dict[str, Any]:
    """GET from internal API."""
    import aiohttp
    url = f"{_API_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                return await resp.json()
    except Exception as exc:
        logger.error("[Control] API call failed %s: %s", path, exc)
        return {"error": str(exc)}


@router.message(Command("stop"))
@require_permission(Permission.TRADER)
async def cmd_stop_bot(message: types.Message) -> None:
    """Stop the trading bot (TRADER+)."""
    await message.answer(
        "\u26a0\ufe0f <b>\u062a\u0623\u06cc\u06cc\u062f \u062a\u0648\u0642\u0641 \u0631\u0628\u0627\u062a</b>\n"
        "\u0622\u06cc\u0627 \u0627\u0632 \u062a\u0648\u0642\u0641 \u06a9\u0627\u0645\u0644 \u0631\u0628\u0627\u062a \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u062f\u0627\u0631\u06cc\u062f\u061f",
        parse_mode="HTML",
    )


@router.message(Command("status"))
@require_permission(Permission.USER)
async def cmd_status(message: types.Message) -> None:
    """Show bot status."""
    headers = _get_headers(message.from_user.id)
    status  = await _api_get("/trading/status", headers)

    bot_status      = "\u2705 Online" if status.get("bot_online") else "\u274c Offline"
    analysis_status = "\u2705 Active" if status.get("analysis_active") else "\u274c Inactive"

    lines = [
        "\U0001f4ca <b>\u0648\u0636\u0639\u06cc\u062a \u0631\u0628\u0627\u062a</b>",
        f"\U0001f916 <b>\u0631\u0628\u0627\u062a:</b> {bot_status}",
        f"\U0001f9e0 <b>\u062a\u062d\u0644\u06cc\u0644:</b> {analysis_status}",
        f"\U0001f4c8 <b>\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u0632:</b> {status.get('open_trades', 0)}",
        f"\U0001f4b0 <b>\u0645\u0648\u062c\u0648\u062f\u06cc:</b> {status.get('balance', 0):.2f}$",
        f"\U0001f4ca <b>\u0633\u0648\u062f \u0627\u0645\u0631\u0648\u0632:</b> {status.get('daily_profit', 0):.2f}$",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("close_all"))
@require_permission(Permission.TRADER)
async def cmd_close_all(message: types.Message) -> None:
    """Close all open positions (TRADER+)."""
    headers = _get_headers(message.from_user.id)
    data    = await _api_post("/trading/close_all", headers)
    closed  = data.get("closed_count", 0)
    total_pl = data.get("total_pl", 0.0)
    pl_sign = "+" if total_pl >= 0 else ""
    lines = [
        f"\u2705 <b>\u0647\u0645\u0647 \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0633\u062a\u0647 \u0634\u062f\u0646\u062f</b>",
        f"\U0001f4ca \u062a\u0639\u062f\u0627\u062f \u0628\u0633\u062a\u0647 \u0634\u062f\u0647: {closed}",
        f"\U0001f4b5 \u0646\u062a\u06cc\u062c\u0647 \u06a9\u0644: {pl_sign}{total_pl:.2f}$",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")
