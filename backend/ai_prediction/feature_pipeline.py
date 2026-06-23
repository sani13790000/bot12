"""Feature Pipeline v3 — Phase Q fixes Q-1..Q-7."""
from __future__ import annotations
import hashlib, json, logging, math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
FEATURE_VERSION = "3.0.0"
_FEATURE_NAMES: Optional[List[str]] = None

SESSIONS   = {"SYDNEY":(22,7),"TOKYO":(0,9),"LONDON":(7,16),"NEW_YORK":(12,21)}
KILL_ZONES = {"LONDON_OPEN":(7,9),"NY_OPEN":(12,14),"ASIA_OPEN":(0,2),"LONDON_CLOSE":(15,17)}


def get_feature_names() -> List[str]:
    """Q-2: build once and cache. Same list used for training and inference."""
    global _FEATURE_NAMES
    if _FEATURE_NAMES is not None:
        return list(_FEATURE_NAMES)
    smc=["bos_detected","choch_detected","ob_quality","ob_size_pips",
         "fvg_size_pips","fvg_filled_pct","liquidity_swept","sweep_type",
         "premium_discount_zone","pd_score","structure_aligned","mss_count",
         "inducement_detected","order_flow_score"]
    pa =["candle_pattern_score","candle_quality","direction_aligned",
         "timeframe_weight","wick_ratio","body_ratio","close_position","engulf_strength"]
    mkt=["atr_normalized","spread_ratio","volatility_score","trend_strength",
         "adx_value","rsi_14","macd_histogram","bb_width_pct"]
    t  =["session_score","hour_sin","hour_cos","day_of_week",
         "is_kill_zone","minutes_to_session_open","is_news_window","london_ny_overlap"]
    _FEATURE_NAMES = smc+pa+mkt+t
    assert len(_FEATURE_NAMES)==38, f"expected 38 got {len(_FEATURE_NAMES)}"
    return list(_FEATURE_NAMES)


def feature_schema_hash() -> str:
    """Q-5: MD5(feature_names[:8]) — detects train/predict schema mismatch."""
    return hashlib.md5(json.dumps(get_feature_names()).encode()).hexdigest()[:8]


def _safe_float(value: Any, default: float=0.0, name: str="") -> float:
    """Q-4: replace NaN/inf/None with safe default, log warning."""
    try:
        v=float(value)
        if math.isnan(v) or math.isinf(v):
            if name: logger.warning("[FeaturePipeline] NaN/inf in '%s', using %.3f",name,default)
            return default
        return v
    except (TypeError,ValueError):
        if name: logger.warning("[FeaturePipeline] invalid '%s'=%r, using %.3f",name,value,default)
        return default


def _broker_hour(signal: Dict[str,Any]) -> int:
    """Q-6: broker_hour from signal takes priority over UTC."""
    if "broker_hour" in signal: return int(signal["broker_hour"])%24
    ts=signal.get("generated_at") or signal.get("timestamp")
    if ts:
        try:
            if isinstance(ts,str): dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
            elif isinstance(ts,(int,float)): dt=datetime.fromtimestamp(ts,tz=timezone.utc)
            else: dt=ts
            return dt.hour
        except Exception: pass
    return datetime.now(timezone.utc).hour  # Q-3 FIX


def _session_score(hour:int)->float:
    return sum(1 for _,(s,e) in SESSIONS.items() if (s<=hour<e)or(s>e and(hour>=s or hour<e)))/4.0

def _is_kill_zone(hour:int)->float:
    return next((1.0 for _,(s,e) in KILL_ZONES.items() if s<=hour<e),0.0)

def _london_ny_overlap(hour:int)->float: return 1.0 if 12<=hour<16 else 0.0

def _minutes_to_session_open(hour:int,minute:int=0)->float:
    cur=hour*60+minute
    return float(min((o-cur)%(24*60) for o in [7*60,12*60]))


@dataclass
class FeatureNormalizer:
    """Q-1: min-max normalization — fit on train set only to prevent leakage."""
    mins:  Dict[str,float] = field(default_factory=dict)
    maxs:  Dict[str,float] = field(default_factory=dict)
    fitted:bool = False

    def fit(self, rows:List[Dict[str,float]])->None:
        if not rows: return
        for name in get_feature_names():
            vals=[r[name] for r in rows if name in r and not math.isnan(r[name])]
            if vals: self.mins[name]=min(vals); self.maxs[name]=max(vals)
        self.fitted=True

    def transform(self, row:Dict[str,float])->Dict[str,float]:
        if not self.fitted: return row
        out={}
        for name,val in row.items():
            lo,hi=self.mins.get(name,0.0),self.maxs.get(name,1.0)
            out[name]=0.0 if hi-lo<1e-9 else max(0.0,min(1.0,(val-lo)/(hi-lo)))
        return out

    def to_dict(self)->Dict[str,Any]: return {"mins":self.mins,"maxs":self.maxs,"fitted":self.fitted}

    @classmethod
    def from_dict(cls,d:Dict[str,Any])->"FeatureNormalizer":
        o=cls(); o.mins=d.get("mins",{}); o.maxs=d.get("maxs",{}); o.fitted=d.get("fitted",False)
        return o


