"""WebSocket routes — real-time price and signal streaming.

Security: JWT token required via query parameter ?token=...
Clients that fail auth are immediately disconnected with code 1008.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("routes.websocket")
router = APIRouter()

# Connected client sets
_price_connections:  Set[WebSocket] = set()
_signal_connections: Set[WebSocket] = set()


# ── Auth helper ───────────────────────────────────────────────────────────────────

def _verify_ws_token(token: str) -> dict | None:
    """Verify JWT from WS query param. Returns payload or None."""
    if not token:
        return None
    try:
        import jwt
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except Exception:
        return None


async def _safe_send(ws: WebSocket, data: dict) -> bool:
    """Send JSON safely; return False if connection is dead."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


# ── Endpoints ───────────────────────────────────────────────────────────────────

@router.websocket("/ws/prices")
async def ws_prices(
    websocket: WebSocket,
    token: str = Query(default="", description="JWT access token"),
) -> None:
    """Real-time price stream. Auth required: ?token=<access_token>"""
    # Authenticate before accepting
    payload = _verify_ws_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("WS /ws/prices rejected: invalid or missing token")
        return

    await websocket.accept()
    _price_connections.add(websocket)
    logger.info("WS price client connected. Total: %d", len(_price_connections))

    try:
        await _safe_send(websocket, {
            "type": "connected",
            "message": "Price stream active",
            "user_id": payload.get("sub"),
        })
        # Keep-alive: send ping every 30s; real prices pushed via broadcast_price()
        while True:
            await asyncio.sleep(30)
            ok = await _safe_send(websocket, {"type": "ping", "timestamp": time.time()})
            if not ok:
                break
    except WebSocketDisconnect:
        pass
    finally:
        _price_connections.discard(websocket)
        logger.info("WS price client disconnected. Total: %d", len(_price_connections))


@router.websocket("/ws/signals")
async def ws_signals(
    websocket: WebSocket,
    token: str = Query(default="", description="JWT access token"),
) -> None:
    """Real-time signal stream. Auth required: ?token=<access_token>"""
    payload = _verify_ws_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("WS /ws/signals rejected: invalid or missing token")
        return

    await websocket.accept()
    _signal_connections.add(websocket)
    logger.info("WS signal client connected. Total: %d", len(_signal_connections))

    try:
        await _safe_send(websocket, {"type": "connected", "message": "Signal stream active"})
        # Keep alive — real signals pushed via broadcast_signal()
        while True:
            await asyncio.sleep(30)
            await _safe_send(websocket, {"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        _signal_connections.discard(websocket)


# ── Broadcast helpers (called from signal/execution services) ───────────────────────

async def broadcast_price(price_data: dict) -> None:
    """Broadcast price update to all connected WebSocket clients."""
    dead: Set[WebSocket] = set()
    for ws in list(_price_connections):
        ok = await _safe_send(ws, {"type": "price", **price_data})
        if not ok:
            dead.add(ws)
    _price_connections -= dead


async def broadcast_signal(signal: dict) -> None:
    """Broadcast a signal to all connected WebSocket clients."""
    dead: Set[WebSocket] = set()
    for ws in list(_signal_connections):
        ok = await _safe_send(ws, {"type": "signal", **signal})
        if not ok:
            dead.add(ws)
    _signal_connections -= dead


@router.get("/ws/status")
async def ws_status() -> dict:
    """Return current WebSocket connection counts."""
    return {
        "price_connections": len(_price_connections),
        "signal_connections": len(_signal_connections),
    }
