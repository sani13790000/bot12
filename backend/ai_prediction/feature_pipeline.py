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
    opens=[7,12,22,0]
    return min((o-hour)*60-minute for o in opens if (o-hour)*60-minute>=0) if any((o-hour)*60-minute>=0 for o in opens) else 0.0


def build_feature_vector(signal: Dict[str, Any]) -> List[float]:
    """
    Q-1 FIX: Build 38-feature vector from signal dict.
    Returns list of float in exact order of get_feature_names().
    """
    smc = signal.get("smc_analysis", signal)  # flat or nested
    pa  = signal.get("price_action", signal)
    mkt = signal.get("market",       signal)
    hour = _broker_hour(signal)
    minute = int(signal.get("minute", 0))

    direction = str(signal.get("direction", "NEUTRAL")).upper()
    dir_factor = 1.0 if direction == "BUY" else (-1.0 if direction == "SELL" else 0.0)

    # SMC features (14)
    f_smc = [
        _safe_float(smc.get("bos_detected",    False), name="bos_detected"),
        _safe_float(smc.get("choch_detected",  False), name="choch_detected"),
        _safe_float(smc.get("ob_quality",      0.0),   name="ob_quality"),
        _safe_float(smc.get("ob_size_pips",    0.0),   name="ob_size_pips"),
        _safe_float(smc.get("fvg_size_pips",   0.0),   name="fvg_size_pips"),
        _safe_float(smc.get("fvg_filled_pct",  0.0),   name="fvg_filled_pct"),
        _safe_float(smc.get("liquidity_sweep", False), name="liquidity_swept"),
        _safe_float(smc.get("sweep_type",      0.0),   name="sweep_type"),
        _safe_float(smc.get("in_premium_zone", False), name="premium_discount_zone"),
        _safe_float(smc.get("smc_confidence",  0.5),   name="pd_score"),
        _safe_float(smc.get("htf_alignment",   False), name="structure_aligned"),
        _safe_float(smc.get("mss_count",       0),     name="mss_count"),
        _safe_float(smc.get("inducement",      False), name="inducement_detected"),
        _safe_float(smc.get("order_flow",      0.5),   name="order_flow_score"),
    ]
    # PA features (8)
    f_pa = [
        _safe_float(pa.get("candle_pattern_score", 0.5), name="candle_pattern_score"),
        _safe_float(pa.get("candle_quality",       0.5), name="candle_quality"),
        _safe_float(dir_factor,                          name="direction_aligned"),
        _safe_float(pa.get("timeframe_weight",     1.0), name="timeframe_weight"),
        _safe_float(pa.get("wick_ratio",           0.3), name="wick_ratio"),
        _safe_float(pa.get("body_ratio",           0.6), name="body_ratio"),
        _safe_float(pa.get("close_position",       0.5), name="close_position"),
        _safe_float(pa.get("engulf_strength",      0.0), name="engulf_strength"),
    ]
    # Market features (8)
    f_mkt = [
        _safe_float(mkt.get("atr_normalized",   1.0), name="atr_normalized"),
        _safe_float(mkt.get("spread_ratio",     1.0), name="spread_ratio"),
        _safe_float(mkt.get("volatility_score", 0.5), name="volatility_score"),
        _safe_float(mkt.get("trend_strength",   0.5), name="trend_strength"),
        _safe_float(mkt.get("adx_value",        25.0),name="adx_value"),
        _safe_float(mkt.get("rsi_14",           50.0),name="rsi_14"),
        _safe_float(mkt.get("macd_histogram",   0.0), name="macd_histogram"),
        _safe_float(mkt.get("bb_width_pct",     1.0), name="bb_width_pct"),
    ]
    # Time features (8)
    f_time = [
        _session_score(hour),
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        _safe_float(signal.get("day_of_week", datetime.now(timezone.utc).weekday())),
        _is_kill_zone(hour),
        _minutes_to_session_open(hour, minute),
        _safe_float(signal.get("is_news_window", False), name="is_news_window"),
        _london_ny_overlap(hour),
    ]
    return f_smc + f_pa + f_mkt + f_time


def build_features_from_context(context: Dict[str, Any]) -> "np.ndarray":
    """
    Phase G NEW: Build 38-feature numpy array from enriched context dict.
    Used by PredictionService._extract_features().
    """
    import numpy as np
    feats = build_feature_vector(context)
    if len(feats) != 38:
        logger.warning("[FeaturePipeline] expected 38 features, got %d", len(feats))
    return np.array([feats], dtype=np.float32)


@dataclass
class FeatureVector:
    """Typed wrapper for a single feature vector."""
    values: List[float]
    feature_names: List[str] = field(default_factory=get_feature_names)
    schema_hash: str = field(default_factory=feature_schema_hash)

    def to_numpy(self) -> "np.ndarray":
        import numpy as np
        return np.array(self.values, dtype=np.float32)

    @classmethod
    def from_signal(cls, signal: Dict[str, Any]) -> "FeatureVector":
        """Q-1: build from signal dict, validate length."""
        values = build_feature_vector(signal)
        if len(values) != 38:
            raise ValueError(f"[FeaturePipeline] expected 38, got {len(values)}")
        return cls(values=values)
