"""
Galaxy Vast AI Trading Platform
Research Backtest Engine
"""
from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    OPEN      = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_BE = "CLOSED_BE"
    CLOSED_MN = "CLOSED_MN"


@dataclass
class CandleData:
    timestamp: datetime
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float = 0.0
    spread:    float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open":   self.open,  "high":  self.high,
            "low":    self.low,   "close": self.close,
            "volume": self.volume, "spread": self.spread,
        }


@dataclass
class BacktestSignal:
    direction:    TradeDirection
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    confidence:   float
    time:         datetime
    symbol:       str = "XAUUSD"
    metadata:     Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestTrade:
    signal:       BacktestSignal
    entry_time:   datetime
    entry_price:  float
    direction:    TradeDirection
    stop_loss:    float
    take_profit:  float
    exit_time:    Optional[datetime]   = None
    exit_price:   Optional[float]      = None
    status:       TradeStatus          = TradeStatus.OPEN
    pnl_pips:     float                = 0.0
    pnl_usd:      float                = 0.0
    r_multiple:   float                = 0.0
    slippage:     float                = 0.0
    commission:   float                = 0.0

    def risk_pips(self) -> float:
        if self.direction == TradeDirection.BUY:
            return abs(self.entry_price - self.stop_loss) * 10
        return abs(self.stop_loss - self.entry_price) * 10

    def reward_pips(self) -> float:
        if self.direction == TradeDirection.BUY:
            return abs(self.take_profit - self.entry_price) * 10
        return abs(self.entry_price - self.take_profit) * 10

    def is_closed(self) -> bool:
        return self.status != TradeStatus.OPEN


@dataclass
class BacktestConfig:
    symbol:              str   = "XAUUSD"
    initial_balance:     float = 10_000.0
    lot_size:            float = 0.01
    commission_per_lot:  float = 3.50
    max_slippage_pips:   float = 2.0
    enable_slippage:     bool  = True
    max_spread_pips:     float = 5.0
    risk_per_trade_pct:  float = 1.0
    max_open_trades:     int   = 3


@dataclass
class EquityCurvePoint:
    timestamp:   datetime
    equity:      float
    balance:     float
    open_trades: int = 0


@dataclass
class BacktestResult:
    run_id:              str
    symbol:              str
    start_date:          datetime
    end_date:            datetime
    config:              BacktestConfig
    trades:              List[BacktestTrade]
    total_trades:        int
    winning_trades:      int
    losing_trades:       int
    initial_balance:     float
    final_balance:       float
    peak_balance:        float
    max_drawdown_pct:    float
    equity_curve:        List[EquityCurvePoint]
    win_rate:            float
    profit_factor:       float
    sharpe_ratio:        float
    sortino_ratio:       float
    calmar_ratio:        float
    expectancy_pips:     float
    avg_win_pips:        float
    avg_loss_pips:       float
    total_pnl_pips:      float
    total_pnl_usd:       float
    total_commission:    float
    run_time_seconds:    float

    @property
    def net_pnl_usd(self) -> float:
        return self.total_pnl_usd - self.total_commission

    @property
    def roi_pct(self) -> float:
        return ((self.final_balance - self.initial_balance) / self.initial_balance) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id, "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 3),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "expectancy_pips": round(self.expectancy_pips, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "net_pnl_usd": round(self.net_pnl_usd, 2),
            "roi_pct": round(self.roi_pct, 2),
            "total_commission": round(self.total_commission, 2),
            "run_time_seconds": round(self.run_time_seconds, 2),
        }


