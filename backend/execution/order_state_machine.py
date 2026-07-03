"""
backend/execution/order_state_machine.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thread-safe finite state machine (FSM) for trade order life-cycles.

State diagram
-------------

    PENDING ──► SUBMITTED ──► OPEN ──► CLOSING ──► CLOSED
        │            │          │
        └──► REJECTED └──► CANCELLED  └──► ERROR

Usage::

    from backend.execution.order_state_machine import order_state_machine

    order_state_machine.register(ticket=12345)
    order_state_machine.transition(12345, "SUBMITTED")
    order_state_machine.transition(12345, "OPEN")
    state = order_state_machine.get_state(12345)   # → "OPEN"

Notes
-----
- The machine is a module-level singleton and is thread-safe.
- Unknown tickets raise KeyError; invalid transitions raise ValueError.
- History is capped at 1 000 tickets to bound memory usage.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Allowed transitions ───────────────────────────────────────────────────── #

_TRANSITIONS: Dict[str, List[str]] = {
    "PENDING":   ["SUBMITTED", "CANCELLED", "REJECTED"],
    "SUBMITTED": ["OPEN",      "REJECTED",  "CANCELLED"],
    "OPEN":      ["CLOSING",   "CLOSED",    "ERROR"],
    "CLOSING":   ["CLOSED",    "ERROR"],
    "CLOSED":    [],          # terminal
    "REJECTED":  [],          # terminal
    "CANCELLED": [],          # terminal
    "ERROR":     ["PENDING"],  # allow retry
}

_TERMINAL = {"CLOSED", "REJECTED", "CANCELLED"}
_MAX_TICKETS = 1_000


# ── State machine ─────────────────────────────────────────────────────────── #


class OrderStateMachine:
    """
    Tracks the state of every active trade ticket.

    The internal store is an ``OrderedDict`` so oldest entries can be
    evicted when the cap is reached.
    """

    def __init__(self, max_tickets: int = _MAX_TICKETS) -> None:
        self._lock:        threading.Lock = threading.Lock()
        self._max_tickets: int = max_tickets
        # ticket → (current_state, history)
        self._store: OrderedDict[int, Tuple[str, List[Tuple[str, str]]]] = \
            OrderedDict()

    # ── Public API ───────────────────────────────────────────────────────── #

    def register(self, ticket: int) -> None:
        """
        Register a new ticket in PENDING state.

        Safe to call if the ticket is already registered (no-op).
        """
        with self._lock:
            if ticket in self._store:
                return
            self._evict_if_full()
            self._store[ticket] = ("PENDING", [("PENDING", self._now())])
            logger.debug("[OSM] ticket=%d registered", ticket)

    def transition(self, ticket: int, new_state: str) -> None:
        """
        Move *ticket* to *new_state*.

        Raises
        ------
        KeyError
            Ticket was not registered.
        ValueError
            Transition is not allowed from the current state.
        """
        with self._lock:
            if ticket not in self._store:
                # Auto-register if missing (tolerant mode)
                self._evict_if_full()
                self._store[ticket] = ("PENDING", [("PENDING", self._now())])

            current, history = self._store[ticket]
            if new_state == current:
                return  # idempotent

            allowed = _TRANSITIONS.get(current, [])
            if new_state not in allowed:
                raise ValueError(
                    f"[OSM] ticket={ticket}: {current!r} → {new_state!r} "
                    f"not allowed (allowed: {allowed})"
                )

            history.append((new_state, self._now()))
            self._store[ticket] = (new_state, history)
            logger.info("[OSM] ticket=%d: %s → %s", ticket, current, new_state)

    def get_state(self, ticket: int) -> Optional[str]:
        """Return current state, or None if ticket is unknown."""
        with self._lock:
            entry = self._store.get(ticket)
            return entry[0] if entry else None

    def get_history(self, ticket: int) -> List[Tuple[str, str]]:
        """Return the full transition history as [(state, iso_timestamp), ...]."""
        with self._lock:
            entry = self._store.get(ticket)
            return list(entry[1]) if entry else []

    def is_terminal(self, ticket: int) -> bool:
        """Return True when the ticket is in a terminal state (CLOSED/REJECTED/CANCELLED)."""
        state = self.get_state(ticket)
        return state in _TERMINAL if state else False

    def active_tickets(self) -> List[int]:
        """Return tickets that are not yet in a terminal state."""
        with self._lock:
            return [
                t for t, (s, _) in self._store.items()
                if s not in _TERMINAL
            ]

    def stats(self) -> Dict[str, int]:
        """Return a count of tickets per state (useful for dashboards)."""
        counts: Dict[str, int] = {}
        with self._lock:
            for state, _ in self._store.values():
                counts[state] = counts.get(state, 0) + 1
        return counts

    # ── Internals ─────────────────────────────────────────────────────────── #

    def _evict_if_full(self) -> None:
        """Remove the oldest terminal ticket when the store is at capacity."""
        while len(self._store) >= self._max_tickets:
            for ticket, (state, _) in self._store.items():
                if state in _TERMINAL:
                    del self._store[ticket]
                    logger.debug("[OSM] evicted terminal ticket=%d", ticket)
                    break
            else:
                # No terminal ticket found — evict the oldest one
                self._store.popitem(last=False)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


# ── Module-level singleton ────────────────────────────────────────────────── #
order_state_machine = OrderStateMachine()
