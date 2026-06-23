"""Phase Q unit tests - 44 tests."""
from __future__ import annotations
import asyncio, math, sys, time, unittest
from datetime import datetime, timezone
from typing import Any, Dict

from backend.ai_prediction.feature_pipeline import (
    FeatureNormalizer, FeaturePipeline, _broker_hour,
    _is_kill_zone, _london_ny_overlap, _safe_float, _session_score,
    feature_schema_hash, get_feature_names,
)
from backend.analytics.analytics_service_v2 import (
    AnalyticsServiceV2, MetricsCache, max_drawdown, profit_factor, sharpe_ratio, win_rate,
)
from backend.services.scheduler import BackgroundScheduler, TaskStatus

class TestFeaturePipeline(unittest.TestCase):
    def _s(self, **kw) -> Dict[str,Any]:
        b = {"direction":"BUY","price":1.1000,"market_data":{"atr":0.001,"spread":0.0001,"rsi":55,"volatility_score":0.3}}
        b.update(kw); return b
    def test_q1_normalizer(self):
        n=FeatureNormalizer()
        n.fit([{"atr_normalized":float(i/10)} for i in range(11)])
        self.assertAlmostEqual(n.transform({"atr_normalized":-1.0})["atr_normalized"],0.0)
        self.assertAlmostEqual(n.transform({"atr_normalized":5.0})["atr_normalized"],1.0)
    def test_q2_names_equal(self):
        self.assertEqual(get_feature_names(),get_feature_names()); self.assertEqual(len(get_feature_names()),38)
    def test_q2_names_38(self): self.assertEqual(len(get_feature_names()),38)
    def test_q3_tz_aware(self):
        from backend.ai_prediction.prediction_service_v2 import PredictionResult
        r=PredictionResult(probability=70,confidence=80,risk="LOW",direction="BUY")
        self.assertIsNotNone(r.predicted_at.tzinfo)
    def test_q4_nan(self):
        s=self._s(); s["market_data"]["rsi"]=float("nan")
        vec,_=FeaturePipeline().extract(s)
        for v in vec: self.assertFalse(math.isnan(v))
    def test_q4_inf(self): self.assertEqual(_safe_float(float("inf"),0.0,"x"),0.0)
    def test_q5_hash_stable(self): self.assertEqual(feature_schema_hash(),feature_schema_hash()); self.assertEqual(len(feature_schema_hash()),8)
    def test_q6_broker_hour(self): self.assertEqual(_broker_hour({"broker_hour":14,"generated_at":"2024-01-01T02:00:00Z"}),14)
    def test_q6_utc_fallback(self): self.assertEqual(_broker_hour({"generated_at":"2024-01-01T08:30:00+00:00"}),8)
    def test_q7_vec_length(self): self.assertEqual(len(FeaturePipeline().extract(self._s())[0]),38)
    def test_session(self): self.assertGreater(_session_score(8),0)
    def test_kz(self): self.assertEqual(_is_kill_zone(7),1.0); self.assertEqual(_is_kill_zone(11),0.0)
    def test_overlap(self): self.assertEqual(_london_ny_overlap(13),1.0); self.assertEqual(_london_ny_overlap(20),0.0)

class TestPrediction(unittest.TestCase):
    def _s(self): return {"direction":"BUY","price":1.2,"market_data":{"atr":0.0015,"spread":0.0002,"rsi":60,"volatility_score":0.2}}
    def test_q11_hi_auc(self):
        from backend.ai_prediction.prediction_service_v2 import _compute_confidence
        self.assertGreater(_compute_confidence(0.90,2000,0.8,80),60)
    def test_q11_lo_auc(self):
        from backend.ai_prediction.prediction_service_v2 import _compute_confidence
        self.assertLess(_compute_confidence(0.51,50,0.1,55),30)
    def test_q12_hi_spread(self):
        from backend.ai_prediction.prediction_service_v2 import _compute_risk_level
        self.assertIn(_compute_risk_level(60,3.0,0.3),["HIGH","VERY_HIGH"])
    def test_q12_low(self):
        from backend.ai_prediction.prediction_service_v2 import _compute_risk_level
        self.assertEqual(_compute_risk_level(80,0.5,0.2),"LOW")
    def test_q12_very_high(self):
        from backend.ai_prediction.prediction_service_v2 import _compute_risk_level
        self.assertEqual(_compute_risk_level(40,3.0,0.9),"VERY_HIGH")
    def test_q13_fallback(self):
        from backend.ai_prediction.prediction_service_v2 import PredictionServiceV2
        r=PredictionServiceV2()._fallback(self._s(),"test")
        self.assertTrue(r.is_fallback); self.assertEqual(r.risk,"HIGH")
    def test_q14_async(self):
        from backend.ai_prediction.prediction_service_v2 import PredictionServiceV2
        r=asyncio.run(PredictionServiceV2().predict(self._s()))
        self.assertGreater(r.latency_ms,0)
    def test_q14_concurrent(self):
        from backend.ai_prediction.prediction_service_v2 import PredictionServiceV2
        svc=PredictionServiceV2()
        res=asyncio.run(asyncio.gather(*[svc.predict(self._s()) for _ in range(5)]))
        self.assertEqual(len(res),5)

