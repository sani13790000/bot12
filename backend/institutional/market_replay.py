"""Galaxy Vast AI Trading Platform — Institutional Market Replay Engine.

Features:
- Candle-by-candle playback
- Play / Pause / Resume / Stop
- Speed control: x1, x2, x4, x10
- Step forward / backward
- Historical simulation from 2018 to present
- Visual trade entries and exits (markers)
- Signal overlay support
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from backend.research.backtest.engine import BacktestTrade, CandleData


class ReplayState(str, Enum):
    IDLE = "IDLE"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class ReplaySpeed(float, Enum):
    X1 = 1.0
    X2 = 2.0
    X4 = 4.0
    X10 = 10.0


@dataclass
class ReplayConfig:
    symbol: str = "XAUUSD"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    speed: ReplaySpeed = ReplaySpeed.X1
    candle_delay_ms: int = 500
    initial_balance: float = 100_000.0


@dataclass
class ReplayTradeMarker:
    trade_id: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    outcome: Optional[str] = None
    pnl_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "direction": self.direction,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "outcome": self.outcome,
            "pnl_usd": self.pnl_usd,
        }


@dataclass
class ReplayFrame:
    index: int
    candle: CandleData
    history: List[CandleData]
    current_price: float
    trade_markers: List[ReplayTradeMarker] = field(default_factory=list)
    signal: Optional[Dict[str, Any]] = None
    annotations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "candle": self.candle.to_dict() if hasattr(self.candle, "to_dict") else self.candle.__dict__,
            "history_count": len(self.history),
            "current_price": self.current_price,
            "trade_markers": [m.to_dict() for m in self.trade_markers],
            "signal": self.signal,
            "annotations": self.annotations,
        }


@dataclass
class ReplaySession:
    state: ReplayState = ReplayState.IDLE
    current_index: int = 0
    total_candles: int = 0
    speed: ReplaySpeed = ReplaySpeed.X1
    start_time: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    current_balance: float = 100_000.0
    equity_curve: List[tuple] = field(default_factory=list)
    trade_markers: List[ReplayTradeMarker] = field(default_factory=list)
    annotations_log: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def progress_pct(self) -> float:
        if self.total_candles == 0:
            return 0.0
        return round(self.current_index / self.total_candles * 100, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "current_index": self.current_index,
            "total_candles": self.total_candles,
            "progress_pct": self.progress_pct,
            "speed": self.speed.value,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "current_balance": round(self.current_balance, 2),
        }


class MarketReplayEngine:
    """Production-grade async market replay engine."""

    def __init__(self) -> None:
        self._candles: List[CandleData] = []
        self._config = ReplayConfig()
        self._session = ReplaySession()
        self._pause_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._frame_callbacks: List[Callable[[ReplayFrame], Any]] = []
        self._signal_generator: Optional[Callable[..., Any]] = None
        self._lock = asyncio.Lock()

    def load_candles(self, candles: List[CandleData], config: Optional[ReplayConfig] = None) -> None:
        if not candles:
            raise ValueError("No candles provided to replay engine")
        self._candles = sorted(candles, key=lambda c: c.timestamp)
        if config:
            self._config = config
        start, end = self._config.start_date, self._config.end_date
        if start or end:
            self._candles = [
                c for c in self._candles
                if (not start or c.timestamp >= start)
                and (not end or c.timestamp <= end)
            ]
        if len(self._candles) < 10:
            raise ValueError(f"Insufficient candles after filtering: {len(self._candles)}")
        self._session = ReplaySession(
            state=ReplayState.IDLE,
            total_candles=len(self._candles),
            speed=self._config.speed,
            current_balance=self._config.initial_balance,
        )
        self._session.equity_curve.append((self._candles[0].timestamp, self._config.initial_balance))
        self._pause_event.set()
        self._stop_event.clear()

    def register_frame_callback(self, callback: Callable[[ReplayFrame], Any]) -> None:
        self._frame_callbacks.append(callback)

    def set_signal_generator(self, generator: Callable[..., Any]) -> None:
        self._signal_generator = generator

    def add_trade_marker(self, marker: ReplayTradeMarker) -> None:
        self._session.trade_markers.append(marker)

    def add_annotation(self, annotation: Dict[str, Any]) -> None:
        self._session.annotations_log.append(annotation)

    async def play(self, start_index: int = 0) -> ReplaySession:
        async with self._lock:
            if not self._candles:
                raise RuntimeError("Candles not loaded. Call load_candles() first.")
            if self._session.state == ReplayState.PLAYING:
                return self._session
            self._session.state = ReplayState.PLAYING
            self._session.start_time = datetime.utcnow()
            if 0 <= start_index < len(self._candles):
                self._session.current_index = start_index

        speed_factor = self._config.speed.value
        delay = max(0.0, self._config.candle_delay_ms / 1000.0 / speed_factor)

        try:
            for i in range(self._session.current_index, len(self._candles)):
                if self._stop_event.is_set():
                    self._session.state = ReplayState.IDLE
                    break
                await self._pause_event.wait()

                candle = self._candles[i]
                history = self._candles[max(0, i - 200):i]
                signal = await self._generate_signal(history, candle)
                markers = self._markers_up_to(candle.timestamp)
                frame = ReplayFrame(
                    index=i,
                    candle=candle,
                    history=history,
                    current_price=candle.close,
                    trade_markers=markers,
                    signal=signal,
                    annotations=self._session.annotations_log.copy(),
                )

                await self._dispatch_frame(frame)
                self._session.current_index = i + 1
                if self._session.start_time:
                    self._session.elapsed_seconds = (datetime.utcnow() - self._session.start_time).total_seconds()
                self._session.equity_curve.append((candle.timestamp, self._session.current_balance))

                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(0)
            else:
                self._session.state = ReplayState.FINISHED
        except Exception as exc:
            self._session.state = ReplayState.ERROR
            raise RuntimeError(f"Replay error at index {self._session.current_index}: {exc}") from exc
        return self._session

    async def _generate_signal(self, history: List[CandleData], candle: CandleData) -> Optional[Dict[str, Any]]:
        if not self._signal_generator or len(history) < 20:
            return None
        try:
            result = self._signal_generator(history, candle)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:
            return None

    def _markers_up_to(self, timestamp: datetime) -> List[ReplayTradeMarker]:
        return [m for m in self._session.trade_markers if m.entry_time <= timestamp]

    async def _dispatch_frame(self, frame: ReplayFrame) -> None:
        for cb in self._frame_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(frame)
                else:
                    cb(frame)
            except Exception:
                pass

    def pause(self) -> None:
        if self._session.state == ReplayState.PLAYING:
            self._pause_event.clear()
            self._session.state = ReplayState.PAUSED

    def resume(self) -> None:
        if self._session.state == ReplayState.PAUSED:
            self._pause_event.set()
            self._session.state = ReplayState.PLAYING

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()
        self._session.state = ReplayState.IDLE

    def set_speed(self, speed: ReplaySpeed) -> None:
        self._config.speed = speed
        self._session.speed = speed

    def step_forward(self) -> Optional[ReplayFrame]:
        if self._session.current_index >= len(self._candles):
            return None
        i = self._session.current_index
        frame = self._build_frame(i)
        self._session.current_index = i + 1
        return frame

    def step_backward(self) -> Optional[ReplayFrame]:
        if self._session.current_index <= 0:
            return None
        i = self._session.current_index - 1
        frame = self._build_frame(i)
        self._session.current_index = i
        return frame

    def jump_to(self, index: int) -> Optional[ReplayFrame]:
        if not self._candles or index < 0 or index >= len(self._candles):
            return None
        self._session.current_index = index
        return self._build_frame(index)

    def _build_frame(self, index: int) -> ReplayFrame:
        candle = self._candles[index]
        history = self._candles[max(0, index - 200):index]
        return ReplayFrame(
            index=index,
            candle=candle,
            history=history,
            current_price=candle.close,
            trade_markers=self._markers_up_to(candle.timestamp),
            annotations=self._session.annotations_log.copy(),
        )

    def update_balance(self, balance: float) -> None:
        self._session.current_balance = balance

    def get_state(self) -> Dict[str, Any]:
        return self._session.to_dict()

    def get_frame_history(self) -> List[ReplayFrame]:
        """Return last 100 frames for dashboard re-hydration."""
        frames = []
        for i in range(max(0, self._session.current_index - 100), self._session.current_index):
            frames.append(self._build_frame(i))
        return frames
