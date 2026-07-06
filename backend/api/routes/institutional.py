from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["institutional"])


class InstitutionalBacktestRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol e.g. XAUUSD")
    timeframe: str = Field("H1", description="Timeframe e.g. M1, M5, H1, D1")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    initial_balance: float = Field(10000.0, ge=100)
    risk_per_trade: float = Field(0.01, ge=0.001, le=0.1)
    use_smc: bool = Field(True)
    use_pa: bool = Field(True)
    use_ml: bool = Field(False)


class InstitutionalSignalRequest(BaseModel):
    symbol: str
    timeframe: str = "H1"
    candles: List[Dict[str, Any]]
    context: Optional[Dict[str, Any]] = None


@router.post("/backtest")
async def run_institutional_backtest(
    req: InstitutionalBacktestRequest,
) -> Dict[str, Any]:
    """Run institutional-grade backtest with full SMC + PA analysis."""
    try:
        from backend.research.backtest.engine import BacktestEngine, BacktestConfig
        config = BacktestConfig(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_balance=req.initial_balance,
            risk_per_trade=req.risk_per_trade,
            use_smc=req.use_smc,
            use_pa=req.use_pa,
            use_ml=req.use_ml,
        )
        engine = BacktestEngine(config)
        result = await engine.run()
        return {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        logger.exception("[institutional] backtest error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/signal")
async def get_institutional_signal(
    req: InstitutionalSignalRequest,
) -> Dict[str, Any]:
    """Generate institutional-grade signal with full context enrichment."""
    try:
        from backend.analysis.decision_engine import DecisionEngine
        from backend.analysis.smc_engine import SMCEngine
        from backend.analysis.price_action_engine import PriceActionEngine

        smc_engine = SMCEngine()
        pa_engine  = PriceActionEngine()
        dec_engine = DecisionEngine()

        smc_result = smc_engine.analyse(req.candles)
        pa_result  = pa_engine.analyze(req.candles)
        decision   = dec_engine.decide(
            smc_result=smc_result,
            pa_result=pa_result,
            symbol=req.symbol,
            timeframe=req.timeframe,
        )
        return {
            "ok": True,
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "decision": decision,
        }
    except Exception as exc:
        logger.exception("[institutional] signal error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def get_institutional_summary() -> Dict[str, Any]:
    """Return institutional trading summary statistics."""
    try:
        from backend.database.client import db_client
        rows = await db_client.select(
            "institutional_trades",
            limit=100,
            order="created_at.desc",
        )
        total = len(rows or [])
        winners = sum(1 for r in (rows or []) if r.get("pnl", 0) > 0)
        total_pnl = sum(r.get("pnl", 0) for r in (rows or []))
        return {
            "ok": True,
            "total_trades": total,
            "winners": winners,
            "win_rate": round(winners / total, 4) if total else 0.0,
            "total_pnl": round(total_pnl, 2),
        }
    except Exception as exc:
        logger.exception("[institutional] summary error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
