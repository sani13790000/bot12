"""Galaxy Vast AI Trading Platform — Backtest Engine (phase6 lookahead fix)"""
from __future__ import annotations
import math, statistics, uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SharedEquityPoint:
    timestamp: str
    equity:    float
    drawdown:  float = 0.0
    trade_id:  Optional[str] = None


class SharedBacktestMetrics:
    @staticmethod
    def sharpe_ratio(returns, risk_free_rate=0.0, periods_per_year=252):
        if len(returns) < 2: return 0.0
        try:
            excess = [r - risk_free_rate / periods_per_year for r in returns]
            mean_r = statistics.mean(excess); std_r = statistics.stdev(excess)
            if std_r == 0: return 0.0
            return round(mean_r / std_r * math.sqrt(periods_per_year), 4)
        except Exception: return 0.0

    @staticmethod
    def sortino_ratio(returns, risk_free_rate=0.0, periods_per_year=252):
        if len(returns) < 2: return 0.0
        try:
            target = risk_free_rate / periods_per_year
            neg = [r for r in returns if r < target]
            if not neg: return float('inf')
            downside_std = math.sqrt(sum((r - target)**2 for r in neg) / len(returns))
            if downside_std == 0: return 0.0
            return round((statistics.mean(returns) - target) / downside_std * math.sqrt(periods_per_year), 4)
        except Exception: return 0.0

    @staticmethod
    def calmar_ratio(returns, periods_per_year=252):
        if len(returns) < 2: return 0.0
        try:
            eq = [10000.0]
            for r in returns: eq.append(eq[-1] * (1.0 + r))
            dd_pct, _ = SharedBacktestMetrics.max_drawdown(eq)
            if dd_pct <= 0: return 0.0
            return round(statistics.mean(returns) * periods_per_year * 100.0 / dd_pct, 4)
        except Exception: return 0.0

    @staticmethod
    def max_drawdown(equity_curve):
        if not equity_curve: return 0.0, 0.0
        peak = equity_curve[0]; max_dd = 0.0; max_abs = 0.0
        for val in equity_curve:
            if val > peak: peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd: max_dd = dd; max_abs = peak - val
        return round(max_dd * 100.0, 4), round(max_abs, 4)

    @staticmethod
    def profit_factor(gross_profit, gross_loss):
        if gross_loss == 0: return float('inf') if gross_profit > 0 else 0.0
        return round(abs(gross_profit / gross_loss), 4)

    @staticmethod
    def win_rate(wins, total):
        if total == 0: return 0.0
        return round(wins / total * 100.0, 2)

    @staticmethod
    def expectancy(win_rate_pct, avg_win, avg_loss):
        wr = win_rate_pct / 100.0
        return round(wr * avg_win - (1.0 - wr) * abs(avg_loss), 4)

    @staticmethod
    def build_equity_curve(trades, initial_balance=10_000.0):
        curve = [SharedEquityPoint(timestamp='start', equity=initial_balance, drawdown=0.0)]
        balance = initial_balance; peak = initial_balance
        for trade in trades:
            balance += trade.pnl_usd
            if balance > peak: peak = balance
            dd = (peak - balance) / peak * 100.0 if peak > 0 else 0.0
            curve.append(SharedEquityPoint(
                timestamp=str(getattr(trade, 'exit_time', '')),
                equity=round(balance, 2), drawdown=round(dd, 4),
                trade_id=getattr(trade, 'trade_id', None),
            ))
        return curve


@dataclass
class CandleData:
    timestamp: str
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0
    spread: float = 0.0


@dataclass
class BacktestTrade:
    trade_id:      str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol:        str   = 'XAUUSD'
    direction:     str   = 'BUY'
    entry_time:    str   = ''
    exit_time:     str   = ''
    entry_price:   float = 0.0
    exit_price:    float = 0.0
    stop_loss:     float = 0.0   # ✔ was stmp_loss (typo) in earlier commits
    take_profit:   float = 0.0
    lot_size:      float = 0.01
    pnl_pips:      float = 0.0
    pnl_usd:       float = 0.0
    slippage_pips: float = 0.0
    outcome:       str   = 'UNKNOWN'


@dataclass
class BacktestConfig:
    symbol:            str   = 'XAUUSD'
    timeframe:         str   = 'H1'
    initial_balance:   float = 10_000.0
    risk_per_trade:    float = 1.0
    max_spread_pips:   float = 3.0
    slippage_pips:     float = 0.5
    commission_usd:    float = 3.5
    min_rr_ratio:      float = 1.5
    max_trades_day:    int   = 5
    pip_value:         float = 10.0


