"""Alert manager. Phase L fixes L-14/L-19/L-20/L-21."""
from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)
_MAX_HISTORY = 500


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class AlertRule:
    name: str
    description: str
    level: AlertLevel = AlertLevel.WARNING
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "level": self.level, "enabled": self.enabled}


_DEFAULT_RULES: List[AlertRule] = [
    AlertRule("high_drawdown",    "Equity drawdown > 10%",    AlertLevel.CRITICAL),
    AlertRule("daily_loss_limit", "Daily loss limit reached", AlertLevel.CRITICAL),
    AlertRule("db_unhealthy",     "Database not reachable",   AlertLevel.CRITICAL),
    AlertRule("circuit_open",     "Circuit breaker opened",   AlertLevel.WARNING),
    AlertRule("slow_request",     "Request > 2s",             AlertLevel.WARNING),
    AlertRule("ml_drift",         "ML model drift detected",  AlertLevel.WARNING),
    AlertRule("test",             "Manual test alert",        AlertLevel.INFO),
]


class AlertManager:
    def __init__(self) -> None:
        self._token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
        self._history: Deque[Dict[str, Any]] = deque(maxlen=_MAX_HISTORY)
        self._rules: Dict[str, AlertRule] = {r.name: r for r in _DEFAULT_RULES}

    async def send(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        log_fn = {AlertLevel.INFO: logger.info, AlertLevel.WARNING: logger.warning,
                  AlertLevel.CRITICAL: logger.critical}.get(level, logger.info)
        log_fn("[ALERT][%s] %s | context=%s", level, message, context)
        self._history.append({
            "level": level, "message": message,
            "context": context or {},
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if self._token and self._chat_id and level == AlertLevel.CRITICAL:
            await self._send_telegram(message, level)

    async def fire(self, rule_name: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """FIX L-14."""
        rule = self._rules.get(rule_name)
        if rule is None:
            logger.warning("Alert rule '%s' not found", rule_name)
            return False
        if not rule.enabled:
            return False
        await self.send(message=f"[{rule_name}] {rule.description}",
                        level=rule.level, context=context)
        return True

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """FIX L-14."""
        items = list(self._history)
        items.reverse()
        return items[:limit]

    def get_rules(self) -> List[Dict[str, Any]]:
        """FIX L-14."""
        return [r.to_dict() for r in self._rules.values()]

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    async def _send_telegram(self, message: str, level: AlertLevel) -> None:
        """FIX L-20: 5s timeout."""
        try:
            import httpx
            icon = {AlertLevel.CRITICAL: "\u26a0\ufe0f", AlertLevel.WARNING: "\U0001f514"}.get(level, "\u2139\ufe0f")
            text = f"{icon} *[{level}]*\n{message}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                )
        except Exception as exc:
            logger.warning("Telegram alert failed: %s", exc)


alert_manager = AlertManager()
