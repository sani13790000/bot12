"""backend/observability/observability_patch.py — Phase T

T-13: prometheus_format() fallback text
T-14: AlertManager deduplication — prevents Telegram flood
T-15: correlation_id propagation across async tasks
T-16: fire() warns loudly on unknown rule names
T-17: TradeLatencyHistogram for P50/P90/P99
T-18: thread-safe label keys
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from contextvars import ContextVar

log = logging.getLogger(__name__)

_DEDUP_WINDOW_SEC = 300
_DEDUP_MAX_KEYS = 1_000


class AlertDeduplicator:
    """T-14: Prevents alert flooding within window_sec."""

    def __init__(self, window_sec: int = _DEDUP_WINDOW_SEC) -> None:
        self._window = window_sec
        self._seen: Dict[str, float] = {}

    def _make_key(self, rule_name: str, context: Optional[Dict[str, Any]]) -> str:
        ctx_str = str(sorted((context or {}).items()))
        raw = f"{rule_name}:{ctx_str}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def should_fire(self, rule_name: str, context: Optional[Dict[str, Any]]) -> bool:
        key = self._make_key(rule_name, context)
        now = time.monotonic()
        last = self._seen.get(key)
        if last is not None and (now - last) < self._window:
            log.debug("Alert '%s' suppressed (dedup window %ds)", rule_name, self._window)
            return False
        if len(self._seen) >= _DEDUP_MAX_KEYS:
            oldest = min(self._seen, key=lambda k: self._seen[k])
            del self._seen[oldest]
        self._seen[key] = now
        return True

    def reset(self) -> None:
        self._seen.clear()


_alert_deduplicator = AlertDeduplicator()


def patch_alert_manager() -> None:
    """T-14 + T-16: deduplication + unknown-rule loud warning."""
    from backend.observability.alert_manager import AlertManager
    _original_fire = AlertManager.fire

    async def _patched_fire(self, rule_name: str, context=None) -> bool:
        if rule_name not in self._rules:
            log.warning("alert_manager.fire(): UNKNOWN rule '%s' — alert dropped. Available: %s", rule_name, list(self._rules.keys()))
            return False
        if not _alert_deduplicator.should_fire(rule_name, context):
            return False
        return await _original_fire(self, rule_name, context)

    AlertManager.fire = _patched_fire
    log.info("AlertManager patched: T-14 dedup + T-16 unknown-rule warning")


class TradeLatencyHistogram:
    """T-17: P50/P90/P99 trade execution latency."""
    _WINDOW = 10_000

    def __init__(self) -> None:
        self._samples: deque = deque(maxlen=self._WINDOW)

    def observe_sync(self, latency_ms: float) -> None:
        self._samples.append(latency_ms)

    async def observe(self, latency_ms: float) -> None:
        self._samples.append(latency_ms)

    def percentile(self, p: float) -> float:
        s = sorted(self._samples)
        if not s:
            return 0.0
        idx = max(0, int(len(s) * p / 100) - 1)
        return s[idx]

    def snapshot(self) -> Dict[str, float]:
        return {"count": len(self._samples), "p50_ms": round(self.percentile(50), 2), "p90_ms": round(self.percentile(90), 2), "p99_ms": round(self.percentile(99), 2), "max_ms": round(max(self._samples, default=0.0), 2)}

    def patch_into_metrics_registry(self) -> None:
        try:
            from backend.observability.metrics import metrics_registry
            metrics_registry.trade_latency = self
            log.info("TradeLatencyHistogram injected into metrics_registry")
        except Exception as exc:
            log.warning("Could not patch metrics_registry: %s", exc)


trade_latency = TradeLatencyHistogram()

_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def set_correlation_id(cid: str) -> None:
    _correlation_id_var.set(cid)


def get_correlation_id() -> str:
    return _correlation_id_var.get("")


def get_prometheus_text() -> str:
    """T-13: Always returns valid exposition text, even without prometheus_client."""
    try:
        from prometheus_client import generate_latest
        return generate_latest().decode("utf-8")
    except ImportError:
        pass
    snap = trade_latency.snapshot()
    lines = [
        "# HELP gv_uptime_seconds Uptime",
        "# TYPE gv_uptime_seconds gauge",
        f"gv_uptime_seconds {time.time():.1f}",
        "# HELP gv_trade_latency_p99_ms P99 trade latency ms",
        "# TYPE gv_trade_latency_p99_ms gauge",
        f"gv_trade_latency_p99_ms {snap['p99_ms']}",
    ]
    return "\n".join(lines) + "\n"


def safe_label_key(**labels: str) -> str:
    """T-18: Immutable hashable key from label dict."""
    return str(tuple(sorted(labels.items())))


def apply_all_patches() -> None:
    patch_alert_manager()
    trade_latency.patch_into_metrics_registry()
    log.info("Phase-T observability patches applied")
