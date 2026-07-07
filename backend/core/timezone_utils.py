"""
backend/core/timezone_utils.py — Phase 5: Timezone & Market Session Consistency

مرکز تمام عملیات datetime/timezone در پروژه.
همه ماژول‌های دیگر باید از این helper استفاده کنند.

اصول:
  1. همه datetime های داخلی: UTC-aware
  2. broker_time همیشه صریحاً تبدیل می‌شود
  3. session boundaries با DST-aware zoneinfo محاسبه می‌شوند
  4. Clock injection برای testability
  5. هیچ datetime.utcnow() یا datetime.now() بدون tz مجاز نیست
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("core.timezone_utils")

# ────────────────────────────────────────────────────────────────
# Sentinel timezones
# ────────────────────────────────────────────────────────────────
UTC = timezone.utc

# Forex broker standard timezone (most MT5 brokers: EET = UTC+2/+3 DST)
_BROKER_ZONES = {
    "EET": "Europe/Helsinki",  # UTC+2 / UTC+3 DST  ← most MT5 brokers
    "UTC": "UTC",
    "EST": "America/New_York",
    "GMT": "Europe/London",
    "AEST": "Australia/Sydney",
    "JST": "Asia/Tokyo",
}

# Market session zones (for DST-aware open/close)
_SESSION_ZONES = {
    "london": ZoneInfo("Europe/London"),  # BST/GMT (+0/+1)
    "new_york": ZoneInfo("America/New_York"),  # EST/EDT (-5/-4)
    "tokyo": ZoneInfo("Asia/Tokyo"),  # JST +9 (no DST)
    "sydney": ZoneInfo("Australia/Sydney"),  # AEST/AEDT (+10/+11)
}

# ────────────────────────────────────────────────────────────────
# Core helpers
# ────────────────────────────────────────────────────────────────


def utcnow() -> datetime:
    """
    Canonical now() — UTC-aware. Replaces ALL datetime.utcnow() calls.
    Always returns tzinfo=UTC.
    """
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """
    Garantee dt is UTC-aware.

    - If already UTC-aware → return as-is
    - If aware but non-UTC  → convert to UTC
    - If naive              → assume UTC, attach tzinfo (safe for our internal dts)

    NOTE: Never call this on broker_time — use broker_time_to_utc() instead.
    """
    if dt.tzinfo is None:
        # Naive: assume UTC (our internal convention)
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def broker_time_to_utc(
    broker_dt: datetime,
    broker_tz: str = "EET",
) -> datetime:
    """
    Convert MT5 broker server time to UTC-aware datetime.

    MT5 brokers typically run on EET (UTC+2 in winter, UTC+3 in summer DST).
    This function properly handles DST transitions.

    Args:
        broker_dt:  datetime from mt5.symbol_info_tick().time or positions
        broker_tz:  broker's timezone string, e.g. "EET", "UTC", "GMT"

    Returns:
        UTC-aware datetime

    Raises:
        ValueError: if broker_tz is unrecognised
    """
    zone_name = _BROKER_ZONES.get(broker_tz.upper())
    if zone_name is None:
        # Try direct zoneinfo lookup (e.g. "Europe/Helsinki")
        zone_name = broker_tz

    try:
        tz = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(
            f"Unknown broker timezone: {broker_tz!r}. Valid values: {list(_BROKER_ZONES)}"
        ) from exc

    if broker_dt.tzinfo is None:
        # Naive broker time: attach broker tz
        broker_dt = broker_dt.replace(tzinfo=tz)
    else:
        # Already aware — re-interpret as broker tz
        broker_dt = broker_dt.astimezone(tz)

    return broker_dt.astimezone(UTC)


def to_broker_time(
    utc_dt: datetime,
    broker_tz: str = "EET",
) -> datetime:
    """Convert UTC-aware datetime to broker timezone (for display/logging)."""
    zone_name = _BROKER_ZONES.get(broker_tz.upper(), broker_tz)
    try:
        tz = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"Unknown broker timezone: {broker_tz!r}") from exc

    dt = ensure_utc(utc_dt)
    return dt.astimezone(tz)


def utc_date() -> date:
    """Current UTC date (not local date)."""
    return utcnow().date()


def next_midnight_utc(from_dt: Optional[datetime] = None) -> datetime:
    """
    Next midnight in UTC. Safe for scheduling daily resets.
    No DST ambiguity since we work in UTC.
    """
    now = from_dt if from_dt is not None else utcnow()
    now = ensure_utc(now)
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def next_monday_midnight_utc(from_dt: Optional[datetime] = None) -> datetime:
    """Next Monday 00:00 UTC."""
    now = from_dt if from_dt is not None else utcnow()
    now = ensure_utc(now)
    days_ahead = (7 - now.weekday()) % 7 or 7
    return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)


def next_month_start_utc(from_dt: Optional[datetime] = None) -> datetime:
    """First day of next calendar month at 00:00 UTC."""
    now = from_dt if from_dt is not None else utcnow()
    now = ensure_utc(now)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=UTC)
    return datetime(now.year, now.month + 1, 1, tzinfo=UTC)


# ────────────────────────────────────────────────────────────────
# DST-aware session open/close helpers
# ────────────────────────────────────────────────────────────────


def session_open_utc(
    session: str,
    ref_dt: Optional[datetime] = None,
    local_hour: int = 8,
    local_minute: int = 0,
) -> datetime:
    """
    Return UTC datetime for a session open on the date of ref_dt.
    Handles DST automatically via zoneinfo.

    Example:
        London opens at 08:00 BST (UTC+1 summer) = 07:00 UTC
        London opens at 08:00 GMT (UTC+0 winter)  = 08:00 UTC
        This function returns the CORRECT UTC value for that day.
    """
    ref = ensure_utc(ref_dt if ref_dt else utcnow())
    tz = _SESSION_ZONES.get(session.lower())
    if tz is None:
        raise ValueError(f"Unknown session: {session!r}. Valid: {list(_SESSION_ZONES)}")

    local_dt = datetime(
        ref.year,
        ref.month,
        ref.day,
        local_hour,
        local_minute,
        0,
        tzinfo=tz,
    )
    return local_dt.astimezone(UTC)


def is_dst_active(zone_name: str, dt: Optional[datetime] = None) -> bool:
    """
    Returns True if DST is active in zone_name at time dt.
    Useful for logging/alerting during DST transitions.
    """
    check_dt = ensure_utc(dt) if dt else utcnow()
    try:
        tz = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError):
        return False
    local = check_dt.astimezone(tz)
    utcoff = local.utcoffset()
    # DST active when offset > standard offset (approximation)
    std_offset = tz.utcoffset(datetime(check_dt.year, 1, 15, tzinfo=tz))
    return utcoff != std_offset


def dst_transition_warning(
    broker_tz: str = "EET",
    window_hours: int = 48,
) -> Optional[str]:
    """
    Returns a warning string if a DST transition is imminent in broker_tz.
    Call this at startup and periodically (e.g., daily) to alert operators.
    """
    zone_name = _BROKER_ZONES.get(broker_tz.upper(), broker_tz)
    now = utcnow()
    try:
        tz = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError):
        return None

    current_offset = now.astimezone(tz).utcoffset()
    check = now + timedelta(hours=window_hours)
    future_offset = check.astimezone(tz).utcoffset()

    if current_offset != future_offset:
        diff = int((future_offset - current_offset).total_seconds() / 3600)
        direction = "forward" if diff > 0 else "back"
        return (
            f"DST transition in {broker_tz} within {window_hours}h: "
            f"UTC offset shifts {direction} by {abs(diff)}h"
        )
    return None


# ────────────────────────────────────────────────────────────────
# Clock injection (for tests)
# ────────────────────────────────────────────────────────────────

ClockFn = Callable[[], datetime]

_global_clock: ClockFn = utcnow


def get_clock() -> ClockFn:
    """Return the current global clock function."""
    return _global_clock


def set_clock(clock_fn: ClockFn) -> None:
    """
    Override the global clock (for tests only).
    Restore with reset_clock() after test.
    """
    global _global_clock
    _global_clock = clock_fn
    logger.warning("Global clock overridden — only use in tests")


def reset_clock() -> None:
    """Restore global clock to utcnow()."""
    global _global_clock
    _global_clock = utcnow


def now() -> datetime:
    """
    Current time via injectable clock.
    Use this everywhere instead of datetime.now(UTC) for testability.
    """
    return _global_clock()


# ────────────────────────────────────────────────────────────────
# Formatting helpers
# ────────────────────────────────────────────────────────────────


def to_iso(dt: datetime) -> str:
    """UTC-aware datetime to ISO 8601 string with Z suffix."""
    return ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def from_iso(s: str) -> datetime:
    """
    Parse ISO 8601 string → UTC-aware datetime.
    Handles 'Z' suffix and +HH:MM offsets.
    """
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return ensure_utc(dt)


def parse_broker_timestamp(
    ts: float,
    broker_tz: str = "EET",
) -> datetime:
    """
    Convert MT5 Unix timestamp (seconds since epoch) to UTC.
    MT5 timestamps are always UTC epoch — attach UTC tzinfo directly.
    """
    return datetime.fromtimestamp(ts, tz=UTC)
