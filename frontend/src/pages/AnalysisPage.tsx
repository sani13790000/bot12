// frontend/src/pages/AnalysisPage.tsx
import React, { useState } from "react";
import { BarChart2, RefreshCw } from "lucide-react";
import { analysisApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

const SYMBOLS=["EURUSD","GBPUSD","XAUUSD","USDJPY","USDCHF","AUDUSD","NZDUSD"];
const TIMEFRAMES=["M5","M15","H1","H4","D1"];

export default function AnalysisPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [tf, setTf]         = useState("H1");
  const smc = useApi(() => analysisApi.getSMC(symbol, tf),         [symbol, tf]);
  const pa  = useApi(() => analysisApi.getPriceAction(symbol, tf), [symbol, tf]);
  const dec = useApi(() => analysisApi.getDecision(symbol),        [symbol]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><BarChart2 size={20} className="text-blue-400" /> تحلیل بازار</h1><p className="text-sm text-gray-400 mt-1">SMC + Price Action + Decision Engine</p></div>
        <div className="flex gap-2 flex-wrap">
          <select value={symbol} onChange={e => setSymbol(e.target.value)} className="rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={tf} onChange={e => setTf(e.target.value)} className="rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
            {TIMEFRAMES.map(t => <option key={t}>{t}</option>)}
          </select>
          <button onClick={() => { smc.refetch(); pa.refetch(); dec.refetch(); }} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-gray-300 hover:text-white transition-colors">
            <RefreshCw size={14} /> به‌روزرسانی
          </button>
        </div>
      </div>

      {/* Decision */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">تصمیم نهایی — Decision Engine</h2>
        {dec.isLoading && <LoadingSpinner size="sm" />}
        {dec.error    && <ErrorAlert message={dec.error} onRetry={dec.refetch} />}
        {dec.data && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <Badge label={dec.data.action} color={dec.data.action==="BUY"?"green":dec.data.action==="SELL"?"red":"gray"} />
              <Badge label={`اطمینان: ${(dec.data.confidence*100).toFixed(0)}%`} color={dec.data.confidence>=0.7?"green":dec.data.confidence>=0.5?"yellow":"red"} />
              <Badge label={`R:R = 1:${dec.data.risk_reward.toFixed(2)}`} color="blue" />
            </div>
            <p className="text-xs text-gray-400">{dec.data.reasoning}</p>
            {dec.data.votes.length>0 && (
              <div><p className="text-xs text-gray-500 mb-2">رأی‌های عوامل:</p>
                <div className="flex flex-wrap gap-2">
                  {dec.data.votes.map((v,i) => (
                    <div key={i} className="text-xs bg-gray-800 rounded-lg px-2 py-1">
                      <span className="text-gray-400">{v.agent}:</span>{" "}
                      <span className={v.vote==="BUY"?"text-green-400":v.vote==="SELL"?"text-red-400":"text-gray-400"}>{v.vote}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* SMC */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">SMC Analysis</h2>
        {smc.isLoading && <LoadingSpinner size="sm" />}
        {smc.error    && <ErrorAlert message={smc.error} onRetry={smc.refetch} />}
        {smc.data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div><p className="text-gray-400">Bias</p><Badge label={smc.data.bias} color={smc.data.bias==="bullish"?"green":smc.data.bias==="bearish"?"red":"gray"} /></div>
            <div><p className="text-gray-400 mb-1">Order Blocks</p><p className="text-white">{smc.data.order_blocks.length} ناحیه</p></div>
            <div><p className="text-gray-400 mb-1">FVG</p><p className="text-white">{smc.data.fvg_zones.length} ناحیه</p></div>
            <div><p className="text-gray-400 mb-1">BOS/CHoCH</p><p className="text-white">{smc.data.bos_points.length} نقطه</p></div>
          </div>
        )}
      </div>

      {/* Price Action */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">Price Action</h2>
        {pa.isLoading && <LoadingSpinner size="sm" />}
        {pa.error    && <ErrorAlert message={pa.error} onRetry={pa.refetch} />}
        {pa.data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div><p className="text-gray-400 mb-1">روند</p><Badge label={pa.data.trend} color={pa.data.trend==="up"?"green":pa.data.trend==="down"?"red":"gray"} /></div>
            <div><p className="text-gray-400 mb-1">RSI</p><p className={`font-mono font-bold ${pa.data.rsi>70?"text-red-400":pa.data.rsi<30?"text-green-400":"text-white"}`}>{pa.data.rsi.toFixed(1)}</p></div>
            <div><p className="text-gray-400 mb-1">MACD</p><p className={`font-mono ${pa.data.macd.histogram>=0?"text-green-400":"text-red-400"}`}>{pa.data.macd.value.toFixed(5)}</p></div>
            <div><p className="text-gray-400 mb-1">الگوها</p><p className="text-white">{pa.data.patterns.length} الگو</p></div>
          </div>
        )}
      </div>
    </div>
  );
}
