"""
Galaxy Vast AI Trading Platform
Multi-Symbol Multi-Timeframe Backtesting Engine

Features:
  - Multi-symbol parallel backtesting
  - Multi-timeframe analysis
  - Realistic slippage and spread modeling
  - Correlation-aware portfolio simulation
  - Equity curve generation
  - Drawdown calculation
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
    W1  = "W1"


@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0
    symbol: str = ""
    timeframe: Timeframe = Timeframe.H1


@dataclass
class BacktestSignal:
    symbol: str
    direction: str               # BUY / SELL
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float = 0.01
    confidence: float = 80.0
    timeframe: Timeframe = Timeframe.H1
    timestamp: datetime = field(default_factory=datetime.utcnow)
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
    result: str = "OPEN"         # WIN / LOSS / BE / OPEN
    exit_reason: str = ""        # TP / SL / TIMEOUT / FORCED
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
    timeframe_results: List[TimeframeResult]
    combined_trades: List[BacktestTrade]
    equity_curve: List[EquityPoint]
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


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
    # Portfolio metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    net_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    cagr: float = 0.0
    avg_trade_duration_minutes: int = 0
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": {
                "symbols": self.config.symbols,
                "timeframes": [tf.value for tf in self.config.timeframes],
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_balance": self.config.initial_balance,
                "risk_per_trade_pct": self.config.risk_per_trade_pct,
                "name": self.config.name,
            },
            "portfolio": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 4),
                "profit_factor": round(self.profit_factor, 4),
                "net_pnl": round(self.net_pnl, 2),
                "net_pnl_pct": round(self.net_pnl_pct, 4),
                "max_drawdown_pct": round(self.max_drawdown_pct, 4),
                "max_drawdown_amount": round(self.max_drawdown_amount, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 4),
                "sortino_ratio": round(self.sortino_ratio, 4),
                "calmar_ratio": round(self.calmar_ratio, 4),
                "recovery_factor": round(self.recovery_factor, 4),
                "expectancy": round(self.expectancy, 4),
                "cagr": round(self.cagr, 4),
                "avg_trade_duration_minutes": self.avg_trade_duration_minutes,
            },
            "per_symbol": {
                sym: {
                    "total_trades": r.total_trades,
                    "win_rate": round(r.win_rate, 4),
                    "profit_factor": round(r.profit_factor, 4),
                    "net_pnl": round(r.net_pnl, 2),
                    "max_drawdown_pct": round(r.max_drawdown_pct, 4),
                    "sharpe_ratio": round(r.sharpe_ratio, 4),
                    "calmar_ratio": round(r.calmar_ratio, 4),
                    "expectancy": round(r.expectancy, 4),
                } for sym, r in self.symbol_results.items()
            },
            "equity_curve": [
                {"time": p.time.isoformat(), "equity": round(p.equity, 2),
                 "drawdown_pct": round(p.drawdown_pct, 4)}
                for p in self.portfolio_equity[::max(1, len(self.portfolio_equity)//200)]
            ],
            "execution": {
                "duration_seconds": round(self.duration_seconds, 2),
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
            }
        }


# ─── Pip value helper ─────────────────────────────────────────────────────────
_PIP_VALUES: Dict[str, float] = {
    "XAUUSD": 1.0, "XAGUSD": 50.0,
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
    "NZDUSD": 10.0, "USDCAD": 10.0, "USDCHF": 10.0,
    "USDJPY": 0.09, "EURJPY": 0.09, "GBPJPY": 0.09,
    "US30": 1.0, "NAS100": 1.0, "SP500": 1.0,
}

def _pip_value(symbol: str) -> float:
    for k, v in _PIP_VALUES.items():
        if k in symbol.upper():
            return v
    return 10.0

def _pip_size(symbol: str) -> float:
    if "JPY" in symbol.upper():
        return 0.01
    if "XAU" in symbol.upper() or "XAG" in symbol.upper():
        return 0.1
    return 0.0001


# ─── Correlation matrix (simplified) ──────────────────────────────────────────
_CORRELATIONS: Dict[Tuple[str,str], float] = {
    ("EURUSD","GBPUSD"): 0.85, ("EURUSD","AUDUSD"): 0.72,
    ("EURUSD","NZDUSD"): 0.68, ("GBPUSD","AUDUSD"): 0.65,
    ("XAUUSD","XAGUSD"): 0.92, ("XAUUSD","EURUSD"): 0.45,
    ("USDJPY","USDCHF"): 0.75, ("US30","NAS100"):  0.88,
}

def _correlation(a: str, b: str) -> float:
    key = (a, b) if (a, b) in _CORRELATIONS else (b, a)
    return _CORRELATIONS.get(key, 0.0)


# ─── Core engine ──────────────────────────────────────────────────────────────
class MultiSymbolBacktestEngine:
    """
    Institutional-grade multi-symbol, multi-timeframe backtesting engine.
    Simulates realistic portfolio execution with correlation filtering,
    equity curve generation, and comprehensive performance metrics.
    """

    def __init__(self) -> None:
        self._open_trades: List[BacktestTrade] = []
        self._closed_trades: List[BacktestTrade] = []
        self._equity_curve: List[EquityPoint] = []
        self._balance: float = 10_000.0
        self._peak_equity: float = 10_000.0

    # ── Public API ────────────────────────────────────────────────────────────
    async def run(
        self,
        config: MultiSymbolConfig,
        candle_data: Dict[str, Dict[Timeframe, List[Candle]]],
        signal_generator: Callable[[str, Timeframe, List[Candle]], List[BacktestSignal]],
    ) -> MultiSymbolResult:
        """
        Run full multi-symbol, multi-timeframe backtest.

        Args:
            config: Backtest configuration
            candle_data: {symbol: {timeframe: [candles]}}
            signal_generator: Callable that returns signals given candles
        """
        start_time = datetime.utcnow()
        self._reset(config.initial_balance)

        symbol_results: Dict[str, SymbolResult] = {}

        # Run each symbol concurrently
        tasks = [
            self._backtest_symbol(symbol, config, candle_data.get(symbol, {}), signal_generator)
            for symbol in config.symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for sym, res in zip(config.symbols, results):
            symbol_results[sym] = res

        # Merge all trades into portfolio timeline
        all_trades = sorted(
            [t for r in symbol_results.values() for t in r.combined_trades],
            key=lambda t: t.entry_time,
        )

        # Build portfolio equity curve
        portfolio_equity = self._build_portfolio_equity(all_trades, config.initial_balance)

        # Compute portfolio-level metrics
        result = MultiSymbolResult(
            config=config,
            symbol_results=symbol_results,
            portfolio_equity=portfolio_equity,
            all_trades=all_trades,
        )
        self._fill_portfolio_metrics(result, config)
        result.start_time = start_time
        result.end_time = datetime.utcnow()
        result.duration_seconds = (result.end_time - result.start_time).total_seconds()
        return result

    # ── Per-symbol logic ──────────────────────────────────────────────────────
    async def _backtest_symbol(
        self,
        symbol: str,
        config: MultiSymbolConfig,
        tf_candles: Dict[Timeframe, List[Candle]],
        signal_generator: Callable,
    ) -> SymbolResult:
        tf_results: List[TimeframeResult] = []
        all_trades: List[BacktestTrade] = []

        for tf in config.timeframes:
            candles = tf_candles.get(tf, [])
            if not candles:
                candles = self._generate_synthetic_candles(symbol, tf, config.start_date, config.end_date)

            trades = await self._simulate_timeframe(symbol, tf, candles, config, signal_generator)
            all_trades.extend(trades)

            tf_result = self._compute_tf_metrics(symbol, tf, trades, config.initial_balance / len(config.symbols))
            tf_results.append(tf_result)

        equity_curve = self._build_symbol_equity(all_trades, config.initial_balance / len(config.symbols))
        sym_result = SymbolResult(
            symbol=symbol,
            timeframe_results=tf_results,
            combined_trades=all_trades,
            equity_curve=equity_curve,
        )
        self._fill_symbol_metrics(sym_result, config.initial_balance / len(config.symbols))
        return sym_result

    async def _simulate_timeframe(
        self,
        symbol: str,
        tf: Timeframe,
        candles: List[Candle],
        config: MultiSymbolConfig,
        signal_generator: Callable,
    ) -> List[BacktestTrade]:
        trades: List[BacktestTrade] = []
        balance = config.initial_balance / len(config.symbols) / len(config.timeframes)
        open_trades: List[BacktestTrade] = []

        for i, candle in enumerate(candles[20:], start=20):  # warm-up 20 candles
            # Check open trades for exits
            still_open: List[BacktestTrade] = []
            for trade in open_trades:
                if self._check_exit(trade, candle):
                    balance += trade.pnl
                    trades.append(trade)
                else:
                    still_open.append(trade)
            open_trades = still_open

            # Max simultaneous check
            if len(open_trades) >= config.max_simultaneous_trades:
                continue

            # Get signals from generator
            past_candles = candles[max(0, i-100):i+1]
            try:
                signals = signal_generator(symbol, tf, past_candles)
            except Exception:
                signals = []

            for sig in signals:
                if sig.confidence < config.min_confidence:
                    continue
                # Portfolio risk check
                if len(open_trades) >= config.max_simultaneous_trades:
                    break
                # Correlation check
                if config.correlation_filter and self._is_correlated(sig, open_trades, config.max_correlation):
                    continue
                # Apply slippage
                entry = self._apply_slippage(sig.entry_price, sig.direction, config.slippage_pips, symbol)
                # Compute lot size
                lot = self._compute_lot(balance, config.risk_per_trade_pct, entry, sig.stop_loss, symbol)
                # Commission
                commission = lot * config.commission_per_lot
                balance -= commission

                trade = BacktestTrade(
                    signal=sig,
                    entry_time=candle.time,
                    entry_price=entry,
                )
                trade.signal.lot_size = lot
                trade.commission = commission
                open_trades.append(trade)

        # Force close remaining
        if candles:
            last = candles[-1]
            for trade in open_trades:
                trade.exit_time = last.time
                trade.exit_price = last.close
                trade.result = "TIMEOUT"
                trade.exit_reason = "PERIOD_END"
                pnl = self._calc_pnl(trade, last.close, symbol)
                trade.pnl = pnl
                balance += pnl
                trades.append(trade)

        return trades

    # ── Trade helpers ─────────────────────────────────────────────────────────
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
        # Track MAE/MFE
        if sig.direction == "BUY":
            trade.max_favorable = max(trade.max_favorable, candle.high - trade.entry_price)
            trade.max_adverse  = min(trade.max_adverse,  candle.low  - trade.entry_price)
        else:
            trade.max_favorable = max(trade.max_favorable, trade.entry_price - candle.low)
            trade.max_adverse  = min(trade.max_adverse,  trade.entry_price - candle.high)
        return False

    def _close_trade(self, trade: BacktestTrade, exit_price: float, exit_time: datetime, reason: str) -> None:
        trade.exit_price  = exit_price
        trade.exit_time   = exit_time
        trade.exit_reason = reason
        duration = (exit_time - trade.entry_time).total_seconds() / 60
        trade.duration_minutes = int(duration)
        pnl = self._calc_pnl(trade, exit_price, trade.signal.symbol)
        trade.pnl = pnl - trade.commission
        initial = 10_000.0
        trade.pnl_pct = trade.pnl / initial
        if reason == "TP":
            trade.result = "WIN"
        elif reason == "SL":
            trade.result = "LOSS"
        else:
            trade.result = "BE"

    def _calc_pnl(self, trade: BacktestTrade, exit_price: float, symbol: str) -> float:
        pip_sz  = _pip_size(symbol)
        pip_val = _pip_value(symbol)
        lot = trade.signal.lot_size
        if pip_sz == 0:
            return 0.0
        if trade.signal.direction == "BUY":
            pips = (exit_price - trade.entry_price) / pip_sz
        else:
            pips = (trade.entry_price - exit_price) / pip_sz
        return pips * pip_val * lot

    def _apply_slippage(self, price: float, direction: str, slippage: float, symbol: str) -> float:
        pip = _pip_size(symbol)
        slip = slippage * pip
        return price + slip if direction == "BUY" else price - slip

    def _compute_lot(self, balance: float, risk_pct: float, entry: float, sl: float, symbol: str) -> float:
        risk_amount = balance * (risk_pct / 100)
        pip_sz  = _pip_size(symbol)
        pip_val = _pip_value(symbol)
        if pip_sz == 0 or pip_val == 0:
            return 0.01
        sl_pips = abs(entry - sl) / pip_sz
        if sl_pips == 0:
            return 0.01
        lot = risk_amount / (sl_pips * pip_val)
        return max(0.01, min(round(lot, 2), 100.0))

    def _is_correlated(self, sig: BacktestSignal, open_trades: List[BacktestTrade], max_corr: float) -> bool:
        for trade in open_trades:
            corr = _correlation(sig.symbol, trade.signal.symbol)
            if corr >= max_corr and sig.direction == trade.signal.direction:
                return True
        return False

    # ── Equity curve ──────────────────────────────────────────────────────────
    def _build_portfolio_equity(self, trades: List[BacktestTrade], initial: float) -> List[EquityPoint]:
        equity = initial
        peak   = initial
        points = [EquityPoint(time=datetime.utcnow() - timedelta(days=365), equity=initial, drawdown=0, drawdown_pct=0, peak=initial)]
        for t in trades:
            if t.exit_time and t.pnl != 0:
                equity += t.pnl
                peak = max(peak, equity)
                dd = peak - equity
                dd_pct = dd / peak if peak > 0 else 0
                points.append(EquityPoint(time=t.exit_time, equity=equity, drawdown=dd, drawdown_pct=dd_pct, peak=peak))
        return points

    def _build_symbol_equity(self, trades: List[BacktestTrade], initial: float) -> List[EquityPoint]:
        return self._build_portfolio_equity(trades, initial)

    # ── Metrics ───────────────────────────────────────────────────────────────
    def _compute_tf_metrics(self, symbol: str, tf: Timeframe, trades: List[BacktestTrade], initial: float) -> TimeframeResult:
        closed = [t for t in trades if t.result in ("WIN","LOSS","BE")]
        total = len(closed)
        if total == 0:
            return TimeframeResult(tf, symbol, 0, 0, 0, 0, 0, 0)
        wins   = [t for t in closed if t.result == "WIN"]
        losses = [t for t in closed if t.result == "LOSS"]
        win_rate = len(wins) / total
        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in losses))
        pf = gp / gl if gl > 0 else (gp if gp > 0 else 0)
        net = sum(t.pnl for t in closed)
        # Sharpe (simplified daily return approximation)
        returns = [t.pnl / initial for t in closed]
        sr = self._sharpe(returns)
        # MaxDD
        eq = initial
        peak = initial
        max_dd = 0.0
        for t in closed:
            eq += t.pnl
            peak = max(peak, eq)
            dd_pct = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd_pct)
        return TimeframeResult(tf, symbol, total, win_rate, pf, net, max_dd, sr)

    def _fill_symbol_metrics(self, r: SymbolResult, initial: float) -> None:
        closed = [t for t in r.combined_trades if t.result in ("WIN","LOSS","BE","TIMEOUT")]
        r.total_trades = len(closed)
        if r.total_trades == 0:
            return
        wins   = [t for t in closed if t.result == "WIN"]
        losses = [t for t in closed if t.result == "LOSS"]
        r.win_rate    = len(wins) / r.total_trades
        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in losses))
        r.profit_factor = gp / gl if gl > 0 else (gp if gp > 0 else 0)
        r.net_pnl = sum(t.pnl for t in closed)
        r.avg_win  = gp / len(wins)  if wins   else 0
        r.avg_loss = gl / len(losses) if losses else 0
        r.avg_rr   = r.avg_win / r.avg_loss if r.avg_loss > 0 else 0
        r.expectancy = r.win_rate * r.avg_win - (1 - r.win_rate) * r.avg_loss
        returns = [t.pnl / initial for t in closed]
        r.sharpe_ratio  = self._sharpe(returns)
        r.sortino_ratio = self._sortino(returns)
        # MaxDD
        eq = initial; peak = initial; max_dd = 0.0
        for t in closed:
            eq += t.pnl; peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        r.max_drawdown_pct = max_dd
        years = max((r.combined_trades[-1].exit_time - r.combined_trades[0].entry_time).days / 365, 1/12) if r.combined_trades else 1
        final = initial + r.net_pnl
        r.calmar_ratio    = ((final/initial)**(1/years)-1) / max_dd if max_dd > 0 else 0
        r.recovery_factor = r.net_pnl / (max_dd * initial) if max_dd > 0 else 0
        # Streaks
        streak = best_w = best_l = 0
        for t in closed:
            if t.result == "WIN":
                streak = max(streak, 0) + 1; best_w = max(best_w, streak)
            elif t.result == "LOSS":
                streak = min(streak, 0) - 1; best_l = max(best_l, abs(streak))
            else:
                streak = 0
        r.max_consecutive_wins   = best_w
        r.max_consecutive_losses = best_l

    def _fill_portfolio_metrics(self, r: MultiSymbolResult, config: MultiSymbolConfig) -> None:
        closed = [t for t in r.all_trades if t.result in ("WIN","LOSS","BE","TIMEOUT")]
        r.total_trades   = len(closed)
        if r.total_trades == 0:
            return
        wins   = [t for t in closed if t.result == "WIN"]
        losses = [t for t in closed if t.result == "LOSS"]
        r.winning_trades = len(wins)
        r.losing_trades  = len(losses)
        r.win_rate       = r.winning_trades / r.total_trades
        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in losses))
        r.profit_factor  = gp / gl if gl > 0 else (gp if gp > 0 else 0)
        r.net_pnl        = sum(t.pnl for t in closed)
        r.net_pnl_pct    = r.net_pnl / config.initial_balance
        avg_win  = gp / len(wins)  if wins   else 0
        avg_loss = gl / len(losses) if losses else 0
        r.expectancy = r.win_rate * avg_win - (1 - r.win_rate) * avg_loss
        returns = [t.pnl / config.initial_balance for t in closed]
        r.sharpe_ratio  = self._sharpe(returns)
        r.sortino_ratio = self._sortino(returns)
        # MaxDD
        eq = config.initial_balance; peak = config.initial_balance
        max_dd_pct = 0.0; max_dd_amt = 0.0
        for t in closed:
            eq += t.pnl; peak = max(peak, eq)
            dd_amt = peak - eq; dd_pct = dd_amt / peak if peak > 0 else 0
            max_dd_pct = max(max_dd_pct, dd_pct)
            max_dd_amt = max(max_dd_amt, dd_amt)
        r.max_drawdown_pct    = max_dd_pct
        r.max_drawdown_amount = max_dd_amt
        if closed:
            date0 = closed[0].entry_time; date1 = closed[-1].exit_time or datetime.utcnow()
            years = max((date1 - date0).days / 365, 1/12)
            final = config.initial_balance + r.net_pnl
            cagr  = (final / config.initial_balance) ** (1/years) - 1
            r.cagr         = cagr
            r.calmar_ratio = cagr / max_dd_pct if max_dd_pct > 0 else 0
            r.avg_trade_duration_minutes = int(statistics.mean(t.duration_minutes for t in closed if t.duration_minutes > 0) if closed else 0)
        r.recovery_factor = r.net_pnl / max_dd_amt if max_dd_amt > 0 else 0

    # ── Stat helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _sharpe(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
        if len(returns) < 2:
            return 0.0
        avg = statistics.mean(returns) - rfr / ann
        std = statistics.stdev(returns)
        return (avg / std * math.sqrt(ann)) if std > 0 else 0.0

    @staticmethod
    def _sortino(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
        if len(returns) < 2:
            return 0.0
        avg = statistics.mean(returns) - rfr / ann
        neg = [r for r in returns if r < 0]
        if not neg:
            return 999.0
        down_std = statistics.stdev(neg)
        return (avg / down_std * math.sqrt(ann)) if down_std > 0 else 0.0

    # ── Reset ─────────────────────────────────────────────────────────────────
    def _reset(self, initial_balance: float) -> None:
        self._open_trades   = []
        self._closed_trades = []
        self._equity_curve  = []
        self._balance       = initial_balance
        self._peak_equity   = initial_balance

    # ── Synthetic candles (for testing / missing data) ────────────────────────
    def _generate_synthetic_candles(
        self, symbol: str, tf: Timeframe, start: datetime, end: datetime
    ) -> List[Candle]:
        tf_minutes = {"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240,"D1":1440,"W1":10080}
        mins = tf_minutes.get(tf.value, 60)
        base_prices = {
            "XAUUSD": 2000.0, "EURUSD": 1.085, "GBPUSD": 1.265,
            "USDJPY": 149.0,  "AUDUSD": 0.655, "USDCAD": 1.355,
            "US30": 38000.0,  "NAS100": 17000.0,
        }
        base  = next((v for k, v in base_prices.items() if k in symbol.upper()), 1.0)
        volatility = base * 0.003
        candles: List[Candle] = []
        current_time = start
        price = base
        rng = random.Random(hash(symbol))
        while current_time < end:
            move = rng.gauss(0, volatility)
            o = price
            c = price + move
            h = max(o, c) + abs(rng.gauss(0, volatility * 0.3))
            l = min(o, c) - abs(rng.gauss(0, volatility * 0.3))
            spread = base * 0.0002
            candles.append(Candle(time=current_time, open=round(o,5), high=round(h,5),
                                  low=round(l,5), close=round(c,5),
                                  volume=rng.randint(100,5000), spread=spread,
                                  symbol=symbol, timeframe=tf))
            price = c
            current_time += timedelta(minutes=mins)
        return candles
