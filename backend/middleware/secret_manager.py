"""
Phase 10 — Secret Manager
Validates all required env vars at startup.
Never logs secret values — only their presence/absence.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.observability import get_logger

logger = get_logger("security.secrets")


@dataclass
class SecretSpec:
    name: str
    required: bool = True
    min_length: int = 8
    description: str = ""


# All secrets the bot needs
_SECRETS: List[SecretSpec] = [
    SecretSpec("SUPABASE_URL", required=True, min_length=20, description="Supabase project URL"),
    SecretSpec("SUPABASE_ANON_KEY", required=True, min_length=20, description="Supabase anon key"),
    SecretSpec("SUPABASE_SERVICE_KEY", required=False, min_length=20, description="Supabase service role key"),
    SecretSpec("JWT_SECRET", required=True, min_length=32, description="JWT signing secret"),
    SecretSpec("ALLOWED_ORIGINS", required=False, min_length=5, description="Comma-separated CORS origins"),
    SecretSpec("SENTRY_DSN", required=False, min_length=10, description="Sentry DSN"),
    SecretSpec("TELEGRAM_BOT_TOKEN", required=False, min_length=20, description="Telegram bot token"),
    SecretSpec("TELEGRAM_ADMIN_CHAT_ID", required=False, min_length=5, description="Admin chat ID"),
    SecretSpec("MT5_LOGIN", required=False, min_length=5, description="MT5 account login"),
    SecretSpec("MT5_PASSWORD", required=False, min_length=4, description="MT5 account password"),
    SecretSpec("MT5_SERVER", required=False, min_length=3, description="MT5 broker server"),
    SecretSpec("REDIS_URL", required=False, min_length=10, description="Redis connection URL"),
    SecretSpec("NEWS_API_KEY", required=False, min_length=10, description="NewsAPI key"),
]


@dataclass
class SecretValidationResult:
    ok: bool
    missing_required: List[str] = field(default_factory=list)
    too_short: List[str] = field(default_factory=list)
    present_optional: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)

    def summary(self) -> Dict:
        return {
            "valid": self.ok,
            "missing_required": self.missing_required,
            "too_short": self.too_short,
            "optional_present": len(self.present_optional),
            "optional_missing": self.missing_optional,
        }


def validate_secrets() -> SecretValidationResult:
    """Validate all secrets at startup. Call from lifespan."""
    missing_required: List[str] = []
    too_short: List[str] = []
    present_optional: List[str] = []
    missing_optional: List[str] = []

    for spec in _SECRETS:
        val = os.getenv(spec.name, "")
        if not val:
            if spec.required:
                missing_required.append(spec.name)
                logger.error(f"MISSING required secret: {spec.name} — {spec.description}")
            else:
                missing_optional.append(spec.name)
                logger.warning(f"Optional secret not set: {spec.name} — {spec.description}")
        elif len(val) < spec.min_length:
            too_short.append(spec.name)
            logger.error(f"Secret too short: {spec.name} (min {spec.min_length} chars)")
        else:
            if not spec.required:
                present_optional.append(spec.name)
            logger.debug(f"Secret OK: {spec.name}")

    ok = len(missing_required) == 0 and len(too_short) == 0
    result = SecretValidationResult(
        ok=ok,
        missing_required=missing_required,
        too_short=too_short,
        present_optional=present_optional,
        missing_optional=missing_optional,
    )

    if ok:
        logger.info("Secret validation passed", summary=result.summary())
    else:
        logger.error("Secret validation FAILED", summary=result.summary())

    return result


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Safe secret getter — never raises, never logs value."""
    val = os.getenv(name, default)
    return val if val else default
