"""Signal handler — fetches from API, never accepts signal data from user."""
from __future__ import annotations

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from backend.core.config import settings
from backend.core.logger import get_logger
from backend.telegram.keyboards import signal_action_keyboard

logger = get_logger(__name__)
router = Router(name="signal")

# Allowed symbols whitelist — prevents SSRF via user-supplied symbol
_ALLOWED_SYMBOLS = {
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500",
}

_API_BASE = getattr(settings, "API_BASE_URL", "http://api:8000")


def _format_signal(data: dict) -> str:
    """Format signal dict into Telegram-safe Markdown."""
    direction = data.get("direction", "N/A")
    symbol = data.get("symbol", "N/A")
    score = data.get("score", 0)
    confidence = data.get("confidence", 0)
    entry = data.get("entry_price", 0)
    sl = data.get("stop_loss", 0)
    tp1 = data.get("take_profit_1", 0)
    tp2 = data.get("take_profit_2", 0)
    rr = data.get("risk_reward", 0)

    emoji = "\U0001f7e2" if direction == "BUY" else "\U0001f534" if direction == "SELL" else "\u26aa"

    return (
        f"{emoji} *{symbol} {direction}*\n"
        f"Score: `{score:.1f}/100` | Confidence: `{confidence:.1f}%`\n\n"
        f"Entry:  `{entry:.5f}`\n"
        f"SL:     `{sl:.5f}`\n"
        f"TP1:    `{tp1:.5f}`\n"
        f"TP2:    `{tp2:.5f}`\n"
        f"R:R:    `{rr:.2f}`"
    )


@router.message(Command("signal"))
async def cmd_signal(message: Message, **kwargs) -> None:
    """Fetch and display trading signal."""
    # Parse optional symbol from command args
    parts = (message.text or "").split(maxsplit=1)
    symbol = "XAUUSD"
    if len(parts) > 1:
        candidate = parts[1].strip().upper()[:10]   # length-cap
        if candidate in _ALLOWED_SYMBOLS:
            symbol = candidate
        else:
            await message.answer(
                f"\u274c Unknown symbol `{candidate}`.\n"
                f"Allowed: {', '.join(sorted(_ALLOWED_SYMBOLS))}"
            )
            return

    wait_msg = await message.answer(f"\U0001f504 Fetching signal for *{symbol}*...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_API_BASE}/api/v1/decision/signal",
                params={"symbol": symbol},
                headers={"X-Internal-Service": "telegram-bot"},
            )
        if resp.status_code == 200:
            data = resp.json()
            text = _format_signal(data)
            await wait_msg.edit_text(text, reply_markup=signal_action_keyboard(symbol))
        else:
            await wait_msg.edit_text(
                f"\u26a0\ufe0f API returned {resp.status_code}. Please try again later."
            )
    except httpx.TimeoutException:
        await wait_msg.edit_text("\u23f0 Request timed out. API may be busy.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Signal fetch failed symbol=%s: %s", symbol, exc)
        await wait_msg.edit_text("\u274c Failed to fetch signal. Please try again.")
