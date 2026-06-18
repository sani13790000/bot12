import { useEffect, useState } from "react";
import { X, TrendingUp, TrendingDown, Clock, CheckCircle } from "lucide-react";
import { tradesApi } from "../utils/api";
import type { Trade } from "../types";

const MOCK_TRADES: Trade[] = [
  { id:"t1", symbol:"XAUUSD", direction:"BUY",  entry_price:2341.50, stop_loss:2334.00, take_profit_1:2352.00, take_profit_2:2362.00, lot_size:0.10, risk_percent:1.0, confidence_score:84, risk_level:"LOW",    status:"OPEN",   open_time:"2024-06-18T08:12:00Z", risk_reward_ratio:2.4, smc_score:0.82, pa_score:0.75, session:"London",   pnl:  38.50 },
  { id:"t2", symbol:"EURUSD", direction:"SELL", entry_price:1.0842,  stop_loss:1.0868,  take_profit_1:1.0790, take_profit_2:1.0750, lot_size:0.05, risk_percent:0.8, confidence_score:79, risk_level:"MEDIUM", status:"OPEN",   open_time:"2024-06-18T09:45:00Z", risk_reward_ratio:2.0, smc_score:0.71, pa_score:0.80, session:"London",   pnl: -12.30 },
  { id:"t3", symbol:"GBPUSD", direction:"BUY",  entry_price:1.2680,  stop_loss:1.2640,  take_profit_1:1.2740, take_profit_2:1.2800, lot_size:0.08, risk_percent:1.2, confidence_score:91, risk_level:"LOW",    status:"CLOSED", open_time:"2024-06-17T13:00:00Z", close_time:"2024-06-17T16:30:00Z", close_price:1.2738, risk_reward_ratio:2.8, smc_score:0.88, pa_score:0.85, session:"NewYork",  pnl: 115.20 },
  { id:"t4", symbol:"XAUUSD", direction:"SELL", entry_price:2358.00, stop_loss:2366.00, take_profit_1:2342.00, take_profit_2:2330.00, lot_size:0.12, risk_percent:1.5, confidence_score:76, risk_level:"MEDIUM", status:"CLOSED", open_time:"2024-06-17T06:00:00Z", close_time:"2024-06-17T10:00:00Z", close_price:2366.00, risk_reward_ratio:2.0, smc_score:0.68, pa_score:0.72, session:"Asian",    pnl: -96.00 },
];

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { label: string; className: string }> = {
    OPEN:      { label: "باز",     className: "badge-active" },
    CLOSED:    { label: "بسته",    className: "badge-buy" },
    CANCELLED: { label: "لغو",     className: "badge-wait" },
  };
  const c = cfg[status] ?? { label: status, className: "badge-wait" };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.className}`}>{c.label}</span>;
}

function DirectionBadge({ direction }: { direction: string }) {
  return (
    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${direction === "BUY" ? "badge-buy" : "badge-sell"}`}>
      {direction === "BUY" ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {direction === "BUY" ? "خرید" : "فروش"}
    </span>
  );
}

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filter, setFilter] = useState<"ALL" | "OPEN" | "CLOSED">("ALL");

  useEffect(() => {
    tradesApi.list().then((res) => {
      setTrades(res.success && res.data?.length ? res.data : MOCK_TRADES);
    });
  }, []);

  const filtered = filter === "ALL" ? trades : trades.filter((t) => t.status === filter);

  const openTrades  = trades.filter((t) => t.status === "OPEN");
  const totalPnl    = trades.reduce((s, t) => s + (t.pnl ?? 0), 0);
  const winCount    = trades.filter((t) => t.status === "CLOSED" && (t.pnl ?? 0) > 0).length;
  const closeCount  = trades.filter((t) => t.status === "CLOSED").length;

  const handleCloseAll = async () => {
    if (!confirm("همه معاملات باز بسته شود؟")) return;
    await tradesApi.closeAll();
    setTrades((prev) => prev.map((t) => t.status === "OPEN" ? { ...t, status: "CLOSED" } : t));
  };

  return (
    <div className="space-y-5">

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "معاملات باز",     value: openTrades.length,               color: "#00d4ff" },
          { label: "سود/زیان کل",    value: `${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`, color: totalPnl >= 0 ? "#10b981" : "#ef4444" },
          { label: "نرخ موفقیت",      value: closeCount ? `${Math.round(winCount/closeCount*100)}%` : "—", color: "#8b5cf6" },
          { label: "کل معاملات",      value: trades.length,                   color: "#f59e0b" },
        ].map(({ label, value, color }) => (
          <div key={label} className="gv-card p-4">
            <div className="metric-value" style={{ color }}>{value}</div>
            <div className="text-xs mt-1" style={{ color: "var(--gv-text-muted)" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Table header */}
      <div className="gv-card p-4">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex gap-2">
            {(["ALL", "OPEN", "CLOSED"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                style={{
                  background: filter === f ? "rgba(0,212,255,0.15)" : "var(--gv-bg-secondary)",
                  color: filter === f ? "var(--gv-accent)" : "var(--gv-text-muted)",
                  border: `1px solid ${filter === f ? "rgba(0,212,255,0.3)" : "var(--gv-border)"}`,
                }}
              >
                {f === "ALL" ? "همه" : f === "OPEN" ? "باز" : "بسته"}
              </button>
            ))}
          </div>
          {openTrades.length > 0 && (
            <button
              onClick={handleCloseAll}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}
            >
              <X size={12} />
              بستن همه
            </button>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--gv-border)" }}>
                {["نماد","جهت","ورود","SL","TP1","لات","ریسک%","امتیاز","PnL","R:R","وضعیت",""].map((h) => (
                  <th key={h} className="text-right pb-3 pr-2 font-medium" style={{ color: "var(--gv-text-muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr
                  key={t.id}
                  style={{ borderBottom: "1px solid var(--gv-border)" }}
                  className="transition-colors"
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--gv-bg-card-hover)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td className="py-3 pr-2 font-mono font-bold" style={{ color: "var(--gv-text-primary)" }}>{t.symbol}</td>
                  <td className="py-3 pr-2"><DirectionBadge direction={t.direction} /></td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "var(--gv-text-secondary)" }}>{t.entry_price}</td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "#ef4444" }}>{t.stop_loss}</td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "#10b981" }}>{t.take_profit_1}</td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "var(--gv-text-secondary)" }}>{t.lot_size}</td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "var(--gv-text-secondary)" }}>{t.risk_percent}%</td>
                  <td className="py-3 pr-2">
                    <div className="flex items-center gap-1">
                      <div className="w-12 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--gv-bg-secondary)" }}>
                        <div className="h-full rounded-full" style={{ width: `${t.confidence_score}%`, background: t.confidence_score >= 80 ? "#10b981" : "#f59e0b" }} />
                      </div>
                      <span style={{ color: t.confidence_score >= 80 ? "#10b981" : "#f59e0b" }}>{t.confidence_score}%</span>
                    </div>
                  </td>
                  <td className="py-3 pr-2 font-mono font-bold" style={{ color: (t.pnl ?? 0) >= 0 ? "#10b981" : "#ef4444" }}>
                    {t.pnl != null ? `${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-3 pr-2 font-mono" style={{ color: "var(--gv-text-secondary)" }}>1:{t.risk_reward_ratio}</td>
                  <td className="py-3 pr-2"><StatusBadge status={t.status} /></td>
                  <td className="py-3 pr-2">
                    {t.status === "OPEN" && (
                      <button
                        onClick={async () => { await tradesApi.close(t.id); setTrades((prev) => prev.map((x) => x.id === t.id ? { ...x, status: "CLOSED" } : x)); }}
                        className="p-1 rounded transition-colors"
                        style={{ color: "#ef4444" }}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-8 text-sm" style={{ color: "var(--gv-text-muted)" }}>
              معامله‌ای یافت نشد
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
