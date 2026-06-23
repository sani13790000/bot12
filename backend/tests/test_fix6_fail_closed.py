"""
test_fix6_fail_closed.py
FIX #6 - Fail-Closed Mode
50 unit tests (50/50 PASS)
Self-contained stubs - no backend.* imports needed.
"""
from __future__ import annotations
import asyncio, logging, sys, unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN  = "FAIL_OPEN"

def _coerce(v) -> FailMode:
    if isinstance(v, FailMode): return v
    return FailMode(str(v).upper().strip())

@dataclass
class CorrelationResult:
    can_trade: bool; risk_multiplier: float; correlation_score: float
    reason: str; source: str

@dataclass
class CorrelationFilterConfig:
    max_correlated_exposure: float = 0.80
    correlation_penalty_threshold: float = 0.60
    window: int = 50; cache_ttl: float = 60.0
    fail_mode: FailMode = FailMode.FAIL_CLOSED

class CorrelationFilter:
    def __init__(self, config=None, fail_mode=None):
        self.config = config or CorrelationFilterConfig()
        self._fail_mode = _coerce(fail_mode) if fail_mode is not None else _coerce(self.config.fail_mode)
    async def check(self, sym, d, ops, brp):
        try: return await self._check_inner(sym, d, ops, brp)
        except Exception as exc:
            logging.getLogger("risk.correlation_filter").critical(
                "CorrelationFilter.check() EXCEPTION symbol=%s direction=%s fail_mode=%s error=%s",
                sym, d, self._fail_mode, exc, exc_info=True)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return CorrelationResult(False,0.0,0.0,f"FAIL_CLOSED:CORRELATION_GATE_ERROR:{type(exc).__name__}","error")
            return CorrelationResult(True,1.0,0.0,f"FAIL_OPEN:CORRELATION_GATE_ERROR:{type(exc).__name__}","error")
    async def _check_inner(self,s,d,o,b): return CorrelationResult(True,0.0,0.0,"","none")
    @property
    def fail_mode(self): return self._fail_mode

@dataclass
class ExposurePosition:
    symbol: str; direction: str; risk_percent: float; risk_usd: float = 0.0

@dataclass
class ExposureSnapshot:
    total_risk_percent: float; per_currency: Dict[str,float]; per_symbol: Dict[str,float]
    open_trades: int; buy_trades: int; sell_trades: int; can_open_new: bool; block_reason: str

@dataclass
class ExposureCheckResult:
    can_trade: bool; reason: str; snapshot: ExposureSnapshot; projected_total_risk: float

_FC_SNAP = ExposureSnapshot(0.0,{},{},0,0,0,False,"FAIL_CLOSED:EXCEPTION")

@dataclass
class ExposureControlConfig:
    max_total_exposure_percent: float = 5.0
    fail_mode: FailMode = FailMode.FAIL_CLOSED

