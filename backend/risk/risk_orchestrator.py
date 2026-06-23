from __future__ import annotations
import asyncio,logging
from dataclasses import dataclass,field
from enum import Enum
from typing import Any,Dict,List,Optional
from backend.risk._pip_helpers import _price_to_pips,_estimate_risk_pct
logger=logging.getLogger('risk.orchestrator')
class RiskDecision(str,Enum):APPROVED='APPROVED';BLOCKED='BLOCKED';WARNING='WARNING'
@dataclass
class RiskCheckResult:
 decision:RiskDecision;approved:bool;block_reason:str
 risk_percent:float;lot_size:float;lot_multiplier:float
 gates_passed:List[str]=field(default_factory=list)
 gates_failed:List[str]=field(default_factory=list)
 metadata:Dict[str,Any]=field(default_factory=dict)
class RiskOrchestrator:
 def __init__(self,equity_guard=None,daily_limits=None,volatility_filter=None,
              correlation_filter=None,exposure_control=None,lot_sizer=None,
              fail_mode_correlation='FAIL_CLOSED',fail_mode_exposure='FAIL_CLOSED'):
  self._equity=equity_guard;self._daily=daily_limits
  self._volatility=volatility_filter;self._correlation=correlation_filter
  self._exposure=exposure_control;self._lot_sizer=lot_sizer
  self._fail_corr=fail_mode_correlation;self._fail_exp=fail_mode_exposure
 async def _run_equity_gate(self,u,b,ctx):
  r=self._equity
  if hasattr(r,'check'):
   res=r.check(user_id=u,account_balance=b,**ctx)
   if hasattr(res,'__await__'):res=await res
   return{'can_trade':getattr(res,'can_trade',True),'reason':getattr(res,'reason','')}
  return{'can_trade':True,'reason':''}
 async def _run_daily_gate(self,u,ctx):
  r=self._daily
  if hasattr(r,'check'):
   res=r.check(user_id=u)
   if hasattr(res,'__await__'):res=await res
   return{'can_trade':getattr(res,'can_trade',True),'reason':getattr(res,'reason','')}
  return{'can_trade':True,'reason':''}
