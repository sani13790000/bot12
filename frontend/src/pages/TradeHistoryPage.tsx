import { useState, useEffect, useMemo } from "react";
import { Filter, TrendingUp, TrendingDown, Search } from "lucide-react";
import { tradesApi } from "../utils/api";
import type { Trade } from "../types";

const SYMBOLS = ["همه","XAUUSD","EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD"];
const DIRS    = ["همه","BUY","SELL"];

export default function TradeHistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol]   = useState("همه");
  const [dir, setDir]         = useState("همه");
  const [search, setSearch]   = useState("");

  useEffect(() => {
    tradesApi.listHistory().then(r => {
      if (r.success) setTrades(r.data);
      setLoading(false);
    });
  }, []);

  const filtered = useMemo(() => trades.filter(t => {
    if (symbol !== "همه" && t.symbol !== symbol) return false;
    if (dir !== "همه" && t.direction !== dir) return false;
    if (search && !t.symbol.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [trades, symbol, dir, search]);

  const wins   = filtered.filter(t => (t.pnl ?? 0) > 0).length;
  const losses = filtered.filter(t => (t.pnl ?? 0) < 0).length;
  const totalPnl = filtered.reduce((s, t) => s + (t.pnl ?? 0), 0);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">تاریخچه معاملات</h1>
          <p className="text-[#475569] text-sm mt-1">{filtered.length} معامله — {wins} سود / {losses} زیان — P&L: <span className={totalPnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>${totalPnl.toFixed(2)}</span></p>
        </div>
      </div>

      {/* Filters */}
      <div className="gv-card p-4 flex flex-wrap items-center gap-3">
        <Filter size={15} className="text-[#475569]" />
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#475569]" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="جستجو نماد..."
            className="w-full bg-[#111827] border border-[#1e2d40] rounded-xl pr-9 pl-4 py-2 text-sm text-[#f0f6ff] outline-none focus:border-[#00d4ff]/50" />
        </div>
        <select value={symbol} onChange={e => setSymbol(e.target.value)}
          className="bg-[#111827] border border-[#1e2d40] rounded-xl px-3 py-2 text-sm text-[#f0f6ff] outline-none focus:border-[#00d4ff]/50">
          {SYMBOLS.map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={dir} onChange={e => setDir(e.target.value)}
          className="bg-[#111827] border border-[#1e2d40] rounded-xl px-3 py-2 text-sm text-[#f0f6ff] outline-none focus:border-[#00d4ff]/50">
          {DIRS.map(d => <option key={d}>{d}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="gv-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e2d40]">
                  {["نماد","جهت","ورود","خروج","لات","پیپ","P&L","RR","Session","تاریخ"].map(h => (
                    <th key={h} className="px-4 py-3 text-right text-[#475569] font-medium text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => (
                  <tr key={t.id} className="border-b border-[#1e2d40]/50 hover:bg-[#111827]/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-[#f0f6ff]">{t.symbol}</td>
                    <td className="px-4 py-3">
                      <span className={t.direction === "BUY" ? "badge-buy" : "badge-sell"}>{t.direction}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8] text-xs">{t.entry_price.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8] text-xs">{t.close_price?.toFixed(5) ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8]">{t.lot_size}</td>
                    <td className="px-4 py-3 font-mono">
                      <span className={(t.pips ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>
                        {t.pips !== undefined ? `${t.pips >= 0 ? "+" : ""}${t.pips.toFixed(1)}p` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold">
                      <span className={(t.pnl ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>
                        {t.pnl !== undefined ? `${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(2)}` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8]">{t.risk_reward_ratio.toFixed(2)}</td>
                    <td className="px-4 py-3 text-[#475569] text-xs">{t.session}</td>
                    <td className="px-4 py-3 text-[#475569] text-xs">{new Date(t.open_time).toLocaleDateString("fa-IR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
