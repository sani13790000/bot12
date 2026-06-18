"""
================================================================================
Galaxy Vast AI Trading Platform
کنترلر Replay — Replay Controller
================================================================================
این ماژول یک interface ساده برای کنترل ReplayEngine از طریق API فراهم می‌کند.

قابلیت‌ها:
  - مدیریت session های Replay برای چند کاربر همزمان
  - API برای play/pause/stop/speed/jump
  - ارسال فریم‌ها به WebSocket clients

نویسنده: Galaxy Vast AI Engine
================================================================================
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from ...core.logger import get_logger
from ..backtest.engine import CandleData
from .engine import ReplayConfig, ReplayEngine, ReplayFrame, ReplaySpeed, ReplayStatus

logger = get_logger("research.replay.controller")


class ReplaySession:
    """
    یک session Replay برای یک کاربر

    هر کاربر session مستقل خود را دارد.
    """

    def __init__(self, session_id: str, user_id: int) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.engine = ReplayEngine()
        self.created_at = datetime.utcnow()
        self._task: Optional[asyncio.Task] = None
        self._on_frame: Optional[Callable] = None

    def set_frame_callback(self, callback: Callable[[ReplayFrame], None]) -> None:
        """تنظیم callback برای دریافت فریم‌ها"""
        self._on_frame = callback

    async def start(self, candles: list, config: ReplayConfig) -> None:
        """شروع Replay در یک task جداگانه"""
        await self.engine.load(candles, config)
        self._task = asyncio.create_task(
            self.engine.play(on_frame=self._on_frame, config=config)
        )
        logger.info(f"Replay session شروع شد | user: {self.user_id}")

    def pause(self) -> None:
        """pause کردن Replay"""
        self.engine.pause()

    def resume(self) -> None:
        """ادامه Replay"""
        self.engine.resume()

    def stop(self) -> None:
        """توقف کامل Replay"""
        self.engine.stop()
        if self._task and not self._task.done():
            self._task.cancel()

    def set_speed(self, speed: ReplaySpeed) -> None:
        """تغییر سرعت"""
        self.engine.set_speed(speed)

    def jump_to(self, index: int) -> None:
        """پرش به index"""
        self.engine.jump_to(index)

    def get_state(self) -> Dict[str, Any]:
        """وضعیت فعلی session"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "state": self.engine.state.to_dict(),
            "created_at": self.created_at.isoformat(),
        }


class ReplayController:
    """
    کنترلر مرکزی Replay برای مدیریت چند session

    این کلاس session های Replay را برای کاربران مختلف مدیریت می‌کند
    و از تداخل بین آن‌ها جلوگیری می‌کند.
    """

    def __init__(self) -> None:
        """مقداردهی اولیه کنترلر"""
        self._sessions: Dict[str, ReplaySession] = {}
        self._max_sessions = 10   # حداکثر session همزمان
        logger.info("ReplayController راه‌اندازی شد")

    async def create_session(
        self,
        user_id: int,
        candles: list,
        config: ReplayConfig,
        on_frame: Optional[Callable] = None,
    ) -> ReplaySession:
        """
        ایجاد و شروع یک session جدید

        اگر کاربر session فعال داشته باشد، ابتدا متوقف می‌شود.

        Args:
            user_id: شناسه کاربر
            candles: داده‌های تاریخی
            config: تنظیمات Replay
            on_frame: callback برای دریافت فریم‌ها

        Returns:
            ReplaySession: session ایجادشده
        """
        # ─── پاکسازی session قبلی همین کاربر ───
        existing_key = f"user_{user_id}"
        if existing_key in self._sessions:
            self._sessions[existing_key].stop()
            del self._sessions[existing_key]
            logger.info(f"Session قبلی کاربر {user_id} متوقف شد")

        # ─── بررسی محدودیت ───
        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError(
                f"حداکثر session همزمان ({self._max_sessions}) رسیده"
            )

        # ─── ساخت session جدید ───
        import uuid
        session_id = str(uuid.uuid4())[:8]
        session = ReplaySession(session_id=session_id, user_id=user_id)

        if on_frame:
            session.set_frame_callback(on_frame)

        await session.start(candles, config)
        self._sessions[existing_key] = session

        logger.info(
            f"Session جدید ایجاد شد | id: {session_id} | user: {user_id}"
        )
        return session

    def get_session(self, user_id: int) -> Optional[ReplaySession]:
        """دریافت session فعال یک کاربر"""
        return self._sessions.get(f"user_{user_id}")

    def stop_session(self, user_id: int) -> bool:
        """توقف session یک کاربر"""
        key = f"user_{user_id}"
        if key in self._sessions:
            self._sessions[key].stop()
            del self._sessions[key]
            logger.info(f"Session کاربر {user_id} متوقف شد")
            return True
        return False

    def get_all_states(self) -> list:
        """وضعیت تمام session های فعال"""
        return [s.get_state() for s in self._sessions.values()]

    def cleanup_finished(self) -> int:
        """پاکسازی session های تمام‌شده"""
        finished_keys = [
            k for k, s in self._sessions.items()
            if s.engine.state.status == ReplayStatus.FINISHED
        ]
        for k in finished_keys:
            del self._sessions[k]
        if finished_keys:
            logger.info(f"{len(finished_keys)} session تمام‌شده پاک شد")
        return len(finished_keys)


# ─── instance سراسری ───
replay_controller = ReplayController()
