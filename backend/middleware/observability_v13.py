from __future__ import annotations
import logging, re, time, uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from backend.observability.structured_logger_v13 import RequestContext, set_request_context, clear_request_context

logger=logging.getLogger(__name__)
_SLOW_REQUEST_THRESHOLD_S=2.0
_UUID_RE=re.compile(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',re.IGNORECASE)
_ID_RE=re.compile(r'/\d+')

_REQUEST_COUNT=None; _REQUEST_LATENCY=None; _ERROR_COUNT_5XX=None; _HAS_PROMETHEUS=False
try:
    from prometheus_client import Counter, Histogram, REGISTRY
    def _goc(cls,name,desc,labels,**kw):
        try: return cls(name,desc,labels,**kw)
        except ValueError: return REGISTRY._names_to_collectors.get(name)
    _REQUEST_COUNT=_goc(Counter,'gv_http_requests_total','HTTP requests total',['method','path','status'])
    _REQUEST_LATENCY=_goc(Histogram,'gv_http_request_duration_seconds','HTTP request latency',['method','path'],buckets=(0.01,0.05,0.1,0.25,0.5,1.0,2.0,5.0,10.0))
    _ERROR_COUNT_5XX=_goc(Counter,'gv_http_5xx_total','HTTP 5xx errors',['method','path'])
    _HAS_PROMETHEUS=True
except ImportError: pass

def _normalise_path(path):
    path=_UUID_RE.sub('/{uuid}',path); path=_ID_RE.sub('/{id}',path); return path

class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self,app: ASGIApp): super().__init__(app)
    async def dispatch(self,request: Request,call_next: Callable) -> Response:
        cid=request.headers.get('X-Request-ID') or str(uuid.uuid4())
        with RequestContext(request_id=cid):
            set_request_context(request_id=cid)
            start=time.perf_counter(); status_code=500
            try:
                response: Response=await call_next(request)
                status_code=response.status_code
                response.headers['X-Request-ID']=cid
                response.headers['X-Response-Time']=f'{(time.perf_counter()-start)*1000:.1f}ms'
            except Exception as exc: logger.error('Unhandled exception: %s',exc,exc_info=True); raise
            finally:
                elapsed=time.perf_counter()-start; normalised=_normalise_path(request.url.path)
                if _HAS_PROMETHEUS:
                    try:
                        _REQUEST_COUNT.labels(method=request.method,path=normalised,status=str(status_code)).inc()
                        _REQUEST_LATENCY.labels(method=request.method,path=normalised).observe(elapsed)
                        if status_code>=500: _ERROR_COUNT_5XX.labels(method=request.method,path=normalised).inc()
                    except Exception: pass
                logger.info('HTTP %s %s -> %s (%.0fms)',request.method,normalised,status_code,elapsed*1000,extra={'request_id':cid,'method':request.method,'path':normalised,'status':status_code,'elapsed_ms':round(elapsed*1000,1)})
                if elapsed>=_SLOW_REQUEST_THRESHOLD_S:
                    try:
                        from backend.observability.alert_manager_v13 import alert_manager
                        await alert_manager.fire('slow_request',context={'path':normalised,'elapsed_s':round(elapsed,2),'request_id':cid})
                    except Exception: pass
                clear_request_context()
        return response
