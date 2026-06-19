"""Alert manager for Galaxy Vast AI Trading Platform.

Handles critical alerts via:
1. Structured logging (always)
2. Telegram (if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID configured)
"""
from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertManager:
    """Centralised alert dispatcher."""

    def __init__(self) -> None:
        self._token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
        self._history: List[Dict[str, Any]] = []
        self._max_history = 500

    async def send(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send an alert via logging and optionally Telegram."""
        log_fn = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.critical,
        }.get(level, logger.info)

        log_fn("[ALERT][%s] %s | context=%s", level, message, context)

        entry = {
            "level": level,
            "message": message,
            "context": context or {},
        }
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        if self._token and self._chat_id and level == AlertLevel.CRITICAL:
            await self._send_telegram(message, level)

    async def _send_telegram(self, message: str, level: AlertLevel) -> None:
        """Send Telegram message — fire-and-forget."""
        try:
            import httpx
            icon = {AlertLevel.CRITICAL: "\u26a0\ufe0f", AlertLevel.WARNING: "\U0001f514"}.get(
                level, "\u2139\ufe0f"
            )
            text = f"{icon} *Galaxy Vast Alert*\n\n*Level:* {level}\n*Message:* {message}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram alert failed: %s", exc)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._history[-limit:]


# Module-level singleton
alert_manager = AlertManager()
