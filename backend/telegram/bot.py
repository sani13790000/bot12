"""
Telegram Bot - Real-time trading alerts and management via Telegram.

Provides:
- Real-time trade notifications
- Position monitoring
- Manual trade commands
- Risk management alerts
- Strategy status updates

Integration with FastAPI handlers for message routing.
"""

import logging
import os
from typing import Optional, Dict, Any
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    """Telegram message wrapper."""
    chat_id: str
    text: str
    parse_mode: str = "HTML"
    disable_notification: bool = False


@dataclass
class TelegramUpdate:
    """Telegram update (message from user)."""
    update_id: int
    chat_id: str
    user_id: str
    text: str
    message_type: str  # 'text', 'command', 'callback'


class TelegramBot:
    """Telegram bot for trading alerts and commands."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        base_url: str = "https://api.telegram.org"
    ):
        """
        Initialize Telegram Bot.

        Args:
            token: Bot API token (defaults to TELEGRAM_BOT_TOKEN env var)
            chat_id: Default chat ID (defaults to TELEGRAM_CHAT_ID env var)
            base_url: Telegram API base URL
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.base_url = base_url
        self.api_url = f"{base_url}/bot{self.token}"

        if not self.token:
            logger.warning("[telegram] No token provided - bot notifications disabled")
        if not self.chat_id:
            logger.warning("[telegram] No chat_id provided - using updates only")

    async def send_message(self, message: TelegramMessage) -> bool:
        """
        Send message to Telegram chat.

        Args:
            message: TelegramMessage object

        Returns:
            True if sent successfully
        """
        if not self.token:
            logger.warning("[telegram] Cannot send: no token configured")
            return False

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": message.chat_id or self.chat_id,
            "text": message.text,
            "parse_mode": message.parse_mode,
            "disable_notification": message.disable_notification,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info("[telegram] Message sent to chat=%s", message.chat_id or self.chat_id)
                        return True
                    else:
                        logger.error("[telegram] Failed to send: status=%d", resp.status)
                        return False
        except Exception as exc:
            logger.error("[telegram] send_message error: %s", exc)
            return False

    async def send_trade_alert(
        self,
        symbol: str,
        signal_type: str,  # BUY, SELL
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        position_size: float,
        confidence: float,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send trade signal alert.

        Args:
            symbol: Trading instrument
            signal_type: BUY or SELL
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            position_size: Position size in lots
            confidence: Signal confidence (0-1)
            chat_id: Override default chat ID

        Returns:
            True if sent successfully
        """
        emoji = "📈" if signal_type == "BUY" else "📉"
        text = f"""{emoji} <b>{signal_type} Signal: {symbol}</b>
<b>Entry:</b> {entry_price:.5f}
<b>SL:</b> {stop_loss:.5f}
<b>TP:</b> {take_profit:.5f}
<b>Size:</b> {position_size:.2f} lots
<b>Confidence:</b> {confidence*100:.0f}%
<b>R/R:</b> {self._calculate_rr(entry_price, stop_loss, take_profit):.2f}:1
"""

        message = TelegramMessage(
            chat_id=chat_id or self.chat_id,
            text=text,
            parse_mode="HTML"
        )
        return await self.send_message(message)

    async def send_position_update(
        self,
        symbol: str,
        position_type: str,  # OPEN, UPDATE, CLOSE
        current_pnl: float,
        current_price: float,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send position update alert.

        Args:
            symbol: Trading instrument
            position_type: OPEN, UPDATE, or CLOSE
            current_pnl: Current profit/loss
            current_price: Current market price
            chat_id: Override default chat ID

        Returns:
            True if sent successfully
        """
        emoji_map = {
            "OPEN": "🟢",
            "UPDATE": "🟡",
            "CLOSE": "🔴"
        }
        emoji = emoji_map.get(position_type, "❓")
        pnl_emoji = "📈" if current_pnl >= 0 else "📉"

        text = f"""{emoji} <b>{position_type}: {symbol}</b>
{pnl_emoji} <b>P&L:</b> ${current_pnl:+.2f}
<b>Price:</b> {current_price:.5f}
"""

        message = TelegramMessage(
            chat_id=chat_id or self.chat_id,
            text=text,
            parse_mode="HTML"
        )
        return await self.send_message(message)

    async def send_risk_alert(
        self,
        alert_type: str,  # MARGIN, EQUITY, STRATEGY
        message_text: str,
        severity: str = "WARNING",  # INFO, WARNING, CRITICAL
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send risk management alert.

        Args:
            alert_type: Type of alert
            message_text: Alert message
            severity: Severity level
            chat_id: Override default chat ID

        Returns:
            True if sent successfully
        """
        severity_emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨"
        }
        emoji = severity_emoji.get(severity, "❓")

        text = f"{emoji} <b>{severity} - {alert_type}</b>\n{message_text}"

        message = TelegramMessage(
            chat_id=chat_id or self.chat_id,
            text=text,
            parse_mode="HTML",
            disable_notification=(severity == "INFO")
        )
        return await self.send_message(message)

    async def send_strategy_status(
        self,
        enabled: bool,
        active_positions: int,
        daily_pnl: float,
        success_rate: float,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send strategy status report.

        Args:
            enabled: Is strategy enabled
            active_positions: Number of open positions
            daily_pnl: Daily P&L
            success_rate: Win rate (0-1)
            chat_id: Override default chat ID

        Returns:
            True if sent successfully
        """
        status_emoji = "🟢" if enabled else "🔴"
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

        text = f"""📊 <b>Strategy Status Report</b>
{status_emoji} <b>Status:</b> {'ENABLED' if enabled else 'DISABLED'}
<b>Positions:</b> {active_positions} open
{pnl_emoji} <b>Daily P&L:</b> ${daily_pnl:+.2f}
<b>Win Rate:</b> {success_rate*100:.1f}%
"""

        message = TelegramMessage(
            chat_id=chat_id or self.chat_id,
            text=text,
            parse_mode="HTML"
        )
        return await self.send_message(message)

    @staticmethod
    def _calculate_rr(entry: float, sl: float, tp: float) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return reward / risk if risk > 0 else 0.0


# Global bot instance
_bot_instance: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    """Get or create global Telegram bot instance."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TelegramBot()
    return _bot_instance
