"""
backend/api/main.py
Galaxy Vast AI Trading Platform -- FastAPI Application Entry Point

Phase AB fix: restore from placeholder "MAIN_CONTENT" (12 bytes) to full application.
Phase AC fix: BUG-AC1 backtest double prefix + BUG-AC2 research registered.
Phase AD fix: BUG-AD5 CORS wildcard default -> None + production-safe fallback.
Phase AG fix:
  BUG-AG1: websocket_routes.py no longer has prefix="/ws" -- main.py provides it
  BUG-AG2: institutional_backtest.py no longer has broken prefix
  BUG-AG3: security_ai_loader.router removed -- it has no .router attr (only function)
Phase AH fix:
  BUG-AH3: observability_routes imported + registered -- was never registered -> /observability/* -> 404
Phase AI fix:
  BUG-AI1: main.py was TRUNCATED (77 lines, 2769B) -- _create_app() incomplete, zero include_router
  BUG-AI2: analytics.py @router.get("/analytics/security/metrics") -> double path fixed in analytics.py
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
    global _startup_time
    _startup_time = time.time()
    logger.info("[startup] Galaxy Vast AI Trading Platform starting...")

    try:
        from backend.self_learning.retraining_service import retraining_service

        await retraining_service.start()
        logger.info("[startup] RetrainingService started")
    except Exception as exc:
        logger.warning("[startup] RetrainingService start failed: %s", exc)

    try:
        from backend.agents.security_ai_agent import security_ai_agent

        await security_ai_agent.start()
        logger.info("[startup] SecurityAIAgent started")
    except Exception as exc:
        logger.warning("[startup] SecurityAIAgent start failed: %s", exc)

    logger.info("[startup] All services started -- ready to serve.")
    yield

    logger.info("[shutdown] Shutting down Galaxy Vast AI Trading Platform...")

    try:
        from backend.self_learning.retraining_service import retraining_service

        retraining_service.stop()
        logger.info("[shutdown] RetrainingService stopped")
    except Exception as exc:  # BUG-AA2 fix: was bare pass
        logger.warning("[shutdown] RetrainingService.stop failed: %s", exc)

    try:
        from backend.agents.security_ai_agent import security_ai_agent

        await security_ai_agent.stop()
        logger.info("[shutdown] SecurityAIAgent stopped")
    except Exception as exc:  # BUG-AA2 fix: was bare pass
        logger.warning("[shutdown] SecurityAIAgent.stop failed: %s", exc)

    logger.info("[shutdown] Shutdown complete.")


def _create_app() -> FastAPI:
    from backend.core.config import settings

    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        description="Enterprise MT5 Trading Ecosystem with SMC Engine, Price Action, Decision Engine",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware - BUG-AD5 fix: no wildcard default in production
    cors_origins = getattr(settings, "CORS_ORIGINS", None)
    if not cors_origins:
        env = getattr(settings, "ENVIRONMENT", "development")
        if env == "production":
            logger.warning(
                "[CORS] CORS_ORIGINS not set in production -- defaulting to localhost only"
            )
            cors_origins = ["http://localhost:3000", "http://localhost:5173"]
        else:
            cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("[exception] Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": str(request.url.path)},
        )

    from backend.api import observability_routes
    from backend.api.routes import (
        admin,
        admin_observability,
        admin_users,
        agents,
        ai_prediction,
        analysis,
        analytics,
        auth,
        backtest,
        backtest_engine,
        billing,
        dashboard,
        decision,
        health,
        institutional,
        institutional_backtest,
        intelligence,
        learning,
        license,
        metrics,
        permissions_routes,
        portfolio,
        rate_limit_routes,
        reports,
        research,
        risk,
        security_ai,
        security_ai_extended,
        self_learning,
        signals,
        trade_history,
        trade_report,
        trades,
        users,
        websocket_routes,
    )

    app.include_router(auth.router, prefix="/auth")
    app.include_router(signals.router, prefix="/signals")
    app.include_router(trades.router, prefix="/trades")
    app.include_router(decision.router, prefix="/decision")
    app.include_router(analysis.router, prefix="/analysis")
    app.include_router(ai_prediction.router, prefix="/ai-prediction")
    app.include_router(dashboard.router, prefix="/dashboard")
    app.include_router(metrics.router, prefix="/metrics")
    app.include_router(analytics.router, prefix="/analytics")
    app.include_router(portfolio.router, prefix="/portfolio")
    app.include_router(risk.router, prefix="/risk")
    app.include_router(reports.router, prefix="/reports")
    app.include_router(research.router, prefix="/research")
    app.include_router(backtest.router, prefix="/backtest")
    app.include_router(backtest_engine.router, prefix="/backtest-engine")
    app.include_router(intelligence.router, prefix="/intelligence")
    app.include_router(agents.router, prefix="/agents")
    app.include_router(learning.router, prefix="/learning")
    app.include_router(self_learning.router, prefix="/self-learning")
    app.include_router(institutional.router, prefix="/institutional")
    app.include_router(institutional_backtest.router, prefix="/institutional-backtest")
    app.include_router(security_ai.router, prefix="/security-ai")
    app.include_router(security_ai_extended.router, prefix="/security-ai-ext")
    app.include_router(billing.router, prefix="/billing")
    app.include_router(license.router, prefix="/license")
    app.include_router(users.router, prefix="/users")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(admin_users.router, prefix="/admin")
    app.include_router(admin_observability.router, prefix="/admin")
    app.include_router(permissions_routes.router, prefix="/permissions")
    app.include_router(rate_limit_routes.router, prefix="/rate-limit")
    app.include_router(trade_history.router, prefix="/trade-history")
    app.include_router(trade_report.router, prefix="/trade-report")
    app.include_router(health.router, prefix="/health")
    app.include_router(websocket_routes.router, prefix="/ws")
    app.include_router(observability_routes.router)

    try:
        from backend.api.routes import audit_routes_v21

        app.include_router(audit_routes_v21.router, prefix="/admin/audit")
    except Exception as exc:
        logger.warning("[startup] audit_routes_v21 not loaded: %s", exc)

    @app.get("/", tags=["health"])
    async def root() -> Dict[str, Any]:
        uptime = round(time.time() - _startup_time, 2)
        return {
            "service": "Galaxy Vast AI Trading Platform",
            "version": "1.0.0",
            "status": "running",
            "uptime_seconds": uptime,
        }

    return app


app = _create_app()
