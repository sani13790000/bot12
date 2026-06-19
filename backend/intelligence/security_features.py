"""
backend/intelligence/security_features.py
Phase-2 (FINAL) + Phase-13 performance requirements.

12 features, all normalized [0.0, 1.0].
Hot path < 5ms — reads only in-process deque.
Background: geo enrichment via threat intel (async only).
"""
from __future__ import annotations
import asyncio, hashlib, logging, math, os, time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional
import numpy as np

log = logging.getLogger(__name__)

_FEATURE_DIM = 12
_WINDOW_S    = 300.0
_MAX_TRACKED = 50_000
_DB_TIMEOUT  = 2.0


@dataclass
class FeatureVector:
    request_rate:         float = 0.0
    failed_login_ratio:   float = 0.0
    ip_entropy:           float = 0.0
    trade_frequency:      float = 0.0
    trade_volume_change:  float = 0.0
    session_duration:     float = 0.0
    endpoint_diversity:   float = 0.0
    error_rate:           float = 0.0
    unusual_hour:         float = 0.0
    geo_change_flag:      float = 0.0
    payload_size_avg:     float = 0.0
    repeat_pattern_score: float = 0.0
    ip:           str           = ""
    user_id:      Optional[str] = None
    risk_level:   str           = "low"
    extracted_at: str           = ""

    def to_array(self) -> np.ndarray:
        return np.array([
            self.request_rate, self.failed_login_ratio, self.ip_entropy,
            self.trade_frequency, self.trade_volume_change, self.session_duration,
            self.endpoint_diversity, self.error_rate, self.unusual_hour,
            self.geo_change_flag, self.payload_size_avg, self.repeat_pattern_score,
        ], dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_rate":         round(self.request_rate, 4),
            "failed_login_ratio":   round(self.failed_login_ratio, 4),
            "ip_entropy":           round(self.ip_entropy, 4),
            "trade_frequency":      round(self.trade_frequency, 4),
            "trade_volume_change":  round(self.trade_volume_change, 4),
            "session_duration":     round(self.session_duration, 4),
            "endpoint_diversity":   round(self.endpoint_diversity, 4),
            "error_rate":           round(self.error_rate, 4),
            "unusual_hour":         self.unusual_hour,
            "geo_change_flag":      self.geo_change_flag,
            "payload_size_avg":     round(self.payload_size_avg, 4),
            "repeat_pattern_score": round(self.repeat_pattern_score, 4),
            "ip": self.ip, "user_id": self.user_id,
            "risk_level": self.risk_level, "extracted_at": self.extracted_at,
        }


@dataclass
class _RequestEvent:
    ts: float; path: str; status: int
    payload_bytes: int; is_login: bool; is_failed_login: bool


class _IPBuffer:
    __slots__ = ("_events", "_login_failures", "_last_asn",
                 "_session_start", "_trade_times", "_prev_trade_vol")

    def __init__(self) -> None:
        self._events:         Deque[_RequestEvent] = deque()
        self._login_failures: int   = 0
        self._last_asn:       str   = ""
        self._session_start:  float = time.monotonic()
        self._trade_times:    Deque[float] = deque(maxlen=1000)
        self._prev_trade_vol: float = 0.0

    def record_request(self, path: str, status: int, payload: int = 0) -> None:
        now  = time.monotonic()
        is_l = path.endswith("/login") or path.endswith("/auth/login")
        is_f = is_l and status in (401, 403, 429)
        self._events.append(_RequestEvent(now, path, status, payload, is_l, is_f))
        if is_f: self._login_failures += 1
        self._purge(now)

    def record_trade(self, volume: float = 0.0) -> None:
        self._trade_times.append(time.monotonic())
        self._prev_trade_vol = volume

    def _purge(self, now: float) -> None:
        cutoff = now - _WINDOW_S
        while self._events and self._events[0].ts < cutoff:
            ev = self._events.popleft()
            if ev.is_failed_login:
                self._login_failures = max(0, self._login_failures - 1)

    def snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        self._purge(now)
        evs   = list(self._events)
        total = max(len(evs), 1)
        if not evs: return {}
        paths    = [e.path for e in evs]
        statuses = [e.status for e in evs]
        payloads = [e.payload_bytes for e in evs]
        span     = (evs[-1].ts - evs[0].ts) if len(evs) > 1 else 1.0
        path_counts = defaultdict(int)
        for p in paths: path_counts[p] += 1
        entropy = -sum((c / total) * math.log2(c / total)
                       for c in path_counts.values() if c > 0)
        max_ent = math.log2(total + 1)
        return {
            "total_requests":  total,
            "window_span":     max(span, 1.0),
            "failed_logins":   self._login_failures,
            "unique_paths":    len(set(paths)),
            "error_count":     sum(1 for s in statuses if s >= 400),
            "avg_payload":     sum(payloads) / total,
            "repeat_score":    1.0 - (entropy / max_ent) if max_ent > 0 else 0.0,
            "session_seconds": now - self._session_start,
            "trade_count_1h":  sum(1 for t in self._trade_times if t > now - 3600),
            "prev_trade_vol":  self._prev_trade_vol,
        }


def _ip_entropy(ip: str) -> float:
    try:
        parts = [int(x) for x in ip.split(".")]
        if len(parts) != 4: return 0.5
        total = sum(parts) or 1
        probs = [p / total for p in parts if p > 0]
        return min(1.0, -sum(p * math.log2(p) for p in probs) / 8.0)
    except Exception:
        return (int(hashlib.md5(ip.encode()).hexdigest(), 16) % 1000) / 1000.0


