"""
backend/analysis/session_manager.py — Phase 5: DST-aware session manager

CHANGES vs previous version:
  P5-SM-1: DST-aware session boundaries via zoneinfo (not hardcoded UTC hours)
  P5-SM-2: broker_offset param for broker_time → session conversion
  P5-SM-3: clock injection for testability
  P5-SM-4: FX weekend detection fix (closes Fri 22:00, opens Sun 22:00 UTC)
  P5-SM-5: replace(tzinfo) → ensure_utc() from timezone_utils
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from core.timezone_utils import (
    broker_time_to_utc,
    ensure_utc,
    is_dst_active,
)
from core.timezone_utils import (
    now as tz_now,
)

logger = logging.getLogger("analysis.session_manager")


class SessionType(str, Enum):
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP_LN_NY = "overlap_ln_ny"
    CLOSED = "closed"
    WEEKEND = "weekend"


_TRADEABLE = {
    SessionType.LONDON,
    SessionType.NEW_YORK,
    SessionType.OVERLAP_LN_NY,
    SessionType.TOKYO,
    SessionType.SYDNEY,
}

_SESSION_SCORE: Dict[SessionType, float] = {
    SessionType.OVERLAP_LN_NY: 1.0,
    SessionType.LONDON: 0.9,
    SessionType.NEW_YORK: 0.85,
    SessionType.TOKYO: 0.7,
    SessionType.SYDNEY: 0.6,
    SessionType.CLOSED: 0.0,
    SessionType.WEEKEND: 0.0,
}

# DST-aware session zones
_SESSION_ZONES = {
    "london": ZoneInfo("Europe/London"),
    "new_york": ZoneInfo("America/New_York"),
    "tokyo": ZoneInfo("Asia/Tokyo"),
    "sydney": ZoneInfo("Australia/Sydney"),
}


@dataclass(frozen=True)
class SessionInfo:
    session: SessionType
    is_tradeable: bool
    score: float
    utc_hour: int
    is_weekend: bool
    dst_active: bool = False  # P5-SM-1: DST info
    broker_offset_h: int = 0  # P5-SM-2: broker UTC offset


def _in_range_utc(utc_dt: datetime, zone: str, oh: int, om: int, ch: int, cm: int) -> bool:
    """P5-SM-1: Check if utc_dt falls within local session hours, DST-aware."""
    try:
        tz = ZoneInfo(zone)
    except Exception:
        return False
    local = utc_dt.astimezone(tz)
    t = local.hour * 60 + local.minute
    start = oh * 60 + om
    end = ch * 60 + cm
    if end > start:
        return start <= t < end
    # wraps midnight
    return t >= start or t < end


class SessionManager:
    """
    P5-SM: DST-aware Forex market session detection.

    Unlike the previous version (hardcoded UTC hours), this class converts
    UTC time to each market's local timezone and checks against LOCAL
    session hours — automatically handling DST transitions.
    """

    def get_session(
        self,
        dt: Optional[datetime] = None,
        broker_tz: str = "EET",
    ) -> SessionInfo:
        """
        Determine current/given session with full DST support.

        Args:
            dt:         UTC-aware datetime (or None for now).
                        If naive, assumed UTC (P5-SM-5: use ensure_utc not replace).
            broker_tz:  Broker timezone for offset reporting only.
        """
        # P5-SM-5: ensure UTC-aware
        if dt is None:
            dt = tz_now()
        dt = ensure_utc(dt)

        # P5-SM-4: Correct FX weekend detection
        weekday = dt.weekday()  # 0=Mon, 5=Sat, 6=Sun
        utc_hour = dt.hour
        if weekday == 5:  # Saturday — always closed
            return self._make(SessionType.WEEKEND, dt, broker_tz, True)
        if weekday == 6 and utc_hour < 22:  # Sunday before 22:00
            return self._make(SessionType.WEEKEND, dt, broker_tz, True)
        if weekday == 4 and utc_hour >= 22:  # Friday after 22:00
            return self._make(SessionType.WEEKEND, dt, broker_tz, True)

        # P5-SM-1: DST-aware session detection using local clocks
        ln_open = _in_range_utc(dt, "Europe/London", 8, 0, 17, 0)
        ny_open = _in_range_utc(dt, "America/New_York", 8, 0, 17, 0)
        tok_open = _in_range_utc(dt, "Asia/Tokyo", 9, 0, 18, 0)
        syd_open = _in_range_utc(dt, "Australia/Sydney", 8, 0, 17, 0)

        if ln_open and ny_open:
            sess = SessionType.OVERLAP_LN_NY
        elif ln_open:
            sess = SessionType.LONDON
        elif ny_open:
            sess = SessionType.NEW_YORK
        elif tok_open:
            sess = SessionType.TOKYO
        elif syd_open:
            sess = SessionType.SYDNEY
        else:
            sess = SessionType.CLOSED

        return self._make(sess, dt, broker_tz, False)

    def _make(
        self,
        sess: SessionType,
        dt: datetime,
        broker_tz: str,
        is_weekend: bool,
    ) -> SessionInfo:
        from zoneinfo import ZoneInfo

        from core.timezone_utils import _BROKER_ZONES

        try:
            btz = ZoneInfo(_BROKER_ZONES.get(broker_tz.upper(), broker_tz))
            broker_offset_h = int(dt.astimezone(btz).utcoffset().total_seconds() / 3600)
        except Exception:
            broker_offset_h = 0

        dst_active = False
        try:
            dst_active = is_dst_active("Europe/London", dt)
        except Exception:
            pass

        return SessionInfo(
            session=sess,
            is_tradeable=sess in _TRADEABLE,
            score=_SESSION_SCORE.get(sess, 0.0),
            utc_hour=dt.hour,
            is_weekend=is_weekend,
            dst_active=dst_active,
            broker_offset_h=broker_offset_h,
        )

    def is_tradeable(
        self,
        dt: Optional[datetime] = None,
        broker_tz: str = "EET",
    ) -> bool:
        return self.get_session(dt, broker_tz).is_tradeable

    def best_sessions(self) -> List[SessionType]:
        return sorted(
            [s for s in SessionType if s not in (SessionType.CLOSED, SessionType.WEEKEND)],
            key=lambda s: _SESSION_SCORE.get(s, 0),
            reverse=True,
        )

    def get_session_from_broker_time(
        self,
        broker_dt: datetime,
        broker_tz: str = "EET",
    ) -> SessionInfo:
        """
        P5-SM-2: Convert broker_time → UTC first, then detect session.
        Safe for MT5 server_time which may be in EET (UTC+2/+3).
        """
        utc_dt = broker_time_to_utc(broker_dt, broker_tz)
        return self.get_session(utc_dt, broker_tz)


# singleton
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _session_manager


def get_current_session_info(
    dt: Optional[datetime] = None,
    broker_tz: str = "EET",
) -> SessionInfo:
    return _session_manager.get_session(dt, broker_tz)
