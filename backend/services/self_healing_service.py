"""backend/services/self_healing_service.py v2 (Phase R)
R-23: asyncio.get_running_loop() everywhere
R-24: bounded LRU dict (cap=1000)
R-25: audit trail of healing actions
R-26: asyncio.Lock on shared state
R-27: graceful shutdown with task tracking
R-28: named score threshold constants
"""
from __future__ import annotations
import asyncio, logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# R-28: named constants
_SCORE_CRITICAL = -0.40
_SCORE_HIGH     = -0.20
_SCORE_MEDIUM   = -0.10
_BLOCK_TTL_CRITICAL = 3600
_BLOCK_TTL_HIGH     = 1800
_BLOCK_TTL_MEDIUM   =  900
_RATE_LIMIT_MAX = 1000  # R-24

@dataclass
class HealingAction:
    action_type: str
    target: str
    severity: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    auto_expire_at: Optional[datetime] = None
    def to_dict(self) -> dict:
        return {"action_type": self.action_type, "target": self.target,
                "severity": self.severity, "reason": self.reason,
                "timestamp": self.timestamp.isoformat(),
                "auto_expire_at": self.auto_expire_at.isoformat() if self.auto_expire_at else None}

class _LRUDict(OrderedDict):  # R-24
    def __init__(self, maxsize: int = _RATE_LIMIT_MAX):
        super().__init__()
        self._maxsize = maxsize
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._maxsize:
            self.popitem(last=False)

class SelfHealingService:
    def __init__(self) -> None:
        self._dynamic_rate_limits: _LRUDict = _LRUDict(_RATE_LIMIT_MAX)
        self._lock = asyncio.Lock()  # R-26
        self._action_history: List[HealingAction] = []
        self._tasks: List[asyncio.Task] = []  # R-27

    async def handle_anomaly(self, event: Dict[str, Any], anomaly_score: float) -> List[HealingAction]:
        ip = str(event.get("ip", ""))
        user_id = str(event.get("user_id", ""))
        actions: List[HealingAction] = []
        try:
            if anomaly_score <= _SCORE_CRITICAL:
                actions += await self._handle_critical(ip, user_id, anomaly_score)
            elif anomaly_score <= _SCORE_HIGH:
                actions += await self._handle_high(ip, user_id, anomaly_score)
            elif anomaly_score <= _SCORE_MEDIUM:
                actions += await self._handle_medium(ip, anomaly_score)
            else:
                return []
            async with self._lock:
                self._action_history.extend(actions)
                if len(self._action_history) > 2000:
                    self._action_history = self._action_history[-2000:]
            t = asyncio.create_task(self._log_actions(actions, anomaly_score), name="self_heal_log")
            self._tasks.append(t)
            t.add_done_callback(lambda _t: self._tasks.remove(_t) if _t in self._tasks else None)
        except Exception as exc:
            log.error("handle_anomaly error: %s", exc, exc_info=True)
        return actions

    def get_action_history(self, limit: int = 100) -> List[dict]:
        return [a.to_dict() for a in self._action_history[-limit:]]

    def get_rate_limits(self) -> Dict[str, float]:
        return dict(self._dynamic_rate_limits)

    async def shutdown(self) -> None:  # R-27
        for t in list(self._tasks):
            if not t.done():
                t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("SelfHealingService shutdown (%d actions)", len(self._action_history))

    async def _handle_critical(self, ip, user_id, score):
        actions = []
        async with self._lock:
            if ip:
                self._dynamic_rate_limits[ip] = 0.0
                actions.append(HealingAction("BLOCK_IP", ip, "critical", f"score={score}",
                               auto_expire_at=datetime.now(timezone.utc)+timedelta(seconds=_BLOCK_TTL_CRITICAL)))
            if user_id and user_id != "None":
                self._dynamic_rate_limits[f"user:{user_id}"] = 0.0
                actions.append(HealingAction("BLOCK_USER", user_id, "critical", f"score={score}",
                               auto_expire_at=datetime.now(timezone.utc)+timedelta(seconds=_BLOCK_TTL_CRITICAL)))
        return actions

    async def _handle_high(self, ip, user_id, score):
        actions = []
        async with self._lock:
            if ip:
                self._dynamic_rate_limits[ip] = 5.0
                actions.append(HealingAction("THROTTLE_IP", ip, "high", f"score={score}",
                               auto_expire_at=datetime.now(timezone.utc)+timedelta(seconds=_BLOCK_TTL_HIGH)))
        return actions

    async def _handle_medium(self, ip, score):
        actions = []
        async with self._lock:
            if ip:
                self._dynamic_rate_limits[ip] = 30.0
                actions.append(HealingAction("THROTTLE_IP_SOFT", ip, "medium", f"score={score}",
                               auto_expire_at=datetime.now(timezone.utc)+timedelta(seconds=_BLOCK_TTL_MEDIUM)))
        return actions

    async def _log_actions(self, actions, score):
        for a in actions:
            log.warning("SelfHeal[%s] target=%s severity=%s score=%.3f", a.action_type, a.target, a.severity, score)

    async def _run_sync(self, fn) -> Any:  # R-23
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn)

_service: Optional[SelfHealingService] = None
def get_self_healing_service() -> SelfHealingService:
    global _service
    if _service is None:
        _service = SelfHealingService()
    return _service
