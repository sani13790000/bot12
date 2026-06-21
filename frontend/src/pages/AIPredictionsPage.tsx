/** frontend/src/pages/AIPredictionsPage.tsx -- FIX-E7: Missing page */
import { useEffect, useState } from "react";
import { aiApi } from "../utils/api";
import type { ModelVersion } from "../types";
import { Brain, RefreshCw } from "lucide-react";

export default function AIPredictionsPage() {
  const [models,  setModels]  = useState<ModelVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    aiApi.getModels()
      .then(r=>{ if(r.success) setModels(r.data??[]); else setError(r.error??"\u062e\u0637\u0627"); })
      .finally(()=>setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Brain className="w-6 h-6 text-blue-400" />\u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc</h1>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {models.length===0
          ? <div className="col-span-3 text-center py-12 text-gray-500">\u0645\u062f\u0644\u06cc \u0622\u0645\u0648\u0632\u0634 \u0646\u062f\u06cc\u062f\u0647 \u0627\u0633\u062a</div>
          : models.map(m=>(
            <div key={m.version} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-white font-semibold">{m.symbol}</span>
                {m.is_active&&<span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full">\u0641\u0639\u0627\u0644</span>}
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-400">\u062f\u0642\u062a</span><span className="text-white font-mono">{(m.accuracy*100).toFixed(1)}%</span></div>
                <div className="flex justify-between"><span className="text-gray-400">\u0646\u0645\u0648\u0646\u0647\u200c\u0647\u0627</span><span className="text-white font-mono">{m.samples.toLocaleString()}</span></div>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
