"""WebSocket routes — Phase I: broadcast positions + signals to all connected clients."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.execution.mt5_connector import mt5_connector
from backend.risk.kill_switch import get_kill_switch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# ── Connection manager ────────────────────────────────────────

class _ConnectionManager:
    """Thread-safe WebSocket connection manager."""

    def __init__(self) -> None:
        self._clients: Dict[str, Set[WebSocket]] = {}  # channel -> clients

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.setdefault(channel, set()).add(ws)
        logger.info("WS client connected to channel=%s total=%d", channel, len(self._clients[channel]))

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        if channel in self._clients:
            self._clients[channel].discard(ws)
        logger.info("WS client disconnected from channel=%s", channel)

    async def broadcast(self, channel: str, data: dict) -> None:
        """Broadcast JSON data to all clients on a channel."""
        dead: List[WebSocket] = []
        for ws in list(self._clients.get(channel, [])):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)

    def client_count(self, channel: str) -> int:
        return len(self._clients.get(channel, set()))


_manager = _ConnectionManager()


# ── Background broadcaster ────────────────────────────────────

async def _positions_broadcaster() -> None:
    """Push positions to all /ws/positions clients every 2 seconds."""
    while True:
        try:
            if _manager.client_count("positions") > 0:
                positions = await mt5_connector.get_positions()
                ks = get_kill_switch()
                payload = {
                    "type": "positions",
                    "positions": [p if isinstance(p, dict) else p.__dict__ for p in (positions or [])],
                    "kill_switch_active": ks.is_active,
                }
                await _manager.broadcast("positions", payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("positions broadcaster error: %s", exc)
        await asyncio.sleep(2)


async def _signals_broadcaster() -> None:
    """Push latest signal to all /ws/signals clients every 5 seconds."""
    from backend.database.redis_client import get_redis  # lazy import
    while True:
        try:
            if _manager.client_count("signals") > 0:
                r = await get_redis()
                if r:
                    raw = await r.lrange("recent_signals", 0, 4)
                    signals = [json.loads(s) for s in (raw or [])]
                    await _manager.broadcast("signals", {"type": "signals", "signals": signals})
        except Exception as exc:  # noqa: BLE001
            logger.debug("signals broadcaster error: %s", exc)
        await asyncio.sleep(5)


def start_broadcasters() -> None:
    """Start background broadcast tasks. Called from lifespan()."""
    loop = asyncio.get_event_loop()
    loop.create_task(_positions_broadcaster())
    loop.create_task(_signals_broadcaster())
    logger.info("WebSocket broadcasters started")


# ── WebSocket endpoints ───────────────────────────────────────

@router.websocket("/positions")
async def ws_positions(websocket: WebSocket) -> None:
    """Real-time position updates (push every 2s from broadcaster)."""
    await _manager.connect("positions", websocket)
    try:
        while True:
            # Keep alive — client can send ping
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _manager.disconnect("positions", websocket)
    except Exception:  # noqa: BLE001
        _manager.disconnect("positions", websocket)


@router.websocket("/signals")
async def ws_signals(websocket: WebSocket) -> None:
    """Real-time signal feed."""
    await _manager.connect("signals", websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _manager.disconnect("signals", websocket)
    except Exception:  # noqa: BLE001
        _manager.disconnect("signals", websocket)


@router.websocket("/health")
async def ws_health(websocket: WebSocket) -> None:
    """Health stream — useful for monitoring dashboards."""
    await websocket.accept()
    try:
        while True:
            ks = get_kill_switch()
            await websocket.send_json({
                "type": "health",
                "kill_switch": ks.is_active,
                "positions_clients": _manager.client_count("positions"),
                "signals_clients": _manager.client_count("signals"),
            })
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
