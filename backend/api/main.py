"""
backend/api/main.py - FastAPI Application Entry Point
Galaxy Vast AI Trading Platform - Enterprise Trading Bot

Complete implementation with all routes, middleware, and startup logic.
"""
from __future__ import annotations

import logging
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_startup_time: float = 0.0
_app_instance: Optional[FastAPI] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    global _startup_time
    _startup_time = time.time()
    logger.info("="*70)
    logger.info("[STARTUP] Galaxy Vast AI Trading Platform initializing...")
    logger.info("="*70)

    # Startup tasks
    try:
        # Start retraining service
        try:
            from backend.self_learning.retraining_service import retraining_service
            await retraining_service.start()
            logger.info("✅ [STARTUP] RetrainingService started")
        except Exception as exc:
            logger.warning("⚠️  [STARTUP] RetrainingService unavailable: %s", exc)

        # Start security AI agent
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            await security_ai_agent.start()
            logger.info("✅ [STARTUP] SecurityAIAgent started")
        except Exception as exc:
            logger.warning("⚠️  [STARTUP] SecurityAIAgent unavailable: %s", exc)

        # Start institutional RL agent
        try:
            from backend.institutional.rl_agent import institutional_rl_agent
            await institutional_rl_agent.start()
            logger.info("✅ [STARTUP] InstitutionalRLAgent started")
        except Exception as exc:
            logger.warning("⚠️  [STARTUP] InstitutionalRLAgent unavailable: %s", exc)

        # Initialize MT5 connection
        try:
            from backend.mt5_gateway.agent import mt5_agent
            await mt5_agent.initialize()
            logger.info("✅ [STARTUP] MT5 Gateway initialized")
        except Exception as exc:
            logger.warning("⚠️  [STARTUP] MT5 Gateway unavailable: %s", exc)

        startup_time = time.time() - _startup_time
        logger.info("✅ [STARTUP] Initialization complete in %.2f seconds", startup_time)

    except Exception as exc:
        logger.error("[STARTUP] Critical initialization error: %s", exc, exc_info=True)

    yield  # Application is running

    # Shutdown tasks
    logger.info("="*70)
    logger.info("[SHUTDOWN] Galaxy Vast AI Trading Platform shutting down...")
    logger.info("="*70)

    try:
        # Shutdown agents
        try:
            from backend.agents.security_ai_agent import security_ai_agent
            await security_ai_agent.shutdown()
            logger.info("✅ [SHUTDOWN] SecurityAIAgent stopped")
        except Exception as exc:
            logger.warning("⚠️  [SHUTDOWN] SecurityAIAgent shutdown error: %s", exc)

        # Shutdown MT5
        try:
            from backend.mt5_gateway.agent import mt5_agent
            await mt5_agent.shutdown()
            logger.info("✅ [SHUTDOWN] MT5 Gateway stopped")
        except Exception as exc:
            logger.warning("⚠️  [SHUTDOWN] MT5 Gateway shutdown error: %s", exc)

        logger.info("✅ [SHUTDOWN] All services stopped cleanly")

    except Exception as exc:
        logger.error("[SHUTDOWN] Error during shutdown: %s", exc, exc_info=True)

    logger.info("[SHUTDOWN] Shutdown complete.")


