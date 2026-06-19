"""
backend/agents/security_ai_agent.py
Phase-13: Hybrid Autonomous Security AI Agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_RETRAIN_INTERVAL_SECONDS: int = 3_600
_MIN_SAMPLES_FOR_TRAINING: int = 50
_ANOMALY_SCORE_THRESHOLD: float = -0.15
_FEATURE_DIM: int = 12
_MAX_RECENT_EVENTS: int = 10_000
_SELF_HEAL_BLOCK_THRESHOLD: float = -0.40
_BLOCK_DURATION_SECONDS: int = 3_600


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(str, Enum):
    API_REQUEST = "api_request"
    LOGIN_ATTEMPT = "login_attempt"
    TRADE_ACTIVITY = "trade_activity"
    SESSION_ANOMALY = "session_anomaly"
    WEBSOCKET = "websocket"


@dataclass
class SecurityEvent:
    event_type: EventType
    ip_address: str
    user_id: Optional[str] = None
    endpoint: str = ""
    method: str = "GET"
    status_code: int = 200
    response_time_ms: float = 0.0
    payload_size: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyResult:
    is_anomaly: bool
    score: float
    risk_level: RiskLevel
    confidence: float
    features: List[float]
    explanation: List[str]
    self_heal_action: Optional[str] = None


class _FeatureExtractor:
    def __init__(self) -> None:
        self._ip_req: Dict[str, deque] = defaultdict(lambda: deque())
        self._ip_fail: Dict[str, deque] = defaultdict(lambda: deque())
        self._ip_endpoints: Dict[str, set] = defaultdict(set)

    def _prune(self, dq: deque, window_s: int = 60) -> None:
        cutoff = time.monotonic() - window_s
        while dq and dq[0] < cutoff:
            dq.popleft()

    def extract(self, event: SecurityEvent) -> List[float]:
        now = time.monotonic()
        ip = event.ip_address
        self._ip_req[ip].append(now)
        self._prune(self._ip_req[ip])
        if event.status_code >= 400:
            self._ip_fail[ip].append(now)
            self._prune(self._ip_fail[ip])
        self._ip_endpoints[ip].add(event.endpoint)
        req_rate_1m = len(self._ip_req[ip])
        fail_rate_1m = len(self._ip_fail[ip])
        fail_ratio = fail_rate_1m / max(req_rate_1m, 1)
        endpoint_count = len(self._ip_endpoints[ip])
        is_auth_ep = 1.0 if "auth" in event.endpoint else 0.0
        is_trade_ep = 1.0 if "trade" in event.endpoint or "order" in event.endpoint else 0.0
        is_ws = 1.0 if "ws" in event.endpoint else 0.0
        resp_time_norm = min(event.response_time_ms / 10_000.0, 1.0)
        payload_norm = min(event.payload_size / 1_048_576.0, 1.0)
        status_bucket = (event.status_code // 100) / 5.0
        hour_of_day = datetime.now(timezone.utc).hour / 24.0
        is_night = 1.0 if datetime.now(timezone.utc).hour in range(0, 6) else 0.0
        return [
            req_rate_1m / 100.0,
            fail_rate_1m / 50.0,
            fail_ratio,
            endpoint_count / 20.0,
            is_auth_ep,
            is_trade_ep,
            is_ws,
            resp_time_norm,
            payload_norm,
            status_bucket,
            hour_of_day,
            is_night,
        ]


class _IsolationForestModel:
    def __init__(self) -> None:
        self._model: Any = None
        self._trained_at: Optional[float] = None
        self._n_samples: int = 0
        self._lock = asyncio.Lock()

    def is_trained(self) -> bool:
        return self._model is not None

    async def train(self, X: List[List[float]]) -> bool:
        if len(X) < _MIN_SAMPLES_FOR_TRAINING:
            logger.warning("SecurityAI: only %d samples, need %d", len(X), _MIN_SAMPLES_FOR_TRAINING)
            return False
        async with self._lock:
            try:
                from sklearn.ensemble import IsolationForest
                arr = np.array(X, dtype=np.float32)
                model = IsolationForest(
                    n_estimators=200,
                    max_samples="auto",
                    contamination=0.05,
                    random_state=42,
                    n_jobs=-1,
                )
                model.fit(arr)
                self._model = model
                self._trained_at = time.monotonic()
                self._n_samples = len(X)
                logger.info("SecurityAI: IsolationForest trained on %d samples", len(X))
                return True
            except Exception as exc:
                logger.error("SecurityAI: training failed: %s", exc)
                return False

    def predict(self, features: List[float]) -> Tuple[float, bool]:
        if self._model is None:
            return 0.0, False
        arr = np.array([features], dtype=np.float32)
        score = float(self._model.score_samples(arr)[0])
        return score, score < _ANOMALY_SCORE_THRESHOLD


class _SelfHealingEngine:
    def __init__(self) -> None:
        self._blocked_ips: Dict[str, float] = {}
        self._revoked_sessions: set = set()

    def is_blocked(self, ip: str) -> bool:
        if ip in self._blocked_ips:
            if time.monotonic() < self._blocked_ips[ip]:
                return True
            del self._blocked_ips[ip]
        return False

    async def apply(self, event: SecurityEvent, result: AnomalyResult, db_client: Any) -> Optional[str]:
        if not result.is_anomaly:
            return None
        if result.score >= _SELF_HEAL_BLOCK_THRESHOLD:
            return None
        ip = event.ip_address
        self._blocked_ips[ip] = time.monotonic() + _BLOCK_DURATION_SECONDS
        action = f"auto_block_ip:{ip}:1h"
        logger.warning("SecurityAI: auto-blocked IP %s (score=%.3f)", ip, result.score)
        if event.user_id:
            self._revoked_sessions.add(event.user_id)
            action += f"|revoke_sessions:{event.user_id}"
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: db_client.table("revoked_tokens")
                    .insert({"user_id": event.user_id, "reason": "security_ai_auto_revoke"})
                    .execute(),
                )
            except Exception as exc:
                logger.error("SecurityAI: failed to revoke sessions: %s", exc)
        return action


class SecurityAIAgent:
    """
    Phase-13: Hybrid Autonomous Security AI Agent.
    IsolationForest ML + heuristic fallback + self-healing.
    """

    def __init__(self) -> None:
        self._model = _IsolationForestModel()
        self._extractor = _FeatureExtractor()
        self._healer = _SelfHealingEngine()
        self._event_buffer: deque = deque(maxlen=_MAX_RECENT_EVENTS)
        self._feature_buffer: deque = deque(maxlen=_MAX_RECENT_EVENTS)
        self._retrain_task: Optional[asyncio.Task] = None
        self._db_client: Any = None
        self._analysis_count: int = 0
        self._anomaly_count: int = 0
        self._last_retrain: Optional[datetime] = None

    async def start(self) -> None:
        try:
            from backend.database.connection import get_db_client
            self._db_client = await get_db_client()
        except Exception as exc:
            logger.warning("SecurityAI: DB unavailable at start: %s", exc)
        await self.retrain_model()
        self._retrain_task = asyncio.create_task(
            self._retrain_loop(), name="security_ai_retrain"
        )
        logger.info("SecurityAI: agent started")

    async def stop(self) -> None:
        if self._retrain_task and not self._retrain_task.done():
            self._retrain_task.cancel()
            try:
                await self._retrain_task
            except asyncio.CancelledError:
                pass
        logger.info("SecurityAI: agent stopped")

    async def _retrain_loop(self) -> None:
        while True:
            await asyncio.sleep(_RETRAIN_INTERVAL_SECONDS)
            await self.retrain_model()

    async def analyze_event(self, event: SecurityEvent) -> AnomalyResult:
        features = self._extractor.extract(event)
        self._event_buffer.append(event)
        self._feature_buffer.append(features)
        score, is_anomaly = self._model.predict(features)
        if not self._model.is_trained():
            score, is_anomaly = self._heuristic_fallback(event, features)
        risk_level = self._score_to_risk(score, is_anomaly)
        confidence = self._calc_confidence(score)
        explanation = self._explain(event, features, score, is_anomaly)
        result = AnomalyResult(
            is_anomaly=is_anomaly,
            score=round(score, 6),
            risk_level=risk_level,
            confidence=round(confidence, 4),
            features=features,
            explanation=explanation,
        )
        if is_anomaly and self._db_client:
            action = await self._healer.apply(event, result, self._db_client)
            result.self_heal_action = action
        self._analysis_count += 1
        if is_anomaly:
            self._anomaly_count += 1
        asyncio.create_task(self._persist_analysis(event, result))
        return result

    async def detect_anomaly(self, features: List[float]) -> Tuple[float, bool]:
        return self._model.predict(features)

    async def retrain_model(self) -> bool:
        X: List[List[float]] = list(self._feature_buffer)
        if self._db_client:
            try:
                db_features = await asyncio.get_running_loop().run_in_executor(
                    None, self._fetch_training_data
                )
                X = db_features + X
            except Exception as exc:
                logger.warning("SecurityAI: DB fetch for training failed: %s", exc)
        if not X:
            logger.info("SecurityAI: no training data yet")
            return False
        success = await self._model.train(X)
        if success:
            self._last_retrain = datetime.now(timezone.utc)
        return success

    def is_ip_blocked(self, ip: str) -> bool:
        return self._healer.is_blocked(ip)

    def stats(self) -> Dict[str, Any]:
        return {
            "analysis_count": self._analysis_count,
            "anomaly_count": self._anomaly_count,
            "model_trained": self._model.is_trained(),
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
            "buffer_size": len(self._feature_buffer),
            "blocked_ips": len(self._healer._blocked_ips),
        }

    def _heuristic_fallback(self, event: SecurityEvent, features: List[float]) -> Tuple[float, bool]:
        score = 0.0
        req_rate = features[0] * 100
        fail_rate = features[1] * 50
        fail_ratio = features[2]
        if req_rate > 50:
            score -= 0.3
        if fail_rate > 10:
            score -= 0.25
        if fail_ratio > 0.5:
            score -= 0.2
        if features[4] == 1.0 and fail_rate > 3:
            score -= 0.3
        return score, score < _ANOMALY_SCORE_THRESHOLD

    def _score_to_risk(self, score: float, is_anomaly: bool) -> RiskLevel:
        if not is_anomaly:
            return RiskLevel.LOW
        if score > -0.25:
            return RiskLevel.MEDIUM
        if score > -0.40:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _calc_confidence(self, score: float) -> float:
        return max(0.0, min(1.0, (-score + 0.1) / 0.8))

    def _explain(self, event: SecurityEvent, features: List[float], score: float, is_anomaly: bool) -> List[str]:
        reasons: List[str] = []
        if features[0] * 100 > 30:
            reasons.append(f"High request rate: {features[0]*100:.0f} req/min")
        if features[2] > 0.3:
            reasons.append(f"High failure ratio: {features[2]*100:.0f}%")
        if features[4] == 1.0 and features[1] * 50 > 3:
            reasons.append("Multiple auth failures")
        if features[11] == 1.0:
            reasons.append("Night-time activity (00:00-06:00 UTC)")
        if features[9] < 0.6:
            reasons.append(f"HTTP {event.status_code} error responses")
        if not reasons and is_anomaly:
            reasons.append(f"Statistical anomaly (IF score={score:.4f})")
        return reasons

    def _fetch_training_data(self) -> List[List[float]]:
        rows = (
            self._db_client.table("security_audit_logs")
            .select("ip_address,endpoint,method,status_code,response_time_ms,payload_size,created_at,event_type")
            .order("created_at", desc=True)
            .limit(5_000)
            .execute()
        )
        X: List[List[float]] = []
        for row in (rows.data or []):
            try:
                event = SecurityEvent(
                    event_type=EventType(row.get("event_type", "api_request")),
                    ip_address=row.get("ip_address", "0.0.0.0"),
                    endpoint=row.get("endpoint", ""),
                    method=row.get("method", "GET"),
                    status_code=int(row.get("status_code", 200)),
                    response_time_ms=float(row.get("response_time_ms", 0)),
                    payload_size=int(row.get("payload_size", 0)),
                )
                X.append(self._extractor.extract(event))
            except Exception:
                continue
        return X

    async def _persist_analysis(self, event: SecurityEvent, result: AnomalyResult) -> None:
        if not self._db_client:
            return
        try:
            record = {
                "event_type": event.event_type.value,
                "ip_address": event.ip_address,
                "user_id": event.user_id,
                "endpoint": event.endpoint,
                "is_anomaly": result.is_anomaly,
                "anomaly_score": result.score,
                "risk_level": result.risk_level.value,
                "confidence": result.confidence,
                "features": json.dumps(result.features),
                "explanation": json.dumps(result.explanation),
                "self_heal_action": result.self_heal_action,
                "created_at": event.timestamp.isoformat(),
            }
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._db_client.table("security_ai_analysis").insert(record).execute(),
            )
        except Exception as exc:
            logger.debug("SecurityAI: persist failed: %s", exc)


_agent_instance: Optional[SecurityAIAgent] = None
_agent_lock = asyncio.Lock()


async def get_security_agent() -> SecurityAIAgent:
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance
    async with _agent_lock:
        if _agent_instance is None:
            _agent_instance = SecurityAIAgent()
            await _agent_instance.start()
    return _agent_instance
