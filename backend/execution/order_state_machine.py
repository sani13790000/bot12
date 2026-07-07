"""
backend/execution/order_state_machine.py
Galaxy Vast AI Trading Platform

BUG-6 FIX: Added TTL-based expiry for stuck orders.
Orders stuck in PENDING/SUBMITTED/OPEN/CLOSING beyond non_terminal_ttl_s
are automatically transitioned to ERROR state via expire_stale_tickets().

State diagram
-------------
    PENDING -> SUBMITTED -> OPEN -> CLOSING -> CLOSED
        |           |         |
        +-> REJECTED +-> CANCELLED  +-> ERROR

    ERROR -> PENDING  (retry allowed)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TRANSITIONS: Dict[str, List[str]] = {
    "PENDING": ["SUBMITTED", "CANCELLED", "REJECTED"],
    "SUBMITTED": ["OPEN", "REJECTED", "CANCELLED"],
    "OPEN": ["CLOSING", "CLOSED", "ERROR"],
    "CLOSING": ["CLOSED", "ERROR"],
    "CLOSED": [],
    "REJECTED": [],
    "CANCELLED": [],
    "ERROR": ["PENDING"],
}

_TERMINAL = {"CLOSED", "REJECTED", "CANCELLED"}
_MAX_TICKETS = 1_000


class OrderStateMachine:
    """
    Tracks the state of every active trade ticket.
    Thread-safe finite state machine with TTL-based expiry.
    """

    # BUG-6 FIX: default TTL for non-terminal states
    _NON_TERMINAL_TTL_S: int = 3600  # 1 hour

    def __init__(self, max_tickets: int = _MAX_TICKETS, non_terminal_ttl_s: int = 3600) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._max: int = max_tickets
        self._ttl_s: int = non_terminal_ttl_s
        # ticket -> (state, history, registered_at_monotonic)
        self._store: OrderedDict[int, Tuple[str, List[Tuple[str, str]], float]] = OrderedDict()

    def register(self, ticket: int) -> None:
        """Register new ticket in PENDING state. No-op if already registered."""
        with self._lock:
            if ticket in self._store:
                return
            self._evict_if_full()
            self._store[ticket] = ("PENDING", [("PENDING", self._now())], time.monotonic())
            logger.debug("[OSM] ticket=%d registered", ticket)

    def transition(self, ticket: int, new_state: str) -> None:
        """
        Move ticket to new_state.
        Raises KeyError if ticket unknown, ValueError if transition invalid.
        """
        with self._lock:
            if ticket not in self._store:
                self._evict_if_full()
                self._store[ticket] = ("PENDING", [("PENDING", self._now())], time.monotonic())

            current, history, registered_at = self._store[ticket]
            if new_state == current:
                return

            allowed = _TRANSITIONS.get(current, [])
            if new_state not in allowed:
                raise ValueError(
                    f"[OSM] ticket={ticket}: {current!r} -> {new_state!r} "
                    f"not allowed (allowed: {allowed})"
                )

            history.append((new_state, self._now()))
            self._store[ticket] = (new_state, history, registered_at)
            logger.info("[OSM] ticket=%d: %s -> %s", ticket, current, new_state)

    def get_state(self, ticket: int) -> Optional[str]:
        """Return current state, or None if ticket unknown."""
        with self._lock:
            entry = self._store.get(ticket)
            return entry[0] if entry else None

    def get_history(self, ticket: int) -> List[Tuple[str, str]]:
        """Return full transition history as [(state, iso_timestamp), ...]."""
        with self._lock:
            entry = self._store.get(ticket)
            return list(entry[1]) if entry else []

    def get_age_seconds(self, ticket: int) -> Optional[float]:
        """Return seconds since ticket was registered."""
        with self._lock:
            entry = self._store.get(ticket)
            return time.monotonic() - entry[2] if entry else None

    def is_terminal(self, ticket: int) -> bool:
        """Return True when ticket is in terminal state."""
        state = self.get_state(ticket)
        return state in _TERMINAL if state else False

    def active_tickets(self) -> List[int]:
        """Return tickets not yet in terminal state."""
        with self._lock:
            return [t for t, (s, _, _reg) in self._store.items() if s not in _TERMINAL]

    def stale_tickets(self) -> List[int]:
        """Return non-terminal tickets that have exceeded TTL."""
        now = time.monotonic()
        with self._lock:
            return [
                t
                for t, (s, _, reg) in self._store.items()
                if s not in _TERMINAL and s != "ERROR" and (now - reg) > self._ttl_s
            ]

    def expire_stale_tickets(self) -> int:
        """
        BUG-6 FIX: Mark orders stuck beyond TTL as ERROR.
        Call periodically from a background task (e.g. every 60s).
        Returns count of expired tickets.
        """
        now = time.monotonic()
        expired = 0
        with self._lock:
            for ticket, (state, history, registered_at) in list(self._store.items()):
                if state not in _TERMINAL and state != "ERROR":
                    age_s = now - registered_at
                    if age_s > self._ttl_s:
                        history.append(("ERROR", self._now()))
                        self._store[ticket] = ("ERROR", history, registered_at)
                        logger.warning(
                            "[OSM] ticket=%d expired after %.0fs in state %s -> ERROR",
                            ticket,
                            age_s,
                            state,
                        )
                        expired += 1
        return expired

    def stats(self) -> Dict[str, int]:
        """Return count of tickets per state."""
        counts: Dict[str, int] = {}
        with self._lock:
            for state, _, _ in self._store.values():
                counts[state] = counts.get(state, 0) + 1
        return counts

    def _evict_if_full(self) -> None:
        """Remove oldest terminal ticket when store is at capacity."""
        while len(self._store) >= self._max:
            for ticket, (state, _, _reg) in self._store.items():
                if state in _TERMINAL:
                    del self._store[ticket]
                    logger.debug("[OSM] evicted terminal ticket=%d", ticket)
                    break
            else:
                self._store.popitem(last=False)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


# Module-level singleton
order_state_machine = OrderStateMachine()
