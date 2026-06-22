/**
 * frontend/src/pages/TradesPage.tsx
 * FIX-FE13: tradesApi.list() did not exist — use listAll()
 * FIX-FE14: duplicate export default removed
 */
import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, XCircle } from "lucide-react";
import { tradesApi } from "../utils/api";
import type { Trade } from "../types";

const MOCK_TRADES: Trade[] = [
  { id:"t1", symbol:"XAUUSD", direction:"BUY",  entry_price:2341.50, stop_loss:2332.00, take_profit_1:2355.00, lot_size:0.10, status:"OPEN",   open_time:"2024-06-18T08:30:00Z", pnl:  34.50 },
  { id:"t2", symbol:"EURUSD", direction:"SELL", entry_price:1.0842,  stop_loss:1.0870,  take_profit_1:1.0790, lot_size:0.15, status:"OPEN",   open_time:"2024-06-18T09:15:00Z", pnl: -12.30 },
  { id:"t3", symbol:"GBPUSD", direction:"BUY",  entry_price:1.2680,  stop_loss:1.2640,  take_profit_1:1.2740, lot_size:0.08, status:"CLOSED", open_time:"2024-06-17T13:00:00Z", pnl: 115.20 },
];

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    OPEN:      { label: "باز",   cls: "bg-blue-500/20  text-blue-400"  },
    CLOSED:    { label: "بسته",  cls: "bg-gray-500/20  text-gray-400"  },
    PENDING:   { label: "معلق",  cls: "bg-amber-500/20 text-amber-400" },
    CANCELLED: { label: "لغو",   cls: "bg-red-500/20   text-red-400"   },
  };
  const c = cfg[status.toUpperCase()] ?? { label: status, cls: "bg-gray-500/20 text-gray-400" };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.cls}`}>{c.label}</span>;
}

function DirectionBadge({ direction }: { direction: string }) {
  const isBuy = direction.toUpperCase() === "BUY";
  return (
    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
      isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
    }`}>
      {isBuy ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {isBuy ? "خرید" : "فروش"}
    </span>
  );
}

export default function TradesPage() {
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [filter,  setFilter]  = useState<"ALL" | "OPEN" | "CLOSED">("ALL");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    tradesApi.listAll(200)
      .then(res => setTrades(res.success && res.data?.length ? res.data : MOCK_TRADES))
      .finally(() => setLoading(false));
  }, []);

  const handleClose = async (id: string) => {
    await tradesApi.close(id);
    setTrades(prev => prev.map(t => t.id === id ? { ...t, status: "CLOSED" } : t));
  };

  const filtered = filter === "ALL" ? trades : trades.filter(t => t.status?.toUpperCase() === filter);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">معاملات</h1>
        <div className="flex gap-2">
          {(["ALL", "OPEN", "CLOSED"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}>
              {f === "ALL" ? "همه" : f === "OPEN" ? "باز" : "بسته"}
            </button>
          ))}
        </div>
      </div>
      {loading && <div className="text-center py-10 text-gray-500">در حال بارگذاری...</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-xs">
              <th className="text-right pb-3 pr-2">نماد</th>
              <th className="text-right pb-3">جهت</th>
              <th className="text-right pb-3">حجم</th>
              <th className="text-right pb-3">ورود</th>
              <th className="text-right pb-3">SL</th>
              <th className="text-right pb-3">TP</th>
              <th className="text-right pb-3">P&L</th>
              <th className="text-right pb-3">وضعیت</th>
              <th className="pb-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {filtered.map(t => {
              const pnl = t.pnl ?? t.profit_loss ?? t.profit_money ?? 0;
              return (
                <tr key={t.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="py-3 pr-2 font-semibold text-white">{t.symbol}</td>
                  <td className="py-3"><DirectionBadge direction={String(t.direction)} /></td>
                  <td className="py-3 text-gray-300 font-mono">{(t.lot_size ?? t.volume ?? 0).toFixed(2)}</td>
                  <td className="py-3 text-gray-300 font-mono">{t.entry_price}</td>
                  <td className="py-3 text-rose-400 font-mono">{t.stop_loss ?? "\u2014"}</td>
                  <td className="py-3 text-emerald-400 font-mono">{t.take_profit_1 ?? t.take_profit ?? "\u2014"}</td>
                  <td className={`py-3 font-mono font-semibold ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
                  </td>
                  <td className="py-3"><StatusBadge status={String(t.status)} /></td>
                  <td className="py-3 pl-2">
                    {String(t.status).toUpperCase() === "OPEN" && (
                      <button onClick={() => handleClose(t.id)}
                        className="p-1.5 rounded-lg hover:bg-red-900/30 text-gray-500 hover:text-red-400 transition-colors">
                        <XCircle size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={9} className="py-10 text-center text-gray-500">معامله\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
