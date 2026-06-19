"""Structured logging for Galaxy Vast AI Trading Platform.

Provides:
- JSON structured logging in production
- Human-readable logging in development
- Correlation ID propagation via contextvars
- Log sanitization (no secrets in logs)
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from typing import Any

# ContextVar for request correlation ID
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


class _SanitizeFilter(logging.Filter):
    """Strip secrets from log records."""

    _REDACT = frozenset({
        "password", "secret", "token", "key", "authorization",
        "supabase_key", "jwt_secret", "license_salt", "license_secret",
    })

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        msg = str(record.getMessage())
        for word in self._REDACT:
            if word in msg.lower():
                record.msg = "[REDACTED — contains sensitive data]"
                record.args = ()
                break
        return True


class _CorrelationFilter(logging.Filter):
    """Inject correlation_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        return True


def _configure_logging() -> None:
    environment = os.getenv("ENVIRONMENT", "production")
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Reset handlers
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_SanitizeFilter())
    handler.addFilter(_CorrelationFilter())

    if environment == "production":
        # JSON structured for log aggregators (Loki, CloudWatch, etc.)
        fmt = (
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "correlation_id": "%(correlation_id)s", '
            '"message": "%(message)s"}'
        )
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    else:
        # Human-readable in development
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | [%(correlation_id)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for name in ("uvicorn.access", "httpx", "httpcore", "supabase", "postgrest"):
        logging.getLogger(name).setLevel(logging.WARNING)


_configure_logging()


def get_logger(name: str) -> logging.Logger:
    """Return a logger with sanitize + correlation filters attached."""
    return logging.getLogger(name)
