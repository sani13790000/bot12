"""
backend/services/session_service.py

دو مسئولیت جداگانه:
  1. SessionService  — محاسبه سشن‌های معاملاتی (Sydney/Tokyo/London/NY)
  2. UserSessionManager — مدیریت refresh-token های کاربران در DB

FIX: revoke_all_user_sessions() و revoke_session() با DB write واقعی پیاده‌سازی شد.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ────────────────────────────────────────────────
class SessionType(Enum):
    NONE    = "بدون سشن"
    SYDNEY  = "Sydney"
    TOKYO   = "Tokyo"
    LONDON  = "London"
    NEWYORK = "New York"
    OVERLAP = "London/NY Overlap"


class KillZoneType(Enum):
    NONE         = "بدون Kill Zone"
    ASIAN        = "Asian Kill Zone"
    LONDON_OPEN  = "London Open Kill Zone"
    NY_OPEN      = "NY Open Kill Zone"
    NY_PM        = "NY PM Kill Zone"
    LONDON_CLOSE = "London Close Kill Zone"


@dataclass
class SessionInfo:
    session_type: SessionType       = SessionType.NONE
    kill_zone: KillZoneType         = KillZoneType.NONE
    is_overlap: bool                = False
    is_kill_zone: bool              = False
    can_trade: bool                 = False
    session_score: float            = 0.0
    session_name_fa: str            = "بدون سشن"
    kill_zone_name_fa: str          = "بدون Kill Zone"
    utc_hour: int                   = 0
    utc_minute: int                 = 0
    minutes_to_london_open: int     = 0
    minutes_to_ny_open: int         = 0
    active_sessions: List[str]      = field(default_factory=list)


class SessionService:
    """  محاسبه سشن‌های معاملاتی — بدون I/O """

    _SESSION_SCORES: Dict[Any, float] = {
        KillZoneType.LONDON_OPEN:  100.0,
        KillZoneType.NY_OPEN:      100.0,
        SessionType.OVERLAP:        90.0,
        KillZoneType.NY_PM:         75.0,
        SessionType.LONDON:         70.0,
        SessionType.NEWYORK:        65.0,
        KillZoneType.ASIAN:         50.0,
        KillZoneType.LONDON_CLOSE:  45.0,
        SessionType.TOKYO:          40.0,
        SessionType.SYDNEY:         25.0,
        SessionType.NONE:            0.0,
    }

    def __init__(
        self,
        use_sydney: bool       = False,
        use_tokyo: bool        = True,
        use_london: bool       = True,
        use_newyork: bool      = True,
        only_kill_zones: bool  = False,
        prefer_overlap: bool   = False,
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
        return (cur >= s or cur < e) if s >= e else (s <= cur < e)

    @staticmethod
    def _minutes_until(h: int, m: int, th: int, tm: int) -> int:
        cur = h * 60 + m
        tgt = th * 60 + tm
        return tgt - cur if tgt > cur else 1440 - cur + tgt

    def get_current_session(self, dt: Optional[datetime] = None) -> SessionInfo:
        if dt is None:
            dt = datetime.now(timezone.utc)
        H, M = dt.hour, dt.minute
        r = self._in_range

        in_sydney  = r(H, M, 22, 0,  7, 0)
        in_tokyo   = r(H, M,  0, 0,  9, 0)
        in_london  = r(H, M,  7, 0, 16, 0)
        in_newyork = r(H, M, 12, 0, 21, 0)
        in_overlap = r(H, M, 12, 0, 16, 0)

        in_kz_asian        = r(H, M, 20, 0,  0, 0)
        in_kz_london_open  = r(H, M,  7, 0,  9, 0)
        in_kz_ny_open      = r(H, M, 12, 0, 14, 0)
        in_kz_ny_pm        = r(H, M, 17, 0, 18, 0)
        in_kz_london_close = r(H, M, 15, 0, 16, 0)

        info = SessionInfo(utc_hour=H, utc_minute=M)
        active: List[str] = []

        if in_sydney  and self.use_sydney:  active.append("Sydney");   info.session_type = SessionType.SYDNEY
        if in_tokyo   and self.use_tokyo:   active.append("Tokyo");    info.session_type = SessionType.TOKYO
        if in_london  and self.use_london:  active.append("London");   info.session_type = SessionType.LONDON
        if in_newyork and self.use_newyork: active.append("New York"); info.session_type = SessionType.NEWYORK
        if in_overlap:                      active.append("Overlap");  info.session_type = SessionType.OVERLAP

        info.active_sessions = active
        info.is_overlap = in_overlap

        if   in_kz_london_open:  info.kill_zone = KillZoneType.LONDON_OPEN;  info.kill_zone_name_fa = "\U0001f3af London Open KZ"
        elif in_kz_ny_open:      info.kill_zone = KillZoneType.NY_OPEN;      info.kill_zone_name_fa = "\U0001f3af NY Open KZ"
        elif in_kz_ny_pm:        info.kill_zone = KillZoneType.NY_PM;        info.kill_zone_name_fa = "\U0001f3af NY PM KZ"
        elif in_kz_london_close: info.kill_zone = KillZoneType.LONDON_CLOSE; info.kill_zone_name_fa = "London Close KZ"
        elif in_kz_asian:        info.kill_zone = KillZoneType.ASIAN;        info.kill_zone_name_fa = "Asian KZ"

        info.is_kill_zone = info.kill_zone != KillZoneType.NONE

        if   in_overlap:  info.session_name_fa = "\u2b50 London/NY Overlap"
        elif in_london:   info.session_name_fa = "London Session"
        elif in_newyork:  info.session_name_fa = "New York Session"
        elif in_tokyo:    info.session_name_fa = "Tokyo Session"
        elif in_sydney:   info.session_name_fa = "Sydney Session"
        else:             info.session_name_fa = "\u062e\u0627\u0631\u062c \u0627\u0632 \u0633\u0634\u0646"

        if info.is_kill_zone:
            info.session_score = self._SESSION_SCORES.get(info.kill_zone, 50.0)
        elif in_overlap:
            info.session_score = 90.0
        else:
            info.session_score = self._SESSION_SCORES.get(info.session_type, 0.0)

        if self.only_kill_zones:    info.can_trade = info.is_kill_zone
        elif self.prefer_overlap:   info.can_trade = info.is_overlap
        else:                       info.can_trade = bool(active)

        info.minutes_to_london_open = self._minutes_until(H, M,  7, 0)
        info.minutes_to_ny_open     = self._minutes_until(H, M, 12, 0)
        return info


class UserSessionManager:
    """
    \u0645\u062f\u06cc\u0631\u06cc\u062a refresh-token \u0647\u0627\u06cc \u06a9\u0627\u0631\u0628\u0631\u0627\u0646 \u062f\u0631 \u062c\u062f\u0648\u0644 refresh_tokens.

    FIX: revoke_all_user_sessions() \u0648 revoke_session() \u0628\u0627 DB write \u0648\u0627\u0642\u0639\u06cc
    \u0647\u0645\u0647 \u0645\u062a\u062f\u0647\u0627 \u0628\u0627 run_in_executor \u0627\u0632 blocking Supabase SDK \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u0645\u06cc\u200c\u06a9\u0646\u0646\u062f
    \u062a\u0627 event loop \u0645\u0633\u062f\u0648\u062f \u0646\u0634\u0648\u062f.
    """

    _TABLE = "refresh_tokens"

    @property
    def _client(self):
        from backend.database.connection import get_db_client
        return get_db_client()

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def revoke_session(self, jti: str) -> bool:
        """\u0628\u0627\u0637\u0644 \u06a9\u0631\u062f\u0646 \u06cc\u06a9 refresh-token \u0628\u0631 \u0627\u0633\u0627\u0633 JTI."""
        try:
            def _do():
                return (
                    self._client
                    .table(self._TABLE)
                    .delete()
                    .eq("jti", jti)
                    .execute()
                )
            result = await self._run(_do)
            deleted = len(result.data) if result.data else 0
            log.info("session_revoke jti=%s deleted=%d", jti, deleted)
            return deleted > 0
        except Exception:
            log.exception("revoke_session failed jti=%s", jti)
            return False

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """
        \u0628\u0627\u0637\u0644 \u06a9\u0631\u062f\u0646 \u062a\u0645\u0627\u0645 refresh-token \u0647\u0627\u06cc \u06cc\u06a9 \u06a9\u0627\u0631\u0628\u0631.

        \u062a\u0648\u0633\u0637 SelfHealingService \u062f\u0631 \u0645\u0648\u0627\u0642\u0639 anomaly \u0635\u062f\u0627 \u0632\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f.
        Returns: \u062a\u0639\u062f\u0627\u062f session \u0647\u0627\u06cc \u0628\u0627\u0637\u0644 \u0634\u062f\u0647.
        """
        try:
            def _do():
                return (
                    self._client
                    .table(self._TABLE)
                    .delete()
                    .eq("user_id", user_id)
                    .execute()
                )
            result = await self._run(_do)
            count = len(result.data) if result.data else 0
            log.warning("all_sessions_revoked user_id=%s count=%d", user_id, count)
            return count
        except Exception:
            log.exception("revoke_all_user_sessions failed user_id=%s", user_id)
            return 0

    async def get_active_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            def _do():
                return (
                    self._client
                    .table(self._TABLE)
                    .select("jti, created_at, expires_at")
                    .eq("user_id", user_id)
                    .gte("expires_at", now_iso)
                    .order("created_at", desc=True)
                    .execute()
                )
            result = await self._run(_do)
            return result.data or []
        except Exception:
            log.exception("get_active_sessions failed user_id=%s", user_id)
            return []

    async def count_active_sessions(self, user_id: str) -> int:
        sessions = await self.get_active_sessions(user_id)
        return len(sessions)

    async def purge_expired(self) -> int:
        """\u062d\u0630\u0641 session \u0647\u0627\u06cc \u0645\u0646\u0642\u0636\u06cc \u2014 background cleanup."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            def _do():
                return (
                    self._client
                    .table(self._TABLE)
                    .delete()
                    .lt("expires_at", now_iso)
                    .execute()
                )
            result = await self._run(_do)
            count = len(result.data) if result.data else 0
            if count:
                log.info("purged_expired_sessions count=%d", count)
            return count
        except Exception:
            log.exception("purge_expired failed")
            return 0


# Singletons
session_service      = SessionService()
user_session_manager = UserSessionManager()

# backward compat alias
async def revoke_all_user_sessions(user_id: str) -> int:
    return await user_session_manager.revoke_all_user_sessions(user_id)
