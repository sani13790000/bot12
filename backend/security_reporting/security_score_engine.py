from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

log = logging.getLogger(__name__)

_REFRESH_INTERVAL_S = int(os.getenv("SECURITY_SCORE_INTERVAL_S", "300"))
_ALERT_THRESHOLD    = float(os.getenv("SECURITY_SCORE_ALERT",    "65"))
_BREAKER_THRESHOLD  = float(os.getenv("SECURITY_SCORE_BREAKER",  "40"))
_HISTORY_POINTS     = 288
_DB_TIMEOUT         = 3.0
_METRIC_CACHE_TTL   = 60.0

_WEIGHTS: Dict[str, float] = {
    "authentication":   0.20,
    "anomaly":          0.20,
    "api_health":       0.15,
    "trading_security": 0.15,
    "session":          0.10,
    "infrastructure":   0.10,
    "data_integrity":   0.05,
    "compliance":       0.05,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9


class ScoreLevel(str, Enum):
    SECURE    = "secure"
    MODERATE  = "moderate"
    HIGH_RISK = "high_risk"
    CRITICAL  = "critical"


@dataclass
class DimensionScore:
    name:   str
    score:  float
    weight: float
    notes:  List[str] = field(default_factory=list)

    @property
    def weighted(self) -> float:
        return self.score * self.weight * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":     self.name,
            "score":    round(self.score * 100, 1),
            "weight":   round(self.weight * 100, 1),
            "weighted": round(self.weighted, 1),
            "notes":    self.notes,
        }


@dataclass
class SecuritySnapshot:
    score:      float
    level:      ScoreLevel
    trend:      str
    dimensions: List[DimensionScore]
    top_risks:  List[str]
    timestamp:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delta_1h:  Optional[float] = None
    delta_24h: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score":      round(self.score, 2),
            "level":      self.level.value,
            "trend":      self.trend,
            "top_risks":  self.top_risks,
            "delta_1h":   round(self.delta_1h,  2) if self.delta_1h  is not None else None,
            "delta_24h":  round(self.delta_24h, 2) if self.delta_24h is not None else None,
            "timestamp":  self.timestamp.isoformat(),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


def _level(s: float) -> ScoreLevel:
    if s >= 80: return ScoreLevel.SECURE
    if s >= 65: return ScoreLevel.MODERATE
    if s >= 40: return ScoreLevel.HIGH_RISK
    return ScoreLevel.CRITICAL


def _trend(now: float, prev: Optional[float]) -> str:
    if prev is None: return "stable"
    d = now - prev
    if d >  3: return "improving"
    if d < -3: return "degrading"
    return "stable"


@dataclass
class _CachedMetric:
    value:   float
    fetched: float = field(default_factory=time.monotonic)
    def stale(self) -> bool:
        return time.monotonic() - self.fetched > _METRIC_CACHE_TTL


class _MetricCache:
    def __init__(self) -> None:
        self._store: Dict[str, _CachedMetric] = {}
        self._lock = asyncio.Lock()

    async def get_or_fetch(self, key: str, fetcher) -> float:
        async with self._lock:
            c = self._store.get(key)
            if c and not c.stale():
                return c.value
        v = await fetcher()
        async with self._lock:
            self._store[key] = _CachedMetric(value=v)
        return v

    def invalidate(self) -> None:
        self._store.clear()


