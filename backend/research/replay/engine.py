"""
================================================================================
Galaxy Vast AI Trading Platform
موتور Replay بازار تاریخی — Market Replay Engine
================================================================================
این ماژول امکان پخش مجدد بازار تاریخی را با کنترل کامل فراهم می‌کند.

قابلیت‌ها:
  - برگشت به هر تاریخ در گذشته (۱ روز تا ۱ سال)
  - پخش کندل به کندل با کنترل سرعت
  - مقایسه پیش‌بینی سیستم با نتیجه واقعی
  - Pause / Resume / Fast Forward / Slow Motion
  - اجرای تحلیل در لحظه برای هر کندل

نویسنده: Galaxy Vast AI Engine
================================================================================
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ...core.logger import get_logger
from ..backtest.engine import CandleData

logger = get_logger("research.replay.engine")


class ReplayStatus(Enum):
    """وضعیت موتور Replay"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class ReplaySpeed(Enum):
    """سرعت پخش Replay"""
    SLOW = 0.25      # ۴ برابر کندتر
    NORMAL = 1.0     # سرعت عادی
    FAST = 4.0       # ۴ برابر سریع‌تر
    VERY_FAST = 16.0 # ۱۶ برابر سریع‌تر
    INSTANT = 0.0    # بدون تأخیر


@dataclass
class ReplayConfig:
    """تنظیمات موتور Replay"""
    symbol: str = "XAUUSD"
    start_date: Optional[datetime] = None
    days_back: int = 2              # چند روز به عقب برگردیم
    speed: ReplaySpeed = ReplaySpeed.NORMAL
    candle_delay_ms: int = 500      # تأخیر بین کندل‌ها (میلی‌ثانیه)
    run_analysis: bool = True       # اجرای تحلیل روی هر کندل
    show_predictions: bool = True   # نمایش پیش‌بینی قبل از نتیجه واقعی


@dataclass
class ReplayFrame:
    """
    یک فریم در Replay

    اطلاعات هر کندل به همراه تحلیل سیستم و نتیجه واقعی.
    """
    frame_index: int
    candle: CandleData
    candles_so_far: int

    # تحلیل سیستم در لحظه‌ای که این کندل باز بود
    system_prediction: Optional[Dict[str, Any]] = None

    # نتیجه واقعی (از کندل بعدی به بعد مشخص می‌شود)
    actual_outcome: Optional[str] = None   # "TP_HIT" / "SL_HIT" / "PENDING"

    # مقایسه
    prediction_correct: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary برای ارسال به frontend"""
        return {
            "index": self.frame_index,
            "candle": self.candle.to_dict(),
            "candles_count": self.candles_so_far,
            "prediction": self.system_prediction,
            "outcome": self.actual_outcome,
            "correct": self.prediction_correct,
        }


@dataclass
class ReplayState:
    """وضعیت فعلی موتور Replay"""
    status: ReplayStatus = ReplayStatus.IDLE
    current_index: int = 0
    total_candles: int = 0
    current_candle: Optional[CandleData] = None
    start_date: Optional[datetime] = None
    current_date: Optional[datetime] = None
    frames_played: int = 0
    correct_predictions: int = 0
    total_predictions: int = 0
    speed: ReplaySpeed = ReplaySpeed.NORMAL

    @property
    def progress(self) -> float:
        """پیشرفت Replay (0.0 تا 1.0)"""
        if self.total_candles == 0:
            return 0.0
        return self.current_index / self.total_candles

    @property
    def accuracy(self) -> float:
        """دقت پیش‌بینی‌ها (درصد)"""
        if self.total_predictions == 0:
            return 0.0
        return (self.correct_predictions / self.total_predictions) * 100

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary"""
        return {
            "status": self.status.value,
            "current_index": self.current_index,
            "total_candles": self.total_candles,
            "progress": round(self.progress * 100, 1),
            "current_date": self.current_date.isoformat() if self.current_date else None,
            "frames_played": self.frames_played,
            "accuracy": round(self.accuracy, 1),
            "speed": self.speed.value,
        }


