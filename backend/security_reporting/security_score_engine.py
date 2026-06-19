"""
backend/security_reporting/security_score_engine.py
Phase-10 — Security Score Engine

Calculates system security score 0-100 from 8 weighted dimensions.

Score bands:
  80-100 : Secure      green
  65-79  : Moderate    yellow
  40-64  : High Risk   orange
   0-39  : Critical    red

Triggers:
  * score < ALERT_THRESHOLD   -> Telegram alert
  * score < BREAKER_THRESHOLD -> Security circuit breaker opened
  * Refreshes every 5 minutes
  * Stores every snapshot in security_scores DB table
  * Keeps 288-point in-memory history (24h x 5min)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_REFRESH_INTERVAL_S: int   = int(os.getenv("SECURITY_SCORE_INTERVAL_S", "300"))
_ALERT_THRESHOLD:    float = float(os.getenv("SECURITY_SCORE_ALERT",    "65"))
_BREAKER_THRESHOLD:  float = float(os.getenv("SECURITY_SCORE_BREAKER",  "40"))
_HISTORY_POINTS:     int   = 288


class ScoreLevel(str, Enum):
    SECURE    = "secure"
    MODERATE  = "moderate"
    HIGH_RISK = "high_risk"
    CRITICAL  = "critical"


@dataclass
class DimensionScore:
    name:        str
    score:       float
    weight:      float
    raw_metrics: Dict[str, Any] = field(default_factory=dict)
    notes:       List[str]      = field(default_factory=list)

    @property
    def weighted(self) -> float:
        return self.score * self.weight * 100


@dataclass
class SecuritySnapshot:
    score:       float
    level:       ScoreLevel
    trend:       str
    dimensions:  List[DimensionScore]
    top_risks:   List[str]
    timestamp:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delta_1h:    Optional[float] = None
    delta_24h:   Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score":      round(self.score, 2),
            "level":      self.level.value,
            "trend":      self.trend,
            "top_risks":  self.top_risks,
            "delta_1h":   round(self.delta_1h,  2) if self.delta_1h  is not None else None,
            "delta_24h":  round(self.delta_24h, 2) if self.delta_24h is not None else None,
            "timestamp":  self.timestamp.isoformat(),
            "dimensions": [
                {
                    "name":     d.name,
                    "score":    round(d.score * 100, 1),
                    "weight":   round(d.weight * 100, 1),
                    "weighted": round(d.weighted, 1),
                    "notes":    d.notes,
                }
                for d in self.dimensions
            ],
        }


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
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


class SecurityScoreEngine:
    def __init__(self) -> None:
        self._history:      Deque[SecuritySnapshot] = deque(maxlen=_HISTORY_POINTS)
        self._latest:       Optional[SecuritySnapshot] = None
        self._running:      bool         = False
        self._lock:         asyncio.Lock = asyncio.Lock()
        self._alert_sent:   bool         = False
        self._breaker_open: bool         = False

    async def start(self) -> None:
        self._running = True
        log.info("SecurityScoreEngine started | interval=%ds", _REFRESH_INTERVAL_S)
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Score refresh error: %s", exc, exc_info=True)
            await asyncio.sleep(_REFRESH_INTERVAL_S)

    def stop(self) -> None:
        self._running = False

    async def refresh(self) -> SecuritySnapshot:
        async with self._lock:
            snap            = await self._compute()
            self._history.append(snap)
            snap.delta_1h   = self._delta(snap.score, minutes=60)
            snap.delta_24h  = self._delta(snap.score, minutes=1440)
            snap.trend      = self._trend(snap)
            self._latest    = snap
            await self._persist(snap)
            await self._check_thresholds(snap)
            return snap

    def current(self) -> Optional[SecuritySnapshot]:
        return self._latest

    def history(self, points: int = 288) -> List[Dict[str, Any]]:
        hist = list(self._history)[-points:]
        return [
            {
                "score":     round(s.score, 2),
                "level":     s.level.value,
                "trend":     s.trend,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in hist
        ]

    def stats(self) -> Dict[str, Any]:
        snap = self._latest
        if snap is None:
            return {"score": None, "level": "unknown", "history_points": 0}
        return {
            **snap.to_dict(),
            "history_points":      len(self._history),
            "breaker_open":        self._breaker_open,
            "refresh_interval_s":  _REFRESH_INTERVAL_S,
            "alert_threshold":     _ALERT_THRESHOLD,
            "breaker_threshold":   _BREAKER_THRESHOLD,
        }

    async def _compute(self) -> SecuritySnapshot:
        dims:  List[DimensionScore] = []
        risks: List[str]            = []

        for scorer_fn in [
            self._score_auth, self._score_anomaly, self._score_api,
            self._score_trading, self._score_sessions, self._score_infra,
            self._score_data_integrity, self._score_compliance,
        ]:
            d = await scorer_fn()
            dims.append(d)
            if d.score < 0.7:
                risks.extend(d.notes[:2])

        total = max(0.0, min(100.0, sum(d.weighted for d in dims)))
        return SecuritySnapshot(
            score=total, level=self._to_level(total),
            trend="stable", dimensions=dims,
            top_risks=list(dict.fromkeys(risks))[:6],
        )

    async def _score_auth(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.institutional.data_store import data_store
            rows = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_audit_logs "
                "WHERE event_type='login_failed' AND created_at > NOW() - INTERVAL '1 hour'"
            )
            failed_1h = rows[0]["cnt"] if rows else 0
            raw["failed_logins_1h"] = failed_1h
            blk = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_blocked_ips WHERE expires_at > NOW()"
            )
            blocked = blk[0]["cnt"] if blk else 0
            raw["blocked_ips"] = blocked
            if   failed_1h > 100: score -= 0.5; notes.append(f"Extreme login failures: {failed_1h}/h")
            elif failed_1h > 30:  score -= 0.3; notes.append(f"High login failures: {failed_1h}/h")
            elif failed_1h > 10:  score -= 0.1; notes.append(f"Elevated login failures: {failed_1h}/h")
            if   blocked > 50: score -= 0.2; notes.append(f"Many blocked IPs: {blocked}")
            elif blocked > 10: score -= 0.1; notes.append(f"Blocked IPs: {blocked}")
        except Exception as exc:
            log.debug("Auth score: %s", exc)
            score = 0.8
        return DimensionScore("authentication", max(0.0, score), _WEIGHTS["authentication"], raw, notes)

    async def _score_anomaly(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.agents.security_ai_agent import get_security_agent
            agent = await get_security_agent()
            st    = agent.stats()
            total   = st.get("total_analyzed",  0)
            anomaly = st.get("total_anomalies",  0)
            rate    = anomaly / max(total, 1)
            raw["anomaly_rate"] = round(rate, 4)
            if   rate > 0.10: score -= 0.6; notes.append(f"Critical anomaly rate: {rate:.1%}")
            elif rate > 0.05: score -= 0.3; notes.append(f"High anomaly rate: {rate:.1%}")
            elif rate > 0.02: score -= 0.1; notes.append(f"Elevated anomaly rate: {rate:.1%}")
            from backend.institutional.data_store import data_store
            crit = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_ai_analysis "
                "WHERE risk_level='critical' AND created_at > NOW() - INTERVAL '1 hour'"
            )
            crit_1h = crit[0]["cnt"] if crit else 0
            raw["critical_anomalies_1h"] = crit_1h
            if   crit_1h > 5: score -= 0.3; notes.append(f"Critical anomalies 1h: {crit_1h}")
            elif crit_1h > 0: score -= 0.1; notes.append(f"Critical anomalies 1h: {crit_1h}")
        except Exception as exc:
            log.debug("Anomaly score: %s", exc)
            score = 0.85
        return DimensionScore("anomaly", max(0.0, score), _WEIGHTS["anomaly"], raw, notes)

    async def _score_api(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.institutional.data_store import data_store
            rows = await data_store.query(
                "SELECT COUNT(*) FILTER (WHERE status_code >= 500) AS errors, "
                "COUNT(*) AS total, AVG(response_time_ms) AS avg_rt "
                "FROM security_audit_logs WHERE created_at > NOW() - INTERVAL '15 minutes'"
            )
            if rows:
                errors   = rows[0]["errors"] or 0
                total_r  = rows[0]["total"]  or 1
                avg_rt   = rows[0]["avg_rt"] or 0
                err_rate = errors / total_r
                raw.update({"error_rate": round(err_rate, 4), "avg_response_ms": round(avg_rt, 1)})
                if   err_rate > 0.10: score -= 0.4; notes.append(f"High 5xx rate: {err_rate:.1%}")
                elif err_rate > 0.02: score -= 0.15; notes.append(f"Elevated 5xx: {err_rate:.1%}")
                if   avg_rt > 5000: score -= 0.3; notes.append(f"Very slow API: {avg_rt:.0f}ms")
                elif avg_rt > 2000: score -= 0.1; notes.append(f"Slow API: {avg_rt:.0f}ms")
        except Exception as exc:
            log.debug("API score: %s", exc)
            score = 0.9
        return DimensionScore("api_health", max(0.0, score), _WEIGHTS["api_health"], raw, notes)

    async def _score_trading(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.institutional.data_store import data_store
            flagged = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_audit_logs "
                "WHERE event_type='suspicious_trading' AND created_at > NOW() - INTERVAL '24 hours'"
            )
            flag_24h = flagged[0]["cnt"] if flagged else 0
            raw["flagged_accounts_24h"] = flag_24h
            if   flag_24h > 10: score -= 0.5; notes.append(f"Suspicious trading events: {flag_24h}")
            elif flag_24h > 3:  score -= 0.2; notes.append(f"Suspicious trading events: {flag_24h}")
            elif flag_24h > 0:  score -= 0.05
            try:
                from backend.circuit_breaker import circuit_breaker_manager
                open_cbs = [
                    name for name, cb in circuit_breaker_manager._breakers.items()
                    if cb.state.value == "open"
                ]
                raw["open_circuit_breakers"] = len(open_cbs)
                if open_cbs:
                    score -= 0.2 * len(open_cbs)
                    notes.append(f"Open circuit breakers: {', '.join(open_cbs[:3])}")
            except Exception:
                pass
        except Exception as exc:
            log.debug("Trading score: %s", exc)
            score = 0.9
        return DimensionScore("trading_security", max(0.0, score), _WEIGHTS["trading_security"], raw, notes)

    async def _score_sessions(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.institutional.data_store import data_store
            sess = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_audit_logs "
                "WHERE event_type='session_anomaly' AND created_at > NOW() - INTERVAL '1 hour'"
            )
            anom = sess[0]["cnt"] if sess else 0
            raw["session_anomalies_1h"] = anom
            if   anom > 20: score -= 0.4; notes.append(f"Session anomalies 1h: {anom}")
            elif anom > 5:  score -= 0.15; notes.append(f"Session anomalies 1h: {anom}")
        except Exception as exc:
            log.debug("Session score: %s", exc)
            score = 0.9
        return DimensionScore("session", max(0.0, score), _WEIGHTS["session"], raw, notes)

    async def _score_infra(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            import redis.asyncio as aioredis
            from backend.core.config import settings
            r = aioredis.from_url(str(settings.REDIS_URL), socket_timeout=2)
            await r.ping()
            await r.aclose()
            raw["redis"] = "ok"
        except Exception:
            score -= 0.3
            notes.append("Redis unavailable")
            raw["redis"] = "error"
        try:
            from backend.database.connection import get_db_client
            await get_db_client()
            raw["database"] = "ok"
        except Exception:
            score -= 0.3
            notes.append("Database unavailable")
            raw["database"] = "error"
        return DimensionScore("infrastructure", max(0.0, score), _WEIGHTS["infrastructure"], raw, notes)

    async def _score_data_integrity(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            from backend.institutional.data_store import data_store
            bad = await data_store.query(
                "SELECT COUNT(*) AS cnt FROM security_audit_logs "
                "WHERE event_type='data_integrity_error' AND created_at > NOW() - INTERVAL '24 hours'"
            )
            err_24h = bad[0]["cnt"] if bad else 0
            raw["data_errors_24h"] = err_24h
            if   err_24h > 10: score -= 0.3; notes.append(f"Data errors 24h: {err_24h}")
            elif err_24h > 0:  score -= 0.1
        except Exception as exc:
            log.debug("Data integrity: %s", exc)
            score = 0.95
        return DimensionScore("data_integrity", max(0.0, score), _WEIGHTS["data_integrity"], raw, notes)

    async def _score_compliance(self) -> DimensionScore:
        raw: Dict[str, Any] = {}
        score = 1.0
        notes: List[str] = []
        try:
            import os as _os
            rules_path = _os.path.join(_os.path.dirname(__file__), "..", "core", "security_rules.json")
            if _os.path.exists(rules_path):
                age_h = (time.time() - _os.path.getmtime(rules_path)) / 3600
                raw["rules_age_h"] = round(age_h, 1)
                if age_h > 168:
                    score -= 0.2
                    notes.append(f"Security rules stale: {age_h:.0f}h")
            else:
                score -= 0.1
                notes.append("Security rules file missing")
            try:
                from backend.agents.security_ai_agent import get_security_agent
                agent = await get_security_agent()
                st    = agent.stats()
                raw["model_trained"] = st.get("last_retrain") is not None
                if not raw["model_trained"]:
                    score -= 0.1
                    notes.append("ML model not yet trained")
            except Exception:
                pass
        except Exception as exc:
            log.debug("Compliance: %s", exc)
        return DimensionScore("compliance", max(0.0, score), _WEIGHTS["compliance"], raw, notes)

    def _to_level(self, score: float) -> ScoreLevel:
        if score >= 80: return ScoreLevel.SECURE
        if score >= 65: return ScoreLevel.MODERATE
        if score >= 40: return ScoreLevel.HIGH_RISK
        return ScoreLevel.CRITICAL

    def _delta(self, current: float, minutes: int) -> Optional[float]:
        target_points = minutes // (_REFRESH_INTERVAL_S // 60)
        hist = list(self._history)
        if len(hist) <= target_points:
            return None
        return round(current - hist[-target_points - 1].score, 2)

    def _trend(self, snap: SecuritySnapshot) -> str:
        if snap.delta_1h is None:  return "stable"
        if snap.delta_1h > 2:      return "improving"
        if snap.delta_1h < -2:     return "degrading"
        return "stable"

    async def _persist(self, snap: SecuritySnapshot) -> None:
        try:
            from backend.institutional.data_store import data_store
            import json as _json
            await data_store.upsert("security_scores", {
                "score":      round(snap.score, 2),
                "level":      snap.level.value,
                "trend":      snap.trend,
                "dimensions": _json.dumps(snap.to_dict()["dimensions"]),
                "top_risks":  _json.dumps(snap.top_risks),
                "created_at": snap.timestamp.isoformat(),
            })
        except Exception as exc:
            log.debug("Persist score: %s", exc)

    async def _check_thresholds(self, snap: SecuritySnapshot) -> None:
        if snap.score < _ALERT_THRESHOLD:
            if not self._alert_sent:
                self._alert_sent = True
                try:
                    from backend.telegram.alerts import alert_score_drop
                    prev = list(self._history)[-2].score if len(self._history) >= 2 else snap.score
                    asyncio.create_task(
                        alert_score_drop(
                            current_score=snap.score, previous_score=prev,
                            threshold=_ALERT_THRESHOLD, top_risk_factors=snap.top_risks,
                        )
                    )
                except Exception as exc:
                    log.debug("Score alert: %s", exc)
        else:
            self._alert_sent = False

        if snap.score < _BREAKER_THRESHOLD and not self._breaker_open:
            self._breaker_open = True
            log.critical("SECURITY CIRCUIT BREAKER OPENED | score=%.1f", snap.score)
            try:
                from backend.circuit_breaker import circuit_breaker_manager
                cb = circuit_breaker_manager.get("security_global")
                await cb.open(reason=f"Security score critical: {snap.score:.1f}")
                from backend.telegram.alerts import alert_circuit_breaker
                asyncio.create_task(
                    alert_circuit_breaker(
                        symbol="security_global",
                        reason=f"Score dropped to {snap.score:.1f} (threshold: {_BREAKER_THRESHOLD})",
                        state="OPEN",
                    )
                )
            except Exception as exc:
                log.error("Breaker open: %s", exc)
        elif snap.score >= _BREAKER_THRESHOLD and self._breaker_open:
            self._breaker_open = False
            log.info("Security score recovered: %.1f", snap.score)
            try:
                from backend.circuit_breaker import circuit_breaker_manager
                cb = circuit_breaker_manager.get("security_global")
                await cb.close()
                from backend.telegram.alerts import alert_circuit_breaker
                asyncio.create_task(
                    alert_circuit_breaker(
                        symbol="security_global",
                        reason=f"Score recovered to {snap.score:.1f}",
                        state="CLOSED",
                    )
                )
            except Exception as exc:
                log.debug("Breaker close: %s", exc)


security_score_engine = SecurityScoreEngine()