def _classify_risk(fv: FeatureVector) -> str:
    score = (fv.failed_login_ratio * 3.0 + fv.request_rate * 2.0 +
             fv.error_rate * 2.0 + fv.geo_change_flag * 2.0 +
             fv.unusual_hour + fv.repeat_pattern_score +
             fv.trade_volume_change * 1.5)
    if score >= 7.0: return "critical"
    if score >= 4.0: return "high"
    if score >= 2.0: return "medium"
    return "low"


class SecurityFeatureExtractor:
    def __init__(self) -> None:
        self._buffers:   Dict[str, _IPBuffer] = {}
        self._last_seen: Dict[str, float]     = {}
        self._geo_cache: Dict[str, str]       = {}

    def ingest_request(self, ip: str, path: str, status: int, payload: int = 0) -> None:
        self._get_buf(ip).record_request(path, status, payload)
        self._last_seen[ip] = time.monotonic()
        self._maybe_evict()

    def ingest_trade(self, ip: str, volume: float = 0.0) -> None:
        self._get_buf(ip).record_trade(volume)

    async def extract(
        self, ip: str, user_id: Optional[str] = None,
        window_seconds: float = _WINDOW_S, enrich_db: bool = False,
    ) -> FeatureVector:
        t0   = time.perf_counter()
        snap = self._get_buf(ip).snapshot()
        total   = snap.get("total_requests", 0)
        span    = snap.get("window_span", 1.0)
        failed  = snap.get("failed_logins", 0)
        tc      = snap.get("trade_count_1h", 0)
        pv      = snap.get("prev_trade_vol", 0.0)
        hour    = datetime.now(timezone.utc).hour
        geo     = await self._check_geo_change(ip) if enrich_db else 0.0

        fv = FeatureVector(
            request_rate         = min(1.0, (total / span) / 10.0) if total > 0 else 0.0,
            failed_login_ratio   = min(1.0, failed / max(total, 1)),
            ip_entropy           = _ip_entropy(ip),
            trade_frequency      = min(1.0, tc / 100.0),
            trade_volume_change  = min(1.0, abs(tc - pv) / max(pv, 1.0)),
            session_duration     = min(1.0, snap.get("session_seconds", 0) / 60.0 / 480.0),
            endpoint_diversity   = min(1.0, snap.get("unique_paths", 0) / max(total, 1)),
            error_rate           = min(1.0, snap.get("error_count", 0) / max(total, 1)),
            unusual_hour         = 1.0 if 2 <= hour <= 5 else 0.0,
            geo_change_flag      = geo,
            payload_size_avg     = min(1.0, snap.get("avg_payload", 0) / 10_000.0),
            repeat_pattern_score = snap.get("repeat_score", 0.0),
            ip=ip, user_id=user_id,
            extracted_at=datetime.now(timezone.utc).isoformat(),
        )
        fv.risk_level = _classify_risk(fv)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > 10.0:
            log.warning("Feature extraction slow: %.1fms for %s", elapsed_ms, ip)
        return fv

    async def extract_batch(self, ips: List[str]) -> List[FeatureVector]:
        return list(await asyncio.gather(*[self.extract(ip) for ip in ips]))

    def get_matrix(self, ips: Optional[List[str]] = None) -> np.ndarray:
        target = ips or list(self._buffers.keys())
        rows   = []
        hour   = datetime.now(timezone.utc).hour
        for ip in target:
            buf  = self._buffers.get(ip)
            if not buf: continue
            snap = buf.snapshot()
            if not snap: continue
            total = snap.get("total_requests", 0)
            span  = snap.get("window_span", 1.0)
            rows.append(np.array([
                min(1.0, (total / span) / 10.0) if total > 0 else 0.0,
                min(1.0, snap.get("failed_logins", 0) / max(total, 1)),
                _ip_entropy(ip),
                min(1.0, snap.get("trade_count_1h", 0) / 100.0),
                0.0,
                min(1.0, snap.get("session_seconds", 0) / 60.0 / 480.0),
                min(1.0, snap.get("unique_paths", 0) / max(total, 1)),
                min(1.0, snap.get("error_count", 0) / max(total, 1)),
                1.0 if 2 <= hour <= 5 else 0.0,
                0.0,
                min(1.0, snap.get("avg_payload", 0) / 10_000.0),
                snap.get("repeat_score", 0.0),
            ], dtype=np.float32))
        return np.vstack(rows) if rows else np.empty((0, _FEATURE_DIM), dtype=np.float32)

    def _get_buf(self, ip: str) -> _IPBuffer:
        if ip not in self._buffers:
            self._buffers[ip]   = _IPBuffer()
            self._last_seen[ip] = time.monotonic()
        return self._buffers[ip]

    def _maybe_evict(self) -> None:
        if len(self._buffers) <= _MAX_TRACKED: return
        evict = sorted(self._last_seen, key=lambda k: self._last_seen[k])
        for ip in evict[:_MAX_TRACKED // 10]:
            self._buffers.pop(ip, None)
            self._last_seen.pop(ip, None)
            self._geo_cache.pop(ip, None)

    async def _check_geo_change(self, ip: str) -> float:
        try:
            from backend.services.threat_intelligence_service import threat_intel_service
            report = await asyncio.wait_for(threat_intel_service.check_ip(ip), timeout=_DB_TIMEOUT)
            asn  = str(report.metadata.get("asn", ""))
            prev = self._geo_cache.get(ip, asn)
            self._geo_cache[ip] = asn
            return 0.0 if asn == prev else 1.0
        except Exception:
            return 0.0

    def stats(self) -> Dict[str, Any]:
        return {"tracked_ips": len(self._buffers), "feature_dim": _FEATURE_DIM,
                "window_seconds": _WINDOW_S, "max_tracked": _MAX_TRACKED}


feature_extractor = SecurityFeatureExtractor()
