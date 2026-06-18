import { useEffect, useState } from "react";
import { X, XCircle, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import { tradesApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import type { Trade } from "../types";

function PnlBadge({ pnl }: { pnl?: number }) {
  if (pnl === undefined) return <span className="text-[#475569]">—</span>;
  return (
    <span className={`font-mono font-semibold ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
      {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
    </span>
  );
}

export default function LiveTradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState<string | null>(null);
  const { on } = useWS();

  const load = async () => {
    setLoading(true);
    const r = await tradesApi.listOpen();
    if (r.success) setTrades(r.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const off1 = on("TRADE_OPENED", load);
    const off2 = on("TRADE_CLOSED", load);
    const off3 = on("EQUITY_UPDATE", (d: Partial<Record<string, Trade[]>>) => {
      if (d && Array.isArray((d as Record<string, Trade[]>).trades)) {
        setTrades((d as Record<string, Trade[]>).trades);
      }
    });
    return () => { off1(); off2(); off3(); };
  }, [on]);

  const handleClose = async (id: string) => {
    setClosing(id);
    await tradesApi.close(id);
    await load();
    setClosing(null);
  };

  const handleCloseAll = async () => {
    setLoading(true);
    await tradesApi.closeAll();
    await load();
  };

  const totalPnl = trades.reduce((s, t) => s + (t.pnl ?? 0), 0);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">معاملات زنده</h1>
          <p className="text-[#475569] text-sm mt-1">{trades.length} معامله باز — P&L: <span className={totalPnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>${totalPnl.toFixed(2)}</span></p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="p-2 rounded-xl border border-[#1e2d40] text-[#94a3b8] hover:text-[#00d4ff] hover:border-[#00d4ff]/30 transition-all">
            <RefreshCw size={16} />
          </button>
          {trades.length > 0 && (
            <button onClick={handleCloseAll} className="px-4 py-2 bg-[#ef4444]/10 border border-[#ef4444]/30 text-[#ef4444] rounded-xl text-sm hover:bg-[#ef4444]/20 transition-all flex items-center gap-2">
              <XCircle size={15} /> بستن همه
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>
      ) : trades.length === 0 ? (
        <div className="gv-card p-12 text-center text-[#475569]">
          <TrendingUp size={40} className="mx-auto mb-3 opacity-30" />
          <p>هیچ معامله بازی وجود ندارد</p>
        </div>
      ) : (
        <div className="gv-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e2d40]">
                  {["نماد","جهت","ورود","SL","TP","لات","ریسک","P&L","اطمینان","زمان",""].map(h => (
                    <th key={h} className="px-4 py-3 text-right text-[#475569] font-medium text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <tr key={t.id} className="border-b border-[#1e2d40]/50 hover:bg-[#111827]/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-[#f0f6ff]">{t.symbol}</td>
                    <td className="px-4 py-3">
                      <span className={t.direction === "BUY" ? "badge-buy" : "badge-sell"}>
                        {t.direction === "BUY" ? <TrendingUp size={11} className="inline mr-1" /> : <TrendingDown size={11} className="inline mr-1" />}
                        {t.direction}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8]">{t.entry_price.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-[#ef4444]">{t.stop_loss.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-[#10b981]">{t.take_profit_1.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-[#94a3b8]">{t.lot_size}</td>
                    <td className="px-4 py-3 font-mono text-[#f59e0b]">{t.risk_percent.toFixed(1)}%</td>
                    <td className="px-4 py-3"><PnlBadge pnl={t.pnl} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-[#1e2d40] rounded-full overflow-hidden">
                          <div className="h-full bg-[#00d4ff] rounded-full" style={{ width: `${t.confidence_score}%` }} />
                        </div>
                        <span className="text-[#94a3b8] text-xs font-mono">{t.confidence_score.toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[#475569] text-xs">{new Date(t.open_time).toLocaleTimeString("fa")}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleClose(t.id)} disabled={closing === t.id}
                        className="p-1.5 rounded-lg text-[#475569] hover:text-[#ef4444] hover:bg-[#ef444410] transition-all disabled:opacity-50">
                        <X size={14} />
                      </button>
                    </td>
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
