from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Backtest Engine"])


class BacktestEngineRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field("H1", description="Timeframe")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    initial_balance: float = Field(10000.0, ge=100)
    risk_per_trade: float = Field(0.01, ge=0.001, le=0.1)
    commission: float = Field(0.0, ge=0)
    slippage: float = Field(0.0, ge=0)
    use_smc: bool = Field(True)
    use_pa: bool = Field(True)
    use_ml: bool = Field(False)
    max_trades: Optional[int] = Field(None, ge=1)


class WalkForwardRequest(BaseModel):
    symbol: str
    timeframe: str = "H1"
    start_date: str
    end_date: str
    n_splits: int = Field(5, ge=2, le=20)
    initial_balance: float = Field(10000.0, ge=100)
    risk_per_trade: float = Field(0.01, ge=0.001, le=0.1)


@router.post("/run")
async def run_backtest(
    req: BacktestEngineRequest,
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Run a full backtest using the BacktestEngine."""
    try:
        from backend.research.backtest.engine import BacktestEngine, BacktestConfig
        config = BacktestConfig(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_balance=req.initial_balance,
            risk_per_trade=req.risk_per_trade,
            commission=req.commission,
            slippage=req.slippage,
            use_smc=req.use_smc,
            use_pa=req.use_pa,
            use_ml=req.use_ml,
            max_trades=req.max_trades,
        )
        engine = BacktestEngine(config)
        result = await engine.run()
        return {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        logger.exception("[backtest_engine] run error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/walk-forward")
async def run_walk_forward(
    req: WalkForwardRequest,
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Run walk-forward validation."""
    try:
        from backend.research.backtest.engine import BacktestEngine, BacktestConfig
        from backend.research.backtest.walk_forward import WalkForwardValidator
        config = BacktestConfig(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_balance=req.initial_balance,
            risk_per_trade=req.risk_per_trade,
        )
        validator = WalkForwardValidator(config, n_splits=req.n_splits)
        result = await validator.run()
        return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("[backtest_engine] walk_forward error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/results")
async def list_backtest_results(
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    """List all saved backtest results."""
    try:
        from backend.database.client import db_client
        rows = await db_client.select(
            "backtest_results",
            limit=50,
            order="created_at.desc",
        )
        return {"ok": True, "results": rows or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