class ReplayEngine:
    """
    موتور Replay بازار تاریخی Galaxy Vast

    این کلاس اجازه می‌دهد بازار تاریخی را مثل یک فیلم پخش کنید
    و ببینید سیستم در آن لحظه‌ها چه پیش‌بینی می‌کرد.

    نحوه استفاده:
        engine = ReplayEngine()
        config = ReplayConfig(symbol="XAUUSD", days_back=2)
        await engine.load(candles, config)
        await engine.play(on_frame=my_callback)
    """

    def __init__(self) -> None:
        """مقداردهی اولیه موتور Replay"""
        self._candles: List[CandleData] = []
        self._state = ReplayState()
        self._pause_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._frames: List[ReplayFrame] = []
        self._signal_generator: Optional[Callable] = None
        logger.info("موتور Replay Galaxy Vast راه‌اندازی شد")

    @property
    def state(self) -> ReplayState:
        """وضعیت فعلی موتور"""
        return self._state

    def set_signal_generator(self, generator: Callable) -> None:
        """
        تنظیم موتور تولید سیگنال برای تحلیل در Replay

        Args:
            generator: تابع async که کندل‌ها را دریافت و سیگنال تولید می‌کند
        """
        self._signal_generator = generator
        logger.info("Signal generator به Replay متصل شد")

    async def load(
        self,
        candles: List[CandleData],
        config: ReplayConfig,
    ) -> None:
        """
        بارگذاری داده‌های تاریخی برای Replay

        Args:
            candles: تمام کندل‌های موجود
            config: تنظیمات Replay
        """
        if self._state.status == ReplayStatus.RUNNING:
            raise RuntimeError("Replay در حال اجرا است — ابتدا متوقف کنید")

        # ─── فیلتر کندل‌ها ───
        if config.start_date:
            start = config.start_date
        else:
            if not candles:
                raise ValueError("داده‌ای برای Replay وجود ندارد")
            start = candles[-1].timestamp - timedelta(days=config.days_back)

        self._candles = [c for c in candles if c.timestamp >= start]

        if len(self._candles) < 10:
            raise ValueError(
                f"داده کافی برای Replay وجود ندارد: {len(self._candles)} کندل"
            )

        # ─── مقداردهی state ───
        self._state = ReplayState(
            status=ReplayStatus.IDLE,
            total_candles=len(self._candles),
            start_date=self._candles[0].timestamp,
            speed=config.speed,
        )
        self._pause_event.set()
        self._stop_event.clear()
        self._frames = []

        logger.info(
            f"Replay بارگذاری شد | نماد: {config.symbol} | "
            f"کندل‌ها: {len(self._candles)} | "
            f"از: {self._candles[0].timestamp.date()}"
        )

    async def play(
        self,
        on_frame: Optional[Callable[[ReplayFrame], None]] = None,
        config: Optional[ReplayConfig] = None,
    ) -> None:
        """
        شروع یا ادامه پخش Replay

        Args:
            on_frame: callback که برای هر فریم فراخوانی می‌شود
            config: تنظیمات (اختیاری — از load استفاده می‌شود)
        """
        if not self._candles:
            raise RuntimeError("ابتدا candles را با load() بارگذاری کنید")

        run_analysis = config.run_analysis if config else True
        candle_delay = config.candle_delay_ms / 1000 if config else 0.5
        speed_factor = config.speed.value if config else 1.0
        actual_delay = candle_delay / speed_factor if speed_factor > 0 else 0

        self._state.status = ReplayStatus.RUNNING
        logger.info(
            f"Replay شروع شد | "
            f"از index: {self._state.current_index} | "
            f"سرعت: {speed_factor}x"
        )

        start_idx = self._state.current_index

        try:
            for i in range(start_idx, len(self._candles)):
                # ─── بررسی Stop ───
                if self._stop_event.is_set():
                    self._state.status = ReplayStatus.IDLE
                    logger.info("Replay متوقف شد")
                    break

                # ─── بررسی Pause ───
                await self._pause_event.wait()

                candle = self._candles[i]
                historical = self._candles[max(0, i - 100):i]

                # ─── تولید پیش‌بینی ───
                prediction = None
                if run_analysis and self._signal_generator and len(historical) >= 20:
                    try:
                        prediction = await self._signal_generator(historical, candle)
                    except Exception as e:
                        logger.warning(f"خطا در تولید پیش‌بینی: {e}")

                # ─── مقایسه با نتیجه واقعی ───
                outcome = None
                correct = None
                if prediction and i + 1 < len(self._candles):
                    outcome, correct = self._evaluate_prediction(
                        prediction, self._candles[i + 1 :][:10]
                    )
                    if correct is not None:
                        self._state.total_predictions += 1
                        if correct:
                            self._state.correct_predictions += 1

                # ─── ساخت فریم ───
                frame = ReplayFrame(
                    frame_index=i,
                    candle=candle,
                    candles_so_far=i + 1,
                    system_prediction=prediction,
                    actual_outcome=outcome,
                    prediction_correct=correct,
                )
                self._frames.append(frame)

                # ─── به‌روزرسانی state ───
                self._state.current_index = i + 1
                self._state.current_candle = candle
                self._state.current_date = candle.timestamp
                self._state.frames_played += 1

                # ─── فراخوانی callback ───
                if on_frame:
                    try:
                        if asyncio.iscoroutinefunction(on_frame):
                            await on_frame(frame)
                        else:
                            on_frame(frame)
                    except Exception as e:
                        logger.warning(f"خطا در on_frame callback: {e}")

                # ─── تأخیر بین کندل‌ها ───
                if actual_delay > 0:
                    await asyncio.sleep(actual_delay)
                else:
                    await asyncio.sleep(0)

            else:
                self._state.status = ReplayStatus.FINISHED
                logger.info(
                    f"Replay کامل شد | "
                    f"دقت پیش‌بینی: {self._state.accuracy:.1f}%"
                )

        except Exception as e:
            self._state.status = ReplayStatus.ERROR
            logger.error(f"خطا در Replay: {e}", exc_info=True)
            raise

    def pause(self) -> None:
        """توقف موقت Replay"""
        if self._state.status == ReplayStatus.RUNNING:
            self._pause_event.clear()
            self._state.status = ReplayStatus.PAUSED
            logger.info("Replay pause شد")

    def resume(self) -> None:
        """ادامه Replay بعد از pause"""
        if self._state.status == ReplayStatus.PAUSED:
            self._pause_event.set()
            self._state.status = ReplayStatus.RUNNING
            logger.info("Replay resume شد")

    def stop(self) -> None:
        """توقف کامل Replay"""
        self._stop_event.set()
        self._pause_event.set()  # رفع block در صورت pause
        logger.info("Replay stop درخواست شد")

    def set_speed(self, speed: ReplaySpeed) -> None:
        """تغییر سرعت Replay در حال اجرا"""
        self._state.speed = speed
        logger.info(f"سرعت Replay تغییر کرد: {speed.value}x")

    def jump_to(self, index: int) -> None:
        """
        پرش به یک index خاص

        Args:
            index: شماره کندل مقصد
        """
        if index < 0 or index >= len(self._candles):
            raise ValueError(f"index نامعتبر: {index} (کل: {len(self._candles)})")
        self._state.current_index = index
        logger.info(f"Replay jump به index: {index}")

    def get_frames(self) -> List[ReplayFrame]:
        """دریافت تمام فریم‌های پخش‌شده"""
        return self._frames.copy()

    def _evaluate_prediction(
        self,
        prediction: Dict[str, Any],
        future_candles: List[CandleData],
    ) -> tuple:
        """
        ارزیابی دقت پیش‌بینی بر اساس کندل‌های آینده

        بررسی می‌کند آیا قیمت به TP یا SL رسیده است.

        Returns:
            Tuple[str, bool]: (نتیجه واقعی، درستی پیش‌بینی)
        """
        if not future_candles or "direction" not in prediction:
            return None, None

        direction = prediction.get("direction")
        tp1 = prediction.get("take_profit_1")
        sl = prediction.get("stop_loss")

        if not tp1 or not sl:
            return None, None

        for candle in future_candles:
            if direction == "BUY":
                if candle.high >= tp1:
                    return "TP_HIT", True
                if candle.low <= sl:
                    return "SL_HIT", False
            elif direction == "SELL":
                if candle.low <= tp1:
                    return "TP_HIT", True
                if candle.high >= sl:
                    return "SL_HIT", False

        return "PENDING", None
