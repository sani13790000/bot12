from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_SCORE_CRITICAL = -0.40
_SCORE_HIGH = -0.20
_SCORE_MEDIUM = -0.10
_BLOCK_TTL_CRITICAL = 3600
_BLOCK_TTL_HIGH = 1800
_BLOCK_TTL_MEDIUM = 900


@dataclass
class _HealingAction:
    action_type: str
    target: str
    severity: str
    reason: str
    auto_expire_at: Optional[datetime] = None


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _expire_at(seconds: int) -> datetime:
    return _now_utc() + timedelta(seconds=seconds)


async def _run_sync(fn) -> Any:
    """Run synchronous callable in executor.
    FIX: asyncio.get_event_loop() deprecated in Python 3.10+.
    Uses asyncio.get_running_loop() instead.
    """
    loop = asyncio.get_running_loop()  # FIX: was get_event_loop()
    return await loop.run_in_executor(None, fn)


class SelfHealingService:
    def __init__(self) -> None:
        self._dynamic_rate_limits: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def handle_anomaly(self, event: Dict[str, Any], anomaly_score: float) -> None:
        ip = str(event.get("ip", ""))
        user_id = str(event.get("user_id", ""))
        actions: List[_HealingAction] = []
        try:
            if anomaly_score <= _SCORE_CRITICAL:
                actions += await self._handle_critical(ip, user_id, anomaly_score)
            elif anomaly_score <= _SCORE_HIGH:
                actions += await self._handle_high(ip, user_id, anomaly_score)
            elif anomaly_score <= _SCORE_MEDIUM:
                actions += await self._handle_medium(ip, anomaly_score)
            else:
                return
            asyncio.create_task(self._log_actions(actions, anomaly_score), name="self_heal_log")
        except Exception as exc:
            log.error("SelfHealingService.handle_anomaly: %s", exc, exc_info=True)

    async def _handle_critical(self, ip: str, user_id: str, score: float) -> List[_HealingAction]:
        actions: List[_HealingAction] = []
        ttl = _BLOCK_TTL_CRITICAL
        if ip:
            await self._block_ip(ip, score, ttl, "critical")
            actions.append(_HealingAction("block_ip", ip, "critical", f"score={score:.3f}", _expire_at(ttl)))
        if user_id and user_id != "None":
            await self._revoke_sessions(user_id, "critical")
            actions.append(_HealingAction("revoke_sessions", user_id, "critical", f"score={score:.3f}"))
            await self._flag_trading_account(user_id, "critical", score)
            actions.append(_HealingAction("flag_account", user_id, "critical", f"score={score:.3f}"))
        await self._open_circuit_breaker("security_global", score)
        actions.append(_HealingAction("circuit_break", "security_global", "critical", f"score={score:.3f}"))
        return actions

    async def _handle_high(self, ip: str, user_id: str, score: float) -> List[_HealingAction]:
        actions: List[_HealingAction] = []
        ttl = _BLOCK_TTL_HIGH
        if ip:
            await self._reduce_rate_limit(ip, 0.25)
            actions.append(_HealingAction("reduce_rate_limit", ip, "high", f"factor=0.25 score={score:.3f}", _expire_at(ttl)))
        if user_id and user_id != "None":
            await self._revoke_sessions(user_id, "high")
            actions.append(_HealingAction("revoke_sessions", user_id, "high", f"score={score:.3f}"))
            await self._flag_trading_account(user_id, "high", score)
            actions.append(_HealingAction("flag_account", user_id, "high", f"score={score:.3f}"))
        return actions

    async def _handle_medium(self, ip: str, score: float) -> List[_HealingAction]:
        actions: List[_HealingAction] = []
        if ip:
            await self._reduce_rate_limit(ip, 0.50)
            actions.append(_HealingAction("reduce_rate_limit", ip, "medium", f"factor=0.50 score={score:.3f}", _expire_at(_BLOCK_TTL_MEDIUM)))
        return actions

    async def _block_ip(self, ip: str, score: float, ttl_s: int, severity: str) -> None:
        expire = _expire_at(ttl_s)
        await self._reduce_rate_limit(ip, 0.0)
        row = {"ip_address": ip, "reason": f"auto_block_{severity}", "risk_score": float(score), "expires_at": expire.isoformat(), "auto_blocked": True}

        async def _db_write() -> None:
            try:
                from backend.database.connection import get_db_client
                db = await asyncio.wait_for(get_db_client(), timeout=2.0)
                await _run_sync(lambda: db.table("security_blocked_ips").upsert(row).execute())
            except Exception as exc:
                log.debug("_block_ip DB: %s", exc)

        asyncio.create_task(_db_write(), name=f"block_ip_{ip}")
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            await security_ai_agent.add_blocked_ip(ip)
        except Exception as exc:
            log.debug("add_blocked_ip: %s", exc)
        log.warning("SelfHealing: blocked ip=%s severity=%s ttl=%ds", ip, severity, ttl_s)

    async def _revoke_sessions(self, user_id: str, severity: str) -> None:
        now = _now_utc().isoformat()

        async def _do() -> None:
            try:
                from backend.database.connection import get_db_client
                db = await asyncio.wait_for(get_db_client(), timeout=2.0)
                await _run_sync(lambda: db.table("refresh_tokens").update({"revoked": True, "revoked_at": now}).eq("user_id", user_id).eq("revoked", False).execute())
            except Exception as exc:
                log.debug("_revoke_sessions: %s", exc)

        asyncio.create_task(_do(), name=f"revoke_{user_id}")
        log.warning("SelfHealing: revoked sessions user=%s severity=%s", user_id, severity)

    async def _flag_trading_account(self, user_id: str, severity: str, score: float) -> None:
        update = {"trading_flagged": True, "flag_reason": f"security_anomaly_{severity}", "flag_score": float(score), "flagged_at": _now_utc().isoformat()}

        async def _do() -> None:
            try:
                from backend.database.connection import get_db_client
                db = await asyncio.wait_for(get_db_client(), timeout=2.0)
                await _run_sync(lambda: db.table("users").update(update).eq("id", user_id).execute())
            except Exception as exc:
                log.debug("_flag_account: %s", exc)

        asyncio.create_task(_do(), name=f"flag_{user_id}")
        log.warning("SelfHealing: flagged user=%s", user_id)

    async def _open_circuit_breaker(self, name: str, score: float) -> None:
        try:
            from backend.circuit_breaker import circuit_breaker_manager
            cb = circuit_breaker_manager.get_breaker(name)
            await cb.open(reason=f"security_anomaly score={score:.3f}")
        except Exception as exc:
            log.debug("_open_circuit_breaker: %s", exc)

    async def _reduce_rate_limit(self, ip: str, factor: float) -> None:
        async with self._lock:
            self._dynamic_rate_limits[ip] = factor
        log.info("SelfHealing: rate factor ip=%s -> %.2f", ip, factor)

    async def restore_rate_limit(self, ip: str) -> None:
        async with self._lock:
            self._dynamic_rate_limits.pop(ip, None)

    def get_rate_limit_factor(self, ip: str) -> float:
        return self._dynamic_rate_limits.get(ip, 1.0)

    async def _log_actions(self, actions: List[_HealingAction], score: float) -> None:
        if not actions:
            return
        try:
            from backend.database.connection import get_db_client
            db = await asyncio.wait_for(get_db_client(), timeout=3.0)
            now = _now_utc().isoformat()
            rows = [{"action_type": a.action_type, "target": a.target, "severity": a.severity, "anomaly_score": float(score), "reason": a.reason, "auto_expire_at": (a.auto_expire_at.isoformat() if a.auto_expire_at else None), "created_at": now} for a in actions]
            await _run_sync(lambda: db.table("self_healing_actions").insert(rows).execute())
        except Exception as exc:
            log.debug("_log_actions: %s", exc)


self_healing_service = SelfHealingService()
