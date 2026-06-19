"""security_ai_loader.py
Helper imported by main.py to register security AI routers.
Kept separate to avoid inflating main.py size.
"""
from __future__ import annotations

import logging
from fastapi import FastAPI

log = logging.getLogger(__name__)


def register_security_ai_routes(app: FastAPI, prefix: str = "/api/v1/security-ai") -> bool:
    """Register security_ai and security_ai_extended routers.

    Returns True if successful, False if routes unavailable.
    FIX-D: These routers existed but were never registered in main.py,
    causing HTTP 404 for all /api/v1/security-ai/* endpoints.
    """
    try:
        from backend.api.routes import security_ai, security_ai_extended
        app.include_router(security_ai.router, prefix=prefix, tags=["Security AI"])
        app.include_router(security_ai_extended.router, prefix=prefix, tags=["Security AI"])
        log.info("Security AI routes registered at %s", prefix)
        return True
    except ImportError as exc:
        log.warning("Security AI routes not available: %s", exc)
        return False
