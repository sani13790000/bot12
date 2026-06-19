"""WebSocket Routes — Galaxy Vast AI
Provides real-time price feed and signal streaming via WebSocket.
Frontend connects to ws://localhost:8000/ws/signals and ws://localhost:8000/ws/prices
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.logger import get_logger

logger = get_logger("api.websocket")
router = APIRouter()

# Connection registry
_price_connections: Set[WebSocket] = set()
_signal_connections: Set[WebSocket] = set()


async def _safe_send(ws: WebSocket, data: dict) -> bool:
    try:
        await ws.send_text(json.dumps(data))
        return True
    except Exception:
        return False


@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    """Real-time price feed — sends mock tick every second."""
    await websocket.accept()
    _price_connections.add(websocket)
    logger.info("WS price client connected. Total: %d", len(_price_connections))
    try:
        import random
        price = 2000.0
        while True:
            price += random.uniform(-2, 2)
            payload = {
                "type": "tick",
                "symbol": "XAUUSD",
                "bid": round(price, 2),
                "ask": round(price + 0.3, 2),
                "timestamp": time.time(),
            }
            ok = await _safe_send(websocket, payload)
            if not ok:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        _price_connections.discard(websocket)
        logger.info("WS price client disconnected. Total: %d", len(_price_connections))


@router.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket):
    """Real-time signal stream — sends signals as they are generated."""
    await websocket.accept()
    _signal_connections.add(websocket)
    logger.info("WS signal client connected. Total: %d", len(_signal_connections))
    try:
        # Send welcome
        await _safe_send(websocket, {"type": "connected", "message": "Signal stream active"})
        # Keep alive — real signals pushed via broadcast_signal()
        while True:
            await asyncio.sleep(30)
            await _safe_send(websocket, {"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        _signal_connections.discard(websocket)


async def broadcast_signal(signal: dict) -> None:
    """Broadcast a signal to all connected WebSocket clients."""
    dead = set()
    for ws in list(_signal_connections):
        ok = await _safe_send(ws, {"type": "signal", **signal})
        if not ok:
            dead.add(ws)
    _signal_connections -= dead


@router.get("/ws/status")
async def ws_status():
    return {
        "price_connections": len(_price_connections),
        "signal_connections": len(_signal_connections),
    }
