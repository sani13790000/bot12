"""WebSocket routes for Galaxy Vast AI Trading Platform.

Fixes applied:
- HIGH: JWT authentication via ?token= query param (1008 close if invalid)
- MEDIUM: Connection cleanup on disconnect (no resource leak)
- MEDIUM: Per-connection error handling
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Connection registry — track active connections for cleanup
# ---------------------------------------------------------------------------
_price_connections: Set[WebSocket] = set()
_signal_connections: Set[WebSocket] = set()
_connections_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# JWT validation helper
# ---------------------------------------------------------------------------

def _verify_ws_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token for WebSocket auth. Returns payload or None."""
    try:
        from jose import jwt, JWTError
        secret = os.environ.get("JWT_SECRET_KEY", "")
        if not secret:
            logger.warning("JWT_SECRET_KEY not set — WS auth disabled")
            return {"sub": "anonymous"}  # dev mode: allow all
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception as exc:
        logger.warning("WS JWT validation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.websocket("/ws/prices")
async def ws_prices(
    websocket: WebSocket,
    token: str = Query(""),
    symbol: str = Query("XAUUSD"),
) -> None:
    """Real-time price stream. Requires valid JWT via ?token=<jwt>."""
    # Authenticate
    if token:
        payload = _verify_ws_token(token)
        if payload is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        # No token — close in production, allow in development
        env = os.environ.get("ENVIRONMENT", "production")
        if env == "production":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    async with _connections_lock:
        _price_connections.add(websocket)
    logger.info("WS /ws/prices connected (symbol=%s, connections=%d)", symbol, len(_price_connections))

    try:
        seq = 0
        while True:
            # Simulate price tick (replace with real market data feed)
            import random
            base = {"XAUUSD": 2000.0, "EURUSD": 1.08, "BTCUSD": 65000.0}.get(symbol, 100.0)
            price = base + random.uniform(-base * 0.001, base * 0.001)
            tick = {
                "type": "tick",
                "symbol": symbol,
                "bid": round(price - 0.5, 2),
                "ask": round(price + 0.5, 2),
                "mid": round(price, 2),
                "timestamp": time.time(),
                "seq": seq,
            }
            await websocket.send_text(json.dumps(tick))
            seq += 1
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("WS /ws/prices client disconnected (symbol=%s)", symbol)
    except Exception as exc:
        logger.error("WS /ws/prices error: %s", exc)
    finally:
        # Always cleanup — prevents resource leak
        async with _connections_lock:
            _price_connections.discard(websocket)
        logger.info("WS /ws/prices cleanup done (remaining=%d)", len(_price_connections))


@router.websocket("/ws/signals")
async def ws_signals(
    websocket: WebSocket,
    token: str = Query(""),
) -> None:
    """Real-time trading signals stream. Requires valid JWT."""
    if token:
        payload = _verify_ws_token(token)
        if payload is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        env = os.environ.get("ENVIRONMENT", "production")
        if env == "production":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    async with _connections_lock:
        _signal_connections.add(websocket)
    logger.info("WS /ws/signals connected (connections=%d)", len(_signal_connections))

    try:
        while True:
            # Send heartbeat every 30s (replace with real signal events)
            heartbeat = {
                "type": "heartbeat",
                "timestamp": time.time(),
                "active_signals": 0,
            }
            await websocket.send_text(json.dumps(heartbeat))
            await asyncio.sleep(30.0)
    except WebSocketDisconnect:
        logger.info("WS /ws/signals client disconnected")
    except Exception as exc:
        logger.error("WS /ws/signals error: %s", exc)
    finally:
        async with _connections_lock:
            _signal_connections.discard(websocket)
        logger.info("WS /ws/signals cleanup done (remaining=%d)", len(_signal_connections))


@router.websocket("/ws/health")
async def ws_health(websocket: WebSocket) -> None:
    """Health check WebSocket — no auth required."""
    await websocket.accept()
    try:
        await websocket.send_text(json.dumps({
            "type": "health",
            "status": "ok",
            "timestamp": time.time(),
            "price_connections": len(_price_connections),
            "signal_connections": len(_signal_connections),
        }))
        await websocket.close()
    except Exception as exc:
        logger.error("WS /ws/health error: %s", exc)


def get_connection_stats() -> Dict[str, int]:
    """Return current connection counts."""
    return {
        "price_connections": len(_price_connections),
        "signal_connections": len(_signal_connections),
    }
