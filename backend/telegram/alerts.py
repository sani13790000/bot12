"""
backend/telegram/alerts.py
Phase-9 — Telegram Security Alerts

Sends real-time security alerts to admin IDs for:
  * Critical anomaly detected
  * Multiple failed login attacks
  * Suspicious trading detected
  * Security score drop below threshold
  * IP auto-blocked
  * System events (retrain, circuit breaker)

Design:
  * Completely decoupled from bot.py.
  * Uses httpx directly via Telegram Bot API.
  * 8s timeout, fire-and-forget.
  * Deduplicated — same alert within 60s suppressed.
  * Rate-limited per admin: max 20 alerts/minute.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set

import httpx

log = logging.getLogger(__name__)

_BOT_TOKEN:     str       = os.getenv("TELEGRAM_BOT_TOKEN", "")
_ADMIN_IDS:     List[int] = []
_SEND_TIMEOUT_S: float    = 8.0
_DEDUP_WINDOW_S: int      = 60
_RATE_LIMIT:     int      = 20
_RATE_WINDOW_S:  int      = 60

_EMOJI = {
    "critical": "\U0001f6a8",
    "high":     "\U000026a0",
    "medium":   "\U0001f4e2",
    "low":      "\U00002139",
    "ok":       "\U00002705",
    "block":    "\U0001f6d1",
    "score":    "\U0001f4ca",
    "trade":    "\U0001f4b0",
    "login":    "\U0001f512",
    "system":   "\U0001f916",
}


class AlertSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


_sent_hashes:  Set[str]               = set()
_hash_times:   Dict[str, float]       = {}
_rate_buckets: Dict[int, Deque[float]] = defaultdict(lambda: deque())
_state_lock:   Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _state_lock
    if _state_lock is None:
        _state_lock = asyncio.Lock()
    return _state_lock


def _get_admin_ids() -> List[int]:
    global _ADMIN_IDS
    if _ADMIN_IDS:
        return _ADMIN_IDS
    try:
        from backend.core.config import settings
        raw = getattr(settings, "TELEGRAM_ADMIN_IDS", "")
        if raw:
            _ADMIN_IDS = [int(x.strip()) for x in str(raw).split(",") if x.strip()]
            return _ADMIN_IDS
        single = getattr(settings, "TELEGRAM_ADMIN_ID", "")
        if single:
            _ADMIN_IDS = [int(single)]
    except Exception:
        pass
    raw_env = os.getenv("TELEGRAM_ADMIN_IDS", os.getenv("TELEGRAM_ADMIN_ID", ""))
    if raw_env:
        _ADMIN_IDS = [int(x.strip()) for x in raw_env.split(",") if x.strip()]
    return _ADMIN_IDS


def _alert_hash(text: str) -> str:
    return hashlib.md5(text[:200].encode(), usedforsecurity=False).hexdigest()


def _is_duplicate(h: str) -> bool:
    now   = time.monotonic()
    stale = [k for k, t in _hash_times.items() if now - t > _DEDUP_WINDOW_S]
    for k in stale:
        _hash_times.pop(k, None)
        _sent_hashes.discard(k)
    if h in _sent_hashes:
        return True
    _sent_hashes.add(h)
    _hash_times[h] = now
    return False


def _is_rate_limited(admin_id: int) -> bool:
    now    = time.monotonic()
    bucket = _rate_buckets[admin_id]
    while bucket and now - bucket[0] > _RATE_WINDOW_S:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT:
        return True
    bucket.append(now)
    return False


async def _send_one(admin_id: int, text: str) -> bool:
    token = _BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": admin_id, "text": text[:4096], "parse_mode": "Markdown"}
    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_S) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as exc:
        log.debug("Telegram send to %d: %s", admin_id, exc)
        return False


async def _broadcast(text: str, severity: AlertSeverity = AlertSeverity.MEDIUM) -> None:
    admins = _get_admin_ids()
    if not admins:
        return
    h = _alert_hash(text)
    async with _get_lock():
        if _is_duplicate(h):
            return
    tasks = []
    for admin_id in admins:
        async with _get_lock():
            if _is_rate_limited(admin_id):
                continue
        tasks.append(asyncio.create_task(_send_one(admin_id, text)))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def send_admin_message(text: str) -> None:
    """Generic admin message — compatible with previous bot.py signature."""
    await _broadcast(text, AlertSeverity.MEDIUM)


async def alert_critical_anomaly(
    ip: str, score: float, risk_level: str,
    explanations: List[str], user_id: Optional[str] = None,
) -> None:
    emoji   = _EMOJI["critical"]
    details = "\n".join(f"  * {e}" for e in explanations[:5])
    uid     = f"\nUser: `{user_id}`" if user_id else ""
    text = (
        f"{emoji} *CRITICAL ANOMALY DETECTED*\n"
        f"IP: `{ip}`{uid}\n"
        f"Score: `{score:.3f}`\n"
        f"Risk: `{risk_level.upper()}`\n"
        f"Reasons:\n{details}\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.CRITICAL)


async def alert_failed_login_attack(
    ip: str, count: int, window_minutes: int = 5,
    usernames_tried: Optional[List[str]] = None,
) -> None:
    emoji = _EMOJI["login"]
    users = ""
    if usernames_tried:
        sample = ", ".join(f"`{u}`" for u in usernames_tried[:3])
        users  = f"\nUsernames tried: {sample}"
    text = (
        f"{emoji} *FAILED LOGIN ATTACK*\n"
        f"IP: `{ip}`\n"
        f"Attempts: `{count}` in `{window_minutes}` min{users}\n"
        f"Action: IP rate-limited + flagged\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.HIGH)


async def alert_suspicious_trading(
    user_id: str, symbol: str, reason: str,
    volume_change_pct: Optional[float] = None,
    trade_count: Optional[int] = None,
) -> None:
    emoji = _EMOJI["trade"]
    vol   = f"\nVolume change: `{volume_change_pct:+.1f}%`" if volume_change_pct else ""
    cnt   = f"\nTrade count: `{trade_count}`" if trade_count else ""
    text  = (
        f"{emoji} *SUSPICIOUS TRADING DETECTED*\n"
        f"User: `{user_id}`\n"
        f"Symbol: `{symbol}`\n"
        f"Reason: {reason}{vol}{cnt}\n"
        f"Action: Account flagged + circuit breaker armed\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.HIGH)


async def alert_score_drop(
    current_score: float, previous_score: float, threshold: float,
    top_risk_factors: Optional[List[str]] = None,
) -> None:
    drop  = previous_score - current_score
    emoji = _EMOJI["critical"] if current_score < 40 else _EMOJI["score"]
    level = "CRITICAL" if current_score < 40 else "WARNING"
    risks = ""
    if top_risk_factors:
        risks = "\nTop risks:\n" + "\n".join(f"  * {r}" for r in top_risk_factors[:4])
    text  = (
        f"{emoji} *SECURITY SCORE {level}*\n"
        f"Score: `{current_score:.1f}/100` (down `{drop:.1f}` from `{previous_score:.1f}`)\n"
        f"Threshold: `{threshold:.1f}`{risks}\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.CRITICAL if current_score < 40 else AlertSeverity.HIGH)


async def alert_ip_blocked(
    ip: str, reason: str, duration_seconds: int, auto: bool = True,
) -> None:
    emoji  = _EMOJI["block"]
    source = "AUTO" if auto else "MANUAL"
    dur    = f"{duration_seconds // 60} min" if duration_seconds < 3600 else f"{duration_seconds // 3600}h"
    text   = (
        f"{emoji} *IP BLOCKED [{source}]*\n"
        f"IP: `{ip}`\n"
        f"Reason: {reason}\n"
        f"Duration: `{dur}`\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.HIGH)


async def alert_circuit_breaker(symbol: str, reason: str, state: str = "OPEN") -> None:
    emoji = _EMOJI["critical"] if state == "OPEN" else _EMOJI["ok"]
    text  = (
        f"{emoji} *CIRCUIT BREAKER {state}*\n"
        f"Symbol: `{symbol}`\n"
        f"Reason: {reason}\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    await _broadcast(text, AlertSeverity.CRITICAL if state == "OPEN" else AlertSeverity.MEDIUM)


async def send_security_report_alert(report: Any, label: str = "scheduled") -> None:
    score  = getattr(report, "security_score", 0.0)
    trend  = getattr(report, "score_trend",    "stable")
    atk    = getattr(report, "attack_stats",   None)
    blk    = getattr(report, "blocked_ips",    None)
    period = getattr(report, "period_hours",   24)
    rep_id = getattr(report, "report_id",      "?")

    total_atk  = getattr(atk, "total_detected",  0) if atk else 0
    critical_c = getattr(atk, "critical",         0) if atk else 0
    high_c     = getattr(atk, "high",             0) if atk else 0
    active_blk = getattr(blk, "currently_active", 0) if blk else 0
    failed_l   = getattr(report, "total_failed_logins", 0)
    high_risk  = len(getattr(report, "high_risk_accounts", []))

    if   score >= 80: emoji = _EMOJI["ok"]
    elif score >= 65: emoji = "\u26a0\ufe0f"
    else:             emoji = _EMOJI["critical"]

    label_map = {"monthly": "Monthly", "manual": "Manual", "api_manual": "API", "scheduled": "Scheduled"}
    label_str = label_map.get(label, label.title())

    text = (
        f"{emoji} *Security Report [{label_str}]*\n"
        f"Period: `{period // 24}d` | Score: `{score:.1f}/100` ({trend})\n"
        f"Attacks: `{total_atk}` (C:`{critical_c}` H:`{high_c}`)\n"
        f"Blocked IPs: `{active_blk}` | High-Risk: `{high_risk}`\n"
        f"Failed Logins: `{failed_l}`\n"
        f"Report ID: `{str(rep_id)[:8]}`"
    )
    await _broadcast(text, AlertSeverity.LOW)
