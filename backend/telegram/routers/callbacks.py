"""Inline keyboard callback handlers.

Security:
- All callback_data values are validated against a strict whitelist.
- Unknown or malformed callback data is rejected with an alert.
- No eval/exec, no dynamic imports from callback data.
- No privilege escalation via callback injection.
"""
from __future__ import annotations

import re
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from backend.core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="callbacks")

# ---------------------------------------------------------------------------
# Strict callback data whitelist pattern
# Format: action:value  (value: alphanumeric + underscore, max 20 chars)
# ---------------------------------------------------------------------------
_CB_PATTERN = re.compile(r"^([a-z_]+):([A-Z0-9_]{1,20})$")
_ALLOWED_ACTIONS = {
    "signal",
    "analyze",
    "refresh",
    "close",
    "risk",
}
_ALLOWED_SYMBOLS = {
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500", "DISMISS",
}


def _validate_callback(data: str | None) -> tuple[str, str] | None:
    """
    Validate callback data against whitelist.
    Returns (action, value) or None if invalid.
    Prevents callback injection attacks.
    """
    if not data:
        return None
    m = _CB_PATTERN.match(data)
    if not m:
        return None
    action, value = m.group(1), m.group(2)
    if action not in _ALLOWED_ACTIONS:
        return None
    if action in ("signal", "analyze", "refresh") and value not in _ALLOWED_SYMBOLS:
        return None
    return action, value


# ---------------------------------------------------------------------------
# Catch-all callback handler — validates then dispatches
# ---------------------------------------------------------------------------
@router.callback_query()
async def handle_callback(callback: CallbackQuery, is_admin: bool, **kwargs: Any) -> None:
    """Validate and dispatch all inline keyboard callbacks."""
    parsed = _validate_callback(callback.data)

    if parsed is None:
        logger.warning(
            "INVALID callback data uid=%s data=%r",
            callback.from_user.id if callback.from_user else "?",
            (callback.data or "")[:50],
        )
        await callback.answer(
            "Invalid action. Please use the menu.", show_alert=True
        )
        return

    action, value = parsed

    if action == "signal":
        await callback.answer(f"Fetching signal for {value}...")
        # Import here to avoid circular imports
        from backend.telegram.routers.signal import cmd_signal
        # Re-use signal logic by sending a synthetic message is complex;
        # instead, edit the message with signal data directly.
        await _send_signal_inline(callback, value)

    elif action == "analyze":
        await callback.answer(f"Analysing {value}...")
        await _send_analysis_inline(callback, value)

    elif action == "refresh":
        await callback.answer("\U0001f504 Refreshing...")
        await _send_signal_inline(callback, value)

    elif action == "close":
        await callback.answer("Dismissed.")
        if callback.message:
            await callback.message.delete()

    elif action == "risk":
        await callback.answer()
        await callback.message.answer("\U0001f6e1\ufe0f Use /risk for risk status.") if callback.message else None


async def _send_signal_inline(callback: CallbackQuery, symbol: str) -> None:
    """Fetch signal and edit the inline message."""
    import httpx
    from backend.core.config import settings
    from backend.telegram.keyboards import signal_action_keyboard

    api_base = getattr(settings, "API_BASE_URL", "http://api:8000")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{api_base}/api/v1/decision/signal",
                params={"symbol": symbol},
                headers={"X-Internal-Service": "telegram-bot"},
            )
        if resp.status_code == 200 and callback.message:
            d = resp.json()
            direction = d.get("direction", "N/A")
            score = d.get("score", 0)
            emoji = "\U0001f7e2" if direction == "BUY" else "\U0001f534" if direction == "SELL" else "\u26aa"
            text = (
                f"{emoji} *{symbol} {direction}*\n"
                f"Score: `{score:.1f}/100`\n"
                f"Entry: `{d.get('entry_price', 0):.5f}`\n"
                f"SL:    `{d.get('stop_loss', 0):.5f}`\n"
                f"TP1:   `{d.get('take_profit_1', 0):.5f}`"
            )
            await callback.message.edit_text(text, reply_markup=signal_action_keyboard(symbol))
    except Exception as exc:  # noqa: BLE001
        logger.error("Inline signal error symbol=%s: %s", symbol, exc)


async def _send_analysis_inline(callback: CallbackQuery, symbol: str) -> None:
    """Fetch analysis and reply."""
    import httpx
    from backend.core.config import settings

    api_base = getattr(settings, "API_BASE_URL", "http://api:8000")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{api_base}/api/v1/analysis/smc",
                params={"symbol": symbol, "timeframe": "H1"},
            )
        if resp.status_code == 200 and callback.message:
            d = resp.json()
            await callback.message.reply(
                f"\U0001f4ca *{symbol}* | Trend: `{d.get('trend','N/A')}` | "
                f"Score: `{d.get('confluence_score',0):.1f}`"
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Inline analysis error: %s", exc)
