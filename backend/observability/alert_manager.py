"""
faz 9 - Alert Manager
Threshold-based alerts ba Telegram + Sentry + structured log
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .structured_logger import get_logger

logger = get_logger("alert_manager")


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class AlertRule:
    name: str
    severity: AlertSeverity
    message_template: str
    min_interval_seconds: float = 300.0  # 5 min deduplication
    _last_fired: float = field(default=0.0, init=False, repr=False)

    def should_fire(self) -> bool:
        now = time.time()
        if now - self._last_fired >= self.min_interval_seconds:
            self._last_fired = now
            return True
        return False


@dataclass
class Alert:
    rule_name: str
    severity: AlertSeverity
    message: str
    context: Dict[str, Any]
    fired_at: float = field(default_factory=time.time)


class AlertManager:
    """Centralized alert manager"""

    def __init__(self) -> None:
        self._rules: Dict[str, AlertRule] = {}
        self._history: List[Alert] = []
        self._max_history = 500
        self._handlers: List[Callable] = []
        self._telegram_fn: Optional[Callable] = None
        self._sentry_fn: Optional[Callable] = None
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        rules = [
            AlertRule(
                name="circuit_breaker_open",
                severity=AlertSeverity.CRITICAL,
                message_template="Circuit breaker OPEN: {service}",
                min_interval_seconds=60,
            ),
            AlertRule(
                name="ml_drift_high",
                severity=AlertSeverity.WARNING,
                message_template="ML concept drift: {symbol} score={score:.3f}",
                min_interval_seconds=600,
            ),
            AlertRule(
                name="db_slow_query",
                severity=AlertSeverity.WARNING,
                message_template="Slow DB query: {table} op={op} duration={duration_ms:.0f}ms",
                min_interval_seconds=120,
            ),
            AlertRule(
                name="mt5_disconnected",
                severity=AlertSeverity.CRITICAL,
                message_template="MT5 disconnected: {reason}",
                min_interval_seconds=30,
            ),
            AlertRule(
                name="trade_loss_streak",
                severity=AlertSeverity.WARNING,
                message_template="Loss streak: {count} consecutive losses, last={symbol}",
                min_interval_seconds=300,
            ),
            AlertRule(
                name="daily_loss_limit",
                severity=AlertSeverity.CRITICAL,
                message_template="Daily loss limit reached: {pnl_usd:.2f} USD",
                min_interval_seconds=3600,
            ),
            AlertRule(
                name="model_retrain_failed",
                severity=AlertSeverity.ERROR,
                message_template="Model retrain failed: {symbol} error={error}",
                min_interval_seconds=300,
            ),
            AlertRule(
                name="execution_dead_letter",
                severity=AlertSeverity.ERROR,
                message_template="Order dead-lettered: signal={signal_id} retcode={retcode}",
                min_interval_seconds=60,
            ),
            AlertRule(
                name="news_fetch_failed",
                severity=AlertSeverity.WARNING,
                message_template="News fetch failed: {error}",
                min_interval_seconds=600,
            ),
            AlertRule(
                name="reconciliation_mismatch",
                severity=AlertSeverity.ERROR,
                message_template="Position mismatch: MT5={mt5_count} DB={db_count}",
                min_interval_seconds=120,
            ),
        ]
        for rule in rules:
            self._rules[rule.name] = rule

    def register_telegram(self, send_fn: Callable) -> None:
        """Register async Telegram send function"""
        self._telegram_fn = send_fn

    def register_sentry(self, capture_fn: Callable) -> None:
        """Register Sentry capture function"""
        self._sentry_fn = capture_fn

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    async def fire(self, rule_name: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Fire an alert if rule allows"""
        context = context or {}
        rule = self._rules.get(rule_name)
        if rule is None:
            logger.warning(f"Unknown alert rule: {rule_name}")
            return False

        if not rule.should_fire():
            return False

        try:
            message = rule.message_template.format(**context)
        except (KeyError, ValueError):
            message = f"{rule_name}: {context}"

        alert = Alert(
            rule_name=rule_name,
            severity=rule.severity,
            message=message,
            context=context,
        )

        # Store history
        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Structured log
        log_fn = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(rule.severity, logger.warning)
        log_fn(f"ALERT [{rule.severity}]: {message}", rule=rule_name, **context)

        # Telegram (CRITICAL + ERROR)
        if self._telegram_fn and rule.severity in (AlertSeverity.CRITICAL, AlertSeverity.ERROR):
            try:
                emoji = {AlertSeverity.CRITICAL: "🚨", AlertSeverity.ERROR: "❌"}.get(rule.severity, "⚠️")
                await self._telegram_fn(f"{emoji} {message}")
            except Exception as e:
                logger.error(f"Telegram alert failed: {e}")

        # Sentry (CRITICAL + ERROR)
        if self._sentry_fn and rule.severity in (AlertSeverity.CRITICAL, AlertSeverity.ERROR):
            try:
                self._sentry_fn(Exception(message), extras=context)
            except Exception:
                pass

        return True

    def get_history(self, limit: int = 50) -> List[Dict]:
        return [
            {
                "rule": a.rule_name,
                "severity": a.severity,
                "message": a.message,
                "fired_at": a.fired_at,
            }
            for a in self._history[-limit:]
        ]

    def get_rules(self) -> Dict[str, Dict]:
        return {
            name: {
                "severity": r.severity,
                "min_interval_seconds": r.min_interval_seconds,
                "last_fired": r._last_fired,
            }
            for name, r in self._rules.items()
        }


# Singleton
alert_manager = AlertManager()
