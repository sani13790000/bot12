"""WebSocket routes — real-time price and signal streaming.

Security:
- Every connection requires a valid JWT passed as ?token=<access_token>
- Invalid / expired tokens receive WS 1008 Policy Violation and are closed
- No unauthenticated access to live data
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import time
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

logger = logging.getLogger(__name__)
router = APIRouter()

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGO = "HS256"

# Active connection registries (symbol → set of WebSockets)
_price_connections: Dict[str, Set[WebSocket]] = {}
_signal_connections: Set[WebSocket] = set()
_registry_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_ws_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT. Returns payload or None on failure."""
    if not token or not JWT_SECRET:
        return None
    try:
        import jwt as pyjwt  # PyJWT
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload
    except Exception:  # noqa: BLE001
        return None


async def _authenticate_ws(websocket: WebSocket, token: str) -> Optional[Dict[str, Any]]:
    """Authenticate WS handshake. Closes with 1008 on failure, returns payload on success."""
    payload = _verify_ws_token(token)
    if not payload:
        logger.warning(
            "WS auth failed from %s — closing with 1008.",
            websocket.client.host if websocket.client else "unknown",
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return payload


# ---------------------------------------------------------------------------
# /ws/prices  — candlestick + tick streaming
# ---------------------------------------------------------------------------

@router.websocket("/ws/prices")
async def ws_prices(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    symbol: str = Query("XAUUSD", description="Trading symbol"),
) -> None:
    """Stream real-time price ticks for a given symbol.

    Query params:
        token  — required JWT (from HttpOnly cookie flow, passed as ?token=)
        symbol — e.g. XAUUSD, EURUSD (default: XAUUSD)
    """
    await websocket.accept()
    payload = await _authenticate_ws(websocket, token)
    if payload is None:
        return  # already closed

    username = payload.get("username", "unknown")
    logger.info("WS /prices connected: user=%s symbol=%s", username, symbol)

    async with _registry_lock:
        _price_connections.setdefault(symbol, set()).add(websocket)

    # Seed price for realistic simulation
    base_prices = {
        "XAUUSD": 2650.0, "EURUSD": 1.0850, "GBPUSD": 1.2700,
        "USDJPY": 149.50, "BTCUSD": 43000.0, "US30": 38500.0,
    }
    price = base_prices.get(symbol.upper(), 1.0)

    try:
        while True:
            # Simulate realistic tick
            change_pct = random.gauss(0, 0.0003)
            price *= 1 + change_pct
            tick = {
                "type": "tick",
                "symbol": symbol,
                "bid": round(price, 5),
                "ask": round(price * 1.00015, 5),
                "timestamp": time.time(),
                "volume": random.randint(100, 5000),
            }
            await websocket.send_text(json.dumps(tick))
            await asyncio.sleep(0.5)  # 2 ticks/sec

    except WebSocketDisconnect:
        logger.info("WS /prices disconnected: user=%s symbol=%s", username, symbol)
    except Exception as exc:  # noqa: BLE001
        logger.error("WS /prices error for %s: %s", username, exc)
    finally:
        async with _registry_lock:
            conns = _price_connections.get(symbol, set())
            conns.discard(websocket)
            if not conns:
                _price_connections.pop(symbol, None)


# ---------------------------------------------------------------------------
# /ws/signals  — trade signal streaming
# ---------------------------------------------------------------------------

@router.websocket("/ws/signals")
async def ws_signals(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """Stream real-time trade signals from all active agents."""
    await websocket.accept()
    payload = await _authenticate_ws(websocket, token)
    if payload is None:
        return

    username = payload.get("username", "unknown")
    logger.info("WS /signals connected: user=%s", username)

    async with _registry_lock:
        _signal_connections.add(websocket)

    signals_sent = 0
    try:
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": f"Signal stream started for {username}",
            "timestamp": time.time(),
        }))

        while True:
            # Simulate periodic signal (every 10-30s in real system)
            await asyncio.sleep(15)
            signal = {
                "type": "signal",
                "symbol": random.choice(["XAUUSD", "EURUSD", "GBPUSD"]),
                "direction": random.choice(["BUY", "SELL"]),
                "confidence": round(random.uniform(0.55, 0.95), 3),
                "entry": round(random.uniform(1900, 2700), 2),
                "sl_pips": random.randint(20, 80),
                "tp_pips": random.randint(40, 200),
                "agents": ["SMC", "ML", "PA", "Risk", "Liquidity"],
                "timestamp": time.time(),
                "signal_id": signals_sent,
            }
            signals_sent += 1
            await websocket.send_text(json.dumps(signal))

    except WebSocketDisconnect:
        logger.info("WS /signals disconnected: user=%s signals_sent=%d", username, signals_sent)
    except Exception as exc:  # noqa: BLE001
        logger.error("WS /signals error for %s: %s", username, exc)
    finally:
        async with _registry_lock:
            _signal_connections.discard(websocket)


# ---------------------------------------------------------------------------
# /ws/health  — lightweight ping (no auth required)
# ---------------------------------------------------------------------------

@router.websocket("/ws/health")
async def ws_health(websocket: WebSocket) -> None:
    """WebSocket health check — no auth, used by load balancers."""
    await websocket.accept()
    await websocket.send_text(json.dumps({"status": "ok", "timestamp": time.time()}))
    await websocket.close()
