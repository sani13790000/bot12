"""
================================================================================
Galaxy Vast AI Trading Platform
موتور بک‌تست حرفه‌ای — Professional Backtest Engine

این ماژول شبیه‌سازی کامل معاملات روی داده‌های تاریخی را انجام می‌دهد.
ویژگی‌ها:
- بک‌تست در سطح کندل با دقت بالا
- محاسبه تمام معیارهای عملکرد (Sharpe، Sortino، Calmar، ...)
- گزارش کامل با جزئیات هر معامله
- پشتیبانی از مدیریت ریسک واقعی (Portfolio Risk + Daily Limits)
- قابلیت اتصال به Decision Engine واقعی سیستم

نسخه: 3.0.0
برند: Galaxy Vast AI Trading Platform
================================================================================
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import get_logger

# ─── لاگر ماژول ───────────────────────────────────────────────────────────────
logger = get_logger("research.backtest.engine")


# ─── انواع داده ───────────────────────────────────────────────────────────────

class BacktestStatus(str, Enum):
    """وضعیت بک‌تست"""
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class TradeDirection(str, Enum):
    """جهت معامله"""
    BUY  = "BUY"
    SELL = "SELL"


@dataclass
class Candle:
    """
    یک کندل OHLCV — داده اصلی بک‌تست

    هر کندل شامل قیمت باز، بالا، پایین، بسته و حجم است.
    """
    timestamp : datetime
    open      : float
    high      : float
    low       : float
    close     : float
    volume    : float
    spread    : float = 0.0  # اسپرد در این لحظه (pips)


@dataclass
class BacktestTrade:
    """
    یک معامله در جریان بک‌تست

    شامل تمام اطلاعات ورود، خروج و نتیجه معامله است.
    """
    trade_id       : str
    direction      : TradeDirection
    entry_price    : float
    stop_loss      : float
    take_profit    : float
    lot_size       : float
    entry_time     : datetime
    entry_bar_idx  : int
    confidence     : float          # امتیاز سیگنال (۰-۱۰۰)
    risk_amount    : float          # مقدار ریسک به دلار

    # فیلدهای خروج — بعد از بسته شدن پر می‌شوند
    exit_price     : Optional[float]    = None
    exit_time      : Optional[datetime] = None
    exit_bar_idx   : Optional[int]      = None
    exit_reason    : Optional[str]      = None   # SL / TP / MANUAL / END
    pnl_dollar     : float              = 0.0
    pnl_pips       : float              = 0.0
    is_winner      : bool               = False
    max_favorable  : float              = 0.0    # بیشترین سود در طول معامله
    max_adverse    : float              = 0.0    # بیشترین ضرر در طول معامله


@dataclass
class BacktestConfig:
    """
    تنظیمات بک‌تست

    تمام پارامترهای بک‌تست از طریق این کلاس تعریف می‌شوند.
    """
    symbol              : str
    start_date          : datetime
    end_date            : datetime
    initial_balance     : float  = 10_000.0
    risk_per_trade_pct  : float  = 1.0        # درصد ریسک هر معامله
    max_portfolio_risk  : float  = 5.0        # حداکثر ریسک کل پرتفولیو
    max_daily_trades    : int    = 5          # حداکثر معامله در روز
    max_daily_loss_pct  : float  = 3.0        # حداکثر ضرر روزانه
    commission_per_lot  : float  = 7.0        # کمیسیون به دلار برای هر لات
    pip_value           : float  = 10.0       # ارزش هر پیپ برای ۱ لات استاندارد
    pip_size            : float  = 0.0001     # اندازه یک پیپ (۰.۰۰۰۱ برای EURUSD)
    min_confidence      : float  = 80.0       # حداقل امتیاز برای ورود
    timeframe_minutes   : int    = 60         # تایم‌فریم اصلی (دقیقه)
    use_spread_filter   : bool   = True       # فیلتر اسپرد
    max_spread_pips     : float  = 3.0        # حداکثر اسپرد مجاز
    use_session_filter  : bool   = True       # فیلتر سشن
    allowed_sessions    : List[str] = field(
        default_factory=lambda: ["london", "new_york"]
    )


@dataclass
class EquityCurvePoint:
    """یک نقطه روی منحنی equity"""
    timestamp  : datetime
    equity     : float
    balance    : float
    drawdown   : float
    trade_pnl  : float = 0.0


@dataclass
class BacktestResult:
    """
    نتیجه کامل بک‌تست

    شامل تمام معیارهای عملکرد و جزئیات معاملات است.
    """
    # اطلاعات کلی
    backtest_id        : str
    config             : BacktestConfig
    status             : BacktestStatus
    start_time         : datetime
    end_time           : Optional[datetime]
    duration_seconds   : float

    # معیارهای مالی
    initial_balance    : float
    final_balance      : float
    net_profit         : float
    net_profit_pct     : float
    gross_profit       : float
    gross_loss         : float

    # معیارهای معاملاتی
    total_trades       : int
    winning_trades     : int
    losing_trades      : int
    win_rate           : float          # ۰.۰ تا ۱.۰
    profit_factor      : float          # gross_profit / gross_loss
    avg_win            : float          # میانگین سود معاملات برنده
    avg_loss           : float          # میانگین ضرر معاملات بازنده
    avg_rr             : float          # میانگین نسبت ریسک به ریوارد
    largest_win        : float
    largest_loss       : float
    consecutive_wins   : int
    consecutive_losses : int

    # معیارهای ریسک
    max_drawdown       : float          # بیشترین افت از اوج (درصد)
    max_drawdown_dollar: float
    sharpe_ratio       : float          # نسبت شارپ (ریسک‌فری ۲٪)
    sortino_ratio      : float          # نسبت سورتینو
    calmar_ratio       : float          # CAGR / MaxDrawdown
    recovery_factor    : float          # net_profit / max_drawdown_dollar

    # داده‌های جزئیات
    trades             : List[BacktestTrade]
    equity_curve       : List[EquityCurvePoint]
    monthly_returns    : Dict[str, float]    # {"2024-01": 3.2, ...}

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای API"""
        return {
            "backtest_id"        : self.backtest_id,
            "status"             : self.status.value,
            "symbol"             : self.config.symbol,
            "start_date"         : self.config.start_date.isoformat(),
            "end_date"           : self.config.end_date.isoformat(),
            "duration_seconds"   : round(self.duration_seconds, 2),
            "initial_balance"    : self.initial_balance,
            "final_balance"      : round(self.final_balance, 2),
            "net_profit"         : round(self.net_profit, 2),
            "net_profit_pct"     : round(self.net_profit_pct, 2),
            "total_trades"       : self.total_trades,
            "winning_trades"     : self.winning_trades,
            "losing_trades"      : self.losing_trades,
            "win_rate"           : round(self.win_rate * 100, 2),
            "profit_factor"      : round(self.profit_factor, 2),
            "avg_win"            : round(self.avg_win, 2),
            "avg_loss"           : round(self.avg_loss, 2),
            "avg_rr"             : round(self.avg_rr, 2),
            "max_drawdown_pct"   : round(self.max_drawdown, 2),
            "sharpe_ratio"       : round(self.sharpe_ratio, 2),
            "sortino_ratio"      : round(self.sortino_ratio, 2),
            "calmar_ratio"       : round(self.calmar_ratio, 2),
            "recovery_factor"    : round(self.recovery_factor, 2),
            "monthly_returns"    : self.monthly_returns,
            "equity_curve"       : [
                {
                    "t"  : p.timestamp.isoformat(),
                    "eq" : round(p.equity, 2),
                    "bal": round(p.balance, 2),
                    "dd" : round(p.drawdown, 2),
                }
                for p in self.equity_curve
            ],
        }


