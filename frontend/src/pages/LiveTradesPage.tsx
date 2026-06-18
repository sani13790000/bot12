import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, RefreshCw, Clock } from "lucide-react";
import { tradesApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import type { Trade } from "../types";

function PnlBadge({ pnl }: { pnl?: number }) {
  if (pnl === undefined) return null;
  const pos = pnl >= 0;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${pos ? "bg-[#10b981]/15 text-[#10b981]" : "bg-[#ef4444]/15 text-[#ef4444]"}`}>
      {pos ? "+" : ""}{pnl.toFixed(2)}
    </span>
  );
}

export default function LiveTradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const { on } = useWS();

  const load = async () => { setLoading(true); const r = await tradesApi.getActive(); if (r.success) setTrades(r.data ?? []); setLoading(false); };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const off1 = on("TRADE_OPENED", () => load());
    const off2 = on("TRADE_CLOSED", () => load());
    const off3 = on("EQUITY_UPDATE", () => load());
    return () => { off1(); off2(); off3(); };
  }, [on]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-xl font-bold">معاملات زنده</h1>
          <p className="text-[#475569] text-sm mt-0.5">{trades.length} پوزیشن باز</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#111827] border border-[#1e2d40] text-[#475569] hover:text-[#f0f6ff] text-sm transition-all">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> رفرش
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>
      ) : trades.length === 0 ? (
        <div className="gv-card p-12 text-center">
          <Clock size={40} className="text-[#1e2d40] mx-auto mb-3" />
          <p className="text-[#475569]">هیچ معامله‌ای در حال اجرا نیست</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {trades.map(t => (
            <div key={t.id} className="gv-card p-4 border border-[#1e2d40] hover:border-[#00d4ff]/30 transition-all">
              <div className="flex items-start justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${t.direction === "BUY" ? "bg-[#10b981]/10" : "bg-[#ef4444]/10"}`}>
                    {t.direction === "BUY" ? <TrendingUp size={18} className="text-[#10b981]" /> : <TrendingDown size={18} className="text-[#ef4444]" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[#f0f6ff] font-bold">{t.symbol}</span>
                      <span className={`text-xs font-bold ${t.direction === "BUY" ? "text-[#10b981]" : "text-[#ef4444]"}`}>{t.direction}</span>
                    </div>
                    <div className="text-xs text-[#475569] mt-0.5">Lot: {t.lot_size} · Risk: {t.risk_percent.toFixed(2)}%</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <PnlBadge pnl={t.pnl} />
                  <span className="badge-active text-xs">{t.status}</span>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 pt-3 border-t border-[#1e2d40]">
                {[["Entry",      `$${t.entry_price}`],
                  ["Stop Loss",  `$${t.stop_loss}`],
                  ["TP1",        `$${t.take_profit_1}`],
                  ["Confidence", `${t.confidence_score}%`]].map(([k, v]) => (
                  <div key={k}>
                    <div className="text-[#475569] text-xs">{k}</div>
                    <div className="text-[#f0f6ff] text-sm font-semibold mt-0.5">{v}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
