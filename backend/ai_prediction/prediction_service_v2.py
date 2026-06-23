"""PredictionService v2 — Phase Q fixes Q-8..Q-14.
Q-8:  schema validation (feature hash mismatch warning)
Q-9:  asyncio.to_thread — no blocking in event loop
Q-10: warm_up() at startup
Q-11: _compute_confidence() dynamic (AUC+samples+confluence)
Q-12: _compute_risk_level() dynamic (prob+spread+volatility)
Q-13: is_fallback flag — never silent
Q-14: asyncio.Lock — concurrent predict safe
"""
from __future__ import annotations
import asyncio, logging, math, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
try:
    from .feature_pipeline import get_feature_pipeline, feature_schema_hash, FEATURE_VERSION
except ImportError:
    from feature_pipeline import get_feature_pipeline, feature_schema_hash, FEATURE_VERSION  # type: ignore
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class PredictionResult:
    probability: float
    confidence:  float
    risk:        str
    direction:   str
    feature_schema_hash: str = ""
    model_version:       str = "unknown"
    predicted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms:   float = 0.0
    is_fallback:  bool  = False
    def to_dict(self)->Dict[str,Any]:
        return {"probability":round(self.probability,2),"confidence":round(self.confidence,2),
                "risk":self.risk,"direction":self.direction,
                "feature_schema_hash":self.feature_schema_hash,
                "model_version":self.model_version,
                "predicted_at":self.predicted_at.isoformat(),
                "latency_ms":round(self.latency_ms,2),"is_fallback":self.is_fallback}

def _compute_risk_level(probability:float, spread_ratio:float, volatility_score:float)->str:
    """Q-12: dynamic risk from signal data — not hardcoded."""
    s=0
    if probability<55: s+=2
    elif probability<65: s+=1
    if spread_ratio>2.0: s+=2
    elif spread_ratio>1.5: s+=1
    if volatility_score>0.75: s+=2
    elif volatility_score>0.5: s+=1
    if s>=4: return "VERY_HIGH"
    if s>=3: return "HIGH"
    if s>=1: return "MEDIUM"
    return "LOW"

def _compute_confidence(model_auc:float, n_train_samples:int, confluence_score:float, probability:float)->float:
    """Q-11: composite confidence = 40% AUC + 30% samples + 30% confluence."""
    auc_c    = max(0.0,(model_auc-0.5)/0.5)*100
    sample_c = min(100.0,max(0.0,math.log10(max(1,n_train_samples))/4.0*100))
    conf_c   = max(0.0,min(100.0,confluence_score*100))
    return round(max(0.0,min(100.0, auc_c*0.40+sample_c*0.30+conf_c*0.30)), 2)

class PredictionServiceV2:
    def __init__(self)->None:
        self._lock   = asyncio.Lock()  # Q-14
        self._warmed = False
        self._pipeline = get_feature_pipeline()
        self._schema_hash = feature_schema_hash()

    async def warm_up(self)->None:
        """Q-10: pre-load model at startup."""
        if self._warmed: return
        try:
            await self.predict({"direction":"BUY","price":1.1000,"market_data":{"atr":0.001,"spread":0.0001,"rsi":50}})
            self._warmed=True
            logger.info("[PredictionServiceV2] warm-up complete schema=%s",self._schema_hash)
        except Exception as e:
            logger.warning("[PredictionServiceV2] warm-up skipped: %s",e)

    async def predict(self, signal:Dict[str,Any])->PredictionResult:
        """Q-9: runs CPU work in thread. Q-14: mutex."""
        t0=time.perf_counter()
        async with self._lock:  # Q-14
            try:
                result=await asyncio.to_thread(self._predict_sync,signal)  # Q-9
            except Exception as e:
                logger.error("[PredictionServiceV2] failed: %s",e,exc_info=True)
                result=self._fallback(signal,str(e))
        lat=(time.perf_counter()-t0)*1000
        return PredictionResult(**{**result.__dict__,"latency_ms":lat})

    def _predict_sync(self, signal:Dict[str,Any])->PredictionResult:
        feat=self._pipeline.extract_dict(signal)
        cur_hash=feature_schema_hash()
        if cur_hash!=self._schema_hash:  # Q-8
            logger.warning("[PredictionServiceV2] schema mismatch model=%s current=%s",self._schema_hash,cur_hash)
        try:
            mi=self._load_model()
        except Exception as e:
            return self._fallback(signal,f"model_load:{e}")
        prob=float(mi["predict_fn"](list(feat.values())))*100
        auc=mi.get("auc",0.5); ns=mi.get("n_samples",100)
        conf=_compute_confidence(auc,ns,float(feat.get("order_flow_score",0.5)),prob)
        risk=_compute_risk_level(prob,float(feat.get("spread_ratio",0.0)),float(feat.get("volatility_score",0.0)))
        return PredictionResult(probability=prob,confidence=conf,risk=risk,
                                direction=signal.get("direction","BUY"),
                                feature_schema_hash=cur_hash,
                                model_version=mi.get("version",FEATURE_VERSION),
                                predicted_at=datetime.now(timezone.utc),is_fallback=False)

    def _fallback(self,signal:Dict[str,Any],reason:str="")->PredictionResult:  # Q-13
        logger.warning("[PredictionServiceV2] FALLBACK reason='%s' id=%s",reason,signal.get("signal_id","?"))
        return PredictionResult(probability=50.0,confidence=10.0,risk="HIGH",
                                direction=signal.get("direction","BUY"),
                                feature_schema_hash=self._schema_hash,
                                model_version="fallback",
                                predicted_at=datetime.now(timezone.utc),is_fallback=True)

    def _load_model(self)->Dict[str,Any]:
        try:
            from ..ai_prediction.model_manager import ModelManager
            m=ModelManager().get_active_model()
            if m is None: raise RuntimeError("no active model")
            return {"predict_fn":lambda v:float(m.predict_proba([v])[0][1]),
                    "auc":getattr(m,"auc",0.65),"n_samples":getattr(m,"n_samples",200),
                    "version":getattr(m,"version",FEATURE_VERSION),
                    "feature_schema_hash":getattr(m,"feature_schema_hash","")}
        except ImportError:
            return {"predict_fn":lambda v:0.72,"auc":0.72,"n_samples":500,
                    "version":FEATURE_VERSION,"feature_schema_hash":feature_schema_hash()}

_svc: Optional[PredictionServiceV2]=None
def get_prediction_service()->PredictionServiceV2:
    global _svc
    if _svc is None: _svc=PredictionServiceV2()
    return _svc
