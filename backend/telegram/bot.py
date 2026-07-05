"""
bot.py — Telegram Bot entrypoint

Runs as: python -m backend.telegram.bot
Includes:
  - Aiogram polling
  - Liveness heartbeat (/tmp/bot_heartbeat)
  - Admin command handlers
  - Signal notification system
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot initialization
# ---------------------------------------------------------------------------

_bot = None
_dp = None
_initialized = False


async def init_bot() -> bool:
    """Initialize bot and dispatcher. Returns True on success."""
    global _bot, _dp, _initialized
    try:
        from aiogram import Bot, Dispatcher
        from aiogram.enums import ParseMode
        from aiogram.client.default import DefaultBotProperties
        from backend.core.config import get_settings

        settings = get_settings()
        token = settings.TELEGRAM_BOT_TOKEN
        if not token or token == "your_telegram_bot_token_here":
            logger.error("[Bot] TELEGRAM_BOT_TOKEN not configured")
            return False

        _bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _dp = Dispatcher()
        _register_handlers(_dp)
        _initialized = True
        logger.info("[Bot] Initialized successfully")
        return True
    except ImportError as e:
        logger.error("[Bot] aiogram not installed: %s", e)
        return False
    except Exception as e:
        logger.error("[Bot] Initialization failed: %s", e)
        return False


def _register_handlers(dp) -> None:
    """Register all command and message handlers."""
    try:
        from aiogram import Router
        from aiogram.filters import Command
        from aiogram.types import Message
        from backend.core.config import get_settings

        router = Router()
        settings = get_settings()
        admin_ids = set(getattr(settings, 'TELEGRAM_ADMIN_IDS', []))

        @router.message(Command("start"))
        async def cmd_start(message: Message):
            await message.answer(
                "<b>GalaxyVast MT5 Trading Bot</b>\n"
                "Type /help for available commands."
            )

        @router.message(Command("help"))
        async def cmd_help(message: Message):
            await message.answer(
                "<b>Available Commands:</b>\n"
                "/status — Bot and system status\n"
                "/balance — Account balance\n"
                "/positions — Open positions\n"
                "/kill — Emergency stop (admin only)\n"
                "/resume — Resume trading (admin only)\n"
                "/health — System health check"
            )

        @router.message(Command("status"))
        async def cmd_status(message: Message):
            from backend.risk.kill_switch import kill_switch
            ks_status = "\ud83d\udd34 ACTIVE" if kill_switch.is_active else "\ud83d\udfe2 Inactive"
            await message.answer(
                f"<b>Bot Status</b>\n"
                f"Kill Switch: {ks_status}\n"
                f"Mode: {'DEMO' if os.environ.get('MT5_DEMO_MODE', '').lower() in ('1', 'true') else 'LIVE'}"
            )

        @router.message(Command("kill"))
        async def cmd_kill(message: Message):
            if message.from_user.id not in admin_ids:
                await message.answer("\u26d4 Unauthorized")
                return
            from backend.risk.kill_switch import kill_switch
            kill_switch.activate("Manual kill via Telegram")
            await message.answer("\ud83d\udd34 <b>KILL SWITCH ACTIVATED</b>\nAll trading stopped.")

        @router.message(Command("resume"))
        async def cmd_resume(message: Message):
            if message.from_user.id not in admin_ids:
                await message.answer("\u26d4 Unauthorized")
                return
            from backend.risk.kill_switch import kill_switch
            kill_switch.reset("Manual resume via Telegram")
            await message.answer("\u2705 Kill switch reset. Trading resumed.")

        @router.message(Command("health"))
        async def cmd_health(message: Message):
            from backend.telegram.heartbeat import is_alive
            alive = is_alive()
            await message.answer(
                f"<b>Health Check</b>\n"
                f"Bot heartbeat: {'\u2705 alive' if alive else '\u26a0\ufe0f stale'}\n"
            )

        dp.include_router(router)
        logger.info("[Bot] Handlers registered")
    except Exception as e:
        logger.error("[Bot] Handler registration failed: %s", e)


async def start_polling() -> None:
    """Start bot polling loop."""
    if not _initialized or _bot is None or _dp is None:
        logger.error("[Bot] Not initialized — call init_bot() first")
        return
    try:
        await _dp.start_polling(_bot, allowed_updates=["message", "callback_query"])
    except Exception as e:
        logger.error("[Bot] Polling error: %s", e)
        raise


async def send_notification(message: str, parse_mode: str = "HTML") -> bool:
    """Send notification to all admin users."""
    if not _initialized or _bot is None:
        return False
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        admin_ids = getattr(settings, 'TELEGRAM_ADMIN_IDS', [])
        for admin_id in admin_ids:
            try:
                await _bot.send_message(admin_id, message, parse_mode=parse_mode)
            except Exception as e:
                logger.warning("[Bot] Failed to send to %s: %s", admin_id, e)
        return True
    except Exception as e:
        logger.error("[Bot] send_notification error: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    """Main async entry point for the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    logger.info("[Bot] Starting GalaxyVast Telegram Bot...")

    # Initialize bot
    ok = await init_bot()
    if not ok:
        logger.critical("[Bot] Failed to initialize. Exiting.")
        sys.exit(1)

    # Start heartbeat
    from backend.telegram.heartbeat import start_heartbeat, stop_heartbeat
    await start_heartbeat()

    try:
        logger.info("[Bot] Starting polling...")
        await start_polling()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[Bot] Polling stopped")
    finally:
        await stop_heartbeat()
        if _bot:
            await _bot.session.close()
        logger.info("[Bot] Shutdown complete")


if __name__ == "__main__":
    asyncio.run(_main())
