"""
=====================================================================
ماژول: سرویس مدیریت سشن‌های معاملاتی
فایل: backend/services/session_service.py

توضیح:
    این سرویس مدیریت سشن‌های معاملاتی را از سمت Python انجام می‌دهد.
    اطلاعات سشن جاری، Kill Zones و امتیاز زمانی را محاسبه می‌کند.
    این اطلاعات توسط Decision Engine برای تصمیم‌گیری استفاده می‌شود.

سشن‌های پشتیبانی شده:
    - Sydney: 22:00 - 07:00 UTC
    - Tokyo: 00:00 - 09:00 UTC
    - London: 07:00 - 16:00 UTC
    - New York: 12:00 - 21:00 UTC
    - London/NY Overlap: 12:00 - 16:00 UTC

Kill Zones ICT:
    - Asian KZ: 20:00 - 00:00 UTC
    - London Open KZ: 07:00 - 09:00 UTC
    - NY Open KZ: 12:00 - 14:00 UTC
    - NY PM KZ: 17:00 - 18:00 UTC

نویسنده: تیم توسعه Bot12
=====================================================================
"""

from dataclasses import dataclass
from datetime import datetime, timezone, time
from enum import Enum
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class SessionType(Enum):
    """انواع سشن معاملاتی"""
    NONE    = "بدون سشن"
    SYDNEY  = "Sydney"
    TOKYO   = "Tokyo"
    LONDON  = "London"
    NEWYORK = "New York"
    OVERLAP = "London/NY Overlap"


class KillZoneType(Enum):
    """انواع Kill Zone"""
    NONE         = "بدون Kill Zone"
    ASIAN        = "Asian Kill Zone"
    LONDON_OPEN  = "London Open Kill Zone"
    NY_OPEN      = "NY Open Kill Zone"
    NY_PM        = "NY PM Kill Zone"
    LONDON_CLOSE = "London Close Kill Zone"


@dataclass
class SessionInfo:
    """
    اطلاعات کامل سشن جاری

    این دیتاکلاس تمام اطلاعات مورد نیاز Decision Engine را دارد.
    """
    session_type: SessionType = SessionType.NONE
    kill_zone: KillZoneType = KillZoneType.NONE
    is_overlap: bool = False
    is_kill_zone: bool = False
    can_trade: bool = False
    session_score: float = 0.0          # امتیاز ۰ تا ۱۰۰
    session_name_fa: str = "بدون سشن"
    kill_zone_name_fa: str = "بدون Kill Zone"
    utc_hour: int = 0
    utc_minute: int = 0
    minutes_to_london_open: int = 0
    minutes_to_ny_open: int = 0
    active_sessions: List[str] = None

    def __post_init__(self):
        if self.active_sessions is None:
            self.active_sessions = []


