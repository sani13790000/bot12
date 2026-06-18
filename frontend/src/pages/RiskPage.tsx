import { useEffect, useState } from "react";
import { ShieldAlert, AlertTriangle, CheckCircle, XCircle, RefreshCw } from "lucide-react";
import { riskApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import type { PortfolioRisk } from "../types";

function GaugeBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="w-full h-3 bg-[#1e2d40] rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export default function RiskPage() {
  const [risk, setRisk]   = useState<PortfolioRisk | null>(null);
  const [loading, setLoading] = useState(true);
  const { on } = useWS();

  const load = async () => {
    setLoading(true);
    const r = await riskApi.getPortfolio();
    if (r.success) setRisk(r.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { const off = on("RISK_ALERT", load); return off; }, [on]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">مدیریت ریسک</h1>
          <p className="text-[#475569] text-sm mt-1">وضعیت لحظه‌ای ریسک پرتفولیو</p>
        </div>
        <button onClick={load} className="p-2 rounded-xl border border-[#1e2d40] text-[#94a3b8] hover:text-[#00d4ff]">
          <RefreshCw size={16} />
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#ef4444] border-t-transparent rounded-full animate-spin" /></div>
      ) : !risk ? (
        <div className="gv-card p-12 text-center text-[#475569]">اطلاعات ریسک در دسترس نیست</div>
      ) : (
        <>
          {/* Halt Alert */}
          {risk.halt_active && (
            <div className="p-4 bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-xl flex items-center gap-3">
              <AlertTriangle size={20} className="text-[#ef4444]" />
              <div>
                <div className="text-[#ef4444] font-bold">سیستم متوقف شده است</div>
                <div className="text-[#ef4444]/70 text-sm">Equity Protection فعال است — معاملات جدید مسدود</div>
              </div>
              <button onClick={() => riskApi.resumeHalt().then(load)}
                className="mr-auto px-4 py-2 bg-[#ef4444] text-white rounded-xl text-sm font-bold hover:bg-[#dc2626]">
                لغو توقف
              </button>
            </div>
          )}

          {/* Trade Status */}
          <div className={`gv-card p-5 flex items-center gap-4 ${risk.can_open_new_trade ? "border-[#10b981]/30" : "border-[#ef4444]/30"}`}>
            {risk.can_open_new_trade
              ? <CheckCircle size={24} className="text-[#10b981]" />
              : <XCircle    size={24} className="text-[#ef4444]" />}
            <div>
              <div className={`font-bold ${risk.can_open_new_trade ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                {risk.can_open_new_trade ? "معاملات جدید مجاز است" : "معاملات جدید مسدود است"}
              </div>
              <div className="text-[#475569] text-sm">
                ریسک پرتفولیو: {risk.total_risk_percent.toFixed(2)}% از {risk.max_allowed_percent}%
              </div>
            </div>
          </div>

          {/* Risk Gauges */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="gv-card p-5 space-y-4">
              <h2 className="text-[#f0f6ff] font-semibold flex items-center gap-2">
                <ShieldAlert size={16} className="text-[#f59e0b]" /> محدودیت‌های ریسک
              </h2>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">ریسک پرتفولیو</span>
                  <span className="font-mono text-[#f59e0b]">{risk.total_risk_percent.toFixed(2)}% / {risk.max_allowed_percent}%</span>
                </div>
                <GaugeBar value={risk.total_risk_percent} max={risk.max_allowed_percent} color={risk.total_risk_percent > risk.max_allowed_percent * 0.8 ? "#ef4444" : "#f59e0b"} />
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">ضرر روزانه</span>
                  <span className="font-mono text-[#ef4444]">{risk.daily_loss_percent.toFixed(2)}% / 3%</span>
                </div>
                <GaugeBar value={risk.daily_loss_percent} max={3} color="#ef4444" />
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">ضرر هفتگی</span>
                  <span className="font-mono text-[#ef4444]">{risk.weekly_loss_percent.toFixed(2)}% / 7%</span>
                </div>
                <GaugeBar value={risk.weekly_loss_percent} max={7} color="#ef4444" />
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">Equity Drawdown</span>
                  <span className="font-mono text-[#ef4444]">{risk.equity_drawdown.toFixed(2)}% / 10%</span>
                </div>
                <GaugeBar value={risk.equity_drawdown} max={10} color="#ef4444" />
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">معاملات امروز</span>
                  <span className="font-mono text-[#00d4ff]">{risk.daily_trades_used} / {risk.daily_trades_max}</span>
                </div>
                <GaugeBar value={risk.daily_trades_used} max={risk.daily_trades_max} color="#00d4ff" />
              </div>
            </div>

            {/* Currency Exposure */}
            <div className="gv-card p-5">
              <h2 className="text-[#f0f6ff] font-semibold mb-4">Currency Exposure</h2>
              <div className="space-y-3">
                {Object.entries(risk.currency_exposure).map(([cur, pct]) => (
                  <div key={cur}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-mono text-[#94a3b8]">{cur}</span>
                      <span className="font-mono" style={{ color: (pct as number) > 2.5 ? "#ef4444" : "#10b981" }}>{(pct as number).toFixed(2)}%</span>
                    </div>
                    <GaugeBar value={pct as number} max={3} color={(pct as number) > 2.5 ? "#ef4444" : "#10b981"} />
                  </div>
                ))}
                {Object.keys(risk.currency_exposure).length === 0 && (
                  <p className="text-[#475569] text-sm text-center py-4">هیچ پوزیشن بازی وجود ندارد</p>
                )}
              </div>
            </div>
          </div>

          {/* Open Positions */}
          {risk.open_positions.length > 0 && (
            <div className="gv-card overflow-hidden">
              <div className="px-5 py-4 border-b border-[#1e2d40]"><h2 className="text-[#f0f6ff] font-semibold">پوزیشن‌های باز</h2></div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-[#1e2d40]">
                    {["نماد","جهت","ریسک","P&L","همبستگی"].map(h => <th key={h} className="px-4 py-3 text-right text-[#475569] text-xs">{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {risk.open_positions.map((p, i) => (
                      <tr key={i} className="border-b border-[#1e2d40]/50 hover:bg-[#111827]/50">
                        <td className="px-4 py-3 font-mono font-semibold text-[#f0f6ff]">{p.symbol}</td>
                        <td className="px-4 py-3"><span className={p.direction === "BUY" ? "badge-buy" : "badge-sell"}>{p.direction}</span></td>
                        <td className="px-4 py-3 font-mono text-[#f59e0b]">{p.risk_percent.toFixed(2)}%</td>
                        <td className="px-4 py-3 font-mono"><span className={p.unrealized_pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>${p.unrealized_pnl.toFixed(2)}</span></td>
                        <td className="px-4 py-3 text-[#94a3b8] text-xs">{p.correlation_group}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
