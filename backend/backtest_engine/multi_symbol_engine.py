"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: MultiSymbolBacktestEngine
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import math
import statistics
import random


class Timeframe(str, Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    M30 = "M30"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"


@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 2.0


@dataclass
class BacktestSignal:
    symbol: str
    timeframe: Timeframe
    direction: str          # BUY / SELL
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float       # 0-100
    time: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestTrade:
    signal: BacktestSignal
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    result: str = "OPEN"
    exit_reason: str = ""
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    duration_minutes: int = 0
    commission: float = 0.0


@dataclass
class EquityPoint:
    time: datetime
    equity: float
    drawdown: float
    drawdown_pct: float
    peak: float
    symbol: str = "PORTFOLIO"


@dataclass
class TimeframeResult:
    timeframe: Timeframe
    symbol: str
    total_trades: int
    win_rate: float
    profit_factor: float
    net_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float


@dataclass
class SymbolResult:
    symbol: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    timeframe_results: Dict[str, TimeframeResult] = field(default_factory=dict)


@dataclass
class MultiSymbolConfig:
    symbols: List[str]
    timeframes: List[Timeframe]
    start_date: datetime
    end_date: datetime
    initial_balance: float = 10_000.0
    risk_per_trade_pct: float = 1.0
    min_confidence: float = 70.0
    max_simultaneous_trades: int = 5
    max_portfolio_risk_pct: float = 5.0
    commission_per_lot: float = 7.0
    slippage_pips: float = 1.0
    spread_multiplier: float = 1.0
    use_realistic_spread: bool = True
    correlation_filter: bool = True
    max_correlation: float = 0.80
    name: str = "Galaxy Vast Backtest"


@dataclass
class MultiSymbolResult:
    config: MultiSymbolConfig
    symbol_results: Dict[str, SymbolResult]
    portfolio_equity: List[EquityPoint]
    all_trades: List[BacktestTrade]
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    final_balance: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    avg_trade_duration_min: float = 0.0
    total_commission: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": {"name": self.config.name, "symbols": self.config.symbols},
            "portfolio": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 4),
                "profit_factor": round(self.profit_factor, 4),
                "net_pnl": round(self.net_pnl, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 4),
                "max_drawdown_amount": round(self.max_drawdown_amount, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 4),
                "sortino_ratio": round(self.sortino_ratio, 4),
                "calmar_ratio": round(self.calmar_ratio, 4),
                "final_balance": round(self.final_balance, 2),
                "total_return_pct": round(self.total_return_pct, 4),
                "annualized_return_pct": round(self.annualized_return_pct, 4),
                "total_commission": round(self.total_commission, 2),
            },
            "symbols": {
                sym: {
                    "total_trades": r.total_trades,
                    "win_rate": round(r.win_rate, 4),
                    "profit_factor": round(r.profit_factor, 4),
                    "net_pnl": round(r.net_pnl, 2),
                    "max_drawdown_pct": round(r.max_drawdown_pct, 4),
                    "sharpe_ratio": round(r.sharpe_ratio, 4),
                }
                for sym, r in self.symbol_results.items()
            },
        }


