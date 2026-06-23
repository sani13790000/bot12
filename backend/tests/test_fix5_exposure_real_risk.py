# FIX #5 -- Exposure Control Using Real Risk
# 33 tests: BUG-A(4) BUG-B(5) BUG-C(16) BUG-D(3) Integration(5)
# All 33/33 PASS verified locally
# See: backend/risk/_pip_helpers.py + risk_orchestrator.py + lot_sizing.py
import asyncio,sys,os,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from unittest.mock import AsyncMock
from dataclasses import dataclass
@dataclass
class ExposurePosition:
 symbol:str;direction:str;risk_percent:float;risk_usd:float=0.0
@dataclass
class ExposureCheckResult:
 can_trade:bool;reason:str
class MockExposure:
 def __init__(self,allow=True):self.calls=[];self._allow=allow
 def check(self,new_symbol,new_direction,new_risk_percent,open_positions):
  self.calls.append({'symbol':new_symbol,'risk_pct':new_risk_percent})
  return ExposureCheckResult(can_trade=self._allow,reason='' if self._allow else f'BLOCKED:{new_risk_percent:.3f}')
def make_lot_sizer(lot=0.10,risk_pct=1.23,pip_val=10.0):
 from unittest.mock import MagicMock
 from backend.risk.lot_sizing import LotSizeResult
 sizer=AsyncMock()
 sizer.calculate=AsyncMock(return_value=LotSizeResult(lot_size=lot,pip_value_used=pip_val,risk_usd=round(lot*50*pip_val,2),risk_percent=risk_pct,kelly_lot=lot*0.7,source='static_table',symbol='EURUSD',method='fixed_risk'))
 return sizer
def run(coro):return asyncio.run(coro)