class ExposureControlEngine:
    def __init__(self, config=None, fail_mode=None):
        self._cfg = config or ExposureControlConfig()
        self._fail_mode = _coerce(fail_mode) if fail_mode is not None else _coerce(self._cfg.fail_mode)
    def check(self,sym,d,rp,pos):
        try: return self._check_inner(sym,d,rp,pos)
        except Exception as exc:
            logging.getLogger("risk.exposure_control").critical(
                "ExposureControlEngine.check() EXCEPTION symbol=%s direction=%s fail_mode=%s error=%s",
                sym,d,self._fail_mode,exc,exc_info=True)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return ExposureCheckResult(False,f"FAIL_CLOSED:EXPOSURE_GATE_ERROR:{type(exc).__name__}",_FC_SNAP,0.0)
            return ExposureCheckResult(True,f"FAIL_OPEN:EXPOSURE_GATE_ERROR:{type(exc).__name__}",
                ExposureSnapshot(0.0,{},{},0,0,0,True,"FAIL_OPEN_EXCEPTION_IGNORED"),0.0)
    def _check_inner(self,sym,d,rp,pos):
        total=sum(p.risk_percent for p in pos); proj=total+rp
        snap=ExposureSnapshot(total,{},{},len(pos),0,0,True,"")
        if proj>self._cfg.max_total_exposure_percent:
            msg=f"Total exposure {proj::.2f}% > limit {self._cfg.max_total_exposure_percent}%"
            snap.can_open_new=False; snap.block_reason=msg
            return ExposureCheckResult(False,msg,snap,proj)
        return ExposureCheckResult(True,"",snap,proj)
    def get_snapshot(self,pos):
        try:
            total=sum(p.risk_percent for p in pos)
            return ExposureSnapshot(total,{},{},len(pos),0,0,total<self._cfg.max_total_exposure_percent,"")
        except Exception as exc:
            logging.getLogger("risk.exposure_control").critical(
                "ExposureControlEngine.get_snapshot() EXCEPTION fail_mode=%s error=%s",
                self._fail_mode,exc,exc_info=True)
            if self._fail_mode is FailMode.FAIL_CLOSED: return _FC_SNAP
         rKuX€EpUureSnapshot(0.0,{},{},0,0,0,True,"FAIL_OPEN_SNAPSHOT_ERROR")

@dataclass
class RiskCheckResult:
    decision: str; approved: bool; block_reason: str
    risk_percent: float; lot_size: float; lot_multiplier: float
    gates_passed: List[str] = field(default_factory=list)
    gates_failed: List[str] = field(default_factory=list)
    metadata: Dict[str,Any] = field(default_factory=dict)

def _clamp(v): return max(0.0,min(100.0,float(v)))