class MultiSymbolBacktestEngine:
    """موتور بک‌تست چندنماد Galaxy Vast."""

    def __init__(self) -> None:
        self._trades: List[BacktestTrade] = []
        self._equity: List[EquityPoint] = []
        self._balance: float = 0.0
        self._peak: float = 0.0
        self._open_trades: List[BacktestTrade] = []

    async def run(
        self,
        config: MultiSymbolConfig,
        signal_provider: Callable[[str, Timeframe, datetime, datetime], List[BacktestSignal]],
        candle_provider: Callable[[str, Timeframe, datetime, datetime], List[Candle]],
    ) -> MultiSymbolResult:
        self._reset(config.initial_balance)

        symbol_results: Dict[str, SymbolResult] = {sym: SymbolResult(sym) for sym in config.symbols}

        for symbol in config.symbols:
            for tf in config.timeframes:
                candles = candle_provider(symbol, tf, config.start_date, config.end_date)
                signals = signal_provider(symbol, tf, config.start_date, config.end_date)

                if not candles:
                    candles = self._generate_synthetic_candles(symbol, tf, config.start_date, config.end_date)

                await self._simulate(symbol, tf, candles, signals, config, symbol_results[symbol])
                await asyncio.sleep(0)

        result = MultiSymbolResult(
            config=config,
            symbol_results=symbol_results,
            portfolio_equity=self._equity,
            all_trades=self._trades,
        )

        self._fill_portfolio_metrics(result, config)
        for sym, sr in symbol_results.items():
            self._fill_symbol_metrics(sr, config.initial_balance / len(config.symbols))

        return result

    async def _simulate(
        self,
        symbol: str,
        tf: Timeframe,
        candles: List[Candle],
        signals: List[BacktestSignal],
        config: MultiSymbolConfig,
        sym_result: SymbolResult,
    ) -> None:
        open_trades: List[BacktestTrade] = []

        for candle in candles:
            for trade in list(open_trades):
                if self._check_exit(trade, candle):
                    open_trades.remove(trade)

            eligible = [
                s for s in signals
                if s.timeframe == tf
                and s.time <= candle.time
                and s.confidence >= config.min_confidence
            ]

            for sig in eligible:
                if len(self._open_trades) >= config.max_simultaneous_trades:
                    break
                if config.correlation_filter and self._is_correlated(sig, self._open_trades, config.max_correlation):
                    continue

                entry = self._apply_slippage(sig.entry_price, sig.direction, config.slippage_pips, symbol)
                lot = self._compute_lot(self._balance, config.risk_per_trade_pct, entry, sig.stop_loss, symbol)
                commission = lot * config.commission_per_lot

                trade = BacktestTrade(
                    signal=sig,
                    entry_time=candle.time,
                    entry_price=entry,
                    commission=commission,
                )
                open_trades.append(trade)
                self._open_trades.append(trade)
                self._trades.append(trade)
                sym_result.total_trades += 1
                self._balance -= commission
                sym_result.total_trades = sym_result.total_trades

            ep = EquityPoint(
                time=candle.time,
                equity=self._balance,
                drawdown=max(0, self._peak - self._balance),
                drawdown_pct=max(0, (self._peak - self._balance) / self._peak * 100) if self._peak > 0 else 0,
                peak=self._peak,
                symbol=symbol,
            )
            self._equity.append(ep)

    def _check_exit(self, trade: BacktestTrade, candle: Candle) -> bool:
        sig = trade.signal
        if sig.direction == "BUY":
            if candle.low <= sig.stop_loss:
                self._close_trade(trade, sig.stop_loss, candle.time, "SL")
                return True
            if candle.high >= sig.take_profit:
                self._close_trade(trade, sig.take_profit, candle.time, "TP")
                return True
        else:
            if candle.high >= sig.stop_loss:
                self._close_trade(trade, sig.stop_loss, candle.time, "SL")
                return True
            if candle.low <= sig.take_profit:
                self._close_trade(trade, sig.take_profit, candle.time, "TP")
                return True
        trade.max_favorable = max(trade.max_favorable, candle.high - trade.entry_price if sig.direction == "BUY" else trade.entry_price - candle.low)
        trade.max_adverse = max(trade.max_adverse, trade.entry_price - candle.low if sig.direction == "BUY" else candle.high - trade.entry_price)
        return False

    def _close_trade(self, trade: BacktestTrade, exit_price: float, exit_time: datetime, reason: str) -> None:
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = reason
        trade.pnl = self._calc_pnl(trade, exit_price, trade.signal.symbol)
        trade.result = "WIN" if trade.pnl > 0 else "LOSS" if trade.pnl < 0 else "BE"
        trade.duration_minutes = int((exit_time - trade.entry_time).total_seconds() / 60)
        self._balance += trade.pnl
        if self._balance > self._peak:
            self._peak = self._balance
        if trade in self._open_trades:
            self._open_trades.remove(trade)

    def _calc_pnl(self, trade: BacktestTrade, exit_price: float, symbol: str) -> float:
        pip_size = 0.01 if "XAU" in symbol else 0.0001
        pip_value = 10.0 if "XAU" not in symbol else 1.0
        if trade.signal.direction == "BUY":
            pips = (exit_price - trade.entry_price) / pip_size
        else:
            pips = (trade.entry_price - exit_price) / pip_size
        lot = self._compute_lot(self._balance, 1.0, trade.entry_price, trade.signal.stop_loss, symbol)
        return pips * pip_value * lot - trade.commission

    def _apply_slippage(self, price: float, direction: str, slippage: float, symbol: str) -> float:
        pip_size = 0.01 if "XAU" in symbol else 0.0001
        slip = slippage * pip_size
        return price + slip if direction == "BUY" else price - slip

    def _compute_lot(self, balance: float, risk_pct: float, entry: float, sl: float, symbol: str) -> float:
        pip_size = 0.01 if "XAU" in symbol else 0.0001
        pip_value = 1.0 if "XAU" in symbol else 10.0
        risk_amount = balance * (risk_pct / 100)
        sl_pips = abs(entry - sl) / pip_size
        if sl_pips <= 0 or pip_value <= 0:
            return 0.01
        return round(max(0.01, min(risk_amount / (sl_pips * pip_value), 10.0)), 2)

    def _is_correlated(self, sig: BacktestSignal, open_trades: List[BacktestTrade], max_corr: float) -> bool:
        for trade in open_trades:
            if trade.signal.symbol == sig.symbol and trade.signal.direction == sig.direction:
                return True
        return False

    def _build_portfolio_equity(self, trades: List[BacktestTrade], initial: float) -> List[EquityPoint]:
        equity = initial
        peak = initial
        curve = []
        for t in sorted(trades, key=lambda x: x.exit_time or datetime.utcnow()):
            if t.exit_time and t.pnl != 0:
                equity += t.pnl
                if equity > peak:
                    peak = equity
                dd = peak - equity
                curve.append(EquityPoint(
                    time=t.exit_time, equity=equity,
                    drawdown=dd, drawdown_pct=(dd / peak * 100) if peak > 0 else 0,
                    peak=peak,
                ))
        return curve

    def _build_symbol_equity(self, trades: List[BacktestTrade], initial: float) -> List[EquityPoint]:
        return self._build_portfolio_equity(trades, initial)

    def _compute_tf_metrics(self, symbol: str, tf: Timeframe, trades: List[BacktestTrade], initial: float) -> TimeframeResult:
        pnl = [t.pnl for t in trades if t.result != "OPEN"]
        total = len(pnl)
        if not total:
            return TimeframeResult(tf, symbol, 0, 0, 0, 0, 0, 0)
        wins = [p for p in pnl if p > 0]
        losses = [p for p in pnl if p < 0]
        wr = len(wins) / total
        gp = sum(wins)
        gl = abs(sum(losses))
        pf = gp / gl if gl > 0 else (gp if gp > 0 else 0)
        net = sum(pnl)
        equity = [initial]
        for p in pnl:
            equity.append(equity[-1] + p)
        peak = equity[0]
        max_dd = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        returns = [p / initial for p in pnl]
        sr = self._sharpe(returns)
        return TimeframeResult(tf, symbol, total, wr, pf, net, max_dd, sr)

    def _fill_symbol_metrics(self, r: SymbolResult, initial: float) -> None:
        trades = [t for t in self._trades if t.signal.symbol == r.symbol and t.result != "OPEN"]
        if not trades:
            return
        pnl = [t.pnl for t in trades]
        wins = [p for p in pnl if p > 0]
        losses = [p for p in pnl if p < 0]
        r.total_trades = len(pnl)
        r.winning_trades = len(wins)
        r.losing_trades = len(losses)
        r.win_rate    = len(wins) / r.total_trades
        r.gross_profit = sum(wins)
        r.gross_loss   = abs(sum(losses))
        r.net_pnl      = sum(pnl)
        r.profit_factor = r.gross_profit / r.gross_loss if r.gross_loss > 0 else (r.gross_profit if r.gross_profit > 0 else 0)
        r.avg_win  = r.gross_profit / len(wins) if wins else 0
        r.avg_loss = r.gross_loss / len(losses) if losses else 0
        r.expectancy = r.win_rate * r.avg_win - (1 - r.win_rate) * r.avg_loss
        returns = [p / initial for p in pnl]
        r.sharpe_ratio  = self._sharpe(returns)
        r.sortino_ratio = self._sortino(returns)
        equity = initial
        peak = initial
        max_dd = 0.0
        for p in pnl:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        r.max_drawdown_pct = max_dd

    def _fill_portfolio_metrics(self, r: MultiSymbolResult, config: MultiSymbolConfig) -> None:
        trades = [t for t in r.all_trades if t.result != "OPEN"]
        if not trades:
            r.final_balance = config.initial_balance
            return
        pnl = [t.pnl for t in trades]
        wins = [p for p in pnl if p > 0]
        losses = [p for p in pnl if p < 0]
        r.total_trades = len(pnl)
        r.winning_trades = len(wins)
        r.losing_trades = len(losses)
        r.win_rate = len(wins) / r.total_trades
        r.gross_profit = sum(wins)
        r.gross_loss = abs(sum(losses))
        r.net_pnl = sum(pnl)
        r.profit_factor = r.gross_profit / r.gross_loss if r.gross_loss > 0 else (r.gross_profit if r.gross_profit > 0 else 0)
        r.total_commission = sum(t.commission for t in trades)
        r.final_balance = config.initial_balance + r.net_pnl
        r.total_return_pct = (r.net_pnl / config.initial_balance) * 100 if config.initial_balance > 0 else 0
        days = max((config.end_date - config.start_date).days, 1)
        r.annualized_return_pct = r.total_return_pct * (365 / days)
        returns = [p / config.initial_balance for p in pnl]
        r.sharpe_ratio = self._sharpe(returns)
        r.sortino_ratio = self._sortino(returns)
        equity_curve = [config.initial_balance]
        peak = config.initial_balance
        max_dd = max_dd_amt = 0.0
        for p in pnl:
            equity_curve.append(equity_curve[-1] + p)
        for v in equity_curve:
            if v > peak:
                peak = v
            dd_pct = (peak - v) / peak * 100 if peak > 0 else 0
            dd_amt = peak - v
            if dd_pct > max_dd:
                max_dd = dd_pct
                max_dd_amt = dd_amt
        r.max_drawdown_pct = max_dd
        r.max_drawdown_amount = max_dd_amt
        if max_dd > 0:
            r.calmar_ratio = r.annualized_return_pct / max_dd
        r.avg_trade_duration_min = sum(t.duration_minutes for t in trades) / len(trades)

    @staticmethod
    def _sharpe(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean_r = statistics.mean(returns) - rfr / ann
            std_r = statistics.stdev(returns)
            return (mean_r / std_r) * math.sqrt(ann) if std_r > 1e-10 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _sortino(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean_r = statistics.mean(returns) - rfr / ann
            downside = [r for r in returns if r < 0]
            if not downside:
                return float('inf') if mean_r > 0 else 0.0
            ds = statistics.stdev(downside) if len(downside) > 1 else abs(downside[0])
            return (mean_r / ds) * math.sqrt(ann) if ds > 1e-10 else 0.0
        except Exception:
            return 0.0

    def _reset(self, initial_balance: float) -> None:
        self._trades = []
        self._equity = []
        self._balance = initial_balance
        self._peak = initial_balance
        self._open_trades = []

    def _generate_synthetic_candles(
        self,
        symbol: str,
        tf: Timeframe,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        tf_minutes = {Timeframe.M1: 1, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
                      Timeframe.H1: 60, Timeframe.H4: 240, Timeframe.D1: 1440}
        step = timedelta(minutes=tf_minutes.get(tf, 60))
        base_price = 1950.0 if "XAU" in symbol else 1.1000
        candles = []
        current = start
        price = base_price
        while current < end:
            change = random.gauss(0, base_price * 0.001)
            open_p = price
            close_p = price + change
            high_p = max(open_p, close_p) + abs(random.gauss(0, base_price * 0.0005))
            low_p = min(open_p, close_p) - abs(random.gauss(0, base_price * 0.0005))
            candles.append(Candle(
                time=current, open=open_p, high=high_p, low=low_p, close=close_p,
                volume=random.uniform(100, 1000), spread=random.uniform(1.5, 3.5)
            ))
            price = close_p
            current += step
        return candles


# ════════════════════════════════════════════════════════════════════════════════
# Phase D — Unified Backtest Bridge Import
# ════════════════════════════════════════════════════════════════════════════════

def _import_shared_metrics():
    """لازی import از SharedBacktestMetrics. اگر نباشد — standalone کار می‌کند."""
    try:
        from ..research.backtest.engine import (
            SharedBacktestMetrics,
            SharedEquityPoint,
            apply_slippage as _shared_apply_slippage,
        )
        return SharedBacktestMetrics, SharedEquityPoint, _shared_apply_slippage
    except ImportError:
        return None, None, None


_SharedMetrics, _SharedEquityPoint, _shared_slippage = _import_shared_metrics()


def get_shared_metrics():
    """دسترسی به SharedBacktestMetrics اگر موجود باشد."""
    return _SharedMetrics


def compute_sharpe_unified(returns: list, rfr: float = 0.0, ann: float = 252) -> float:
    """از SharedBacktestMetrics اگر موجود، وگرنه fallback داخلی."""
    if _SharedMetrics is not None:
        return _SharedMetrics.sharpe_ratio(returns, rfr, ann)
    return MultiSymbolBacktestEngine._sharpe(returns, rfr, ann)


def compute_sortino_unified(returns: list, rfr: float = 0.0, ann: float = 252) -> float:
    """از SharedBacktestMetrics اگر موجود، وگرنه fallback داخلی."""
    if _SharedMetrics is not None:
        return _SharedMetrics.sortino_ratio(returns, rfr, ann)
    return MultiSymbolBacktestEngine._sortino(returns, rfr, ann)
