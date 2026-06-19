from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

_RETRAIN_INTERVAL_S: int   = 3_600
_MIN_SAMPLES:        int   = 50
_SCORE_THRESHOLD:    float = -0.15
_BLOCK_THRESHOLD:    float = -0.40
_BLOCK_DURATION_S:   int   = 3_600
_FEATURE_DIM:        int   = 12
_MAX_BUFFER:         int   = 10_000
_DB_TIMEOUT:         float = 3.0
_INFER_TIMEOUT_MS:   float = 10.0


class RiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class EventType(str, Enum):
    API_REQUEST     = "api_request"
    LOGIN_ATTEMPT   = "login_attempt"
    TRADE_ACTIVITY  = "trade_activity"
    SESSION_ANOMALY = "session_anomaly"
    WEBSOCKET       = "websocket"


@dataclass
class SecurityEvent:
    event_type:       EventType
    ip_address:       str
    user_id:          Optional[str] = None
    endpoint:         str           = ""
    method:           str           = "GET"
    status_code:      int           = 200
    response_time_ms: float         = 0.0
    payload_size:     int           = 0
    timestamp:        datetime      = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: Dict[str, Any]           = field(default_factory=dict)


@dataclass
class AnomalyResult:
    is_anomaly:        bool
    score:             float
    risk_level:        RiskLevel
    confidence:        float
    features:          List[float]
    explanation:       List[str]
    self_heal_action:  Optional[str] = None
    inference_time_ms: float         = 0.0


