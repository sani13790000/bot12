from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from fastapi import APIRouter
from ..core.logger import get_logger
logger = get_logger('api.health')
router = APIRouter(tags=['health'])

class HealthStatus(str, Enum):
    HEALTHY   = 'healthy'
    DEGRADED  = 'degraded'
    UNHEALTHY = 'unhealthy'

@dataclass
class ComponentHealth:
    name: str; status: HealthStatus; latency_ms: float
    detail: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {'status': self.status.value, 'latency_ms': round(self.latency_ms, 2)}
        if self.detail: d['detail'] = self.detail
        if self.error:  d['error']  = self.error
        return d

@dataclass
class SystemHealth:
    status: HealthStatus; version: str; uptime_s: float
    components: List[ComponentHealth] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {'status': self.status.value, 'version': self.version, 'uptime_s': round(self.uptime_s, 1), 'components': {c.name: c.to_dict() for c in self.components}}

async def _check(name: str, fn: Callable[[], Coroutine[Any, Any, Dict[str, Any]]], critical: bool = True) -> ComponentHealth:
    t0 = time.monotonic()
    try:
        detail = await asyncio.wait_for(fn(), timeout=5.0)
        status = HealthStatus.HEALTHY; error = None
    except asyncio.TimeoutError:
        detail = {}; status = HealthStatus.UNHEALTHY if critical else HealthStatus.DEGRADED; error = 'timeout after 5s'
    except Exception as exc:
        detail = {}; status = HealthStatus.UNHEALTHY if critical else HealthStatus.DEGRADED; error = str(exc)[:200]
    return ComponentHealth(name=name, status=status, latency_ms=(time.monotonic()-t0)*1000, detail=detail, error=error)

async def _check_database() -> Dict[str, Any]:
    from ..database.connection import get_db
    async for db in get_db(): await db.execute('SELECT 1'); return {'ok': True}
    return {'ok': False}

async def _check_redis() -> Dict[str, Any]:
    try:
        import redis.asyncio as aioredis
        from ..core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping(); await r.aclose(); return {'ok': True}
    except Exception as exc: raise RuntimeError(f'Redis ping failed: {exc}') from exc

async def _check_mt5() -> Dict[str, Any]:
    try:
        from ..execution.mt5_connector import mt5_connector
        ok = await asyncio.wait_for(mt5_connector.health_check(), timeout=3.0)
        return {'connected': ok}
    except Exception as exc: raise RuntimeError(f'MT5: {exc}') from exc

async def _check_risk() -> Dict[str, Any]:
    try:
        from ..risk.risk_orchestrator import get_risk_orchestrator
        orch = await get_risk_orchestrator()
        return {'gates': list(orch._gates.keys()) if hasattr(orch, '_gates') else []}
    except Exception as exc: raise RuntimeError(f'Risk: {exc}') from exc

async def _check_equity() -> Dict[str, Any]:
    try:
        from ..risk.equity_protection import get_equity_protection
        ep = get_equity_protection()
        snap = ep.snapshot() if hasattr(ep, 'snapshot') else {}
        return {'initialized': ep.is_initialized, **snap}
    except Exception as exc: raise RuntimeError(f'Equity: {exc}') from exc

async def _check_circuit_breaker() -> Dict[str, Any]:
    try:
        from ..circuit_breaker import get_mt5_breaker
        cb = get_mt5_breaker()
        return cb.snapshot() if hasattr(cb, 'snapshot') else {}
    except Exception as exc: raise RuntimeError(f'CB: {exc}') from exc

async def _check_scheduler() -> Dict[str, Any]:
    try:
        from ..services.scheduler import get_scheduler
        s = get_scheduler()
        return s.health() if hasattr(s, 'health') else {}
    except Exception as exc: raise RuntimeError(f'Scheduler: {exc}') from exc

_STARTED_AT = time.time()
def _uptime() -> float: return time.time() - _STARTED_AT
def _version() -> str:
    try: from ..core.config import settings; return settings.APP_VERSION
    except Exception: return 'unknown'

@router.get('/health', summary='Liveness probe')
async def liveness() -> Dict[str, Any]:
    return {'status': 'ok', 'uptime_s': round(_uptime(), 1), 'version': _version()}

@router.get('/health/ready', summary='Readiness probe')
async def readiness() -> Dict[str, Any]:
    from fastapi.responses import JSONResponse
    checks = await asyncio.gather(_check('database', _check_database, critical=True), _check('risk_engine', _check_risk, critical=True), return_exceptions=False)
    failed = [c for c in checks if c.status == HealthStatus.UNHEALTHY]
    overall = HealthStatus.HEALTHY if not failed else HealthStatus.UNHEALTHY
    return JSONResponse(content={'status': overall.value, 'uptime_s': round(_uptime(), 1), 'checks': {c.name: c.to_dict() for c in checks}}, status_code=200 if overall == HealthStatus.HEALTHY else 503)

@router.get('/health/deep', summary='Full system health')
async def deep_health() -> Dict[str, Any]:
    checks = await asyncio.gather(
        _check('database',          _check_database,       critical=True),
        _check('redis',             _check_redis,          critical=False),
        _check('mt5',               _check_mt5,            critical=True),
        _check('risk_engine',       _check_risk,           critical=True),
        _check('equity_protection', _check_equity,         critical=True),
        _check('circuit_breaker',   _check_circuit_breaker,critical=False),
        _check('scheduler',         _check_scheduler,      critical=False),
        return_exceptions=False,
    )
    critical = [c for c in checks if c.status == HealthStatus.UNHEALTHY]
    degraded = [c for c in checks if c.status == HealthStatus.DEGRADED]
    overall  = HealthStatus.UNHEALTHY if critical else (HealthStatus.DEGRADED if degraded else HealthStatus.HEALTHY)
    logger.info('Deep health', status=overall.value, unhealthy=[c.name for c in critical], degraded=[c.name for c in degraded])
    try:
        from ..observability.metrics import metrics_registry
        metrics_registry.gauge('system_health', 0.0 if critical else (0.5 if degraded else 1.0))
    except Exception: pass
    return SystemHealth(status=overall, version=_version(), uptime_s=_uptime(), components=list(checks)).to_dict()
