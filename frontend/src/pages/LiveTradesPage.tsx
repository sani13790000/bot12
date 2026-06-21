/** frontend/src/pages/LiveTradesPage.tsx -- FIX-E5: Missing page */
import { useEffect, useState, useCallback } from "react";
import { tradesApi } from "../utils/api";
import type { Trade } from "../types";
import { RefreshCw, TrendingUp, TrendingDown, XCircle } from "lucide-react";

export default function LiveTradesPage() {
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState<string | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    tradesApi.listOpen()
      .then(r => { if (r.success) setTrades(r.data ?? []); else setError(r.error ?? "\u062e\u0637\u0627"); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 5_000); return () => clearInterval(id); }, [load]);

  const handleClose = async (id: string) => {
    if (!confirm("\u0622\u06cc\u0627 \u0645\u0637\u0645\u0626\u0646\u06cc\u062f\u061f")) return;
    setClosing(id);
    const r = await tradesApi.close(id);
    if (r.success) load(); else alert(r.error ?? "\u062e\u0637\u0627 \u062f\u0631 \u0628\u0633\u062a\u0646 \u0645\u0639\u0627\u0645\u0644\u0647");
    setClosing(null);
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0632\u0646\u062f\u0647</h1>
        <button onClick={load} className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {trades.length === 0 && !loading
        ? <div className="text-center py-20 text-gray-500">\u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0627\u0632 \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f</div>
        : (
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs uppercase">
                  {["\u0646\u0645\u0627\u062f","\u062c\u0647\u062a","\u062d\u062c\u0645","\u0648\u0631\u0648\u062f","SL","TP","P&L","\u0639\u0645\u0644\u06cc\u0627\u062a"].map(h => (
                    <th key={h} className="px-4 py-3 text-right">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {trades.map(t => (
                  <tr key={t.id} className="hover:bg-gray-800/50">
                    <td className="px-4 py-2.5 text-white font-medium">{t.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className={`flex items-center gap-1 font-bold text-xs ${t.direction==="BUY"?"text-green-400":"text-red-400"}`}>
                        {t.direction==="BUY"?<TrendingUp className="w-3 h-3"/>:<TrendingDown className="w-3 h-3"/>}{t.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-300 font-mono">{t.volume}</td>
                    <td className="px-4 py-2.5 text-gray-300 font-mono">{t.entry_price?.toFixed(5)}</td>
                    <td className="px-4 py-2.5 text-red-400 font-mono">{t.stop_loss?.toFixed(5)??"\u2014"}</td>
                    <td className="px-4 py-2.5 text-green-400 font-mono">{t.take_profit?.toFixed(5)??"\u2014"}</td>
                    <td className={`px-4 py-2.5 font-mono font-semibold ${(t.profit_loss??0)>=0?"text-green-400":"text-red-400"}`}>
                      {t.profit_loss!==undefined?`$${t.profit_loss.toFixed(2)}`:"\u2014"}
                    </td>
                    <td className="px-4 py-2.5">
                      <button onClick={()=>handleClose(t.id)} disabled={closing===t.id}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-900/30 text-red-400 hover:bg-red-900/60 disabled:opacity-50 text-xs">
                        <XCircle className="w-3.5 h-3.5"/>{closing===t.id?"...":"\u0628\u0633\u062a\u0646"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}
