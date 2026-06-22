from __future__ import annotations
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/summary")
async def get_portfolio_summary() -> Dict[str, Any]:
    """P-19 FIX: real data from trade_service."""
    try:
        from backend.trading.trade_service import TradeService
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
    """P-19 FIX: real positions from MT5."""
    try:
        from backend.trading.trade_service import TradeService
        trades = await TradeService().get_open_trades()
        return {"ok": True, "positions": trades, "count": len(trades)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/exposure")
async def get_exposure() -> Dict[str, Any]:
    """P-21 FIX: real exposure calculation per symbol and direction."""
    try:
        from backend.trading.trade_service import TradeService
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
    """P-20 FIX: rolling correlation instead of hardcoded table."""
    try:
        from backend.trading.correlation_filter import RollingCorrelationEngine
        engine = RollingCorrelationEngine()
        matrix = engine.portfolio_correlation_matrix()
        return {"ok": True, "matrix": matrix, "engine": "rolling_pearson"}
    except Exception as exc:
        logger.error("[Portfolio] correlation error: %s", exc)
        return {"ok": True, "matrix": {}, "engine": "unavailable", "error": str(exc)}


@router.get("/risk-breakdown")
async def get_risk_breakdown() -> Dict[str, Any]:
    try:
        from backend.trading.risk_orchestrator import RiskOrchestrator
        status = await RiskOrchestrator().get_full_status()
        return {"ok": True, "breakdown": status}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
