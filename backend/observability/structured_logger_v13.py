from __future__ import annotations
import json, logging, os, re, sys, time, uuid
from contextvars import ContextVar, Token
from typing import Any, Dict, Optional

_request_id: ContextVar[str] = ContextVar('request_id', default='')
_trace_id:   ContextVar[str] = ContextVar('trace_id',   default='')
_user_id:    ContextVar[str] = ContextVar('user_id',    default='')
_symbol:     ContextVar[str] = ContextVar('symbol',     default='')

class RequestContext:
    def __init__(self, request_id='', trace_id='', user_id='', symbol=''):
        self._req_id=request_id or str(uuid.uuid4()); self._trc_id=trace_id; self._usr_id=user_id; self._sym=symbol; self._tokens=[]
    def __enter__(self):
        self._tokens=[_request_id.set(self._req_id),_trace_id.set(self._trc_id),_user_id.set(self._usr_id),_symbol.set(self._sym)]; return self
    def __exit__(self,*_):
        for tok in self._tokens: tok.var.reset(tok)

def set_request_context(request_id='',trace_id='',user_id='',symbol=''):
    _request_id.set(request_id); _trace_id.set(trace_id); _user_id.set(user_id); _symbol.set(symbol)
def clear_request_context(): _request_id.set(''); _trace_id.set(''); _user_id.set(''); _symbol.set('')
def get_request_id() -> str: return _request_id.get()
def get_trace_id()   -> str: return _trace_id.get()
def get_user_id()    -> str: return _user_id.get()

_SENSITIVE_KEYS = frozenset({'password','passwd','secret','token','api_key','apikey','license_key','access_token','refresh_token','private_key','authorization','credit_card','cvv','ssn'})
_REDACTED = '[REDACTED]'

def _redact_value(key, value):
    if isinstance(value, str) and len(value) > 20:
        if re.match(r'^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', value): return '[REDACTED:JWT]'
    if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS: return _REDACTED
    return value
def _redact_dict(d):
    return {k: _redact_dict(v) if isinstance(v,dict) else _redact_value(k,v) for k,v in d.items()}

_SKIP_FIELDS = frozenset({'name','msg','args','created','filename','funcName','levelname','levelno','lineno','module','msecs','pathname','process','processName','relativeCreated','stack_info','thread','threadName','exc_info','exc_text','message','taskName'})

class JSONFormatter(logging.Formatter):
    def format(self, record):
        record.message=record.getMessage()
        payload={'ts':self.formatTime(record,'%Y-%m-%dT%H:%M:%S'),'level':record.levelname,'logger':record.name,'msg':record.message,'request_id':get_request_id(),'trace_id':get_trace_id(),'user_id':get_user_id()}
        if record.exc_info: payload['exc']=self.formatException(record.exc_info)
        for k,v in record.__dict__.items():
            if k not in _SKIP_FIELDS and not k.startswith('_'):
                try: redacted=_redact_value(k,v); json.dumps(redacted); payload[k]=redacted
                except: payload[k]=str(v)
        try: return json.dumps(payload,ensure_ascii=False)
        except: return json.dumps({'level':'ERROR','msg':'log serialization failed'})

class HumanFormatter(logging.Formatter):
    def __init__(self): super().__init__(fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',datefmt='%Y-%m-%dT%H:%M:%S')

class SamplingFilter(logging.Filter):
    def __init__(self, sample_rate=0.01): super().__init__(); self._rate=sample_rate; self._counter=0
    def filter(self, record):
        if record.levelno>logging.DEBUG: return True
        self._counter+=1; return (self._counter%max(1,int(1/self._rate)))==0

_configured=False
def configure_logging():
    global _configured
    if _configured: return
    _configured=True
    env=os.environ.get('ENVIRONMENT','production').lower()
    log_level=os.environ.get('LOG_LEVEL','INFO').upper()
    level=getattr(logging,log_level,logging.INFO)
    root=logging.getLogger()
    if root.handlers: return
    handler=logging.StreamHandler(sys.stdout)
    if env in ('production','staging'):
        handler.setFormatter(JSONFormatter())
        if env=='production': handler.addFilter(SamplingFilter(sample_rate=0.01))
    else: handler.setFormatter(HumanFormatter())
    root.addHandler(handler); root.setLevel(level)
    for noisy in ('uvicorn.access','httpx','asyncio'): logging.getLogger(noisy).setLevel(logging.WARNING)
configure_logging()

class StructuredLogger:
    def __init__(self, name): self._logger=logging.getLogger(name)
    def _log(self, level, message, **kwargs):
        if not self._logger.isEnabledFor(level): return
        safe_kwargs={k:_redact_value(k,v) for k,v in kwargs.items()}
        self._logger.log(level,message,extra=safe_kwargs,stacklevel=3)
    def debug(self,msg,**kw): self._log(logging.DEBUG,msg,**kw)
    def info(self,msg,**kw): self._log(logging.INFO,msg,**kw)
    def warning(self,msg,**kw): self._log(logging.WARNING,msg,**kw)
    def error(self,msg,**kw): self._log(logging.ERROR,msg,**kw)
    def critical(self,msg,**kw): self._log(logging.CRITICAL,msg,**kw)
    def bind(self,**kwargs): child=StructuredLogger(self._logger.name); child._logger=self._logger; return child
    def exception(self,msg,**kw): self._logger.exception(msg,extra=kw,stacklevel=2)
    def audit(self,action,actor,resource,result,**detail): self._log(logging.INFO,f'AUDIT {action}',action=action,actor=actor,resource=resource,result=result,**detail)

def get_logger(name): return StructuredLogger(name)
