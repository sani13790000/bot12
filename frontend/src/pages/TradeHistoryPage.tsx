/** frontend/src/pages/TradeHistoryPage.tsx -- FIX-E6: Missing page */
import { useEffect, useState } from "react";
import { tradesApi } from "../utils/api";
import type { Trade } from "../types";
import { RefreshCw } from "lucide-react";

export default function TradeHistoryPage() {
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    tradesApi.listHistory()
      .then(r => { if (r.success) setTrades(r.data??[]); else setError(r.error??"\u062e\u0637\u0627"); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold text-white">\u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0645\u0639\u0627\u0645\u0644\u0627\u062a</h1>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {trades.length===0
        ? <div className="text-center py-20 text-gray-500">\u0645\u0639\u0627\u0645\u0644\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f</div>
        : <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead><tr className="border-b border-gray-800 text-gray-400 text-xs uppercase">
                {["\u0646\u0645\u0627\u062f","\u062c\u0647\u062a","\u062d\u062c\u0645","\u0648\u0631\u0648\u062f","P&L","\u062a\u0627\u0631\u06cc\u062e"].map(h=><th key={h} className="px-4 py-3 text-right">{h}</th>)}
              </tr></thead>
              <tbody className="divide-y divide-gray-800">
                {trades.map(t=>(
                  <tr key={t.id} className="hover:bg-gray-800/50">
                    <td className="px-4 py-2.5 text-white font-medium">{t.symbol}</td>
                    <td className={`px-4 py-2.5 font-bold text-sm ${t.direction==="BUY"?"text-green-400":"text-red-400"}`}>{t.direction}</td>
                    <td className="px-4 py-2.5 text-gray-300 font-mono">{t.volume}</td>
                    <td className="px-4 py-2.5 text-gray-300 font-mono">{t.entry_price?.toFixed(5)}</td>
                    <td className={`px-4 py-2.5 font-mono font-semibold ${(t.profit_loss??0)>=0?"text-green-400":"text-red-400"}`}>{t.profit_loss!==undefined?`$${t.profit_loss.toFixed(2)}`:"\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{new Date(t.closed_at??t.opened_at).toLocaleDateString("fa-IR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
    </div>
  );
}
