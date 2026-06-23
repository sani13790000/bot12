"""Multi-Agent Safety Unit Tests (MS-1 to MS-5) -- 30 tests."""
import asyncio, sys, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
import logging

class AgentStatus(str, Enum):
    OK='OK'; WARNING='WARNING'; ERROR='ERROR'; SKIP='SKIP'

@dataclass
class AgentVote:
    score: float; confidence: float; direction: Optional[str]=None
    status: AgentStatus=AgentStatus.OK; reason: str=''
    metadata: Dict[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        self.score=max(0.0,min(100.0,float(self.score)))
        self.confidence=max(0.0,min(100.0,float(self.confidence)))

@dataclass
class AgentResult:
    agent_name: str; vote: AgentVote; elapsed_ms: float=0.0; error: Optional[str]=None

class BaseAgent(ABC):
    def __init__(self,name,weight=1.0,enabled=True):
        self.name=name; self.weight=max(0.0,float(weight)); self.enabled=enabled
        self._logger=logging.getLogger(f'agent.{name}')
    @abstractmethod
    async def analyze(self,context): ...
    async def run(self,context,timeout_s=None):
        if not self.enabled:
            return AgentResult(agent_name=self.name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.SKIP,reason='disabled'))
        t0=time.perf_counter()
        try:
            if timeout_s is not None: vote=await asyncio.wait_for(self.analyze(context),timeout=timeout_s)
            else: vote=await self.analyze(context)
            return AgentResult(agent_name=self.name,vote=vote,elapsed_ms=(time.perf_counter()-t0)*1000)
        except asyncio.TimeoutError:
            return AgentResult(agent_name=self.name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.ERROR,reason=f'Timeout after {timeout_s}s',direction='NEUTRAL'),elapsed_ms=(time.perf_counter()-t0)*1000,error=f'timeout after {timeout_s}s')
        except Exception as exc:
            return AgentResult(agent_name=self.name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.ERROR,reason=f'Crash: {exc}',direction='NEUTRAL'),elapsed_ms=(time.perf_counter()-t0)*1000,error=str(exc))

_AGENT_TIMEOUT_S=5.0; _TIE_TOLERANCE=0.01; _RISK_AGENT_NAME='Risk'
from enum import Enum as _E; from dataclasses import dataclass as _dc, field as _f

class VoteDecision(str,_E):
    BUY='BUY'; SELL='SELL'; NO_TRADE='NO_TRADE'; BLOCKED='BLOCKED'

@_dc
class VoteResult:
    decision: VoteDecision; weighted_score: float; confidence: float; direction: str
    agent_results: List[AgentResult]=_f(default_factory=list); blocked_by: Optional[str]=None
    reasons: List[str]=_f(default_factory=list); elapsed_ms: float=0.0
    metadata: Dict[str,Any]=_f(default_factory=dict)
    @property
    def passed_threshold(self): return self.decision in (VoteDecision.BUY,VoteDecision.SELL)

