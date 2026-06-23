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
