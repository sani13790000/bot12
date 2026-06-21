"""backend/api/routes/websocket_routes.py — Security Audit Fix (Phase H)

SEC-20 Token never logged in plaintext
SEC-21 JTI revocation check before accept
SEC-22 Per-IP connection limit (max 10)
SEC-23 Message size enforced (64 KB)
SEC-24 Origin header validated against ALLOWED_ORIGINS
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.core.security import validate_access_token
from backend.core.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])

_MAX_CONNS_PER_IP: int  = 10
_MAX_MSG_BYTES:    int  = 64 * 1024
_REVOKE_CACHE_TTL: float = 30.0

_ip_conns:     Dict[str, int]   = defaultdict(int)
_ip_conn_lock: asyncio.Lock     = asyncio.Lock()
_revoked_cache: Dict[str, float] = {}


async def _check_revoked(jti: str, db) -> bool:
    now = time.monotonic()
    last_check = _revoked_cache.get(jti)
    if last_check and now - last_check < _REVOKE_CACHE_TTL:
        return False
    try:
        row = await db.select_one("revoked_tokens", {"jti": jti}, columns="jti")
        if row:
            return True
        _revoked_cache[jti] = now
        return False
    except Exception:
        return False


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            old = self._conns.get(user_id)
            if old and old.client_state == WebSocketState.CONNECTED:
                try:
                    await old.close(code=4000)
                except Exception:
                    pass
            self._conns[user_id] = ws

    async def disconnect(self, user_id: str) -> None:
        async with self._lock:
            self._conns.pop(user_id, None)

    async def send(self, user_id: str, data: dict) -> bool:
        ws = self._conns.get(user_id)
        if ws and ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.send_json(data)
                return True
            except Exception:
                await self.disconnect(user_id)
        return False

    async def broadcast(self, data: dict) -> int:
        sent = 0
        async with self._lock:
            user_ids = list(self._conns.keys())
        for uid in user_ids:
            if await self.send(uid, data):
                sent += 1
        return sent


manager = ConnectionManager()


def _validate_origin(ws: WebSocket) -> bool:
    settings = get_settings()
    origin = ws.headers.get("origin", "")
    if not origin:
        return settings.ENVIRONMENT != "production"
    return origin in settings.ALLOWED_ORIGINS


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: Optional[str] = Query(None),
):
    if not _validate_origin(websocket):
        await websocket.close(code=4003)
        return

    if not token:
        log.warning("WS: missing token for user_id=%s", user_id)
        await websocket.close(code=4001)
        return

    try:
        payload = validate_access_token(token)
    except ValueError:
        log.warning("WS: invalid token for user_id=%s", user_id)
        await websocket.close(code=4001)
        return

    token_user_id = payload.get("sub")
    if token_user_id != user_id:
        log.warning("WS: user_id mismatch token_sub=%s path=%s", token_user_id, user_id)
        await websocket.close(code=4003)
        return

    jti = payload.get("jti", "")
    from backend.database import db as _db
    if jti and await _check_revoked(jti, _db):
        log.warning("WS: revoked token jti=%s", jti)
        await websocket.close(code=4001)
        return

    client_ip = websocket.client.host if websocket.client else "unknown"
    async with _ip_conn_lock:
        current = _ip_conns[client_ip]
        if current >= _MAX_CONNS_PER_IP:
            log.warning("WS: connection limit exceeded ip=%s", client_ip)
            await websocket.close(code=4029)
            return
        _ip_conns[client_ip] = current + 1

    await websocket.accept()
    await manager.connect(user_id, websocket)
    log.info("WS: connected user_id=%s", user_id)

    try:
        await websocket.send_json({"type": "connected", "user_id": user_id})
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                if len(raw.encode()) > _MAX_MSG_BYTES:
                    await websocket.send_json({"error": "Message too large"})
                    continue
                if raw == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.error("WS: error user_id=%s: %s", user_id, type(exc).__name__)
    finally:
        await manager.disconnect(user_id)
        async with _ip_conn_lock:
            _ip_conns[client_ip] = max(0, _ip_conns.get(client_ip, 1) - 1)
        log.info("WS: disconnected user_id=%s", user_id)
