"""
backend/execution/semi_auto.py
Galaxy Vast AI — Semi-Automatic Trading Handler

Handles human-in-the-loop confirmations for high-risk or oversized trades.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from backend.core.logger import get_logger

LOGGER = get_logger(__name__)


class SemiAutoStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class SemiAutoRequest:
    request_id: str
    symbol: str
    direction: str
    size: float
    risk_score: float
    status: SemiAutoStatus = SemiAutoStatus.PENDING
    created_at: datetime = datetime.now(timezone.utc)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
        if self.expires_at is None:
            self.expires_at = self.created_at.replace(minute=self.created_at.minute + 5)


class SemiAutoController:
    """Manages pending semi-auto trade confirmations."""

    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self.default_ttl = default_ttl_seconds
        self._pending: Dict[str, SemiAutoRequest] = {}
        self._lock = asyncio.Lock()

    async def create_request(
        self,
        request_id: str,
        symbol: str,
        direction: str,
        size: float,
        risk_score: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SemiAutoRequest:
        req = SemiAutoRequest(
            request_id=request_id,
            symbol=symbol,
            direction=direction,
            size=size,
            risk_score=risk_score,
            metadata=metadata or {},
        )
        async with self._lock:
            self._pending[request_id] = req
        LOGGER.info("Semi-auto request %s created for %s", request_id, symbol)
        return req

    async def approve(self, request_id: str) -> Optional[SemiAutoRequest]:
        async with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != SemiAutoStatus.PENDING:
                return None
            req.status = SemiAutoStatus.APPROVED
            del self._pending[request_id]
        LOGGER.info("Semi-auto request %s approved", request_id)
        return req

    async def reject(self, request_id: str) -> Optional[SemiAutoRequest]:
        async with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != SemiAutoStatus.PENDING:
                return None
            req.status = SemiAutoStatus.REJECTED
            del self._pending[request_id]
        LOGGER.info("Semi-auto request %s rejected", request_id)
        return req

    async def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [rid for rid, req in self._pending.items() if req.expires_at and req.expires_at <= now]
            for rid in expired:
                self._pending[rid].status = SemiAutoStatus.EXPIRED
                del self._pending[rid]
        return len(expired)
