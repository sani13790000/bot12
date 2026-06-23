"""
backend/analysis/session_manager.py — Phase S
S-3: Real market session detection using UTC time.

Problem: decision_engine.py used hardcoded string 'london' in market_context.
Fix: SessionManager.get_session(dt) -> SessionInfo with is_tradeable + score.

Sessions (UTC):
  SYDNEY:    21:00 - 06:00
  TOKYO:     00:00 - 09:00
  LONDON:    07:00 - 16:00
  NEW_YORK:  12:00 - 21:00
  OVERLAP_LN_NY: 12:00 - 16:00
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("analysis.session_manager")


class SessionType(str, Enum):
    SYDNEY        = "sydney"
    TOKYO         = "tokyo"
    LONDON        = "london"
    NEW_YORK      = "new_york"
    OVERLAP_LN_NY = "overlap_ln_ny"
    CLOSED        = "closed"
    WEEKEND       = "weekend"


_SESSION_HOURS: Dict[SessionType, Tuple[int, int, int, int]] = {
    SessionType.SYDNEY:        (21,  0, 30,  0),
    SessionType.TOKYO:         ( 0,  0,  9,  0),
    SessionType.LONDON:        ( 7,  0, 16,  0),
    SessionType.NEW_YORK:      (12,  0, 21,  0),
    SessionType.OVERLAP_LN_NY: (12,  0, 16,  0),
}

_TRADEABLE = {
    SessionType.LONDON, SessionType.NEW_YORK,
    SessionType.OVERLAP_LN_NY, SessionType.TOKYO, SessionType.SYDNEY,
}

_SESSION_SCORE: Dict[SessionType, float] = {
    SessionType.OVERLAP_LN_NY: 1.0,
    SessionType.LONDON:        0.9,
    SessionType.NEW_YORK:      0.85,
    SessionType.TOKYO:         0.7,
    SessionType.SYDNEY:        0.6,
    SessionType.CLOSED:        0.0,
    SessionType.WEEKEND:       0.0,
}


@dataclass(frozen=True)
class SessionInfo:
    session:      SessionType
    is_tradeable: bool
    score:        float
    utc_hour:     int
    is_weekend:   bool


def _in_range(minutes: int, oh: int, om: int, ch: int, cm: int) -> bool:
    start = oh * 60 + om
    end   = ch * 60 + cm
    if end > start:
        return start <= minutes < end
    return minutes >= start or minutes < end


class SessionManager:
    """S-3: Determines current Forex market session from UTC datetime."""

    def get_session(self, dt: Optional[datetime] = None) -> SessionInfo:
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if dt.weekday() >= 5:
            return SessionInfo(
                session=SessionType.WEEKEND, is_tradeable=False,
                score=0.0, utc_hour=dt.hour, is_weekend=True,
            )

        mins = dt.hour * 60 + dt.minute

        if _in_range(mins, *_SESSION_HOURS[SessionType.OVERLAP_LN_NY]):
            sess = SessionType.OVERLAP_LN_NY
        elif _in_range(mins, *_SESSION_HOURS[SessionType.LONDON]):
            sess = SessionType.LONDON
        elif _in_range(mins, *_SESSION_HOURS[SessionType.NEW_YORK]):
            sess = SessionType.NEW_YORK
        elif _in_range(mins, *_SESSION_HOURS[SessionType.TOKYO]):
            sess = SessionType.TOKYO
        elif _in_range(mins, *_SESSION_HOURS[SessionType.SYDNEY]):
            sess = SessionType.SYDNEY
        else:
            sess = SessionType.CLOSED

        return SessionInfo(
            session=sess, is_tradeable=sess in _TRADEABLE,
            score=_SESSION_SCORE.get(sess, 0.0),
            utc_hour=dt.hour, is_weekend=False,
        )

    def is_tradeable(self, dt: Optional[datetime] = None) -> bool:
        return self.get_session(dt).is_tradeable

    def best_sessions(self) -> List[SessionType]:
        return sorted(
            [s for s in SessionType if s not in (SessionType.CLOSED, SessionType.WEEKEND)],
            key=lambda s: _SESSION_SCORE.get(s, 0),
            reverse=True,
        )


_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _session_manager


def get_current_session_info(dt: Optional[datetime] = None) -> SessionInfo:
    return _session_manager.get_session(dt)
