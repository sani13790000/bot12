"""
================================================================================
Galaxy Vast AI Trading Platform
API Routes — Research (Backtest + Replay + Walk-Forward)

این ماژول تمام endpoints مربوط به بک‌تست، ریپلی و Walk-Forward را
در اختیار داشبورد و کلاینت‌ها قرار می‌دهد.

نسخه: 3.0.0
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator

from ...core.logger import get_logger
from ...research.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    backtest_engine,
)
from ...research.backtest.monte_carlo import monte_carlo_simulator
from ...research.replay.engine import (
    ReplayConfig,
    ReplaySpeed,
    replay_engine,
)
from ...research.walk_forward.analyzer import (
    WalkForwardConfig,
    walk_forward_analyzer,
)

logger = get_logger("api.routes.research")

# ─── Router ───────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/research", tags=["Research"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    """درخواست بک‌تست از طریق API"""
    symbol              : str   = Field(..., example="XAUUSD")
    start_date          : str   = Field(..., example="2024-01-01")
    end_date            : str   = Field(..., example="2024-12-31")
    initial_balance     : float = Field(default=10_000.0, ge=1_000)
    risk_per_trade_pct  : float = Field(default=1.0, ge=0.1, le=10.0)
    max_portfolio_risk  : float = Field(default=5.0, ge=1.0, le=20.0)
    max_daily_trades    : int   = Field(default=5, ge=1, le=50)
    max_daily_loss_pct  : float = Field(default=3.0, ge=0.5, le=20.0)
    min_confidence      : float = Field(default=80.0, ge=50.0, le=100.0)
    pip_size            : float = Field(default=0.0001)
    pip_value           : float = Field(default=10.0)
    commission_per_lot  : float = Field(default=7.0, ge=0)
    # داده‌های کندل — از MT5 یا CSV
    candles             : List[Dict[str, Any]] = Field(
        ..., description="لیست کندل‌ها: [{timestamp, open, high, low, close, volume}]"
    )

    @validator("candles")
    def validate_candles(cls, v):
        if len(v) < 50:
            raise ValueError("حداقل ۵۰ کندل برای بک‌تست نیاز است")
        return v


class ReplayStartRequest(BaseModel):
    """درخواست شروع ریپلی"""
    symbol      : str         = Field(..., example="XAUUSD")
    start_date  : str         = Field(..., example="2024-01-01")
    end_date    : Optional[str] = None
    speed       : ReplaySpeed = Field(default=ReplaySpeed.NORMAL)
    run_analysis: bool        = Field(default=True)
    candles     : List[Dict[str, Any]] = Field(...)

    @validator("candles")
    def validate_candles(cls, v):
        if len(v) < 10:
            raise ValueError("حداقل ۱۰ کندل برای ریپلی نیاز است")
        return v


class WalkForwardRequest(BaseModel):
    """درخواست تحلیل Walk-Forward"""
    symbol              : str   = Field(..., example="XAUUSD")
    start_date          : str   = Field(..., example="2023-01-01")
    end_date            : str   = Field(..., example="2024-12-31")
    initial_balance     : float = Field(default=10_000.0)
    risk_per_trade_pct  : float = Field(default=1.0)
    min_confidence      : float = Field(default=80.0)
    window_count        : int   = Field(default=5, ge=2, le=20)
    use_rolling_windows : bool  = Field(default=True)
    candles             : List[Dict[str, Any]] = Field(...)

    @validator("candles")
    def validate_candles(cls, v):
        if len(v) < 200:
            raise ValueError("حداقل ۲۰۰ کندل برای Walk-Forward نیاز است")
        return v


# ─── Endpoint ها ─────────────────────────────────────────────────────────────

@router.post("/backtest", summary="اجرای بک‌تست")
async def run_backtest(request: BacktestRequest) -> Dict[str, Any]:
    """
    اجرای بک‌تست کامل روی داده‌های تاریخی

    خروجی شامل تمام معیارهای عملکرد:
    WinRate، ProfitFactor، Sharpe، Sortino، Calmar، MaxDrawdown، ...
    """
    try:
        from ...research.backtest.engine import Candle

        # ── تبدیل داده ورودی به Candle ───────────────────────────────────────
        candles = []
        for c in request.candles:
            ts = c.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            candles.append(Candle(
                timestamp = ts,
                open      = float(c["open"]),
                high      = float(c["high"]),
                low       = float(c["low"]),
                close     = float(c["close"]),
                volume    = float(c.get("volume", 0)),
                spread    = float(c.get("spread", 1.0)),
            ))

        config = BacktestConfig(
            symbol             = request.symbol,
            start_date         = datetime.fromisoformat(request.start_date),
            end_date           = datetime.fromisoformat(request.end_date),
            initial_balance    = request.initial_balance,
            risk_per_trade_pct = request.risk_per_trade_pct,
            max_portfolio_risk = request.max_portfolio_risk,
            max_daily_trades   = request.max_daily_trades,
            max_daily_loss_pct = request.max_daily_loss_pct,
            min_confidence     = request.min_confidence,
            pip_size           = request.pip_size,
            pip_value          = request.pip_value,
            commission_per_lot = request.commission_per_lot,
        )

        # ── Signal Generator پیش‌فرض (از Decision Engine واقعی) ─────────────
        from ...services.decision_service import decision_service

        async def signal_gen(window, symbol):
            if len(window) < 20:
                return None
            from ...analysis.decision_engine import MarketData, Timeframe
            market_data = MarketData(
                symbol    = symbol,
                timeframe = Timeframe.H1,
                candles   = window,
                spread    = window[-1].spread if hasattr(window[-1], 'spread') else 1.0,
                atr       = 0.001,
            )
            result = await decision_service.analyze(market_data)
            if result.action.value in ("BUY", "SELL"):
                return {
                    "direction"  : result.action.value,
                    "entry"      : result.entry_price,
                    "stop_loss"  : result.stop_loss,
                    "take_profit": result.take_profit,
                    "confidence" : result.confidence * 100,
                }
            return None

        result = await backtest_engine.run(config, candles, signal_gen)

        logger.info(f"✅ بک‌تست API | {result.total_trades} معامله | WR: {result.win_rate*100:.1f}٪")
        return {"success": True, "data": result.to_dict()}

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"❌ خطا در بک‌تست: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطای داخلی سیستم")


@router.post("/backtest/monte-carlo", summary="شبیه‌سازی مونت‌کارلو")
async def run_monte_carlo(
    trades_pnl   : List[float],
    simulations  : int   = 1000,
    initial_balance: float = 10_000.0,
) -> Dict[str, Any]:
    """
    اجرای شبیه‌سازی مونت‌کارلو روی نتایج بک‌تست

    نتیجه: توزیع احتمال سود، drawdown، و احتمال از دست دادن سرمایه
    """
    from ...research.backtest.engine import BacktestTrade, TradeDirection
    from datetime import datetime, timezone

    # ساخت trade object از PnL ساده
    fake_trades = []
    for i, pnl in enumerate(trades_pnl):
        t = BacktestTrade(
            trade_id      = str(i),
            direction     = TradeDirection.BUY,
            entry_price   = 1.0,
            stop_loss     = 0.99,
            take_profit   = 1.02,
            lot_size      = 1.0,
            entry_time    = datetime.now(timezone.utc),
            entry_bar_idx = i,
            confidence    = 80.0,
            risk_amount   = abs(pnl),
        )
        t.pnl_dollar = pnl
        t.is_winner  = pnl > 0
        fake_trades.append(t)

    simulator = type(monte_carlo_simulator)(simulations=min(simulations, 5000))
    result    = simulator.run(fake_trades, initial_balance)

    return {
        "success": True,
        "data"   : {
            "simulations"         : result.simulations,
            "mean_final_return"   : result.mean_final_return,
            "median_final_return" : result.median_final_return,
            "p5_final_return"     : result.p5_final_return,
            "p95_final_return"    : result.p95_final_return,
            "mean_max_drawdown"   : result.mean_max_drawdown,
            "p95_max_drawdown"    : result.p95_max_drawdown,
            "p99_max_drawdown"    : result.p99_max_drawdown,
            "prob_profit_pct"     : round(result.prob_profit * 100, 1),
            "prob_ruin_pct"       : round(result.prob_ruin * 100, 1),
            "summary"             : result.summary,
        }
    }


@router.post("/replay/load", summary="بارگذاری ریپلی")
async def load_replay(request: ReplayStartRequest) -> Dict[str, Any]:
    """
    بارگذاری داده برای ریپلی بازار

    بعد از این endpoint، از /replay/state و /replay/control استفاده کنید.
    """
    try:
        from ...research.backtest.engine import Candle

        candles = []
        for c in request.candles:
            ts = c.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            candles.append(Candle(
                timestamp = ts,
                open      = float(c["open"]),
                high      = float(c["high"]),
                low       = float(c["low"]),
                close     = float(c["close"]),
                volume    = float(c.get("volume", 0)),
            ))

        end_date = None
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date)

        config = ReplayConfig(
            symbol       = request.symbol,
            start_date   = datetime.fromisoformat(request.start_date),
            end_date     = end_date,
            speed        = request.speed,
            run_analysis = request.run_analysis,
        )

        replay_id = await replay_engine.load(config, candles)
        return {"success": True, "replay_id": replay_id, "total_candles": len(candles)}

    except Exception as exc:
        logger.error(f"❌ خطا در بارگذاری ریپلی: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/replay/state", summary="وضعیت ریپلی")
async def get_replay_state() -> Dict[str, Any]:
    """دریافت وضعیت فعلی ریپلی"""
    return {"success": True, "data": replay_engine.state.to_dict()}


@router.post("/replay/control/{action}", summary="کنترل ریپلی")
async def control_replay(
    action    : str,
    bar_index : Optional[int] = None,
    speed     : Optional[ReplaySpeed] = None,
) -> Dict[str, Any]:
    """
    کنترل ریپلی

    action: pause | resume | stop | jump
    """
    if action == "pause":
        replay_engine.pause()
    elif action == "resume":
        replay_engine.resume()
    elif action == "stop":
        replay_engine.stop()
    elif action == "jump" and bar_index is not None:
        replay_engine.jump_to(bar_index)
    elif action == "speed" and speed is not None:
        replay_engine.set_speed(speed)
    else:
        raise HTTPException(status_code=400, detail=f"دستور نامعتبر: {action}")

    return {"success": True, "action": action, "state": replay_engine.state.to_dict()}


@router.post("/walk-forward", summary="تحلیل Walk-Forward")
async def run_walk_forward(request: WalkForwardRequest) -> Dict[str, Any]:
    """
    اجرای تحلیل Walk-Forward برای ارزیابی overfitting

    خروجی: توصیه ROBUST / ACCEPTABLE / OVERFITTED
    """
    try:
        from ...research.backtest.engine import Candle

        candles = []
        for c in request.candles:
            ts = c.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            candles.append(Candle(
                timestamp = ts,
                open      = float(c["open"]),
                high      = float(c["high"]),
                low       = float(c["low"]),
                close     = float(c["close"]),
                volume    = float(c.get("volume", 0)),
            ))

        config = WalkForwardConfig(
            symbol              = request.symbol,
            start_date          = datetime.fromisoformat(request.start_date),
            end_date            = datetime.fromisoformat(request.end_date),
            initial_balance     = request.initial_balance,
            risk_per_trade_pct  = request.risk_per_trade_pct,
            min_confidence      = request.min_confidence,
            window_count        = request.window_count,
            use_rolling_windows = request.use_rolling_windows,
        )

        from ...services.decision_service import decision_service
        from ...analysis.decision_engine import MarketData, Timeframe

        async def signal_gen(window, symbol):
            if len(window) < 20:
                return None
            market_data = MarketData(
                symbol=symbol, timeframe=Timeframe.H1,
                candles=window, spread=1.0, atr=0.001,
            )
            result = await decision_service.analyze(market_data)
            if result.action.value in ("BUY", "SELL"):
                return {
                    "direction"  : result.action.value,
                    "entry"      : result.entry_price,
                    "stop_loss"  : result.stop_loss,
                    "take_profit": result.take_profit,
                    "confidence" : result.confidence * 100,
                }
            return None

        result = await walk_forward_analyzer.analyze(config, candles, signal_gen)

        logger.info(f"✅ Walk-Forward API | {result.recommendation}")
        return {"success": True, "data": result.to_dict()}

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"❌ خطا در Walk-Forward: {exc}")
        raise HTTPException(status_code=500, detail="خطای داخلی سیستم")
