// frontend/src/pages/AIpredictionsPage.tsx
import React, { useState } from "react";
import { Brain, RefreshCw } from "lucide-react";
import { analysisApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

const SYMBOLS=["EURUSD","GBPUSD","XAUUSD","USDJPY","USDCHF","AUDUSD"];

export default function AIpredictionsPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const { data, isLoading, error, refetch } = useApi(() => analysisApi.getDecision(symbol), [symbol]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Brain size={20} className="text-purple-400" /> پیش‌بینی AI</h1><p className="text-sm text-gray-400 mt-1">تحلیل Decision Engine با رأی‌گیری چندعاملی</p></div>
        <div className="flex gap-2">
          <select value={symbol} onChange={e => setSymbol(e.target.value)} className="rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <button onClick={refetch} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-gray-300 hover:text-white transition-colors"><RefreshCw size={14} /></button>
        </div>
      </div>
      {isLoading && <LoadingSpinner text="در حال پردازش AI..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
            <div className="flex items-center gap-4 mb-4">
              <div className={`text-4xl font-black ${data.action==="BUY"?"text-green-400":data.action==="SELL"?"text-red-400":"text-gray-400"}`}>{data.action}</div>
              <div className="space-y-1">
                <Badge label={`اطمینان: ${(data.confidence*100).toFixed(0)}%`} color={data.confidence>=0.7?"green":data.confidence>=0.5?"yellow":"red"} />
                <Badge label={`R:R = 1:${data.risk_reward.toFixed(2)}`} color="blue" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-xs mb-4">
              {[{ل:"ورود",v:data.entry_price.toFixed(5),c:"text-white"},{ل:"SL",v:data.stop_loss.toFixed(5),c:"text-red-400"},{ل:"TP",v:data.take_profit.toFixed(5),c:"text-green-400"}]
                .map(({l,v,c}) => <div key={l} className="bg-gray-800 rounded-lg p-3"><p className="text-gray-400">{l}</p><p className={`font-mono font-bold mt-1 ${c}`}>{v}</p></div>)}
            </div>
            <p className="text-xs text-gray-400">{data.reasoning}</p>
          </div>
          {data.votes.length>0 && (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
              <h2 className="text-sm font-semibold text-white mb-4">رأی‌های عوامل ({data.votes.length} عامل)</h2>
              <div className="space-y-2">
                {data.votes.map((v,i) => (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-gray-800">
                    <span className="text-sm text-gray-300">{v.agent}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-24 h-1.5 bg-gray-700 rounded-full overflow-hidden"><div className="h-full bg-blue-500 rounded-full" style={{width:`${v.weight*100}%`}} /></div>
                      <Badge label={v.vote} color={v.vote==="BUY"?"green":v.vote==="SELL"?"red":"gray"} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
