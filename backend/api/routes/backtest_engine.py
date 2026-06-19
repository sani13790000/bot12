"""Galaxy Vast AI Trading Platform
Backtest Engine API Routes

Fixes applied:
- HIGH: asyncio.get_event_loop() → asyncio.get_running_loop() (Python 3.10+ safe)
- HIGH: _jobs in-memory dict — added MAX_JOBS_STORED=500 cap with eviction
- HIGH: No job timeout — added asyncio.wait_for(timeout=JOB_TIMEOUT_SECONDS)
- MEDIUM: _executor._max_workers private attr → use _CPU_WORKERS variable
- LOW: workers connected to real engines (MultiSymbolBacktestEngine etc.)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Worker pool config ─────────────────────────────────────────────────
_CPU_WORKERS: int = getattr(settings, "BACKTEST_MAX_WORKERS", 4)
_executor: Optional[ProcessPoolExecutor] = None
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()

MAX_JOBS_STORED = 500          # evict oldest when exceeded
JOB_TIMEOUT_SECONDS = 300      # 5 minutes max per job


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=_CPU_WORKERS)
        logger.info("BacktestEngine: ProcessPoolExecutor started (%d workers)", _CPU_WORKERS)
    return _executor


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _store_job(job_id: str, data: Dict[str, Any]) -> None:
    """Store job with MAX_JOBS_STORED cap."""
    async with _jobs_lock:
        _jobs[job_id] = data
        if len(_jobs) > MAX_JOBS_STORED:
            # evict oldest by insertion order (dict is ordered in Python 3.7+)
            oldest = next(iter(_jobs))
            del _jobs[oldest]
            logger.debug("BacktestEngine: evicted oldest job %s", oldest)


async def _update_job(job_id: str, updates: Dict[str, Any]) -> None:
    async with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)


# ── Process-pool workers (run in separate process) ──────────────────────────

def _run_backtest_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Real backtest via MultiSymbolBacktestEngine."""
    try:
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        from backend.backtest_engine.data_provider import DataProvider

        provider = DataProvider()
        candles = provider.get_candles(
            symbol=params["symbol"],
            timeframe=params["timeframe"],
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
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
    except Exception as exc:
        logger.error("Backtest worker error: %s", exc, exc_info=True)
        return {"error": str(exc), "status": "failed"}


def _run_wfo_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Real Walk-Forward Optimization."""
    try:
        from backend.backtest_engine.walk_forward_advanced import WalkForwardAnalyzer
        from backend.backtest_engine.data_provider import DataProvider

        provider = DataProvider()
        candles = provider.get_candles(
            symbol=params["symbol"],
            timeframe=params["timeframe"],
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        analyzer = WalkForwardAnalyzer(
            in_sample_pct=params.get("in_sample_pct", 0.7),
            n_folds=params.get("n_folds", 5),
        )
        return analyzer.run(
            candles=candles,
            symbol=params["symbol"],
            strategy=params.get("strategy", "smc"),
        )
    except Exception as exc:
        logger.error("WFO worker error: %s", exc, exc_info=True)
        return {"error": str(exc), "status": "failed"}


def _run_mc_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """Real Monte Carlo simulation."""
    try:
        from backend.backtest_engine.monte_carlo import MonteCarloSimulator

        sim = MonteCarloSimulator(
            n_simulations=params.get("n_simulations", 1000),
            confidence_level=params.get("confidence_level", 0.95),
        )
        return sim.run(
            trades=params["trades"],
            initial_balance=params.get("initial_balance", 10_000.0),
        )
    except Exception as exc:
        logger.error("MC worker error: %s", exc, exc_info=True)
        return {"error": str(exc), "status": "failed"}


# ── Request models ─────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_balance: float = Field(10_000.0, gt=0)
    risk_pct: float = Field(1.0, gt=0, le=10)
    strategy: str = "smc"
    parameters: Dict[str, Any] = {}

class WFORequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    in_sample_pct: float = Field(0.7, gt=0, lt=1)
    n_folds: int = Field(5, ge=2, le=20)
    strategy: str = "smc"

class MonteCarloRequest(BaseModel):
    trades: List[float]   # list of P&L values
    n_simulations: int = Field(1000, ge=100, le=100_000)
    confidence_level: float = Field(0.95, gt=0, lt=1)
    initial_balance: float = Field(10_000.0, gt=0)


# ── Helper to submit and await with timeout ────────────────────────────────

async def _submit_job(
    worker_fn,
    params: Dict[str, Any],
    job_type: str,
) -> str:
    """Submit work to ProcessPool, register job, return job_id."""
    job_id = str(uuid.uuid4())
    await _store_job(job_id, {
        "id": job_id,
        "type": job_type,
        "status": "running",
        "created_at": _utcnow(),
        "params": params,
        "result": None,
        "error": None,
    })

    async def _run() -> None:
        loop = asyncio.get_running_loop()  # ✔ Python 3.10+ safe
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(_get_executor(), worker_fn, params),
                timeout=JOB_TIMEOUT_SECONDS,
            )
            error = result.pop("error", None) if isinstance(result, dict) else None
            status = "failed" if error else "completed"
            await _update_job(job_id, {"status": status, "result": result,
                                        "error": error, "completed_at": _utcnow()})
        except asyncio.TimeoutError:
            logger.error("Job %s timed out after %ds", job_id, JOB_TIMEOUT_SECONDS)
            await _update_job(job_id, {
                "status": "timeout",
                "error": f"Job exceeded {JOB_TIMEOUT_SECONDS}s timeout",
                "completed_at": _utcnow(),
            })
        except Exception as exc:  # noqa: BLE001
            logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
            await _update_job(job_id, {
                "status": "failed",
                "error": str(exc),
                "completed_at": _utcnow(),
            })

    asyncio.create_task(_run(), name=f"backtest_{job_id[:8]}")
    return job_id


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Submit a backtest job. Returns job_id for polling."""
    job_id = await _submit_job(_run_backtest_worker, req.dict(), "backtest")
    return {"job_id": job_id, "status": "running",
            "poll_url": f"/api/v1/backtest-engine/status/{job_id}"}


@router.post("/wfo")
async def run_wfo(req: WFORequest):
    """Submit a Walk-Forward Optimization job."""
    job_id = await _submit_job(_run_wfo_worker, req.dict(), "wfo")
    return {"job_id": job_id, "status": "running",
            "poll_url": f"/api/v1/backtest-engine/status/{job_id}"}


@router.post("/monte-carlo")
async def run_monte_carlo(req: MonteCarloRequest):
    """Submit a Monte Carlo simulation job."""
    job_id = await _submit_job(_run_mc_worker, req.dict(), "monte_carlo")
    return {"job_id": job_id, "status": "running",
            "poll_url": f"/api/v1/backtest-engine/status/{job_id}"}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status and result."""
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return job


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List recent backtest jobs."""
    async with _jobs_lock:
        all_jobs = list(_jobs.values())
    recent = sorted(all_jobs, key=lambda j: j.get("created_at", ""), reverse=True)
    return {"jobs": recent[:limit], "total": len(all_jobs)}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel / forget a job."""
    async with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, f"Job {job_id!r} not found")
        _jobs.pop(job_id)
    return {"cancelled": True, "job_id": job_id}


@router.get("/symbols")
async def list_symbols():
    """Return supported symbols and timeframes."""
    return {
        "symbols": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
                    "AUDUSD", "NZDUSD", "USDCAD", "BTCUSD", "ETHUSD",
                    "US30", "US500", "NAS100", "GER40"],
        "timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"],
        "strategies": ["smc", "price_action", "hybrid"],
        "max_workers": _CPU_WORKERS,
        "timeout_seconds": JOB_TIMEOUT_SECONDS,
    }
