"""
backend/services/self_healing_service.py
Phase-3 (FINAL) + Phase-13.

handle_anomaly() < 2ms hot path — all side-effects via asyncio.create_task.
Never blocks trading execution.
"""
from __future__ import annotations
import asyncio, logging, os, time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_SCORE_CRITICAL       = float(os.getenv("HEALING_SCORE_CRITICAL", "-0.40"))
_SCORE_HIGH           = float(os.getenv("HEALING_SCORE_HIGH",     "-0.20"))
_SCORE_MEDIUM         = float(os.getenv("HEALING_SCORE_MEDIUM",   "-0.10"))
_BLOCK_TTL_CRITICAL_H = int(os.getenv("HEALING_BLOCK_TTL_CRITICAL_H", "24"))
_BLOCK_TTL_HIGH_H     = int(os.getenv("HEALING_BLOCK_TTL_HIGH_H",      "4"))


class Severity(str, Enum):
    MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"


@dataclass
class HealingAction:
    action_type: str; target: str; severity: Severity
    anomaly_score: float; reason: str
    auto_expire_at: Optional[datetime] = None


@dataclass
class HealingResult:
    severity: Severity; actions_taken: List[str]
    elapsed_ms: float; anomaly_score: float
    ip: Optional[str]; user_id: Optional[str]


