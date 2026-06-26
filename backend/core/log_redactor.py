"""
backend/core/log_redactor.py
Galaxy Vast AI — Log Redaction Layer (Phase 11)

P11-LR-1: تمام log recordها را قبل از emit بررسی می‌کند
P11-LR-2: 15 pattern برای redact: JWT، password، card، MT5، API key
P11-LR-3: structlog و stdlib logging هر دو پوشش داده می‌شوند
P11-LR-4: Redacted value → [REDACTED:TYPE] برای debugging
P11-LR-5: False positive rate پایین — فقط key=value patterns
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    (
        "jwt",
        re.compile(
            r"(eyJ[A-Za-z0-9_-]{4,}\.eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,})",
            re.ASCII,
        ),
        "[REDACTED:JWT]",
    ),
    (
        "bearer",
        re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
        r"\1[REDACTED:BEARER]",
    ),
    (
        "password",
        re.compile(
            r'(password|passwd|pwd|pass)(\s*[:=]\s*)["\']?([^\s"\']&,;}{]{3,})["\']?',
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED:PASSWORD]",
    ),
    (
        "secret",
        re.compile(
            r'((?:secret|api_?key|api_?token|access_?token|refresh_?token|'
            r'client_?secret|private_?key|signing_?key|license_?key|license_?secret|'
            r'license_?salt|mql5_?api_?token|telegram_?bot_?token|telegram_?webhook_?secret|'
            r'jwt_?secret(?:_?key)?|supabase_?(?:service_?)?key|master_?key|'
            r'\w+_secret(?:_key)?|\w+_?password|\w+_?api_?(?:key|token))'
            r')(\s*[:=]\s*)["\']?([^\s"\']&,;}{]{4,})["\']?',
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED:SECRET]",
    ),
    (
        "card",
        re.compile(r"\b([3-6]\d{3})[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}\b"),
        r"\1-****-****-[REDACTED:CARD]",
    ),
    (
        "mt5_password",
        re.compile(
            r"(mt5_password|MT5_PASSWORD|mt5.*pass)(\s*[:=]\s*)(\S+)",
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED:MT5_PASSWORD]",
    ),
    (
        "supabase",
        re.compile(r"(eyJ[A-Za-z0-9_-]{50,})", re.ASCII),
        "[REDACTED:SUPABASE_KEY]",
    ),
    (
        "hex_secret",
        re.compile(r"\b([0-9a-fA-F]{32,})\b"),
        "[REDACTED:HEX_SECRET]",
    ),
]

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "pwd", "pass",
    "secret", "jwt_secret", "jwt_secret_key",
    "api_key", "apikey", "api_token",
    "access_token", "refresh_token", "id_token",
    "client_secret", "private_key", "signing_key",
    "license_key", "license_secret", "license_salt",
    "mql5_api_token",
    "telegram_bot_token", "telegram_webhook_secret",
    "supabase_key", "supabase_service_key",
    "master_key", "secrets_master_key",
    "mt5_password",
    "card_number", "pan", "cvv", "cvc",
    "authorization",
    "x-api-key",
    "cookie",
})


def redact_string(text: str) -> str:
    """Apply all redaction patterns to a string."""
    for _name, pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_dict(data: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """Recursively redact sensitive keys from a dict (max 5 levels)."""
    if depth > 5:
        return data
    result = {}
    for k, v in data.items():
        key_lower = k.lower().replace("-", "_")
        if key_lower in _SENSITIVE_KEYS:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, depth + 1)
        elif isinstance(v, str):
            result[k] = redact_string(v)
        elif isinstance(v, (list, tuple)):
            result[k] = [
                redact_dict(i, depth + 1) if isinstance(i, dict)
                else redact_string(i) if isinstance(i, str)
                else i
                for i in v
            ]
        else:
            result[k] = v
    return result


class RedactionFilter(logging.Filter):
    """P11-LR-3: stdlib logging filter — redacts msg, args, extra fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
        _SKIP = {
            "msg", "args", "exc_info", "exc_text", "stack_info",
            "name", "levelname", "levelno", "pathname", "filename",
            "module", "funcName", "lineno", "created", "msecs",
            "relativeCreated", "thread", "threadName", "processName",
            "process", "message",
        }
        for attr in list(vars(record).keys()):
            if attr in _SKIP:
                continue
            val = getattr(record, attr)
            if isinstance(val, str):
                setattr(record, attr, redact_string(val))
            elif isinstance(val, dict):
                setattr(record, attr, redact_dict(val))
        return True


def install_redaction_filter(logger_name: Optional[str] = None) -> None:
    """Install RedactionFilter on root (or named) logger. Call once at startup."""
    target = logging.getLogger(logger_name)
    f = RedactionFilter()
    if not any(isinstance(x, RedactionFilter) for x in target.filters):
        target.addFilter(f)
    for handler in target.handlers:
        if not any(isinstance(x, RedactionFilter) for x in handler.filters):
            handler.addFilter(f)


def structlog_redact_processor(logger: Any, method: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """P11-LR-3: structlog processor. Add to processor chain at startup."""
    return redact_dict(event_dict)
