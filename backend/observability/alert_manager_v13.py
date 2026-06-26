from __future__ import annotations
import asyncio, logging, os, time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)
_MAX_HISTORY=500; _DEDUP_WINDOW_S=300; _RATE_LIMIT_N=10; _RATE_LIMIT_WIN_S=60

class AlertLevel(str, Enum):
    INFO='INFO'; WARNING='WARNING'; CRITICAL='CRITICAL'

@dataclass
class AlertRule:
    name: str; description: str
    level: AlertLevel=AlertLevel.WARNING; enabled: bool=True
    metadata: Dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return {'name':self.name,'description':self.description,'level':self.level,'enabled':self.enabled}

_DEFAULT_RULES = [
    AlertRule('high_drawdown','Equity drawdown > 10%',AlertLevel.CRITICAL),
    AlertRule('daily_loss_limit','Daily loss limit reached',AlertLevel.CRITICAL),
    AlertRule('db_unhealthy','Database not reachable',AlertLevel.CRITICAL),
    AlertRule('circuit_open','Circuit breaker opened',AlertLevel.WARNING),
    AlertRule('slow_request','Request > 2s',AlertLevel.WARNING),
    AlertRule('ml_drift','ML model drift detected',AlertLevel.WARNING),
    AlertRule('kill_switch','Kill switch activated',AlertLevel.CRITICAL),
    AlertRule('test','Manual test alert',AlertLevel.INFO),
]

AlertCallback = Callable[[str, AlertLevel, Optional[Dict[str,Any]]], Coroutine]

class AlertManager:
    def __init__(self):
        self._token=os.environ.get('TELEGRAM_BOT_TOKEN'); self._chat_id=os.environ.get('TELEGRAM_CHAT_ID')
        self._webhook=os.environ.get('ALERT_WEBHOOK_URL')
        self._history: Deque[Dict[str,Any]]=deque(maxlen=_MAX_HISTORY)
        self._rules: Dict[str,AlertRule]={r.name:r for r in _DEFAULT_RULES}
        self._dedup: Dict[str,float]={}; self._rate_win: Deque[float]=deque()
        self._callbacks: List[AlertCallback]=[]
    def add_callback(self, cb): self._callbacks.append(cb)
    def remove_callback(self, cb): self._callbacks=[c for c in self._callbacks if c is not cb]
    async def send(self, message, level=AlertLevel.INFO, context=None, dedup_key=None):
        if dedup_key:
            last=self._dedup.get(dedup_key,0.0)
            if time.time()-last<_DEDUP_WINDOW_S: logger.debug('Alert deduped: %s',dedup_key); return False
            self._dedup[dedup_key]=time.time()
        now=time.time()
        self._rate_win=deque(ts for ts in self._rate_win if now-ts<_RATE_LIMIT_WIN_S)
        if len(self._rate_win)>=_RATE_LIMIT_N: logger.warning('Alert rate limit: %s',message[:80]); return False
        self._rate_win.append(now)
        log_fn={AlertLevel.INFO:logger.info,AlertLevel.WARNING:logger.warning,AlertLevel.CRITICAL:logger.critical}.get(level,logger.info)
        log_fn('[ALERT][%s] %s | ctx=%s',level,message,context)
        entry={'level':level,'message':message,'context':context or {},'ts':datetime.now(timezone.utc).isoformat()}
        self._history.append(entry)
        for cb in list(self._callbacks):
            try: await cb(message,level,context)
            except Exception as e: logger.debug('Alert callback error: %s',e)
        if level in (AlertLevel.CRITICAL,AlertLevel.WARNING):
            tasks=[]
            if self._token and self._chat_id: tasks.append(self._send_telegram(message,level))
            if self._webhook: tasks.append(self._send_webhook(message,level,context))
            if tasks: await asyncio.gather(*tasks,return_exceptions=True)
        return True
    async def fire(self, rule_name, context=None):
        rule=self._rules.get(rule_name)
        if rule is None: logger.warning("Alert rule '%s' not found",rule_name); return False
        if not rule.enabled: return False
        return await self.send(message=f'[{rule_name}] {rule.description}',level=rule.level,context=context,dedup_key=rule_name)
    def get_history(self, limit=50):
        items=list(self._history); items.reverse(); return items[:limit]
    def get_rules(self): return [r.to_dict() for r in self._rules.values()]
    def add_rule(self, rule): self._rules[rule.name]=rule
    async def _send_telegram(self, message, level):
        import urllib.parse, urllib.request
        emoji={'INFO':'i','WARNING':'W','CRITICAL':'CRIT'}.get(level.value,'')
        text=f'{emoji} [{level.value}] {message}'
        url=f'https://api.telegram.org/bot{self._token}/sendMessage'
        data=urllib.parse.urlencode({'chat_id':self._chat_id,'text':text,'parse_mode':'HTML'}).encode()
        try:
            req=urllib.request.Request(url,data=data,method='POST')
            loop=asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None,lambda:urllib.request.urlopen(req,timeout=5)),timeout=6.0)
        except Exception as exc: logger.warning('Telegram alert failed: %s',exc)
    async def _send_webhook(self, message, level, context):
        try:
            import json, urllib.request
            payload=json.dumps({'level':level.value,'message':message,'context':context or {},'ts':datetime.now(timezone.utc).isoformat()}).encode()
            req=urllib.request.Request(self._webhook,data=payload,method='POST',headers={'Content-Type':'application/json'})
            loop=asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None,lambda:urllib.request.urlopen(req,timeout=5)),timeout=6.0)
        except Exception as exc: logger.warning('Webhook alert failed: %s',exc)

alert_manager = AlertManager()