class SharedBacktestMetrics:
    """Shared metrics used by both backtest engines."""
    ANNUALIZATION_FACTOR = math.sqrt(252)

    @staticmethod
    def sharpe_ratio(returns: List[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean = statistics.mean(returns)
            std  = statistics.stdev(returns)
            if std == 0:
                return 0.0
            return ((mean - risk_free) / std) * SharedBacktestMetrics.ANNUALIZATION_FACTOR
        except Exception:
            return 0.0

    @staticmethod
    def sortino_ratio(returns: List[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean = statistics.mean(returns)
            neg  = [r for r in returns if r < risk_free]
            if not neg:
                return 10.0
            down_std = math.sqrt(sum((r - risk_free) ** 2 for r in neg) / len(neg))
            if down_std == 0:
                return 10.0
            return ((mean - risk_free) / down_std) * SharedBacktestMetrics.ANNUALIZATION_FACTOR
        except Exception:
            return 0.0

    @staticmethod
    def calmar_ratio(annual_return: float, max_drawdown_pct: float) -> float:
        if max_drawdown_pct <= 0:
            return 0.0
        return annual_return / max_drawdown_pct

    @staticmethod
    def max_drawdown(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak   = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def profit_factor(wins: List[float], losses: List[float]) -> float:
        total_win  = sum(w for w in wins   if w > 0)
        total_loss = sum(abs(l) for l in losses if l < 0)
        if total_loss == 0:
            return 999.0 if total_win > 0 else 0.0
        return total_win / total_loss

    @staticmethod
    def win_rate(winning: int, total: int) -> float:
        if total == 0:
            return 0.0
        return (winning / total) * 100

    @staticmethod
    def expectancy(win_rate_pct: float, avg_win: float, avg_loss: float) -> float:
        wr = win_rate_pct / 100
        return (wr * avg_win) - ((1 - wr) * abs(avg_loss))

    @staticmethod
    def build_equity_curve(
        trades: List[BacktestTrade],
        initial_balance: float,
    ) -> List[EquityCurvePoint]:
        curve: List[EquityCurvePoint] = []
        balance = initial_balance
        curve.append(EquityCurvePoint(
            timestamp=datetime.utcnow(), equity=balance, balance=balance
        ))
        for t in sorted(trades, key=lambda x: x.entry_time):
            if t.is_closed() and t.exit_time:
                balance += t.pnl_usd - t.commission
                curve.append(EquityCurvePoint(
                    timestamp=t.exit_time, equity=balance, balance=balance
                ))
        return curve


@dataclass
class SharedEquityPoint:
    timestamp: datetime
    equity:    float
    balance:   float
    drawdown:  float = 0.0


def apply_slippage(
    price: float,
    direction: TradeDirection,
    max_slippage_pips: float,
    symbol: str = "XAUUSD",
) -> float:
    pip_value = 0.1 if "XAU" in symbol.upper() else 0.0001
    slippage  = random.uniform(0, max_slippage_pips) * pip_value
    if direction == TradeDirection.BUY:
        return price + slippage
    return price - slippage


class BacktestEngine:
    """Async backtest engine with full metrics via SharedBacktestMetrics."""

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        self._config  = config or BacktestConfig()
        self._metrics = SharedBacktestMetrics()

    async def run(
        self,
        candles:           List[CandleData],
        signal_generator:  Callable[[List[CandleData]], Optional[BacktestSignal]],
        config:            Optional[BacktestConfig] = None,
    ) -> BacktestResult:
        import uuid
        cfg    = config or self._config
        t0     = time.time()
        run_id = str(uuid.uuid4())[:8]

        balance      = cfg.initial_balance
        peak_balance = cfg.initial_balance
        trades:       List[BacktestTrade]    = []
        equity_curve: List[EquityCurvePoint] = []
        open_trades:  List[BacktestTrade]    = []

        equity_curve.append(EquityCurvePoint(
            timestamp=candles[0].timestamp if candles else datetime.utcnow(),
            equity=balance, balance=balance
        ))

        lookback = 50
        for i in range(lookback, len(candles)):
            current    = candles[i]
            historical = candles[max(0, i - 200):i]

            still_open: List[BacktestTrade] = []
            for trade in open_trades:
                if self._check_exit(trade, current, cfg):
                    balance      += trade.pnl_usd - trade.commission
                    peak_balance  = max(peak_balance, balance)
                    trades.append(trade)
                    equity_curve.append(EquityCurvePoint(
                        timestamp=current.timestamp,
                        equity=balance, balance=balance,
                        open_trades=len(still_open),
                    ))
                else:
                    still_open.append(trade)
            open_trades = still_open

            if len(open_trades) >= cfg.max_open_trades:
                continue
            if current.spread > cfg.max_spread_pips:
                continue

            try:
                signal = signal_generator(historical)
            except Exception:
                signal = None
            if signal is None:
                continue

            entry = current.close
            if cfg.enable_slippage:
                entry = apply_slippage(entry, signal.direction, cfg.max_slippage_pips, cfg.symbol)

            comm  = cfg.commission_per_lot * cfg.lot_size
            trade = BacktestTrade(
                signal=signal, entry_time=current.timestamp,
                entry_price=entry, direction=signal.direction,
                stop_loss=signal.stop_loss, take_profit=signal.take_profit,
                commission=comm, slippage=abs(entry - current.close),
            )
            open_trades.append(trade)

        if candles:
            last = candles[-1]
            for trade in open_trades:
                self._force_close(trade, last)
                balance += trade.pnl_usd - trade.commission
                trades.append(trade)

        closed        = [t for t in trades if t.is_closed()]
        wins          = [t for t in closed if t.pnl_pips > 0]
        losses        = [t for t in closed if t.pnl_pips <= 0]
        win_pips_list = [t.pnl_pips for t in wins]
        loss_pips_list= [t.pnl_pips for t in losses]
        pnl_usd_list  = [t.pnl_usd  for t in closed]
        equity_values = [p.equity for p in equity_curve]

        win_rt  = SharedBacktestMetrics.win_rate(len(wins), len(closed))
        pf      = SharedBacktestMetrics.profit_factor(win_pips_list, loss_pips_list)
        dd      = SharedBacktestMetrics.max_drawdown(equity_values)
        returns = [p / cfg.initial_balance for p in pnl_usd_list]
        sharpe  = SharedBacktestMetrics.sharpe_ratio(returns)
        sortino = SharedBacktestMetrics.sortino_ratio(returns)
        annual  = ((balance - cfg.initial_balance) / cfg.initial_balance) * 100
        calmar  = SharedBacktestMetrics.calmar_ratio(annual, dd)
        avg_win = statistics.mean(win_pips_list)   if win_pips_list  else 0.0
        avg_los = statistics.mean(loss_pips_list)  if loss_pips_list else 0.0
        exp     = SharedBacktestMetrics.expectancy(win_rt, avg_win, avg_los)

        return BacktestResult(
            run_id=run_id, symbol=cfg.symbol,
            start_date=candles[0].timestamp  if candles else datetime.utcnow(),
            end_date=candles[-1].timestamp   if candles else datetime.utcnow(),
            config=cfg, trades=closed,
            total_trades=len(closed), winning_trades=len(wins), losing_trades=len(losses),
            initial_balance=cfg.initial_balance, final_balance=round(balance, 2),
            peak_balance=round(peak_balance, 2), max_drawdown_pct=dd,
            equity_curve=equity_curve,
            win_rate=win_rt, profit_factor=pf, sharpe_ratio=sharpe,
            sortino_ratio=sortino, calmar_ratio=calmar, expectancy_pips=exp,
            avg_win_pips=avg_win, avg_loss_pips=avg_los,
            total_pnl_pips=sum(t.pnl_pips for t in closed),
            total_pnl_usd=sum(t.pnl_usd   for t in closed),
            total_commission=sum(t.commission for t in closed),
            run_time_seconds=time.time() - t0,
        )

    def _check_exit(self, trade: BacktestTrade, candle: CandleData, cfg: BacktestConfig) -> bool:
        if trade.direction == TradeDirection.BUY:
            if candle.low  <= trade.stop_loss:   self._close_trade(trade, trade.stop_loss,   candle.timestamp, TradeStatus.CLOSED_SL); return True
            if candle.high >= trade.take_profit: self._close_trade(trade, trade.take_profit, candle.timestamp, TradeStatus.CLOSED_TP); return True
        else:
            if candle.high >= trade.stop_loss:   self._close_trade(trade, trade.stop_loss,   candle.timestamp, TradeStatus.CLOSED_SL); return True
            if candle.low  <= trade.take_profit: self._close_trade(trade, trade.take_profit, candle.timestamp, TradeStatus.CLOSED_TP); return True
        return False

    def _close_trade(self, trade: BacktestTrade, exit_price: float, exit_time: datetime, status: TradeStatus) -> None:
        trade.exit_time  = exit_time
        trade.exit_price = exit_price
        trade.status     = status
        pip_value        = 0.1
        if trade.direction == TradeDirection.BUY:
            trade.pnl_pips = (exit_price - trade.entry_price) * 10
        else:
            trade.pnl_pips = (trade.entry_price - exit_price) * 10
        trade.pnl_usd   = trade.pnl_pips * pip_value * self._config.lot_size * 100
        rp               = trade.risk_pips()
        trade.r_multiple = trade.pnl_pips / rp if rp > 0 else 0.0

    def _force_close(self, trade: BacktestTrade, candle: CandleData) -> None:
        self._close_trade(trade, candle.close, candle.timestamp, TradeStatus.CLOSED_MN)


backtest_engine = BacktestEngine()