class TestTraining(unittest.TestCase):
    def test_q7_tz(self):
        from backend.self_learning.training_pipeline_v2 import TrainingResultV2
        self.assertIsNotNone(TrainingResultV2().trained_at.tzinfo)
    def test_q15_field(self):
        from backend.self_learning.training_pipeline_v2 import TrainingResultV2
        self.assertEqual(TrainingResultV2().class_balance_ratio,1.0)
    def test_q16_hash(self):
        from backend.self_learning.training_pipeline_v2 import TrainingResultV2
        r=TrainingResultV2(); r.feature_schema_hash=feature_schema_hash()
        self.assertNotEqual(r.feature_schema_hash,"")
    def test_q20_names(self):
        from backend.self_learning.training_pipeline_v2 import TrainingResultV2
        r=TrainingResultV2(); r.feature_names=get_feature_names()
        self.assertEqual(len(r.feature_names),38)

class TestAnalytics(unittest.TestCase):
    def test_q22_empty(self): self.assertEqual(sharpe_ratio([]),0.0)
    def test_q22_single(self): self.assertEqual(sharpe_ratio([0.01]),0.0)
    def test_q22_positive(self):
        import random; random.seed(1)
        rets=[0.001+random.uniform(-0.0005,0.0005) for _ in range(252)]
        self.assertGreater(sharpe_ratio(rets),0)
    def test_q23_correct(self):
        mdd,pi,ti=max_drawdown([10000,11000,9000,9500,8000,10000])
        self.assertAlmostEqual(mdd,(11000-8000)/11000*100,places=1)
        self.assertEqual(pi,1); self.assertEqual(ti,4)
    def test_q23_empty(self): self.assertEqual(max_drawdown([])[0],0.0)
    def test_q25_float(self): self.assertIsInstance(win_rate(3,5),float); self.assertAlmostEqual(win_rate(3,5),60.0)
    def test_q25_zero(self): self.assertEqual(win_rate(0,0),0.0)
    def test_q26_cache(self):
        async def _r():
            c=MetricsCache(5.0); await c.set("k",{"x":1}); return await c.get("k")
        self.assertEqual(asyncio.run(_r()),{"x":1})
    def test_q26_expired(self):
        async def _r():
            c=MetricsCache(0.01); await c.set("k",42); await asyncio.sleep(0.05); return await c.get("k")
        self.assertIsNone(asyncio.run(_r()))
    def test_pf_zero(self): self.assertEqual(profit_factor(100,0),999.9)
    def test_pf_normal(self): self.assertAlmostEqual(profit_factor(200,100),2.0)

class TestScheduler(unittest.TestCase):
    def test_q28_task_type(self):
        async def _r():
            async def _noop(): pass
            s=BackgroundScheduler(); s.register("x",_noop,60)
            ok=isinstance(s._registry["x"].task,asyncio.Task)
            await s.shutdown(1.0); return ok
        self.assertTrue(asyncio.run(_r()))
    def test_q29_exception_recorded(self):
        errs=[0]
        async def _flaky(): errs[0]+=1; raise RuntimeError("err")
        async def _r():
            s=BackgroundScheduler(); s.register("f",_flaky,0.02)
            await asyncio.sleep(0.15)
            ec=s._registry["f"].error_count
            await s.shutdown(1.0); return ec
        self.assertGreaterEqual(asyncio.run(_r()),1)
    def test_q30_clears_registry(self):
        async def _r():
            async def _n(): pass
            s=BackgroundScheduler(); s.register("a",_n,60); s.register("b",_n,60)
            await s.shutdown(1.0); return len(s._registry)
        self.assertEqual(asyncio.run(_r()),0)
    def test_q31_registered(self):
        async def _r():
            async def _n(): pass
            s=BackgroundScheduler(); s.register("x",_n,60)
            n=len(s._registry); await s.shutdown(1.0); return n
        self.assertEqual(asyncio.run(_r()),1)
    def test_q32_health(self):
        async def _r():
            async def _n(): pass
            s=BackgroundScheduler(); s.register("h",_n,60)
            await asyncio.sleep(0.05); h=s.health(); await s.shutdown(1.0); return h
        h=asyncio.run(_r())
        self.assertIn("total_tasks",h); self.assertIn("healthy",h); self.assertEqual(h["total_tasks"],1)
    def test_q33_jitter(self):
        async def _r():
            async def _n(): pass
            s=BackgroundScheduler(); s.register("j",_n,60,jitter_s=5.0)
            await s.shutdown(1.0)
        asyncio.run(_r())

class TestIntegration(unittest.TestCase):
    def test_full_pipeline(self):
        from backend.ai_prediction.prediction_service_v2 import PredictionServiceV2
        sig={"direction":"SELL","price":1.085,"broker_hour":9,
             "market_data":{"atr":0.0012,"spread":0.00015,"rsi":35,"volatility_score":0.4,"trend_strength":0.7,"adx":28},
             "smc_data":{"bos":True,"choch":True,"ob":{"quality":0.9,"size_pips":25},"pd_zone":"PREMIUM"},
             "pa_data":{"pattern_score":0.85,"quality":0.8,"timeframe_weight":0.9}}
        vec,names=FeaturePipeline().extract(sig)
        self.assertEqual(len(vec),38)
        for v in vec: self.assertFalse(math.isnan(v))
        r=asyncio.run(PredictionServiceV2().predict(sig))
        self.assertGreaterEqual(r.probability,0); self.assertLessEqual(r.probability,100)
    def test_analytics_chain(self):
        rets=[0.002,-0.001,0.003,-0.002,0.001]*50
        curve=[10000.0]
        eq=10000.0
        for r in rets: eq*=(1+r); curve.append(eq)
        self.assertIsInstance(sharpe_ratio(rets),float)
        mdd,_,_=max_drawdown(curve); self.assertGreater(mdd,0); self.assertLess(mdd,100)
        self.assertGreater(win_rate(sum(1 for r in rets if r>0),len(rets)),0)

if __name__=="__main__":
    unittest.main(verbosity=2)
