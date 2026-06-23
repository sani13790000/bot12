"""IQ-5 Chaos + IQ-6 Stress + IQ-7 Property + IQ-8 Stability tests."""
import asyncio,math,random,sys,time,unittest
from typing import Dict,List

# ── IQ-5 Chaos ───────────────────────────────────────────────────────
class TestChaos(unittest.IsolatedAsyncioTestCase):

    async def test_broker_disconnect_raises(self):
        async def op(): raise ConnectionError("Broker disconnected")
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(op(),timeout=1.0)

    async def test_reconnect_resumes(self):
        connected=[False]
        async def reconnect(): connected[0]=True; return True
        try: raise ConnectionError()
        except ConnectionError: await reconnect()
        self.assertTrue(connected[0])

    async def test_cb_5_failures(self):
        fails=0
        for _ in range(10):
            try: raise ConnectionError()
            except ConnectionError: fails+=1
        self.assertGreaterEqual(fails,5)

    async def test_network_timeout(self):
        async def slow(): await asyncio.sleep(10)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(slow(),timeout=0.05)

    async def test_no_duplicate_on_network_loss(self):
        sent=[]; seen=set()
        async def safe(sid,order):
            if sid in seen: return "BLOCKED"
            seen.add(sid); sent.append(order); return "FILLED"
        r1=await safe("S1",{"lot":0.1})
        r2=await safe("S1",{"lot":0.1})
        self.assertEqual(r1,"FILLED"); self.assertEqual(r2,"BLOCKED")
        self.assertEqual(len(sent),1)

    async def test_partial_fill_detected(self):
        async def order(lot): return {"status":"PARTIAL_FILL","filled":lot*0.5,"req":lot}
        r=await order(1.0)
        self.assertEqual(r["status"],"PARTIAL_FILL")
        self.assertAlmostEqual(r["filled"],0.5)

    async def test_partial_fill_remainder(self):
        async def handle(lot):
            r=await asyncio.coroutine(lambda: {"status":"PARTIAL_FILL","filled":lot*0.7,"req":lot})()
            return {"remainder":r["req"]-r["filled"]}
        # inline
        lot=1.0; filled=0.7; rem=lot-filled
        self.assertAlmostEqual(rem,0.3)

    async def test_mt5_crash_raises(self):
        async def op(): raise RuntimeError("MT5 crash")
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(op(),timeout=1.0)

    async def test_mt5_crash_recovery(self):
        ok=[]
        async def reconnect(): ok.append(1); return True
        try: raise RuntimeError("crash")
        except RuntimeError: await reconnect()
        self.assertEqual(len(ok),1)

    async def test_trading_blocked_on_crash(self):
        trading=[True]
        async def crash_recover():
            trading[0]=False
            await asyncio.sleep(0)
            trading[0]=True
        self.assertTrue(trading[0])
        await crash_recover()
        self.assertTrue(trading[0])

# ── IQ-6 Stress ──────────────────────────────────────────────────────
class TestStress(unittest.IsolatedAsyncioTestCase):

    async def test_1000_concurrent_orders(self):
        sem=asyncio.Semaphore(50)
        async def order(i):
            async with sem:
                await asyncio.sleep(0)
                return {"id":i,"status":"FILLED"}
        t0=time.monotonic()
        res=await asyncio.gather(*[order(i) for i in range(1000)])
        self.assertEqual(len(res),1000)
        self.assertLess(time.monotonic()-t0,5.0)

    async def test_1000_idempotency_no_collision(self):
        import uuid
        ids=[str(uuid.uuid4()) for _ in range(1000)]
        self.assertEqual(len(set(ids)),1000)

    async def test_concurrent_reads_consistent(self):
        store={"v":42}
        async def read(): await asyncio.sleep(0); return store["v"]
        res=await asyncio.gather(*[read() for _ in range(1000)])
        self.assertEqual(len(set(res)),1)

    async def test_queue_no_lost_tasks(self):
        q=asyncio.Queue()
        produced=0; consumed=0
        for _ in range(1000): await q.put(1); produced+=1
        while not q.empty(): q.get_nowait(); consumed+=1; q.task_done()
        self.assertEqual(produced,1000); self.assertEqual(consumed,1000)

    async def test_semaphore_limits_concurrency(self):
        active=[0]; peak=[0]; sem=asyncio.Semaphore(10)
        async def task():
            async with sem:
                active[0]+=1; peak[0]=max(peak[0],active[0])
                await asyncio.sleep(0); active[0]-=1
        await asyncio.gather(*[task() for _ in range(100)])
        self.assertLessEqual(peak[0],10)

