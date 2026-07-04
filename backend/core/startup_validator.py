"""
backend/core/startup_validator.py
Galaxy Vast AI Trading Platform -- Startup Environment Validator

faz I:
  I-13: qabl az startup hame env vars ejbari ra barrasi mi-konad
  I-14: maghadir zaeif (Masalan "change-me") ra rad mi-konad
  I-15: gzaresh kamel az vaziat configuration

faz R:
  R-FIX-1: OPTIONAL_VARS ta'rif nashode bud -> NameError dar runtime
  R-FIX-2: GATEWAY_API_KEY be OPTIONAL_VARS ezafe shod
  R-FIX-3: MT5_DEMO_MODE warning faqat dar production bud ->
           hala dar hame envha log mishavad
  R-FIX-4: corruption dar L58-75 (binary garbage) -> pak shod
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class EnvVar:
    name: str
    required: bool = True
    min_length: int = 1
    forbidden_values: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    sensitive: bool = False

    def validate(self) -> Optional[str]:
        value = os.environ.get(self.name, "")
        if not value:
            if self.required:
                return f"MISSING: {self.name} -- {self.description}"
            return None
        if len(value) < self.min_length:
            return (
                f"TOO SHORT: {self.name} -- "
                f"min {self.min_length} chars (got {len(value)})"
            )
        for bad in self.forbidden_values:
            if value.lower() == bad.lower():
                return f"INSECURE VALUE: {self.name} = '{value}' -- change this!"
        return None

    def status(self) -> str:
        value = os.environ.get(self.name, "")
        if not value:
            prefix = "OPTIONAL" if not self.required else "MISSING"
            return f"  {prefix}: {self.name}: NOT SET"
        display = "[SET]" if self.sensitive else f"'{value[:20]}{'...' if len(value) > 20 else ''}'"
        return f"  OK: {self.name}: {display}"


REQUIRED_VARS: list[EnvVar] = [
    EnvVar(
        "JWT_SECRET", required=True, min_length=32,
        forbidden_values=("change-me-in-production", "secret", "changeme", "jwt_secret"),
        description="JWT secret key -- min 32 chars",
        sensitive=True,
    ),
    EnvVar(
        "LICENSE_SECRET", required=True, min_length=32,
        forbidden_values=("change-me-in-production", "secret", "changeme"),
        description="License HMAC secret -- min 32 chars",
        sensitive=True,
    ),
    EnvVar(
        "SUPABASE_URL", required=True, min_length=10,
        description="Supabase project URL",
    ),
    EnvVar(
        "SUPABASE_KEY", required=True, min_length=20,
        forbidden_values=("your-supabase-anon-key", "changeme"),
        description="Supabase anon/service key",
        sensitive=True,
    ),
    EnvVar(
        "TELEGRAM_BOT_TOKEN", required=True, min_length=20,
        forbidden_values=("CHANGE_ME_bot_token", "changeme"),
        description="Telegram Bot API token",
        sensitive=True,
    ),
]

# R-FIX-1: OPTIONAL_VARS was undefined -> NameError at runtime on L85
# R-FIX-2: GATEWAY_API_KEY added so startup warns if gateway runs without auth
OPTIONAL_VARS: list[EnvVar] = [
    EnvVar("GATEWAY_API_KEY", required=False, min_length=16,
           description="MT5 Gateway API key -- if empty, gateway runs without auth (dev only)",
           sensitive=True),
    EnvVar("MT5_GATEWAY_URL", required=False,
           description="MT5 Gateway base URL"),
    EnvVar("MT5_DEMO_MODE", required=False,
           description="MT5 demo mode: 'false' for live trading, 'true' for demo/CI"),
    EnvVar("CORS_ORIGINS", required=False,
           description="Comma-separated allowed CORS origins"),
    EnvVar("ADMIN_IP_ALLOWLIST", required=False,
           description="Comma-separated admin IPs"),
    EnvVar("SENTRY_DSN", required=False,
           description="Sentry DSN for error tracking"),
    EnvVar("REDIS_URL", required=False,
           description="Redis URL for rate limiting"),
    EnvVar("BCRYPT_ROUNDS", required=False,
           description="bcrypt work factor (default 12)"),
    EnvVar("JWT_EXPIRE_MINUTES", required=False,
           description="JWT expiry in minutes"),
]


def validate_environment(strict: bool = True) -> bool:
    errors: list[str] = []
    warnings: list[str] = []

    log.info("======== Startup Environment Validation ========")
    log.info("Required variables:")
    for var in REQUIRED_VARS:
        error = var.validate()
        if error:
            errors.append(error)
            log.error(error)
        else:
            log.info(var.status())

    log.info("Optional variables:")
    for var in OPTIONAL_VARS:
        error = var.validate()
        if error and var.required:
            errors.append(error)
            log.error(error)
        else:
            log.info(var.status())

    # R-FIX-3: MT5_DEMO_MODE warning in ALL envs, not just production
    _check_demo_and_security(errors, warnings)

    env = os.environ.get("APP_ENV", "development").lower()
    if env == "production":
        _check_production_specifics(errors, warnings)

    if errors:
        log.critical("STARTUP BLOCKED: %d error(s)", len(errors))
        for err in errors:
            log.critical(err)
        if strict:
            sys.exit(1)
        return False

    for w in warnings:
        log.warning(w)

    log.info("Environment validation passed | env=%s", env)
    return True


def _check_demo_and_security(errors: list[str], warnings: list[str]) -> None:
    """R-FIX-3: warn about demo mode and missing gateway key in ALL environments."""
    demo_mode = os.environ.get("MT5_DEMO_MODE", "true").lower()
    if demo_mode in ("true", "1", "yes", "on", ""):
        warnings.append(
            "WARNING: MT5_DEMO_MODE=true -- no real trades will be placed. "
            "Set MT5_DEMO_MODE=false for live trading."
        )

    gateway_key = os.environ.get("GATEWAY_API_KEY", "").strip()
    if not gateway_key:
        warnings.append(
            "WARNING: GATEWAY_API_KEY is not set -- "
            "MT5 gateway will accept requests without authentication (dev mode only)."
        )


def _check_production_specifics(errors: list[str], warnings: list[str]) -> None:
    """Extra checks enforced only in APP_ENV=production."""
    if not os.environ.get("ADMIN_IP_ALLOWLIST", "").strip():
        warnings.append(
            "WARNING: ADMIN_IP_ALLOWLIST not set -- "
            "admin panel accessible from all IPs in production."
        )
    if not os.environ.get("SENTRY_DSN", "").strip():
        warnings.append(
            "WARNING: SENTRY_DSN not set -- error tracking disabled in production."
        )
    cors = os.environ.get("CORS_ORIGINS", "")
    if "*" in cors:
        errors.append(
            "CORS_ORIGINS contains '*' -- not allowed in production."
        )
    demo_mode = os.environ.get("MT5_DEMO_MODE", "true").lower()
    if demo_mode in ("true", "1", "yes", "on", ""):
        errors.append(
            "BLOCKED: MT5_DEMO_MODE=true in production -- "
            "set MT5_DEMO_MODE=false to enable live trading."
        )


if __name__ == "__main__":
    ok = validate_environment(strict=False)
    sys.exit(0 if ok else 1)
