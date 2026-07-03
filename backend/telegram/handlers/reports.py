"""
========================================================
Reports Handler - Galaxy Vast AI Trading Platform
Trade performance reports via Telegram
========================================================
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.formatting import Bold as hbold

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()

_API_BASE = "http://localhost:8000/api/v1"


def _format_number(n: float, decimals: int = 2) -> str:
    """Format a float with thousand separators."""
    return f"{n:,.{decimals}f}"


def _format_pnl(pnl: float) -> str:
    """Format P&L with sign and 2 decimals."""
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.2f}$"


def _format_trade_row(t: Dict[str, Any]) -> str:
    """Format a single trade row for list display."""
    symbol    = t.get("symbol", "?")
    direction = t.get("direction", "?")
    pnl       = t.get("pnl", 0.0) or 0.0
    return f"  {symbol} {direction.upper()} {_format_pnl(pnl)}"


async def _api_get(path: str, user_id: int) -> Dict[str, Any]:
    """GET from internal API."""
    import aiohttp
    headers = {"X-Telegram-User-Id": str(user_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{_API_BASE}{path}", headers=headers) as resp:
                return await resp.json()
    except Exception as exc:
        logger.error("[Reports] API error %s: %s", path, exc)
        return {}


@router.message(Command("report"))
@require_permission(Permission.USER)
async def cmd_daily_report(message: types.Message) -> None:
    """Show daily performance summary."""
    data = await _api_get("/reports/daily", message.from_user.id)
    if not data:
        await message.answer("\u274c \u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.")
        return

    pf_str  = f"{data.get('profit_factor', 0):.2f}" if data.get('profit_factor') else "N/A"
    msg = "\n".join([
        f"\U0001f4ca {hbold('\u06af\u0632\u0627\u0631\u0634 \u0631\u0648\u0632\u0627\u0646\u0647')}",
        f"\u2500" * 30,
        f"  \u0633\u0648\u062f/\u0636\u0631\u0631 \u062e\u0627\u0644\u0635: {_format_pnl(data.get('net_profit', 0))}",
        f"  \u0648\u06cc\u0646\u200c\u0631\u06cc\u062a: {data.get('win_rate', 0):.1f}%",
        f"  \u062a\u0639\u062f\u0627\u062f \u0645\u0639\u0627\u0645\u0644\u0627\u062a: {data.get('total_trades', 0)}",
        f"  \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0628\u0631\u062f:  +{_format_number(data.get('avg_win', 0))}",
        f"  \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0628\u0627\u062e\u062a: -{_format_number(data.get('avg_loss', 0))}",
        f"  Profit Factor: {pf_str}",
    ])
    await message.answer(msg, parse_mode="HTML")


@router.message(Command("winrate"))
@require_permission(Permission.USER)
async def cmd_winrate(message: types.Message) -> None:
    """Show win rate breakdown by period."""
    uid  = message.from_user.id
    d_day   = await _api_get("/reports/stats?period=day",   uid)
    d_week  = await _api_get("/reports/stats?period=week",  uid)
    d_month = await _api_get("/reports/stats?period=month", uid)

    lines = [
        f"\U0001f3af {hbold('\u06af\u0632\u0627\u0631\u0634 \u0648\u06cc\u0646\u200c\u0631\u06cc\u062a')}",
        "\u2500" * 30,
        f"  \u0631\u0648\u0632: {d_day.get('win_rate', 0):.1f}% ({d_day.get('wins', 0)}/{d_day.get('total_trades', 0)})",
        f"  \u0647\u0641\u062a\u0647: {d_week.get('win_rate', 0):.1f}% ({d_week.get('wins', 0)}/{d_week.get('total_trades', 0)})",
        f"  \u0645\u0627\u0647: {d_month.get('win_rate', 0):.1f}% ({d_month.get('wins', 0)}/{d_month.get('total_trades', 0)})",
        "\u2500" * 30,
        f"\U0001f4b0 \u0633\u0648\u062f \u062e\u0627\u0644\u0635 \u0627\u06cc\u0646 \u0645\u0627\u0647: {_format_pnl(d_month.get('net_profit', 0))}",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("trades"))
@require_permission(Permission.USER)
async def cmd_recent_trades(message: types.Message) -> None:
    """Show recent trades (last 24h)."""
    data = await _api_get("/trades?limit=10", message.from_user.id)
    trades = data if isinstance(data, list) else data.get("trades", [])
    if not trades:
        await message.answer("\u0645\u0639\u0627\u0645\u0644\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.")
        return
    lines = [
        f"\U0001f4cb {hbold('\u0622\u062e\u0631\u06cc\u0646 \u0645\u0639\u0627\u0645\u0644\u0627\u062a')}",
        "\u2500" * 30,
    ]
    for t in trades[:10]:
        lines.append(_format_trade_row(t))
    await message.answer("\n".join(lines), parse_mode="HTML")
