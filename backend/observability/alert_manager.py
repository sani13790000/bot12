"""
backend/observability/alert_manager.py — Merged canonical (Phase L + Phase 15)

Merged from alert_manager.py + alert_manager_v15.py
Unique additions from v15:
  - Deduplication window per rule
  - Rate limiting (15 alerts/min)
  - Callback system (add_callback/remove_callback)
  - Webhook delivery channel
  - Convenience methods: alert_kill_switch, alert_drawdown,
    alert_heartbeat_loss, alert_license_failure, alert_reconciliation_mismatch
  - stats(), reset(), history() with filtering
  - enable_rule() / disable_rule() / get_rule() / list_rules()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_HISTORY = 1000
_DEDUP_WINDOW_S = 300
_RATE_LIMIT_N = 15
_RATE_WIN_S = 60


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
    dedup_window_s: int = _DEDUP_WINDOW_S
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "level": self.level,
            "enabled": self.enabled,
            "dedup_s": self.dedup_window_s,
        }


_DEFAULT_RULES: List[AlertRule] = [
    AlertRule(
        "license_failure", "License validation failed", AlertLevel.CRITICAL, dedup_window_s=60
    ),
    AlertRule("license_expired", "License expired", AlertLevel.WARNING),
    AlertRule("license_device_limit", "Device limit reached", AlertLevel.WARNING),
    AlertRule("heartbeat_loss", "EA heartbeat missing", AlertLevel.CRITICAL, dedup_window_s=120),
    AlertRule("heartbeat_slow", "EA heartbeat latency > 30s", AlertLevel.WARNING),
    AlertRule(
        "kill_switch_activated", "Kill switch activated", AlertLevel.CRITICAL, dedup_window_s=30
    ),
    AlertRule("kill_switch_reset", "Kill switch reset", AlertLevel.INFO, dedup_window_s=30),
    AlertRule(
        "drawdown_critical", "Equity drawdown > 10%", AlertLevel.CRITICAL, dedup_window_s=180
    ),
    AlertRule("drawdown_warning", "Equity drawdown > 5%", AlertLevel.WARNING),
    AlertRule(
        "daily_loss_limit", "Daily loss limit reached", AlertLevel.CRITICAL, dedup_window_s=3600
    ),
    AlertRule(
        "reconciliation_mismatch",
        "Position mismatch broker vs local",
        AlertLevel.CRITICAL,
        dedup_window_s=300,
    ),
    AlertRule("reconciliation_failed", "Reconciliation failed", AlertLevel.WARNING),
    AlertRule("db_unhealthy", "Database not reachable", AlertLevel.CRITICAL),
    AlertRule("circuit_open", "Circuit breaker opened", AlertLevel.WARNING),
    AlertRule("slow_request", "Request > 2s", AlertLevel.WARNING),
    AlertRule("ml_drift", "ML model drift detected", AlertLevel.WARNING),
    AlertRule("test", "Manual test alert", AlertLevel.INFO, dedup_window_s=0),
]

AlertCallback = Callable[[str, AlertLevel, Optional[Dict[str, Any]]], Coroutine[Any, Any, None]]


@dataclass
class AlertRecord:
    rule_name: str
    level: AlertLevel
    message: str
    context: Dict[str, Any]
    ts: float = field(default_factory=time.time)
    sent: bool = False
    deduped: bool = False


class AlertManager:
    def __init__(self) -> None:
        self._token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
        self._webhook: Optional[str] = os.environ.get("ALERT_WEBHOOK_URL")
        self._history: Deque[AlertRecord] = deque(maxlen=_MAX_HISTORY)
        self._rules: Dict[str, AlertRule] = {r.name: r for r in _DEFAULT_RULES}
        self._dedup: Dict[str, float] = {}
        self._rate_win: Deque[float] = deque()
        self._callbacks: List[AlertCallback] = []
        self._sent_count: int = 0
        self._dedup_count: int = 0

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    def get_rule(self, name: str) -> Optional[AlertRule]:
        return self._rules.get(name)

    def get_rules(self) -> List[Dict[str, Any]]:
        return self.list_rules()

    def list_rules(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._rules.values()]

    def enable_rule(self, name: str) -> bool:
        if name in self._rules:
            self._rules[name].enabled = True
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        if name in self._rules:
            self._rules[name].enabled = False
            return True
        return False

    def add_callback(self, cb: AlertCallback) -> None:
        self._callbacks.append(cb)

    def remove_callback(self, cb: AlertCallback) -> None:
        self._callbacks = [c for c in self._callbacks if c is not cb]

    async def send(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        log_fn = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.critical,
        }.get(level, logger.info)
        log_fn("[ALERT][%s] %s | context=%s", level, message, context)
        self._history.append(
            AlertRecord(
                rule_name="", level=level, message=message, context=context or {}, sent=True
            )
        )
        if self._token and self._chat_id and level == AlertLevel.CRITICAL:
            await self._send_telegram("", level, message, context or {})

    async def fire(
        self,
        rule_name: str,
        context: Optional[Dict[str, Any]] = None,
        override_level: Optional[AlertLevel] = None,
        message: Optional[str] = None,
    ) -> bool:
        rule = self._rules.get(rule_name)
        if rule is None:
            rule = AlertRule(rule_name, rule_name, AlertLevel.WARNING)
            self._rules[rule_name] = rule
        if not rule.enabled:
            return False
        level = override_level or rule.level
        ctx = context or {}
        msg = message or rule.description
        if rule.dedup_window_s > 0:
            last = self._dedup.get(rule_name, 0.0)
            if time.time() - last < rule.dedup_window_s:
                self._history.append(
                    AlertRecord(
                        rule_name=rule_name, level=level, message=msg, context=ctx, deduped=True
                    )
                )
                self._dedup_count += 1
                return False
        now = time.time()
        while self._rate_win and self._rate_win[0] < now - _RATE_WIN_S:
            self._rate_win.popleft()
        if len(self._rate_win) >= _RATE_LIMIT_N:
            logger.warning("alert rate limit hit for rule=%s", rule_name)
            self._history.append(
                AlertRecord(
                    rule_name=rule_name, level=level, message=msg, context=ctx, deduped=True
                )
            )
            return False
        self._rate_win.append(now)
        self._dedup[rule_name] = now
        self._history.append(
            AlertRecord(rule_name=rule_name, level=level, message=msg, context=ctx, sent=True)
        )
        self._sent_count += 1
        tasks: List[Any] = []
        if level == AlertLevel.CRITICAL:
            tasks.append(self._send_telegram(rule_name, level, msg, ctx))
            tasks.append(self._send_webhook(rule_name, level, msg, ctx))
        elif level == AlertLevel.WARNING:
            tasks.append(self._send_telegram(rule_name, level, msg, ctx))
        for cb in self._callbacks:
            tasks.append(cb(rule_name, level, ctx))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("alert dispatch error: %s", r)
        return True

    async def alert_license_failure(
        self, reason: str, user_id: Optional[str] = None, device_id: Optional[str] = None
    ) -> bool:
        return await self.fire(
            "license_failure",
            context={"reason": reason, "user_id": user_id, "device_id": device_id},
            message=f"License validation failed: {reason}",
        )

    async def alert_heartbeat_loss(
        self, device_id: str, gap_s: float, user_id: Optional[str] = None
    ) -> bool:
        return await self.fire(
            "heartbeat_loss",
            context={"device_id": device_id, "gap_s": gap_s, "user_id": user_id},
            message=f"Heartbeat missing {gap_s:.0f}s for device {device_id}",
        )

    async def alert_kill_switch(self, actor: str, reason: str, scope: str = "global") -> bool:
        return await self.fire(
            "kill_switch_activated",
            context={"actor": actor, "reason": reason, "scope": scope},
            message=f"KILL SWITCH by {actor}: {reason}",
            override_level=AlertLevel.CRITICAL,
        )

    async def alert_drawdown(self, pct: float, equity_usd: Optional[float] = None) -> bool:
        rule = "drawdown_critical" if pct >= 10.0 else "drawdown_warning"
        level = AlertLevel.CRITICAL if pct >= 10.0 else AlertLevel.WARNING
        return await self.fire(
            rule,
            context={"drawdown_pct": pct, "equity_usd": equity_usd},
            message=f"Drawdown {pct:.1f}%",
            override_level=level,
        )

    async def alert_reconciliation_mismatch(
        self, symbol: str, broker_qty: float, local_qty: float
    ) -> bool:
        return await self.fire(
            "reconciliation_mismatch",
            context={
                "symbol": symbol,
                "broker_qty": broker_qty,
                "local_qty": local_qty,
                "delta": abs(broker_qty - local_qty),
            },
            message=f"Position mismatch {symbol}: broker={broker_qty} local={local_qty}",
            override_level=AlertLevel.CRITICAL,
        )

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.history(limit=limit)

    def history(
        self,
        level: Optional[AlertLevel] = None,
        rule_name: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        records = list(self._history)
        if level:
            records = [r for r in records if r.level == level]
        if rule_name:
            records = [r for r in records if r.rule_name == rule_name]
        if since_ts:
            records = [r for r in records if r.ts >= since_ts]
        records = records[-limit:]
        return [
            {
                "rule": r.rule_name,
                "level": r.level,
                "message": r.message,
                "context": r.context,
                "ts": r.ts,
                "sent": r.sent,
                "deduped": r.deduped,
            }
            for r in records
        ]

    def stats(self) -> Dict[str, Any]:
        return {
            "sent_total": self._sent_count,
            "dedup_total": self._dedup_count,
            "history_len": len(self._history),
            "rules_total": len(self._rules),
            "rate_window": len(self._rate_win),
        }

    def reset(self) -> None:
        self._history.clear()
        self._dedup.clear()
        self._rate_win.clear()
        self._sent_count = 0
        self._dedup_count = 0

    async def _send_telegram(
        self, rule: str, level: AlertLevel, msg: str, ctx: Dict[str, Any]
    ) -> None:
        if not self._token or not self._chat_id:
            return
        emoji = {"CRITICAL": "\u26a0\ufe0f", "WARNING": "\U0001f514"}.get(
            str(level), "\u2139\ufe0f"
        )
        text = f"{emoji} *[{level}]* {rule}: {msg}"
        try:
            import httpx

            async with httpx.AsyncClient(timeout=6.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                )
        except Exception as exc:
            logger.warning("Telegram alert failed: %s", exc)

    async def _send_webhook(
        self, rule: str, level: AlertLevel, msg: str, ctx: Dict[str, Any]
    ) -> None:
        if not self._webhook:
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=6.0) as client:
                await client.post(
                    self._webhook,
                    json={
                        "rule": rule,
                        "level": str(level),
                        "message": msg,
                        "context": ctx,
                        "ts": time.time(),
                    },
                )
        except Exception as exc:
            logger.warning("Webhook alert failed: %s", exc)


alert_manager = AlertManager()
