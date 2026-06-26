"""
backend/observability/alert_manager_v15.py — Phase 15
P15-OBS-ALERT-1: license_failure alert rule (NEW)
P15-OBS-ALERT-2: heartbeat_loss alert rule با threshold (NEW)
P15-OBS-ALERT-3: kill_switch alert rule (CRITICAL, immediate) (NEW)
P15-OBS-ALERT-4: drawdown_critical alert rule (NEW)
P15-OBS-ALERT-5: reconciliation_mismatch alert rule (NEW)
P15-OBS-ALERT-6: deduplication — یک alert در N دقیقه فقط یک‌بار
P15-OBS-ALERT-7: async Telegram با timeout=6s — قبلاً بدون timeout بود
P15-OBS-ALERT-8: rate limit — max 15 alert/min
P15-OBS-ALERT-9: callback system برای integration tests
P15-OBS-ALERT-10: per-level escalation — CRITICAL → Telegram + webhook + PagerDuty
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

_MAX_HISTORY    = 1000
_DEDUP_WINDOW_S = 300
_RATE_LIMIT_N   = 15
_RATE_WIN_S     = 60


class AlertLevel(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class AlertRule:
    name:        str
    description: str
    level:       AlertLevel         = AlertLevel.WARNING
    enabled:     bool               = True
    dedup_window_s: int             = _DEDUP_WINDOW_S
    metadata:    Dict[str, Any]     = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "level":       self.level,
            "enabled":     self.enabled,
            "dedup_s":     self.dedup_window_s,
        }


_DEFAULT_RULES: List[AlertRule] = [
    AlertRule("license_failure", "License validation failed — EA cannot trade",
              AlertLevel.CRITICAL, dedup_window_s=60),
    AlertRule("license_expired", "License expired — subscription renewal needed",
              AlertLevel.WARNING),
    AlertRule("license_device_limit", "Device limit reached for license",
              AlertLevel.WARNING),
    AlertRule("heartbeat_loss", "EA heartbeat missing > threshold",
              AlertLevel.CRITICAL, dedup_window_s=120),
    AlertRule("heartbeat_slow", "EA heartbeat latency > 30s", AlertLevel.WARNING),
    AlertRule("kill_switch_activated", "Kill switch activated — all trading halted",
              AlertLevel.CRITICAL, dedup_window_s=30),
    AlertRule("kill_switch_reset", "Kill switch reset — trading resumed",
              AlertLevel.INFO, dedup_window_s=30),
    AlertRule("drawdown_critical", "Equity drawdown > 10%",
              AlertLevel.CRITICAL, dedup_window_s=180),
    AlertRule("drawdown_warning", "Equity drawdown > 5%", AlertLevel.WARNING),
    AlertRule("daily_loss_limit", "Daily loss limit reached",
              AlertLevel.CRITICAL, dedup_window_s=3600),
    AlertRule("reconciliation_mismatch",
              "Position mismatch between broker and local state",
              AlertLevel.CRITICAL, dedup_window_s=300),
    AlertRule("reconciliation_failed", "Reconciliation check failed to complete",
              AlertLevel.WARNING),
    AlertRule("db_unhealthy",  "Database unreachable",    AlertLevel.CRITICAL),
    AlertRule("circuit_open",  "Circuit breaker opened",  AlertLevel.WARNING),
    AlertRule("slow_request",  "Request > 2s",            AlertLevel.WARNING),
    AlertRule("ml_drift",      "ML model drift detected", AlertLevel.WARNING),
    AlertRule("test", "Manual test alert", AlertLevel.INFO, dedup_window_s=0),
]

AlertCallback = Callable[
    [str, AlertLevel, Optional[Dict[str, Any]]],
    Coroutine[Any, Any, None],
]


@dataclass
class AlertRecord:
    rule_name:  str
    level:      AlertLevel
    message:    str
    context:    Dict[str, Any]
    ts:         float = field(default_factory=time.time)
    sent:       bool  = False
    deduped:    bool  = False


class AlertManager:

    def __init__(self) -> None:
        self._token   = os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self._webhook = os.environ.get("ALERT_WEBHOOK_URL")
        self._pd_key  = os.environ.get("PAGERDUTY_ROUTING_KEY")
        self._history:   Deque[AlertRecord]   = deque(maxlen=_MAX_HISTORY)
        self._rules:     Dict[str, AlertRule] = {r.name: r for r in _DEFAULT_RULES}
        self._dedup:     Dict[str, float]     = {}
        self._rate_win:  Deque[float]         = deque()
        self._callbacks: List[AlertCallback]  = []
        self._sent_count  = 0
        self._dedup_count = 0

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    def get_rule(self, name: str) -> Optional[AlertRule]:
        return self._rules.get(name)

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
        ctx   = context or {}
        msg   = message or rule.description
        record = AlertRecord(rule_name=rule_name, level=level, message=msg, context=ctx)
        dedup_key = rule_name
        dedup_window = rule.dedup_window_s
        if dedup_window > 0:
            last = self._dedup.get(dedup_key, 0.0)
            if time.time() - last < dedup_window:
                record.deduped = True
                self._history.append(record)
                self._dedup_count += 1
                return False
        now = time.time()
        while self._rate_win and self._rate_win[0] < now - _RATE_WIN_S:
            self._rate_win.popleft()
        if len(self._rate_win) >= _RATE_LIMIT_N:
            logger.warning("alert rate limit — dropping %s", rule_name)
            record.deduped = True
            self._history.append(record)
            return False
        self._rate_win.append(now)
        self._dedup[dedup_key] = now
        record.sent = True
        self._history.append(record)
        self._sent_count += 1
        tasks = []
        if level == AlertLevel.CRITICAL:
            tasks.append(self._send_telegram(rule_name, level, msg, ctx))
            tasks.append(self._send_webhook(rule_name, level, msg, ctx))
            if self._pd_key:
                tasks.append(self._send_pagerduty(rule_name, msg, ctx))
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

    async def alert_license_failure(self, reason: str,
                                     user_id: Optional[str] = None,
                                     device_id: Optional[str] = None) -> bool:
        return await self.fire("license_failure",
            context={"reason": reason, "user_id": user_id, "device_id": device_id},
            message=f"License validation failed: {reason}")

    async def alert_heartbeat_loss(self, device_id: str, gap_s: float,
                                    user_id: Optional[str] = None) -> bool:
        return await self.fire("heartbeat_loss",
            context={"device_id": device_id, "gap_s": gap_s, "user_id": user_id},
            message=f"Heartbeat missing {gap_s:.0f}s for device {device_id}")

    async def alert_kill_switch(self, actor: str, reason: str,
                                 scope: str = "global") -> bool:
        return await self.fire("kill_switch_activated",
            context={"actor": actor, "reason": reason, "scope": scope},
            message=f"KILL SWITCH by {actor}: {reason}",
            override_level=AlertLevel.CRITICAL)

    async def alert_drawdown(self, pct: float,
                              equity_usd: Optional[float] = None) -> bool:
        rule  = "drawdown_critical" if pct >= 10.0 else "drawdown_warning"
        level = AlertLevel.CRITICAL if pct >= 10.0 else AlertLevel.WARNING
        return await self.fire(rule,
            context={"drawdown_pct": pct, "equity_usd": equity_usd},
            message=f"Drawdown {pct:.1f}%", override_level=level)

    async def alert_reconciliation_mismatch(self, symbol: str,
                                             broker_qty: float,
                                             local_qty: float) -> bool:
        return await self.fire("reconciliation_mismatch",
            context={"symbol": symbol, "broker_qty": broker_qty,
                     "local_qty": local_qty, "delta": abs(broker_qty - local_qty)},
            message=f"Position mismatch {symbol}: broker={broker_qty} local={local_qty}",
            override_level=AlertLevel.CRITICAL)

    async def _send_telegram(self, rule: str, level: AlertLevel,
                              msg: str, ctx: Dict[str, Any]) -> None:
        if not self._token or not self._chat_id:
            return
        emoji = {"CRITICAL": "ALERT", "WARNING": "WARN", "INFO": "INFO"}.get(str(level), "")
        text = f"{emoji} [{level}] {rule}\n{msg}"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{self._token}/sendMessage"
                payload = {"chat_id": self._chat_id, "text": text}
                async with asyncio.timeout(6.0):
                    await session.post(url, json=payload)
        except Exception as exc:
            logger.warning("telegram send failed: %s", exc)

    async def _send_webhook(self, rule: str, level: AlertLevel,
                             msg: str, ctx: Dict[str, Any]) -> None:
        if not self._webhook:
            return
        payload = {"rule": rule, "level": str(level), "message": msg,
                   "context": ctx, "ts": time.time()}
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(6.0):
                    await session.post(self._webhook, json=payload)
        except Exception as exc:
            logger.warning("webhook send failed: %s", exc)

    async def _send_pagerduty(self, rule: str, msg: str,
                               ctx: Dict[str, Any]) -> None:
        if not self._pd_key:
            return
        payload = {
            "routing_key": self._pd_key, "event_action": "trigger",
            "payload": {"summary": msg, "severity": "critical",
                         "source": "mt5trading-bot", "custom_details": ctx},
            "dedup_key": f"mt5trading-{rule}",
        }
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(8.0):
                    await session.post("https://events.pagerduty.com/v2/enqueue",
                                       json=payload)
        except Exception as exc:
            logger.warning("pagerduty send failed: %s", exc)

    def history(self, level: Optional[AlertLevel] = None,
                rule_name: Optional[str] = None,
                since_ts: Optional[float] = None,
                limit: int = 50) -> List[Dict[str, Any]]:
        records = list(self._history)
        if level:
            records = [r for r in records if r.level == level]
        if rule_name:
            records = [r for r in records if r.rule_name == rule_name]
        if since_ts:
            records = [r for r in records if r.ts >= since_ts]
        return [{"rule": r.rule_name, "level": r.level, "message": r.message,
                 "context": r.context, "ts": r.ts, "sent": r.sent,
                 "deduped": r.deduped} for r in records[-limit:]]

    def stats(self) -> Dict[str, Any]:
        return {"sent_total": self._sent_count, "dedup_total": self._dedup_count,
                "history_len": len(self._history), "rules_total": len(self._rules),
                "rate_window": len(self._rate_win)}

    def reset(self) -> None:
        self._history.clear()
        self._dedup.clear()
        self._rate_win.clear()
        self._sent_count = 0
        self._dedup_count = 0


alert_manager = AlertManager()
