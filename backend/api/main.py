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
        title="Galaxy Vast AI TI