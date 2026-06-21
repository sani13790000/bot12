/** frontend/src/pages/AnalyticsPage.tsx -- FIX-E9: Missing page */
import { useEffect, useState } from "react";
import { analyticsApi } from "../utils/api";
import type { AnalyticsMetrics } from "../types";
import { BarChart2, RefreshCw } from "lucide-react";

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<AnalyticsMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.getMetrics(30).then(r=>{ if(r.success) setMetrics(r.data); }).finally(()=>setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2"><BarChart2 className="w-6 h-6 text-blue-400" />\u0622\u0646\u0627\u0644\u06cc\u062a\u06cc\u06a9\u0633 \u06f3\u06f0 \u0631\u0648\u0632\u0647</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {label:"\u06a9\u0644 \u0645\u0639\u0627\u0645\u0644\u0627\u062a",value:metrics?.total_trades},
          {label:"Win Rate",value:metrics?`${metrics.win_rate.toFixed(1)}%`:"\u2014"},
          {label:"Profit Factor",value:metrics?.profit_factor?.toFixed(2)},
          {label:"Max Drawdown",value:metrics?`${metrics.max_drawdown.toFixed(1)}%`:"\u2014"},
          {label:"\u06a9\u0644 \u0633\u0648\u062f",value:metrics?`$${metrics.total_profit.toFixed(2)}`:"\u2014"},
          {label:"\u0628\u0647\u062a\u0631\u06cc\u0646 \u0645\u0639\u0627\u0645\u0644\u0647",value:metrics?`$${metrics.best_trade.toFixed(2)}`:"\u2014"},
          {label:"\u0628\u062f\u062a\u0631\u06cc\u0646 \u0645\u0639\u0627\u0645\u0644\u0647",value:metrics?`$${metrics.worst_trade.toFixed(2)}`:"\u2014"},
          {label:"\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0645\u062f\u062a",value:metrics?.avg_trade_duration??"\u2014"},
        ].map(({label,value})=>(
          <div key={label} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
            <p className="text-gray-400 text-sm mb-1">{label}</p>
            <p className="text-xl font-bold text-white">{value??"\u2014"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
