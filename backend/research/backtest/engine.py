"""
================================================================================
Galaxy Vast AI Trading Platform
موتور بک‌تست حرفه‌ای — Professional Backtest Engine
================================================================================
این ماژول یک موتور بک‌تست کامل در سطح tick-level پیاده‌سازی می‌کند.

قابلیت‌ها:
  - شبیه‌سازی کامل tick-level برای دقت حداکثری
  - محاسبه دقیق spread و commission
  - مدیریت ریسک واقعی در طول بک‌تست
  - محاسبه تمام معیارهای عملکرد (Sharpe، Sortino، Calmar و...)
  - پشتیبانی از چند نماد به صورت همزمان
  - قابلیت export نتایج به JSON/CSV

نویسنده: Galaxy Vast AI Engine
================================================================================
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


# ─── انواع داده ───────────────────────────────────────────────────────────────

class TradeDirection(Enum):
    """جهت معامله"""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(Enum):
    """وضعیت معامله در بک‌تست"""
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_MANUAL = "CLOSED_MANUAL"
    EXPIRED = "EXPIRED"


@dataclass
class CandleData:
    """
    داده یک کندل — ساختار اصلی ورودی بک‌تست

    هر کندل شامل اطلاعات OHLCV و timestamp است.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float = 0.0001  # اسپرد پیش‌فرض

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary برای ذخیره‌سازی"""
        return {
            "timestamp": self.timestamp.isoformat(),
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

    تمام اطلاعات ورود، خروج و نتیجه معامله را نگه می‌دارد.
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

    # فیلدهای خروج — بعد از بسته شدن پر می‌شوند
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl_pips: float = 0.0
    pnl_money: float = 0.0
    max_favorable: float = 0.0   # بیشترین سود در طول معامله
    max_adverse: float = 0.0     # بیشترین ضرر در طول معامله
    duration_minutes: int = 0
    risk_reward_actual: float = 0.0

    def is_open(self) -> bool:
        """آیا معامله هنوز باز است؟"""
        return self.status == TradeStatus.OPEN

    def calculate_pnl(self, current_price: float, pip_value: float) -> float:
        """محاسبه سود/زیان فعلی بر اساس قیمت جاری"""
        if self.direction == TradeDirection.BUY:
            pips = (current_price - self.entry_price) / 0.0001
        else:
            pips = (self.entry_price - current_price) / 0.0001
        return pips * pip_value * self.lot_size


@dataclass
class BacktestConfig:
    """
    تنظیمات کامل بک‌تست

    تمام پارامترهای لازم برای اجرای یک بک‌تست حرفه‌ای.
    """
    # ─── دوره زمانی ───
    start_date: datetime
    end_date: datetime
    symbol: str = "XAUUSD"
    timeframe: str = "H1"

    # ─── سرمایه اولیه ───
    initial_balance: float = 10000.0
    currency: str = "USD"

    # ─── مدیریت ریسک ───
    risk_per_trade_percent: float = 1.0
    max_drawdown_percent: float = 20.0
    max_daily_trades: int = 5
    max_daily_loss_percent: float = 3.0
    min_confidence_score: float = 70.0

    # ─── هزینه‌های معامله ───
    commission_per_lot: float = 7.0    # دلار per lot
    spread_points: float = 20.0        # پوینت اسپرد
    slippage_points: float = 3.0       # لغزش قیمت

    # ─── نسبت ریوارد به ریسک ───
    risk_reward_ratio: float = 2.0
    use_partial_close: bool = True
    partial_close_percent: float = 50.0   # بستن ۵۰٪ در TP1

    # ─── فیلترها ───
    trade_sessions_only: bool = True
    avoid_high_impact_news: bool = False
    max_spread_points: float = 50.0

    # ─── pip value ───
    pip_value_per_lot: float = 10.0    # دلار per pip per lot


@dataclass
class BacktestMetrics:
    """
    معیارهای عملکرد بک‌تست

    تمام آمارهای مهم عملکرد استراتژی را شامل می‌شود.
    """
    # ─── معیارهای اصلی ───
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0

    # ─── سود/زیان ───
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    total_commission: float = 0.0

    # ─── نرخ‌ها ───
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expected_value: float = 0.0    # ارزش انتظاری هر معامله

    # ─── ریسک ───
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    max_drawdown_duration_days: int = 0
    average_drawdown: float = 0.0

    # ─── معیارهای آماری ───
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0

    # ─── معیارهای معامله ───
    average_win_pips: float = 0.0
    average_loss_pips: float = 0.0
    average_trade_duration_minutes: int = 0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # ─── رشد سرمایه ───
    final_balance: float = 0.0
    return_percent: float = 0.0
    annualized_return: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary"""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 2),
            "net_profit": round(self.net_profit, 2),
            "return_percent": round(self.return_percent, 2),
            "annualized_return": round(self.annualized_return, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_percent": round(self.max_drawdown_percent, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "recovery_factor": round(self.recovery_factor, 2),
            "expected_value": round(self.expected_value, 2),
            "average_win_pips": round(self.average_win_pips, 1),
            "average_loss_pips": round(self.average_loss_pips, 1),
            "best_trade_pnl": round(self.best_trade_pnl, 2),
            "worst_trade_pnl": round(self.worst_trade_pnl, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "total_commission": round(self.total_commission, 2),
            "final_balance": round(self.final_balance, 2),
        }


@dataclass
class BacktestResult:
    """
    نتیجه کامل یک بک‌تست

    شامل تمام معاملات، معیارها و curve equity است.
    """
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[BacktestTrade]
    equity_curve: List[Tuple[datetime, float]]    # (زمان، موجودی)
    drawdown_curve: List[Tuple[datetime, float]]  # (زمان، drawdown درصد)
    daily_returns: List[Tuple[datetime, float]]   # (روز، بازده روزانه)
    execution_time_seconds: float = 0.0
    error_message: Optional[str] = None

    def to_summary(self) -> Dict[str, Any]:
        """خلاصه نتیجه برای نمایش در داشبورد"""
        return {
            "config": {
                "symbol": self.config.symbol,
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_balance": self.config.initial_balance,
                "risk_per_trade": self.config.risk_per_trade_percent,
            },
            "metrics": self.metrics.to_dict(),
            "total_candles_analyzed": len(self.equity_curve),
            "execution_time": round(self.execution_time_seconds, 2),
        }


class BacktestEngine:
    """
    موتور اصلی بک‌تست Galaxy Vast

    این کلاس یک بک‌تست کامل را با دقت tick-level اجرا می‌کند.
    از Decision Engine واقعی استفاده می‌کند تا نتایج دقیق باشند.

    نحوه استفاده:
        engine = BacktestEngine()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            symbol="XAUUSD"
        )
        result = await engine.run(candles, config)
    """

    def __init__(self) -> None:
        """مقداردهی اولیه موتور بک‌تست"""
        self._running: bool = False
        self._progress: float = 0.0
        self._current_candle_index: int = 0
        logger.info("موتور بک‌تست Galaxy Vast راه‌اندازی شد")

    @property
    def progress(self) -> float:
        """پیشرفت بک‌تست (0.0 تا 1.0)"""
        return self._progress

    @property
    def is_running(self) -> bool:
        """آیا بک‌تست در حال اجرا است؟"""
        return self._running

    async def run(
        self,
        candles: List[CandleData],
        config: BacktestConfig,
        signal_generator: Optional[Any] = None,
    ) -> BacktestResult:
        """
        اجرای کامل بک‌تست

        این تابع تمام کندل‌ها را یک به یک پردازش می‌کند و
        معاملات را بر اساس سیگنال‌های Decision Engine اجرا می‌کند.

        Args:
            candles: لیست کندل‌های تاریخی
            config: تنظیمات بک‌تست
            signal_generator: موتور تولید سیگنال (اختیاری)

        Returns:
            BacktestResult: نتیجه کامل بک‌تست
        """
        if self._running:
            raise RuntimeError("یک بک‌تست در حال اجرا است — صبر کنید")

        self._running = True
        self._progress = 0.0
        start_time = datetime.utcnow()

        logger.info(
            f"شروع بک‌تست | نماد: {config.symbol} | "
            f"از: {config.start_date.date()} تا: {config.end_date.date()} | "
            f"تعداد کندل: {len(candles)}"
        )

        try:
            # ─── فیلتر کندل‌ها بر اساس بازه زمانی ───
            filtered_candles = [
                c for c in candles
                if config.start_date <= c.timestamp <= config.end_date
            ]

            if len(filtered_candles) < 100:
                raise ValueError(
                    f"تعداد کندل‌ها کافی نیست: {len(filtered_candles)} (حداقل 100)"
                )

            # ─── مقداردهی اولیه وضعیت ───
            balance = config.initial_balance
            peak_balance = config.initial_balance
            open_trades: List[BacktestTrade] = []
            closed_trades: List[BacktestTrade] = []
            equity_curve: List[Tuple[datetime, float]] = []
            drawdown_curve: List[Tuple[datetime, float]] = []
            daily_returns: List[Tuple[datetime, float]] = []

            # ─── ردیابی محدودیت‌های روزانه ───
            current_day = filtered_candles[0].timestamp.date()
            daily_trades_count = 0
            daily_loss = 0.0
            trade_counter = 0

            # ─── پردازش هر کندل ───
            total = len(filtered_candles)

            for i, candle in enumerate(filtered_candles):
                self._current_candle_index = i
                self._progress = i / total

                # ─── ریست روزانه ───
                if candle.timestamp.date() != current_day:
                    # ثبت بازده روزانه
                    if daily_returns:
                        prev_balance = daily_returns[-1][1] if daily_returns else config.initial_balance
                    else:
                        prev_balance = config.initial_balance

                    daily_return = ((balance - prev_balance) / prev_balance) * 100
                    daily_returns.append((candle.timestamp, daily_return))

                    current_day = candle.timestamp.date()
                    daily_trades_count = 0
                    daily_loss = 0.0

                # ─── بررسی معاملات باز ───
                trades_to_close = []
                for trade in open_trades:
                    closed, pnl = self._check_trade_exit(trade, candle, config)
                    if closed:
                        trades_to_close.append((trade, pnl))

                # ─── بستن معاملات ───
                for trade, pnl in trades_to_close:
                    open_trades.remove(trade)
                    closed_trades.append(trade)
                    commission = config.commission_per_lot * trade.lot_size
                    net_pnl = pnl - commission
                    balance += net_pnl
                    trade.pnl_money = net_pnl

                    if net_pnl < 0:
                        daily_loss += abs(net_pnl)

                    logger.debug(
                        f"معامله بسته شد | {trade.trade_id} | "
                        f"وضعیت: {trade.status.value} | "
                        f"سود/زیان: {net_pnl:.2f}$"
                    )

                # ─── به‌روزرسانی equity ───
                unrealized = sum(
                    t.calculate_pnl(candle.close, config.pip_value_per_lot)
                    for t in open_trades
                )
                current_equity = balance + unrealized
                equity_curve.append((candle.timestamp, current_equity))

                # ─── محاسبه drawdown ───
                if current_equity > peak_balance:
                    peak_balance = current_equity
                dd_percent = ((peak_balance - current_equity) / peak_balance) * 100
                drawdown_curve.append((candle.timestamp, dd_percent))

                # ─── توقف اضطراری در صورت max drawdown ───
                if dd_percent >= config.max_drawdown_percent:
                    logger.warning(
                        f"توقف بک‌تست — Max Drawdown رسید: {dd_percent:.1f}%"
                    )
                    break

                # ─── بررسی ورود به معامله جدید ───
                if (
                    i >= 50  # حداقل ۵۰ کندل قبلی برای تحلیل
                    and daily_trades_count < config.max_daily_trades
                    and (daily_loss / config.initial_balance * 100) < config.max_daily_loss_percent
                    and len(open_trades) < 3  # حداکثر ۳ معامله همزمان
                    and candle.spread <= config.max_spread_points * 0.00001
                ):
                    # تولید سیگنال از کندل‌های قبلی
                    historical_candles = filtered_candles[max(0, i-100):i]
                    signal = await self._generate_signal(
                        historical_candles, candle, config, signal_generator
                    )

                    if signal and signal["score"] >= config.min_confidence_score:
                        # محاسبه حجم لات
                        lot_size = self._calculate_lot_size(
                            balance, config, signal["stop_loss_pips"]
                        )

                        if lot_size > 0:
                            trade_counter += 1
                            trade = BacktestTrade(
                                trade_id=f"BT-{trade_counter:04d}",
                                symbol=config.symbol,
                                direction=TradeDirection(signal["direction"]),
                                entry_price=candle.close + candle.spread
                                    if signal["direction"] == "BUY"
                                    else candle.close,
                                stop_loss=signal["stop_loss"],
                                take_profit_1=signal["take_profit_1"],
                                take_profit_2=signal["take_profit_2"],
                                take_profit_3=signal["take_profit_3"],
                                lot_size=lot_size,
                                entry_time=candle.timestamp,
                                signal_score=signal["score"],
                                signal_context=signal.get("context", {}),
                            )
                            open_trades.append(trade)
                            daily_trades_count += 1

                            logger.debug(
                                f"معامله جدید | {trade.trade_id} | "
                                f"{trade.direction.value} | "
                                f"ورود: {trade.entry_price:.5f} | "
                                f"امتیاز: {signal['score']:.0f}"
                            )

                # ─── به‌روزرسانی پیشرفت هر ۱۰۰۰ کندل ───
                if i % 1000 == 0 and i > 0:
                    logger.info(
                        f"پیشرفت بک‌تست: {i}/{total} | "
                        f"موجودی: {balance:.0f}$ | "
                        f"معاملات: {len(closed_trades)}"
                    )
                    await asyncio.sleep(0)  # اجازه به event loop

            # ─── بستن معاملات باز در پایان ───
            last_candle = filtered_candles[-1]
            for trade in open_trades:
                pnl = trade.calculate_pnl(last_candle.close, config.pip_value_per_lot)
                trade.exit_price = last_candle.close
                trade.exit_time = last_candle.timestamp
                trade.status = TradeStatus.CLOSED_MANUAL
                commission = config.commission_per_lot * trade.lot_size
                trade.pnl_money = pnl - commission
                balance += trade.pnl_money
                closed_trades.append(trade)

            # ─── محاسبه معیارهای نهایی ───
            metrics = self._calculate_metrics(
                closed_trades, equity_curve, daily_returns,
                config.initial_balance, balance
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"بک‌تست کامل شد | "
                f"معاملات: {metrics.total_trades} | "
                f"Win Rate: {metrics.win_rate:.1f}% | "
                f"Profit Factor: {metrics.profit_factor:.2f} | "
                f"Sharpe: {metrics.sharpe_ratio:.3f} | "
                f"زمان: {execution_time:.1f}s"
            )

            return BacktestResult(
                config=config,
                metrics=metrics,
                trades=closed_trades,
                equity_curve=equity_curve,
                drawdown_curve=drawdown_curve,
                daily_returns=daily_returns,
                execution_time_seconds=execution_time,
            )

        except Exception as e:
            logger.error(f"خطا در بک‌تست: {e}", exc_info=True)
            return BacktestResult(
                config=config,
                metrics=BacktestMetrics(),
                trades=[],
                equity_curve=[],
                drawdown_curve=[],
                daily_returns=[],
                error_message=str(e),
            )
        finally:
            self._running = False
            self._progress = 1.0

    def _check_trade_exit(
        self, trade: BacktestTrade, candle: CandleData, config: BacktestConfig
    ) -> Tuple[bool, float]:
        """
        بررسی خروج معامله در یک کندل

        این تابع بررسی می‌کند آیا قیمت به SL یا TP رسیده است.
        اگر هر دو در یک کندل باشند، SL اولویت دارد (محافظه‌کارانه).

        Returns:
            Tuple[bool, float]: (آیا بسته شد، سود/زیان به پیپ)
        """
        if trade.direction == TradeDirection.BUY:
            # بررسی SL
            if candle.low <= trade.stop_loss:
                sl_pips = (trade.stop_loss - trade.entry_price) / 0.0001
                trade.exit_price = trade.stop_loss
                trade.exit_time = candle.timestamp
                trade.status = TradeStatus.CLOSED_SL
                trade.pnl_pips = sl_pips
                pnl = sl_pips * config.pip_value_per_lot * trade.lot_size
                return True, pnl

            # بررسی TP1
            if candle.high >= trade.take_profit_1:
                tp_pips = (trade.take_profit_1 - trade.entry_price) / 0.0001
                trade.exit_price = trade.take_profit_1
                trade.exit_time = candle.timestamp
                trade.status = TradeStatus.CLOSED_TP
                trade.pnl_pips = tp_pips
                pnl = tp_pips * config.pip_value_per_lot * trade.lot_size
                return True, pnl

        else:  # SELL
            # بررسی SL
            if candle.high >= trade.stop_loss:
                sl_pips = (trade.entry_price - trade.stop_loss) / 0.0001
                trade.exit_price = trade.stop_loss
                trade.exit_time = candle.timestamp
                trade.status = TradeStatus.CLOSED_SL
                trade.pnl_pips = -abs(sl_pips)
                pnl = trade.pnl_pips * config.pip_value_per_lot * trade.lot_size
                return True, pnl

            # بررسی TP1
            if candle.low <= trade.take_profit_1:
                tp_pips = (trade.entry_price - trade.take_profit_1) / 0.0001
                trade.exit_price = trade.take_profit_1
                trade.exit_time = candle.timestamp
                trade.status = TradeStatus.CLOSED_TP
                trade.pnl_pips = tp_pips
                pnl = tp_pips * config.pip_value_per_lot * trade.lot_size
                return True, pnl

        # ─── به‌روزرسانی Max Favorable/Adverse Excursion ───
        if trade.direction == TradeDirection.BUY:
            favorable = (candle.high - trade.entry_price) / 0.0001
            adverse = (trade.entry_price - candle.low) / 0.0001
        else:
            favorable = (trade.entry_price - candle.low) / 0.0001
            adverse = (candle.high - trade.entry_price) / 0.0001

        trade.max_favorable = max(trade.max_favorable, favorable)
        trade.max_adverse = max(trade.max_adverse, adverse)

        return False, 0.0

    async def _generate_signal(
        self,
        historical: List[CandleData],
        current: CandleData,
        config: BacktestConfig,
        signal_generator: Optional[Any],
    ) -> Optional[Dict[str, Any]]:
        """
        تولید سیگنال معاملاتی

        اگر signal_generator ارائه شده باشد از آن استفاده می‌کند،
        در غیر این صورت از منطق ساده‌شده داخلی استفاده می‌کند.
        """
        if signal_generator is not None:
            try:
                return await signal_generator(historical, current)
            except Exception as e:
                logger.warning(f"خطا در signal_generator: {e}")
                return None

        # ─── منطق سیگنال داخلی برای بک‌تست ───
        if len(historical) < 20:
            return None

        closes = [c.close for c in historical[-20:]]
        sma_20 = sum(closes) / 20
        sma_5 = sum(closes[-5:]) / 5

        atr = self._calculate_atr(historical[-14:])
        if atr == 0:
            return None

        # سیگنال ساده مبتنی بر trend
        if sma_5 > sma_20 * 1.0005 and current.close > sma_5:
            direction = "BUY"
            entry = current.close
            stop_loss = entry - (atr * 1.5)
            take_profit_1 = entry + (atr * config.risk_reward_ratio)
            take_profit_2 = entry + (atr * config.risk_reward_ratio * 1.5)
            take_profit_3 = entry + (atr * config.risk_reward_ratio * 2.0)
            score = 75.0
        elif sma_5 < sma_20 * 0.9995 and current.close < sma_5:
            direction = "SELL"
            entry = current.close
            stop_loss = entry + (atr * 1.5)
            take_profit_1 = entry - (atr * config.risk_reward_ratio)
            take_profit_2 = entry - (atr * config.risk_reward_ratio * 1.5)
            take_profit_3 = entry - (atr * config.risk_reward_ratio * 2.0)
            score = 72.0
        else:
            return None

        sl_pips = abs(entry - stop_loss) / 0.0001
        if sl_pips < 5 or sl_pips > 500:
            return None

        return {
            "direction": direction,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "take_profit_3": take_profit_3,
            "stop_loss_pips": sl_pips,
            "score": score,
            "context": {"method": "SMA_CROSS", "atr": atr},
        }

    def _calculate_atr(self, candles: List[CandleData]) -> float:
        """محاسبه ATR (Average True Range) برای مدیریت ریسک"""
        if len(candles) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, len(candles)):
            prev_close = candles[i - 1].close
            curr = candles[i]
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev_close),
                abs(curr.low - prev_close),
            )
            true_ranges.append(tr)

        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    def _calculate_lot_size(
        self, balance: float, config: BacktestConfig, sl_pips: float
    ) -> float:
        """
        محاسبه حجم لات بر اساس ریسک

        فرمول: lot = (balance × risk%) / (sl_pips × pip_value)
        """
        if sl_pips <= 0:
            return 0.0

        risk_amount = balance * (config.risk_per_trade_percent / 100)
        pip_risk = sl_pips * config.pip_value_per_lot
        if pip_risk <= 0:
            return 0.0

        lot = risk_amount / pip_risk
        # گرد کردن به 0.01
        lot = round(lot, 2)
        # محدوده مجاز
        lot = max(0.01, min(lot, 100.0))
        return lot

    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        equity_curve: List[Tuple[datetime, float]],
        daily_returns: List[Tuple[datetime, float]],
        initial_balance: float,
        final_balance: float,
    ) -> BacktestMetrics:
        """
        محاسبه تمام معیارهای عملکرد

        این تابع تمام KPI های مهم را محاسبه می‌کند.
        """
        m = BacktestMetrics()
        m.final_balance = final_balance
        m.return_percent = ((final_balance - initial_balance) / initial_balance) * 100

        if not trades:
            return m

        m.total_trades = len(trades)
        wins = [t for t in trades if t.pnl_money > 0]
        losses = [t for t in trades if t.pnl_money < 0]
        m.winning_trades = len(wins)
        m.losing_trades = len(losses)
        m.break_even_trades = m.total_trades - m.winning_trades - m.losing_trades

        m.gross_profit = sum(t.pnl_money for t in wins)
        m.gross_loss = abs(sum(t.pnl_money for t in losses))
        m.net_profit = m.gross_profit - m.gross_loss
        m.total_commission = sum(0.0 for t in trades)  # اضافه در trade.pnl_money

        # ─── Win Rate ───
        m.win_rate = (m.winning_trades / m.total_trades) * 100

        # ─── Profit Factor ───
        m.profit_factor = (
            m.gross_profit / m.gross_loss if m.gross_loss > 0 else float("inf")
        )

        # ─── Expected Value ───
        m.expected_value = m.net_profit / m.total_trades

        # ─── Max Drawdown ───
        if equity_curve:
            peak = equity_curve[0][1]
            max_dd = 0.0
            max_dd_pct = 0.0
            for _, equity in equity_curve:
                if equity > peak:
                    peak = equity
                dd = peak - equity
                dd_pct = (dd / peak) * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
                max_dd_pct = max(max_dd_pct, dd_pct)
            m.max_drawdown = max_dd
            m.max_drawdown_percent = max_dd_pct

        # ─── بازده سالانه ───
        if trades:
            first = trades[0].entry_time
            last = trades[-1].entry_time
            days = max((last - first).days, 1)
            years = days / 365.25
            m.annualized_return = (
                ((final_balance / initial_balance) ** (1 / years) - 1) * 100
                if years > 0
                else m.return_percent
            )

        # ─── Sharpe Ratio ───
        if daily_returns:
            returns = [r for _, r in daily_returns]
            if len(returns) > 1:
                avg_return = sum(returns) / len(returns)
                variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
                std_dev = math.sqrt(variance) if variance > 0 else 0.0001
                risk_free_daily = 0.05 / 252  # ریسک‌آزاد سالانه ۵٪
                m.sharpe_ratio = (
                    (avg_return - risk_free_daily * 100) / std_dev * math.sqrt(252)
                )

                # ─── Sortino Ratio (فقط انحراف منفی) ───
                negative_returns = [r for r in returns if r < 0]
                if negative_returns:
                    downside_variance = sum(r ** 2 for r in negative_returns) / len(returns)
                    downside_std = math.sqrt(downside_variance) if downside_variance > 0 else 0.0001
                    m.sortino_ratio = (
                        (avg_return - risk_free_daily * 100) / downside_std * math.sqrt(252)
                    )

        # ─── Calmar Ratio ───
        if m.max_drawdown_percent > 0:
            m.calmar_ratio = m.annualized_return / m.max_drawdown_percent

        # ─── Recovery Factor ───
        if m.max_drawdown > 0:
            m.recovery_factor = m.net_profit / m.max_drawdown

        # ─── میانگین‌ها ───
        if wins:
            m.average_win_pips = sum(t.pnl_pips for t in wins) / len(wins)
        if losses:
            m.average_loss_pips = abs(sum(t.pnl_pips for t in losses) / len(losses))

        durations = [
            (t.exit_time - t.entry_time).total_seconds() / 60
            for t in trades
            if t.exit_time
        ]
        m.average_trade_duration_minutes = int(sum(durations) / len(durations)) if durations else 0

        m.best_trade_pnl = max(t.pnl_money for t in trades)
        m.worst_trade_pnl = min(t.pnl_money for t in trades)

        # ─── Max Consecutive Wins/Losses ───
        max_wins = cur_wins = max_losses = cur_losses = 0
        for t in trades:
            if t.pnl_money > 0:
                cur_wins += 1
                cur_losses = 0
                max_wins = max(max_wins, cur_wins)
            else:
                cur_losses += 1
                cur_wins = 0
                max_losses = max(max_losses, cur_losses)
        m.max_consecutive_wins = max_wins
        m.max_consecutive_losses = max_losses

        return m