class VotingEngine:
    def __init__(self,agents,min_score_threshold=65.0,min_confidence_threshold=50.0,run_parallel=True,agent_timeout_s=_AGENT_TIMEOUT_S):
        self._agents=agents; self._min_score_threshold=min_score_threshold
        self._min_confidence_threshold=min_confidence_threshold
        self._run_parallel=run_parallel; self._agent_timeout_s=agent_timeout_s
        self._normalise_weights()
    async def vote(self,context):
        t0=time.perf_counter()
        rv=await self._check_risk_veto(context)
        if rv is not None: rv.elapsed_ms=(time.perf_counter()-t0)*1000; return rv
        results=await (self._run_parallel_safe(context) if self._run_parallel else self._run_sequential_safe(context))
        r=self._aggregate(results); r.elapsed_ms=(time.perf_counter()-t0)*1000; return r
    async def _check_risk_veto(self,context):
        ra=next((a for a in self._agents if a.name==_RISK_AGENT_NAME and a.enabled),None)
        if ra is None: return VoteResult(decision=VoteDecision.BLOCKED,weighted_score=0.0,confidence=0.0,direction='BLOCKED',blocked_by='SYSTEM',reasons=['Risk agent missing'])
        r=await self._run_with_timeout(ra,context)
        if r.vote.status==AgentStatus.ERROR and r.vote.score==0.0: return VoteResult(decision=VoteDecision.BLOCKED,weighted_score=0.0,confidence=0.0,direction='BLOCKED',agent_results=[r],blocked_by=r.agent_name,reasons=[f'Risk veto: {r.vote.reason}'])
        if r.error and 'timeout' in r.error.lower(): return VoteResult(decision=VoteDecision.BLOCKED,weighted_score=0.0,confidence=0.0,direction='BLOCKED',agent_results=[r],blocked_by=r.agent_name,reasons=['Risk timeout'])
        return None
    async def _run_with_timeout(self,agent,context):
        try: return await asyncio.wait_for(agent.run(context),timeout=self._agent_timeout_s)
        except asyncio.TimeoutError: return AgentResult(agent_name=agent.name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.ERROR,reason=f'Timeout',direction='NEUTRAL'),elapsed_ms=self._agent_timeout_s*1000,error=f'timeout after {self._agent_timeout_s}s')
        except Exception as exc: return AgentResult(agent_name=agent.name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.ERROR,reason=f'Crash: {exc}',direction='NEUTRAL'),elapsed_ms=0.0,error=str(exc))
    async def _run_parallel_safe(self,context):
        nr=[a for a in self._agents if a.name!=_RISK_AGENT_NAME]
        raw=await asyncio.gather(*[self._run_with_timeout(a,context) for a in nr],return_exceptions=True)
        return [AgentResult(agent_name=nr[i].name,vote=AgentVote(score=50.0,confidence=0.0,status=AgentStatus.ERROR,reason=f'Unhandled: {item}',direction='NEUTRAL'),elapsed_ms=0.0,error=str(item)) if isinstance(item,BaseException) else item for i,item in enumerate(raw)]
    async def _run_sequential_safe(self,context):
        return [await self._run_with_timeout(a,context) for a in self._agents if a.name!=_RISK_AGENT_NAME]
    def _aggregate(self,results):
        tw=0.0; ws=0.0; wc=0.0; dw={'BUY':0.0,'SELL':0.0,'NEUTRAL':0.0}; reasons=[]
        aw={a.name:a.weight for a in self._agents}
        for r in results:
            if r.vote.status==AgentStatus.SKIP: continue
            bw=aw.get(r.agent_name,1.0/max(len(results),1))
            cm=max(0.0,r.vote.confidence/100.0); ew=bw*cm
            if r.vote.status==AgentStatus.ERROR: ew*=0.5
            ws+=r.vote.score*ew; wc+=r.vote.confidence*ew; tw+=ew
            d=(r.vote.direction or 'NEUTRAL').upper(); dw.setdefault(d,0.0); dw[d]+=ew
            if r.vote.reason: reasons.append(f'[{r.agent_name}] {r.vote.reason}')
        fs,fc=(ws/tw,wc/tw) if tw>0 else (50.0,0.0)
        fs=max(0.0,min(100.0,fs)); fc=max(0.0,min(100.0,fc))
        bw2=dw.get('BUY',0.0); sw2=dw.get('SELL',0.0)
        if abs(bw2-sw2)<=_TIE_TOLERANCE and (bw2+sw2)>0: reasons.append(f'TIE'); return VoteResult(decision=VoteDecision.NO_TRADE,weighted_score=fs,confidence=fc,direction='NEUTRAL',agent_results=results,reasons=reasons,metadata={'tie_detected':True,'buy_weight':round(bw2,4),'sell_weight':round(sw2,4),'active_agents':len([r for r in results if r.vote.status!=AgentStatus.SKIP]),'error_agents':len([r for r in results if r.vote.status==AgentStatus.ERROR])})
        top=max(dw,key=lambda d:dw[d])
        if fs>=self._min_score_threshold and fc>=self._min_confidence_threshold: dec=VoteDecision.BUY if top=='BUY' else (VoteDecision.SELL if top=='SELL' else VoteDecision.NO_TRADE)
        else: dec=VoteDecision.NO_TRADE
        return VoteResult(decision=dec,weighted_score=fs,confidence=fc,direction=top,agent_results=results,reasons=reasons,metadata={'tie_detected':False,'buy_weight':round(bw2,4),'sell_weight':round(sw2,4),'active_agents':len([r for r in results if r.vote.status!=AgentStatus.SKIP]),'error_agents':len([r for r in results if r.vote.status==AgentStatus.ERROR])})
    def _normalise_weights(self):
        e=[a for a in self._agents if a.enabled]
        if not e: return
        t=sum(a.weight for a in e)
        if t>0 and abs(t-1.0)>0.01:
            for a in e: a.weight=a.weight/t
    @property
    def agents(self): return self._agents

# test agents
class GoodRisk(BaseAgent):
    def __init__(self): super().__init__('Risk',0.20)
    async def analyze(self,c): return AgentVote(score=85.0,confidence=90.0,direction=c.get('direction','BUY'),status=AgentStatus.OK,reason='OK')
