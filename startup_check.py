"""startup_check.py v2 (Phase R)
R-11: asyncio.run() not get_event_loop()
R-12: exit(1) on real errors
R-13: timeout on DB probe
R-14: required env var validation
R-15: Redis check non-fatal
"""
from __future__ import annotations
import asyncio, logging, os, sys
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("startup")
_TIMEOUT_S = 10.0

async def _check_env() -> list[str]:
    required = ["SUPABASE_URL", "SUPABASE_KEY", "JWT_SECRET_KEY", "SUPABASE_JWT_SECRET"]
    optional_warn = ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "TELEGRAM_BOT_TOKEN", "REDIS_URL"]
    errors: list[str] = []
    for key in required:
        if not os.getenv(key):
            errors.append(f"MISSING required: {key}")
    for key in optional_warn:
        if not os.getenv(key):
            log.warning("Optional not set: %s", key)
    return errors

async def _check_db() -> bool:
    try:
        from backend.database.connection import get_db_client
        async with asyncio.timeout(_TIMEOUT_S):  # R-13
            client = await get_db_client()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: client.table("signals").select("id").limit(1).execute())
        log.info("Database: OK")
        return True
    except TimeoutError:
        log.error("Database: timeout after %.0fs", _TIMEOUT_S)
        return False
    except Exception as exc:
        log.error("Database: %s", exc)
        return False

async def _check_redis() -> bool:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        import redis.asyncio as aioredis
        async with asyncio.timeout(5.0):
            r = aioredis.from_url(redis_url, socket_connect_timeout=3)
            await r.ping()
            await r.aclose()
        log.info("Redis: OK")
        return True
    except ImportError:
        log.warning("redis-py not installed")
        return True  # R-15: non-fatal
    except Exception as exc:
        log.warning("Redis unavailable: %s - rate limiting disabled", exc)
        return True  # R-15: non-fatal

async def _check_settings() -> bool:
    try:
        from backend.core.config import get_settings
        s = get_settings()
        log.info("Settings: OK env=%s", s.ENVIRONMENT)
        return True
    except Exception as exc:
        log.error("Settings: %s", exc)
        return False

async def main() -> int:
    log.info("Galaxy Vast - Startup Check")
    errors: list[str] = []
    env_errors = await _check_env()  # R-14
    if env_errors:
        for e in env_errors:
            log.error("%s", e)
        errors.extend(env_errors)
    if not await _check_settings():
        errors.append("Settings failed")
    if not await _check_db():
        errors.append("Database unreachable")
    await _check_redis()
    if errors:
        log.error("Startup FAILED - %d error(s)", len(errors))
        return 1  # R-12
    log.info("Startup OK")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))  # R-11
