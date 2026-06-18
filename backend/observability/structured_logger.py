"""
faz 9 - Structured JSON Logger
har log entry: timestamp, level, message, correlation_id, trace_id, context
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

# Context variables baraye request tracing
_request_id: ContextVar[str] = ContextVar("request_id", default="")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="")
_symbol: ContextVar[str] = ContextVar("symbol", default="")


def set_request_context(
    request_id: str = "",
    trace_id: str = "",
    user_id: str = "",
    symbol: str = "",
) -> None:
    """Set context variables for current async task"""
    _request_id.set(request_id or str(uuid.uuid4())[:8])
    _trace_id.set(trace_id or str(uuid.uuid4())[:8])
    _user_id.set(user_id)
    _symbol.set(symbol)


def get_request_id() -> str:
    return _request_id.get()


def get_trace_id() -> str:
    return _trace_id.get()


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id.get() or None,
            "trace_id": _trace_id.get() or None,
            "user_id": _user_id.get() or None,
            "symbol": _symbol.get() or None,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Extra fields
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                log_obj[key] = val

        # Exception info
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Remove None values
        log_obj = {k: v for k, v in log_obj.items() if v is not None}

        return json.dumps(log_obj, ensure_ascii=False, default=str)


class StructuredLogger:
    """Logger wrapper ba structured output"""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        if self._logger.isEnabledFor(level):
            self._logger.log(level, message, extra=kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        self._logger.exception(msg, extra=kwargs)


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Initialize logging baraye kol application"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
        )

    root_logger.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Get a StructuredLogger instance"""
    return StructuredLogger(name)
