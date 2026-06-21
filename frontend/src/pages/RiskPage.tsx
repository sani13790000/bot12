/** frontend/src/pages/RiskPage.tsx -- FIX-E8: Missing page */
import { useEffect, useState } from "react";
import { riskApi } from "../utils/api";
import type { RiskStatus } from "../types";
import { Shield, AlertTriangle, RefreshCw } from "lucide-react";

export default function RiskPage() {
  const [risk,    setRisk]    = useState<RiskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    riskApi.getStatus()
      .then(r=>{ if(r.success) setRisk(r.data); else setError(r.error??"\u062e\u0637\u0627"); })
      .finally(()=>setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Shield className="w-6 h-6 text-blue-400" />\u0645\u062f\u06cc\u0631\u06cc\u062a \u0631\u06cc\u0633\u06a9</h1>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {risk?.circuit_breaker_open && (
        <div className="p-4 bg-red-900/30 border border-red-600 rounded-xl flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
          <p className="text-red-300 font-medium">Circuit Breaker \u0641\u0639\u0627\u0644 \u2014 \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0645\u062a\u0648\u0642\u0641 \u0634\u062f\u0647</p>
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          { label: "Exposure \u0641\u0639\u0644\u06cc", value: risk?`${risk.current_exposure.toFixed(1)}%`:"\u2014", color:"blue" },
          { label: "\u0636\u0631\u0631 \u0631\u0648\u0632\u0627\u0646\u0647", value: risk?`$${risk.daily_loss.toFixed(2)}`:"\u2014", color:"red" },
          { label: "\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u0632", value: risk?`${risk.open_trades_count}/${risk.max_trades}`:"\u2014", color:"purple" },
        ].map(({label,value,color})=>(
          <div key={label} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
            <p className="text-gray-400 text-sm mb-2">{label}</p>
            <p className={`text-2xl font-bold ${color==="red"?"text-red-400":color==="blue"?"text-blue-400":"text-purple-400"}`}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