class SecurityScoreEngine:
    def __init__(self) -> None:
        self._history:  Deque[SecuritySnapshot] = deque(maxlen=_HISTORY_POINTS)
        self._latest:   Optional[SecuritySnapshot] = None
        self._running   = False
        self._lock      = asyncio.Lock()
        self._cache     = _MetricCache()
        self._alert_sent    = False
        self._breaker_open  = False

    def current_sync(self) -> Optional[SecuritySnapshot]:
        return self._latest

    async def current(self) -> Optional[SecuritySnapshot]:
        return self._latest

    def history(self) -> List[SecuritySnapshot]:
        return list(self._history)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        log.info("SecurityScoreEngine started (interval=%ds)", _REFRESH_INTERVAL_S)
        try:
            await self._refresh()
        except Exception as exc:
            log.error("Initial score failed: %s", exc)
        while self._running:
            await asyncio.sleep(_REFRESH_INTERVAL_S)
            try:
                await self._refresh()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Score refresh error: %s", exc)

    def stop(self) -> None:
        self._running = False

    async def _refresh(self) -> None:
        t0   = time.monotonic()
        dims = await asyncio.gather(
            self._auth_dim(), self._anomaly_dim(), self._api_dim(),
            self._trading_dim(), self._session_dim(), self._infra_dim(),
            self._integrity_dim(), self._compliance_dim(),
            return_exceptions=True,
        )
        results: List[DimensionScore] = []
        for i, (name, weight) in enumerate(_WEIGHTS.items()):
            d = dims[i]
            if isinstance(d, Exception):
                results.append(DimensionScore(name, 0.5, weight, ["error"]))
            else:
                results.append(d)
        composite = max(0.0, min(100.0, sum(d.weighted for d in results)))
        prev_1h = self._history[-12].score if len(self._history) >= 12 else None
        prev_24h = self._history[0].score if len(self._history) >= _HISTORY_POINTS else None
        snap = SecuritySnapshot(
            score=composite, level=_level(composite),
            trend=_trend(composite, prev_1h), dimensions=results,
            top_risks=self._top_risks(results),
            delta_1h=round(composite - prev_1h, 2) if prev_1h is not None else None,
            delta_24h=round(composite - prev_24h, 2) if prev_24h is not None else None,
        )
        async with self._lock:
            self._latest = snap
            self._history.append(snap)
        asyncio.create_task(self._persist(snap))
        asyncio.create_task(self._check_thresholds(snap))
        log.info("SecurityScore: %.1f [%s] in %.0f ms",
                 composite, snap.level.value, (time.monotonic()-t0)*1000)

    async def _auth_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h1 = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
            h24 = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            rf = await asyncio.wait_for(db.table("security_audit_logs").select("id",count="exact").eq("event_type","login_failed").gte("created_at",h1).execute(), timeout=_DB_TIMEOUT)
            rb = await asyncio.wait_for(db.table("security_blocked_ips").select("id",count="exact").gte("created_at",h24).execute(), timeout=_DB_TIMEOUT)
            f = rf.count or 0; b = rb.count or 0
            if f > 100: score -= 0.5; notes.append(f"{f} failed logins/h")
            elif f > 20: score -= 0.2; notes.append(f"{f} failed logins/h")
            elif f > 5: score -= 0.1
            if b > 50: score -= 0.3; notes.append(f"{b} IPs blocked/24h")
            elif b > 10: score -= 0.1
        except Exception as e: notes.append(str(e)); score = 0.7
        return DimensionScore("authentication", max(0.0, score), _WEIGHTS["authentication"], notes)

    async def _anomaly_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h1 = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
            h24 = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            ra = await asyncio.wait_for(db.table("security_ai_analysis").select("id",count="exact").gte("created_at",h1).execute(), timeout=_DB_TIMEOUT)
            rc = await asyncio.wait_for(db.table("security_ai_analysis").select("id",count="exact").eq("risk_level","critical").gte("created_at",h24).execute(), timeout=_DB_TIMEOUT)
            a = ra.count or 0; c = rc.count or 0
            if c > 10: score -= 0.5; notes.append(f"{c} critical/24h")
            elif c > 3: score -= 0.3; notes.append(f"{c} critical/24h")
            elif c > 0: score -= 0.1
            if a > 50: score -= 0.3; notes.append(f"{a} anomalies/h")
            elif a > 10: score -= 0.1
        except Exception as e: notes.append(str(e)); score = 0.7
        return DimensionScore("anomaly", max(0.0, score), _WEIGHTS["anomaly"], notes)

    async def _api_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h1 = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
            r = await asyncio.wait_for(db.table("security_audit_logs").select("id",count="exact").gte("status_code",500).gte("created_at",h1).execute(), timeout=_DB_TIMEOUT)
            e = r.count or 0
            if e > 50: score -= 0.4; notes.append(f"{e} 5xx/h")
            elif e > 10: score -= 0.2
            elif e > 3: score -= 0.1
        except Exception as ex: notes.append(str(ex)); score = 0.8
        return DimensionScore("api_health", max(0.0, score), _WEIGHTS["api_health"], notes)

    async def _trading_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h24 = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            r = await asyncio.wait_for(db.table("security_ai_analysis").select("id",count="exact").eq("event_type","trade_activity").gte("created_at",h24).execute(), timeout=_DB_TIMEOUT)
            t = r.count or 0
            if t > 20: score -= 0.4; notes.append(f"{t} suspicious trades/24h")
            elif t > 5: score -= 0.2
            try:
                from backend.circuit_breaker import circuit_breaker_manager
                open_cbs = sum(1 for cb in circuit_breaker_manager._breakers.values() if cb.state.value=="open")
                if open_cbs > 0: score -= 0.2*open_cbs; notes.append(f"{open_cbs} CBs OPEN")
            except Exception: pass
        except Exception as ex: notes.append(str(ex)); score = 0.8
        return DimensionScore("trading_security", max(0.0, score), _WEIGHTS["trading_security"], notes)

    async def _session_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h24 = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            r = await asyncio.wait_for(db.table("security_audit_logs").select("id",count="exact").eq("event_type","session_anomaly").gte("created_at",h24).execute(), timeout=_DB_TIMEOUT)
            s = r.count or 0
            if s > 10: score -= 0.3; notes.append(f"{s} session anomalies/24h")
            elif s > 3: score -= 0.15
        except Exception as ex: notes.append(str(ex)); score = 0.8
        return DimensionScore("session", max(0.0, score), _WEIGHTS["session"], notes)

    async def _infra_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            import redis.asyncio as aioredis
            rc = aioredis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"),socket_timeout=1.0)
            await asyncio.wait_for(rc.ping(), timeout=1.0); await rc.aclose()
        except Exception: score -= 0.2; notes.append("Redis unreachable")
        try:
            db = self._db()
            await asyncio.wait_for(db.table("security_audit_logs").select("id").limit(1).execute(), timeout=2.0)
        except Exception: score -= 0.4; notes.append("DB unreachable")
        return DimensionScore("infrastructure", max(0.0, score), _WEIGHTS["infrastructure"], notes)

    async def _integrity_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            db = self._db(); h24 = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            r = await asyncio.wait_for(db.table("security_audit_logs").select("id",count="exact").eq("event_type","data_integrity_error").gte("created_at",h24).execute(), timeout=_DB_TIMEOUT)
            e = r.count or 0
            if e > 5: score -= 0.4; notes.append(f"{e} integrity errors/24h")
            elif e > 0: score -= 0.1
        except Exception as ex: notes.append(str(ex)); score = 0.8
        return DimensionScore("data_integrity", max(0.0, score), _WEIGHTS["data_integrity"], notes)

    async def _compliance_dim(self) -> DimensionScore:
        notes: List[str] = []; score = 1.0
        try:
            p = os.path.join(os.path.dirname(__file__), "..", "core", "security_rules.json")
            age = (time.time() - os.path.getmtime(p)) / 86400
            if age > 30: score -= 0.2; notes.append(f"rules {age:.0f}d old")
        except FileNotFoundError: score -= 0.3; notes.append("security_rules.json missing")
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            if not security_ai_agent.get_stats().get("model_trained", False):
                score -= 0.2; notes.append("Model not trained")
        except Exception: pass
        return DimensionScore("compliance", max(0.0, score), _WEIGHTS["compliance"], notes)

    @staticmethod
    def _top_risks(dims: List[DimensionScore]) -> List[str]:
        low = sorted([(d.name, d.score) for d in dims if d.score < 0.7], key=lambda x: x[1])
        return [f"{n}: {s*100:.0f}%" for n, s in low[:5]]

    @staticmethod
    def _db():
        from backend.database.connection import get_db_client
        return get_db_client()

    async def _persist(self, snap: SecuritySnapshot) -> None:
        try:
            db = self._db()
            await asyncio.wait_for(db.table("security_scores").insert({
                "score": round(snap.score,2), "level": snap.level.value,
                "trend": snap.trend, "dimensions": {d.name: round(d.score*100,1) for d in snap.dimensions},
                "top_risks": snap.top_risks, "created_at": snap.timestamp.isoformat(),
            }).execute(), timeout=_DB_TIMEOUT)
        except Exception as e: log.debug("persist score: %s", e)

    async def _check_thresholds(self, snap: SecuritySnapshot) -> None:
        try:
            from backend.telegram.alerts import alert_score_drop, alert_circuit_breaker
            from backend.circuit_breaker import circuit_breaker_manager
            if snap.score < _ALERT_THRESHOLD and not self._alert_sent:
                self._alert_sent = True
                asyncio.create_task(alert_score_drop(snap.score, _ALERT_THRESHOLD, snap.trend))
            elif snap.score >= _ALERT_THRESHOLD:
                self._alert_sent = False
            if snap.score < _BREAKER_THRESHOLD and not self._breaker_open:
                self._breaker_open = True
                cb = circuit_breaker_manager.get("security_global")
                await cb.open(reason=f"score {snap.score:.1f} < {_BREAKER_THRESHOLD}")
                asyncio.create_task(alert_circuit_breaker("security_global", "OPEN", f"score {snap.score:.1f}"))
            elif snap.score >= _BREAKER_THRESHOLD and self._breaker_open:
                self._breaker_open = False
                try:
                    await circuit_breaker_manager.get("security_global").close()
                    asyncio.create_task(alert_circuit_breaker("security_global", "CLOSED", "recovered"))
                except Exception: pass
        except ImportError: pass
        except Exception as e: log.warning("threshold check: %s", e)


security_score_engine = SecurityScoreEngine()
