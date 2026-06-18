"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: BacktestEngine — موتور بک‌تست حرفه‌ای
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قابلیت‌ها:
  • بک‌تست تک‌نماد با داده واقعی MT5
  • سه سطح TP با بستن جزئی
  • مدیریت ریسک دینامیک
  • فیلترهای سشن و نیوز
  • متریک‌های جامع عملکرد
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import get_logger

logger = get_logger("research.backtest.engine")


class TradeDirection(Enum):
    BUY  = "BUY"
    SELL = "SELL"


class TradeStatus(Enum):
    OPEN      = "OPEN"
    WIN       = "WIN"
    LOSS      = "LOSS"
    BE        = "BE"
    PARTIAL   = "PARTIAL"
    TIMEOUT   = "TIMEOUT"


@dataclass
class CandleData:
    """اطلاعات یک کندل."""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "spread": self.spread,
        }


@dataclass
class BacktestTrade:
    """
    یک معامله در بک‌تست
    """
    trade_id: str
    symbol: str
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    lot_size: float
    entry_time: datetime
    signal_score: float
    signal_context: Dict[str, Any] = field(default_factory=dict)

    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl_pips: float = 0.0
    pnl_money: float = 0.0
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    duration_minutes: int = 0
    risk_reward_actual: float = 0.0

    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    def calculate_pnl(self, current_price: float, pip_value: float) -> float:
        if self.direction == TradeDirection.BUY:
            pips = (current_price - self.entry_price) / 0.0001
        else:
            pips = (self.entry_price - current_price) / 0.0001
        return pips * pip_value * self.lot_size


@dataclass
class BacktestConfig:
    """تنظیمات بک‌تست"""
    start_date: datetime
    end_date: datetime
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    initial_balance: float = 10000.0
    currency: str = "USD"
    risk_per_trade_percent: float = 1.0
    max_drawdown_percent: float = 20.0
    max_daily_trades: int = 5
    max_daily_loss_percent: float = 3.0
    min_confidence_score: float = 70.0
    commission_per_lot: float = 7.0
    spread_points: float = 20.0
    slippage_points: float = 3.0
    risk_reward_ratio: float = 2.0
    use_partial_close: bool = True
    partial_close_percent: float = 50.0
    trade_sessions_only: bool = True
    avoid_high_impact_news: bool = False
    max_spread_points: float = 50.0
    pip_value_per_lot: float = 10.0


