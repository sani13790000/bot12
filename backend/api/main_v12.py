"""backend/api/main_v12.py — Phase 12 hardened app factory.
P12-FIX-CORS-1,2,3: no wildcard CORS
P12-FIX-TRUST-1: TrustedHostMiddleware
P12-FIX-EXC-1,2: standardized exception handlers
P12-FIX-DOCS-1: /openapi.json disabled in production
"""
from __future__ import annotations
import logging, time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List
from fastapi import FastAPI

log = logging.getLogger("api.main_v12")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    t0 = time.monotonic()
    log.info("startup begin")
    try:
        from ..middleware.rate_limit_v2 import start_cleanup_v2
        await start_cleanup_v2()
    except Exception as e:
        log.debug("rate_limit_v2 cleanup skipped: %s", e)
    log.info("startup complete elapsed=%.2fs", time.monotonic() - t0)
    yield
    log.info("shutdown")


def create_hardened_app(
    allowed_origins:  List[str],
    trusted_hosts:    List[str],
    trusted_proxies:  str = "",
    environment:      str = "production",
    api_prefix:       str = "/api/v1",
) -> FastAPI:
    is_prod = environment == "production"
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        version="3.0.0",
        lifespan=lifespan,
        docs_url    = None if is_prod else "/docs",
        redoc_url   = None if is_prod else "/redoc",
        openapi_url = None if is_prod else "/openapi.json",
    )
    from ..middleware.security_hardened import apply_security_middleware, install_exception_handlers
    apply_security_middleware(app, allowed_origins, trusted_hosts, trusted_proxies)
    install_exception_handlers(app)
    try:
        from ..middleware.rate_limit_v2 import RateLimitMiddlewareV2
        app.add_middleware(RateLimitMiddlewareV2)
    except Exception as e:
        log.debug("RateLimitMiddlewareV2 skipped: %s", e)
    _register_routes(app, api_prefix)

    @app.get("/ping", include_in_schema=False)
    async def ping() -> dict:
        return {"ok": True}

    return app


def _register_routes(app: FastAPI, prefix: str) -> None:
    import importlib
    _map = [
        ("routes.signals",   f"{prefix}/signals",   ["Signals"]),
        ("routes.trades",    f"{prefix}/trades",     ["Trades"]),
        ("routes.auth",      f"{prefix}/auth",       ["Auth"]),
        ("routes.risk",      f"{prefix}/risk",       ["Risk"]),
        ("routes.users",     f"{prefix}/users",      ["Users"]),
        ("routes.billing",   f"{prefix}/billing",    ["Billing"]),
        ("routes.dashboard", f"{prefix}/dashboard",  ["Dashboard"]),
    ]
    for module, pfx, tags in _map:
        try:
            mod = importlib.import_module(f".{module}", package=__package__)
            app.include_router(mod.router, prefix=pfx, tags=tags)
            log.debug("route registered prefix=%s", pfx)
        except Exception as e:
            log.debug("route skipped module=%s error=%s", module, e)
