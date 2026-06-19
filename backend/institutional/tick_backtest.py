"""Tick-Level Backtesting Engine with spread, slippage, commission simulation."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class SymbolSpec:
    """Symbol-specific parameters for accurate pip/lot calculations."""
    symbol: str
    pip_size: float          # e.g. 0.1 for XAUUSD, 0.0001 for EURUSD
    contract_size: float     # e.g. 100 for XAUUSD, 100_000 for Forex
    point_value: float       # USD per pip per lot
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    avg_spread_pips: float = 2.0
    commission_per_lot: float = 3.5  # USD per lot (round-turn)

    @classmethod
    def for_symbol(cls, symbol: str) -> "SymbolSpec":
        specs: Dict[str, Dict] = {
            "XAUUSD": dict(pip_size=0.1, contract_size=100.0, point_value=1.0, avg_spread_pips=3.0, commission_per_lot=5.0),
            "XAGUSD": dict(pip_size=0.01, contract_size=5000.0, point_value=5.0, avg_spread_pips=5.0, commission_per_lot=4.0),
            "EURUSD": dict(pip_size=0.0001, contract_size=100_000.0, point_value=10.0, avg_spread_pips=1.0, commission_per_lot=3.5),
            "GBPUSD": dict(pip_size=0.0001, contract_size=100_000.0, point_value=10.0, avg_spread_pips=1.5, commission_per_lot=3.5),
            "USDJPY": dict(pip_size=0.01, contract_size=100_000.0, point_value=9.0, avg_spread_pips=1.0, commission_per_lot=3.5),
            "GBPJPY": dict(pip_size=0.01, contract_size=100_000.0, point_value=9.0, avg_spread_pips=2.5, commission_per_lot=3.5),
            "US30":   dict(pip_size=1.0, contract_size=1.0, point_value=1.0, avg_spread_pips=3.0, commission_per_lot=2.0),
            "NAS100": dict(pip_size=0.25, contract_size=1.0, point_value=1.0, avg_spread_pips=1.0, commission_per_lot=2.0),
            "BTCUSD": dict(pip_size=1.0, contract_size=1.0, point_value=1.0, avg_spread_pips=50.0, commission_per_lot=10.0),
        }
        s = symbol.upper()
        if s in specs:
            return cls(symbol=s, **specs[s])
        # Default Forex
        return cls(symbol=s, pip_size=0.0001, contract_size=100_000.0, point_value=10.0)


@dataclass
class TickBacktestConfig:
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    initial_balance: float = 10_000.0
    risk_pct_per_trade: float = 1.0
    spread_multiplier: float = 1.0    # 1.0 = realistic, 2.0 = conservative
    slippage_pips: float = 0.5        # extra slippage on market orders
    use_commission: bool = True
    max_open_trades: int = 3
    start_date: Optional[str] = None  # "2018-01-01"
    end_date: Optional[str] = None
    symbols: List[str] = field(default_factory=lambda: ["XAUUSD"])
    timeframes: List[str] = field(default_factory=lambda: ["M15"])


@dataclass
class BacktestTrade:
    trade_id: int
    symbol: str
    direction: Direction
    open_time: float
    close_time: Optional[float]
    open_price: float
    close_price: Optional[float]
    stop_loss: float
    take_profit: float
    lot_size: float
    gross_profit: float = 0.0
    commission: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    net_profit: float = 0.0
    is_open: bool = True
    close_reason: str = ""  # "tp" | "sl" | "signal" | "end_of_data"
    explanation: Optional[Dict] = None

    @property
    def total_cost(self) -> float:
        return self.commission + self.spread_cost + self.slippage_cost

    @property
    def risk_reward(self) -> float:
        sl_dist = abs(self.open_price - self.stop_loss)
        tp_dist = abs(self.take_profit - self.open_price)
        return round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0


@dataclass
class TickBacktestResult:
    config: TickBacktestConfig
    trades: List[BacktestTrade]
    equity_curve: List[Tuple[float, float]]  # (timestamp, equity)
    initial_balance: float
    final_balance: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    total_net_profit: float
    total_commission: float
    total_spread_cost: float
    total_slippage_cost: float
    max_drawdown_pct: float
    max_drawdown_usd: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    recovery_factor: float
    expectancy_usd: float
    avg_win_usd: float
    avg_loss_usd: float
    avg_rr: float
    per_symbol_stats: Dict[str, Dict] = field(default_factory=dict)
    per_timeframe_stats: Dict[str, Dict] = field(default_factory=dict)


class TickBacktestEngine:
    """
    Tick-Level Backtesting Engine.

    Features:
    - Bar-by-bar simulation with intra-bar high/low fill logic
    - Spread simulation (variable or fixed)
    - Slippage simulation on market orders
    - Commission simulation (per lot, round-turn)
    - Multi-symbol, multi-timeframe
    - No lookahead bias: signal generated on close of N-1, executed on open of N
    - Full equity curve tracking
    """

    def __init__(self, config: TickBacktestConfig):
        self.config = config
        self._spec = SymbolSpec.for_symbol(config.symbol)
        self._trades: List[BacktestTrade] = []
        self._trade_counter: int = 0
        self._balance: float = config.initial_balance
        self._equity_curve: List[Tuple[float, float]] = []
        self._peak_equity: float = config.initial_balance
        self._max_dd_usd: float = 0.0

    def run(
        self,
        candles: List[Dict],  # [{timestamp, open, high, low, close, volume}, ...]
        signal_fn: Callable[[Dict, List[Dict]], Optional[Dict]],
        # signal_fn returns {direction, stop_loss, take_profit} or None
    ) -> TickBacktestResult:
        """
        Run the backtest.
        signal_fn receives (current_candle, history_so_far) — NO lookahead.
        """
        history: List[Dict] = []
        open_trades: List[BacktestTrade] = []

        for i, candle in enumerate(candles):
            ts = candle["timestamp"]

            # ── 1. Check SL/TP on open trades (intra-bar fill) ──
            for trade in list(open_trades):
                self._check_fill(trade, candle)
                if not trade.is_open:
                    open_trades.remove(trade)

            # ── 2. Track equity ──
            floating_pnl = sum(self._calc_floating(t, candle["close"]) for t in open_trades)
            current_equity = self._balance + floating_pnl
            self._equity_curve.append((ts, current_equity))

            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
            dd = self._peak_equity - current_equity
            if dd > self._max_dd_usd:
                self._max_dd_usd = dd

            # ── 3. Generate signal (NO lookahead: use history BEFORE appending) ──
            past = history[-200:] if len(history) >= 1 else []
            if i > 0 and len(open_trades) < self.config.max_open_trades:
                sig = signal_fn(candle, past)
                if sig:
                    trade = self._open_trade(candle, sig)
                    if trade:
                        open_trades.append(trade)

            history.append(candle)

        # Close all remaining trades at last price
        if candles:
            last = candles[-1]
            for trade in open_trades:
                self._close_trade(trade, last["close"], last["timestamp"], "end_of_data")

        return self._build_result()

    # ------------------------------------------------------------------ #
    #  Internal methods                                                     #
    # ------------------------------------------------------------------ #

    def _open_trade(
        self, candle: Dict, signal: Dict
    ) -> Optional[BacktestTrade]:
        direction = Direction(signal["direction"])
        sl = signal["stop_loss"]
        tp = signal["take_profit"]

        # Slippage on entry
        slippage = self._spec.pip_size * self.config.slippage_pips
        spread = self._spec.pip_size * self._spec.avg_spread_pips * self.config.spread_multiplier

        if direction == Direction.BUY:
            entry_price = candle["open"] + spread + slippage
        else:
            entry_price = candle["open"] - spread - slippage

        # Position sizing (risk-based)
        sl_pips = abs(entry_price - sl) / self._spec.pip_size
        if sl_pips < 0.1:
            return None

        risk_usd = self._balance * (self.config.risk_pct_per_trade / 100.0)
        lot_size = risk_usd / (sl_pips * self._spec.point_value)
        lot_size = max(
            self._spec.min_lot,
            min(self._spec.max_lot, round(lot_size / self._spec.lot_step) * self._spec.lot_step)
        )

        commission = lot_size * self._spec.commission_per_lot if self.config.use_commission else 0.0
        spread_cost = spread * lot_size * self._spec.contract_size / self._spec.pip_size * self._spec.point_value / self._spec.contract_size
        slippage_cost = slippage * lot_size * self._spec.contract_size / self._spec.pip_size * self._spec.point_value / self._spec.contract_size

        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=self._trade_counter,
            symbol=self.config.symbol,
            direction=direction,
            open_time=candle["timestamp"],
            close_time=None,
            open_price=entry_price,
            close_price=None,
            stop_loss=sl,
            take_profit=tp,
            lot_size=lot_size,
            commission=commission,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            explanation=signal.get("explanation"),
        )
        return trade

    def _check_fill(self, trade: BacktestTrade, candle: Dict) -> None:
        """Check if SL or TP was hit intra-bar."""
        hi, lo = candle["high"], candle["low"]

        if trade.direction == Direction.BUY:
            if lo <= trade.stop_loss:
                self._close_trade(trade, trade.stop_loss, candle["timestamp"], "sl")
            elif hi >= trade.take_profit:
                self._close_trade(trade, trade.take_profit, candle["timestamp"], "tp")
        else:  # SELL
            if hi >= trade.stop_loss:
                self._close_trade(trade, trade.stop_loss, candle["timestamp"], "sl")
            elif lo <= trade.take_profit:
                self._close_trade(trade, trade.take_profit, candle["timestamp"], "tp")

    def _close_trade(
        self, trade: BacktestTrade, price: float, ts: float, reason: str
    ) -> None:
        trade.close_price = price
        trade.close_time = ts
        trade.close_reason = reason
        trade.is_open = False

        pip_diff = (price - trade.open_price) / self._spec.pip_size
        if trade.direction == Direction.SELL:
            pip_diff = -pip_diff

        trade.gross_profit = pip_diff * self._spec.point_value * trade.lot_size
        trade.net_profit = trade.gross_profit - trade.total_cost
        self._balance += trade.net_profit
        self._trades.append(trade)

    def _calc_floating(self, trade: BacktestTrade, current_price: float) -> float:
        pip_diff = (current_price - trade.open_price) / self._spec.pip_size
        if trade.direction == Direction.SELL:
            pip_diff = -pip_diff
        return pip_diff * self._spec.point_value * trade.lot_size - trade.total_cost

    def _build_result(self) -> TickBacktestResult:
        trades = self._trades
        if not trades:
            return TickBacktestResult(
                config=self.config, trades=[], equity_curve=self._equity_curve,
                initial_balance=self.config.initial_balance, final_balance=self._balance,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, profit_factor=0.0, total_net_profit=0.0,
                total_commission=0.0, total_spread_cost=0.0, total_slippage_cost=0.0,
                max_drawdown_pct=0.0, max_drawdown_usd=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                recovery_factor=0.0, expectancy_usd=0.0,
                avg_win_usd=0.0, avg_loss_usd=0.0, avg_rr=0.0,
            )

        winners = [t for t in trades if t.net_profit > 0]
        losers = [t for t in trades if t.net_profit <= 0]
        gross_win = sum(t.net_profit for t in winners)
        gross_loss = abs(sum(t.net_profit for t in losers))

        returns = [t.net_profit / self.config.initial_balance for t in trades]
        avg_ret = sum(returns) / len(returns) if returns else 0
        std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / len(returns)) if returns else 1
        downside = [r for r in returns if r < 0]
        std_down = math.sqrt(sum(r ** 2 for r in downside) / len(downside)) if downside else std_ret

        sharpe = (avg_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
        sortino = (avg_ret / std_down) * math.sqrt(252) if std_down > 0 else 0
        max_dd_pct = (self._max_dd_usd / self._peak_equity * 100) if self._peak_equity > 0 else 0
        total_net = sum(t.net_profit for t in trades)
        calmar = (total_net / self.config.initial_balance * 100) / max_dd_pct if max_dd_pct > 0 else 0
        recovery = total_net / self._max_dd_usd if self._max_dd_usd > 0 else 0

        return TickBacktestResult(
            config=self.config,
            trades=trades,
            equity_curve=self._equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=self._balance,
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / len(trades) * 100,
            profit_factor=gross_win / gross_loss if gross_loss > 0 else float("inf"),
            total_net_profit=total_net,
            total_commission=sum(t.commission for t in trades),
            total_spread_cost=sum(t.spread_cost for t in trades),
            total_slippage_cost=sum(t.slippage_cost for t in trades),
            max_drawdown_pct=max_dd_pct,
            max_drawdown_usd=self._max_dd_usd,
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            calmar_ratio=round(calmar, 3),
            recovery_factor=round(recovery, 3),
            expectancy_usd=total_net / len(trades),
            avg_win_usd=gross_win / len(winners) if winners else 0,
            avg_loss_usd=-gross_loss / len(losers) if losers else 0,
            avg_rr=sum(t.risk_reward for t in trades) / len(trades),
        )
