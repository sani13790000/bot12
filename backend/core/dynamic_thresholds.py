from __future__ import annotations
import logging,math,os
from dataclasses import dataclass
from typing import Callable,Dict,Optional
logger=logging.getLogger(__name__)

@dataclass
class ThresholdSpec:
    name:str; default:float; min_val:float; max_val:float; description:str; env_key:str=""
    def validate(self,v):
        if not math.isfinite(v): raise ValueError(f"{self.name}: not finite: {v}")
        if not(self.min_val<=v<=self.max_val): raise ValueError(f"{self.name}: {v} outside [{self.min_val},{self.max_val}]")
        return v

_SPECS:Dict[str,ThresholdSpec]={s.name:s for s in [
    ThresholdSpec("risk.max_risk_pct",1.0,0.1,10.0,"Max risk per trade %","MT5_THRESH_MAX_RISK_PCT"),
    ThresholdSpec("risk.max_drawdown_pct",5.0,1.0,50.0,"Daily drawdown halt %","MT5_THRESH_MAX_DD_PCT"),
    ThresholdSpec("risk.max_open_trades",10.0,1.0,100.0,"Max concurrent open trades","MT5_THRESH_MAX_TRADES"),
    ThresholdSpec("risk.max_correlated_pairs",3.0,1.0,20.0,"Max correlated pairs","MT5_THRESH_MAX_CORR_PAIRS"),
    ThresholdSpec("risk.correlation_block",0.75,0.3,1.0,"Correlation block threshold","MT5_THRESH_CORR_BLOCK"),
    ThresholdSpec("risk.kelly_fraction",0.25,0.05,1.0,"Kelly fraction","MT5_THRESH_KELLY_FRAC"),
    ThresholdSpec("circuit.failure_count",5.0,1.0,50.0,"Failures before OPEN","MT5_THRESH_CB_FAIL_COUNT"),
    ThresholdSpec("circuit.window_seconds",60.0,10.0,600.0,"Sliding window s","MT5_THRESH_CB_WINDOW_S"),
    ThresholdSpec("circuit.half_open_timeout",30.0,5.0,300.0,"Half-open timeout s","MT5_THRESH_CB_HALF_OPEN_S"),
    ThresholdSpec("circuit.success_to_close",2.0,1.0,10.0,"Successes to re-close","MT5_THRESH_CB_SUCCESS"),
    ThresholdSpec("slippage.base_deviation",10.0,1.0,100.0,"Base deviation pts","MT5_THRESH_SLIP_BASE"),
    ThresholdSpec("slippage.max_deviation",50.0,10.0,500.0,"Max deviation pts","MT5_THRESH_SLIP_MAX"),
    ThresholdSpec("slippage.atr_multiplier",2.0,0.5,10.0,"ATR spike mult","MT5_THRESH_SLIP_ATR_MULT"),
    ThresholdSpec("slippage.spread_multiplier",1.5,0.5,10.0,"Spread spike mult","MT5_THRESH_SLIP_SPREAD_MULT"),
    ThresholdSpec("recon.interval_seconds",10.0,5.0,300.0,"Recon interval s","MT5_THRESH_RECON_INTERVAL"),
    ThresholdSpec("recon.orphan_age_seconds",60.0,10.0,3600.0,"Orphan age s","MT5_THRESH_ORPHAN_AGE_S"),
    ThresholdSpec("signal.min_confidence",60.0,30.0,99.0,"Min confidence %","MT5_THRESH_SIG_MIN_CONF"),
    ThresholdSpec("signal.min_rr_ratio",1.5,0.5,20.0,"Min R:R ratio","MT5_THRESH_SIG_MIN_RR"),
    ThresholdSpec("signal.expiry_seconds",300.0,30.0,3600.0,"Signal expiry s","MT5_THRESH_SIG_EXPIRY_S"),
    ThresholdSpec("regime.adx_trend",25.0,10.0,60.0,"ADX trending thresh","MT5_THRESH_ADX_TREND"),
    ThresholdSpec("regime.adx_strong",40.0,20.0,80.0,"ADX strong-trend","MT5_THRESH_ADX_STRONG"),
    ThresholdSpec("regime.vol_high_zscore",1.5,0.5,5.0,"ATR z high-vol","MT5_THRESH_VOL_HIGH_Z"),
    ThresholdSpec("regime.vol_low_zscore",-1.0,-5.0,-0.1,"ATR z low-vol","MT5_THRESH_VOL_LOW_Z"),
    ThresholdSpec("regime.bb_ranging_pct",0.03,0.005,0.2,"BB width% ranging","MT5_THRESH_BB_RANGE_PCT"),
    ThresholdSpec("learning.drift_threshold",0.08,0.01,0.5,"Drift -> retrain","MT5_THRESH_DRIFT"),
    ThresholdSpec("learning.min_accuracy",0.55,0.5,0.99,"Min test accuracy","MT5_THRESH_MIN_ACC"),
    ThresholdSpec("learning.retrain_interval",3600.0,300.0,86400.0,"Retrain interval s","MT5_THRESH_RETRAIN_S"),
    ThresholdSpec("lot.min",0.01,0.01,1.0,"Min lot size","MT5_THRESH_LOT_MIN"),
    ThresholdSpec("lot.max",100.0,1.0,500.0,"Max lot size","MT5_THRESH_LOT_MAX"),
    ThresholdSpec("lot.max_delta_per_cycle",0.05,0.01,0.5,"Max weight delta/cycle","MT5_THRESH_LOT_MAX_DELTA"),
]}