class FeaturePipeline:
    """Production feature extractor — used identically in training and inference."""
    VERSION = FEATURE_VERSION

    def extract(self, signal:Dict[str,Any])->Tuple[List[float],List[str]]:
        names=get_feature_names()
        raw=self._extract_raw(signal)
        vec=[_safe_float(raw.get(n,0.0),0.0,n) for n in names]
        if len(vec)!=38: raise ValueError(f"expected 38 features, got {len(vec)}")
        return vec,names

    def extract_dict(self,signal:Dict[str,Any])->Dict[str,float]:
        vec,names=self.extract(signal); return dict(zip(names,vec))

    def _extract_raw(self,signal:Dict[str,Any])->Dict[str,Any]:
        hour=_broker_hour(signal); minute=int(signal.get("minute",0))
        smc=signal.get("smc_data") or {}; ob=smc.get("order_block") or smc.get("ob") or {}
        fvg=smc.get("fvg") or {}; pa=signal.get("pa_data") or {}; candle=pa.get("candle") or {}
        mkt=signal.get("market_data") or {}
        atr=_safe_float(mkt.get("atr"),0.0,"atr"); spread=_safe_float(mkt.get("spread"),0.0,"spread")
        price=_safe_float(signal.get("price") or signal.get("entry_price"),1.0,"price")
        hr=2*math.pi*hour/24
        st={"HIGH":1.0,"LOW":-1.0,"BOTH":0.5}; zn={"PREMIUM":1.0,"DISCOUNT":-1.0,"EQUILIBRIUM":0.0}
        return {
            "bos_detected":float(bool(smc.get("bos"))),
            "choch_detected":float(bool(smc.get("choch"))),
            "ob_quality":_safe_float(ob.get("quality"),0.0,"ob_quality"),
            "ob_size_pips":_safe_float(ob.get("size_pips"),0.0,"ob_size_pips"),
            "fvg_size_pips":_safe_float(fvg.get("size_pips"),0.0,"fvg_size_pips"),
            "fvg_filled_pct":_safe_float(fvg.get("filled_pct"),0.0,"fvg_filled_pct"),
            "liquidity_swept":float(bool(smc.get("liquidity_swept"))),
            "sweep_type":st.get(str(smc.get("sweep_type","")),0.0),
            "premium_discount_zone":zn.get(str(smc.get("pd_zone","")),0.0),
            "pd_score":_safe_float(smc.get("pd_score"),0.0,"pd_score"),
            "structure_aligned":float(bool(smc.get("structure_aligned"))),
            "mss_count":_safe_float(smc.get("mss_count"),0.0,"mss_count"),
            "inducement_detected":float(bool(smc.get("inducement"))),
            "order_flow_score":_safe_float(smc.get("order_flow_score"),0.0,"order_flow_score"),
            "candle_pattern_score":_safe_float(pa.get("pattern_score"),0.0,"candle_pattern_score"),
            "candle_quality":_safe_float(pa.get("quality"),0.0,"candle_quality"),
            "direction_aligned":float(pa.get("direction","")==signal.get("direction","")),
            "timeframe_weight":_safe_float(pa.get("timeframe_weight"),0.5,"timeframe_weight"),
            "wick_ratio":_safe_float(candle.get("wick_ratio"),0.0,"wick_ratio"),
            "body_ratio":_safe_float(candle.get("body_ratio"),0.5,"body_ratio"),
            "close_position":_safe_float(candle.get("close_position"),0.5,"close_position"),
            "engulf_strength":_safe_float(pa.get("engulf_strength"),0.0,"engulf_strength"),
            "atr_normalized":_safe_float((atr/price) if price>0 else 0.0,0.0,"atr_normalized"),
            "spread_ratio":_safe_float((spread/atr) if atr>0 else 0.0,0.0,"spread_ratio"),
            "volatility_score":_safe_float(mkt.get("volatility_score"),0.0,"volatility_score"),
            "trend_strength":_safe_float(mkt.get("trend_strength"),0.0,"trend_strength"),
            "adx_value":_safe_float(mkt.get("adx"),0.0,"adx_value"),
            "rsi_14":_safe_float(mkt.get("rsi"),50.0,"rsi_14"),
            "macd_histogram":_safe_float(mkt.get("macd_hist"),0.0,"macd_histogram"),
            "bb_width_pct":_safe_float(mkt.get("bb_width_pct"),0.0,"bb_width_pct"),
            "session_score":_session_score(hour),
            "hour_sin":math.sin(hr),"hour_cos":math.cos(hr),
            "day_of_week":float(signal.get("day_of_week",0)),
            "is_kill_zone":_is_kill_zone(hour),
            "minutes_to_session_open":_minutes_to_session_open(hour,minute)/(24*60),
            "is_news_window":float(bool(signal.get("news_window"))),
            "london_ny_overlap":_london_ny_overlap(hour),
        }

_pipeline: Optional[FeaturePipeline]=None
def get_feature_pipeline()->FeaturePipeline:
    global _pipeline
    if _pipeline is None: _pipeline=FeaturePipeline()
    return _pipeline
