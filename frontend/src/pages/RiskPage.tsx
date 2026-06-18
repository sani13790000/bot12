import { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, TrendingDown, Activity, BarChart2, Lock } from "lucide-react";
import { riskApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import { StatCard } from "../components/common/StatCard";
import type { PortfolioRisk } from "../types";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";

export default function RiskPage() {
  const [risk, setRisk] = useState<PortfolioRisk | null>(null);
  const [loading, setLoading] = useState(true);
  const { on } = useWS();

  const load = async () => {
    setLoading(true);
    const r = await riskApi.getStatus();
    if (r.success) setRisk(r.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const off = on("RISK_ALERT", () => load());
    return off;
  }, [on]);

  const radarData = risk ? [
    { label: "Portfolio Risk", value: Math.min((risk.total_risk_percent / risk.max_allowed_percent) * 100, 100) },
    { label: "Daily Loss",     value: Math.min((risk.daily_loss_percent / 3) * 100, 100) },
    { label: "Weekly Loss",    value: Math.min((risk.weekly_loss_percent / 7) * 100, 100) },
    { label: "Drawdown",       value: Math.min((risk.equity_drawdown / 10) * 100, 100) },
    { label: "Correlation",    value: Math.min(risk.correlation_risk * 100, 100) },
    { label: "Trades Used",    value: Math.min((risk.daily_trades_used / risk.daily_trades_max) * 100, 100) },
  ] : [];

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#ef4444]/10 border border-[#ef4444]/30 flex items-center justify-center">
            <ShieldCheck size={20} className="text-[#ef4444]" />
          </div>
          <div>
            <h1 className="text-[#f0f6ff] text-xl font-bold">مدیریت ریسک</h1>
            <p className="text-[#475569] text-sm">ریسک‌سنج لحظه‌ای · 5 لایه حفاظتی</p>
          </div>
        </div>
        {risk?.halt_active && (
          <div className="flex items-center gap-2 bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-xl px-4 py-2">
            <Lock size={16} className="text-[#ef4444]" />
            <span className="text-[#ef4444] text-sm font-bold">HALT فعال</span>
          </div>
        )}
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="ریسک پرتفولیو"  value={risk?.total_risk_percent ?? 0}    format="percent"
          color={(risk?.total_risk_percent ?? 0) > 4 ? "red" : "green"} icon={<Activity size={18} />} glow />
        <StatCard title="ضرر روزانه"     value={risk?.daily_loss_percent ?? 0}     format="percent"
          color={(risk?.daily_loss_percent ?? 0) > 2.5 ? "red" : "green"} icon={<TrendingDown size={18} />} />
        <StatCard title="افت Equity"     value={risk?.equity_drawdown ?? 0}        format="percent"
          color={(risk?.equity_drawdown ?? 0) > 8 ? "red" : "gold"} icon={<ShieldAlert size={18} />} />
        <StatCard title="معاملات امروز"  value={`${risk?.daily_trades_used ?? 0}/${risk?.daily_trades_max ?? 5}`}
          color="accent" icon={<BarChart2 size={18} />} />
      </div>

      {/* Radar + Open Positions */}
      <div className="grid md:grid-cols-2 gap-5">
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">نقشه ریسک</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#1e2d40" />
                <PolarAngleAxis dataKey="label" tick={{ fill: "#475569", fontSize: 11 }} />
                <Radar dataKey="value" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.15} strokeWidth={2} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">پوزیشن‌های باز</h2>
          {(risk?.open_positions?.length ?? 0) === 0 ? (
            <div className="text-center py-8 text-[#475569]">پوزیشن بازی وجود ندارد</div>
          ) : (
            <div className="space-y-2">
              {risk?.open_positions?.map((pos, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-[#111827] border border-[#1e2d40]">
                  <div>
                    <span className="text-[#f0f6ff] text-sm font-semibold">{pos.symbol}</span>
                    <span className={`text-xs mr-2 ${pos.direction === "BUY" ? "text-[#10b981]" : "text-[#ef4444]"}`}>{pos.direction}</span>
                  </div>
                  <div className="text-left">
                    <div className="text-xs text-[#475569]">Risk</div>
                    <div className="text-[#f59e0b] text-sm font-bold">{pos.risk_percent.toFixed(2)}%</div>
                  </div>
                  <div className="text-left">
                    <div className="text-xs text-[#475569]">P&L</div>
                    <div className={`text-sm font-bold ${(pos.unrealized_pnl ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                      {(pos.unrealized_pnl ?? 0) >= 0 ? "+" : ""}{(pos.unrealized_pnl ?? 0).toFixed(2)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Currency Exposure */}
      {risk?.currency_exposure && Object.keys(risk.currency_exposure).length > 0 && (
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">ریسک ارزی</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(risk.currency_exposure).map(([ccy, pct]) => (
              <div key={ccy} className="bg-[#111827] rounded-xl p-3 border border-[#1e2d40]">
                <div className="text-[#475569] text-xs">{ccy}</div>
                <div className="text-[#f0f6ff] font-bold mt-1">{(pct as number).toFixed(2)}%</div>
                <div className="mt-2 h-1.5 bg-[#1e2d40] rounded-full overflow-hidden">
                  <div className="h-full bg-[#00d4ff] rounded-full transition-all" style={{ width: `${Math.min((pct as number) / 3 * 100, 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
