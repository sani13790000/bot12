"""
backend/security_reporting/security_score_engine.py
Phase-10 + Phase-13 — FINAL

Score bands: 80-100 Secure | 65-79 Moderate | 40-64 High Risk | 0-39 Critical
Performance: .current() O(1) < 1us | DB calls < 3s timeout | metric cache TTL=60s
"""
from __future__ import annotations
import asyncio, logging, os, time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_REFRESH_INTERVAL_S = int(os.getenv("SECURITY_SCORE_INTERVAL_S", "300"))
_ALERT_THRESHOLD    = float(os.getenv("SECURITY_SCORE_ALERT",    "65"))
_BREAKER_THRESHOLD  = float(os.getenv("SECURITY_SCORE_BREAKER",  "40"))
_HISTORY_POINTS     = 288
_DB_TIMEOUT         = 3.0
_METRIC_TTL_S       = 60.0


class ScoreLevel(str, Enum):
    SECURE    = "secure"
    MODERATE  = "moderate"
    HIGH_RISK = "high_risk"
    CRITICAL  = "critical"


@dataclass
class DimensionScore:
    name: str; score: float; weight: float
    notes: List[str] = field(default_factory=list)

    @property
    def weighted(self) -> float:
        return self.score * self.weight * 100

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "score": round(self.score * 100, 1),
                "weight": round(self.weight * 100, 1),
                "weighted": round(self.weighted, 1), "notes": self.notes}


@dataclass
class SecuritySnapshot:
    score: float; level: ScoreLevel; trend: str
    dimensions: List[DimensionScore]; top_risks: List[str]
    timestamp: datetime  = field(default_factory=lambda: datetime.now(timezone.utc))
    delta_1h:  Optional[float] = None
    delta_24h: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 2), "level": self.level.value,
            "trend": self.trend, "top_risks": self.top_risks,
            "delta_1h":  round(self.delta_1h,  2) if self.delta_1h  is not None else None,
            "delta_24h": round(self.delta_24h, 2) if self.delta_24h is not None else None,
            "timestamp": self.timestamp.isoformat(),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


_WEIGHTS = {"authentication": 0.20, "anomaly": 0.20, "api_health": 0.15,
            "trading_security": 0.15, "session": 0.10, "infrastructure": 0.10,
            "data_integrity": 0.05, "compliance": 0.05}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9


