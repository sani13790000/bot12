"""
Multi-Symbol Backtest Engine
Phase-4 fix: renamed stmp_loss → stop_loss to match research/backtest/engine.py
Phase-6 fix: added MultiSymbolBacktestResult compat fields for walk_forward_advanced
             (net_profit_pct, sharpe_ratio, profit_factor, win_rate, max_drawdown_pct)
             max_drawdown now uses SharedBacktestMetrics
"""
from __future__ import annotations
import math
import statistics
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── try to import shared metrics from research engine (phase-3 bridge) ──
def _import_shared_metrics():
    try:
        from backend.research.backtest.engine import SharedBacktestMetrics
        return SharedBacktestMetrics
    except Exception:
        return None

_SM = _import_shared_metrics()


def compute_sharpe_unified(returns: list, risk_free: float = 0.0, periods: int = 252) -> float:
    if _SM:
        return _SM.sharpe_ratio(returns, risk_free, periods)
    if len(returns) < 2:
        return 0.0
    try:
        excess = [r - risk_free / periods for r in returns]
        mean_r = statistics.mean(excess)
        std_r  = statistics.stdev(excess)
        return round(mean_r / std_r * math.sqrt(periods), 4) if std_r else 0.0
    except Exception:
        return 0.0


def compute_sortino_unified(returns: list, risk_free: float = 0.0, periods: int = 252) -> float:
    if _SM:
        return _SM.sortino_ratio(returns, risk_free, periods)
    if len(returns) < 2:
        return 0.0
    try:
        target  = risk_free / periods
        neg     = [r for r in returns if r < target]
        if not neg:
            return float('inf')
        downside = math.sqrt(sum((r - target) ** 2 for r in neg) / len(returns))
        return round((statistics.mean(returns) - target) / downside * math.sqrt(periods), 4) if downside else 0.0
    except Exception:
        return 0.0


@dataclass
class Candle:
    timestamp: str
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0


@dataclass
class BacktestTrade:
    """Multi-symbol trade record — stop_loss field (was stmp_loss, now fixed)."""
    trade_id:      str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol:        str   = 'XAUUSD'
    timeframe:     str   = 'H1'
    direction:     str   = 'BUY'
    entry_time:    str   = ''
    exit_time:     str   = ''
    entry_price:   float = 0.0
    exit_price:    float = 0.0
    stop_loss:     float = 0.0    # ✔ fixed: was stmp_loss in previous version
    take_profit:   float = 0.0
    lot_size:      float = 0.01
    pnl_pips:      float = 0.0
    pnl_usd:       float = 0.0
    commission:    float = 0.0
    outcome:       str   = 'UNKNOWN'


@dataclass
class SymbolResult:
    symbol:          str
    timeframe:       str
    total_trades:    int   = 0
    winning_trades:  int   = 0
    losing_trades:   int   = 0
    total_pnl_usd:   float = 0.0
    win_rate:        float = 0.0
    profit_factor:   float = 0.0
    sharpe_ratio:    float = 0.0
    sortino_ratio:   float = 0.0
    max_drawdown_pct:float = 0.0
    trades:          List[BacktestTrade] = field(default_factory=list)
    metadata:        Dict[str, Any]      = field(default_factory=dict)


@dataclass
class MultiSymbolBacktestConfig:
    symbols:            List[str] = field(default_factory=lambda: ['XAUUSD'])
    timeframes:         List[str] = field(default_factory=lambda: ['H1'])
    initial_balance:    float     = 10_000.0
    risk_per_trade:     float     = 1.0
    slippage_pips:      float     = 0.5
    commission_usd:     float     = 3.5
    min_rr_ratio:       float     = 1.5
    pip_value:          float     = 10.0
    max_spread_pips:    float     = 3.0


@dataclass
class MultiSymbolBacktestResult:
    config:             MultiSymbolBacktestConfig
    symbol_results:     Dict[str, SymbolResult] = field(default_factory=dict)
    combined_pnl:       float = 0.0
    combined_trades:    int   = 0
    combined_wr:        float = 0.0
    best_symbol:        str   = ''
    worst_symbol:       str   = ''
    metadata:           Dict[str, Any] = field(default_factory=dict)

    # Phase-6: walk_forward_advanced compatibility fields
    net_profit_pct:     float = 0.0
    sharpe_ratio:       float = 0.0
    profit_factor:      float = 0.0
    win_rate:           float = 0.0    # 0-100
    max_drawdown_pct:   float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'combined_pnl':    round(self.combined_pnl, 2),
            'combined_trades': self.combined_trades,
            'combined_wr':     round(self.combined_wr, 2),
            'best_symbol':     self.best_symbol,
            'worst_symbol':    self.worst_symbol,
            'net_profit_pct':  round(self.net_profit_pct, 4),
            'sharpe_ratio':    round(self.sharpe_ratio, 4),
            'profit_factor':   round(self.profit_factor, 4),
            'win_rate':        round(self.win_rate, 2),
            'max_drawdown_pct':round(self.max_drawdown_pct, 4),
            'symbol_results':  {
                k: {
                    'total_trades':    v.total_trades,
                    'winning_trades':  v.winning_trades,
                    'losing_trades':   v.losing_trades,
                    'total_pnl_usd':   round(v.total_pnl_usd, 2),
                    'win_rate':        round(v.win_rate, 2),
                    'profit_factor':   round(v.profit_factor, 4),
                    'sharpe_ratio':    round(v.sharpe_ratio, 4),
                    'sortino_ratio':   round(v.sortino_ratio, 4),
                    'max_drawdown_pct':round(v.max_drawdown_pct, 4),
                }
                for k, v in self.symbol_results.items()
            },
        }


