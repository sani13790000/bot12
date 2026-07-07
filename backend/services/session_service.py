"""
backend/services/session_service.py -- Phase-C fix

C-7  UserSessionManager._client was calling get_supabase_client_sync()
     but that may return None on cold start.  FIX: use db wrapper
     (DatabaseWrapper) which handles its own executor + retry.

Two responsibilities:
  1. SessionService  -- trading session detection (no I/O)
  2. UserSessionManager -- refresh-token lifecycle in DB
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class SessionType(Enum):
    NONE    = "bdon sesn"
    SYDNEY  = "Sydney"
    TOKYO   = "Tokyo"
    LONDON  = "London"
    NEWYORK = "New York"
    OVERLAP = "London/NY Overlap"


class KillZoneType(Enum):
    NONE         = "bdon Kill Zone"
    ASIAN        = "Asian Kill Zone"
    LONDON_OPEN  = "London Open Kill Zone"
    NY_OPEN      = "NY Oen Kill Zone"
    NY_PM        = "NY PM Kill Zone"
    LONDON_CLOSE = "London Close Kill Zone"


@dataclass
class SessionInfo:
    session_type:           SessionType  = SessionType.NONE
    kill_zone:              KillZoneType = KillZoneType.NONE
    is_overlap:             bool         = False
    is_kill_zone:           bool         = False
    can_trade:              bool         = False
    session_score:          float        = 0.0
    session_name_fa:        str          = "bdon sesn"
    kill_zone_name_fa:      str          = "bdon Kill Zone"
    utc_hour:               int          = 0
    utc_minute:             int          = 0
    minutes_to_london_open: int          = 0
    minutes_to_ny_open:     int          = 0
    active_sessions:        List[str]    = field(default_factory=list)


class SessionService:
    """Pure business logic -- zero I/O."""

    _SESSION_SCORES: Dict[Any, float] = {
        KillZoneType.LONDON_OPEN:  100.0,
        KillZoneType.NY_OPEN:      100.0,
        SessionType.OVERLAP:        90.0,
        KillZoneType.NY_PM:         75.0,
        SessionType.LONDON:          70.0,
        SessionType.NEWYORK:         65.0,
        KillZoneType.ASIAN:          50.0,
        KillZoneType.LONDON_CLOSE:   45.0,
        SessionType.TOKYO:           40.0,
        SessionType.SYDNEY:          25.0,
        SessionType.NONE:             0.0,
    }

    def __init__(
        self,
        use_sydney: bool      = False,
        use_tokyo: bool       = True,
        use_london: bool      = True,
        use_newyork: bool     = True,
        only_kill_zones: bool = False,
        prefer_overlap: bool  = False,
    ) -> None:
        self.use_sydney      = use_sydney
        self.use_tokyo       = use_tokyo
        self.use_london      = use_london
        self.use_newyork     = use_newyork
        self.only_kill_zones = only_kill_zones
        self.prefer_overlap  = prefer_overlap

    @staticmethod
    def _in_range(h: int, m: int, sh: int, sm: int, eh: int, em: int) -> bool:
        cur = h * 60 + m
        s   = sh * 60 + sm
        e   = eh * 60 + em
        if s <= e:
            return s <= cur < e
        return cur >= s or cur < e

    def get_session(self, dt: Optional[datetime] = None) -> SessionInfo:
        if dt is None:
            dt = datetime.now(timezone.utc)
        h, m = dt.hour, dt.minute
        info = SessionInfo(utc_hour=h, utc_minute=m)
        info.minutes_to_london_open = ((8 * 60) - (h * 60 + m)) % (24 * 60)
        info.minutes_to_ny_open     = ((13 * 60) - (h * 60 + m)) % (24 * 60)

        active: List[str] = []
        if self.use_sydney  and self._in_range(h, m, 22, 0, 7, 0):  active.append("Sydney")
        if self.use_tokyo   and self._in_range(h, m,  0, 0, 9, 0):  active.append("Tokyo")
        if self.use_london  and self._in_range(h, m,  8, 0, 17, 0): active.append("London")
        if self.use_newyork and self._in_range(h, m, 13, 0, 22, 0): active.append("New York")
        info.active_sessions = active

        if "London" in active and "New York" in active:
            info.session_type  = SessionType.OVERLAP
            info.is_overlap    = True
        elif "London" in active:
            info.session_type  = SessionType.LONDON
        elif "New York" in active:
            info.session_type  = SessionType.NEWYORK
        elif "Tokyo" in active:
            info.session_type  = SessionType.TOKYO
        elif "Sydney" in active:
            info.session_type  = SessionType.SYDNEY

        if   self._in_range(h, m,  2, 0,  5, 0): info.kill_zone = KillZoneType.ASIAN
        elif self._in_range(h, m,  8, 0, 10, 0): info.kill_zone = KillZoneType.LONDON_OPEN
        elif self._in_range(h, m, 13, 0, 15, 0): info.kill_zone = KillZoneType.NY_OPEN
        elif self._in_range(h, m, 19, 0, 21, 0): info.kill_zone = KillZoneType.NY_PM
        elif self._in_range(h, m, 15, 0, 17, 0): info.kill_zone = KillZoneType.LONDON_CLOSE

        info.is_kill_zone     = info.kill_zone != KillZoneType.NONE
        info.session_name_fa  = info.session_type.value
        info.kill_zone_name_fa = info.kill_zone.value
        score_key = info.kill_zone if info.is_kill_zone else info.session_type
        info.session_score = self._SESSION_SCORES.get(score_key, 0.0)
        if self.only_kill_zones:
            info.can_trade = info.is_kill_zone
        elif self.prefer_overlap:
            info.can_trade = info.is_overlap or info.is_kill_zone
        else:
            info.can_trade = info.session_type != SessionType.NONE
        return info


class UserSessionManager:
    """
    Manages refresh tokens stored in `refresh_tokens` table.

    C-7 FIX: uses DatabaseWrapper (db) instead of raw Supabase client
    to avoid cold-start None issues.
    """

    _TABLE = "refresh_tokens"

    async def revoke_session(self, jti: str) -> bool:
        """Mark a single refresh token as revoked."""
        try:
            from backend.database import db
            now = datetime.now(timezone.utc).isoformat()
            await db.update(self._TABLE, {"jti": jti}, {"revoked": True, "revoked_at": now})
            log.info("session_revoked jti=%s", jti)
            return True
        except Exception:
            log.exception("revoke_session failed jti=%s", jti)
            return False

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """
        Revoke ALL active refresh tokens for user.
        C-7 FIX: real DB write via run_in_executor.
        Returns count of revoked sessions.
        """
        try:
            from backend.database.connection import get_supabase_client_sync
            now = datetime.now(timezone.utc).isoformat()
            def _revoke_all():
                client = get_supabase_client_sync()
                if client is None:
                    return 0
                result = (
                    client.table(self._TABLE)
                    .update({"revoked": True, "revoked_at": now})
                    .eq("user_id", user_id)
                    .eq("revoked", False)
                    .execute()
                )
                return len(result.data) if result.data else 0
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(None, _revoke_all)
            log.info("revoked_all_sessions user_id=%s count=%d", user_id, count)
            return count
        except Exception:
            log.exception("revoke_all_user_sessions failed user_id=%s", user_id)
            return 0

    async def get_active_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            from backend.database import db
            now = datetime.now(timezone.utc).isoformat()
            sessions = await db.select_many(self._TABLE, filters={"user_id": user_id, "revoked": False}, limit=50)
            return [s for s in sessions if s.get("expires_at", "") > now]
        except Exception:
            log.exception("get_active_sessions failed user_id=%s", user_id)
            return []


session_service = SessionService()
user_session_manager = UserSessionManager()
