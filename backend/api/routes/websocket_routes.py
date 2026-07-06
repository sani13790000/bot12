"""WebSocket routes -- BUG-AG1 fix: removed double prefix /ws"""
from __future__ import annotations
import asyncio, json, logging
from typing import Dict, List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.execution.mt5_connector import mt5_connector
from backend.risk.kill_switch import get_kill_switch
logger = logging.getLogger(__name__)
# BUG-AG1 fix: removed prefix="/ws" -- main.py provides prefix="/ws"
router = APIRouter(tags=["websocket"])

class _ConnectionManager:
    def __init__(self) -> None:
        self._clients: Dict[str, Set[WebSocket]] = {}
    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.setdefault(channel, set()).add(ws)
        logger.info("WS client connected to channel=%s", channel)
    def disconnect(self, channel: str, ws: WebSocket) -> None:
        if channel in self._clients:
            self._clients[channel].discard(ws)
    async def broadcast(self, channel: str, data: dict) -> None:
        dead: List[WebSocket] = []
        for ws in list(self._clients.get(channel, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)
    def client_count(self, channel: str) -> int:
        return len(self._clients.get(channel, set()))

_manager = _ConnectionManager()

async def _positions_broadcaster() -> None:
    while True:
        try:
            if _manager.client_count("positions") > 0:
                pos = await mt5_connector.get_positions()
                ks = get_kill_switch()
                await _manager.broadcast("positions", {"type": "positions", "positions": [p if isinstance(p, dict) else p.__dict__ for p in (pos or [])], "kill_switch_active": ks.is_active})
        except Exception as exc:
            logger.debug("positions broadcaster error: %s", exc)
        await asyncio.sleep(2)

async def _signals_broadcaster() -> None:
    from backend.database.redis_client import get_redis
    while True:
        try:
            if _manager.client_count("signals") > 0:
                r = await get_redis()
                if r:
                    raw = await r.lrange("recent_signals", 0, 4)
                    signals = [json.loads(s) for s in (raw or [])]
                    await _manager.broadcast("signals", {"type": "signals", "signals": signals})
        except Exception as exc:
            logger.debug("signals broadcaster error: %s", exc)
        await asyncio.sleep(5)

def start_broadcasters() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(_positions_broadcaster())
    loop.create_task(_signals_broadcaster())
    logger.info("WebSocket broadcasters started")

@router.websocket("/positions")
async def ws_positions(websocket: WebSocket) -> None:
    await _manager.connect("positions", websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _manager.disconnect("positions", websocket)
    except Exception:
        _manager.disconnect("positions", websocket)

@router.websocket("/signals")
async def ws_signals(websocket: WebSocket) -> None:
    await _manager.connect("signals", websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _manager.disconnect("signals", websocket)
    except Exception:
        _manager.disconnect("signals", websocket)

@router.websocket("/health")
async def ws_health(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            ks = get_kill_switch()
            await websocket.send_json({"type": "health", "kill_switch": ks.is_active, "positions_clients": _manager.client_count("positions"), "signals_clients": _manager.client_count("signals")})
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
