"""
Galaxy Vast AI Trading Platform
Semi-Auto Execution Mode - Production Reliability v2

FIXES:
  R-5:     Memory leak fix - terminal signals evicted after TTL.
  T-11:    datetime.utcnow() -> datetime.now(timezone.utc)
  BUG-SA-1: Race condition in _sweep_terminal_signals.
            After releasing self._lock, self._pending.get(sid) was called
            outside the lock. FIX: snapshot (sid, sig, cb) tuple inside lock.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("execution.semi_auto")

_TERMINAL_SIGNAL_TTL_S: int = 300


class PendingSignalStatus(str, Enum):
    WAITING  = "WAITING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED  = "EXPIRED"
    EXECUTED = "EXECUTED"


_TERMINAL_STATES = frozenset({
    PendingSignalStatus.APPROVED,
    PendingSignalStatus.REJECTED,
    PendingSignalStatus.EXPIRED,
    PendingSignalStatus.EXECUTED,
})


@dataclass
class PendingSignal:
    signal_id:        str   = field(default_factory=lambda: str(uuid.uuid4()))
    symbol:           str   = ""
    action:           str   = ""
    entry_price:      float = 0.0
    stop_loss:        float = 0.0
    take_profit_1:    float = 0.0
    take_profit_2:    float = 0.0
    lot_size:         float = 0.0
    risk_percent:     float = 0.0
    confidence_score: float = 0.0
    rr_ratio:         float = 0.0
    market_context:   str   = ""
    created_at:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at:       datetime = field(init=False)
    status:           PendingSignalStatus = PendingSignalStatus.WAITING
    approved_by:      Optional[int]      = None
    approved_at:      Optional[datetime] = None
    message_id:       Optional[int]      = None
    terminal_at:      Optional[datetime] = None

    def __post_init__(self) -> None:
        timeout_seconds = getattr(settings, "SEMI_AUTO_CONFIRMATION_TIMEOUT_SECONDS", 300)
        self.expires_at = self.created_at + timedelta(seconds=timeout_seconds)

    @property
    def is_expired(self) -> bool: return datetime.now(timezone.utc) > self.expires_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, int((self.expires_at - datetime.now(timezone.utc)).total_seconds()))

    @property
    def is_terminal(self) -> bool: return self.status in _TERMINAL_STATES


class SemiAutoManager:
    def __init__(self) -> None:
        self._pending:               Dict[str, PendingSignal] = {}
        self._lock                 = asyncio.Lock()
        self._on_approved_callbacks: Dict[str, Callable]      = {}
        self._on_rejected_callbacks: Dict[str, Callable]      = {}
        self._cleanup_task:          Optional[asyncio.Task]   = None
        logger.info("SemiAutoManager initialised (R-5: terminal-state eviction enabled)")

    async def start(self) -> None:
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SemiAutoManager cleanup loop started")

    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try: await self._cleanup_task
            except asyncio.CancelledError: pass

    async def submit_for_approval(self, signal: PendingSignal,
                                   on_approved: Optional[Callable] = None,
                                   on_rejected: Optional[Callable] = None) -> str:
        async with self._lock:
            self._pending[signal.signal_id] = signal
            if on_approved: self._on_approved_callbacks[signal.signal_id] = on_approved
            if on_rejected: self._on_rejected_callbacks[signal.signal_id] = on_rejected
        logger.info("Signal %s pending %s %s", signal.signal_id[:8], signal.symbol, signal.action)
        return signal.signal_id

    async def approve_signal(self, signal_id: str, approved_by_user_id: int) -> Optional[PendingSignal]:
        async with self._lock:
            signal = self._pending.get(signal_id)
            if not signal: logger.warning("Signal %s not found", signal_id[:8]); return None
            if signal.is_expired: signal.status = PendingSignalStatus.EXPIRED; signal.terminal_at = datetime.now(timezone.utc); return None
            if signal.status != PendingSignalStatus.WAITING: return None
            signal.status = PendingSignalStatus.APPROVED
            signal.approved_by = approved_by_user_id
            signal.approved_at = datetime.now(timezone.utc)
            signal.terminal_at = datetime.now(timezone.utc)
        logger.info("Signal %s approved by %d", signal_id[:8], approved_by_user_id)
        cb = self._on_approved_callbacks.get(signal_id)
        if cb: asyncio.create_task(cb(signal))
        asyncio.create_task(self._deferred_evict(signal_id, delay=5.0))
        return signal

    async def reject_signal(self, signal_id: str, rejected_by_user_id: int) -> Optional[PendingSignal]:
        async with self._lock:
            signal = self._pending.get(signal_id)
            if not signal or signal.status != PendingSignalStatus.WAITING: return None
            signal.status = PendingSignalStatus.REJECTED
            signal.terminal_at = datetime.now(timezone.utc)
        logger.info("Signal %s rejected by %d", signal_id[:8], rejected_by_user_id)
        cb = self._on_rejected_callbacks.get(signal_id)
        if cb: asyncio.create_task(cb(signal))
        asyncio.create_task(self._deferred_evict(signal_id, delay=5.0))
        return signal

    async def mark_executed(self, signal_id: str) -> None:
        async with self._lock:
            signal = self._pending.get(signal_id)
            if signal and signal.status == PendingSignalStatus.APPROVED:
                signal.status = PendingSignalStatus.EXECUTED
                signal.terminal_at = datetime.now(timezone.utc)
                logger.info("Signal %s marked EXECUTED", signal_id[:8])
        asyncio.create_task(self._deferred_evict(signal_id, delay=5.0))

    async def get_pending_signals(self) -> List[PendingSignal]:
        async with self._lock:
            return [s for s in self._pending.values() if s.status == PendingSignalStatus.WAITING and not s.is_expired]

    async def get_signal(self, signal_id: str) -> Optional[PendingSignal]:
        async with self._lock: return self._pending.get(signal_id)

    def pending_count(self) -> int: return len(self._pending)

    async def _deferred_evict(self, signal_id: str, delay: float = 5.0) -> None:
        await asyncio.sleep(delay)
        await self._evict_signal(signal_id)

    async def _evict_signal(self, signal_id: str) -> None:
        async with self._lock:
            removed = self._pending.pop(signal_id, None)
            self._on_approved_callbacks.pop(signal_id, None)
            self._on_rejected_callbacks.pop(signal_id, None)
        if removed: logger.debug("R-5: Signal %s (%s) evicted", signal_id[:8], removed.status)

    async def _cleanup_loop(self) -> None:
        while True:
            try: await asyncio.sleep(30); await self._sweep_terminal_signals()
            except asyncio.CancelledError: break
            except Exception as exc: logger.error("SemiAuto cleanup error: %s", exc)

    async def _sweep_terminal_signals(self) -> None:
        now = datetime.now(timezone.utc)
        # BUG-SA-1 FIX: snapshot (sid, sig, cb) INSIDE lock so no dict access
        # after lock release. Old code: released lock then called .get(sid) outside.
        to_expire: List[Tuple[str, PendingSignal, Optional[Callable]]] = []
        to_evict:  List[str] = []
        async with self._lock:
            for sid, sig in list(self._pending.items()):
                if sig.status == PendingSignalStatus.WAITING and sig.is_expired:
                    sig.status = PendingSignalStatus.EXPIRED
                    sig.terminal_at = now
                    cb = self._on_rejected_callbacks.get(sid)
                    to_expire.append((sid, sig, cb))
                elif sig.is_terminal and sig.terminal_at:
                    if (now - sig.terminal_at).total_seconds() >= _TERMINAL_SIGNAL_TTL_S:
                        to_evict.append(sid)
        for sid, sig, cb in to_expire:
            if cb: asyncio.create_task(cb(sig))
            logger.info("Signal %s expired", sid[:8])
            asyncio.create_task(self._deferred_evict(sid, delay=5.0))
        for sid in to_evict:
            await self._evict_signal(sid)
        if to_expire or to_evict:
            logger.info("R-5: sweep expired=%d evicted=%d remaining=%d",
                        len(to_expire), len(to_evict), len(self._pending))


semi_auto_manager = SemiAutoManager()
