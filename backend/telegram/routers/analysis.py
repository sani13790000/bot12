"""Analysis handler."""
from __future__ import annotations

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="analysis")

_ALLOWED_SYMBOLS = {
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500",
}
_API_BASE = getattr(settings, "API_BASE_URL", "http://api:8000")


@router.message(Command("analyze"))
async def cmd_analyze(message: Message, **kwargs) -> None:
    """Run SMC + PA analysis for a symbol."""
    parts = (message.text or "").split(maxsplit=1)
    symbol = "XAUUSD"
    if len(parts) > 1:
        candidate = parts[1].strip().upper()[:10]
        if candidate in _ALLOWED_SYMBOLS:
            symbol = candidate
        else:
            await message.answer(f"\u274c Unknown symbol: `{candidate}`")
            return

    wait_msg = await message.answer(f"\U0001f504 Analysing *{symbol}*...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{_API_BASE}/api/v1/analysis/smc",
                params={"symbol": symbol, "timeframe": "H1"},
                headers={"X-Internal-Service": "telegram-bot"},
            )
        if resp.status_code == 200:
            d = resp.json()
            trend = d.get("trend", "N/A")
            bias = d.get("market_bias", "N/A")
            score = d.get("confluence_score", 0)
            fvgs = len(d.get("fair_value_gaps", []))
            obs = len(d.get("order_blocks", []))
            text = (
                f"\U0001f4ca *{symbol} Analysis*\n\n"
                f"Trend:      `{trend}`\n"
                f"Bias:       `{bias}`\n"
                f"Score:      `{score:.1f}/100`\n"
                f"FVGs:       `{fvgs}`\n"
                f"Order Blocks: `{obs}`"
            )
            await wait_msg.edit_text(text)
        else:
            await wait_msg.edit_text(f"\u26a0\ufe0f API error {resp.status_code}")
    except httpx.TimeoutException:
        await wait_msg.edit_text("\u23f0 Analysis timed out.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Analysis error symbol=%s: %s", symbol, exc)
        await wait_msg.edit_text("\u274c Analysis failed.")