class SecurityScoreEngine:
    def __init__(self) -> None:
        self._history: Deque[SecuritySnapshot] = deque(maxlen=_HISTORY_POINTS)
        self._latest:  Optional[SecuritySnapshot] = None
        self._running = False
        self._lock    = asyncio.Lock()
        self._alert_sent   = False
        self._breaker_open = False
        self._mcache: Dict[str, Tuple[Any, float]] = {}

    async def start(self) -> None:
        self._running = True
        log.info("SecurityScoreEngine started | interval=%ds", _REFRESH_INTERVAL_S)
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Score refresh: %s", exc, exc_info=True)
            await asyncio.sleep(_REFRESH_INTERVAL_S)

    def stop(self) -> None:
        self._running = False

    def current(self) -> Optional[SecuritySnapshot]:
        """O(1) read — safe from trading hot path."""
        return self._latest

    def current_score(self) -> float:
        snap = self._latest
        return snap.score if snap else 0.0

    def history(self, points: int = _HISTORY_POINTS) -> List[Dict[str, Any]]:
        return [{"score": round(s.score, 2), "level": s.level.value,
                 "trend": s.trend, "timestamp": s.timestamp.isoformat()}
                for s in list(self._history)[-points:]]

    def stats(self) -> Dict[str, Any]:
        snap = self._latest
        if snap is None:
            return {"score": None, "level": "unknown",
                    "history_points": 0, "breaker_open": self._breaker_open}
        return {**snap.to_dict(), "history_points": len(self._history),
                "breaker_open": self._breaker_open,
                "refresh_interval_s": _REFRESH_INTERVAL_S,
                "alert_threshold": _ALERT_THRESHOLD,
                "breaker_threshold": _BREAKER_THRESHOLD}

    async def refresh(self) -> SecuritySnapshot:
        async with self._lock:
            snap = await self._compute()
            snap.delta_1h  = self._delta(snap.score, 60)
            snap.delta_24h = self._delta(snap.score, 1440)
            snap.trend     = self._trend(snap)
            self._history.append(snap)
            self._latest = snap
            asyncio.create_task(self._persist(snap))
            asyncio.create_task(self._check_thresholds(snap))
            return snap

    async def _compute(self) -> SecuritySnapshot:
        dims: List[DimensionScore] = list(await asyncio.gather(
            self._score_auth(), self._score_anomaly(), self._score_api(),
            self._score_trading(), self._score_sessions(), self._score_infra(),
            self._score_data_integrity(), self._score_compliance(),
        ))
        total = max(0.0, min(100.0, sum(d.weighted for d in dims)))
        risks = [n for d in dims if d.score < 0.7 for n in d.notes[:2]]
        level = (ScoreLevel.SECURE if total >= 80 else ScoreLevel.MODERATE if total >= 65
                 else ScoreLevel.HIGH_RISK if total >= 40 else ScoreLevel.CRITICAL)
        return SecuritySnapshot(score=total, level=level, trend="stable",
                                dimensions=dims, top_risks=risks[:5])

    async def _score_auth(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["authentication"], [], 1.0
        try:
            failed  = await self._metric("failed_logins_1h", self._q_failed_logins)
            blocked = await self._metric("blocked_ips_total", self._q_blocked_ips)
            if failed > 50:   score -= 0.40; notes.append(f"High failed logins: {failed}")
            elif failed > 20: score -= 0.20; notes.append(f"Elevated logins: {failed}")
            elif failed > 5:  score -= 0.10
            if blocked > 20:  score -= 0.20; notes.append(f"{blocked} IPs blocked")
            elif blocked > 5: score -= 0.10
        except Exception as e:
            log.debug("auth scorer: %s", e); score = 0.5
        return DimensionScore("authentication", max(0.0, score), w, notes=notes)

    async def _score_anomaly(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["anomaly"], [], 1.0
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            st   = security_ai_agent.stats()
            rate = float(st.get("anomaly_rate_1h", 0.0))
            crit = int(st.get("critical_anomalies_1h", 0))
            if rate > 0.20:   score -= 0.50; notes.append(f"Critical anomaly rate: {rate:.1%}")
            elif rate > 0.10: score -= 0.30; notes.append(f"High rate: {rate:.1%}")
            elif rate > 0.05: score -= 0.15
            if crit > 0:      score -= min(0.30, crit * 0.10); notes.append(f"{crit} critical")
        except Exception as e:
            log.debug("anomaly scorer: %s", e); score = 0.5
        return DimensionScore("anomaly", max(0.0, score), w, notes=notes)

    async def _score_api(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["api_health"], [], 1.0
        try:
            err5xx = await self._metric("api_errors_5xx_1h", self._q_api_5xx)
            total  = await self._metric("api_requests_1h",   self._q_api_total)
            rate   = err5xx / max(total, 1)
            if rate > 0.10:   score -= 0.40; notes.append(f"High 5xx: {rate:.1%}")
            elif rate > 0.05: score -= 0.20
            elif rate > 0.01: score -= 0.10
        except Exception as e:
            log.debug("api scorer: %s", e); score = 0.7
        return DimensionScore("api_health", max(0.0, score), w, notes=notes)

    async def _score_trading(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["trading_security"], [], 1.0
        try:
            from backend.circuit_breaker import circuit_breaker_manager
            open_cbs = [n for n, cb in circuit_breaker_manager._breakers.items()
                        if cb.state.value == "open"]
            if open_cbs:
                score -= min(0.50, len(open_cbs) * 0.15)
                notes.append(f"Open CBs: {', '.join(open_cbs[:3])}")
        except Exception as e:
            log.debug("trading scorer: %s", e); score = 0.7
        return DimensionScore("trading_security", max(0.0, score), w, notes=notes)

    async def _score_sessions(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["session"], [], 1.0
        try:
            anom = await self._metric("session_anomalies_1h", self._q_session_anomalies)
            if anom > 10:  score -= 0.40; notes.append(f"Session anomalies: {anom}")
            elif anom > 3: score -= 0.20
        except Exception:
            score = 0.7
        return DimensionScore("session", max(0.0, score), w, notes=notes)

    async def _score_infra(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["infrastructure"], [], 1.0
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), socket_timeout=1.0)
            await asyncio.wait_for(r.ping(), timeout=1.0)
            await r.aclose()
        except Exception:
            score -= 0.30; notes.append("Redis unavailable")
        try:
            from backend.database.connection import get_db_client
            db = await asyncio.wait_for(get_db_client(), timeout=1.0)
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: db.table("security_audit_logs").select("id").limit(1).execute()),
                timeout=2.0)
        except Exception:
            score -= 0.50; notes.append("Database unreachable")
        return DimensionScore("infrastructure", max(0.0, score), w, notes=notes)

    async def _score_data_integrity(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["data_integrity"], [], 1.0
        try:
            errs = await self._metric("data_errors_24h", self._q_data_errors)
            if errs > 10:  score -= 0.50; notes.append(f"Data errors: {errs}")
            elif errs > 0: score -= 0.20
        except Exception:
            score = 0.8
        return DimensionScore("data_integrity", max(0.0, score), w, notes=notes)

    async def _score_compliance(self) -> DimensionScore:
        w, notes, score = _WEIGHTS["compliance"], [], 1.0
        rules = os.path.join(os.path.dirname(__file__), "..", "core", "security_rules.json")
        try:
            age_h = (time.time() - os.path.getmtime(rules)) / 3600
            if age_h > 168: score -= 0.30; notes.append(f"Rules stale: {age_h:.0f}h")
        except Exception:
            score -= 0.10; notes.append("Rules file not found")
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            st = security_ai_agent.stats()
            if trained := st.get("last_retrain"):
                age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(trained)).total_seconds() / 3600
                if age_h > 48: score -= 0.20; notes.append(f"Model stale: {age_h:.0f}h")
        except Exception:
            pass
        return DimensionScore("compliance", max(0.0, score), w, notes=notes)

    async def _metric(self, key: str, fetcher) -> Any:
        now = time.monotonic()
        if key in self._mcache:
            val, exp = self._mcache[key]
            if now < exp: return val
        val = await fetcher()
        self._mcache[key] = (val, now + _METRIC_TTL_S)
        return val

    async def _get_db(self):
        from backend.database.connection import get_db_client
        return await asyncio.wait_for(get_db_client(), timeout=2.0)

    async def _q(self, fn) -> Any:
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, fn), timeout=_DB_TIMEOUT)

    async def _q_failed_logins(self) -> int:
        db = await self._get_db()
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = await self._q(lambda: db.table("security_audit_logs").select("id", count="exact")
                          .eq("event_type", "login_failed").gte("created_at", since).execute())
        return r.count or 0

    async def _q_blocked_ips(self) -> int:
        db = await self._get_db()
        r = await self._q(lambda: db.table("security_blocked_ips")
                          .select("ip_address", count="exact").is_("expires_at", "null").execute())
        return r.count or 0

    async def _q_api_5xx(self) -> int:
        db = await self._get_db()
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = await self._q(lambda: db.table("security_audit_logs").select("id", count="exact")
                          .eq("event_type", "api_error_5xx").gte("created_at", since).execute())
        return r.count or 0

    async def _q_api_total(self) -> int:
        db = await self._get_db()
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = await self._q(lambda: db.table("security_audit_logs").select("id", count="exact")
                          .gte("created_at", since).execute())
        return max(r.count or 0, 1)

    async def _q_session_anomalies(self) -> int:
        db = await self._get_db()
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = await self._q(lambda: db.table("security_audit_logs").select("id", count="exact")
                          .eq("event_type", "session_anomaly").gte("created_at", since).execute())
        return r.count or 0

    async def _q_data_errors(self) -> int:
        db = await self._get_db()
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        r = await self._q(lambda: db.table("security_audit_logs").select("id", count="exact")
                          .eq("event_type", "data_integrity_error").gte("created_at", since).execute())
        return r.count or 0

    def _delta(self, current: float, minutes: int) -> Optional[float]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        for snap in reversed(self._history):
            if snap.timestamp <= cutoff:
                return round(current - snap.score, 2)
        return None

    def _trend(self, snap: SecuritySnapshot) -> str:
        d = snap.delta_1h
        if d is None: return "stable"
        return "improving" if d >= 3 else "degrading" if d <= -3 else "stable"

    async def _persist(self, snap: SecuritySnapshot) -> None:
        try:
            db = await self._get_db()
            await self._q(lambda: db.table("security_scores").insert({
                "score": round(snap.score, 2), "level": snap.level.value,
                "trend": snap.trend, "dimensions": [d.to_dict() for d in snap.dimensions],
                "top_risks": snap.top_risks, "created_at": snap.timestamp.isoformat(),
            }).execute())
        except Exception as e:
            log.debug("Score persist: %s", e)

    async def _check_thresholds(self, snap: SecuritySnapshot) -> None:
        try:
            from backend.telegram.alerts import alert_score_drop, alert_circuit_breaker
            if snap.score < _ALERT_THRESHOLD and not self._alert_sent:
                self._alert_sent = True
                asyncio.create_task(alert_score_drop(snap.score, _ALERT_THRESHOLD, snap.trend))
            elif snap.score >= _ALERT_THRESHOLD:
                self._alert_sent = False
            if snap.score < _BREAKER_THRESHOLD and not self._breaker_open:
                self._breaker_open = True
                from backend.circuit_breaker import circuit_breaker_manager
                await circuit_breaker_manager.get("security_global").open(
                    reason=f"Security score critical: {snap.score:.1f}")
                asyncio.create_task(alert_circuit_breaker("security_global", "OPEN", snap.score))
            elif snap.score >= _BREAKER_THRESHOLD and self._breaker_open:
                self._breaker_open = False
                from backend.circuit_breaker import circuit_breaker_manager
                await circuit_breaker_manager.get("security_global").close()
                asyncio.create_task(alert_circuit_breaker("security_global", "CLOSED", snap.score))
        except Exception as e:
            log.debug("Threshold check: %s", e)


security_score_engine = SecurityScoreEngine()
