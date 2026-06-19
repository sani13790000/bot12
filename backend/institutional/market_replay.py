"""Market Replay Engine — candle-by-candle playback with full speed control."""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable, Dict, List, Optional


class ReplaySpeed(float, Enum):
    X1 = 1.0
    X2 = 2.0
    X4 = 4.0
    X10 = 10.0


class ReplayState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"


@dataclass
class Candle:
    timestamp: float  # unix epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = "XAUUSD"
    timeframe: str = "M15"


@dataclass
class ReplayTrade:
    """A trade marker overlaid on the replay chart."""
    entry_time: float
    exit_time: Optional[float]
    entry_price: float
    exit_price: Optional[float]
    direction: str  # "BUY" | "SELL"
    profit: Optional[float]
    lot_size: float
    explanation: Optional[Dict] = None


@dataclass
class ReplayFrame:
    """Single frame emitted during replay."""
    candle: Candle
    index: int
    total: int
    trades_on_bar: List[ReplayTrade] = field(default_factory=list)
    equity: float = 0.0
    progress_pct: float = 0.0


class MarketReplayEngine:
    """
    Institutional Market Replay Engine.

    Features:
    - Candle-by-candle playback from 2018 to present
    - Play / Pause / Stop / Step-forward / Step-backward
    - Speed control: x1 x2 x4 x10
    - Trade entry/exit markers per bar
    - Equity curve tracking
    - Async iterator interface for Streamlit / WebSocket streaming
    """

    def __init__(
        self,
        candles: List[Candle],
        trades: Optional[List[ReplayTrade]] = None,
        initial_equity: float = 10_000.0,
    ):
        if not candles:
            raise ValueError("candles list cannot be empty")
        self._candles = candles
        self._trades = trades or []
        self._initial_equity = initial_equity

        self._cursor: int = 0
        self._state: ReplayState = ReplayState.IDLE
        self._speed: ReplaySpeed = ReplaySpeed.X1
        self._equity: float = initial_equity
        self._bar_interval_seconds: float = 900.0  # M15 default
        self._frame_callbacks: List[Callable[[ReplayFrame], None]] = []
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._stop_flag: bool = False

    # ------------------------------------------------------------------ #
    #  Control API                                                          #
    # ------------------------------------------------------------------ #

    def play(self, speed: ReplaySpeed = ReplaySpeed.X1) -> None:
        """Start or resume playback."""
        self._speed = speed
        self._state = ReplayState.PLAYING
        self._pause_event.set()
        self._stop_flag = False

    def pause(self) -> None:
        """Pause playback."""
        self._state = ReplayState.PAUSED
        self._pause_event.clear()

    def stop(self) -> None:
        """Stop and reset to beginning."""
        self._stop_flag = True
        self._pause_event.set()
        self._state = ReplayState.IDLE
        self._cursor = 0
        self._equity = self._initial_equity

    def step_forward(self) -> Optional[ReplayFrame]:
        """Advance one candle and return the frame."""
        if self._cursor >= len(self._candles):
            return None
        frame = self._build_frame(self._cursor)
        self._cursor += 1
        return frame

    def step_backward(self) -> Optional[ReplayFrame]:
        """Go back one candle and return the frame."""
        if self._cursor <= 0:
            return None
        self._cursor = max(0, self._cursor - 1)
        return self._build_frame(self._cursor)

    def seek(self, index: int) -> Optional[ReplayFrame]:
        """Jump to a specific candle index."""
        if 0 <= index < len(self._candles):
            self._cursor = index
            return self._build_frame(index)
        return None

    def set_speed(self, speed: ReplaySpeed) -> None:
        self._speed = speed

    def add_frame_callback(self, cb: Callable[[ReplayFrame], None]) -> None:
        """Register a callback fired on every frame (for Streamlit/WebSocket)."""
        self._frame_callbacks.append(cb)

    # ------------------------------------------------------------------ #
    #  Async iterator interface                                             #
    # ------------------------------------------------------------------ #

    async def stream(self) -> AsyncIterator[ReplayFrame]:
        """Async generator that yields ReplayFrames at the correct speed."""
        self._state = ReplayState.PLAYING
        self._stop_flag = False
        sleep_seconds = self._bar_interval_seconds / self._speed.value / 100

        while self._cursor < len(self._candles):
            if self._stop_flag:
                break

            # Wait while paused
            await self._pause_event.wait()

            if self._stop_flag:
                break

            frame = self._build_frame(self._cursor)
            self._cursor += 1

            for cb in self._frame_callbacks:
                try:
                    cb(frame)
                except Exception:
                    pass

            yield frame

            # Recalculate sleep on every bar (speed may change)
            sleep_seconds = max(0.01, self._bar_interval_seconds / self._speed.value / 200)
            await asyncio.sleep(sleep_seconds)

        self._state = ReplayState.FINISHED

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_frame(self, index: int) -> ReplayFrame:
        candle = self._candles[index]
        trades_on_bar = [
            t for t in self._trades
            if t.entry_time <= candle.timestamp < (t.exit_time or float("inf"))
        ]

        # Update equity from closed trades on this bar
        for t in self._trades:
            if t.exit_time and abs(t.exit_time - candle.timestamp) < 1 and t.profit:
                self._equity += t.profit

        progress = (index + 1) / len(self._candles) * 100

        return ReplayFrame(
            candle=candle,
            index=index,
            total=len(self._candles),
            trades_on_bar=trades_on_bar,
            equity=self._equity,
            progress_pct=round(progress, 2),
        )

    # ------------------------------------------------------------------ #
    #  Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> ReplayState:
        return self._state

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def total_candles(self) -> int:
        return len(self._candles)

    @property
    def current_equity(self) -> float:
        return self._equity

    @property
    def speed(self) -> ReplaySpeed:
        return self._speed
