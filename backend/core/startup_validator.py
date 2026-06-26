"""
backend/core/startup_validator.py
PHASE 2 — Production Startup Safety

validate_startup_config(environment) — central validation before startup.

Rules:
  RULE-01  JWT_SECRET_KEY must not be weak/default
  RULE-02  DATABASE_URL or SUPABASE_URL required
  RULE-03  SUPABASE_SERVICE_KEY required in production
  RULE-04  REDIS_URL must be valid scheme
  RULE-05  CORS wildcard blocked in production/staging
  RULE-06  DEBUG=True blocked in production
  RULE-07  MT5 credentials required for live trading (fail-closed)
  RULE-08  TELEGRAM_BOT_TOKEN recommended in production
  RULE-09  JWT_ALGORITHM allowlist
  RULE-10  ACCESS_TOKEN_EXPIRE_MINUTES cap
  RULE-11  BCRYPT_ROUNDS minimum 12 in production
  RULE-12  SENTRY_DSN recommended in production
  RULE-13  MT5_LOGIN must be positive integer
  RULE-14  SUPABASE_KEY placeholder detection
  RULE-15  SystemExit(1) on errors in production
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

log = logging.getLogger("startup_validator")

_DANGEROUS_SECRETS = {
    "changeme", "secret", "password", "test", "dev",
    "your-secret-key", "jwt-secret", "replace-me", "example",
    "demo", "sample", "placeholder", "none", "null", "true", "false",
}
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512"}
_VALID_DB_SCHEMES   = ("postgresql://", "postgres://", "postgresql+asyncpg://",
                       "postgresql+psycopg2://", "sqlite://")
_VALID_REDIS_SCHEME = ("redis://", "rediss://", "unix://")
_ENV_NAMES = {"development", "staging", "production"}


class Severity(str, Enum):
    INFO    = "INFO"
    WARNING = "WARNING"
    ERROR   = "ERROR"


@dataclass
class ValidationIssue:
    rule:     str
    severity: Severity
    message:  str
    hint:     str = ""


@dataclass
class StartupValidationResult:
    environment: str
    issues:      List[ValidationIssue] = field(default_factory=list)
    live_trading_ready: bool = False

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def _add(self, rule: str, sev: Severity, msg: str, hint: str = "") -> None:
        self.issues.append(ValidationIssue(rule=rule, severity=sev, message=msg, hint=hint))

    def error(self, rule: str, msg: str, hint: str = "") -> None:
        self._add(rule, Severity.ERROR, msg, hint)

    def warning(self, rule: str, msg: str, hint: str = "") -> None:
        self._add(rule, Severity.WARNING, msg, hint)

    def info(self, rule: str, msg: str) -> None:
        self._add(rule, Severity.INFO, msg)

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  STARTUP VALIDATION — {self.environment.upper()}",
            f"{'='*60}",
        ]
        for issue in self.issues:
            icon = {"INFO": "i ", "WARNING": "W ", "ERROR": "E "}[issue.severity.value]
            lines.append(f"  {icon} [{issue.rule}] {issue.message}")
            if issue.hint:
                lines.append(f"       > {issue.hint}")
        lines.append(f"{'='*60}")
        if self.ok:
            lines.append(f"  PASSED — {self.environment} ready to start")
            if self.live_trading_ready:
                lines.append("  LIVE TRADING — MT5 credentials verified")
            else:
                lines.append("  WARNING: LIVE TRADING not ready (MT5 credentials missing)")
        else:
            lines.append(f"  FAILED — {len(self.errors)} error(s) must be fixed before startup")
        lines.append(f"{'='*60}")
        return "\n".join(lines)


def validate_startup_config(
    environment: Optional[str] = None,
    *,
    settings=None,
    abort_on_error: bool = True,
) -> StartupValidationResult:
    """
    Central startup validation function.

    Args:
        environment: "development" | "staging" | "production"
        settings:    Settings instance; if None, get_settings() is called
        abort_on_error: if True and production and errors exist -> SystemExit(1)

    Returns:
        StartupValidationResult
    """
    if environment is None:
        environment = (
            os.environ.get("APP_ENV")
            or os.environ.get("ENVIRONMENT")
            or os.environ.get("FASTAPI_ENV")
            or "development"
        ).lower()

    if environment not in _ENV_NAMES:
        environment = "development"

    is_prod    = environment == "production"
    is_staging = environment == "staging"
    is_dev     = environment == "development"

    if settings is None:
        try:
            from .config import get_settings
            settings = get_settings()
        except Exception as exc:
            result = StartupValidationResult(environment=environment)
            result.error(
                "RULE-00", f"Cannot load Settings: {exc}",
                hint="Check .env file and environment variables"
            )
            _finalize(result, abort_on_error=abort_on_error and is_prod)
            return result

    result = StartupValidationResult(environment=environment)
    result.info("RULE-00", f"Environment detected: {environment}")

    # RULE-01: JWT_SECRET_KEY
    jwt_secret = getattr(settings, "JWT_SECRET_KEY", "")
    if not jwt_secret or jwt_secret.lower() in _DANGEROUS_SECRETS:
        msg = f"JWT_SECRET_KEY is weak/default: {jwt_secret!r}"
        hint = "Run: python -c \"import secrets; print(secrets.token_hex(32))\""
        if is_prod or is_staging:
            result.error("RULE-01", msg, hint)
        else:
            result.warning("RULE-01", msg, hint)
    elif len(jwt_secret) < 32:
        msg = f"JWT_SECRET_KEY too short ({len(jwt_secret)} chars, min 32)"
        hint = "Use a 64-char random hex string"
        if is_prod or is_staging:
            result.error("RULE-01", msg, hint)
        else:
            result.warning("RULE-01", msg, hint)
    else:
        result.info("RULE-01", "JWT_SECRET_KEY OK")

    # RULE-02: Database
    db_url       = getattr(settings, "DATABASE_URL", "") or ""
    supabase_url = getattr(settings, "SUPABASE_URL", "") or ""
    if not db_url and not supabase_url:
        result.error(
            "RULE-02", "Neither DATABASE_URL nor SUPABASE_URL is configured",
            hint="Set DATABASE_URL=postgresql://... or SUPABASE_URL=https://..."
        )
    elif db_url and not any(db_url.startswith(s) for s in _VALID_DB_SCHEMES):
        result.error(
            "RULE-02", f"DATABASE_URL has unsupported scheme: {db_url[:40]}",
            hint=f"Must start with one of: {', '.join(_VALID_DB_SCHEMES)}"
        )
    else:
        result.info("RULE-02", "Database URL OK")

    # RULE-03: SUPABASE_SERVICE_KEY in production
    supabase_service_key = getattr(settings, "SUPABASE_SERVICE_KEY", "") or ""
    if is_prod and supabase_url:
        if not supabase_service_key or supabase_service_key.lower() in _DANGEROUS_SECRETS:
            result.error(
                "RULE-03", "SUPABASE_SERVICE_KEY is missing/weak in production",
                hint="Set SUPABASE_SERVICE_KEY from Supabase dashboard -> Settings -> API"
            )
        else:
            result.info("RULE-03", "SUPABASE_SERVICE_KEY OK")

    # RULE-04: Redis
    redis_url = getattr(settings, "REDIS_URL", "") or ""
    if redis_url and not any(redis_url.startswith(s) for s in _VALID_REDIS_SCHEME):
        result.error(
            "RULE-04", f"REDIS_URL has invalid scheme: {redis_url[:40]}",
            hint="Must start with redis:// or rediss://"
        )
    elif not redis_url and is_prod:
        result.warning("RULE-04", "REDIS_URL not set — caching/rate-limiting disabled")
    else:
        result.info("RULE-04", "Redis URL OK")

    # RULE-05: CORS wildcard
    allowed_origins = getattr(settings, "ALLOWED_ORIGINS", []) or []
    if "*" in allowed_origins or ["*"] == allowed_origins:
        msg  = "ALLOWED_ORIGINS='*' is a security risk"
        hint = "Set ALLOWED_ORIGINS=https://yourdomain.com"
        if is_prod or is_staging:
            result.error("RULE-05", msg, hint)
        else:
            result.warning("RULE-05", msg, hint)
    else:
        result.info("RULE-05", f"CORS origins OK: {allowed_origins}")

    # RULE-06: DEBUG in production
    debug = getattr(settings, "DEBUG", False)
    if debug and (is_prod or is_staging):
        result.error(
            "RULE-06", "DEBUG=True is not allowed in production/staging",
            hint="Set DEBUG=False"
        )
    else:
        result.info("RULE-06", f"DEBUG={debug} OK for {environment}")

    # RULE-07 + RULE-13: MT5 credentials
    mt5_login    = getattr(settings, "MT5_LOGIN", None)
    mt5_password = getattr(settings, "MT5_PASSWORD", None)
    mt5_server   = getattr(settings, "MT5_SERVER", None)
    mt5_all_set  = all([mt5_login, mt5_password, mt5_server])

    if is_prod and not mt5_all_set:
        missing = [
            name for name, val in [
                ("MT5_LOGIN", mt5_login),
                ("MT5_PASSWORD", mt5_password),
                ("MT5_SERVER", mt5_server),
            ] if not val
        ]
        result.error(
            "RULE-07",
            f"Live trading requires MT5 credentials. Missing: {', '.join(missing)}",
            hint="Set MT5_LOGIN=<account> MT5_PASSWORD=<pass> MT5_SERVER=<broker>"
        )
    elif mt5_all_set:
        try:
            login_int = int(mt5_login)
            if login_int <= 0:
                raise ValueError("non-positive")
            result.info("RULE-07", f"MT5 credentials configured (login={login_int})")
            result.info("RULE-13", "MT5_LOGIN is valid positive integer")
            result.live_trading_ready = True
        except (ValueError, TypeError):
            result.error(
                "RULE-13", f"MT5_LOGIN must be a positive integer, got: {mt5_login!r}",
                hint="Set MT5_LOGIN=<numeric_account_number>"
            )
    else:
        result.warning(
            "RULE-07", "MT5 credentials not set — live trading will be disabled",
            hint="Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER to enable live trading"
        )

    # RULE-08: Telegram
    tg_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if is_prod and not tg_token:
        result.warning(
            "RULE-08", "TELEGRAM_BOT_TOKEN not set — trade alerts disabled",
            hint="Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID for real-time alerts"
        )

    # RULE-09: JWT_ALGORITHM
    jwt_algo = getattr(settings, "JWT_ALGORITHM", "HS256")
    if jwt_algo not in _ALLOWED_ALGORITHMS:
        result.error(
            "RULE-09", f"JWT_ALGORITHM={jwt_algo!r} is not supported",
            hint=f"Use one of: {', '.join(sorted(_ALLOWED_ALGORITHMS))}"
        )
    else:
        result.info("RULE-09", f"JWT_ALGORITHM={jwt_algo} OK")

    # RULE-10: ACCESS_TOKEN_EXPIRE_MINUTES
    token_expire = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    if is_prod and token_expire > 480:
        result.warning(
            "RULE-10",
            f"ACCESS_TOKEN_EXPIRE_MINUTES={token_expire} is very long for production",
            hint="Recommend 60-480 minutes for production"
        )
    else:
        result.info("RULE-10", f"ACCESS_TOKEN_EXPIRE_MINUTES={token_expire} OK")

    # RULE-11: BCRYPT_ROUNDS
    bcrypt_rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
    if is_prod and bcrypt_rounds < 12:
        result.error(
            "RULE-11", f"BCRYPT_ROUNDS={bcrypt_rounds} too low for production (min 12)",
            hint="Set BCRYPT_ROUNDS=12 or higher"
        )
    elif is_dev and bcrypt_rounds > 10:
        result.warning(
            "RULE-11",
            f"BCRYPT_ROUNDS={bcrypt_rounds} will slow tests in development",
            hint="Set BCRYPT_ROUNDS=4 for faster development"
        )
    else:
        result.info("RULE-11", f"BCRYPT_ROUNDS={bcrypt_rounds} OK")

    # RULE-12: SENTRY_DSN
    sentry_dsn = getattr(settings, "SENTRY_DSN", None) or os.environ.get("SENTRY_DSN")
    if is_prod and not sentry_dsn:
        result.warning(
            "RULE-12", "SENTRY_DSN not configured — production errors untracked",
            hint="Set SENTRY_DSN=https://... for production error monitoring"
        )

    # RULE-14: SUPABASE_KEY placeholder
    supabase_key = getattr(settings, "SUPABASE_KEY", "") or ""
    if supabase_url and (
        not supabase_key
        or supabase_key.lower() in _DANGEROUS_SECRETS
        or supabase_key.startswith("your-")
    ):
        hint = "Get from Supabase dashboard -> Settings -> API -> anon public key"
        if is_prod:
            result.error("RULE-14", "SUPABASE_KEY is missing or placeholder", hint)
        else:
            result.warning("RULE-14", "SUPABASE_KEY is missing or placeholder", hint)

    for issue in result.issues:
        if issue.severity == Severity.ERROR:
            log.error("[STARTUP] [%s] %s", issue.rule, issue.message)
        elif issue.severity == Severity.WARNING:
            log.warning("[STARTUP] [%s] %s", issue.rule, issue.message)
        else:
            log.debug("[STARTUP] [%s] %s", issue.rule, issue.message)

    _finalize(result, abort_on_error=abort_on_error and is_prod)
    return result


def _finalize(result: StartupValidationResult, *, abort_on_error: bool) -> None:
    if result.errors and abort_on_error:
        print(result.summary(), file=sys.stderr)
        log.critical(
            "[STARTUP] %d critical error(s) — aborting startup in %s",
            len(result.errors), result.environment
        )
        sys.exit(1)


def validate_mt5_credentials(
    login: Optional[int] = None,
    password: Optional[str] = None,
    server: Optional[str] = None,
    *,
    settings=None,
) -> bool:
    """
    Fail-closed MT5 credentials check.
    Returns False if any credential is missing or invalid.
    Called by ExecutionService.initialize() before connecting to broker.
    """
    if settings is not None:
        login    = login    or getattr(settings, "MT5_LOGIN", None)
        password = password or getattr(settings, "MT5_PASSWORD", None)
        server   = server   or getattr(settings, "MT5_SERVER", None)

    if not login or not password or not server:
        log.error(
            "[MT5] Live trading fail-closed: missing credentials "
            "(login=%s, password=%s, server=%s)",
            bool(login), bool(password), bool(server)
        )
        return False

    try:
        login_int = int(login)
        if login_int <= 0:
            raise ValueError("non-positive")
    except (ValueError, TypeError):
        log.error("[MT5] MT5_LOGIN must be a positive integer, got: %r", login)
        return False

    if len(str(password)) < 4:
        log.error("[MT5] MT5_PASSWORD is suspiciously short")
        return False

    if not str(server).strip():
        log.error("[MT5] MT5_SERVER is empty")
        return False

    log.debug("[MT5] Credentials validated (login=%d, server=%s)", login_int, server)
    return True