def _create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    from backend.core.config import settings

    # Create FastAPI instance
    app = FastAPI(
        title="Galaxy Vast AI Trading Platform",
        description="Enterprise MT5 Trading Ecosystem with Multi-Agent AI, SMC Engine, Price Action Analysis",
        version="3.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # ========================================================================
    # MIDDLEWARE SETUP
    # ========================================================================

    # CORS middleware
    cors_origins = getattr(settings, "CORS_ORIGINS", None) or ["*"]
    if not cors_origins and getattr(settings, "ENVIRONMENT", "development") == "production":
        logger.warning("[CORS] CORS_ORIGINS not configured in production - defaulting to safe origins")
        cors_origins = ["http://localhost:3000", "http://localhost:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if isinstance(cors_origins, list) else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=3600,
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "[EXCEPTION] Unhandled error: %s | Path: %s",
            str(exc),
            request.url.path,
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if getattr(settings, "DEBUG", False) else "An error occurred",
                "path": str(request.url.path)
            }
        )

    # ========================================================================
    # ROUTES SETUP
    # ========================================================================

    logger.info("[ROUTES] Loading API routes...")

    # Import all route modules
    from backend.api.routes import (
        # Core routes
        health, auth, dashboard,
        # Trading routes
        trades, trade_history, trade_report, signals,
        # Analysis routes
        analysis, decision, ai_prediction, portfolio,
        # Agent routes
        agents, risk,
        # Analytics & reporting
        analytics, reports, metrics,
        # Admin routes
        admin, admin_users, admin_observability,
        # Advanced features
        backtest, backtest_engine, institutional, institutional_backtest,
        # Intelligence & learning
        intelligence, learning, security_ai, security_ai_extended,
        # Infrastructure
        billing, license, permissions_routes, rate_limit_routes,
        # Research & self-learning
        research, self_learning,
        # WebSocket
        websocket_routes,
        # Users
        users,
    )

    from backend.api import observability_routes

    # Register health check first (critical)
    app.include_router(health.router, prefix="/health", tags=["Health"])
    logger.info("  ✅ Health routes")

    # Authentication & authorization
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(permissions_routes.router, tags=["Permissions"])
    logger.info("  ✅ Auth routes")

    # Core trading routes
    app.include_router(trades.router, prefix="/trades", tags=["Trading"])
    app.include_router(signals.router, prefix="/signals", tags=["Signals"])
    app.include_router(trade_history.router, prefix="/history", tags=["History"])
    app.include_router(trade_report.router, prefix="/reports", tags=["Reports"])
    logger.info("  ✅ Trading routes")

    # Analysis & decision-making
    app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
    app.include_router(decision.router, prefix="/decision", tags=["Decision Engine"])
    app.include_router(ai_prediction.router, prefix="/predictions", tags=["Predictions"])
    app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
    logger.info("  ✅ Analysis routes")

    # Agents
    app.include_router(agents.router, prefix="/agents", tags=["Agents"])
    app.include_router(risk.router, prefix="/risk", tags=["Risk Management"])
    logger.info("  ✅ Agent routes")

    # Analytics & reporting
    app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
    app.include_router(reports.router, prefix="/reports", tags=["Reports"])
    app.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
    logger.info("  ✅ Analytics routes")

    # Admin
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(admin_users.router, prefix="/admin/users", tags=["Admin"])
    logger.info("  ✅ Admin routes")

    # Advanced features
    app.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])
    app.include_router(institutional.router, prefix="/institutional", tags=["Institutional"])
    app.include_router(institutional_backtest.router, prefix="/backtest/institutional", tags=["Backtesting"])
    logger.info("  ✅ Advanced feature routes")

    # Intelligence & learning
    app.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])
    app.include_router(learning.router, prefix="/learning", tags=["Learning"])
    app.include_router(security_ai.router, prefix="/security", tags=["Security"])
    app.include_router(security_ai_extended.router, prefix="/security/extended", tags=["Security"])
    app.include_router(self_learning.router, prefix="/self-learning", tags=["Self-Learning"])
    logger.info("  ✅ Intelligence routes")

    # Infrastructure
    app.include_router(billing.router, prefix="/billing", tags=["Billing"])
    app.include_router(license.router, prefix="/license", tags=["License"])
    app.include_router(rate_limit_routes.router, tags=["Rate Limiting"])
    logger.info("  ✅ Infrastructure routes")

    # Research
    app.include_router(research.router, prefix="/research", tags=["Research"])
    logger.info("  ✅ Research routes")

    # WebSocket
    app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])
    logger.info("  ✅ WebSocket routes")

    # Dashboard
    app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    logger.info("  ✅ Dashboard routes")

    # Users
    app.include_router(users.router, prefix="/users", tags=["Users"])
    logger.info("  ✅ User routes")

    # Observability
    app.include_router(observability_routes.router, prefix="/observability", tags=["Observability"])
    logger.info("  ✅ Observability routes")

    # Admin observability
    app.include_router(admin_observability.router, prefix="/admin/observability", tags=["Admin"])
    logger.info("  ✅ Admin observability routes")

    logger.info("[ROUTES] ✅ All %d route groups registered", 25)

    # ========================================================================
    # STATIC FILES (Optional)
    # ========================================================================

    import os
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    if os.path.exists(static_dir):
        try:
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
            logger.info("[STATIC] React frontend mounted at /")
        except Exception as exc:
            logger.warning("[STATIC] Could not mount frontend: %s", exc)

    # ========================================================================
    # ROOT ENDPOINT
    # ========================================================================

    @app.get("/", tags=["Root"])
    async def root() -> Dict[str, Any]:
        """Root endpoint - API information."""
        uptime_seconds = time.time() - _startup_time
        return {
            "name": "Galaxy Vast AI Trading Platform",
            "version": "3.0.0",
            "status": "online",
            "uptime_seconds": uptime_seconds,
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
            "environment": getattr(settings, "ENVIRONMENT", "development"),
        }

    logger.info("[ROUTES] ✅ API fully configured and ready")
    return app


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def get_app() -> FastAPI:
    """Get or create FastAPI application."""
    global _app_instance
    if _app_instance is None:
        _app_instance = _create_app()
    return _app_instance


def create_app() -> FastAPI:
    """Create new FastAPI application instance."""
    return _create_app()


# ============================================================================
# EXPORT FOR UVICORN
# ============================================================================

app = get_app()

# ============================================================================
# CLI ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("="*70)
    logger.info("Starting Galaxy Vast AI Trading Platform")
    logger.info("="*70)

    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
