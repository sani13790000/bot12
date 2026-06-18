"""
================================================================================
Galaxy Vast AI Trading Platform
موتور ریپلی بازار — Market Replay Engine

این ماژول امکان پخش مجدد تاریخچه بازار را فراهم می‌کند.
ویژگی‌ها:
- بازگشت به هر تاریخ دلخواه
- پخش کندل به کندل (step-by-step)
- سرعت‌های مختلف (آهسته/معمولی/سریع)
- مکث و ادامه
- مقایسه پیش‌بینی با نتیجه واقعی

نسخه: 3.0.0
================================================================================
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("research.replay.engine")


class ReplaySpeed(str, Enum):
    """سرعت پخش ریپلی"""
    SLOW    = "SLOW"    # ۲ ثانیه بین کندل‌ها
    NORMAL  = "NORMAL"  # ۱ ثانیه
    FAST    = "FAST"    # ۰.۳ ثانیه
    INSTANT = "INSTANT" # بدون تاخیر


class ReplayStatus(str, Enum):
    """وضعیت ریپلی"""
    IDLE     = "IDLE"
    RUNNING  = "RUNNING"
    PAUSED   = "PAUSED"
    FINISHED = "FINISHED"
    ERROR    = "ERROR"


@dataclass
class ReplayCandle:
    """کندل در جریان ریپلی — شامل اطلاعات تحلیل"""
    index       : int
    timestamp   : datetime
    open        : float
    high        : float
    low         : float
    close       : float
    volume      : float
    # اطلاعات تحلیل (اختیاری — پر می‌شود اگر signal_generator موجود باشد)
    signal      : Optional[Dict[str, Any]] = None
    smc_zones   : Optional[List[Dict]]     = None
    pa_patterns : Optional[List[Dict]]     = None


@dataclass
class ReplayConfig:
    """
    تنظیمات ریپلی

    تمام پارامترهای پخش مجدد بازار از طریق این کلاس تعریف می‌شوند.
    """
    symbol              : str
    start_date          : datetime
    end_date            : Optional[datetime] = None
    speed               : ReplaySpeed        = ReplaySpeed.NORMAL
    run_analysis        : bool               = True   # آیا تحلیل SMC/PA اجرا شود؟
    window_size         : int                = 50     # تعداد کندل تاریخی برای تحلیل


@dataclass
class ReplayState:
    """
    وضعیت لحظه‌ای ریپلی

    این کلاس وضعیت فعلی پخش را نمایش می‌دهد.
    """
    replay_id       : str
    status          : ReplayStatus
    current_index   : int
    total_candles   : int
    current_candle  : Optional[ReplayCandle]
    progress_pct    : float              # ۰ تا ۱۰۰
    elapsed_seconds : float
    config          : ReplayConfig

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای API/WebSocket"""
        candle_dict = None
        if self.current_candle:
            c = self.current_candle
            candle_dict = {
                "index"     : c.index,
                "timestamp" : c.timestamp.isoformat(),
                "open"      : c.open,
                "high"      : c.high,
                "low"       : c.low,
                "close"     : c.close,
                "volume"    : c.volume,
                "signal"    : c.signal,
            }
        return {
            "replay_id"      : self.replay_id,
            "status"         : self.status.value,
            "current_index"  : self.current_index,
            "total_candles"  : self.total_candles,
            "progress_pct"   : round(self.progress_pct, 1),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "current_candle" : candle_dict,
        }


