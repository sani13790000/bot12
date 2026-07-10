"""
backend/telegram/heartbeat.py
Heartbeat monitoring for Telegram bot connectivity.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramHeartbeat:
    """Monitor Telegram bot health."""

    def __init__(
        self,
        interval_seconds: int = 300,
        timeout_seconds: int = 30,
    ):
        """
        Initialize heartbeat monitor.

        Args:
            interval_seconds: Check interval
            timeout_seconds: Timeout for health check
        """
        self.interval = interval_seconds
        self.timeout = timeout_seconds
        self.last_check: Optional[datetime] = None
        self.is_healthy = True
        logger.info("[heartbeat] Initialized with interval=%ds", interval_seconds)

    async def start(self, bot) -> None:
        """
        Start heartbeat monitoring.

        Args:
            bot: Telegram bot instance
        """
        logger.info("[heartbeat] Starting heartbeat monitor")
        while True:
            try:
                await self._check_health(bot)
                self.last_check = datetime.utcnow()
            except asyncio.TimeoutError:
                logger.error("[heartbeat] Health check timed out")
                self.is_healthy = False
            except Exception as exc:
                logger.error("[heartbeat] Health check failed: %s", exc)
                self.is_healthy = False

            await asyncio.sleep(self.interval)

    async def _check_health(self, bot) -> None:
        """
        Check bot health.

        Args:
            bot: Telegram bot instance
        """
        try:
            # Try to get bot info
            await asyncio.wait_for(
                bot.get_me(),
                timeout=self.timeout
            )
            self.is_healthy = True
            logger.debug("[heartbeat] Health check passed")
        except asyncio.TimeoutError:
            logger.error("[heartbeat] Health check timeout - bot unresponsive")
            raise
        except Exception as exc:
            logger.error("[heartbeat] Health check error: %s", exc)
            raise

    def get_status(self) -> dict:
        """Get current heartbeat status."""
        return {
            'is_healthy': self.is_healthy,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'uptime': 'unknown'
        }