class BlockRisk(BaseAgent):
    def __init__(self,r='blocked'): super().__init__('Risk',0.20); self._r=r
    async def analyze(self,c): return AgentVote(score=0.0,confidence=100.0,direction='NEUTRAL',status=AgentStatus.ERROR,reason=self._r)
class SlowRisk(BaseAgent):
    def __init__(self,d=10): super().__init__('Risk',0.20); self._d=d
    async def analyze(self,c): await asyncio.sleep(self._d); return AgentVote(score=85.0,confidence=90.0,direction='BUY')
class BuyAgent(BaseAgent):
    def __init__(self,n,w=0.25): super().__init__(n,w)
    async def analyze(self,c): return AgentVote(score=80.0,confidence=75.0,direction='BUY',status=AgentStatus.OK,reason='BUY')
class SellAgent(BaseAgent):
    def __init__(self,n,w=0.25): super().__init__(n,w)
    async def analyze(self,c): return AgentVote(score=80.0,confidence=75.0,direction='SELL',status=AgentStatus.OK,reason='SELL')
class Crasher(BaseAgent):
    def __init__(self,n): super().__init__(n,0.20)
    async def analyze(self,c): raise RuntimeError(f'{self.name} crashed')
class SlowAgent(BaseAgent):
    def __init__(self,n,d=10): super().__init__(n,0.20); self._d=d
    async def analyze(self,c): await asyncio.sleep(self._d); return AgentVote(score=80.0,confidence=80.0,direction='BUY')
class HiConfBuy(BaseAgent):
    def __init__(self,n,w=0.40,conf=90.0): super().__init__(n,w); self._conf=conf
    async def analyze(self,c): return AgentVote(score=85.0,confidence=self._conf,direction='BUY',status=AgentStatus.OK)
class LoConfSell(BaseAgent):
    def __init__(self,n,w=0.40,conf=20.0): super().__init__(n,w); self._conf=conf
    async def analyze(self,c): return AgentVote(score=85.0,confidence=self._conf,direction='SELL',status=AgentStatus.OK)
class ZeroConf(BaseAgent):
    def __init__(self): super().__init__('ZeroConf',0.40)
    async def analyze(self,c): return AgentVote(score=100.0,confidence=0.0,direction='SELL')

PASS=0; FAIL=0
def check(label,cond,detail=''):
    global PASS,FAIL
    if cond: PASS+=1; print(f'  PASS  {label}')
    else: FAIL+=1; print(f'  FAIL  {label}'+(f' -- {detail}' if detail else ''))

