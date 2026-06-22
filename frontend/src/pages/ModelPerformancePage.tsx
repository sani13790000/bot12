/**
 * frontend/src/pages/ModelPerformancePage.tsx
 * FIX-FE16: stub -> real bar chart + model cards
 */
import { useEffect, useState } from "react";
import { aiApi } from "../utils/api";
import type { ModelVersion } from "../types";
import { Activity, RefreshCw, CheckCircle, Circle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function ModelPerformancePage() {
  const [models,  setModels]  = useState<ModelVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    aiApi.getModels()
      .then(r => { if (r.success) setModels(r.data ?? []); else setError(r.error ?? "\u062e\u0637\u0627"); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Activity className="w-6 h-6 text-blue-400" /> \u0639\u0645\u0644\u06a9\u0631\u062f \u0645\u062f\u0644
      </h1>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {models.length === 0
        ? <div className="bg-gray-900 rounded-xl border border-gray-800 p-10 text-center text-gray-500">\u0645\u062f\u0644\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f</div>
        : <>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <p className="text-sm text-gray-400 mb-4">\u062f\u0642\u062a \u0645\u062f\u0644\u200c\u0647\u0627 (%)</p>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={models.map(m => ({ name: m.symbol, accuracy: +(m.accuracy * 100).toFixed(1) }))}>
                  <XAxis dataKey="name" tick={{ fill: "#6b7280", fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: "#6b7280", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8 }}
                    formatter={(v: number) => [`${v}%`, "\u062f\u0642\u062a"]} />
                  <Bar dataKey="accuracy" fill="#3b82f6" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {models.map(m => (
                <div key={m.version} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-white font-semibold">{m.symbol}</span>
                    {m.is_active ? <CheckCircle className="w-4 h-4 text-green-400" /> : <Circle className="w-4 h-4 text-gray-600" />}
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-gray-400">\u062f\u0642\u062a</span><span className="text-white font-mono">{(m.accuracy * 100).toFixed(1)}%</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">\u0646\u0645\u0648\u0646\u0647\u200c\u0647\u0627</span><span className="text-white font-mono">{m.samples.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">\u0646\u0633\u062e\u0647</span><span className="text-gray-500 font-mono text-xs">{m.version.slice(0,8)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </>
      }
    </div>
  );
}