class SessionService:
    """
    سرویس مدیریت سشن‌های معاملاتی

    این کلاس تمام محاسبات مربوط به سشن‌ها را انجام می‌دهد.
    تمام زمان‌ها بر اساس UTC هستند.
    """

    # تعریف سشن‌ها به صورت (start_hour, start_min, end_hour, end_min)
    SESSION_TIMES = {
        SessionType.SYDNEY:  (22, 0, 7, 0),
        SessionType.TOKYO:   (0, 0, 9, 0),
        SessionType.LONDON:  (7, 0, 16, 0),
        SessionType.NEWYORK: (12, 0, 21, 0),
        SessionType.OVERLAP: (12, 0, 16, 0),
    }

    # تعریف Kill Zones
    KILL_ZONE_TIMES = {
        KillZoneType.ASIAN:        (20, 0, 0, 0),
        KillZoneType.LONDON_OPEN:  (7, 0, 9, 0),
        KillZoneType.NY_OPEN:      (12, 0, 14, 0),
        KillZoneType.NY_PM:        (17, 0, 18, 0),
        KillZoneType.LONDON_CLOSE: (15, 0, 16, 0),
    }

    # امتیاز هر سشن و Kill Zone
    SESSION_SCORES = {
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
        use_sydney: bool = False,
        use_tokyo: bool = True,
        use_london: bool = True,
        use_newyork: bool = True,
        only_kill_zones: bool = False,
        prefer_overlap: bool = False
    ):
        """
        مقداردهی اولیه سرویس سشن

        Args:
            use_sydney: آیا سشن Sydney فعال است؟
            use_tokyo: آیا سشن Tokyo فعال است؟
            use_london: آیا سشن London فعال است؟
            use_newyork: آیا سشن New York فعال است؟
            only_kill_zones: آیا فقط در Kill Zones معامله شود؟
            prefer_overlap: آیا فقط در Overlap معامله شود؟
        """
        self.use_sydney      = use_sydney
        self.use_tokyo       = use_tokyo
        self.use_london      = use_london
        self.use_newyork     = use_newyork
        self.only_kill_zones = only_kill_zones
        self.prefer_overlap  = prefer_overlap

        logger.info("SessionService راه‌اندازی شد")

    def _is_in_time_range(
        self,
        current_hour: int,
        current_min: int,
        start_hour: int,
        start_min: int,
        end_hour: int,
        end_min: int
    ) -> bool:
        """
        بررسی اینکه آیا زمان فعلی در بازه مشخص شده است

        از midnight-crossing هم پشتیبانی می‌کند (مثل Sydney)
        """
        current_minutes = current_hour * 60 + current_min
        start_minutes   = start_hour * 60 + start_min
        end_minutes     = end_hour * 60 + end_min

        if start_minutes < end_minutes:
            # بازه عادی
            return start_minutes <= current_minutes < end_minutes
        else:
            # بازه midnight-crossing
            return current_minutes >= start_minutes or current_minutes < end_minutes

    def _minutes_until(
        self,
        current_hour: int,
        current_min: int,
        target_hour: int,
        target_min: int
    ) -> int:
        """محاسبه دقیقه تا رویداد بعدی"""
        current_total = current_hour * 60 + current_min
        target_total  = target_hour * 60 + target_min

        if target_total > current_total:
            return target_total - current_total
        else:
            return (24 * 60) - current_total + target_total

    def get_current_session(self, dt: Optional[datetime] = None) -> SessionInfo:
        """
        دریافت اطلاعات کامل سشن جاری

        Args:
            dt: زمان مورد نظر (اگر None باشد، زمان جاری UTC استفاده می‌شود)

        Returns:
            SessionInfo: اطلاعات کامل سشن
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        utc_hour = dt.hour
        utc_min  = dt.minute

        info = SessionInfo(utc_hour=utc_hour, utc_minute=utc_min)

        # --- بررسی سشن‌های فعال ---
        in_sydney  = self._is_in_time_range(utc_hour, utc_min, 22, 0, 7, 0)
        in_tokyo   = self._is_in_time_range(utc_hour, utc_min, 0, 0, 9, 0)
        in_london  = self._is_in_time_range(utc_hour, utc_min, 7, 0, 16, 0)
        in_newyork = self._is_in_time_range(utc_hour, utc_min, 12, 0, 21, 0)
        in_overlap = self._is_in_time_range(utc_hour, utc_min, 12, 0, 16, 0)

        # --- بررسی Kill Zones ---
        in_kz_asian        = self._is_in_time_range(utc_hour, utc_min, 20, 0, 0, 0)
        in_kz_london_open  = self._is_in_time_range(utc_hour, utc_min, 7, 0, 9, 0)
        in_kz_ny_open      = self._is_in_time_range(utc_hour, utc_min, 12, 0, 14, 0)
        in_kz_ny_pm        = self._is_in_time_range(utc_hour, utc_min, 17, 0, 18, 0)
        in_kz_london_close = self._is_in_time_range(utc_hour, utc_min, 15, 0, 16, 0)

        # --- تعیین سشن‌های فعال ---
        active_sessions = []
        if in_sydney and self.use_sydney:
            active_sessions.append("Sydney")
            info.session_type = SessionType.SYDNEY
        if in_tokyo and self.use_tokyo:
            active_sessions.append("Tokyo")
            info.session_type = SessionType.TOKYO
        if in_london and self.use_london:
            active_sessions.append("London")
            info.session_type = SessionType.LONDON
        if in_newyork and self.use_newyork:
            active_sessions.append("New York")
            info.session_type = SessionType.NEWYORK
        if in_overlap:
            active_sessions.append("Overlap")
            info.session_type = SessionType.OVERLAP

        info.active_sessions = active_sessions
        info.is_overlap = in_overlap

        # --- تعیین Kill Zone ---
        if in_kz_london_open:
            info.kill_zone = KillZoneType.LONDON_OPEN
            info.kill_zone_name_fa = "🎯 London Open Kill Zone"
        elif in_kz_ny_open:
            info.kill_zone = KillZoneType.NY_OPEN
            info.kill_zone_name_fa = "🎯 NY Open Kill Zone"
        elif in_kz_ny_pm:
            info.kill_zone = KillZoneType.NY_PM
            info.kill_zone_name_fa = "🎯 NY PM Kill Zone"
        elif in_kz_london_close:
            info.kill_zone = KillZoneType.LONDON_CLOSE
            info.kill_zone_name_fa = "London Close Kill Zone"
        elif in_kz_asian:
            info.kill_zone = KillZoneType.ASIAN
            info.kill_zone_name_fa = "Asian Kill Zone"

        info.is_kill_zone = info.kill_zone != KillZoneType.NONE

        # --- نام فارسی سشن ---
        if in_overlap:
            info.session_name_fa = "⭐ London/NY Overlap"
        elif in_london:
            info.session_name_fa = "London Session"
        elif in_newyork:
            info.session_name_fa = "New York Session"
        elif in_tokyo:
            info.session_name_fa = "Tokyo Session"
        elif in_sydney:
            info.session_name_fa = "Sydney Session"
        else:
            info.session_name_fa = "خارج از سشن"

        # --- محاسبه امتیاز ---
        if info.is_kill_zone:
            info.session_score = self.SESSION_SCORES.get(info.kill_zone, 50.0)
        elif in_overlap:
            info.session_score = 90.0
        else:
            info.session_score = self.SESSION_SCORES.get(info.session_type, 0.0)

        # --- تعیین قابلیت معامله ---
        if self.only_kill_zones:
            info.can_trade = info.is_kill_zone
        elif self.prefer_overlap:
            info.can_trade = info.is_overlap
        else:
            info.can_trade = len(active_sessions) > 0

        # --- محاسبه دقیقه تا سشن‌های مهم ---
        info.minutes_to_london_open = self._minutes_until(utc_hour, utc_min, 7, 0)
        info.minutes_to_ny_open     = self._minutes_until(utc_hour, utc_min, 12, 0)

        logger.debug(
            f"Session: {info.session_name_fa} | "
            f"KZ: {info.kill_zone_name_fa} | "
            f"امتیاز: {info.session_score} | "
            f"معامله: {info.can_trade}"
        )

        return info

    def can_trade_now(self) -> bool:
        """بررسی ساده: آیا الان می‌توان معامله کرد؟"""
        return self.get_current_session().can_trade

    def get_session_score(self) -> float:
        """دریافت امتیاز سشن جاری برای Decision Engine"""
        return self.get_current_session().session_score

    def is_in_kill_zone(self) -> bool:
        """بررسی: آیا در Kill Zone هستیم؟"""
        return self.get_current_session().is_kill_zone

    def get_session_report_fa(self) -> str:
        """
        تولید گزارش فارسی وضعیت سشن
        برای ارسال به تلگرام یا داشبورد
        """
        info = self.get_current_session()

        can_trade_emoji = "✅" if info.can_trade else "❌"
        kz_emoji = "🎯" if info.is_kill_zone else "⏳"

        return (
            f"🕐 زمان UTC: {info.utc_hour:02d}:{info.utc_minute:02d}\n"
            f"📊 سشن جاری: {info.session_name_fa}\n"
            f"{kz_emoji} Kill Zone: {info.kill_zone_name_fa}\n"
            f"⭐ Overlap: {'فعال' if info.is_overlap else 'غیرفعال'}\n"
            f"📈 امتیاز سشن: {info.session_score:.0f}/100\n"
            f"{can_trade_emoji} قابل معامله: {'بله' if info.can_trade else 'خیر'}\n"
            f"⏱ تا London Open: {info.minutes_to_london_open} دقیقه\n"
            f"⏱ تا NY Open: {info.minutes_to_ny_open} دقیقه"
        )