async def run_tests():
    ctx={'direction':'BUY'}
    print('\n-- MS-1: Risk Priority')
    r=await VotingEngine([BlockRisk(),BuyAgent('A'),BuyAgent('B')]).vote(ctx)
    check('MS-1-A blocked',r.decision==VoteDecision.BLOCKED)
    check('MS-1-A blocked_by',r.blocked_by=='Risk')
    check('MS-1-A score=0',r.weighted_score==0.0)
    r=await VotingEngine([BuyAgent('A'),BuyAgent('B')]).vote(ctx)
    check('MS-1-B no risk -> BLOCKED',r.decision==VoteDecision.BLOCKED)
    check('MS-1-B system',r.blocked_by=='SYSTEM')
    r=await VotingEngine([GoodRisk(),BuyAgent('A',0.40),BuyAgent('B',0.40)],min_score_threshold=65.0,min_confidence_threshold=50.0).vote(ctx)
    check('MS-1-C risk OK -> BUY',r.decision==VoteDecision.BUY,f'got {r.decision}')
    dr=GoodRisk(); dr.enabled=False
    r=await VotingEngine([dr,BuyAgent('A')]).vote(ctx)
    check('MS-1-D disabled risk -> BLOCKED',r.decision==VoteDecision.BLOCKED)
    print('\n-- MS-2: Tie -> NO_TRADE')
    r=await VotingEngine([GoodRisk(),BuyAgent('A',0.30),SellAgent('B',0.30)],min_score_threshold=65.0,min_confidence_threshold=50.0).vote({'direction':'BUY'})
    check('MS-2-A tie -> NO_TRADE',r.decision==VoteDecision.NO_TRADE,f'got {r.decision}')
    check('MS-2-A tie_detected',r.metadata.get('tie_detected') is True)
    r=await VotingEngine([GoodRisk(),BuyAgent('A',0.40),SellAgent('B',0.20)],min_score_threshold=65.0,min_confidence_threshold=50.0).vote(ctx)
    check('MS-2-B no tie',r.metadata.get('tie_detected') is False)
    r=await VotingEngine([GoodRisk(),SellAgent('A',0.40),SellAgent('B',0.40)],min_score_threshold=65.0,min_confidence_threshold=50.0).vote({'direction':'SELL'})
    check('MS-2-C all SELL',r.decision==VoteDecision.SELL,f'got {r.decision}')
    print('\n-- MS-3: Confidence-weighted voting')
    r=await VotingEngine([GoodRisk(),HiConfBuy('Hi',0.40,90.0),LoConfSell('Lo',0.40,10.0)],min_score_threshold=60.0,min_confidence_threshold=30.0).vote(ctx)
    check('MS-3-A hi-conf BUY wins',r.metadata.get('buy_weight',0)>r.metadata.get('sell_weight',0))
    check('MS-3-A decision BUY',r.decision==VoteDecision.BUY,f'got {r.decision}')
    r=await VotingEngine([GoodRisk(),HiConfBuy('Hi',0.40,90.0),ZeroConf()],min_score_threshold=60.0,min_confidence_threshold=30.0).vote(ctx)
    check('MS-3-B zero-conf SELL ignored',r.decision==VoteDecision.BUY,f'got {r.decision}')
    print('\n-- MS-4: Timeout handling')
    t0=time.time()
    r=await VotingEngine([GoodRisk(),BuyAgent('Fast',0.40),SlowAgent('Slow',10.0)],min_score_threshold=65.0,min_confidence_threshold=50.0,agent_timeout_s=0.1).vote(ctx)
    elapsed=time.time()-t0
    check('MS-4-A no hang',elapsed<2.0,f'{elapsed:.2f}s')
    check('MS-4-A error counted',r.metadata.get('error_agents',0)>=1)
    r=await VotingEngine([SlowRisk(10.0),BuyAgent('A',0.40)],agent_timeout_s=0.1).vote(ctx)
    check('MS-4-B risk timeout -> BLOCKED',r.decision==VoteDecision.BLOCKED,f'got {r.decision}')
    print('\n-- MS-5: Failover')
    r=await VotingEngine([GoodRisk(),BuyAgent('S',0.35),Crasher('C'),BuyAgent('S2',0.25)],min_score_threshold=65.0,min_confidence_threshold=50.0,agent_timeout_s=2.0).vote(ctx)
    check('MS-5-A continues after crash',r.decision!=VoteDecision.BLOCKED,f'got {r.decision}')
    check('MS-5-A error counted',r.metadata.get('error_agents',0)>=1)
    r=await VotingEngine([GoodRisk(),Crasher('C1'),Crasher('C2')],min_score_threshold=65.0,min_confidence_threshold=50.0,agent_timeout_s=2.0).vote(ctx)
    check('MS-5-B all crash no exception',r.decision in list(VoteDecision))
    try:
        await VotingEngine([GoodRisk(),Crasher('E')],agent_timeout_s=2.0).vote(ctx)
        check('MS-5-C no propagation',True)
    except Exception as e: check('MS-5-C no propagation',False,str(e))
    print('\n-- Integration')
    r=await VotingEngine([GoodRisk(),BuyAgent('A',0.25),BuyAgent('B',0.25),BuyAgent('C',0.10)],min_score_threshold=65.0,min_confidence_threshold=50.0).vote(ctx)
    check('INT-1 full BUY',r.decision==VoteDecision.BUY,f'got {r.decision}')
    check('INT-1 elapsed>0',r.elapsed_ms>0)
    agents_w=[GoodRisk(),BuyAgent('A',0.5),BuyAgent('B',0.5)]
    e=VotingEngine(agents_w)
    check('INT-2 normalised',abs(sum(a.weight for a in e.agents if a.enabled)-1.0)<0.02)
    r=await VotingEngine([GoodRisk(),BuyAgent('A',0.40),BuyAgent('B',0.40)],run_parallel=False,min_score_threshold=65.0,min_confidence_threshold=50.0).vote(ctx)
    check('INT-3 sequential BUY',r.decision==VoteDecision.BUY,f'got {r.decision}')

async def main():
    print('='*50+'\n Multi-Agent Safety Unit Tests\n'+'='*50)
    await run_tests()
    print(f'\nResults: {PASS}/{PASS+FAIL} PASS  {FAIL}/{PASS+FAIL} FAIL')
    return FAIL

if __name__=='__main__':
    sys.exit(asyncio.run(main()))
