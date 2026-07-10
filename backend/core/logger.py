from __future__ import annotations
import json, logging, os, sys, time
from typing import Any, Dict, Optional

_LOG_LEVEL_MAP: Dict[str, int] = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
_DEFAULT_LEVEL = 'INFO'
_FMT_HUMAN = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
_FMT_DATE  = '%Y-%m-%dT%H:%M:%S'

class _JSONFormatter(logging.Formatter):
    _SKIP = frozenset({'name','msg','args','created','filename','funcName','levelname','levelno','lineno','module','msecs','pathname','process','processName','relativeCreated','stack_info','thread','threadName','exc_info','exc_text','message'})
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: Dict[str, Any] = {'ts': self.formatTime(record, _FMT_DATE), 'level': record.levelname, 'logger': record.name, 'msg': record.message}
        if record.exc_info: payload['exc'] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k not in self._SKIP and not k.startswith('_'):
                try: json.dumps(v); payload[k] = v
                except (TypeError, ValueError): payload[k] = str(v)
        try: return json.dumps(payload, ensure_ascii=False)
        except Exception: return json.dumps({'level': 'ERROR', 'msg': 'log serialization failed'})

class ContextualLogger:
    def __init__(self, logger: logging.Logger, **context: Any) -> None:
        self._logger = logger; self._context = context
    def bind(self, **kwargs: Any) -> 'ContextualLogger':
        return ContextualLogger(self._logger, **{**self._context, **kwargs})
    def _emit(self, level: int, msg: str, **kwargs: Any) -> None:
        if not self._logger.isEnabledFor(level): return
        self._logger.log(level, msg, extra={**self._context, **kwargs}, stacklevel=3)
    def debug(self, msg: str, **kwargs: Any) -> None: self._emit(logging.DEBUG, msg, **kwargs)
    def info(self, msg: str, **kwargs: Any) -> None: self._emit(logging.INFO, msg, **kwargs)
    def warning(self, msg: str, **kwargs: Any) -> None: self._emit(logging.WARNING, msg, **kwargs)
    def error(self, msg: str, **kwargs: Any) -> None: self._emit(logging.ERROR, msg, **kwargs)
    def critical(self, msg: str, **kwargs: Any) -> None: self._emit(logging.CRITICAL, msg, **kwargs)
    def exception(self, msg: str, **kwargs: Any) -> None: self._logger.exception(msg, extra={**self._context, **kwargs}, stacklevel=2)

class AuditLogger:
    def __init__(self) -> None: self._log = logging.getLogger('audit')
    def record(self, action: str, actor: str, resource: str, result: str, *, detail: Optional[Dict[str, Any]] = None) -> None:
        self._log.info('AUDIT', extra={'audit': True, 'action': action, 'actor': actor, 'resource': resource, 'result': result, 'epoch': time.time(), **(({'detail': detail}) if detail else {})})

_configured = False
def _configure_root() -> None:
    global _configured
    if _configured: return
    _configured = True
    env = os.environ.get('ENVIRONMENT', 'production').lower()
    level = _LOG_LEVEL_MAP.get(os.environ.get('LOG_LEVEL', _DEFAULT_LEVEL).upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers: return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT_HUMAN, datefmt=_FMT_DATE) if env == 'development' else _JSONFormatter())
    root.setLevel(level); root.addHandler(handler)
    for name in ('httpcore', 'httpx', 'asyncio', 'urllib3'): logging.getLogger(name).setLevel(logging.WARNING)

def get_logger(name: str) -> ContextualLogger:
    _configure_root()
    return ContextualLogger(logging.getLogger(name))

def setup_logger(name: str = "app", level: Optional[str] = None) -> ContextualLogger:
    if level:
        lvl = _LOG_LEVEL_MAP.get(level.upper(), logging.INFO)
        logging.getLogger().setLevel(lvl)
    _configure_root()
    return get_logger(name)

_audit_logger: Optional[AuditLogger] = None
def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None: _configure_root(); _audit_logger = AuditLogger()
    return _audit_logger
