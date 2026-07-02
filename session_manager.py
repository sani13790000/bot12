"""Session manager stub."""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore


@dataclass
class TradingSession:
    name: str
    timezone: str
    open_hour: int
    close_hour: int

    def is_active(self, ts: Optional[float] = None) -> bool:
        import datetime
        ts = ts or time.time()
        try:
            tz = zoneinfo.ZoneInfo(self.timezone)
            dt = datetime.datetime.fromtimestamp(ts, tz=tz)
            return self.open_hour <= dt.hour < self.close_hour
        except Exception:
            return False


class SessionManager:
    """Manages trading sessions."""

    SESSIONS = {
        "london": TradingSession("London", "Europe/London", 8, 17),
        "new_york": TradingSession("New York", "America/New_York", 8, 17),
        "tokyo": TradingSession("Tokyo", "Asia/Tokyo", 9, 18),
        "sydney": TradingSession("Sydney", "Australia/Sydney", 7, 16),
    }

    def active_sessions(self, ts: Optional[float] = None) -> list:
        return [s for s in self.SESSIONS.values() if s.is_active(ts)]

    def get_session(self, name: str) -> Optional[TradingSession]:
        return self.SESSIONS.get(name.lower())