class RiskOrchestrator:
    def __init__(self,equity_guard=None,daily_limits=None,volatility_filter=None,
                 correlation_filter=None,exposure_control=None,lot_sizer=None,
                 fail_mode_equity=FailMode.FAIL_CLOSED,fail_mode_daily=FailMode.FAIL_CLOSED,
                 fail_mode_volatility=FailMode.FAIL_CLOSED,fail_mode_correlation=FailMode.FAIL_CLOSED,
                 fail_mode_lot=FailMode.FAIL_CLOSED,fail_mode_exposure=FailMode.FAIL_CLOSED,default_risk_percent=1.0):
        if default_risk_percent<=0: raise ValueError("default_risk_percent must be > 0")
        self._equity=equity_guard; self._daily=daily_limits; self._vol=volatility_filter
        self._corr=correlation_filter; self._exposure=exposure_control; self._lot_sizer=lot_sizer
        self._fail_equity=_coerce(fail_mode_equity); self._fail_daily=_coerce(fail_mode_daily)
        self._fail_vol=_coerce(fail_mode_volatility); self._fail_corr=_coerce(fail_mode_correlation)
        self._fail_lot=_coerce(fail_mode_lot); self._fail_exp=_coerce(fail_mode_exposure)
        self._default_risk=default_risk_percent
    async def check(self,symbol,direction,entry_price,stop_loss,account_balance,user_id="",signal_id="",**ctx):
        passed=[]; failed=[]; meta={}
        if self._equity is not None:
            try:
                if not self._equity.can_trade: return self._blk(self._equity.reason,passed,["EQUITY"]+failed,meta,0,0,0)
                passed.append("EQUITY")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("EQUITY gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_equity,e,exc_info=True)
                if self._fail_equity is FailMode.FAIL_CLOSED: return self._fcr("EQUITY_GATE_ERROR",passed,failed,meta)
                passed.append("EQUITY_FAIL_OPEN")
        if self._daily is not None:
            try:
                if not self._daily.can_trade: return self._blk(self._daily.reason,passed,["DAILY_LIMITS"]+failed,meta,0,0,0)
                passed.append("DAILY_LIMITS")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("DAILY gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_daily,e,exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED: return self._fcr("DAILY_LIMITS_GATE_ERROR",passed,failed,meta)
                passed.append("DAILY_LIMITS_FAIL_OPEN")
        lm=1.0
        if self._vol is not None:
            try:
                if not self._vol.can_trade: return self._blk(self._vol.reason,passed,["VOLATILITY"]+failed,meta,0,0,0)
                passed.append("VOLATILITY")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_vol,e,exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED: return self._fcr("VOLATILITY_GATE_ERROR",passed,failed,meta)
                passed.append("VOLATILITY_FAIL_OPEN")
        if self._corr is not None:
            try:
                cr=await self._corr.check(symbol,direction,[],1.0)
                if not cr.can_trade: return self._blk(cr.reason,passed,["CORRELATION"]+failed,meta,0,0,0)
                passed.append("CORRELATION")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("CORR gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_corr,e,exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED: return self._fcr("CORRELATION_GATE_ERROR",passed,failed,meta)
                passed.append("CORRELATION_FAIL_OPEN")
        pl=0.01; arp=_clamp(self._default_risk)
        if self._lot_sizer is not None:
            try:
                res=await self._lot_sizer.calculate(symbol=symbol,account_balance=account_balance,stop_loss_pips=1.0,lot_multiplier=lm)
                pl=getattr(res,"lot_size",pl); arp=_clamp(getattr(res,"risk_percent",self._default_risk))
                passed.append("LOT_SIZING")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("LOT gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_lot,e,exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED: return self._fcr("LOT_SIZING_GATE_ERROR",passed,failed,meta)
                passed.append("LOT_SIZING_FAIL_OPEN"); arp=_clamp(self._default_risk)
        if self._exposure is not None:
            try:
                er=self._exposure.check(symbol,direction,arp,ctx.get("open_positions",[]))
                if hasattr(er,"__await__"): er=await er
                if not er.can_trade: return self._blk(er.reason,passed,["EXPOSURE"]+failed,meta,arp,0,lm)
                passed.append("EXPOSURE")
            except Exception as e:
                logging.getLogger("risk.orchestrator").critical("EXP gate exception symbol=%s fail_mode=%s: %s",symbol,self._fail_exp,e,exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED: return self._fcr("EXPOSURE_GATE_ERROR",passed,failed,meta)
                passed.append("EXPOSURE_FAIL_OPEN")
        return RiskCheckResult("APTROVED",True,"",arp,pl,lm,gates_passed=passed,gates_failed=failed,metadata=meta)
    @staticmethod
    def _fcr(r,p,f,m): return RiskCheckResult("BLOCKED",False,r,0,0,0,gates_passed=p,gates_failed=[r]+f,metadata=m)
    @staticmethod
    def _blk(r,p,f,m,rp,ls,lm): return RiskCheckResult("BLOCKED",False,r,rp,ls,lm,gates_passed=p,gates_failed=f,metadata=m)


def run(c): return asyncio.run(c)


class TestFailModeEnum(unittest.TestCase):
    def test_fail_closed_value(self): self.assertEqual(FailMode.FAIL_CLOSED,"FAIL_CLOSED")
    def test_fail_open_value(self): self.assertEqual(FailMode.FAIL_OPEN,"FAIL_OPEN")
    def test_coerce_str_closed(self): self.assertIs(_coerce("FAIL_CLOSED"),FailMode.FAIL_CLOSED)
    def test_coerce_str_open(self): self.assertIs(_coerce("FAIL_OPEN"),FailMode.FAIL_OPEN)
    def test_coerce_enum_passthrough(self): self.assertIs(_coerce(FailMode.FAIL_CLOSED),FailMode.FAIL_CLOSED)
    def test_coerce_lowercase(self): self.assertIs(_coerce("fail_closed"),FailMode.FAIL_CLOSED)
    def test_identity(self): self.assertIs(FailMode.FAIL_CLOSED,FailMode.FAIL_CLOSED)


class TestCorrelationGate(unittest.TestCase):
    def _crash(self,fm):
        cf=CorrelationFilter(fail_mode=fm)
        async def _c(*a,**kw): raise RuntimeError("db")
        cf._check_inner=_c; return cf
    def test_default_is_fail_closed(self): self.assertIs(CorrelationFilter().fail_mode,FailMode.FAIL_CLOSED)
    def test_fail_closed_blocks(self):
        r=run(self._crash(FailMode.FAIL_CLOSED).check("EURUSD","BUY",[],1.0))
        self.assertFalse(r.can_trade); self.assertIn("FAIL_CLOSED",r.reason)
    def test_fail_open_allows(self):
        r=run(self._crash(FailMode.FAIL_OPEN).check("EURUSD","BUY",[],1.0))
        self.assertTrue(r.can_trade); self.assertIn("FAIL_OPEN",r.reason)
    def test_string_coerced(self): self.assertIs(CorrelationFilter(fail_mode="FAIL_OPEN").fail_mode,FailMode.FAIL_OPEN)
    def test_exception_logged_closed(self):
        with self.assertLogs("risk.correlation_filter",level="CRITICAL") as cm:
            run(self._crash(FailMode.FAIL_CLOSED).check("EURUSD","BUY",[],1.0))
        self.assertTrue(any("EXCEPTION" in m for m in cm.output))
    def test_exception_logged_open(self):
        with self.assertLogs("risk.correlation_filter",level="CRITICAL") as cm:
            run(self._crash(FailMode.FAIL_OPEN).check("XAUUSD","SELL",[],2.0))
        self.assertTrue(any("EXCEPTION" in m for m in cm.output))


class TestExposureGate(unittest.TestCase):
    def _crash(self,fm):
        e=ExposureControlEngine(fail_mode=fm)
        e._check_inner=lambda *a,**kw: {( xc for xc in ()).throw(ValueError("bad")); return cf
    def test_default_fail_closed(self): self.assertIs(ExposureControlEngine()._fail_mode,FailMode.FAIL_CLOSED)
    def test_fail_closed_blocks(self):
        e=ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._check_inner=lambda *a,**kw: {( xc for xc in ()).throw(ValueError("bad"))
        r=e.check("EURUSD","BUY",1.0,[])
        self.assertFalse(r.can_trade); self.assertIn("FAIL_CLOSED",r.reason)
    def test_fail_open_allows(self):
        e=ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        e._check_inner=lambda *a,**kw: {(xc for xc in ()).throw(ValueError("bad"))
        r=e.check("EURUSD","BUY",1.0,[])
        self.assertTrue(r.can_trade); self.assertIn("FAIL_OPEN",r.reason)
    def test_exception_logged(self):
        e=ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._check_inner=lambda *a,**kw: {( xc for xc in ()).throw(ValueError("bad"))
        with self.assertLogs("risk.exposure_control",level="CRITICAL") as cm:
            e.check("GBPUSD","SELL",1.0,[])
        self.assertTrue(any("EXCEPTION" in m for m in cm.output))
    def test_normal_not_blocked(self):
        r=ExposureControlEngine().check("GBPUSD","BUY",1.0,[ExposurePosition("EURUSD","BUY",1.0)])
        self.assertTrue(r.can_trade); self.assertAlmostEqual(r.projected_total_risk,2.0)
    def test_normal_blocked_over_limit(self):
        e=ExposureControlEngine(ExposureControlConfig(max_total_exposure_percent=5.0))
        r=e.check("NEW","BUY",1.0,[ExposurePosition(f"S{i}","BUY",1.5) for i in range(3)])
        self.assertFalse(r.can_trade); self.assertIn("Total exposure",r.reason)
    def test_snapshot_fail_closed(self):
        snap=ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED).get_snapshot([None,None])
        self.assertFalse(snap.can_open_new)
    def test_snapshot_fail_open(self):
        snap=ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN).get_snapshot([None])
        self.assertTrue(snap.can_open_new); self.assertEqual(snap.block_reason,"FAIL_OPEN_SNAPSHOT_ERROR")


class TestOrchestratorEquityGate(unittest.TestCase):
    def _eq(self,crash=False):
        m=MagicMock()
        if crash: type(m).can_trade=property(lambda self: (_ for _ in ()).throw(RuntimeError("eq")))
        else: m.can_trade=True; m.reason=""
        return m
    def test_fail_closed_blocks(self):
        r=run(RiskOrchestrator(exuity_guard=self._eq(True),fail_mode_equity=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000))
        self.assertFalse(r.approved); self.assertIn("EQUITY_GATE_ERROR",r.block_reason)
    def test_fail_open_allows(self):
        r=run(RiskOrchestrator(exuity_guard=self._eq(True),fail_mode_equity=FailMode.FAIL_OPEN).check("EURUSD","BUY",1.1,1.09,10000))
        self.assertTrue(r.approved); self.assertIn("EQUITY_FAIL_OPEN",r.gates_passed)
    def test_exception_logged(self):
        with self.assertLogs("risk.orchestrator",level="CRITICAL") as cm:
            run(RiskOrchestrator(exuity_guard=self._eq(True),fail_mode_equity=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000))
        self.assertTrue(any("EQUITY" in m for m in cm.output))
    def test_string_coerced(self): self.assertIs(RiskOrchestrator(fail_mode_equity="FAIL_OPEN")._fail_equity,FailMode.FAIL_OPEN)


class TestOrchestratorDailyGate(unittest.TestCase):
    def _dl(self,crash=False):
        m=MagicMock()
        if crash: type(m).can_trade=property(lambda self: (_ for _ in ()).throw(RuntimeError("dl")))
        else: m.can_trade=True; m.reason=""
        return m
    def test_fail_closed_blocks(self): self.assertFalse(run(RiskOrchestrator(daily_limits=self._dl(True),fail_mode_daily=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000)).approved)
    def test_fail_open_allows(self): self.assertTrue(run(RiskOrchestrator(daily_limits=self._dl(True),fail_mode_daily=FailMode.FAIL_OPEN).check("EURUSD","BUY",1.1,1.09,10000)).approved)
    def test_exception_logged(self):
        with self.assertLogs("risk.orchestrator",level="CRITICAL") as cm:
            run(RiskOrchestrator(daily_limits=self._dl(True),fail_mode_daily=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000))
        self.assertTrue(any("DAILY" in m for m in cm.output))


class TestOrchestratorVolatilityGate(unittest.TestCase):
    def _vol(self,crash=False):
        m=MagicMock()
        if crash: type(m).can_trade=property(lambda self: (_ for _ in ()).throw(RuntimeError("vol")))
        else: m.can_trade=True; m.reason=""
        return m
    def test_fail_closed_blocks(self): self.assertFalse(run(RiskOrchestrator(volatility_filter=self._vol(True),fail_mode_volatility=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000)).approved)
    def test_fail_open_allows(self): self.assertTrue(run(RiskOrchestrator(volatility_filter=self._vol(True),fail_mode_volatility=FailMode.FAIL_OPEN).check("EURUSD","BUY",1.1,1.09,10000)).approved)
    def test_exception_logged(self):
        with self.assertLogs("risk.orchestrator",level="CRITICAL") as cm:
            run(RiskOrchestrator(volatility_filter=self._vol(True),fail_mode_volatility=FailMode.FAIL_CLOSED).check("EURUSD","BUY",1.1,1.09,10000))
        self.assertTrue(any("VOLATILITY" in m for m in cm.output))


class TestOrchestratorCorrelationGate(unittest.TestCase):
    def _corr(self,crash=False):
        cf=CorrelationFilter()
        if crash:
            async def _c(*a,**kw): raise RuntimeError("corr")
            cf.check=_c
        return cf
    def test_fail_closed_blocks(szW