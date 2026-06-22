/**
 * frontend/src/pages/ModelPerformancePage.tsx
 * FIX-29: stub → BarChart دقت مدل‌ها + cards
 */
import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { aiApi } from "@/utils/api";
import type { ModelVersion } from "@/types";
import { Activity, RefreshCw } from "lucide-react";

export default function ModelPerformancePage() {
  const [models,  setModels]  = useState<ModelVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    aiApi.getModels().then(r => { if(r.success) setModels(r.data??[]); else setError(r.error??"error"); }).finally(()=>setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;

  const chartData = models.map(m => ({ name: m.symbol, accuracy: Number((m.accuracy*100).toFixed(1)), active: m.is_active }));

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Activity className="w-6 h-6 text-blue-400" />عملکرد مدل‌های ML
      </h1>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {models.length === 0
        ? <div className="text-center py-20 text-gray-500">مدلی آموزش‌ندیده</div>
        : (
          <>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h2 className="text-white font-semibold mb-4">دقت مدل‌ها (%)</h2>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="name" tick={{ fill:"#9ca3af", fontSize:12 }} />
                  <YAxis domain={[0,100]} tick={{ fill:"#9ca3af", fontSize:11 }} tickFormatter={v=>`${v}%`} />
                  <Tooltip contentStyle={{ background:"#111827", border:"1px solid #374151", borderRadius:8 }} formatter={(v:number)=>[`${v}%`,"دقت"]} />
                  <Bar dataKey="accuracy" radius={[4,4,0,0]}>
                    {chartData.map((entry,i) => <Cell key={i} fill={entry.active?"#3b82f6":"#374151"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {models.map(m => (
                <div key={`${m.symbol}-${m.version}`} className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-white font-semibold">{m.symbol}</span>
                    {m.is_active
                      ? <span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full">فعال</span>
                      : <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded-full">غیرفعال</span>}
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-gray-400 mb-1"><span>دقت</span><span className="font-mono">{(m.accuracy*100).toFixed(1)}%</span></div>
                    <div className="h-1.5 bg-gray-800 rounded-full"><div className="h-full bg-blue-500 rounded-full" style={{width:`${m.accuracy*100}%`}} /></div>
                  </div>
                  <div className="space-y-1 text-xs text-gray-400">
                    <div className="flex justify-between"><span>نسخه</span><span className="text-gray-300 font-mono">{m.version}</span></div>
                    <div className="flex justify-between"><span>نمونه‌ها</span><span className="text-gray-300 font-mono">{m.samples.toLocaleString()}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
    </div>
  );
}
