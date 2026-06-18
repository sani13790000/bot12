"""Galaxy Vast AI Trading Platform — Institutional Tick-Level Backtest Engine.

Features:
- Tick-level simulation from OHLC candles
- Spread, slippage, commission modeling
- Multi-symbol and multi-timeframe support
- Market / Limit / Stop order types
- Position tracking and equity curve
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from backend.research.backtest.engine import BacktestTrade, CandleData
from backend.institutional.performance_metrics import PerformanceMetrics


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class TickData:
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
        }


@dataclass
class BacktestOrder:
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = "XAUUSD"
    direction: str = "BUY"
    order_type: OrderType = OrderType.MARKET
    volume: float = 0.01
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    commission: float = 0.0
    slippage_pips: float = 0.0


@dataclass
class SymbolConfig:
    symbol: str
    pip_size: float
    tick_size: float
    contract_size: float
    spread_pips: float
    commission_per_lot: float
    slippage_pips: float
    point_value: float


@dataclass
class TickBacktestConfig:
    symbols: List[str] = field(default_factory=lambda: ["XAUUSD"])
    timeframes: List[str] = field(default_factory=lambda: ["M15"])
    initial_balance: float = 100_000.0
    risk_per_trade_pct: float = 1.0
    commission_per_lot: float = 3.5
    slippage_pips: float = 0.3
    spread_pips: float = 0.2
    max_spread_pips: float = 5.0
    max_trades_per_day: int = 10
    min_rr_ratio: float = 1.5
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    ticks_per_candle: int = 20


class TickSimulator:
    """Generate realistic bid/ask/last tick paths from OHLC candles."""

    @staticmethod
    def infer_duration(timeframe: str) -> timedelta:
        mapping = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
        minutes = mapping.get(str(timeframe).upper(), 15)
        return timedelta(minutes=minutes)

    @staticmethod
    def candle_to_ticks(
        candle: CandleData,
        symbol_config: SymbolConfig,
        timeframe: str = "M15",
        ticks_per_candle: int = 20,
    ) -> List[TickData]:
        if ticks_per_candle < 4:
            ticks_per_candle = 4
        duration = TickSimulator.infer_duration(timeframe)
        dt = duration / ticks_per_candle
        spread = max(symbol_config.spread_pips * symbol_config.pip_size, symbol_config.tick_size)
        half_spread = spread / 2.0

        rng = np.random.default_rng(seed=int(candle.timestamp.timestamp()) % 2**31)
        points = [candle.open]
        for _ in range(ticks_per_candle - 2):
            val = candle.low + (candle.high - candle.low) * rng.beta(2, 2)
            points.append(val)
        points.append(candle.close)

        if max(points) < candle.high:
            points[ticks_per_candle // 2] = candle.high
        if min(points) > candle.low:
            points[ticks_per_candle // 3] = candle.low

        ticks = []
        for i, price in enumerate(points):
            ticks.append(TickData(
                timestamp=candle.timestamp + i * dt,
                bid=price - half_spread,
                ask=price + half_spread,
                last=price,
                volume=max(0.0, candle.volume / ticks_per_candle),
            ))
        return ticks


class TickBacktestEngine:
    """Tick-level backtest engine with multi-symbol / multi-timeframe support."""

    def __init__(self, config: Optional[TickBacktestConfig] = None):
        self.config = config or TickBacktestConfig()
        self.symbol_configs: Dict[str, SymbolConfig] = {}
        self._candles_by_symbol: Dict[str, List[CandleData]] = {}
        self._orders: List[BacktestOrder] = []
        self._positions: List[BacktestOrder] = []
        self._closed_trades: List[BacktestTrade] = []
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._balance: float = self.config.initial_balance
        self._signal_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None
        self._current_date: Optional[datetime] = None

    def register_symbol(self, cfg: SymbolConfig) -> None:
        self.symbol_configs[cfg.symbol] = cfg

    def set_signal_generator(self, fn: Callable[..., Optional[Dict[str, Any]]]) -> None:
        self._signal_fn = fn

    def load_data(self, candles_by_symbol: Dict[str, List[CandleData]]) -> None:
        self._candles_by_symbol = {
            sym: sorted(c, key=lambda x: x.timestamp)
            for sym, c in candles_by_symbol.items()
        }

    def _default_symbol_config(self, symbol: str) -> SymbolConfig:
        pip_size = 0.1 if "XAU" in symbol.upper() or "JPY" not in symbol.upper() and len(symbol) == 6 else 0.01
        if len(symbol) == 6 and "JPY" in symbol.upper():
            pip_size = 0.01
        return SymbolConfig(
            symbol=symbol,
            pip_size=pip_size,
            tick_size=pip_size / 10.0,
            contract_size=100_000.0 if len(symbol) == 6 else 100.0,
            spread_pips=self.config.spread_pips,
            commission_per_lot=self.config.commission_per_lot,
            slippage_pips=self.config.slippage_pips,
            point_value=10.0,
        )

    def run(
        self,
        candles_by_symbol: Optional[Dict[str, List[CandleData]]] = None,
        timeframe: str = "M15",
    ) -> Dict[str, Any]:
        if candles_by_symbol:
            self.load_data(candles_by_symbol)
        if not self._candles_by_symbol:
            raise ValueError("No candle data loaded for tick backtest")

        self._balance = self.config.initial_balance
        self._orders = []
        self._positions = []
        self._closed_trades = []
        self._equity_curve = []

        all_ticks: List[Tuple[datetime, str, TickData]] = []
        for sym, candles in self._candles_by_symbol.items():
            cfg = self.symbol_configs.get(sym)
            if not cfg:
                cfg = self._default_symbol_config(sym)
                self.symbol_configs[sym] = cfg
            for candle in candles:
                ticks = TickSimulator.candle_to_ticks(candle, cfg, timeframe, self.config.ticks_per_candle)
                for t in ticks:
                    all_ticks.append((t.timestamp, sym, t))

        all_ticks.sort(key=lambda x: x[0])

        daily_trade_count = 0
        last_day: Optional[datetime] = None

        for ts, sym, tick in all_ticks:
            self._current_date = ts
            if last_day is None or ts.date() != last_day:
                last_day = ts.date()
                daily_trade_count = 0

            self._process_orders(sym, tick, ts)

            if self._signal_fn and daily_trade_count < self.config.max_trades_per_day:
                candles = self._candles_by_symbol.get(sym, [])
                history = [c for c in candles if c.timestamp <= ts][-100:]
                signal = self._signal_fn(sym, tick, history)
                if signal and self._is_valid_signal(signal):
                    self._open_order(sym, signal, tick, ts)
                    daily_trade_count += 1

            self._equity_curve.append((ts, self._balance))

        return self._build_result()

    def _is_valid_signal(self, signal: Dict[str, Any]) -> bool:
        required = {"direction", "stop_loss", "take_profit"}
        if not required.issubset(signal.keys()):
            return False
        direction = str(signal.get("direction", "")).upper()
        if direction not in ("BUY", "SELL"):
            return False
        ep = float(signal.get("entry_price", 0.0))
        sl = float(signal.get("stop_loss", 0.0))
        tp = float(signal.get("take_profit", 0.0))
        if ep <= 0 or sl <= 0 or tp <= 0:
            return False
        risk = abs(ep - sl)
        reward = abs(tp - ep)
        if risk <= 0 or reward / risk < self.config.min_rr_ratio:
            return False
        return True

    def _process_orders(self, symbol: str, tick: TickData, ts: datetime) -> None:
        cfg = self.symbol_configs[symbol]
        for pos in list(self._positions):
            if pos.symbol != symbol:
                continue
            if pos.direction == "BUY":
                if pos.stop_loss and tick.bid <= pos.stop_loss:
                    self._close_position(pos, tick.bid, ts, cfg, "SL")
                elif pos.take_profit and tick.bid >= pos.take_profit:
                    self._close_position(pos, tick.bid, ts, cfg, "TP")
            else:
                if pos.stop_loss and tick.ask >= pos.stop_loss:
                    self._close_position(pos, tick.ask, ts, cfg, "SL")
                elif pos.take_profit and tick.ask <= pos.take_profit:
                    self._close_position(pos, tick.ask, ts, cfg, "TP")

        for order in list(self._orders):
            if order.symbol != symbol or order.status != OrderStatus.PENDING:
                continue
            fill_price = None
            if order.order_type == OrderType.MARKET:
                fill_price = tick.ask if order.direction == "BUY" else tick.bid
            elif order.order_type == OrderType.LIMIT:
                if order.direction == "BUY" and tick.ask <= order.entry_price:
                    fill_price = tick.ask
                elif order.direction == "SELL" and tick.bid >= order.entry_price:
                    fill_price = tick.bid
            elif order.order_type == OrderType.STOP:
                if order.direction == "BUY" and tick.ask >= order.entry_price:
                    fill_price = tick.ask
                elif order.direction == "SELL" and tick.bid <= order.entry_price:
                    fill_price = tick.bid

            if fill_price:
                slip = self._slippage(cfg)
                order.fill_price = fill_price + slip if order.direction == "BUY" else fill_price - slip
                order.fill_time = ts
                order.status = OrderStatus.FILLED
                order.slippage_pips = slip / cfg.pip_size
                order.commission = order.volume * cfg.commission_per_lot
                self._balance -= order.commission
                self._positions.append(order)

    def _slippage(self, cfg: SymbolConfig) -> float:
        return cfg.slippage_pips * cfg.pip_size * np.random.uniform(0.5, 1.5)

    def _open_order(self, symbol: str, signal: Dict[str, Any], tick: TickData, ts: datetime) -> None:
        cfg = self.symbol_configs[symbol]
        direction = str(signal.get("direction", "BUY")).upper()
        ep = float(signal.get("entry_price", 0.0))
        if not ep:
            ep = tick.ask if direction == "BUY" else tick.bid
        sl = float(signal.get("stop_loss"))
        tp = float(signal.get("take_profit"))

        risk_usd = self._balance * (self.config.risk_per_trade_pct / 100.0)
        risk_pips = abs(ep - sl) / cfg.pip_size
        if risk_pips <= 0:
            return
        volume = min(10.0, max(0.01, round(risk_usd / (risk_pips * cfg.point_value), 2)))

        order = BacktestOrder(
            symbol=symbol,
            direction=direction,
            order_type=OrderType.MARKET,
            volume=volume,
            entry_price=ep,
            stop_loss=sl,
            take_profit=tp,
        )
        self._orders.append(order)

    def _close_position(self, pos: BacktestOrder, exit_price: float, ts: datetime, cfg: SymbolConfig, reason: str) -> None:
        if pos not in self._positions:
            return
        fill = pos.fill_price or exit_price
        if pos.direction == "BUY":
            pnl_pips = (exit_price - fill) / cfg.pip_size
        else:
            pnl_pips = (fill - exit_price) / cfg.pip_size
        commission = pos.volume * cfg.commission_per_lot
        pnl_usd = pnl_pips * cfg.point_value * pos.volume - commission
        self._balance += pnl_usd

        trade = BacktestTrade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=pos.symbol,
            direction=pos.direction,
            entry_time=pos.fill_time.isoformat() if pos.fill_time else ts.isoformat(),
            exit_time=ts.isoformat(),
            entry_price=fill,
            exit_price=exit_price,
            stop_loss=pos.stop_loss or 0.0,
            take_profit=pos.take_profit or 0.0,
            lot_size=pos.volume,
            pnl_pips=pnl_pips,
            pnl_usd=pnl_usd,
            outcome="WIN" if pnl_usd > 0 else "LOSS" if pnl_usd < 0 else "BE",
        )
        self._closed_trades.append(trade)
        self._positions.remove(pos)

    def _build_result(self) -> Dict[str, Any]:
        metrics = PerformanceMetrics(self._closed_trades, self.config.initial_balance, self._balance)
        return {
            "config": {
                "symbols": self.config.symbols,
                "timeframes": self.config.timeframes,
                "initial_balance": self.config.initial_balance,
            },
            "final_balance": round(self._balance, 2),
            "total_return_pct": round((self._balance - self.config.initial_balance) / self.config.initial_balance * 100, 4),
            "total_trades": len(self._closed_trades),
            "open_positions": len(self._positions),
            "equity_curve": [(t.isoformat(), round(v, 2)) for t, v in self._equity_curve],
            "trades": [t.__dict__ for t in self._closed_trades],
            "metrics": metrics.to_dict(),
        }