@dataclass
class BacktestResult:
    config:             BacktestConfig
    symbol:             str
    timeframe:          str
    start_date:         str
    end_date:           str
    total_trades:       int   = 0
    winning_trades:     int   = 0
    losing_trades:      int   = 0
    breakeven_trades:   int   = 0
    win_rate:           float = 0.0
    profit_factor:      float = 0.0
    total_pnl_pips:     float = 0.0
    total_pnl_usd:      float = 0.0
    max_drawdown_pct:   float = 0.0
    max_drawdown_usd:   float = 0.0
    sharpe_ratio:       float = 0.0
    sortino_ratio:      float = 0.0
    calmar_ratio:       float = 0.0
    expectancy:         float = 0.0
    avg_win_usd:        float = 0.0
    avg_loss_usd:       float = 0.0
    avg_rr_achieved:    float = 0.0
    final_balance:      float = 0.0
    total_return_pct:   float = 0.0
    trades:             List[BacktestTrade]    = field(default_factory=list)
    equity_curve:       List[SharedEquityPoint] = field(default_factory=list)
    monthly_returns:    Dict[str, float]       = field(default_factory=dict)
    metadata:           Dict[str, Any]         = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol, 'timeframe': self.timeframe,
            'start_date': self.start_date, 'end_date': self.end_date,
            'total_trades': self.total_trades, 'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades, 'win_rate': round(self.win_rate, 2),
            'profit_factor': round(self.profit_factor, 4),
            'total_pnl_pips': round(self.total_pnl_pips, 2),
            'total_pnl_usd': round(self.total_pnl_usd, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 4),
            'max_drawdown_usd': round(self.max_drawdown_usd, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'sortino_ratio': round(self.sortino_ratio, 4),
            'calmar_ratio': round(self.calmar_ratio, 4),
            'expectancy': round(self.expectancy, 4),
            'avg_win_usd': round(self.avg_win_usd, 2),
            'avg_loss_usd': round(self.avg_loss_usd, 2),
            'final_balance': round(self.final_balance, 2),
            'total_return_pct': round(self.total_return_pct, 4),
            'monthly_returns': self.monthly_returns,
            'equity_curve': [{'t': p.timestamp, 'eq': p.equity, 'dd': p.drawdown}
                             for p in self.equity_curve],
        }


