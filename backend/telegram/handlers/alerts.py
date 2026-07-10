"""
backend/telegram/handlers/alerts.py
Telegram alert handlers for trading notifications.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AlertHandler:
    """Handle trading alerts via Telegram."""

    def __init__(self, bot=None):
        """
        Initialize alert handler.

        Args:
            bot: Telegram bot instance
        """
        self.bot = bot
        logger.info("[alerts] AlertHandler initialized")

    async def send_trade_alert(
        self,
        symbol: str,
        signal: str,
        price: float,
        confidence: float,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send trade alert.

        Args:
            symbol: Trading symbol
            signal: BUY or SELL
            price: Entry price
            confidence: Confidence level (0-1)
            chat_id: Override default chat

        Returns:
            True if sent successfully
        """
        if not self.bot:
            logger.warning("[alerts] No bot configured - alert not sent")
            return False

        try:
            emoji = "📈" if signal == "BUY" else "📉"
            message = (
                f"{emoji} <b>{signal}: {symbol}</b>\n"
                f"Price: {price:.5f}\n"
                f"Confidence: {confidence*100:.0f}%"
            )
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML"
            )
            logger.info("[alerts] Trade alert sent: %s %s @ %.5f", signal, symbol, price)
            return True
        except Exception as exc:
            logger.error("[alerts] Failed to send alert: %s", exc)
            return False

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "WARNING",
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send risk management alert.

        Args:
            alert_type: Type of alert
            message: Alert message
            severity: INFO, WARNING, or CRITICAL
            chat_id: Override default chat

        Returns:
            True if sent successfully
        """
        if not self.bot:
            logger.warning("[alerts] No bot configured - risk alert not sent")
            return False

        try:
            emoji_map = {
                "INFO": "ℹ️",
                "WARNING": "⚠️",
                "CRITICAL": "🚨"
            }
            emoji = emoji_map.get(severity, "❓")
            
            full_message = f"{emoji} <b>{severity}: {alert_type}</b>\n{message}"
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=full_message,
                parse_mode="HTML"
            )
            logger.info("[alerts] Risk alert sent: %s (severity=%s)", alert_type, severity)
            return True
        except Exception as exc:
            logger.error("[alerts] Failed to send risk alert: %s", exc)
            return False
