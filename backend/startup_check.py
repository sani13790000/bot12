"""
backend/startup_check.py — FIXED
CB-8 FIX: Now actually called at startup via lifespan() in main.py
Previously existed but was never called anywhere.

Runs pre-flight checks before the server accepts traffic:
  1. Config validation (JWT secret, required vars)
  2. Database connectivity
  3. MT5 gateway reachability (non-fatal in dev/demo)
  4. Redis connectivity (non-fatal)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Tuple

logger = logging.getLogger(__name__)

CheckResult = Tuple[str, bool, str]  # (name, passed, detail)


async def _check_config() -> CheckResult:
    """Validate critical config values."""
    try:
        from backend.core.config import get_settings
        s = get_settings()
        issues = []
        if not s.SUPABASE_URL and not s.DATABASE_URL:
            issues.append("Neither SUPABASE_URL nor DATABASE_URL is set")
        if not s.TELEGRAM_BOT_TOKEN:
            issues.append("TELEGRAM_BOT_TOKEN not set — bot will not function")
        mt5_gateway = os.environ.get("MT5_GATEWAY_URL", s.MT5_GATEWAY_URL)
        if mt5_gateway == "http://localhost:8080":
            issues.append(
                "MT5_GATEWAY_URL is default (localhost:8080) — set correct gateway URL in production"
            )
        if issues:
            return ("config", False, "; ".join(issues))
        return ("config", True, f"env={s.APP_ENV} version={s.APP_VERSION}")
    except Exception as exc:
        return ("config", False, str(exc))


async def _check_database() -> CheckResult:
    """Check database connectivity."""
    try:
        from backend.database.connection import get_db_client
        client = await asyncio.wait_for(get_db_client(), timeout=5.0)
        if client:
            return ("database", True, "connected")
        return ("database", False, "client returned None")
    except Exception as exc:
        return ("database", False, str(exc))


async def _check_mt5_gateway() -> CheckResult:
    """Check MT5 gateway reachability (non-fatal in demo mode)."""
    demo_mode = os.environ.get("MT5_DEMO_MODE", "true").lower() not in ("false", "0", "no", "off")
    if demo_mode:
        return ("mt5_gateway", True, "DEMO mode — gateway check skipped")
    try:
        from backend.execution.mt5_connector import mt5_connector
        result = await asyncio.wait_for(mt5_connector.health_check(), timeout=5.0)
        ok = result.get("ok", False) if isinstance(result, dict) else bool(result)
        if ok:
            return ("mt5_gateway", True, f"ping_ms={result.get('ping_ms', '?')}")
        return ("mt5_gateway", False, f"gateway unhealthy: {result}")
    except Exception as exc:
        return ("mt5_gateway", False, str(exc))


async def _check_redis() -> CheckResult:
    """Check Redis connectivity (non-fatal)."""
    try:
        from backend.database.redis_client import get_redis
        r = await asyncio.wait_for(get_redis(), timeout=3.0)
        await r.ping()
        return ("redis", True, "connected")
    except Exception as exc:
        return ("redis", False, f"{exc} (non-fatal — in-memory fallback will be used)")


async def run_startup_checks() -> None:
    """
    Run all pre-flight checks.
    Raises RuntimeError in production if any CRITICAL check fails.
    Logs warnings for non-critical failures.
    """
    from backend.core.config import get_settings
    s = get_settings()
    is_prod = s.APP_ENV == "production"

    results: List[CheckResult] = await asyncio.gather(
        _check_config(),
        _check_database(),
        _check_mt5_gateway(),
        _check_redis(),
        return_exceptions=False,
    )

    critical_checks = {"config", "database"} if is_prod else {"config"}

    failures = []
    for name, passed, detail in results:
        if passed:
            logger.info("[startup] ✅ %s: %s", name, detail)
        else:
            if name in critical_checks:
                logger.error("[startup] ❌ CRITICAL %s: %s", name, detail)
                failures.append(f"{name}: {detail}")
            else:
                logger.warning("[startup] ⚠️  %s: %s", name, detail)

    if failures:
        raise RuntimeError(
            f"Critical startup checks failed: {'; '.join(failures)}"
        )