class BacktestEngine:
    def __init__(self, config=None):
        self._config = config or BacktestConfig()

    def run(self, candles, signal_fn, config=None):
        cfg = config or self._config
        trades = []; balance = cfg.initial_balance; history = []
        for i, candle in enumerate(candles):
            try:
                # Phase-6 lookahead bias fix:
                # Pass history BEFORE appending current candle.
                # signal_fn only sees closed candles, not the candle being processed.
                past = history[-50:] if history else []
                sig = signal_fn(candle, past)
            except Exception:
                sig = None
            if sig and self._is_valid_signal(sig, cfg):
                trade = self._simulate_trade(sig, candle, candles[i:], cfg, balance)
                if trade:
                    trades.append(trade)
                    balance += trade.pnl_usd
            history.append(candle)  # append AFTER signal generation
        return self._build_result(trades, cfg, candles)

    @staticmethod
    def _is_valid_signal(sig, cfg):
        required = {'direction', 'entry_price', 'stop_loss', 'take_profit'}
        if not required.issubset(sig.keys()): return False
        ep = float(sig.get('entry_price', 0))
        sl = float(sig.get('stop_loss', 0))
        tp = float(sig.get('take_profit', 0))
        direction = str(sig.get('direction', '')).upper()
        if ep <= 0 or sl <= 0 or tp <= 0: return False
        if direction not in ('BUY', 'SELL'): return False
        risk, reward = (ep - sl, tp - ep) if direction == 'BUY' else (sl - ep, ep - tp)
        if risk <= 0 or reward <= 0: return False
        if reward / risk < cfg.min_rr_ratio: return False
        return True

    @staticmethod
    def _simulate_trade(sig, entry_candle, future_candles, cfg, balance):
        direction = str(sig['direction']).upper()
        ep = float(sig['entry_price']); sl = float(sig['stop_loss']); tp = float(sig['take_profit'])
        slip = cfg.slippage_pips * 0.1
        ep_actual = ep + slip if direction == 'BUY' else ep - slip
        risk_usd  = balance * (cfg.risk_per_trade / 100.0)
        risk_pips = abs(ep_actual - sl) * 10.0
        if risk_pips <= 0: return None
        lot = max(0.01, min(round(risk_usd / (risk_pips * cfg.pip_value), 2), 10.0))
        exit_price = ep_actual; outcome = 'UNKNOWN'; exit_time = entry_candle.timestamp
        for future in future_candles[1:]:
            if direction == 'BUY':
                if future.low <= sl:
                    exit_price, outcome, exit_time = sl, 'LOSS', future.timestamp; break
                if future.high >= tp:
                    exit_price, outcome, exit_time = tp, 'WIN', future.timestamp; break
            else:
                if future.high >= sl:
                    exit_price, outcome, exit_time = sl, 'LOSS', future.timestamp; break
                if future.low <= tp:
                    exit_price, outcome, exit_time = tp, 'WIN', future.timestamp; break
        else:
            last = future_candles[-1] if future_candles else entry_candle
            exit_price = last.close; outcome = 'BE'; exit_time = last.timestamp
        pnl_pts  = (exit_price - ep_actual) if direction == 'BUY' else (ep_actual - exit_price)
        pnl_pips = pnl_pts * 10.0
        pnl_usd  = pnl_pips * cfg.pip_value * lot - cfg.commission_usd * lot
        return BacktestTrade(
            symbol=cfg.symbol, direction=direction,
            entry_time=entry_candle.timestamp, exit_time=exit_time,
            entry_price=round(ep_actual, 5), exit_price=round(exit_price, 5),
            stop_loss=sl, take_profit=tp, lot_size=lot,
            pnl_pips=round(pnl_pips, 2), pnl_usd=round(pnl_usd, 2),
            slippage_pips=round(cfg.slippage_pips, 2), outcome=outcome,
        )

    def _build_result(self, trades, cfg, candles):
        start_date = candles[0].timestamp  if candles else ''
        end_date   = candles[-1].timestamp if candles else ''
        result = BacktestResult(config=cfg, symbol=cfg.symbol, timeframe=cfg.timeframe,
                                start_date=start_date, end_date=end_date)
        if not trades:
            result.final_balance = cfg.initial_balance
            return result
        wins      = [t for t in trades if t.outcome == 'WIN']
        losses    = [t for t in trades if t.outcome == 'LOSS']
        breakeven = [t for t in trades if t.outcome == 'BE']
        result.total_trades    = len(trades); result.winning_trades = len(wins)
        result.losing_trades   = len(losses); result.breakeven_trades = len(breakeven)
        result.total_pnl_pips  = sum(t.pnl_pips for t in trades)
        result.total_pnl_usd   = sum(t.pnl_usd  for t in trades)
        result.final_balance   = cfg.initial_balance + result.total_pnl_usd
        result.total_return_pct = (result.final_balance - cfg.initial_balance) / cfg.initial_balance * 100.0
        result.avg_win_usd  = (sum(t.pnl_usd for t in wins)   / len(wins))   if wins   else 0.0
        result.avg_loss_usd = (sum(t.pnl_usd for t in losses) / len(losses)) if losses else 0.0
        # ─── use SharedBacktestMetrics for ALL calculations (D3 fix) ───
        result.win_rate       = SharedBacktestMetrics.win_rate(len(wins), len(trades))
        gross_profit = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
        gross_loss   = sum(t.pnl_usd for t in trades if t.pnl_usd < 0)
        result.profit_factor  = SharedBacktestMetrics.profit_factor(gross_profit, gross_loss)
        result.expectancy     = SharedBacktestMetrics.expectancy(result.win_rate, result.avg_win_usd, result.avg_loss_usd)
        result.equity_curve   = SharedBacktestMetrics.build_equity_curve(trades, cfg.initial_balance)
        equity_values         = [p.equity for p in result.equity_curve]
        dd_pct, dd_usd        = SharedBacktestMetrics.max_drawdown(equity_values)
        result.max_drawdown_pct = dd_pct; result.max_drawdown_usd = dd_usd
        trade_returns         = [t.pnl_usd / cfg.initial_balance for t in trades]
        result.sharpe_ratio   = SharedBacktestMetrics.sharpe_ratio(trade_returns)
        result.sortino_ratio  = SharedBacktestMetrics.sortino_ratio(trade_returns)
        result.calmar_ratio   = SharedBacktestMetrics.calmar_ratio(trade_returns)
        result.monthly_returns = self._monthly_returns(trades)
        rr_list = []
        for t in trades:
            risk   = abs(t.entry_price - t.stop_loss)
            reward = abs(t.take_profit  - t.entry_price)
            if risk > 0: rr_list.append(reward / risk)
        result.avg_rr_achieved = round(sum(rr_list) / len(rr_list), 3) if rr_list else 0.0
        result.trades = trades
        return result

    @staticmethod
    def _monthly_returns(trades):
        monthly: Dict[str, float] = {}
        for t in trades:
            try:
                key = str(t.exit_time)[:7]
                monthly[key] = monthly.get(key, 0.0) + t.pnl_usd
            except Exception:
                pass
        return {k: round(v, 2) for k, v in sorted(monthly.items())}


def compute_sharpe_unified(returns, risk_free=0.0, periods=252):
    return SharedBacktestMetrics.sharpe_ratio(returns, risk_free, periods)


def compute_sortino_unified(returns, risk_free=0.0, periods=252):
    return SharedBacktestMetrics.sortino_ratio(returns, risk_free, periods)


def apply_slippage(price: float, direction: str, slippage_pips: float, symbol: str = 'XAUUSD') -> float:
    pip = 0.1 if 'JPY' in symbol else 0.0001 if symbol not in ('XAUUSD', 'XAGUSD') else 0.1
    slip_price = slippage_pips * pip
    return price + slip_price if direction.upper() == 'BUY' else price - slip_price