class SelfHealingService:
    def __init__(self) -> None:
        self._action_log: List[HealingAction] = []
        self._lock = asyncio.Lock()

    async def handle_anomaly(self, event: Dict[str, Any], anomaly_score: float) -> HealingResult:
        t0      = time.perf_counter()
        ip      = str(event.get("ip", ""))
        user_id = event.get("user_id")
        if anomaly_score < _SCORE_CRITICAL:
            sev, taken = Severity.CRITICAL, await self._handle_critical(ip, user_id, anomaly_score, event)
        elif anomaly_score < _SCORE_HIGH:
            sev, taken = Severity.HIGH, await self._handle_high(ip, user_id, anomaly_score, event)
        elif anomaly_score < _SCORE_MEDIUM:
            sev, taken = Severity.MEDIUM, await self._handle_medium(ip, user_id, anomaly_score, event)
        else:
            sev, taken = Severity.MEDIUM, ["no_action"]
        elapsed = (time.perf_counter() - t0) * 1000
        log.info("SelfHealing | sev=%s score=%.3f ip=%s actions=%s %.1fms",
                 sev.value, anomaly_score, ip or "-", ",".join(taken), elapsed)
        return HealingResult(sev, taken, round(elapsed, 2), anomaly_score, ip or None, user_id)

    async def _handle_critical(self, ip, user_id, score, event):
        actions = []
        expire  = datetime.now(timezone.utc) + timedelta(hours=_BLOCK_TTL_CRITICAL_H)
        if ip:
            asyncio.create_task(self._block_ip(ip, score, expire, "critical_anomaly"))
            asyncio.create_task(self._reduce_rate_limit(ip, 0.10))
            actions += ["block_ip_24h", "rate_limit_10pct"]
        if user_id:
            asyncio.create_task(self._revoke_all_sessions(user_id, "critical_anomaly"))
            asyncio.create_task(self._flag_trading_account(user_id, score, "critical"))
            actions += ["revoke_all_sessions", "flag_account_critical"]
        asyncio.create_task(self._open_trading_circuit_breaker(score))
        asyncio.create_task(self._send_alert(Severity.CRITICAL, ip, user_id, score))
        asyncio.create_task(self._log_actions(
            [HealingAction(a, ip or user_id or "?", Severity.CRITICAL, score, "critical_anomaly")
             for a in actions]))
        return actions + ["circuit_breaker_open"]

    async def _handle_high(self, ip, user_id, score, event):
        actions = []
        if ip:
            asyncio.create_task(self._reduce_rate_limit(ip, 0.25))
            actions.append("rate_limit_25pct")
        if user_id:
            asyncio.create_task(self._revoke_active_sessions(user_id, "high_anomaly"))
            asyncio.create_task(self._flag_trading_account(user_id, score, "high"))
            actions += ["revoke_active_sessions", "flag_account_high"]
        asyncio.create_task(self._send_alert(Severity.HIGH, ip, user_id, score))
        asyncio.create_task(self._log_actions(
            [HealingAction(a, ip or user_id or "?", Severity.HIGH, score, "high_anomaly")
             for a in actions]))
        return actions

    async def _handle_medium(self, ip, user_id, score, event):
        actions = []
        if ip:
            asyncio.create_task(self._reduce_rate_limit(ip, 0.50))
            actions.append("rate_limit_50pct")
        asyncio.create_task(self._log_actions(
            [HealingAction(a, ip or "?", Severity.MEDIUM, score, "medium_anomaly") for a in actions]))
        return actions

    async def _block_ip(self, ip, score, expire, reason):
        try:
            from backend.middleware.rate_limit import _dynamic_ip_limits
            _dynamic_ip_limits[ip] = (0, 1)
        except Exception as e: log.debug("rate_limit block: %s", e)
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            await security_ai_agent.add_blocked_ip(ip, reason=reason, expires_at=expire)
        except Exception as e: log.debug("agent block: %s", e)
        try:
            from backend.database.connection import get_db_client
            db = await asyncio.wait_for(get_db_client(), timeout=2.0)
            await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda:
                db.table("security_blocked_ips").upsert({
                    "ip_address": ip, "reason": reason, "risk_score": score,
                    "expires_at": expire.isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()), timeout=3.0)
        except Exception as e: log.debug("DB block: %s", e)

    async def _reduce_rate_limit(self, ip, factor):
        try:
            from backend.middleware.rate_limit import _dynamic_ip_limits
            _dynamic_ip_limits[ip] = (max(1, int(120 * factor)), 60)
        except Exception as e: log.debug("reduce_rl: %s", e)

    async def _revoke_all_sessions(self, user_id, reason):
        try:
            from backend.services.session_service import session_service
            await session_service.revoke_all_user_sessions(user_id=user_id, reason=reason)
        except Exception as e: log.debug("revoke_all: %s", e)

    async def _revoke_active_sessions(self, user_id, reason):
        try:
            from backend.services.session_service import session_service
            await session_service.revoke_active_sessions(user_id=user_id, reason=reason)
        except Exception as e: log.debug("revoke_active: %s", e)

    async def _flag_trading_account(self, user_id, score, severity):
        try:
            from backend.database.connection import get_db_client
            db = await asyncio.wait_for(get_db_client(), timeout=2.0)
            await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda:
                db.table("users").update({
                    "trading_flagged": True,
                    "flag_reason": f"security_anomaly_{severity}",
                    "flag_score": score,
                    "flagged_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", user_id).execute()), timeout=3.0)
        except Exception as e: log.debug("flag_account: %s", e)

    async def _open_trading_circuit_breaker(self, score):
        try:
            from backend.circuit_breaker import circuit_breaker_manager
            await circuit_breaker_manager.get("trading_anomaly").open(reason=f"Anomaly score={score:.3f}")
            asyncio.create_task(self._auto_recover_cb("trading_anomaly", 300))
        except Exception as e: log.debug("CB open: %s", e)

    async def _auto_recover_cb(self, name, delay_s):
        await asyncio.sleep(delay_s)
        try:
            from backend.circuit_breaker import circuit_breaker_manager
            cb = circuit_breaker_manager.get(name)
            if cb.state.value == "open": await cb.close()
        except Exception as e: log.debug("auto_recover: %s", e)

    async def _send_alert(self, severity, ip, user_id, score):
        try:
            from backend.telegram.alerts import alert_critical_anomaly
            await alert_critical_anomaly(
                event_type=f"self_healing_{severity.value}",
                ip_address=ip, user_id=user_id, risk_score=abs(score),
                description=f"SelfHealing | sev={severity.value} score={score:.3f}",
            )
        except Exception as e: log.debug("telegram: %s", e)

    async def _log_actions(self, actions):
        async with self._lock:
            self._action_log.extend(actions)
            if len(self._action_log) > 1000:
                self._action_log = self._action_log[-1000:]
        now = datetime.now(timezone.utc).isoformat()
        try:
            from backend.database.connection import get_db_client
            db   = await asyncio.wait_for(get_db_client(), timeout=2.0)
            rows = [{"action_type": a.action_type, "target": a.target,
                     "severity": a.severity.value, "anomaly_score": a.anomaly_score,
                     "reason": a.reason, "created_at": now} for a in actions]
            if rows:
                await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda:
                    db.table("self_healing_actions").insert(rows).execute()), timeout=3.0)
        except Exception as e: log.debug("log_actions: %s", e)

    def stats(self) -> Dict[str, Any]:
        return {"total_actions": len(self._action_log),
                "recent": [{"action": a.action_type, "severity": a.severity.value,
                            "target": a.target[:32], "score": round(a.anomaly_score, 3)}
                           for a in self._action_log[-20:]]}


self_healing_service = SelfHealingService()