class ReplayEngine:
    """
    موتور ریپلی بازار Galaxy Vast

    امکان پخش مجدد تاریخچه بازار با قابلیت تحلیل زنده را فراهم می‌کند.

    نحوه استفاده:
        engine = ReplayEngine()
        await engine.load(config, candles, signal_generator)
        await engine.play(on_candle_callback)
    """

    # نگاشت سرعت به تاخیر (ثانیه)
    _SPEED_DELAY: Dict[ReplaySpeed, float] = {
        ReplaySpeed.SLOW    : 2.0,
        ReplaySpeed.NORMAL  : 1.0,
        ReplaySpeed.FAST    : 0.3,
        ReplaySpeed.INSTANT : 0.0,
    }

    def __init__(self) -> None:
        """مقداردهی اولیه موتور ریپلی"""
        self._replay_id       : Optional[str]            = None
        self._candles         : List[ReplayCandle]       = []
        self._config          : Optional[ReplayConfig]   = None
        self._status          : ReplayStatus             = ReplayStatus.IDLE
        self._current_index   : int                      = 0
        self._signal_generator: Optional[Any]            = None
        self._start_time      : Optional[datetime]       = None
        self._pause_event     : asyncio.Event            = asyncio.Event()
        self._stop_event      : asyncio.Event            = asyncio.Event()
        self._pause_event.set()  # در ابتدا pause نیست
        logger.info("▶️ Galaxy Vast Market Replay Engine آماده شد")

    async def load(
        self,
        config           : ReplayConfig,
        candles          : List[Any],     # لیست Candle از backtest engine
        signal_generator : Optional[Any] = None,
    ) -> str:
        """
        بارگذاری داده برای ریپلی

        پارامترها:
            config: تنظیمات ریپلی
            candles: لیست کندل‌های تاریخی
            signal_generator: تابع اختیاری برای تحلیل زنده

        خروجی:
            replay_id — شناسه یکتای این ریپلی
        """
        self._replay_id        = str(uuid.uuid4())
        self._config           = config
        self._signal_generator = signal_generator
        self._current_index    = 0
        self._status           = ReplayStatus.IDLE
        self._stop_event.clear()
        self._pause_event.set()

        # ── فیلتر کندل‌ها بر اساس تاریخ ──────────────────────────────────────
        end = config.end_date or datetime.now(timezone.utc)
        filtered = [
            c for c in candles
            if config.start_date <= c.timestamp <= end
        ]

        # ── تبدیل به ReplayCandle ─────────────────────────────────────────────
        self._candles = [
            ReplayCandle(
                index     = i,
                timestamp = c.timestamp,
                open      = c.open,
                high      = c.high,
                low       = c.low,
                close     = c.close,
                volume    = c.volume,
            )
            for i, c in enumerate(filtered)
        ]

        logger.info(
            f"📂 ریپلی بارگذاری شد | ID: {self._replay_id[:8]} | "
            f"نماد: {config.symbol} | کندل‌ها: {len(self._candles)}"
        )
        return self._replay_id

    async def play(
        self,
        on_candle: Callable[[ReplayCandle, ReplayState], None],
    ) -> None:
        """
        شروع یا ادامه پخش ریپلی

        پارامترها:
            on_candle: callback که برای هر کندل فراخوانی می‌شود
        """
        if not self._candles:
            logger.error("❌ ریپلی بارگذاری نشده — ابتدا load() را فراخوانی کنید")
            return

        self._status     = ReplayStatus.RUNNING
        self._start_time = datetime.now(timezone.utc)
        delay            = self._SPEED_DELAY[self._config.speed]

        logger.info(f"▶️ پخش ریپلی شروع شد | سرعت: {self._config.speed.value}")

        while self._current_index < len(self._candles):
            # ── بررسی توقف ──────────────────────────────────────────────────
            if self._stop_event.is_set():
                self._status = ReplayStatus.IDLE
                logger.info("⏹️ ریپلی متوقف شد")
                break

            # ── بررسی مکث ───────────────────────────────────────────────────
            await self._pause_event.wait()

            candle = self._candles[self._current_index]

            # ── اجرای تحلیل اگر فعال است ─────────────────────────────────────
            if self._config.run_analysis and self._signal_generator:
                window_start = max(0, self._current_index - self._config.window_size)
                window       = self._candles[window_start : self._current_index + 1]
                raw_candles  = [
                    type('C', (), {
                        'timestamp': c.timestamp, 'open': c.open, 'high': c.high,
                        'low': c.low, 'close': c.close, 'volume': c.volume,
                    })()
                    for c in window
                ]
                try:
                    signal = await self._signal_generator(raw_candles, self._config.symbol)
                    candle.signal = signal
                except Exception as exc:
                    logger.debug(f"تحلیل ریپلی: {exc}")

            # ── ساخت وضعیت فعلی ──────────────────────────────────────────────
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            state   = ReplayState(
                replay_id       = self._replay_id,
                status          = self._status,
                current_index   = self._current_index,
                total_candles   = len(self._candles),
                current_candle  = candle,
                progress_pct    = self._current_index / len(self._candles) * 100,
                elapsed_seconds = elapsed,
                config          = self._config,
            )

            # ── فراخوانی callback ─────────────────────────────────────────────
            try:
                if asyncio.iscoroutinefunction(on_candle):
                    await on_candle(candle, state)
                else:
                    on_candle(candle, state)
            except Exception as exc:
                logger.error(f"⚠️ خطا در on_candle callback: {exc}")

            self._current_index += 1

            # ── تاخیر بین کندل‌ها ────────────────────────────────────────────
            if delay > 0:
                await asyncio.sleep(delay)

        # ── پایان ریپلی ───────────────────────────────────────────────────────
        if self._current_index >= len(self._candles):
            self._status = ReplayStatus.FINISHED
            logger.info(
                f"✅ ریپلی کامل شد | {len(self._candles)} کندل پخش شد"
            )

    def pause(self) -> None:
        """مکث ریپلی"""
        if self._status == ReplayStatus.RUNNING:
            self._status = ReplayStatus.PAUSED
            self._pause_event.clear()
            logger.info("⏸️ ریپلی متوقف شد")

    def resume(self) -> None:
        """ادامه ریپلی بعد از مکث"""
        if self._status == ReplayStatus.PAUSED:
            self._status = ReplayStatus.RUNNING
            self._pause_event.set()
            logger.info("▶️ ریپلی ادامه یافت")

    def stop(self) -> None:
        """توقف کامل ریپلی"""
        self._stop_event.set()
        self._pause_event.set()  # از مکث خارج شو تا loop پایان یابد
        logger.info("⏹️ دستور توقف ریپلی صادر شد")

    def jump_to(self, bar_index: int) -> None:
        """
        پرش به کندل مشخص

        پارامترها:
            bar_index: شماره کندل (از ۰ شروع می‌شود)
        """
        if 0 <= bar_index < len(self._candles):
            self._current_index = bar_index
            logger.info(f"⏩ پرش به کندل {bar_index}")
        else:
            logger.warning(f"⚠️ شاخص کندل {bar_index} معتبر نیست")

    def jump_to_date(self, target_date: datetime) -> None:
        """
        پرش به تاریخ مشخص

        پارامترها:
            target_date: تاریخ هدف
        """
        for i, candle in enumerate(self._candles):
            if candle.timestamp >= target_date:
                self._current_index = i
                logger.info(f"⏩ پرش به تاریخ {target_date.date()} (کندل {i})")
                return
        logger.warning(f"⚠️ تاریخ {target_date.date()} در داده‌ها یافت نشد")

    def set_speed(self, speed: ReplaySpeed) -> None:
        """تغییر سرعت پخش در حین ریپلی"""
        if self._config:
            self._config.speed = speed
            logger.info(f"⚡ سرعت ریپلی تغییر کرد: {speed.value}")

    @property
    def state(self) -> ReplayState:
        """وضعیت فعلی ریپلی"""
        current = self._candles[self._current_index] if self._candles and self._current_index < len(self._candles) else None
        elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds() if self._start_time else 0
        return ReplayState(
            replay_id       = self._replay_id or "",
            status          = self._status,
            current_index   = self._current_index,
            total_candles   = len(self._candles),
            current_candle  = current,
            progress_pct    = self._current_index / len(self._candles) * 100 if self._candles else 0,
            elapsed_seconds = elapsed,
            config          = self._config,
        )


# ─── نمونه singleton ──────────────────────────────────────────────────────────
replay_engine = ReplayEngine()
