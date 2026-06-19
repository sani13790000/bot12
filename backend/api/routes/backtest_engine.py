"""Backtest Engine API routes — async-safe with ProcessPoolExecutor.

Fixes applied:
- CRITICAL: Replaced MOCK random workers with real engine calls
  (MultiSymbolBacktestEngine, WalkForwardAnalyzer, MonteCarloSimulator)
- HIGH: asyncio.get_event_loop() → asyncio.get_running_loop() (Python 3.10+)
- HIGH: Added job timeout (300s) — jobs can no longer run forever
- HIGH: Jobs dict cleanup to prevent unbounded memory growth
- LOW: Removed _executor._max_workers private attr access
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Executor — CPU-bound backtest work runs in a separate process
# ---------------------------------------------------------------------------
_CPU_WORKERS = max(1, (os.cpu_count() or 2) - 1)
_executor = ProcessPoolExecutor(max_workers=_CPU_WORKERS)

# ---------------------------------------------------------------------------
# In-memory job store (replace with Redis for multi-worker deployments)
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()
JOB_TIMEOUT_SECONDS = 300  # 5 minutes max per job
MAX_JOBS_STORED = 500       # prevent unbounded memory growth


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbol: str = Field("XAUUSD", description="Trading symbol")
    timeframe: str = Field("H1", description="Candle timeframe")
    start_date: str = Field("2024-01-01", description="ISO date string")
    end_date: str = Field("2024-12-31", description="ISO date string")
    initial_balance: float = Field(10_000.0, ge=100)
    risk_pct: float = Field(1.0, ge=0.1, le=10.0)
    strategy: str = Field("smc_pa", description="Strategy identifier")
    parameters: Dict[str, Any] = Field(default_factory=dict)


class WalkForwardRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    n_folds: int = Field(5, ge=2, le=20)
    is_ratio: float = Field(0.7, ge=0.5, le=0.9)
    initial_balance: float = 10_000.0
    risk_pct: float = 1.0


class MonteCarloRequest(BaseModel):
    base_trades: List[Dict[str, Any]] = Field(default_factory=list)
    n_simulations: int = Field(1000, ge=100, le=10_000)
    initial_balance: float = 10_000.0
    ruin_threshold: float = Field(0.5, ge=0.1, le=0.99)


# ---------------------------------------------------------------------------
# CPU-bound worker functions (run in separate process)
# These call the REAL engines — no more mock random data
# ---------------------------------------------------------------------------

def _run_backtest_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run real backtest using MultiSymbolBacktestEngine."""
    try:
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        engine = MultiSymbolBacktestEngine(
            symbol=params["symbol"],
            timeframe=params["timeframe"],
            initial_balance=params["initial_balance"],
            risk_pct=params["risk_pct"],
        )
        result = engine.run(
            start_date=params["start_date"],
            end_date=params["end_date"],
            strategy=params["strategy"],
            parameters=params.get("parameters", {}),
        )
        result["computed_at"] = time.time()
        return result
    except ImportError as exc:
        # Fallback: engine not available — return informative error
        raise RuntimeError(
            f"BacktestEngine import failed: {exc}. "
            "Ensure backend.backtest_engine.multi_symbol_engine is installed."
        ) from exc


def _run_wfo_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run real Walk-Forward Optimisation using WalkForwardAnalyzer."""
    try:
        from backend.backtest_engine.walk_forward_advanced import WalkForwardAnalyzer
        analyzer = WalkForwardAnalyzer(
            symbol=params["symbol"],
            timeframe=params["timeframe"],
            n_folds=params["n_folds"],
            is_ratio=params["is_ratio"],
            initial_balance=params["initial_balance"],
            risk_pct=params["risk_pct"],
        )
        result = analyzer.run()
        result["computed_at"] = time.time()
        return result
    except ImportError as exc:
        raise RuntimeError(
            f"WalkForwardAnalyzer import failed: {exc}."
        ) from exc


def _run_mc_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run real Monte Carlo simulation using MonteCarloSimulator."""
    try:
        from backend.backtest_engine.monte_carlo_advanced import MonteCarloSimulator
        simulator = MonteCarloSimulator(
            base_trades=params.get("base_trades", []),
            n_simulations=params["n_simulations"],
            initial_balance=params["initial_balance"],
            ruin_threshold=params["ruin_threshold"],
        )
        result = simulator.run()
        result["computed_at"] = time.time()
        return result
    except ImportError as exc:
        raise RuntimeError(
            f"MonteCarloSimulator import failed: {exc}."
        ) from exc


# ---------------------------------------------------------------------------
# Helper: run a worker with timeout and job cleanup
# ---------------------------------------------------------------------------