class _FeatureExtractor:
    _WINDOW_S = 60

    def __init__(self) -> None:
        self._req:  Dict[str, deque] = defaultdict(deque)
        self._fail: Dict[str, deque] = defaultdict(deque)
        self._eps:  Dict[str, set]   = defaultdict(set)
        self._ev_count = 0
        self._MAX_IPS  = 50_000

    def _prune(self, dq: deque, cutoff: float) -> None:
        while dq and dq[0] < cutoff:
            dq.popleft()

    def extract(self, ev: SecurityEvent) -> List[float]:
        now = time.monotonic(); cut = now - self._WINDOW_S; ip = ev.ip_address
        self._req[ip].append(now); self._prune(self._req[ip], cut)
        if ev.status_code >= 400:
            self._fail[ip].append(now); self._prune(self._fail[ip], cut)
        self._eps[ip].add(ev.endpoint)
        req = len(self._req[ip]); fail = len(self._fail[ip])
        self._ev_count += 1
        if self._ev_count % 1_000 == 0:
            self._evict()
        hr = datetime.now(timezone.utc).hour
        return [
            min(req  / 100.0, 1.0),
            min(fail / 50.0,  1.0),
            fail / max(req, 1),
            min(len(self._eps[ip]) / 20.0, 1.0),
            1.0 if "auth"  in ev.endpoint else 0.0,
            1.0 if "trade" in ev.endpoint or "order" in ev.endpoint else 0.0,
            1.0 if "ws"    in ev.endpoint else 0.0,
            min(ev.response_time_ms / 10_000.0, 1.0),
            min(ev.payload_size     / 1_048_576.0, 1.0),
            (ev.status_code // 100) / 5.0,
            hr / 24.0,
            1.0 if hr < 6 else 0.0,
        ]

    def _evict(self) -> None:
        if len(self._req) <= self._MAX_IPS:
            return
        stale = [ip for ip, dq in self._req.items() if not dq]
        for ip in stale[: len(stale) // 2 + 1]:
            self._req.pop(ip, None); self._fail.pop(ip, None); self._eps.pop(ip, None)


_HEURISTIC_RULES = [
    (lambda f: f[0] > 0.8,             -0.6, "Very high request rate"),
    (lambda f: f[2] > 0.5,             -0.5, "High failure ratio"),
    (lambda f: f[3] > 0.7,             -0.4, "Abnormal endpoint diversity"),
    (lambda f: f[4] > 0 and f[2] > 0.3,-0.5, "Auth + high failure"),
    (lambda f: f[7] > 0.9,             -0.3, "Very high latency"),
]


def _heuristic_score(features: List[float]) -> Tuple[float, List[str]]:
    score = 0.0; expl: List[str] = []
    for rule, pen, label in _HEURISTIC_RULES:
        try:
            if rule(features): score += pen; expl.append(label)
        except Exception: pass
    return score, expl


class _IFModel:
    def __init__(self) -> None:
        self._model: Any  = None
        self._trained     = False
        self._n_samples   = 0
        self._lock        = asyncio.Lock()

    def _score_impl(self, x: List[float]) -> float:
        if not self._trained or self._model is None: return 0.0
        import numpy as _np
        arr = _np.array(x, dtype=_np.float32).reshape(1, -1)
        return float(self._model.score_samples(arr)[0])

    async def score(self, x: List[float]) -> float:
        if not self._trained: return 0.0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._score_impl, x)

    async def train(self, X: np.ndarray) -> None:
        from sklearn.ensemble import IsolationForest
        loop = asyncio.get_running_loop()
        def _fit():
            m = IsolationForest(n_estimators=200, contamination=0.05,
                                max_features=_FEATURE_DIM, random_state=42, n_jobs=-1)
            m.fit(X); return m
        model = await loop.run_in_executor(None, _fit)
        async with self._lock:
            self._model = model; self._trained = True; self._n_samples = len(X)
        log.info("IsolationForest retrained on %d samples.", len(X))

    @property
    def trained(self) -> bool: return self._trained
    @property
    def n_samples(self) -> int: return self._n_samples


class SecurityAIAgent:
    def __init__(self) -> None:
        self._extractor  = _FeatureExtractor()
        self._model      = _IFModel()
        self._buffer: deque = deque(maxlen=_MAX_BUFFER)
        self._running    = False
        self._last_retrain: Optional[datetime] = None

    async def analyze_event(self, event: SecurityEvent) -> AnomalyResult:
        t0       = time.monotonic()
        features = self._extractor.extract(event)
        self._buffer.append(features)
        result   = await self.detect_anomaly(features)
        result.inference_time_ms = (time.monotonic() - t0) * 1_000
        if result.inference_time_ms > _INFER_TIMEOUT_MS:
            log.warning("Inference %.1f ms > %.0f ms", result.inference_time_ms, _INFER_TIMEOUT_MS)
        asyncio.create_task(self._persist(event, result))
        if result.score < _BLOCK_THRESHOLD:
            asyncio.create_task(self._self_heal(event, result))
        return result

    async def detect_anomaly(self, features: List[float]) -> AnomalyResult:
        if self._model.trained:
            score       = await self._model.score(features)
            explanation = self._explain(features, score)
        else:
            score, explanation = _heuristic_score(features)
        is_anomaly = score < _SCORE_THRESHOLD
        risk       = self._risk(score)
        confidence = min(abs(score) / 0.5, 1.0) if is_anomaly else 0.0
        return AnomalyResult(is_anomaly=is_anomaly, score=round(score,4),
                             risk_level=risk, confidence=round(confidence,3),
                             features=features, explanation=explanation)

    async def retrain_model(self) -> None:
        if len(self._buffer) < _MIN_SAMPLES:
            log.info("Skipping retrain: %d/%d samples", len(self._buffer), _MIN_SAMPLES); return
        X = np.array(list(self._buffer), dtype=np.float32)
        X = await self._enrich(X)
        await self._model.train(X)
        self._last_retrain = datetime.now(timezone.utc)
        asyncio.create_task(self._save_meta())

    def get_stats(self) -> Dict[str, Any]:
        return {"model_trained": self._model.trained,
                "training_samples": self._model.n_samples,
                "buffer_size": len(self._buffer),
                "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
                "retrain_interval": _RETRAIN_INTERVAL_S,
                "inference_threshold": _SCORE_THRESHOLD,
                "block_threshold": _BLOCK_THRESHOLD}

    async def start(self) -> None:
        if self._running: return
        self._running = True
        log.info("SecurityAIAgent started (retrain every %ds)", _RETRAIN_INTERVAL_S)
        await asyncio.sleep(30)
        while self._running:
            try:
                await self.retrain_model()
            except asyncio.CancelledError: break
            except Exception as e: log.error("retrain: %s", e)
            await asyncio.sleep(_RETRAIN_INTERVAL_S)

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _risk(score: float) -> RiskLevel:
        if score < -0.40: return RiskLevel.CRITICAL
        if score < -0.25: return RiskLevel.HIGH
        if score < -0.15: return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _explain(features: List[float], score: float) -> List[str]:
        expl: List[str] = []
        checks = [(0, 0.7, "High request rate"), (1, 0.6, "High fail rate"),
                  (2, 0.4, "High fail ratio"), (3, 0.7, "Endpoint diversity"), (7, 0.8, "High latency")]
        for idx, thresh, label in checks:
            if features[idx] > thresh: expl.append(label)
        if score < -0.4: expl.insert(0, f"IF score={score:.3f}")
        return expl or ["Normal"]

    async def _enrich(self, X: np.ndarray) -> np.ndarray:
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            since = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            r = await asyncio.wait_for(db.table("security_ai_analysis").select("features").gte("created_at",since).limit(5_000).execute(), timeout=_DB_TIMEOUT)
            extras = [row["features"] for row in (r.data or []) if isinstance(row.get("features"),list) and len(row["features"])==_FEATURE_DIM]
            if extras: X = np.vstack([X, np.array(extras, dtype=np.float32)])
        except Exception as e: log.debug("enrich: %s", e)
        return X

    async def _persist(self, ev: SecurityEvent, r: AnomalyResult) -> None:
        if not r.is_anomaly and r.risk_level == RiskLevel.LOW: return
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            await asyncio.wait_for(db.table("security_ai_analysis").insert({
                "id": str(uuid.uuid4()), "event_type": ev.event_type.value,
                "risk_level": r.risk_level.value, "risk_score": r.score,
                "is_anomaly": r.is_anomaly, "user_id": ev.user_id,
                "ip_address": ev.ip_address, "endpoint": ev.endpoint,
                "features": r.features, "explanation": r.explanation,
                "metadata": ev.extra, "created_at": ev.timestamp.isoformat(),
            }).execute(), timeout=_DB_TIMEOUT)
        except Exception as e: log.debug("persist: %s", e)

    async def _self_heal(self, ev: SecurityEvent, r: AnomalyResult) -> None:
        try:
            from backend.services.self_healing_service import self_healing_service
            await self_healing_service.handle_anomaly(
                {"ip_address": ev.ip_address, "user_id": ev.user_id,
                 "event_type": ev.event_type.value, "endpoint": ev.endpoint}, r.score)
        except ImportError: pass
        except Exception as e: log.warning("self_heal: %s", e)

    async def _save_meta(self) -> None:
        try:
            from backend.database.connection import get_db_client
            db = get_db_client()
            await asyncio.wait_for(db.table("security_model_metadata").insert({
                "model_type": "IsolationForest", "training_samples": self._model.n_samples,
                "contamination": 0.05, "feature_dim": _FEATURE_DIM,
                "trained_at": datetime.now(timezone.utc).isoformat(),
            }).execute(), timeout=_DB_TIMEOUT)
        except Exception as e: log.debug("save meta: %s", e)


security_ai_agent = SecurityAIAgent()
