"""
backend/api/main.py
Galaxy Vast AI Trading Platform — FastAPI Application Entry Point

Phase AB fix: restore from placeholder "MAIN_CONTENT" (12 bytes) to full application.
Phase AC fix:
  BUG-AC1: backtest double prefix removed (backtest.py no longer has prefix="/backtest")
  BUG-AC2: research added to import list and include_router at /research

All routes registered:
  auth, signals, trades, dashboard, health, admin, admin_users, admin_observability,
  analytics, risk, reports, portfolio, metrics, billing, backtest, backtest_engine,
  research, decision, intelligence, learning, self_learning, license, institutional,
  institutional_backtest, agents, ai_prediction, analysis, security_ai,
  security_ai_extended, permissions_routes, rate_limit_routes, trade_history,
  trade_report, users, websocket_routes, audit_routes_v21

BUG-AA2 fix: shutdown logger.warning (not bare pass)
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_startup_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    global _startup_time
    _startup_time = time.time()
    logger.info("[startup] Galaxy Vast AI Trading Platform starting...")

    try:
        from backend.self_learning.retraining_service import retraining_service
        await retraining_service.start()
        logger.info("[startup] RetrainingService started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[startup] RetrainingService start failed: %s", exc)

    try:
        from backend.agents.security_ai_agent import security_ai_agent
        await security_ai_agent.start()
        logger.info("[startup] SecurityAIAgent started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[startup] SecurityAIAgent start failed: %s", exc)

    logger.info("[startup] All services started — ready to serve.")
    yield

    logger.info("[shutdown] Shutting down Galaxy Vast AI Trading Platform...")

    try:
        from backend.self_learning.retraining_service import retraining_service
        retraining_service.stop()
        logger.info("[shutdown] RetrainingService stopped")
    except Exception as exc:  # noqa: BLE001 — BUG-AA2 fix: was bare pass
        logger.warning("[shutdown] RetrainingService.stop failed: %s", exc)

    try:
        from backend.agents.security_ai_agent import security_ai_agent
        await security_ai_agent.stop()
        logger.info("[shutdown] SecurityAIAgent stopped")
    except Exception as exc:  # noqa: BLE001 — BUG-AA2 fix: was bare pass
        logger.warning("[shutdown] SecurityAIAgent.stop failed: %s", exc)

    logger.info("[shutdown] Shutdown complete.")


def _create_app() -> FastAPI:
    from backend.core.config import settings

    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        description="Enterprise MT5 Trading Ecosystem — SMC + ML + Decision Engine",
        version=getattr(settings, "APP_VERSION", "3.0.0"),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    cors_origins = getattr(settings, "CORS_ORIGINS", ["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        elapsed = round((time.monotonic() - t0) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(elapsed)
        return response

    from backend.api.routes import (
        admin, admin_observability, admin_users, agents, ai_prediction,
        analysis, analytics, auth, backtest, backtest_engine, billing,
        dashboard, decision, health, institutional, institutional_backtest,
        intelligence, learning, license, metrics, permissions_routes,
        portfolio, rate_limit_routes, reports, research, risk, security_ai,
        security_ai_extended, security_ai_loader, self_learning, signals,
        trade_history, trade_report, trades, users, websocket_routes,
    )

    app.include_router(auth.router,                   prefix="/auth",                     tags=["auth"])
    app.include_router(signals.router,                prefix="/signals",                   tags=["signals"])
    app.include_router(trades.router,                 prefix="/trades",                    tags=["trades"])
    app.include_router(decision.router,               prefix="/decision",                  tags=["decision"])
    app.include_router(analysis.router,               prefix="/analysis",                  tags=["analysis"])
    app.include_router(ai_prediction.router,          prefix="/ai-prediction",             tags=["ai_prediction"])
    app.include_router(dashboard.router,              prefix="/dashboard",                 tags=["dashboard"])
    app.include_router(metrics.router,                prefix="/metrics",                   tags=["metrics"])
    app.include_router(analytics.router,              prefix="/analytics",                 tags=["analytics"])
    app.include_router(portfolio.router,              prefix="/portfolio",                 tags=["portfolio"])
    app.include_router(reports.router,                prefix="/reports",                   tags=["reports"])
    app.include_router(risk.router,                   prefix="/risk",                      tags=["risk"])
    app.include_router(health.router,                 prefix="/health",                    tags=["health"])
    app.include_router(backtest.router,               prefix="/backtest",                  tags=["backtest"])
    app.include_router(backtest_engine.router,        prefix="/backtest-engine",           tags=["backtest_engine"])
    app.include_router(research.router,               prefix="/research",                  tags=["research"])
    app.include_router(intelligence.router,           prefix="/intelligence",              tags=["intelligence"])
    app.include_router(learning.router,               prefix="/learning",                  tags=["learning"])
    app.include_router(self_learning.router,          prefix="/self-learning",             tags=["self_learning"])
    app.include_router(institutional.router,          prefix="/institutional",             tags=["institutional"])
    app.include_router(institutional_backtest.router, prefix="/institutional-backtest",    tags=["institutional_backtest"])
    app.include_router(agents.router,                 prefix="/agents",                    tags=["agents"])
    app.include_router(security_ai.router,            prefix="/security-ai",               tags=["security_ai"])
    app.include_router(security_ai_extended.router,   prefix="/security-ai-ext",           tags=["security_ai_extended"])
    app.include_router(security_ai_loader.router,     prefix="/security-ai-loader",        tags=["security_ai_loader"])
    app.include_router(billing.router,                prefix="/billing",                   tags=["billing"])
    app.include_router(license.router,                prefix="/license",                   tags=["license"])
    app.include_router(users.router,                  prefix="/users",                     tags=["users"])
    app.include_router(admin.router,                  prefix="/admin",                     tags=["admin"])
    app.include_router(admin_users.router,            prefix="/admin",                     tags=["admin_users"])
    app.include_router(admin_observability.router,    prefix="/admin",                     tags=["admin_observability"])
    app.include_router(permissions_routes.router,     prefix="/permissions",               tags=["permissions"])
    app.include_router(rate_limit_routes.router,      prefix="/rate-limit",                tags=["rate_limit"])
    app.include_router(trade_history.router,          prefix="/trade-history",             tags=["trade_history"])
    app.include_router(trade_report.router,           prefix="/trade-report",              tags=["trade_report"])
    app.include_router(websocket_routes.router,       prefix="/ws",                        tags=["websocket"])

    try:
        from backend.api.routes import audit_routes_v21
        if audit_routes_v21.router is not None:
            app.include_router(audit_routes_v21.router, prefix="/admin/audit", tags=["audit"])
            logger.info("[startup] AuditRouteV21 registered at /admin/audit")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[startup] audit_routes_v21 not loaded: %s", exc)

    @app.get("/", include_in_schema=False)
    async def root() -> Dict[str, Any]:
        return {
            "service": "Galaxy Vast AI Trading Platform",
            "status": "running",
            "uptime_seconds": round(time.time() - _startup_time),
            "docs": "/docs",
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("[global] Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": str(request.url.path)},
        )

    return app


app = _create_app()