@dataclass
class BacktestMetrics:
    """متریک‌های کامل بک‌تست"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    partial_close_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    max_drawdown_duration_days: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    annualized_return: float = 0.0
    total_commission: float = 0.0
    total_days: int = 0
    trades_per_day: float = 0.0
    avg_duration_minutes: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 2),
            "net_profit": round(self.net_profit, 2),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_percent": round(self.max_drawdown_percent, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "recovery_factor": round(self.recovery_factor, 3),
            "expectancy": round(self.expectancy, 2),
            "annualized_return": round(self.annualized_return, 2),
            "total_commission": round(self.total_commission, 2),
            "avg_duration_minutes": round(self.avg_duration_minutes, 1),
        }


@dataclass
class BacktestResult:
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[BacktestTrade]
    equity_curve: List[float]
    timestamps: List[datetime]
    error: Optional[str] = None

    def to_summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe,
            "period": f"{self.config.start_date.date()} to {self.config.end_date.date()}",
            "metrics": self.metrics.to_dict(),
            "total_trades": len(self.trades),
        }


class BacktestEngine:
    """
    موتور بک‌تست حرفه‌ای Galaxy Vast.
    شبیه‌سازی واقعی‌سازی‌شده با سه سطح TP و بستن جزئی.
    """

    def __init__(self) -> None:
        self._running = False
        self._progress = 0.0
        self._current_symbol = ""
        self._trades: List[BacktestTrade] = []
        self._equity_curve: List[float] = []
        self._timestamps: List[datetime] = []
        self._daily_trades: Dict[str, int] = {}
        self._daily_loss: Dict[str, float] = {}

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._running

    async def run(self, config: BacktestConfig, signals: List[Dict[str, Any]], candles: List[CandleData]) -> BacktestResult:
        """اجرای بک‌تست."""
        self._running = True
        self._progress = 0.0
        self._trades = []
        self._equity_curve = [config.initial_balance]
        self._timestamps = []
        self._daily_trades = {}
        self._daily_loss = {}

        balance = config.initial_balance
        open_trades: List[BacktestTrade] = []

        try:
            total_candles = len(candles)
            for i, candle in enumerate(candles):
                self._progress = (i / total_candles) * 100

                # بررسی خروج معاملات باز
                for trade in list(open_trades):
                    exit_result = self._check_trade_exit(trade, candle, config)
                    if exit_result:
                        trade.exit_price = exit_result["exit_price"]
                        trade.exit_time = candle.time
                        trade.status = exit_result["status"]
                        trade.pnl_money = exit_result["pnl"]
                        trade.duration_minutes = int((candle.time - trade.entry_time).total_seconds() / 60)
                        balance += trade.pnl_money
                        open_trades.remove(trade)

                # بررسی سیگنال‌های جدید
                day_key = candle.time.strftime("%Y-%m-%d")
                daily_count = self._daily_trades.get(day_key, 0)
                daily_loss = self._daily_loss.get(day_key, 0.0)

                if daily_count >= config.max_daily_trades:
                    continue
                if daily_loss <= -(config.initial_balance * config.max_daily_loss_percent / 100):
                    continue

                matching_signals = [
                    s for s in signals
                    if abs((datetime.fromisoformat(s["time"]) - candle.time).total_seconds()) < 3600
                    and s.get("confidence", 0) >= config.min_confidence_score
                    and s.get("symbol", config.symbol) == config.symbol
                ]

                for signal in matching_signals:
                    if len(open_trades) >= 3:
                        break
                    if candle.spread > config.max_spread_points:
                        continue

                    direction = TradeDirection(signal.get("direction", "BUY"))
                    entry = candle.close + (config.slippage_points * 0.0001 if direction == TradeDirection.BUY else -config.slippage_points * 0.0001)
                    lot = self._calculate_lot_size(balance, config, entry, signal.get("stop_loss", entry - 0.01))

                    if lot <= 0:
                        continue

                    sl = signal.get("stop_loss", entry - 0.01 if direction == TradeDirection.BUY else entry + 0.01)
                    risk_pips = abs(entry - sl) / 0.0001
                    tp1 = entry + (risk_pips * config.risk_reward_ratio * 0.0001) if direction == TradeDirection.BUY else entry - (risk_pips * config.risk_reward_ratio * 0.0001)
                    tp2 = entry + (risk_pips * config.risk_reward_ratio * 1.5 * 0.0001) if direction == TradeDirection.BUY else entry - (risk_pips * config.risk_reward_ratio * 1.5 * 0.0001)
                    tp3 = entry + (risk_pips * config.risk_reward_ratio * 2.0 * 0.0001) if direction == TradeDirection.BUY else entry - (risk_pips * config.risk_reward_ratio * 2.0 * 0.0001)

                    import uuid as _uuid
                    trade = BacktestTrade(
                        trade_id=str(_uuid.uuid4())[:8],
                        symbol=config.symbol,
                        direction=direction,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        take_profit_3=tp3,
                        lot_size=lot,
                        entry_time=candle.time,
                        signal_score=signal.get("confidence", 70.0),
                        signal_context=signal,
                    )
                    open_trades.append(trade)
                    self._trades.append(trade)
                    self._daily_trades[day_key] = daily_count + 1
                    commission = config.commission_per_lot * lot
                    balance -= commission

                self._equity_curve.append(balance)
                self._timestamps.append(candle.time)
                await asyncio.sleep(0)

            # بستن معاملات باز مانده
            if candles:
                last_candle = candles[-1]
                for trade in open_trades:
                    pnl = trade.calculate_pnl(last_candle.close, config.pip_value_per_lot)
                    trade.exit_price = last_candle.close
                    trade.exit_time = last_candle.time
                    trade.status = TradeStatus.WIN if pnl > 0 else TradeStatus.LOSS
                    trade.pnl_money = pnl
                    balance += pnl

            metrics = self._calculate_metrics(self._trades, config, balance)
            return BacktestResult(
                config=config,
                metrics=metrics,
                trades=self._trades,
                equity_curve=self._equity_curve,
                timestamps=self._timestamps,
            )

        except Exception as e:
            logger.error(f"خطا در بک‌تست: {e}")
            return BacktestResult(
                config=config,
                metrics=BacktestMetrics(),
                trades=self._trades,
                equity_curve=self._equity_curve,
                timestamps=self._timestamps,
                error=str(e),
            )
        finally:
            self._running = False
            self._progress = 100.0

    def _check_trade_exit(
        self,
        trade: BacktestTrade,
        candle: CandleData,
        config: BacktestConfig,
    ) -> Optional[Dict[str, Any]]:
        """بررسی شرایط خروج معامله."""
        if trade.direction == TradeDirection.BUY:
            if candle.low <= trade.stop_loss:
                pnl = trade.calculate_pnl(trade.stop_loss, config.pip_value_per_lot)
                return {"exit_price": trade.stop_loss, "status": TradeStatus.LOSS, "pnl": pnl}
            if candle.high >= trade.take_profit_1:
                if config.use_partial_close:
                    partial_lot = trade.lot_size * (config.partial_close_percent / 100)
                    pnl = ((trade.take_profit_1 - trade.entry_price) / 0.0001) * config.pip_value_per_lot * partial_lot
                    return {"exit_price": trade.take_profit_1, "status": TradeStatus.PARTIAL, "pnl": pnl}
                pnl = trade.calculate_pnl(trade.take_profit_1, config.pip_value_per_lot)
                return {"exit_price": trade.take_profit_1, "status": TradeStatus.WIN, "pnl": pnl}
        else:
            if candle.high >= trade.stop_loss:
                pnl = trade.calculate_pnl(trade.stop_loss, config.pip_value_per_lot)
                return {"exit_price": trade.stop_loss, "status": TradeStatus.LOSS, "pnl": pnl}
            if candle.low <= trade.take_profit_1:
                if config.use_partial_close:
                    partial_lot = trade.lot_size * (config.partial_close_percent / 100)
                    pnl = ((trade.entry_price - trade.take_profit_1) / 0.0001) * config.pip_value_per_lot * partial_lot
                    return {"exit_price": trade.take_profit_1, "status": TradeStatus.PARTIAL, "pnl": pnl}
                pnl = trade.calculate_pnl(trade.take_profit_1, config.pip_value_per_lot)
                return {"exit_price": trade.take_profit_1, "status": TradeStatus.WIN, "pnl": pnl}
        return None

    def _calculate_atr(self, candles: List[CandleData]) -> float:
        if len(candles) < 2:
            return 0.001
        trs = []
        for i in range(1, len(candles)):
            c = candles[i]
            p = candles[i - 1]
            tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            trs.append(tr)
        return sum(trs[-14:]) / min(len(trs), 14)

    def _calculate_lot_size(
        self,
        balance: float,
        config: BacktestConfig,
        entry: float,
        stop_loss: float,
    ) -> float:
        risk_amount = balance * (config.risk_per_trade_percent / 100)
        sl_pips = abs(entry - stop_loss) / 0.0001
        if sl_pips <= 0:
            return 0.01
        lot = risk_amount / (sl_pips * config.pip_value_per_lot)
        return round(max(0.01, min(lot, 10.0)), 2)

    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        config: BacktestConfig,
        final_balance: float,
    ) -> BacktestMetrics:
        m = BacktestMetrics()
        m.total_trades = len(trades)
        if not trades:
            return m

        closed = [t for t in trades if t.status != TradeStatus.OPEN]
        m.winning_trades = sum(1 for t in closed if t.pnl_money > 0)
        m.losing_trades  = sum(1 for t in closed if t.pnl_money < 0)
        m.breakeven_trades = sum(1 for t in closed if t.pnl_money == 0)
        m.partial_close_trades = sum(1 for t in closed if t.status == TradeStatus.PARTIAL)

        if m.total_trades > 0:
            m.win_rate = (m.winning_trades / m.total_trades) * 100

        m.gross_profit = sum(t.pnl_money for t in closed if t.pnl_money > 0)
        m.gross_loss   = abs(sum(t.pnl_money for t in closed if t.pnl_money < 0))
        m.net_profit   = final_balance - config.initial_balance

        m.profit_factor = (m.gross_profit / m.gross_loss) if m.gross_loss > 0 else (m.gross_profit if m.gross_profit > 0 else 0.0)

        wins  = [t.pnl_money for t in closed if t.pnl_money > 0]
        losses = [abs(t.pnl_money) for t in closed if t.pnl_money < 0]
        m.avg_win  = sum(wins) / len(wins) if wins else 0.0
        m.avg_loss = sum(losses) / len(losses) if losses else 0.0
        m.expectancy = (m.win_rate / 100 * m.avg_win) - ((1 - m.win_rate / 100) * m.avg_loss)

        # drawdown
        if self._equity_curve:
            peak = self._equity_curve[0]
            max_dd = max_dd_pct = 0.0
            for val in self._equity_curve:
                if val > peak:
                    peak = val
                dd = peak - val
                dd_pct = (dd / peak * 100) if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = dd_pct
            m.max_drawdown = max_dd
            m.max_drawdown_percent = max_dd_pct

        # Sharpe
        pnl_list = [t.pnl_money for t in closed]
        if len(pnl_list) > 1:
            import statistics as _s
            mean_pnl = _s.mean(pnl_list)
            std_pnl  = _s.stdev(pnl_list)
            if std_pnl > 0:
                m.sharpe_ratio = (mean_pnl / std_pnl) * math.sqrt(252)
            downside = [p for p in pnl_list if p < 0]
            if downside:
                ds = _s.stdev(downside) if len(downside) > 1 else abs(downside[0])
                if ds > 0:
                    m.sortino_ratio = (mean_pnl / ds) * math.sqrt(252)

        days = (config.end_date - config.start_date).days or 1
        m.total_days = days
        m.trades_per_day = m.total_trades / days
        if config.initial_balance > 0:
            m.annualized_return = (m.net_profit / config.initial_balance) * (365 / days) * 100
        if m.max_drawdown_percent > 0:
            m.calmar_ratio = m.annualized_return / m.max_drawdown_percent
        if m.max_drawdown > 0:
            m.recovery_factor = m.net_profit / m.max_drawdown
        if closed:
            m.avg_duration_minutes = sum(t.duration_minutes for t in closed) / len(closed)

        return m


# ════════════════════════════════════════════════════════════════════════════════
# Phase D — Unified Backtest Bridge
# ════════════════════════════════════════════════════════════════════════════════
import statistics as _statistics
import math as _math
from dataclasses import dataclass as _bdc
from datetime import datetime as _bdt


@_bdc
class SharedEquityPoint:
    """نقطه equity مشترک بین هر دو engine."""
    time: datetime
    equity: float
    drawdown: float
    drawdown_pct: float
    peak: float
    symbol: str = "PORTFOLIO"


def apply_slippage(
    price: float,
    direction: str,
    slippage_pips: float,
    symbol: str = "XAUUSD",
) -> float:
    """مدل لغزش قیمت — XAUUSD-aware."""
    pip_size = 0.01 if "XAU" in symbol or "GOLD" in symbol.upper() else 0.0001
    slip = slippage_pips * pip_size
    return price + slip if direction.upper() == "BUY" else price - slip


class SharedBacktestMetrics:
    """محاسبات متریک مشترک — هر دو engine استفاده می‌کنند."""

    @staticmethod
    def sharpe_ratio(returns: list, risk_free_rate: float = 0.0, annualization: float = 252.0) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean_r = _statistics.mean(returns) - risk_free_rate / annualization
            std_r = _statistics.stdev(returns)
            return (mean_r / std_r) * _math.sqrt(annualization) if std_r > 1e-10 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def sortino_ratio(returns: list, risk_free_rate: float = 0.0, annualization: float = 252.0) -> float:
        if len(returns) < 2:
            return 0.0
        try:
            mean_r = _statistics.mean(returns) - risk_free_rate / annualization
            downside = [r for r in returns if r < 0]
            if not downside:
                return float('inf') if mean_r > 0 else 0.0
            ds = _statistics.stdev(downside) if len(downside) > 1 else abs(downside[0])
            return (mean_r / ds) * _math.sqrt(annualization) if ds > 1e-10 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def calmar_ratio(annualized_return: float, max_drawdown_pct: float) -> float:
        return annualized_return / max_drawdown_pct if max_drawdown_pct > 0 else 0.0

    @staticmethod
    def max_drawdown(equity_curve: list) -> tuple:
        if not equity_curve:
            return 0.0, 0.0
        peak = equity_curve[0]
        max_dd = max_dd_pct = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = peak - val
            dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
        return max_dd, max_dd_pct

    @staticmethod
    def profit_factor(pnl_list: list) -> float:
        gp = sum(p for p in pnl_list if p > 0)
        gl = abs(sum(p for p in pnl_list if p < 0))
        return gp / gl if gl > 1e-10 else (gp if gp > 0 else 0.0)

    @staticmethod
    def win_rate(pnl_list: list) -> float:
        return sum(1 for p in pnl_list if p > 0) / len(pnl_list) if pnl_list else 0.0

    @staticmethod
    def expectancy(pnl_list: list) -> float:
        if not pnl_list:
            return 0.0
        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]
        wr = len(wins) / len(pnl_list)
        avg_win = _statistics.mean(wins) if wins else 0.0
        avg_loss = abs(_statistics.mean(losses)) if losses else 0.0
        return wr * avg_win - (1 - wr) * avg_loss

    @staticmethod
    def build_equity_curve(trades_pnl: list, initial_balance: float, timestamps: list = None) -> list:
        from datetime import datetime as _dt
        equity = initial_balance
        peak = initial_balance
        curve = []
        for i, pnl in enumerate(trades_pnl):
            equity += pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
            ts = timestamps[i] if timestamps and i < len(timestamps) else _dt.utcnow()
            curve.append(SharedEquityPoint(
                time=ts, equity=equity, drawdown=dd, drawdown_pct=dd_pct, peak=peak
            ))
        return curve
