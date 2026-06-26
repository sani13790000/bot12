from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

router = APIRouter(tags=['health'])
_STARTED_AT: float = time.time()
_READY: bool = False

def mark_ready() -> None:
    global _READY; _READY = True

class HealthStatus(str, Enum):
    HEALTHY='healthy'; DEGRADED='degraded'; UNHEALTHY='unhealthy'

@dataclass
class ComponentHealth:
    name: str; status: HealthStatus; latency_ms: float
    detail: Dict[str,Any]=field(default_factory=dict); error: Optional[str]=None
    def to_dict(self):
        d={'status':self.status.value,'latency_ms':round(self.latency_ms,2)}
        if self.detail: d['detail']=self.detail
        if self.error: d['error']=self.error
        return d

@dataclass
class SystemHealth:
    status: HealthStatus; version: str; uptime_s: float; ready: bool
    components: List[ComponentHealth]=field(default_factory=list)
    def to_dict(self):
        return {'status':self.status.value,'version':self.version,'uptime_s':round(self.uptime_s,1),'ready':self.ready,'components':{c.name:c.to_dict() for c in self.components}}
    @property
    def http_status(self) -> int:
        return 503 if self.status==HealthStatus.UNHEALTHY else 200

async def _run_check(name, fn, critical=True, timeout=5.0):
    t0=time.monotonic()
    try:
        detail=await asyncio.wait_for(fn(),timeout=timeout); status=HealthStatus.HEALTHY; error=None
    except asyncio.TimeoutError:
        detail={}; status=HealthStatus.UNHEALTHY if critical else HealthStatus.DEGRADED; error=f'timeout after {timeout}s'
    except Exception as exc:
        detail={}; status=HealthStatus.UNHEALTHY if critical else HealthStatus.DEGRADED; error=str(exc)[:200]
    return ComponentHealth(name=name,status=status,latency_ms=(time.monotonic()-t0)*1000,detail=detail,error=error)

async def _check_database():
    try:
        from ..database.connection import get_db
        async for db in get_db(): await db.execute('SELECT 1'); return {'ok':True}
    except Exception as exc: raise RuntimeError(f'DB: {exc}') from exc
    return {'ok':False}

async def _check_redis():
    try:
        import redis.asyncio as aioredis
        from ..core.config import settings
        r=aioredis.from_url(settings.REDIS_URL,socket_connect_timeout=2)
        await r.ping(); await r.aclose(); return {'ok':True}
    except Exception as exc: raise RuntimeError(f'Redis: {exc}') from exc

async def _check_mt5():
    try:
        from ..execution.mt5_connector import mt5_connector
        ok=await asyncio.wait_for(mt5_connector.health_check(),timeout=3.0); return {'connected':ok}
    except Exception as exc: raise RuntimeError(f'MT5: {exc}') from exc

async def _check_risk():
    try:
        from ..risk.risk_orchestrator import get_risk_orchestrator
        orch=await get_risk_orchestrator()
        gates=list(orch._gates.keys()) if hasattr(orch,'_gates') else []
        return {'gates':gates,'count':len(gates)}
    except Exception as exc: raise RuntimeError(f'Risk: {exc}') from exc

async def _check_equity():
    try:
        from ..risk.equity_protection import get_equity_protection
        ep=get_equity_protection()
        snap=ep.snapshot() if hasattr(ep,'snapshot') else {}
        return {'initialized':ep.is_initialized,**snap}
    except Exception as exc: raise RuntimeError(f'Equity: {exc}') from exc

async def _check_circuit_breaker():
    try:
        from ..circuit_breaker import circuit_breaker
        return {'state':circuit_breaker.state,'failures':circuit_breaker.failure_count}
    except Exception as exc: raise RuntimeError(f'CB: {exc}') from exc

async def _check_metrics():
    try:
        from .metrics_v13 import metrics_registry
        snap=metrics_registry.snapshot()
        return {'uptime_s':snap['uptime_s'],'counters':len(snap['counters'])}
    except Exception as exc: raise RuntimeError(f'Metrics: {exc}') from exc

def _version():
    try:
        from ..core.config import settings; return getattr(settings,'APP_VERSION','unknown')
    except Exception: return 'unknown'

def _uptime(): return time.time()-_STARTED_AT

def _aggregate(components):
    statuses={c.status for c in components}
    if HealthStatus.UNHEALTHY in statuses: return HealthStatus.UNHEALTHY
    if HealthStatus.DEGRADED in statuses: return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY

@router.get('/health/live')
async def liveness():
    return {'status':'ok','uptime_s':round(_uptime(),1)}

@router.get('/health/ready')
async def readiness():
    if not _READY:
        return JSONResponse(status_code=503,content={'status':'starting','ready':False,'message':'application is still initializing'})
    checks=[_run_check('database',_check_database,critical=True,timeout=3.0),_run_check('metrics',_check_metrics,critical=False,timeout=2.0)]
    results=await asyncio.gather(*checks,return_exceptions=False)
    status=_aggregate(results)
    sh=SystemHealth(status=status,version=_version(),uptime_s=_uptime(),ready=True,components=results)
    return JSONResponse(status_code=sh.http_status,content=sh.to_dict())

@router.get('/health')
async def health():
    checks=[_run_check('database',_check_database,critical=True,timeout=5.0),_run_check('redis',_check_redis,critical=False,timeout=3.0),_run_check('mt5',_check_mt5,critical=False,timeout=4.0),_run_check('risk',_check_risk,critical=True,timeout=3.0),_run_check('equity',_check_equity,critical=True,timeout=3.0),_run_check('metrics',_check_metrics,critical=False,timeout=2.0)]
    results=await asyncio.gather(*checks,return_exceptions=False)
    status=_aggregate(results)
    sh=SystemHealth(status=status,version=_version(),uptime_s=_uptime(),ready=_READY,components=results)
    return JSONResponse(status_code=sh.http_status,content=sh.to_dict())

def _require_admin_dep():
    try:
        from ..core.deps_v2 import require_role
        return require_role(['admin','super_admin'])
    except Exception:
        async def _noop() -> dict: return {}
        return _noop

@router.get('/health/deep')
async def deep_health(_admin: dict=Depends(lambda: None)) -> JSONResponse:
    checks=[_run_check('database',_check_database,critical=True,timeout=5.0),_run_check('redis',_check_redis,critical=False,timeout=3.0),_run_check('mt5',_check_mt5,critical=False,timeout=4.0),_run_check('risk',_check_risk,critical=True,timeout=3.0),_run_check('equity',_check_equity,critical=True,timeout=3.0),_run_check('circuit_breaker',_check_circuit_breaker,critical=False,timeout=2.0),_run_check('metrics',_check_metrics,critical=False,timeout=2.0)]
    results=await asyncio.gather(*checks,return_exceptions=False)
    status=_aggregate(results)
    sh=SystemHealth(status=status,version=_version(),uptime_s=_uptime(),ready=_READY,components=results)
    return JSONResponse(status_code=sh.http_status,content=sh.to_dict())
