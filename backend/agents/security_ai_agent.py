"""backend/agents/security_ai_agent.py — Phase O fix

BUG-O1: Model had no disk persistence — lost on Docker restart
  _IFModel now has save_model(path) / load_model(path) via joblib
  start() loads existing model at startup, saves after each retrain
BUG-O2: MODEL_DIR was /tmp hardcode → now from settings.MODEL_DIR
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

_FEATURE_DIM        = 12
_MAX_BUFFER         = 10_000
_MIN_SAMPLES        = 100
_RETRAIN_INTERVAL_S = 3_600
_SCORE_THRESHOLD    = -0.15
_BLOCK_THRESHOLD    = -0.40
_DB_TIMEOUT         = 5.0
_INFER_TIMEOUT_MS   = 50.0
_MODEL_FILENAME     = "security_isolation_forest.pkl"


class EventType(str, Enum):
    LOGIN_ATTEMPT = "login_attempt"
    TRADE_EXECUTE = "trade_execute"
    API_REQUEST   = "api_request"
    DATA_ACCESS   = "data_access"
    CONFIG_CHANGE = "config_change"


class RiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    event_type:       EventType
    ip_address:       str
    user_id:          Optional[str]  = None
    endpoint:         str            = ""
    status_code:      int            = 200
    response_time_ms: float          = 0.0
    payload_size:     int            = 0
    extra:            Dict[str, Any] = field(default_factory=dict)
    timestamp:        datetime       = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AnomalyResult:
    is_anomaly:        bool
    score:             float
    risk_level:        RiskLevel
    confidence:        float
    features:          List[float]
    explanation:       List[str]
    inference_time_ms: float = 0.0


class _FeatureExtractor:
    _WINDOW_S = 300
    _MAX_IPS  = 5_000

    def __init__(self) -> None:
        self._req:      Dict[str, deque] = defaultdict(deque)
        self._fail:     Dict[str, deque] = defaultdict(deque)
        self._eps:      Dict[str, set]   = defaultdict(set)
        self._ev_count: int              = 0

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
            min(req   / 100.0, 1.0),
            min(fail  / 50.0,  1.0),
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


def _safe_rule(fn, features: List[float]) -> bool:
    try:
        if len(features) < _FEATURE_DIM:
            return False
        return bool(fn(features))
    except Exception:
        return False


_HEURISTIC_RULES: List[Tuple[Any, float, str]] = [
    (lambda f: f[0] > 0.8,              -0.6, "Very high request rate"),
    (lambda f: f[2] > 0.5,              -0.5, "High failure ratio"),
    (lambda f: f[3] > 0.7,              -0.4, "Abnormal endpoint diversity"),
    (lambda f: f[4] > 0 and f[2] > 0.3, -0.5, "Auth + high failure"),
    (lambda f: f[7] > 0.9,              -0.3, "Very high latency"),
]


def _heuristic_score(features: List[float]) -> Tuple[float, List[str]]:
    score = 0.0; expl: List[str] = []
    for rule, pen, label in _HEURISTIC_RULES:
        if _safe_rule(rule, features):
            score += pen; expl.append(label)
    return score, expl


class _IFModel:
    def __init__(self) -> None:
        self._model:    Any  = None
        self._trained        = False
        self._n_samples: int = 0
        self._lock           = asyncio.Lock()

    def _score_impl(self, x: List[float]) -> float:
        if not self._trained or self._model is None:
            return 0.0
        arr = np.array(x, dtype=np.float32).reshape(1, -1)
        return float(self._model.score_samples(arr)[0])

    async def score(self, x: List[float]) -> float:
        if not self._trained:
            return 0.0
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

    # ------------------------------------------------------------------ #
    # BUG-O1 fix: disk persistence via joblib
    # ------------------------------------------------------------------ #
    def save_model(self, path: str) -> None:
        """Persist IsolationForest to disk so it survives Docker restarts."""
        if not self._trained or self._model is None:
            return
        try:
            import joblib
            os.makedirs(os.path.dirname(path), exist_ok=True)
            joblib.dump(self._model, path)
            log.info("SecurityAIAgent model saved → %s (%d samples)", path, self._n_samples)
        except Exception as e:
            log.warning("SecurityAIAgent save_model failed: %s", e)

    def load_model(self, path: str) -> bool:
        """Load persisted model from disk. Returns True if successful."""
        if not os.path.exists(path):
            return False
        try:
            import joblib
            model = joblib.load(path)
            self._model = model
            self._trained = True
            self._n_samples = getattr(model, 'n_samples_fit_', 0)
            log.info("SecurityAIAgent model loaded ← %s", path)
            return True
        except Exception as e:
            log.warning("SecurityAIAgent load_model failed: %s", e)
            return False

    @property
    def trained(self) -> bool:  return self._trained
    @property
    def n_samples(self) -> int: return self._n_samples


async def _get_db():
    from backend.database.connection import get_db_client
    return await get_db_client()


def _get_model_path() -> str:
    """BUG-O2 fix: use settings.MODEL_DIR instead of /tmp hardcode."""
    try:
        from backend.core.config import settings
        model_dir = settings.MODEL_DIR
    except Exception:
        model_dir = os.environ.get("MODEL_DIR", "/data/models")
    return os.path.join(model_dir, _MODEL_FILENAME)


class SecurityAIAgent:
    def __init__(self) -> None:
        self._extractor         = _FeatureExtractor()
        self._model             = _IFModel()
        self._buffer: deque     = deque(maxlen=_MAX_BUFFER)
        self._running           = False
        self._last_retrain: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    # Public API — analyze_threat (was stub)
    # ------------------------------------------------------------------ #
    async def analyze_threat(self, event: SecurityEvent) -> AnomalyResult:
        """Full threat analysis: extract features → detect anomaly → persist."""
        return await self.analyze_event(event)

    # ------------------------------------------------------------------ #
    # Public API — analyze_event (orchestrator)
    # ------------------------------------------------------------------ #
    async def analyze_event(self, event: SecurityEvent) -> AnomalyResult:
        t0 = time.monotonic()
        features = self._extractor.extract(event)
        self._buffer.append(features)
        result = await self.detect_anomaly(features)
        result.inference_time_ms = (time.monotonic() - t0) * 1_000
        if result.inference_time_ms > _INFER_TIMEOUT_MS:
            log.warning("Inference %.1f ms > %.0f ms", result.inference_time_ms, _INFER_TIMEOUT_MS)
        asyncio.create_task(self._persist(event, result))
        if result.score < _BLOCK_THRESHOLD:
            asyncio.create_task(self._self_heal(event, result))
        return result

    # ------------------------------------------------------------------ #
    # Public API — detect_anomaly (was stub → now real)
    # ------------------------------------------------------------------ #
    async def detect_anomaly(self, features: List[float]) -> AnomalyResult:
        """IsolationForest scoring with heuristic fallback when model untrained."""
        if self._model.trained:
            score = await self._model.score(features)
            explanation = self._explain(features, score)
        else:
            score, explanation = _heuristic_score(features)
        is_anomaly = score < _SCORE_THRESHOLD
        risk = self._risk(score)
        confidence = min(abs(score) / 0.5, 1.0) if is_anomaly else 0.0
        return AnomalyResult(is_anomaly=is_anomaly, score=round(score, 4),
                             risk_level=risk, confidence=round(confidence, 3),
                             features=features, explanation=explanation)

    # ------------------------------------------------------------------ #
    # Public API — assess_risk_score (was hardcoded 50 → now real)
    # ------------------------------------------------------------------ #
    async def assess_risk_score(self, event: SecurityEvent) -> Dict[str, Any]:
        """Returns risk score 0-100 based on anomaly detection."""
        features = self._extractor.extract(event)
        result = await self.detect_anomaly(features)
        raw = max(0.0, min(1.0, abs(result.score) / 0.5))
        score_100 = round(raw * 100, 1)
        return {
            "score":       score_100,
            "risk_level":  result.risk_level.value,
            "is_anomaly":  result.is_anomaly,
            "explanation": result.explanation,
            "model_used":  "IsolationForest" if self._model.trained else "heuristic",
        }

    # ------------------------------------------------------------------ #
    # Public API — generate_alert (was stub → Telegram)
    # ------------------------------------------------------------------ #
    async def generate_alert(self, result: AnomalyResult, event: SecurityEvent) -> None:
        """Send Telegram alert for HIGH/CRITICAL anomalies."""
        if result.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return
        try:
            from backend.telegram.bot import telegram_bot
            msg = (
                f"🚨 *Security Alert* — {result.risk_level.value.upper()}\n"
                f"IP: `{event.ip_address}` | Endpoint: `{event.endpoint}`\n"
                f"Score: `{result.score:.4f}` | Confidence: `{result.confidence:.1%}`\n"
                f"Reasons: {', '.join(result.explanation)}"
            )
            await telegram_bot.send_alert(msg)
        except Exception as e:
            log.warning("generate_alert Telegram: %s", e)

    # ------------------------------------------------------------------ #
    # Public API — monitor_behavior (was stub → background loop)
    # ------------------------------------------------------------------ #
    async def monitor_behavior(self) -> None:
        """Background monitoring loop — retrain model periodically."""
        await self.start()

    # ------------------------------------------------------------------ #
    # Public API — create_incident (was stub → DB persist)
    # ------------------------------------------------------------------ #
    async def create_incident(self, event: SecurityEvent, result: AnomalyResult) -> Optional[str]:
        """Persist security incident to DB. Returns incident UUID."""
        if not result.is_anomaly:
            return None
        incident_id = str(uuid.uuid4())
        try:
            db = await _get_db()
            await asyncio.wait_for(
                asyncio.to_thread(lambda: db.table("security_incidents").insert({
                    "id":           incident_id,
                    "event_type":   event.event_type.value,
                    "risk_level":   result.risk_level.value,
                    "risk_score":   result.score,
                    "is_anomaly":   result.is_anomaly,
                    "user_id":      event.user_id,
                    "ip_address":   event.ip_address,
                    "endpoint":     event.endpoint,
                    "features":     result.features,
                    "explanation":  result.explanation,
                    "metadata":     event.extra,
                    "created_at":   event.timestamp.isoformat(),
                }).execute()),
                timeout=_DB_TIMEOUT)
            log.info("Incident created: %s (%s)", incident_id, result.risk_level.value)
            asyncio.create_task(self.generate_alert(result, event))
        except Exception as e:
            log.debug("create_incident: %s", e)
        return incident_id

    # ------------------------------------------------------------------ #
    # Public API — update_threat_intel (was stub → DB enrichment)
    # ------------------------------------------------------------------ #
    async def update_threat_intel(self) -> int:
        """Pull historical anomalies from DB into training buffer. Returns count added."""
        added = 0
        try:
            db = await _get_db()
            since = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
            r = await asyncio.wait_for(
                asyncio.to_thread(lambda: db.table("security_ai_analysis")
                    .select("features").gte("created_at", since)
                    .limit(5_000).execute()),
                timeout=_DB_TIMEOUT)
            for row in (r.data or []):
                feat = row.get("features")
                if isinstance(feat, list) and len(feat) == _FEATURE_DIM:
                    self._buffer.append(feat)
                    added += 1
            log.info("update_threat_intel: +%d samples (buffer=%d)", added, len(self._buffer))
        except Exception as e:
            log.debug("update_threat_intel: %s", e)
        return added

    # ------------------------------------------------------------------ #
    # Retrain
    # ------------------------------------------------------------------ #
    async def retrain_model(self) -> None:
        if len(self._buffer) < _MIN_SAMPLES:
            log.info("Skipping retrain: %d/%d samples", len(self._buffer), _MIN_SAMPLES)
            return
        X = np.array(list(self._buffer), dtype=np.float32)
        await self._model.train(X)
        self._last_retrain = datetime.now(timezone.utc)
        # BUG-O1 fix: persist to disk after each retrain
        loop = asyncio.get_running_loop()
        model_path = _get_model_path()
        await loop.run_in_executor(None, self._model.save_model, model_path)

    # ------------------------------------------------------------------ #
    # Start / Stop
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        # BUG-O1 fix: load existing model from disk at startup
        model_path = _get_model_path()
        loop = asyncio.get_running_loop()
        loaded = await loop.run_in_executor(None, self._model.load_model, model_path)
        if loaded:
            log.info("SecurityAIAgent loaded existing model from %s", model_path)
        else:
            log.info("SecurityAIAgent: no saved model at %s — will train after %d samples",
                     model_path, _MIN_SAMPLES)
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.update_threat_intel()
                if (not self._last_retrain or
                        (datetime.now(timezone.utc) - self._last_retrain).total_seconds()
                        >= _RETRAIN_INTERVAL_S):
                    await self.retrain_model()
            except Exception as e:
                log.warning("SecurityAIAgent _run_loop: %s", e)
            await asyncio.sleep(_RETRAIN_INTERVAL_S)

    async def _persist(self, event: SecurityEvent, result: AnomalyResult) -> None:
        if not result.is_anomaly:
            return
        await self.create_incident(event, result)

    async def _self_heal(self, event: SecurityEvent, result: AnomalyResult) -> None:
        log.warning("BLOCK-level anomaly from %s (score=%.4f) — triggering self-heal",
                    event.ip_address, result.score)
        try:
            db = await _get_db()
            await asyncio.wait_for(
                asyncio.to_thread(lambda: db.table("security_blocked_ips").upsert({
                    "ip_address":  event.ip_address,
                    "blocked_at":  datetime.now(timezone.utc).isoformat(),
                    "reason":      ", ".join(result.explanation),
                    "risk_score":  result.score,
                }).execute()),
                timeout=_DB_TIMEOUT)
        except Exception as e:
            log.debug("_self_heal DB: %s", e)

    def _explain(self, features: List[float], score: float) -> List[str]:
        expl: List[str] = []
        _, h_expl = _heuristic_score(features)
        expl.extend(h_expl)
        if score < _BLOCK_THRESHOLD:
            expl.append(f"IF score={score:.4f} (CRITICAL threshold)")
        elif score < _SCORE_THRESHOLD:
            expl.append(f"IF score={score:.4f} (anomaly threshold)")
        return expl or ["normal"]

    def _risk(self, score: float) -> RiskLevel:
        if score < _BLOCK_THRESHOLD:
            return RiskLevel.CRITICAL
        if score < _SCORE_THRESHOLD:
            return RiskLevel.HIGH
        if score < -0.05:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


# Module-level singleton
security_ai_agent = SecurityAIAgent()
