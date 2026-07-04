"""
backend/observability/monitoring.py
Galaxy Vast AI Trading Platform - Production Monitoring
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
_ENV = os.environ.get("APP_ENV", "development")
_IS_PROD = _ENV == "production"

DRAWDOWN_ALERT_PCT = float(os.environ.get("DRAWDOWN_ALERT_PCT", "5.0"))
ERROR_RATE_ALERT_PCT = float(os.environ.get("ERROR_RATE_ALERT_PCT", "10.0"))
LATENCY_ALERT_MS = float(os.environ.get("LATENCY_ALERT_MS", "3000.0"))

_startup_time = time.time()


def init_sentry() -> bool:
    if not _SENTRY_DSN:
        log.info("Sentry disabled - SENTRY_DSN not set")
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=_ENV,
            traces_sample_rate=0.1 if _IS_PROD else 1.0,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                AsyncioIntegration(),
            ],
            before_send=_before_send_sentry,
        )
        log.info("Sentry initialized | env=%s", _ENV)
        return True
    except ImportError:
        log.warning("sentry-sdk not installed")
        return False
    except Exception as exc:
        log.error("Sentry init failed: %s", exc)
        return False


def _before_send_sentry(event: dict, hint: dict) -> Optional[dict]:
    if "request" in event and "headers" in event.get("request", {}):
        hdrs = event["request"]["headers"]
        if "Authorization" in hdrs:
            hdrs["Authorization"] = "[REDACTED]"
        if "authorization" in hdrs:
            hdrs["authorization"] = "[REDACTED]"
    return event


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json
        doc = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "env": _ENV,
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            doc["request_id"] = record.request_id  # type: ignore
        if hasattr(record, "user_id"):
            doc["user_id"] = record.user_id  # type: ignore
        return json.dumps(doc, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if _IS_PROD:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.addHandler(handler)
    log.info("Logging configured | level=%s env=%s", level, _ENV)


@dataclass
class MetricsSnapshot:
    uptime_s: float = 0.0
    latency_alert_ms: float = LATENCY_ALERT_MS
    error_rate_alert_pct: float = ERROR_RATE_ALERT_PCT
    drawdown_alert_pct: float = DRAWDOWN_ALERT_PCT
    is_prod: bool = _IS_PROD


def get_uptime() -> float:
    return time.time() - _startup_time


def check_drawdown_alert(drawdown_pct: float) -> bool:
    return drawdown_pct >= DRAWDOWN_ALERT_PCT


def check_error_rate_alert(error_rate_pct: float) -> bool:
    return error_rate_pct >= ERROR_RATE_ALERT_PCT


def check_latency_alert(latency_ms: float) -> bool:
    return latency_ms >= LATENCY_ALERT_MS


class ProductionMonitor:
    """Central production monitoring coordinator."""

    def __init__(self):
        self._sentry_ok = False
        self._metrics = MetricsSnapshot()

    def initialize(self) -> None:
        self._sentry_ok = init_sentry()
        log.info("[monitor] initialized | sentry=%s env=%s", self._sentry_ok, _ENV)

    def snapshot(self) -> MetricsSnapshot:
        self._metrics.uptime_s = get_uptime()
        return self._metrics

    def alert_drawdown(self, drawdown_pct: float) -> None:
        if check_drawdown_alert(drawdown_pct):
            log.warning("[monitor] DRAWDOWN ALERT: %.2f%% >= %.2f%%",
                        drawdown_pct, DRAWDOWN_ALERT_PCT)

    def alert_error_rate(self, error_rate_pct: float) -> None:
        if check_error_rate_alert(error_rate_pct):
            log.warning("[monitor] ERROR RATE ALERT: %.2f%% >= %.2f%%",
                        error_rate_pct, ERROR_RATE_ALERT_PCT)

    def alert_latency(self, latency_ms: float) -> None:
        if check_latency_alert(latency_ms):
            log.warning("[monitor] LATENCY ALERT: %.0fms >= %.0fms",
                        latency_ms, LATENCY_ALERT_MS)
