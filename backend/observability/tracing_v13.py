from __future__ import annotations
import asyncio, contextlib, time, uuid
from collections import deque
from contextvars import ContextVar
from typing import Any, AsyncIterator, Deque, Dict, Iterator, List, Optional

_trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_span_id_var:  ContextVar[Optional[str]] = ContextVar('span_id',  default=None)
_MAX_SPANS = 1_000
_STALE_TTL_S = 60.0

def new_trace_id() -> str:
    tid = str(uuid.uuid4()); _trace_id_var.set(tid); return tid
def get_trace_id() -> Optional[str]: return _trace_id_var.get()

class Timer:
    def __init__(self): self._start=0.0; self.elapsed=0.0
    def __enter__(self): self._start=time.perf_counter(); return self
    def __exit__(self,*_): self.elapsed=time.perf_counter()-self._start

class Span:
    def __init__(self, name: str, trace_id: Optional[str]=None, parent_id: Optional[str]=None):
        self.span_id=str(uuid.uuid4())[:8]; self.trace_id=trace_id or get_trace_id() or new_trace_id()
        self.parent_id=parent_id or _span_id_var.get(); self.name=name
        self.start_time=time.perf_counter(); self.wall_time=time.time()
        self.end_time: Optional[float]=None; self.duration_ms=0.0
        self.tags: Dict[str,Any]={}; self.error: Optional[str]=None
    def set_tag(self,key,value): self.tags[key]=value; return self
    def finish(self, error=None):
        self.end_time=time.perf_counter(); self.duration_ms=round((self.end_time-self.start_time)*1000,2); self.error=error; return self
    def to_dict(self):
        return {'span_id':self.span_id,'trace_id':self.trace_id,'parent_id':self.parent_id,'name':self.name,'duration_ms':self.duration_ms,'error':self.error,'tags':self.tags,'finished':self.end_time is not None,'wall_time':self.wall_time}

class Tracer:
    def __init__(self, max_spans=_MAX_SPANS):
        self._spans: Deque[Span]=deque(maxlen=max_spans); self._active: Dict[str,Span]={}
    def start_span(self, name, parent_id=None):
        self._gc_stale(); span=Span(name,parent_id=parent_id); self._active[span.span_id]=span; _span_id_var.set(span.span_id); return span
    def finish_span(self, span, error=None):
        span.finish(error=error); self._active.pop(span.span_id,None); self._spans.append(span)
    @contextlib.contextmanager
    def span(self, name, **tags) -> Iterator[Span]:
        s=self.start_span(name)
        for k,v in tags.items(): s.set_tag(k,v)
        try: yield s; self.finish_span(s)
        except Exception as exc: self.finish_span(s,error=str(exc)); raise
    @contextlib.asynccontextmanager
    async def async_span(self, name, **tags) -> AsyncIterator[Span]:
        s=self.start_span(name)
        for k,v in tags.items(): s.set_tag(k,v)
        try: yield s; self.finish_span(s)
        except Exception as exc: self.finish_span(s,error=str(exc)); raise
    def _gc_stale(self):
        now=time.perf_counter()
        stale=[sid for sid,sp in self._active.items() if now-sp.start_time>_STALE_TTL_S]
        for sid in stale:
            sp=self._active.pop(sid); sp.finish(error='stale_gc'); self._spans.append(sp)
    def get_recent_spans(self, limit=100):
        items=list(self._spans); items.reverse(); return [s.to_dict() for s in items[:limit]]
    def get_active_spans(self):
        self._gc_stale(); return [s.to_dict() for s in self._active.values()]
    def get_slow_spans(self, threshold_ms=500.0):
        return [s.to_dict() for s in reversed(list(self._spans)) if s.duration_ms>=threshold_ms]
    def summary(self):
        spans=list(self._spans)
        if not spans: return {'total':0,'errors':0,'avg_duration_ms':0.0,'max_duration_ms':0.0,'active':0}
        durations=[s.duration_ms for s in spans if s.end_time is not None]
        errors=sum(1 for s in spans if s.error and s.error!='stale_gc')
        return {'total':len(spans),'errors':errors,'avg_duration_ms':round(sum(durations)/len(durations),2) if durations else 0.0,'max_duration_ms':max(durations,default=0.0),'active':len(self._active)}
    def clear(self): self._spans.clear(); self._active.clear()

tracer = Tracer()