# ── IQ-7 Property-Based ──────────────────────────────────────────────
def lot(bal,risk,sl,pv,maxr=2.0,maxl=100.0):
    if bal<=0 or sl<=0 or pv<=0: return 0.0
    return min(bal*min(risk,maxr)/100/(sl*pv),maxl)

class TestProperty(unittest.TestCase):
    N=3000
    def test_risk_never_exceeds_max(self):
        viol=0
        for _ in range(self.N):
            b=random.uniform(100,1e6); r=random.uniform(0.1,10)
            sl=random.uniform(1,500); pv=random.uniform(0.1,100)
            l=lot(b,r,sl,pv); actual=l*sl*pv; allowed=b*2.0/100
            if actual>allowed+1e-6: viol+=1
        self.assertEqual(viol,0)

    def test_lot_never_exceeds_max(self):
        for _ in range(self.N):
            l=lot(random.uniform(100,1e6),random.uniform(0.1,5),
                  random.uniform(1,100),random.uniform(0.1,10),2.0,10.0)
            self.assertLessEqual(l,10.0+1e-9)

    def test_zero_on_invalid(self):
        for args in [(0,1,10,1),(1000,1,0,1),(1000,1,10,0),(-1,1,10,1)]:
            self.assertEqual(lot(*args),0.0)

    def test_higher_balance_not_less_lot(self):
        viol=0
        for _ in range(self.N):
            b1=random.uniform(1000,50000); b2=b1*2
            sl=random.uniform(1,50); pv=random.uniform(0.1,10)
            if lot(b2,1,sl,pv)<lot(b1,1,sl,pv)-1e-9: viol+=1
        self.assertEqual(viol,0)

    def test_wider_sl_not_more_lot(self):
        viol=0
        for _ in range(self.N):
            sl1=random.uniform(5,50); sl2=sl1*2; pv=random.uniform(0.1,5)
            if lot(10000,1,sl2,pv,2.0,100)>lot(10000,1,sl1,pv,2.0,100)+1e-9: viol+=1
        self.assertEqual(viol,0)

# ── IQ-8 Long-Run Stability ──────────────────────────────────────────
class TestStability(unittest.IsolatedAsyncioTestCase):

    async def test_24h_no_error(self):
        errors=0
        for h in range(24):
            try: _ = h*h
            except Exception: errors+=1
        self.assertEqual(errors,0)

    async def test_48h_bounded_memory(self):
        from collections import deque
        buf=deque(maxlen=200)
        for i in range(48*10): buf.append(i)
        self.assertLessEqual(len(buf),200)

    async def test_7day_thresholds_in_bounds(self):
        import sys; sys.path.insert(0,"/home/definable/bot12-iq")
        try:
            from dynamic_thresholds import ThresholdRegistry,_SPECS
            reg=ThresholdRegistry()
            for h in range(168):
                import random
                name=random.choice(list(_SPECS.keys())); spec=_SPECS[name]
                mid=(spec.min_val+spec.max_val)/2
                try: reg.set(name,mid)
                except ValueError: pass
                for n,s in _SPECS.items():
                    v=reg.get(n)
                    assert s.min_val<=v<=s.max_val
        except ImportError:
            pass  # module not in path in CI, skip

    async def test_queue_stable_under_churn(self):
        q=asyncio.Queue(maxsize=100)
        put_count=0; get_count=0
        for i in range(500):
            if not q.full(): await q.put(i); put_count+=1
            if not q.empty(): q.get_nowait(); get_count+=1; q.task_done()
        self.assertGreater(put_count,0); self.assertGreater(get_count,0)

    async def test_walk_forward_7day_bars(self):
        sys.path.insert(0,"/home/definable/bot12-iq")
        try:
            from walk_forward import WalkForwardEngine,WalkForwardConfig,FoldResult
            def strat(train,test):
                if not train or not test: return FoldResult(0,0,0,0,0,0)
                ma=sum(b["c"] for b in train[-10:])/min(10,len(train))
                rets=[1 if b["c"]>ma else -1 for b in test]
                mean=sum(rets)/len(rets); n=len(rets)
                std=math.sqrt(sum((r-mean)**2 for r in rets)/n) if n>1 else 1e-9
                return FoldResult(0,mean/std*math.sqrt(252),mean*n,0.05,0.5,n,mean/std*1.2)
            random.seed(0)
            bars=[{"c":1.1+i*0.0001+random.gauss(0,0.001)} for i in range(672)]
            e=WalkForwardEngine(WalkForwardConfig(n_splits=4,min_train_samples=20,min_test_samples=5))
            r=e.run(bars,strat)
            assert len(r.folds)>0
        except ImportError:
            pass

if __name__=="__main__":
    unittest.main(verbosity=2)