class MultiSymbolBacktestEngine:
    """Runs backtests across multiple symbols and timeframes."""

    def __init__(self, config: Optional[MultiSymbolBacktestConfig] = None) -> None:
        self._config = config or MultiSymbolBacktestConfig()

    def run_multi(
        self,
        candles_map: Dict[str, List[Candle]],
        signal_fn,
        config: Optional[MultiSymbolBacktestConfig] = None,
    ) -> MultiSymbolBacktestResult:
        cfg = config or self._config
        result = MultiSymbolBacktestResult(config=cfg)
        all_trades_flat: List[BacktestTrade] = []

        for symbol in cfg.symbols:
            candles = candles_map.get(symbol, [])
            if not candles:
                continue
            for tf in cfg.timeframes:
                key = f'{symbol}_{tf}'
                sym_result = self._run_symbol(symbol, tf, candles, signal_fn, cfg)
                result.symbol_results[key] = sym_result
                all_trades_flat.extend(sym_result.trades)

        if result.symbol_results:
            all_pnl    = [v.total_pnl_usd for v in result.symbol_results.values()]
            all_trades = [v.total_trades   for v in result.symbol_results.values()]
            all_wr     = [v.win_rate       for v in result.symbol_results.values() if v.total_trades > 0]
            result.combined_pnl    = sum(all_pnl)
            result.combined_trades = sum(all_trades)
            result.combined_wr     = statistics.mean(all_wr) if all_wr else 0.0
            best  = max(result.symbol_results.items(), key=lambda x: x[1].total_pnl_usd)
            worst = min(result.symbol_results.items(), key=lambda x: x[1].total_pnl_usd)
            result.best_symbol  = best[0]
            result.worst_symbol = worst[0]

            # Phase-6: aggregate walk_forward_advanced compat fields
            result.net_profit_pct = result.combined_pnl / cfg.initial_balance * 100.0
            # Aggregate Sharpe/PF/WR/MDD across all trades
            if all_trades_flat:
                trade_returns = [t.pnl_usd / cfg.initial_balance for t in all_trades_flat]
                result.sharpe_ratio    = compute_sharpe_unified(trade_returns)
                wins_usd = [t.pnl_usd for t in all_trades_flat if t.pnl_usd > 0]
                loss_usd = [t.pnl_usd for t in all_trades_flat if t.pnl_usd < 0]
                gp = sum(wins_usd)
                gl = abs(sum(loss_usd))
                result.profit_factor = round(gp / gl, 4) if gl else float('inf')
                total_t = len(all_trades_flat)
                result.win_rate = len(wins_usd) / total_t * 100.0 if total_t else 0.0
                if _SM:
                    equity = [cfg.initial_balance] + [
                        cfg.initial_balance + sum(t.pnl_usd for t in all_trades_flat[:i+1])
                        for i in range(len(all_trades_flat))
                    ]
                    dd_pct, _ = _SM.max_drawdown(equity)
                    result.max_drawdown_pct = dd_pct

        return result

    def _run_symbol(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
        signal_fn,
        cfg: MultiSymbolBacktestConfig,
    ) -> SymbolResult:
        trades: List[BacktestTrade] = []
        balance = cfg.initial_balance
        history: List[Candle] = []
        for i, candle in enumerate(candles):
            try:
                # Phase-6 lookahead fix: pass history BEFORE current candle
                sig = signal_fn(symbol, timeframe, candle, history[-50:]) if history else None
            except Exception:
                sig = None
            if sig and self._is_valid(sig, cfg):
                trade = self._simulate(symbol, timeframe, sig, candle, candles[i:], cfg, balance)
                if trade:
                    trades.append(trade)
                    balance += trade.pnl_usd
            history.append(candle)
        return self._compute_tf_metrics(symbol, timeframe, trades, cfg)

    def _compute_tf_metrics(
        self,
        symbol: str,
        timeframe: str,
        trades: List[BacktestTrade],
        cfg: MultiSymbolBacktestConfig,
    ) -> SymbolResult:
        result = SymbolResult(symbol=symbol, timeframe=timeframe, trades=trades)
        if not trades:
            return result
        wins   = [t for t in trades if t.outcome == 'WIN']
        losses = [t for t in trades if t.outcome == 'LOSS']
        result.total_trades   = len(trades)
        result.winning_trades = len(wins)
        result.losing_trades  = len(losses)
        result.total_pnl_usd  = sum(t.pnl_usd for t in trades)
        result.win_rate       = len(wins) / len(trades) * 100.0 if trades else 0.0
        gross_profit = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
        gross_loss   = abs(sum(t.pnl_usd for t in trades if t.pnl_usd < 0))
        result.profit_factor  = round(gross_profit / gross_loss, 4) if gross_loss else float('inf')
        trade_returns = [t.pnl_usd / cfg.initial_balance for t in trades]
        # ── use SharedBacktestMetrics via unified wrappers (phase-3 bridge) ──
        result.sharpe_ratio   = compute_sharpe_unified(trade_returns)
        result.sortino_ratio  = compute_sortino_unified(trade_returns)
        # max drawdown via SharedBacktestMetrics if available, else inline
        if _SM:
            equity = [cfg.initial_balance]
            for t in trades:
                equity.append(equity[-1] + t.pnl_usd)
            dd_pct, _ = _SM.max_drawdown(equity)
            result.max_drawdown_pct = dd_pct
        else:
            equity = cfg.initial_balance
            peak   = equity
            max_dd = 0.0
            for t in trades:
                equity += t.pnl_usd
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
            result.max_drawdown_pct = round(max_dd, 4)
        return result

    @staticmethod
    def _is_valid(sig: Dict[str, Any], cfg: MultiSymbolBacktestConfig) -> bool:
        ep = float(sig.get('entry_price', 0))
        sl = float(sig.get('stop_loss',   0))
        tp = float(sig.get('take_profit', 0))
        direction = str(sig.get('direction', '')).upper()
        if ep <= 0 or sl <= 0 or tp <= 0 or direction not in ('BUY', 'SELL'):
            return False
        risk, reward = (ep - sl, tp - ep) if direction == 'BUY' else (sl - ep, ep - tp)
        if risk <= 0 or reward <= 0:
            return False
        return reward / risk >= cfg.min_rr_ratio

    @staticmethod
    def _simulate(
        symbol: str,
        timeframe: str,
        sig: Dict[str, Any],
        entry_candle: Candle,
        future_candles: List[Candle],
        cfg: MultiSymbolBacktestConfig,
        balance: float,
    ) -> Optional[BacktestTrade]:
        direction = str(sig['direction']).upper()
        ep = float(sig['entry_price'])
        sl = float(sig['stop_loss'])
        tp = float(sig['take_profit'])
        slip       = cfg.slippage_pips * 0.1
        ep_actual  = ep + slip if direction == 'BUY' else ep - slip
        risk_pips  = abs(ep_actual - sl) * 10.0
        if risk_pips <= 0:
            return None
        risk_usd   = balance * (cfg.risk_per_trade / 100.0)
        lot        = max(0.01, min(round(risk_usd / (risk_pips * cfg.pip_value), 2), 10.0))
        exit_price = ep_actual; outcome = 'UNKNOWN'; exit_time = entry_candle.timestamp
        for future in future_candles[1:]:
            if direction == 'BUY':
                if future.low <= sl:
                    exit_price, outcome, exit_time = sl, 'LOSS', future.timestamp; break
                if future.high >= tp:
                    exit_price, outcome, exit_time = tp, 'WIN',  future.timestamp; break
            else:
                if future.high >= sl:
                    exit_price, outcome, exit_time = sl, 'LOSS', future.timestamp; break
                if future.low <= tp:
                    exit_price, outcome, exit_time = tp, 'WIN',  future.timestamp; break
        else:
            last       = future_candles[-1] if future_candles else entry_candle
            exit_price = last.close; outcome = 'BE'; exit_time = last.timestamp
        pnl_pts  = (exit_price - ep_actual) if direction == 'BUY' else (ep_actual - exit_price)
        pnl_pips = pnl_pts * 10.0
        pnl_usd  = pnl_pips * cfg.pip_value * lot - cfg.commission_usd * lot
        return BacktestTrade(
            symbol=symbol, timeframe=timeframe, direction=direction,
            entry_time=entry_candle.timestamp, exit_time=exit_time,
            entry_price=round(ep_actual, 5), exit_price=round(exit_price, 5),
            stop_loss=sl, take_profit=tp, lot_size=lot,
            pnl_pips=round(pnl_pips, 2), pnl_usd=round(pnl_usd, 2),
            commission=cfg.commission_usd * lot, outcome=outcome,
        )
