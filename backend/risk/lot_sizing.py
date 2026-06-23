from __future__ import annotations
import asyncio, logging, math, time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
logger = logging.getLogger('risk.lot_sizing')
_MIN_LOT_GLOBAL=0.01; _MAX_LOT_GLOBAL=100.0; _PIP_CACHE_TTL=60.0
_PIP_VALUE_TABLE: Dict[str, float] = {
    'EURUSD':10.0,'GBPUSD':10.0,'AUDUSD':10.0,'NZDUSD':10.0,
    'USDCAD':7.7,'USDCHF':10.7,'USDJPY':6.7,
    'EURGBP':12.9,'EURJPY':6.7,'EURAUD':10.0,'EURCHF':10.7,'EURNZD':10.0,'EURCAD':7.7,
    'GBPJPY':6.7,'GBPAUD':10.0,'GBPCHF':10.7,'GBPNZD':10.0,'GBPCAD':7.7,
    'AUDJPY':6.7,'AUDCAD':7.7,'AUDCHF':10.7,'AUDNZD':10.0,
    'CADJPY':6.7,'CADCHF':10.7,'CHFJPY':6.7,
    'NZDCAD':7.7,'NZDCHF':10.7,'NZDJPY':6.7,
    'XAUUSD':1.0,'XAGUSD':50.0,'XPTUSD':1.0,'XPDUSD':1.0,
    'USOIL':1.0,'UKOIL':1.0,'NATGAS':1.0,
    'US30':1.0,'US500':1.0,'NAS100':1.0,'GER40':1.0,'UK100':1.0,'JPN225':0.1,'AUS200':1.0,
    'BTCUSD':1.0,'ETHUSD':1.0,'LTCUSD':1.0,'XRPUSD':1.0,
}
_SYMBOL_ALIASES: Dict[str, str] = {
    'GOLD':'XAUUSD','SILVER':'XAGUSD','PLATINUM':'XPTUSD','PALLADIUM':'XPDUSD',
    'BTC':'BTCUSD','ETH':'ETHUSD','LTC':'LTCUSD','XRP':'XRPUSD',
    'WTI':'USOIL','BRENT':'UKOIL','DAX':'GER40','DAX40':'GER40','FTSE':'UK100',
    'SP500':'US500','SPX500':'US500','SPX':'US500','DOW':'US30','DJ30':'US30',
    'NIKKEI':'JPN225','ASX200':'AUS200',
}
class UnknownSymbolError(ValueError): pass
@dataclass
class LotSizingConfig:
    risk_percent:float=1.0; min_lot:float=0.01; max_lot:float=10.0
    lot_step:float=0.01; kelly_fraction:float=0.5
@dataclass
class LotSizeResult:
    lot_size:float; pip_value_used:float; risk_usd:float
    risk_percent:float; kelly_lot:float; source:str; symbol:str; method:str
class LotSizer:
    def __init__(self,config=None,mt5_connector=None):
        self.config=config or LotSizingConfig(); self._mt5=mt5_connector
        self._cache:Dict[str,Tuple[float,float,str]]={}; self._lock=asyncio.Lock()
    async def get_pip_value(self,symbol:str)->Tuple[float,str]:
        sym=symbol.upper().strip()
        async with self._lock:
            now=time.monotonic(); cached=self._cache.get(sym)
            if cached and (now-cached[1])<_PIP_CACHE_TTL: return cached[0],cached[2]
        if self._mt5 is not None:
            try:
                pv,src=await self._from_mt5(sym)
                async with self._lock: self._cache[sym]=(pv,time.monotonic(),src)
                return pv,src
            except Exception as e: logger.warning('MT5 pip failed %s:%s',sym,e)
        c=self._resolve_canonical(sym); s=_PIP_VALUE_TABLE.get(c)
        if s is not None:
            src='static_table' if c==sym else f'static_table({c})'
            async with self._lock: self._cache[sym]=(s,time.monotonic(),src)
            return s,src
        raise UnknownSymbolError(f"No pip value for '{sym}'")
    async def calculate(self,balance:float,stop_loss_pips:float,symbol:str,
            atr_pips:float=0.0,win_rate:float=0.55,avg_rr:float=1.5,
            volatility_ratio:float=1.0,override_risk_pct:Optional[float]=None)->LotSizeResult:
        sym=symbol.upper().strip()
        if stop_loss_pips<=0: raise ValueError(f'stop_loss_pips>0 required,got {stop_loss_pips}')
        if balance<=0: raise ValueError(f'balance>0 required,got {balance}')
        pip_val,source=await self.get_pip_value(sym)
        eff_risk=(override_risk_pct if (override_risk_pct is not None and override_risk_pct>0)
                  else self.config.risk_percent)
        risk_usd=balance*(eff_risk/100.0)*volatility_ratio
        fixed_lot=risk_usd/(stop_loss_pips*pip_val)
        kp=max(0.0,min(0.25,(win_rate-(1-win_rate)/avg_rr) if avg_rr>0 else 0.0))
        kl=(balance*kp*self.config.kelly_fraction)/(stop_loss_pips*pip_val)
        bl=0.70*fixed_lot+0.30*kl
        fl=max(self.config.min_lot,min(self.config.max_lot,max(_MIN_LOT_GLOBAL,min(_MAX_LOT_GLOBAL,bl))))
        fl=math.floor(fl/self.config.lot_step)*self.config.lot_step
        fl=max(self.config.min_lot,round(fl,2))
        ar=(fl*stop_loss_pips*pip_val/balance*100) if balance>0 else 0.0
        m=('min_fallback' if fl<=self.config.min_lot else 'kelly_blend' if kp>0 else 'fixed_risk')
        return LotSizeResult(lot_size=fl,pip_value_used=pip_val,risk_usd=round(fl*stop_loss_pips*pip_val,2),
            risk_percent=round(ar,3),kelly_lot=round(kl,4),source=source,symbol=sym,method=m)
    @staticmethod
    def _resolve_canonical(sym):
        if sym in _SYMBOL_ALIASES: return _SYMBOL_ALIASES[sym]
        for t in range(1,5):
            c=sym[:-t]
            if c in _PIP_VALUE_TABLE: return c
            if c in _SYMBOL_ALIASES: return _SYMBOL_ALIASES[c]
        return sym
    async def _from_mt5(self,sym):
        info=await asyncio.to_thread(self._mt5.get_symbol_info,sym)
        if info is None: raise RuntimeError(f'MT5 None for {sym}')
        tv=getattr(info,'trade_tick_value',None); ts=getattr(info,'trade_tick_size',None)
        if tv and tv>0 and ts and ts>0:
            pt=getattr(info,'point',ts); ps=pt*10 if pt<=0.001 else pt
            return tv*(ps/ts),'mt5_tick_value'
        ct=getattr(info,'trade_contract_size',None)
        if ct and ct>0 and ts and ts>0: return ts*ct,'mt5_contract'
        raise RuntimeError(f'MT5 pip fail {sym}')
_lot_sizer=None
def get_lot_sizer(config=None,mt5_connector=None):
    global _lot_sizer
    if _lot_sizer is None: _lot_sizer=LotSizer(config=config,mt5_connector=mt5_connector)
    return _lot_sizer
