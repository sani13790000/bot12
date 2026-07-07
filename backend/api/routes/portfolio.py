from __future__ import annotations
import logging
from typing import Any, Dict, List
from fastapi import Depends, APIRouter, HTTPException

from backend.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)], tags=["Portfolio"])


@router.get("/summary")
async def get_portfolio_summary() -> Dict[str, Any]:
    """BUG-T2 FIX: real data from backend.services.trade_service."""
    try:
        from backend.services.trade_service import TradeService
        svc    = TradeService()
        trades = await svc.get_open_trades()
        equity = await svc.get_equity_state()
        risk   = await svc.get_risk_status()
        total_pnl      = sum(t.get("pnl", 0.0) for t in trades)
        total_exposure = sum(
            abs(t.get("volume", 0.0) * t.get("entry_price", 0.0))
            for t in trades
        )
        return {
            "ok": True,
            "summary": {
                "open_positions":  len(trades),
                "total_pnl":       round(total_pnl, 2),
                "total_exposure":  round(total_exposure, 2),
                "equity":          equity.get("equity", 0.0),
                "free_margin":     equity.get("free_margin", 0.0),
                "margin_level":    equity.get("margin_level", 0.0),
                "risk_level":      risk.get("level", "UNKNOWN"),
                "drawdown_pct":    risk.get("drawdown_pct", 0.0),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/positions")
async def get_positions() -> Dict[str, Any]:
    """BUG-T2 FIX: real positions from backend.services.trade_service."""
    try:
        from backend.services.trade_service import TradeService
        trades = await TradeService().get_open_trades()
        return {"ok": True, "positions": trades, "count": len(trades)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/exposure")
async def get_exposure() -> Dict[str, Any]:
    """BUG-T2 FIX: real exposure from backend.services.trade_service."""
    try:
        from backend.services.trade_service import TradeService
        trades = await TradeService().get_open_trades()
        by_symbol: Dict[str, Dict[str, Any]] = {}
        for t in trades:
            sym = t.get("symbol", "UNKNOWN")
            if sym not in by_symbol:
                by_symbol[sym] = {"buy_lots": 0.0, "sell_lots": 0.0, "net_pnl": 0.0, "count": 0}
            vol = float(t.get("volume", 0.0))
            pnl = float(t.get("pnl", 0.0))
            if t.get("direction", "BUY") == "BUY":
                by_symbol[sym]["buy_lots"]  += vol
            else:
                by_symbol[sym]["sell_lots"] += vol
            by_symbol[sym]["net_pnl"] += pnl
            by_symbol[sym]["count"]   += 1
        for sym, data in by_symbol.items():
            data["net_lots"]  = round(data["buy_lots"] - data["sell_lots"], 2)
            data["buy_lots"]  = round(data["buy_lots"],  2)
            data["sell_lots"] = round(data["sell_lots"], 2)
            data["net_pnl"]   = round(data["net_pnl"],   2)
        return {"ok": True, "by_symbol": by_symbol, "total_symbols": len(by_symbol)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/correlation")
async def get_correlation() -> Dict[str, Any]:
    """Rolling correlation matrix. BUG-U1 FIX: correct import path."""
    try:
        from backend.risk.correlation_filter import RollingCorrelationEngine
        engine = RollingCorrelationEngine()
        matrix = await engine.cache_stats()
        symbols = engine.get_tracked_symbols()
        return {
            "ok": True,
            "tracked_symbols": symbols,
            "symbol_count": len(symbols),
            "cache_stats": matrix,
            "engine": "rolling_pearson_window50",
            "note": "add prices via /portfolio/correlation/feed to populate matrix"
        }
    except Exception as exc:
        logger.error("[Portfolio] correlation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/correlation/feed")
async def feed_price(symbol: str, price: float) -> Dict[str, Any]:
    """Feed a live price to the rolling correlation engine."""
    try:
        from backend.risk.correlation_filter import RollingCorrelationEngine
        engine = RollingCorrelationEngine()
        await engine.add_price(symbol, price)
        return {"ok": True, "symbol": symbol.upper(), "price": price}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
