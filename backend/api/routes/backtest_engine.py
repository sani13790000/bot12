"""
Backtest engine API.

Provides endpoints to run backtests, walk-forward analysis, and Monte-Carlo
simulations using the real engine implementations and an LRU+Redis cache.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.core.cache import cache
from backend.core.config import settings
from backend.core.deps import get_current_user
from backend.backtest_engine import (
    MonteCarloSimulator,
    MultiSymbolBacktestEngine,
    WalkForwardAnalyzer,
)
from backend.backtest_engine.data_provider import DataProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest-engine", tags=["Backtest Engine"])

# ── Config ──────────────────────────────────────────
_CPU_WORKERS = min(
    max(2, os.cpu_count() or 2),
    getattr(settings, "BACKTEST_MAX_WORKERS", 4),
)
_JOB_TIMEOUT_SECONDS = 300
_MAX_JOBS_STORED = 500

# ── State ───────────────────────────────────────────
_executor: Optional[ProcessPoolExecutor] = None
_executor_lock = asyncio.Lock()
_jobs_lock = asyncio.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


async def _get_executor() -> ProcessPoolExecutor:
    global _executor  # noqa: PLW0603
    if _executor is None or _executor._shutdown:  # type: ignore[attr-defined]
        async with _executor_lock:
            if _executor is None or _executor._shutdown:  # type: ignore[attr-defined]
                _executor = ProcessPoolExecutor(
                    max_workers=_CPU_WORKERS,
                    initializer=_worker_init,
                )
    return _executor


def _worker_init() -> None:
    """Lower CPU priority for worker processes."""
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


# ── Worker wrappers ─────────────────────────────────

def _run_backtest_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a real backtest in a process worker."""
    provider = DataProvider()
    candles = provider.get_candles_sync(
        symbol=params["symbol"],
        timeframe=params["timeframe"],
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        limit=params.get("limit", 5000),
    )
    engine = MultiSymbolBacktestEngine(
        symbol=params["symbol"],
        timeframe=params["timeframe"],
        initial_balance=params.get("initial_balance", 10_000.0),
        risk_pct=params.get("risk_pct", 1.0),
    )
    return engine.run(
        candles=candles,
        strategy=params.get("strategy", "smc"),
        parameters=params.get("parameters", {}),
    )


def _run_wfo_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run real walk-forward optimization."""
    provider = DataProvider()
    candles = provider.get_candles_sync(
        symbol=params["symbol"],
        timeframe=params["timeframe"],
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        limit=params.get("limit", 5000),
    )
    analyzer = WalkForwardAnalyzer(
        symbol=params["symbol"],
        timeframe=params["timeframe"],
        train_pct=params.get("train_pct", 0.7),
        n_splits=params.get("n_splits", 5),
    )
    return analyzer.run(
        candles=candles,
        strategy=params.get("strategy", "smc"),
        param_grid=params.get("param_grid", {}),
    )


def _run_mc_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run real Monte-Carlo simulation."""
    simulator = MonteCarloSimulator(
        n_iterations=params.get("n_iterations", 1000),
        confidence_level=params.get("confidence_level", 0.95),
    )
    return simulator.run(trades=params.get("trades", []))


# ── Job management ──────────────────────────────────

def _cache_key(prefix: str, params: Dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return f"backtest:{prefix}:{hashlib.sha256(payload.encode()).hexdigest()[:32]}"


async def _run_job(
    job_id: str,
    kind: str,
    worker_fn: Any,
    params: Dict[str, Any],
) -> None:
    loop = asyncio.get_running_loop()
    executor = await _get_executor()
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, worker_fn, params),
            timeout=_JOB_TIMEOUT_SECONDS,
        )
        result["job_id"] = job_id
        result["kind"] = kind
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        await _set_job(job_id, "completed", result)
        await cache.set(_cache_key(kind, params), result, ttl=3600)
    except asyncio.TimeoutError:
        await _set_job(
            job_id,
            "failed",
            {"error": f"Job exceeded {_JOB_TIMEOUT_SECONDS}s timeout"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("backtest job failed")
        await _set_job(job_id, "failed", {"error": str(exc)})


async def _set_job(job_id: str, status: str, payload: Dict[str, Any]) -> None:
    async with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": status,
            "result": payload if status == "completed" else None,
            "error": payload.get("error") if status == "failed" else None,
            "updated_at": time.time(),
        }
        # Evict oldest if over capacity
        while len(_jobs) > _MAX_JOBS_STORED:
            oldest = next(iter(_jobs))
            _jobs.pop(oldest, None)

    # Persist short-term in Redis for multi-worker deployments
    try:
        await cache.set(f"job:{job_id}", _jobs[job_id], ttl=3600)
    except Exception:  # noqa: BLE001
        pass


async def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    # Memory first
    if job_id in _jobs:
        return _jobs[job_id]
    # Redis fallback
    return await cache.get(f"job:{job_id}")


# ── Public endpoints ────────────────────────────────

@router.post("/run")
async def run_backtest(
    symbol: str,
    timeframe: str = "H1",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    strategy: str = "smc",
    initial_balance: float = 10_000.0,
    risk_pct: float = 1.0,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    params = {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "strategy": strategy,
        "initial_balance": initial_balance,
        "risk_pct": risk_pct,
    }
    cache_key = _cache_key("backtest", params)
    cached = await cache.get(cache_key)
    if cached:
        return {"job_id": cached.get("job_id"), "cached": True, "result": cached}

    job_id = str(uuid.uuid4())
    await _set_job(job_id, "running", {})
    asyncio.create_task(
        _run_job(job_id, "backtest", _run_backtest_worker, params),
        name=f"backtest-{job_id}",
    )
    return {"job_id": job_id, "status": "running"}


@router.post("/wfo")
async def run_wfo(
    symbol: str,
    timeframe: str = "H1",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    strategy: str = "smc",
    train_pct: float = 0.7,
    n_splits: int = 5,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    params = {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "strategy": strategy,
        "train_pct": train_pct,
        "n_splits": n_splits,
    }
    cache_key = _cache_key("wfo", params)
    cached = await cache.get(cache_key)
    if cached:
        return {"job_id": cached.get("job_id"), "cached": True, "result": cached}

    job_id = str(uuid.uuid4())
    await _set_job(job_id, "running", {})
    asyncio.create_task(
        _run_job(job_id, "wfo", _run_wfo_worker, params),
        name=f"wfo-{job_id}",
    )
    return {"job_id": job_id, "status": "running"}


@router.post("/monte-carlo")
async def run_monte_carlo(
    trades: list[Dict[str, Any]],
    n_iterations: int = 1000,
    confidence_level: float = 0.95,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    if n_iterations > 50_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="n_iterations must be <= 50000",
        )
    params = {
        "trades": trades,
        "n_iterations": n_iterations,
        "confidence_level": confidence_level,
    }
    cache_key = _cache_key("mc", params)
    cached = await cache.get(cache_key)
    if cached:
        return {"job_id": cached.get("job_id"), "cached": True, "result": cached}

    job_id = str(uuid.uuid4())
    await _set_job(job_id, "running", {})
    asyncio.create_task(
        _run_job(job_id, "monte_carlo", _run_mc_worker, params),
        name=f"mc-{job_id}",
    )
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    job = await _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs")
async def list_jobs(
    limit: int = 50,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    jobs = sorted(
        _jobs.values(),
        key=lambda j: j.get("updated_at", 0),
        reverse=True,
    )[:limit]
    return {"jobs": jobs, "count": len(jobs)}