class BacktestEngine:
    """
    موتور بک‌تست حرفه‌ای Galaxy Vast

    این کلاس شبیه‌سازی کامل معاملات روی داده‌های تاریخی را انجام می‌دهد.
    از تمام قوانین مدیریت ریسک سیستم پشتیبانی می‌کند.

    نحوه استفاده:
        engine = BacktestEngine()
        result = await engine.run(config, candles, signal_generator_fn)
    """

    def __init__(self) -> None:
        """مقداردهی اولیه موتور بک‌تست"""
        logger.info("🔬 Galaxy Vast Backtest Engine راه‌اندازی شد")

    async def run(
        self,
        config           : BacktestConfig,
        candles          : List[Candle],
        signal_generator : Any,   # تابع async که سیگنال تولید می‌کند
    ) -> BacktestResult:
        """
        اجرای کامل بک‌تست

        پارامترها:
            config: تنظیمات بک‌تست
            candles: لیست کندل‌های تاریخی (مرتب از قدیم به جدید)
            signal_generator: تابع async(candles_window) → Optional[dict signal]

        خروجی:
            BacktestResult — نتیجه کامل بک‌تست
        """
        backtest_id = str(uuid.uuid4())
        start_time  = datetime.now(timezone.utc)

        logger.info(
            f"🚀 شروع بک‌تست | ID: {backtest_id[:8]} | "
            f"نماد: {config.symbol} | "
            f"از {config.start_date.date()} تا {config.end_date.date()} | "
            f"کندل‌ها: {len(candles)}"
        )

        # ─── فیلتر کندل‌ها بر اساس بازه زمانی ───────────────────────────────
        candles = [
            c for c in candles
            if config.start_date <= c.timestamp <= config.end_date
        ]

        if len(candles) < 50:
            logger.warning("⚠️ تعداد کندل‌ها کافی نیست (حداقل ۵۰ کندل نیاز است)")
            return self._empty_result(backtest_id, config, start_time, BacktestStatus.FAILED)

        # ─── متغیرهای حالت ───────────────────────────────────────────────────
        balance          : float               = config.initial_balance
        equity           : float               = config.initial_balance
        peak_equity      : float               = config.initial_balance
        max_drawdown     : float               = 0.0
        max_drawdown_dollar: float             = 0.0
        open_trades      : List[BacktestTrade] = []
        closed_trades    : List[BacktestTrade] = []
        equity_curve     : List[EquityCurvePoint] = []
        daily_trades     : Dict[str, int]      = {}
        daily_loss       : Dict[str, float]    = {}
        returns          : List[float]         = []
        monthly_returns  : Dict[str, float]    = {}
        last_month_bal   : float               = config.initial_balance

        min_window = 50  # حداقل کندل برای تحلیل

        # ─── حلقه اصلی بک‌تست ────────────────────────────────────────────────
        for bar_idx in range(min_window, len(candles)):
            current_candle = candles[bar_idx]
            candle_date    = current_candle.timestamp.strftime("%Y-%m-%d")
            candle_month   = current_candle.timestamp.strftime("%Y-%m")

            # ── ۱. مدیریت معاملات باز (بررسی SL/TP) ─────────────────────────
            trades_to_close: List[Tuple[BacktestTrade, str, float]] = []

            for trade in open_trades:
                close_price, close_reason = self._check_sl_tp(trade, current_candle)
                if close_price is not None:
                    trades_to_close.append((trade, close_reason, close_price))

            # بستن معاملاتی که به SL یا TP رسیدند
            for trade, reason, close_px in trades_to_close:
                pnl = self._calculate_pnl(trade, close_px, config)
                self._close_trade(
                    trade, close_px, reason, current_candle.timestamp, bar_idx, pnl
                )
                balance += pnl
                open_trades.remove(trade)
                closed_trades.append(trade)

                # ثبت ضرر روزانه
                if pnl < 0:
                    daily_loss[candle_date] = daily_loss.get(candle_date, 0.0) + abs(pnl)

                logger.debug(
                    f"{'✅' if pnl > 0 else '❌'} معامله بسته شد | "
                    f"{reason} | PnL: {pnl:+.2f}$"
                )

            # ── ۲. محاسبه equity فعلی ────────────────────────────────────────
            floating_pnl = sum(
                self._calculate_floating_pnl(t, current_candle.close, config)
                for t in open_trades
            )
            equity = balance + floating_pnl

            # ── ۳. محاسبه drawdown ───────────────────────────────────────────
            if equity > peak_equity:
                peak_equity = equity
            drawdown_dollar = peak_equity - equity
            drawdown_pct    = (drawdown_dollar / peak_equity * 100) if peak_equity > 0 else 0.0
            if drawdown_pct > max_drawdown:
                max_drawdown        = drawdown_pct
                max_drawdown_dollar = drawdown_dollar

            # ── ۴. ثبت equity curve (هر ۱۰ کندل یک نقطه برای بهینگی) ────────
            if bar_idx % 10 == 0 or bar_idx == len(candles) - 1:
                equity_curve.append(EquityCurvePoint(
                    timestamp = current_candle.timestamp,
                    equity    = equity,
                    balance   = balance,
                    drawdown  = drawdown_pct,
                ))

            # ── ۵. ثبت بازده ماهانه ──────────────────────────────────────────
            if candle_month not in monthly_returns:
                monthly_returns[candle_month] = 0.0
            month_change = (balance - last_month_bal) / last_month_bal * 100
            monthly_returns[candle_month] = round(month_change, 2)
            # بروزرسانی موجودی ماه قبل در ابتدای ماه جدید
            if bar_idx > min_window and candles[bar_idx - 1].timestamp.strftime("%Y-%m") != candle_month:
                last_month_bal = balance

            # ── ۶. بررسی محدودیت‌های روزانه ─────────────────────────────────
            if self._daily_limit_reached(candle_date, daily_trades, daily_loss, balance, config):
                continue

            # ── ۷. بررسی drawdown کل ─────────────────────────────────────────
            total_drawdown_pct = (config.initial_balance - balance) / config.initial_balance * 100
            if total_drawdown_pct >= 20.0:
                logger.warning(f"🛑 drawdown کل به {total_drawdown_pct:.1f}٪ رسید — ادامه بک‌تست متوقف شد")
                break

            # ── ۸. فیلتر اسپرد ───────────────────────────────────────────────
            if config.use_spread_filter and current_candle.spread > config.max_spread_pips:
                continue

            # ── ۹. فراخوانی Signal Generator ─────────────────────────────────
            window = candles[max(0, bar_idx - min_window) : bar_idx + 1]
            try:
                signal = await signal_generator(window, config.symbol)
            except Exception as exc:
                logger.error(f"⚠️ خطا در signal generator: {exc}")
                continue

            if signal is None:
                continue

            # ── ۱۰. بررسی حداقل امتیاز ──────────────────────────────────────
            confidence = signal.get("confidence", 0.0)
            if confidence < config.min_confidence:
                continue

            # ── ۱۱. محاسبه حجم معامله ────────────────────────────────────────
            lot_size, risk_amount = self._calculate_lot_size(
                balance        = balance,
                risk_pct       = config.risk_per_trade_pct,
                entry          = signal["entry"],
                stop_loss      = signal["stop_loss"],
                config         = config,
            )

            if lot_size <= 0:
                continue

            # ── ۱۲. بررسی ریسک پرتفولیو ──────────────────────────────────────
            total_risk_pct = (risk_amount * len(open_trades)) / balance * 100
            if total_risk_pct + config.risk_per_trade_pct > config.max_portfolio_risk:
                logger.debug(f"🚫 ریسک پرتفولیو ({total_risk_pct:.1f}٪) محدودیت را رد کرد")
                continue

            # ── ۱۳. باز کردن معامله ──────────────────────────────────────────
            trade = BacktestTrade(
                trade_id      = str(uuid.uuid4()),
                direction     = TradeDirection(signal["direction"]),
                entry_price   = signal["entry"],
                stop_loss     = signal["stop_loss"],
                take_profit   = signal["take_profit"],
                lot_size      = lot_size,
                entry_time    = current_candle.timestamp,
                entry_bar_idx = bar_idx,
                confidence    = confidence,
                risk_amount   = risk_amount,
            )
            open_trades.append(trade)
            daily_trades[candle_date] = daily_trades.get(candle_date, 0) + 1

            logger.debug(
                f"📈 معامله جدید | {trade.direction.value} {config.symbol} "
                f"@ {trade.entry_price} | SL: {trade.stop_loss} | TP: {trade.take_profit} "
                f"| Lot: {trade.lot_size} | Confidence: {confidence:.0f}٪"
            )

            # ─── بازده برای محاسبه Sharpe ────────────────────────────────────
            if len(closed_trades) > 1:
                prev_balance = closed_trades[-2].pnl_dollar if len(closed_trades) > 1 else config.initial_balance
                returns.append(closed_trades[-1].pnl_dollar / max(balance, 1) * 100)

        # ─── بستن معاملات باز در پایان بک‌تست ────────────────────────────────
        if candles:
            last_candle = candles[-1]
            for trade in open_trades[:]:
                pnl = self._calculate_pnl(trade, last_candle.close, config)
                self._close_trade(
                    trade, last_candle.close, "END", last_candle.timestamp,
                    len(candles) - 1, pnl
                )
                balance += pnl
                closed_trades.append(trade)

        # ─── محاسبه معیارهای عملکرد ──────────────────────────────────────────
        end_time       = datetime.now(timezone.utc)
        duration_secs  = (end_time - start_time).total_seconds()
        result         = self._calculate_metrics(
            backtest_id         = backtest_id,
            config              = config,
            closed_trades       = closed_trades,
            equity_curve        = equity_curve,
            monthly_returns     = monthly_returns,
            final_balance       = balance,
            max_drawdown        = max_drawdown,
            max_drawdown_dollar = max_drawdown_dollar,
            returns             = returns,
            start_time          = start_time,
            end_time            = end_time,
            duration_secs       = duration_secs,
        )

        logger.info(
            f"✅ بک‌تست کامل شد | معاملات: {result.total_trades} | "
            f"Win Rate: {result.win_rate*100:.1f}٪ | "
            f"PF: {result.profit_factor:.2f} | "
            f"MaxDD: {result.max_drawdown:.1f}٪ | "
            f"Sharpe: {result.sharpe_ratio:.2f}"
        )

        return result

    # ─── توابع کمکی ───────────────────────────────────────────────────────────

    def _check_sl_tp(
        self,
        trade  : BacktestTrade,
        candle : Candle,
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        بررسی اینکه آیا SL یا TP در این کندل زده شده است

        خروجی: (قیمت بسته شدن، دلیل) یا (None, None)
        """
        if trade.direction == TradeDirection.BUY:
            if candle.low <= trade.stop_loss:
                return trade.stop_loss, "SL"
            if candle.high >= trade.take_profit:
                return trade.take_profit, "TP"
        else:  # SELL
            if candle.high >= trade.stop_loss:
                return trade.stop_loss, "SL"
            if candle.low <= trade.take_profit:
                return trade.take_profit, "TP"
        return None, None

    def _calculate_pnl(
        self,
        trade      : BacktestTrade,
        close_price: float,
        config     : BacktestConfig,
    ) -> float:
        """
        محاسبه سود/ضرر واقعی یک معامله بسته شده

        فرمول: (قیمت خروج - قیمت ورود) × لات × ارزش پیپ / اندازه پیپ - کمیسیون
        """
        price_diff = (
            close_price - trade.entry_price
            if trade.direction == TradeDirection.BUY
            else trade.entry_price - close_price
        )
        pips       = price_diff / config.pip_size
        pnl_gross  = pips * config.pip_value * trade.lot_size
        commission = config.commission_per_lot * trade.lot_size
        return pnl_gross - commission

    def _calculate_floating_pnl(
        self,
        trade        : BacktestTrade,
        current_price: float,
        config       : BacktestConfig,
    ) -> float:
        """محاسبه سود/ضرر شناور معامله باز"""
        return self._calculate_pnl(trade, current_price, config)

    def _calculate_lot_size(
        self,
        balance  : float,
        risk_pct : float,
        entry    : float,
        stop_loss: float,
        config   : BacktestConfig,
    ) -> Tuple[float, float]:
        """
        محاسبه حجم لات بر اساس درصد ریسک

        خروجی: (lot_size گرد‌شده به ۰.۰۱، risk_amount به دلار)
        """
        risk_amount = balance * (risk_pct / 100)
        sl_distance = abs(entry - stop_loss)
        if sl_distance < config.pip_size:
            return 0.0, 0.0
        sl_pips     = sl_distance / config.pip_size
        lot_size    = risk_amount / (sl_pips * config.pip_value)
        lot_size    = max(0.01, round(lot_size, 2))
        # حداکثر ۱۰ لات برای جلوگیری از اشتباه
        lot_size    = min(lot_size, 10.0)
        return lot_size, risk_amount

    def _close_trade(
        self,
        trade      : BacktestTrade,
        close_price: float,
        reason     : str,
        close_time : datetime,
        bar_idx    : int,
        pnl        : float,
    ) -> None:
        """پر کردن فیلدهای خروج یک معامله"""
        trade.exit_price   = close_price
        trade.exit_time    = close_time
        trade.exit_bar_idx = bar_idx
        trade.exit_reason  = reason
        trade.pnl_dollar   = round(pnl, 2)
        trade.is_winner    = pnl > 0

    def _daily_limit_reached(
        self,
        date         : str,
        daily_trades : Dict[str, int],
        daily_loss   : Dict[str, float],
        balance      : float,
        config       : BacktestConfig,
    ) -> bool:
        """بررسی اینکه آیا محدودیت روزانه رسیده است"""
        trades_today = daily_trades.get(date, 0)
        loss_today   = daily_loss.get(date, 0.0)
        loss_pct     = loss_today / max(balance, 1) * 100

        if trades_today >= config.max_daily_trades:
            return True
        if loss_pct >= config.max_daily_loss_pct:
            return True
        return False

    def _calculate_metrics(
        self,
        backtest_id         : str,
        config              : BacktestConfig,
        closed_trades       : List[BacktestTrade],
        equity_curve        : List[EquityCurvePoint],
        monthly_returns     : Dict[str, float],
        final_balance       : float,
        max_drawdown        : float,
        max_drawdown_dollar : float,
        returns             : List[float],
        start_time          : datetime,
        end_time            : datetime,
        duration_secs       : float,
    ) -> BacktestResult:
        """
        محاسبه تمام معیارهای عملکرد از روی معاملات بسته‌شده

        شامل: WinRate، ProfitFactor، Sharpe، Sortino، Calmar، Recovery
        """
        total_trades   = len(closed_trades)
        winners        = [t for t in closed_trades if t.is_winner]
        losers         = [t for t in closed_trades if not t.is_winner]
        winning_count  = len(winners)
        losing_count   = len(losers)

        gross_profit   = sum(t.pnl_dollar for t in winners)
        gross_loss     = abs(sum(t.pnl_dollar for t in losers))
        net_profit     = gross_profit - gross_loss
        net_profit_pct = (net_profit / config.initial_balance) * 100 if config.initial_balance > 0 else 0

        win_rate       = winning_count / total_trades if total_trades > 0 else 0.0
        profit_factor  = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        avg_win        = gross_profit / winning_count if winning_count > 0 else 0.0
        avg_loss       = gross_loss / losing_count if losing_count > 0 else 0.0
        avg_rr         = avg_win / avg_loss if avg_loss > 0 else 0.0

        largest_win    = max((t.pnl_dollar for t in winners), default=0.0)
        largest_loss   = min((t.pnl_dollar for t in losers), default=0.0)

        # ── بیشترین ضرر/سود متوالی ───────────────────────────────────────────
        consecutive_wins   = self._max_consecutive(closed_trades, win=True)
        consecutive_losses = self._max_consecutive(closed_trades, win=False)

        # ── Sharpe Ratio ─────────────────────────────────────────────────────
        sharpe_ratio  = self._calculate_sharpe(returns, risk_free_annual=2.0)

        # ── Sortino Ratio ────────────────────────────────────────────────────
        sortino_ratio = self._calculate_sortino(returns, risk_free_annual=2.0)

        # ── Calmar Ratio ─────────────────────────────────────────────────────
        # CAGR / MaxDrawdown
        days_total    = max((config.end_date - config.start_date).days, 1)
        years         = days_total / 365.25
        cagr          = ((final_balance / config.initial_balance) ** (1 / years) - 1) * 100 if years > 0 else 0
        calmar_ratio  = cagr / max_drawdown if max_drawdown > 0 else 0.0

        # ── Recovery Factor ───────────────────────────────────────────────────
        recovery_factor = net_profit / max_drawdown_dollar if max_drawdown_dollar > 0 else 0.0

        return BacktestResult(
            backtest_id         = backtest_id,
            config              = config,
            status              = BacktestStatus.COMPLETED,
            start_time          = start_time,
            end_time            = end_time,
            duration_seconds    = duration_secs,
            initial_balance     = config.initial_balance,
            final_balance       = round(final_balance, 2),
            net_profit          = round(net_profit, 2),
            net_profit_pct      = round(net_profit_pct, 2),
            gross_profit        = round(gross_profit, 2),
            gross_loss          = round(gross_loss, 2),
            total_trades        = total_trades,
            winning_trades      = winning_count,
            losing_trades       = losing_count,
            win_rate            = round(win_rate, 4),
            profit_factor       = round(profit_factor, 2),
            avg_win             = round(avg_win, 2),
            avg_loss            = round(avg_loss, 2),
            avg_rr              = round(avg_rr, 2),
            largest_win         = round(largest_win, 2),
            largest_loss        = round(largest_loss, 2),
            consecutive_wins    = consecutive_wins,
            consecutive_losses  = consecutive_losses,
            max_drawdown        = round(max_drawdown, 2),
            max_drawdown_dollar = round(max_drawdown_dollar, 2),
            sharpe_ratio        = round(sharpe_ratio, 2),
            sortino_ratio       = round(sortino_ratio, 2),
            calmar_ratio        = round(calmar_ratio, 2),
            recovery_factor     = round(recovery_factor, 2),
            trades              = closed_trades,
            equity_curve        = equity_curve,
            monthly_returns     = monthly_returns,
        )

    def _max_consecutive(self, trades: List[BacktestTrade], win: bool) -> int:
        """محاسبه بیشترین تعداد برد یا باخت متوالی"""
        max_count = current = 0
        for t in trades:
            if t.is_winner == win:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0
        return max_count

    def _calculate_sharpe(self, returns: List[float], risk_free_annual: float) -> float:
        """
        محاسبه نسبت شارپ

        فرمول: (میانگین بازده - نرخ بی‌ریسک) / انحراف معیار بازده
        """
        if len(returns) < 2:
            return 0.0
        n            = len(returns)
        mean_ret     = sum(returns) / n
        risk_free_pt = risk_free_annual / (252 * 24)  # نرمال‌سازی برای هر کندل
        excess_ret   = mean_ret - risk_free_pt
        variance     = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
        std_dev      = math.sqrt(variance)
        if std_dev == 0:
            return 0.0
        return excess_ret / std_dev * math.sqrt(252)

    def _calculate_sortino(self, returns: List[float], risk_free_annual: float) -> float:
        """
        محاسبه نسبت سورتینو

        مثل شارپ اما فقط انحراف معیار بازده‌های منفی را در نظر می‌گیرد
        """
        if len(returns) < 2:
            return 0.0
        n            = len(returns)
        mean_ret     = sum(returns) / n
        risk_free_pt = risk_free_annual / (252 * 24)
        excess_ret   = mean_ret - risk_free_pt
        neg_returns  = [r for r in returns if r < risk_free_pt]
        if len(neg_returns) < 2:
            return excess_ret * math.sqrt(252) if excess_ret > 0 else 0.0
        downside_var = sum((r - risk_free_pt) ** 2 for r in neg_returns) / len(neg_returns)
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return excess_ret / downside_std * math.sqrt(252)

    def _empty_result(
        self,
        backtest_id: str,
        config     : BacktestConfig,
        start_time : datetime,
        status     : BacktestStatus,
    ) -> BacktestResult:
        """ساخت نتیجه خالی برای حالت‌های خطا"""
        now = datetime.now(timezone.utc)
        return BacktestResult(
            backtest_id         = backtest_id,
            config              = config,
            status              = status,
            start_time          = start_time,
            end_time            = now,
            duration_seconds    = 0.0,
            initial_balance     = config.initial_balance,
            final_balance       = config.initial_balance,
            net_profit          = 0.0,
            net_profit_pct      = 0.0,
            gross_profit        = 0.0,
            gross_loss          = 0.0,
            total_trades        = 0,
            winning_trades      = 0,
            losing_trades       = 0,
            win_rate            = 0.0,
            profit_factor       = 0.0,
            avg_win             = 0.0,
            avg_loss            = 0.0,
            avg_rr              = 0.0,
            largest_win         = 0.0,
            largest_loss        = 0.0,
            consecutive_wins    = 0,
            consecutive_losses  = 0,
            max_drawdown        = 0.0,
            max_drawdown_dollar = 0.0,
            sharpe_ratio        = 0.0,
            sortino_ratio       = 0.0,
            calmar_ratio        = 0.0,
            recovery_factor     = 0.0,
            trades              = [],
            equity_curve        = [],
            monthly_returns     = {},
        )


# ─── نمونه singleton برای استفاده در سراسر سیستم ─────────────────────────────
backtest_engine = BacktestEngine()
