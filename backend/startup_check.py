"""backend/startup_check.py v3 - Phase C

Additions:
  - Check SECRETS_MASTER_KEY and FIELD_ENCRYPTION_KEY in production
  - Check LICENSE_SECRET in production
  - None-guard before redis.ping() (BUG-R5-3 fix retained)
  - All checks return (name, ok, msg) tuples
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

CheckResult = Tuple[str, bool, str]


async def _check_redis() -> CheckResult:
    try:
        from backend.database.redis_client import get_redis

        r = await asyncio.wait_for(get_redis(), timeout=3.0)
        if r is None:  # BUG-R5-3 fix: None guard
            return ("redis", False, "could not connect")
        await r.ping()
        return ("redis", True, "connected")
    except asyncio.TimeoutError:
        return ("redis", False, "timeout")
    except Exception as exc:
        return ("redis", False, str(exc)[:80])


async def _check_supabase() -> CheckResult:
    try:
        from backend.database.connection import get_db_client

        client = await asyncio.wait_for(get_db_client(), timeout=5.0)
        if client is None:
            return ("supabase", False, "client is None")
        return ("supabase", True, "connected")
    except asyncio.TimeoutError:
        return ("supabase", False, "timeout")
    except Exception as exc:
        return ("supabase", False, str(exc)[:80])


async def _check_mt5_gateway() -> CheckResult:
    try:
        import aiohttp

        from backend.core.config import get_settings

        s = get_settings()
        url = getattr(s, "MT5_GATEWAY_URL", "http://localhost:8080")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/ping", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status < 400:
                    return ("mt5_gateway", True, f"HTTP {resp.status}")
                return ("mt5_gateway", False, f"HTTP {resp.status}")
    except Exception as exc:
        return ("mt5_gateway", False, str(exc)[:80])


async def _check_secrets() -> CheckResult:
    """Phase C: Validate critical secrets are set in production."""
    try:
        from backend.core.config import get_settings, is_production

        if not is_production():
            return ("secrets", True, "skipped (not production)")
        s = get_settings()
        missing = []
        if not getattr(s, "SECRETS_MASTER_KEY", ""):
            missing.append("SECRETS_MASTER_KEY")
        if not getattr(s, "FIELD_ENCRYPTION_KEY", ""):
            missing.append("FIELD_ENCRYPTION_KEY")
        if not getattr(s, "LICENSE_SECRET", ""):
            missing.append("LICENSE_SECRET")
        if missing:
            return ("secrets", False, f"missing: {', '.join(missing)}")
        return ("secrets", True, "all critical secrets set")
    except Exception as exc:
        return ("secrets", False, str(exc)[:80])


async def _check_jwt_secret() -> CheckResult:
    """Phase C: Warn if JWT_SECRET_KEY is weak/default."""
    try:
        from backend.core.config import get_settings

        s = get_settings()
        key = getattr(s, "JWT_SECRET_KEY", "")
        weak = {"changeme", "secret", "password", "test", "dev", "replace-me"}
        if key.lower() in weak:
            return ("jwt_secret", False, "weak/default value - set a strong secret")
        if len(key) < 32:
            return ("jwt_secret", False, f"too short ({len(key)} chars, min 32)")
        return ("jwt_secret", True, "ok")
    except Exception as exc:
        return ("jwt_secret", False, str(exc)[:80])


async def run_startup_checks() -> None:
    """Run all pre-flight checks concurrently and log results."""
    results: List[CheckResult] = await asyncio.gather(
        _check_redis(),
        _check_supabase(),
        _check_mt5_gateway(),
        _check_secrets(),
        _check_jwt_secret(),
        return_exceptions=False,
    )

    all_ok = True
    for name, ok, msg in results:
        level = logging.INFO if ok else logging.WARNING
        status = "OK" if ok else "WARN"
        logger.log(level, "[StartupCheck] %-20s %s  %s", name, status, msg)
        if not ok:
            all_ok = False

    if all_ok:
        logger.info("[StartupCheck] All checks passed")
    else:
        logger.warning(
            "[StartupCheck] Some checks failed — system will attempt to start anyway. "
            "Check logs above for details."
        )