class ThresholdRegistry:
    """Central store for all runtime-configurable thresholds. Thread-safe via GIL."""
    def __init__(self):
        self._overrides:Dict[str,float]={}
        self._listeners:Dict[str,list]={}
        self._load_from_env()

    def get(self,name:str)->float:
        if name not in _SPECS: raise KeyError(f"Unknown threshold '{name}'")
        return self._overrides.get(name,_SPECS[name].default)

    def set(self,name:str,value:float,source:str="runtime")->None:
        spec=_SPECS.get(name)
        if spec is None: raise KeyError(f"Unknown threshold '{name}'")
        v=spec.validate(value)
        old=self._overrides.get(name,spec.default)
        self._overrides[name]=v
        logger.info("threshold %s: %.4f -> %.4f (source=%s)",name,old,v,source)
        for cb in self._listeners.get(name,[]):
            try: cb(name,old,v)
            except Exception as e: logger.error("listener error %s: %s",name,e)

    def reset(self,name:str)->None:
        self._overrides.pop(name,None)

    def reset_all(self)->None:
        self._overrides.clear()

    def snapshot(self)->Dict[str,float]:
        return {n:self.get(n) for n in _SPECS}

    def on_change(self,name:str,callback:Callable)->None:
        self._listeners.setdefault(name,[]).append(callback)

    def describe(self,name:str)->str:
        spec=_SPECS[name]; v=self.get(name); src="override" if name in self._overrides else "default"
        return f"{name}: {v:.4f} [{spec.min_val},{spec.max_val}] ({src}) - {spec.description}"

    def _load_from_env(self):
        for name,spec in _SPECS.items():
            if spec.env_key and spec.env_key in os.environ:
                try:
                    v=float(os.environ[spec.env_key]); spec.validate(v); self._overrides[name]=v
                except(ValueError,TypeError) as e:
                    logger.warning("env %s invalid: %s",spec.env_key,e)

_registry:Optional[ThresholdRegistry]=None
def get_thresholds()->ThresholdRegistry:
    global _registry
    if _registry is None: _registry=ThresholdRegistry()
    return _registry

def T(name:str)->float:
    """Quick accessor: T('risk.max_risk_pct')"""
    return get_thresholds().get(name)
