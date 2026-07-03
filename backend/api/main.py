"""
backend/api/main.py
Galaxy Vast AI - FastAPI Application Entry Point

Creates the app, registers middleware, routers, and lifecycle hooks.
"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Galaxy Vast AI starting...")
    try:
        from backend.database.connection import get_db_client
        app.state.db = await get_db_client()
        logger.info("Database connected")
    except Exception as exc:
        logger.warning("DB connection failed (non-fatal in dev): %s", exc)
    yield
    logger.info("Galaxy Vast AI shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title       = "Galaxy Vast AI Trading Platform",
        description = "Enterprise MT5 Trading Ecosystem",
        version     = "12.0.0",
        lifespan    = lifespan,
        docs_url    = "/api/docs",
        redoc_url   = "/api/redoc",
        openapi_url = "/api/openapi.json",
    )
    try:
        from backend.core.config import get_settings
        origins = getattr(get_settings(), "ALLOWED_ORIGINS", ["*"])
    except Exception:
        origins = ["*"]

    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    try:
        from backend.middleware.security_headers import SecurityHeadersMiddleware
        app.add_middleware(SecurityHeadersMiddleware)
    except Exception as exc:
        logger.warning("SecurityHeadersMiddleware skipped: %s", exc)

    _register_routers(app)

    @app.exception_handler(Exception)
    async def _global_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled: %s %s - %s", request.method, request.url, exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


def _register_routers(app: FastAPI) -> None:
    import importlib
    for module_path, prefix in [
        ("backend.api.routes.auth",     "/api/v1"),
        ("backend.api.routes.trades",   "/api/v1"),
        ("backend.api.routes.signals",  "/api/v1"),
        ("backend.api.routes.risk",     "/api/v1"),
        ("backend.api.routes.analytics","/api/v1"),
        ("backend.api.routes.admin",    "/api/v1"),
        ("backend.api.routes.dashboard","/api/v1"),
        ("backend.api.routes.decision", "/api/v1"),
        ("backend.api.routes.analysis", "/api/v1"),
        ("backend.license.routes",      "/api/v1"),
        ("backend.api.health",          ""),
    ]:
        try:
            mod = importlib.import_module(module_path)
            if (router := getattr(mod, "router", None)) is not None:
                app.include_router(router, prefix=prefix)
        except Exception as exc:
            logger.warning("Router %s skipped: %s", module_path, exc)


app = create_app()
