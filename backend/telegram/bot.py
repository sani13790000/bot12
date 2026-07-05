"""Telegram Bot — polling + heartbeat + commands.

BUG-N5 FIX: _format_position() uses .get() with safe fallbacks
so /positions command never crashes with KeyError in DEMO mode.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    log.warning("python-telegram-bot not installed — bot disabled")


def _format_position(pos: Dict[str, Any]) -> str:
    """Format a position dict safely — handles both LIVE and DEMO key schemas.

    BUG-N5 FIX: use .get() with fallbacks for every key so KeyError
    never crashes /positions in DEMO mode where keys differ.
    """
    symbol = pos.get("symbol", pos.get("ticker", "UNKNOWN"))
    volume = pos.get("volume", pos.get("lots", pos.get("size", 0.0)))
    pos_type = pos.get("type", pos.get("side", "?"))
    open_price = pos.get("open_price", pos.get("entry_price", pos.get("price_open", 0.0)))
    current_price = pos.get("current_price", pos.get("price_current", open_price))
    # DEMO mode may not have 'profit' — compute from price difference
    profit = pos.get("profit", pos.get("unrealized_pnl", pos.get("pnl", None)))
    if profit is None:
        try:
            profit = (float(current_price) - float(open_price)) * float(volume)
        except Exception:
            profit = 0.0
    ticket = pos.get("ticket", pos.get("id", pos.get("mt5_ticket", "")))
    comment = pos.get("comment", pos.get("description", ""))

    emoji = "🟢" if float(profit) >= 0 else "🔴"
    return (
        f"{emoji} *{symbol}* | {pos_type} | Vol: {volume}\n"
        f"   Open: `{open_price}` → Now: `{current_price}`\n"
        f"   P&L: `{profit:.2f}` | Ticket: `{ticket}`"
        + (f"\n   📝 {comment}" if comment else "")
    )


class TelegramBot:
    """Telegram bot with polling, heartbeat, and trading commands."""

    def __init__(self) -> None:
        self._token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self._app: Optional[Any] = None
        self._running: bool = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------------- #
    # Lifecycle
    # ---------------------------------------------------------------------- #
    async def start(self) -> None:
        if not TELEGRAM_AVAILABLE or not self._token:
            log.warning("TelegramBot: token missing or library unavailable — skipping")
            return
        if self._running:
            return
        self._running = True
        try:
            self._app = (
                Application.builder()
                .token(self._token)
                .build()
            )
            self._register_handlers()
            await self._app.initialize()
            await self._app.start()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            log.info("TelegramBot started (polling)")
            await self._app.updater.start_polling(drop_pending_updates=True)
        except Exception as e:
            log.error("TelegramBot.start: %s", e)
            self._running = False

    async def stop(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                log.debug("TelegramBot.stop: %s", e)

    # ---------------------------------------------------------------------- #
    # Public: send helpers
    # ---------------------------------------------------------------------- #
    async def send_message(self, text: str, parse_mode: str = "Markdown") -> None:
        if not self._app or not self._chat_id:
            return
        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode=parse_mode
            )
        except Exception as e:
            log.warning("TelegramBot.send_message: %s", e)

    async def send_alert(self, text: str) -> None:
        await self.send_message(text)

    async def send_signal(self, signal: Dict[str, Any]) -> None:
        direction = signal.get("direction", "NO_TRADE")
        symbol = signal.get("symbol", "?")
        entry = signal.get("entry_price", 0)
        sl = signal.get("sl_price", 0)
        tp = signal.get("tp_price", 0)
        rr = signal.get("rr_ratio", 0)
        conf = signal.get("confidence", 0)
        emoji = "🟢" if direction == "LONG" else "🔴" if direction == "SHORT" else "⚪"
        msg = (
            f"{emoji} *Signal: {direction}* | {symbol}\n"
            f"Entry: `{entry}` | SL: `{sl}` | TP: `{tp}`\n"
            f"RR: `{rr:.2f}` | Conf: `{conf:.1%}`"
        )
        await self.send_message(msg)

    # ---------------------------------------------------------------------- #
    # Command handlers
    # ---------------------------------------------------------------------- #
    def _register_handlers(self) -> None:
        if not self._app:
            return
        cmds = [
            ("start",     self._cmd_start),
            ("status",    self._cmd_status),
            ("positions", self._cmd_positions),
            ("kill",      self._cmd_kill),
            ("resume",    self._cmd_resume),
            ("stats",     self._cmd_stats),
            ("help",      self._cmd_help),
        ]
        for name, handler in cmds:
            self._app.add_handler(CommandHandler(name, handler))

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🤖 *GalaxyVast MT5 Bot*\nActive and monitoring markets.",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*Commands:*\n"
            "/status — system status\n"
            "/positions — open positions\n"
            "/kill — activate kill switch\n"
            "/resume — deactivate kill switch\n"
            "/stats — performance stats",
            parse_mode="Markdown",
        )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from backend.risk.kill_switch import kill_switch
            ks = "🔴 ACTIVE" if kill_switch.is_active else "🟢 OK"
        except Exception:
            ks = "unknown"
        await update.message.reply_text(
            f"*System Status*\nKill Switch: {ks}\nTime: {datetime.now(timezone.utc).strftime('%H:%M UTC')}",
            parse_mode="Markdown",
        )

    async def _cmd_positions(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Show open positions — BUG-N5 FIX: uses _format_position() with safe .get()"""
        try:
            from backend.execution.mt5_connector import mt5_connector
            positions: List[Dict[str, Any]] = await mt5_connector.get_positions()
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching positions: {e}")
            return

        if not positions:
            await update.message.reply_text("📭 No open positions.")
            return

        lines = [f"📊 *Open Positions* ({len(positions)})\n"]
        for pos in positions:
            try:
                lines.append(_format_position(pos))
            except Exception as e:
                lines.append(f"⚠️ position parse error: {e}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_kill(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from backend.risk.kill_switch import kill_switch
            await kill_switch.activate(reason="Telegram /kill command")
            await update.message.reply_text("🔴 *Kill switch ACTIVATED*", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from backend.risk.kill_switch import kill_switch
            await kill_switch.reset()
            await update.message.reply_text("🟢 *Kill switch RESET — trading resumed*", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from backend.analytics.metrics_engine import metrics_engine
            perf = await metrics_engine.get_performance_metrics()
            win_rate = perf.get("win_rate", 0)
            total = perf.get("total_trades", 0)
            pnl = perf.get("total_pnl", 0)
            msg = (
                f"📈 *Performance Stats*\n"
                f"Total trades: `{total}`\n"
                f"Win rate: `{win_rate:.1%}`\n"
                f"Total P&L: `{pnl:.2f}`"
            )
        except Exception as e:
            msg = f"❌ Stats error: {e}"
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ---------------------------------------------------------------------- #
    # Heartbeat
    # ---------------------------------------------------------------------- #
    async def _heartbeat_loop(self) -> None:
        interval = int(os.getenv("TELEGRAM_HEARTBEAT_INTERVAL", "3600"))
        while self._running:
            try:
                await asyncio.sleep(interval)
                if self._running:
                    await self.send_message(
                        f"💓 *Heartbeat* — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("heartbeat: %s", e)


telegram_bot = TelegramBot()
