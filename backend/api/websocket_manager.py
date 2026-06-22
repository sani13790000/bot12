from __future__ import annotations
import asyncio, json, logging, time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

PING_INTERVAL_SEC = 30
PONG_TIMEOUT_SEC  = 10
MAX_CONNECTIONS   = 200
MAX_PER_USER      = 5


class WSMessageType(str, Enum):
    SIGNAL        = "signal"
    TRADE_UPDATE  = "trade_update"
    EQUITY_UPDATE = "equity_update"
    RISK_ALERT    = "risk_alert"
    SYSTEM        = "system"
    PING          = "ping"
    PONG          = "pong"
    ERROR         = "error"
    SUBSCRIBE     = "subscribe"
    UNSUBSCRIBE   = "unsubscribe"


@dataclass
class WSConnection:
    ws:            Any
    user_id:       str
    connection_id: str
    connected_at:  float    = field(default_factory=time.monotonic)
    last_pong:     float    = field(default_factory=time.monotonic)
    subscriptions: Set[str] = field(default_factory=set)
    message_count: int      = 0

    @property
    def is_stale(self) -> bool:
        # P-8 FIX: stale if no pong for PING+PONG timeout
        return (time.monotonic() - self.last_pong) > (PING_INTERVAL_SEC + PONG_TIMEOUT_SEC)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "user_id":       self.user_id,
            "last_pong_ago": round(time.monotonic() - self.last_pong, 1),
            "subscriptions": list(self.subscriptions),
            "message_count": self.message_count,
        }


class WebSocketManager:
    """Centralized WebSocket manager - Phase P fixes P-6..P-10."""

    def __init__(self) -> None:
        # P-7 FIX: lock for all mutations
        self._lock        = asyncio.Lock()
        self._connections: Dict[str, WSConnection] = {}
        self._user_conns:  Dict[str, Set[str]]     = defaultdict(set)
        self._ping_task:   Optional[asyncio.Task]  = None
        self._started      = False

    async def start(self) -> None:
        if self._started:
            return
        self._started   = True
        # P-8 FIX: start heartbeat
        self._ping_task = asyncio.create_task(self._ping_loop(), name="ws-ping")

    async def stop(self) -> None:
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            for conn in list(self._connections.values()):
                try:
                    await conn.ws.close()
                except Exception:
                    pass
            self._connections.clear()
            self._user_conns.clear()

    async def connect(self, ws: Any, user_id: str, connection_id: str) -> bool:
        # P-7 FIX: with lock
        async with self._lock:
            if len(self._connections) >= MAX_CONNECTIONS:
                return False
            # P-7 FIX: max per user
            if len(self._user_conns.get(user_id, set())) >= MAX_PER_USER:
                return False
            conn = WSConnection(ws=ws, user_id=user_id, connection_id=connection_id)
            self._connections[connection_id] = conn
            self._user_conns[user_id].add(connection_id)
            return True

    async def disconnect(self, connection_id: str) -> None:
        async with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn:
                self._user_conns[conn.user_id].discard(connection_id)
                if not self._user_conns[conn.user_id]:
                    del self._user_conns[conn.user_id]

    async def handle_pong(self, connection_id: str) -> None:
        # P-8 FIX: update pong timestamp
        async with self._lock:
            conn = self._connections.get(connection_id)
            if conn:
                conn.last_pong = time.monotonic()

    async def handle_subscribe(self, connection_id: str, topics: List[str]) -> None:
        # P-10 FIX: subscription management
        async with self._lock:
            conn = self._connections.get(connection_id)
            if conn:
                conn.subscriptions.update(topics)

    async def handle_unsubscribe(self, connection_id: str, topics: List[str]) -> None:
        async with self._lock:
            conn = self._connections.get(connection_id)
            if conn:
                conn.subscriptions.difference_update(topics)

    async def broadcast(
        self,
        message_type: WSMessageType,
        data: Dict[str, Any],
        topic: Optional[str] = None,
    ) -> int:
        # P-9 FIX: type validation
        if not isinstance(message_type, WSMessageType):
            raise ValueError(f"Invalid message_type: {message_type}")

        payload = json.dumps({
            "type":      message_type.value,
            "data":      data,
            "timestamp": time.time(),
        })

        async with self._lock:
            connections = list(self._connections.values())

        # P-10 FIX: topic-based filter
        if topic:
            connections = [
                c for c in connections
                if not c.subscriptions or topic in c.subscriptions
            ]

        sent = 0
        dead_ids: List[str] = []
        # P-6 FIX: per-connection error isolation
        for conn in connections:
            try:
                await asyncio.wait_for(conn.ws.send_text(payload), timeout=5.0)
                conn.message_count += 1
                sent += 1
            except (asyncio.TimeoutError, Exception):
                dead_ids.append(conn.connection_id)

        for cid in dead_ids:
            await self.disconnect(cid)
        return sent

    async def send_to_user(
        self, user_id: str, message_type: WSMessageType, data: Dict[str, Any]
    ) -> int:
        async with self._lock:
            conn_ids    = list(self._user_conns.get(user_id, set()))
            connections = [self._connections[cid] for cid in conn_ids if cid in self._connections]

        payload = json.dumps({"type": message_type.value, "data": data, "timestamp": time.time()})
        sent = 0
        dead_ids: List[str] = []
        for conn in connections:
            try:
                await asyncio.wait_for(conn.ws.send_text(payload), timeout=5.0)
                conn.message_count += 1
                sent += 1
            except Exception:
                dead_ids.append(conn.connection_id)
        for cid in dead_ids:
            await self.disconnect(cid)
        return sent

    async def _ping_loop(self) -> None:
        """P-8 FIX: heartbeat loop."""
        while True:
            try:
                await asyncio.sleep(PING_INTERVAL_SEC)
                await self._send_pings()
                await self._evict_stale()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[WSManager] ping loop: %s", exc)

    async def _send_pings(self) -> None:
        async with self._lock:
            connections = list(self._connections.values())
        payload = json.dumps({"type": WSMessageType.PING.value, "timestamp": time.time()})
        for conn in connections:
            try:
                await asyncio.wait_for(conn.ws.send_text(payload), timeout=3.0)
            except Exception:
                pass

    async def _evict_stale(self) -> None:
        """P-8 FIX: remove connections that missed pong."""
        async with self._lock:
            stale = [cid for cid, c in self._connections.items() if c.is_stale]
        for cid in stale:
            logger.info("[WSManager] evicting stale conn=%s", cid)
            await self.disconnect(cid)

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                "total_connections": len(self._connections),
                "total_users":       len(self._user_conns),
                "connections":       [c.to_dict() for c in self._connections.values()],
            }


_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    global _manager
    if _manager is None:
        _manager = WebSocketManager()
    return _manager
