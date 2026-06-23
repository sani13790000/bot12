"""backend/api/websocket_manager.py v2 - Phase T

T-8:  per-connection broadcast isolation
T-9:  MAX_CONNECTIONS_PER_USER=5 cap
T-10: background ping/pong loop 30s, evict stale
T-11: asyncio.Lock on all dict mutations
T-12: per-connection subscription topic filter
"""
from __future__ import annotations
import asyncio, logging, time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("api.websocket_manager")

_MAX_CONNECTIONS_PER_USER: int   = 5
_PING_INTERVAL_S:          float = 30.0
_PING_TIMEOUT_S:           float = 10.0
_MAX_TOTAL:                int   = 500


class WSMessageType(str, Enum):
    SIGNAL       = "signal"
    TRADE_UPDATE = "trade_update"
    PRICE_TICK   = "price_tick"
    RISK_ALERT   = "risk_alert"
    SYSTEM       = "system"
    PING         = "ping"
    PONG         = "pong"
    ERROR        = "error"


@dataclass
class _ConnInfo:
    ws:            WebSocket
    user_id:       str
    conn_id:       str
    subscriptions: Set[str] = field(default_factory=set)
    connected_at:  float    = field(default_factory=time.monotonic)
    last_ping_ok:  float    = field(default_factory=time.monotonic)


class WebSocketManager:
    def __init__(self) -> None:
        self._conns:    Dict[str, _ConnInfo]     = {}
        self._by_user:  Dict[str, Set[str]]      = defaultdict(set)
        self._lock      = asyncio.Lock()
        self._ping_task: Optional[asyncio.Task] = None

    async def connect(self, ws: WebSocket, user_id: str, topics: Optional[List[str]] = None) -> str:
        await ws.accept()
        async with self._lock:
            user_conn_ids = self._by_user[user_id]
            if len(user_conn_ids) >= _MAX_CONNECTIONS_PER_USER:  # T-9
                oldest_id = min(user_conn_ids, key=lambda cid: self._conns[cid].connected_at)
                await self._evict(oldest_id, "cap_exceeded")
            if len(self._conns) >= _MAX_TOTAL:
                await ws.close(code=1008); return ""
            conn_id = str(uuid4())
            self._conns[conn_id] = _ConnInfo(ws=ws, user_id=user_id, conn_id=conn_id,
                                             subscriptions=set(topics or []))
            self._by_user[user_id].add(conn_id)
        self._ensure_ping_loop()
        return conn_id

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:  # T-11
            cid = self._find_conn_id(ws)
            if cid: await self._evict(cid, "disconnect")

    async def broadcast(self, msg_type: WSMessageType, payload: Any,
                        topic: Optional[str] = None, user_id: Optional[str] = None) -> int:
        if not isinstance(msg_type, WSMessageType): return 0
        message = {"type": msg_type.value, "payload": payload, "topic": topic, "ts": time.time()}
        async with self._lock:
            candidates = list(self._conns.values())  # T-11: copy
        ok = 0
        for info in candidates:
            if user_id and info.user_id != user_id: continue
            if topic and info.subscriptions and topic not in info.subscriptions: continue  # T-12
            try:
                await info.ws.send_json(message); ok += 1
            except Exception as exc:  # T-8: isolated
                logger.warning("ws send failed conn=%s: %s", info.conn_id, exc)
                asyncio.create_task(self._handle_broken(info.conn_id))
        return ok

    async def send_to_user(self, user_id: str, msg_type: WSMessageType, payload: Any) -> int:
        return await self.broadcast(msg_type, payload, user_id=user_id)

    async def subscribe(self, conn_id: str, topics: List[str]) -> None:
        async with self._lock:
            if conn_id in self._conns: self._conns[conn_id].subscriptions.update(topics)

    async def unsubscribe(self, conn_id: str, topics: List[str]) -> None:
        async with self._lock:
            if conn_id in self._conns: self._conns[conn_id].subscriptions -= set(topics)

    def connection_count(self) -> int: return len(self._conns)
    def user_connection_count(self, user_id: str) -> int:
        return len(self._by_user.get(user_id, set()))
    def stats(self) -> Dict[str, Any]:
        return {"total_connections": len(self._conns), "total_users": len(self._by_user),
                "by_user": {uid: len(ids) for uid, ids in self._by_user.items() if ids}}

    def _ensure_ping_loop(self) -> None:
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_loop(), name="ws_ping_loop")

    async def _ping_loop(self) -> None:  # T-10
        while True:
            await asyncio.sleep(_PING_INTERVAL_S)
            now = time.monotonic()
            async with self._lock:
                stale = [cid for cid, info in self._conns.items()
                         if now - info.last_ping_ok > _PING_INTERVAL_S + _PING_TIMEOUT_S]
            for cid in stale:
                async with self._lock: await self._evict(cid, "ping_timeout")
            async with self._lock:
                candidates = list(self._conns.items())
            for cid, info in candidates:
                try:
                    await info.ws.send_json({"type": WSMessageType.PING.value})
                    async with self._lock:
                        if cid in self._conns: self._conns[cid].last_ping_ok = time.monotonic()
                except Exception:
                    asyncio.create_task(self._handle_broken(cid))

    def _find_conn_id(self, ws: WebSocket) -> Optional[str]:
        return next((cid for cid, info in self._conns.items() if info.ws is ws), None)

    async def _evict(self, conn_id: str, reason: str = "") -> None:
        info = self._conns.pop(conn_id, None)
        if info is None: return
        self._by_user[info.user_id].discard(conn_id)
        if not self._by_user[info.user_id]: del self._by_user[info.user_id]
        try: await info.ws.close()
        except Exception: pass

    async def _handle_broken(self, conn_id: str) -> None:
        async with self._lock: await self._evict(conn_id, "broken_pipe")


_manager: Optional[WebSocketManager] = None
def get_websocket_manager() -> WebSocketManager:
    global _manager
    if _manager is None: _manager = WebSocketManager()
    return _manager