async def _dispatch_job(
    job_id: str,
    job_type: str,
    worker_fn,
    params: Dict[str, Any],
) -> None:
    """Dispatch a CPU-bound worker with timeout protection."""
    async with _jobs_lock:
        _jobs[job_id]["status"] = "running"

    try:
        loop = asyncio.get_running_loop()  # Python 3.10+ safe
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, worker_fn, params),
            timeout=JOB_TIMEOUT_SECONDS,
        )
        async with _jobs_lock:
            _jobs[job_id].update(
                {"status": "done", "result": result, "finished_at": time.time()}
            )
    except asyncio.TimeoutError:
        logger.error("%s job %s timed out after %ss", job_type, job_id, JOB_TIMEOUT_SECONDS)
        async with _jobs_lock:
            _jobs[job_id].update(
                {"status": "error", "error": f"Job timed out after {JOB_TIMEOUT_SECONDS}s"}
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("%s job %s failed: %s", job_type, job_id, exc)
        async with _jobs_lock:
            _jobs[job_id].update({"status": "error", "error": str(exc)})


async def _create_job(job_type: str) -> str:
    """Create a new job entry; evict oldest if limit exceeded."""
    job_id = str(uuid.uuid4())
    async with _jobs_lock:
        # Evict oldest jobs if limit exceeded
        if len(_jobs) >= MAX_JOBS_STORED:
            oldest = sorted(_jobs.items(), key=lambda x: x[1].get("created_at", 0))[:50]
            for k, _ in oldest:
                _jobs.pop(k, None)
        _jobs[job_id] = {
            "status": "queued",
            "type": job_type,
            "created_at": time.time(),
            "result": None,
        }
    return job_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_backtest(body: BacktestRequest) -> Dict[str, Any]:
    """Submit a backtest job. Returns job_id immediately; poll /status/{job_id}."""
    job_id = await _create_job("backtest")
    asyncio.create_task(
        _dispatch_job(job_id, "backtest", _run_backtest_worker, body.model_dump()),
        name=f"backtest_{job_id}",
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/v1/backtest-engine/status/{job_id}",
        "timeout_seconds": JOB_TIMEOUT_SECONDS,
    }


@router.get("/status/{job_id}")
async def backtest_status(job_id: str) -> Dict[str, Any]:
    """Poll backtest job status."""
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return {"job_id": job_id, **job}


@router.delete("/cancel/{job_id}")
async def cancel_backtest(job_id: str) -> Dict[str, str]:
    """Cancel a queued job (running jobs cannot be cancelled)."""
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job["status"] == "queued":
            job["status"] = "cancelled"
    return {"message": f"Job {job_id} cancelled"}


@router.post("/walk-forward", status_code=status.HTTP_202_ACCEPTED)
async def run_walk_forward(body: WalkForwardRequest) -> Dict[str, Any]:
    """Submit a walk-forward optimisation job."""
    job_id = await _create_job("wfo")
    asyncio.create_task(
        _dispatch_job(job_id, "wfo", _run_wfo_worker, body.model_dump()),
        name=f"wfo_{job_id}",
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/v1/backtest-engine/status/{job_id}",
        "timeout_seconds": JOB_TIMEOUT_SECONDS,
    }


@router.post("/monte-carlo", status_code=status.HTTP_202_ACCEPTED)
async def run_monte_carlo(body: MonteCarloRequest) -> Dict[str, Any]:
    """Submit a Monte Carlo simulation job."""
    job_id = await _create_job("mc")
    asyncio.create_task(
        _dispatch_job(job_id, "mc", _run_mc_worker, body.model_dump()),
        name=f"mc_{job_id}",
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "timeout_seconds": JOB_TIMEOUT_SECONDS,
    }


@router.get("/jobs")
async def list_jobs(limit: int = 20) -> Dict[str, Any]:
    """List recent backtest jobs."""
    async with _jobs_lock:
        jobs = [
            {"job_id": k, **{kk: vv for kk, vv in v.items() if kk != "result"}}
            for k, v in list(_jobs.items())[-limit:]
        ]
    return {"jobs": jobs, "total": len(_jobs)}


@router.get("/health")
async def backtest_engine_health() -> Dict[str, Any]:
    """Backtest engine health check."""
    async with _jobs_lock:
        total = len(_jobs)
        running = sum(1 for j in _jobs.values() if j["status"] == "running")
        done = sum(1 for j in _jobs.values() if j["status"] == "done")
    return {
        "status": "healthy",
        "executor": "ProcessPoolExecutor",
        "workers": _CPU_WORKERS,
        "timeout_seconds": JOB_TIMEOUT_SECONDS,
        "max_jobs_stored": MAX_JOBS_STORED,
        "jobs": {"total": total, "running": running, "done": done},
    }
