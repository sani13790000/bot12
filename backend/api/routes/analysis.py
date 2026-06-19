"""
Analysis endpoints — SMC, Price Action, Decision, Voting.

Performance:
  * All analysis endpoints are cached for 30 seconds (L1 memory + Redis L2)
  * SMC + PA + AI predictions run concurrently via asyncio.gather
  * asyncio.wait_for(timeout=30) prevents slow engine blocking the event loop
  * Symbol validated against frozenset whitelist before calling engines
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.cache import cache
from backend.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["Analysis"])

_ALLOWED_SYMBOLS: frozenset[str] = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "EURGBP", "EURJPY",
    "GBPJPY", "BTCUSD", "ETHUSD", "XAGUSD",
})
_ALLOWED_TIMEFRAMES: frozenset[str] = frozenset({
    "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1",
})
_ENGINE_TIMEOUT = 30.0  # seconds


def _validate_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s not in _ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Symbol '{symbol}' not supported. Allowed: {sorted(_ALLOWED_SYMBOLS)}",
        )
    return s


def _validate_timeframe(tf: str) -> str:
    t = tf.upper()
    if t not in _ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Timeframe '{tf}' not supported.",
        )
    return t


async def _run_with_timeout(
    coro: Any,
    timeout: float = _ENGINE_TIMEOUT,
    label: str = "engine",
) -> Optional[Any]:
    """Run a coroutine with timeout; return None on timeout/error."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %ss", label, timeout)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s error: %s", label, exc)
        return None


# ── Lazy engine imports ──────────────────────────────────────
# Import at request time to avoid blocking startup

def _smc_engine():
    from backend.analysis.smc_engine import SMCEngine
    return SMCEngine()


def _pa_engine():
    from backend.analysis.price_action_engine import PriceActionEngine
    return PriceActionEngine()


def _decision_engine():
    from backend.analysis.decision_engine import DecisionEngine
    return DecisionEngine()


def _voting_engine():
    from backend.agents.voting_engine import VotingEngine
    return VotingEngine()


def _prediction_service():
    from backend.ai_prediction.prediction_service import PredictionService
    return PredictionService()


# ── Endpoints ──────────────────────────────────────────

@router.get("/smc")
async def get_smc_analysis(
    symbol: str = Query(..., description="Trading symbol"),
    timeframe: str = Query("H1"),
    limit: int = Query(500, ge=50, le=5000),
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    symbol = _validate_symbol(symbol)
    timeframe = _validate_timeframe(timeframe)
    key = f"analysis:smc:{symbol}:{timeframe}:{limit}"

    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    async def _run() -> Dict[str, Any]:
        engine = _smc_engine()
        return await asyncio.get_running_loop().run_in_executor(
            None, engine.analyze, symbol, timeframe, limit
        )

    result = await _run_with_timeout(_run(), label=f"SMC:{symbol}")
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="SMC engine timed out",
        )
    await cache.set(key, result, ttl=30)
    return result


@router.get("/price-action")
async def get_price_action(
    symbol: str = Query(...),
    timeframe: str = Query("H1"),
    limit: int = Query(500, ge=50, le=5000),
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    symbol = _validate_symbol(symbol)
    timeframe = _validate_timeframe(timeframe)
    key = f"analysis:pa:{symbol}:{timeframe}:{limit}"

    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    async def _run() -> Dict[str, Any]:
        engine = _pa_engine()
        return await asyncio.get_running_loop().run_in_executor(
            None, engine.analyze, symbol, timeframe, limit
        )

    result = await _run_with_timeout(_run(), label=f"PA:{symbol}")
    if result is None:
        raise HTTPException(status_code=504, detail="Price Action engine timed out")
    await cache.set(key, result, ttl=30)
    return result


@router.get("/combined")
async def get_combined_analysis(
    symbol: str = Query(...),
    timeframe: str = Query("H1"),
    limit: int = Query(500, ge=50, le=5000),
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run SMC + Price Action + AI Prediction concurrently."""
    symbol = _validate_symbol(symbol)
    timeframe = _validate_timeframe(timeframe)
    key = f"analysis:combined:{symbol}:{timeframe}:{limit}"

    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    loop = asyncio.get_running_loop()

    async def _smc() -> Optional[Dict[str, Any]]:
        e = _smc_engine()
        return await loop.run_in_executor(None, e.analyze, symbol, timeframe, limit)

    async def _pa() -> Optional[Dict[str, Any]]:
        e = _pa_engine()
        return await loop.run_in_executor(None, e.analyze, symbol, timeframe, limit)

    async def _ai() -> Optional[Dict[str, Any]]:
        svc = _prediction_service()
        return await loop.run_in_executor(None, svc.predict, symbol, timeframe)

    # Run all three concurrently — each with its own timeout
    smc_result, pa_result, ai_result = await asyncio.gather(
        _run_with_timeout(_smc(), label="SMC"),
        _run_with_timeout(_pa(), label="PA"),
        _run_with_timeout(_ai(), label="AI"),
        return_exceptions=False,
    )

    result: Dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "smc": smc_result,
        "price_action": pa_result,
        "ai_prediction": ai_result,
    }
    await cache.set(key, result, ttl=30)
    return result


@router.get("/decision")
async def get_decision(
    symbol: str = Query(...),
    timeframe: str = Query("H1"),
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    symbol = _validate_symbol(symbol)
    timeframe = _validate_timeframe(timeframe)
    key = f"analysis:decision:{symbol}:{timeframe}"

    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    async def _run() -> Dict[str, Any]:
        engine = _decision_engine()
        return await asyncio.get_running_loop().run_in_executor(
            None, engine.decide, symbol, timeframe
        )

    result = await _run_with_timeout(_run(), label=f"Decision:{symbol}")
    if result is None:
        raise HTTPException(status_code=504, detail="Decision engine timed out")
    await cache.set(key, result, ttl=30)
    return result


@router.get("/vote")
async def get_vote(
    symbol: str = Query(...),
    timeframe: str = Query("H1"),
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    symbol = _validate_symbol(symbol)
    timeframe = _validate_timeframe(timeframe)
    key = f"analysis:vote:{symbol}:{timeframe}"

    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    async def _run() -> Dict[str, Any]:
        engine = _voting_engine()
        return await asyncio.get_running_loop().run_in_executor(
            None, engine.vote, symbol, timeframe
        )

    result = await _run_with_timeout(_run(), label=f"Vote:{symbol}")
    if result is None:
        raise HTTPException(status_code=504, detail="Voting engine timed out")
    await cache.set(key, result, ttl=30)
    return result


@router.get("/symbols")
async def list_symbols(
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    return {"symbols": sorted(_ALLOWED_SYMBOLS), "count": len(_ALLOWED_SYMBOLS)}
